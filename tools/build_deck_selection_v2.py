"""Phase 4.3b -- High-Resolution Walk-Forward Validation.

Diagnostic experiment: determine whether Phase 4.3's weak result was caused by
insufficient temporal resolution (weekly decisions), insufficient training-window
design, or unstable matchup estimates -- vs. meta-aware selection genuinely
carrying little deployable predictive value.

Reads ONLY results/meta/episodes_summary.parquet. No new episodes downloaded.
Rating never used. No RL/MCTS/search/opponent-inference/agent code here --
this is an evaluation script, same as Phase 4.3.

Writes:
  results/meta/daily_walk_forward.csv
  results/meta/window_comparison.csv
  results/meta/ogerpon_grimmsnarl_walk_forward.csv
  results/meta/counter_detection.csv
  results/meta/regime_analysis.csv
  results/meta/high_resolution_sensitivity.csv
"""
from __future__ import annotations

import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon

OUT_DIR = os.path.join(REPO_ROOT, "results", "meta")
PARQUET = os.path.join(OUT_DIR, "episodes_summary.parquet")

# ================= documented constants =================
CANDIDATE_MIN_GAMES = 50          # same absolute bar applied to EVERY window, for a fair comparison
MATCHUP_INSUFFICIENT = 20
MATCHUP_USABLE = 50
MATCHUP_HIGH = 100
SHRINKAGE_K = 30
ORACLE_MIN_TEST_GAMES = 10        # lower than Phase 4.3's 20: daily test samples are much smaller than weekly
COUNTER_DETECTION_MIN_GAMES = 50  # identical to Phase 4.2's credible-counter gate, per Sec 17's instruction to reuse it
COUNTER_DETECTION_WILSON_LO = 0.50

WINDOWS = {"7d": 7, "14d": 14, "30d": 30, "full": None}
RNG = np.random.default_rng(20260811)  # fixed seed, documented, for reproducible bootstrap CIs
N_BOOTSTRAP = 2000


def wilson_ci(wins, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def confidence_flag(n, usable=MATCHUP_USABLE):
    if n < MATCHUP_INSUFFICIENT:
        return "INSUFFICIENT"
    elif n < usable:
        return "LOW_CONFIDENCE"
    elif n < MATCHUP_HIGH:
        return "USABLE"
    else:
        return "HIGH_CONFIDENCE"


def shrinkage_wr(wins, n, k=SHRINKAGE_K, prior=0.5):
    return (wins + k * prior) / (n + k)


def load_data():
    df = pd.read_parquet(PARQUET)
    decisive = df[df["outcome_type"] == "DECISIVE"].copy()
    decisive["date_dt"] = pd.to_datetime(decisive["date"]).dt.normalize()
    decisive["timestamp_dt"] = pd.to_datetime(decisive["timestamp"])
    return decisive.sort_values("timestamp_dt")


def get_train_slice(decisive, T, window_days):
    if window_days is None:
        return decisive[decisive["date_dt"] < T]
    lo = T - pd.Timedelta(days=window_days)
    return decisive[(decisive["date_dt"] < T) & (decisive["date_dt"] >= lo)]


def get_test_slice(decisive, T):
    return decisive[decisive["date_dt"] == T]


class WindowStats:
    """All stats computed from ONE training slice -- recency is entirely encoded
    by which slice (7d/14d/30d/full) was passed in, per Sec 9's instruction that
    Strategy D/E's prior must come from the SAME rolling training window."""

    def __init__(self, train_df):
        self.train_df = train_df
        self.total_games = len(train_df)
        if self.total_games == 0:
            self.games, self.wins, self.candidates, self.full_prior = {}, {}, set(), {}
            self.pair_games, self.pair_wins = {}, {}
            return
        g = train_df.groupby("player_deck_cluster_id")
        self.games = g.size().to_dict()
        self.wins = g.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False).to_dict()
        self.candidates = {cid for cid, n in self.games.items() if n >= CANDIDATE_MIN_GAMES}
        self.full_prior = {cid: n / self.total_games for cid, n in self.games.items()}
        pg = train_df.groupby(["player_deck_cluster_id", "opponent_deck_cluster_id"])
        self.pair_games = pg.size().to_dict()
        self.pair_wins = pg.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False).to_dict()

    def win_rate(self, cid):
        n = self.games.get(cid, 0)
        return (self.wins.get(cid, 0) / n) if n else None

    def shrinkage(self, cid):
        return shrinkage_wr(self.wins.get(cid, 0), self.games.get(cid, 0))

    def matchup_estimate(self, a, b, mode, usable_threshold=MATCHUP_USABLE):
        n = self.pair_games.get((a, b), 0)
        w = self.pair_wins.get((a, b), 0)
        conf = confidence_flag(n, usable_threshold)
        usable = conf in ("USABLE", "HIGH_CONFIDENCE")

        if mode == "conservative":
            if n > 0:
                _, lo, _ = wilson_ci(w, n)
                return lo, conf, "wilson_lo"
            fb = np.clip(self.shrinkage(a) - self.shrinkage(b) + 0.5, 0.05, 0.95)
            return fb, conf, "fallback_policy2"

        if usable:
            return w / n, conf, "empirical"
        if mode == "policy1_neutral":
            return 0.5, conf, "fallback_policy1_neutral"
        fb = np.clip(self.shrinkage(a) - self.shrinkage(b) + 0.5, 0.05, 0.95)
        return fb, conf, "fallback_policy2"

    def expected_win_rate(self, a, prior, mode, usable_threshold=MATCHUP_USABLE):
        total, weight_seen = 0.0, 0.0
        for b, pb in prior.items():
            est, _, _ = self.matchup_estimate(a, b, mode, usable_threshold)
            total += pb * est
            weight_seen += pb
        return total / weight_seen if weight_seen > 0 else None

    def credible_counter_count(self, a, usable_threshold=MATCHUP_USABLE):
        cnt = 0
        for (x, y), n in self.pair_games.items():
            if x != a or n < usable_threshold:
                continue
            w = self.pair_wins.get((x, y), 0)
            _, lo, _ = wilson_ci(w, n)
            if lo > 0.5:
                cnt += 1
        return cnt


# ================= strategies =================

def strategy_A(ws):
    if not ws.candidates:
        return None, None, "no_candidates"
    a = max(ws.candidates, key=lambda c: ws.full_prior.get(c, 0))
    return a, ws.full_prior.get(a), "argmax_usage_share_in_window"


def strategy_BC(ws):
    """Highest win rate within the training window -- named B (Highest Historical
    Win Rate) when the window is full-history, C (Recent Win Rate) when the window
    is 7/14/30 days, per Sec 7's instruction that C IS 'the current rolling training
    window' -- mechanically the same computation, the label is what changes."""
    if not ws.candidates:
        return None, None, "no_candidates"
    a = max(ws.candidates, key=lambda c: (ws.win_rate(c), ws.games.get(c, 0)))
    return a, ws.win_rate(a), "argmax_window_win_rate"


def strategy_D(ws, mode="policy2"):
    if not ws.candidates:
        return None, None, "no_candidates"
    scored = {c: ws.expected_win_rate(c, ws.full_prior, mode) for c in ws.candidates}
    a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
    return a, scored[a], f"argmax_EWR_window_prior_{mode}"


def strategy_E(ws):
    if not ws.candidates:
        return None, None, "no_candidates"
    scored = {c: ws.expected_win_rate(c, ws.full_prior, "conservative") for c in ws.candidates}
    a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
    return a, scored[a], "argmax_conservative_EWR_wilson_lo"


def evaluate_selection(test_df, cid):
    if cid is None:
        return None, None, None
    sub = test_df[test_df["player_deck_cluster_id"] == cid]
    n = len(sub)
    if n == 0:
        return 0, 0, None
    w = int((sub["result"] == "WIN").sum())
    return n, w, w / n


def oracle(test_df):
    if len(test_df) == 0:
        return None, None, "no_test_data"
    g = test_df.groupby("player_deck_cluster_id")
    games = g.size()
    wins = g.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False)
    elig = games[games >= ORACLE_MIN_TEST_GAMES].index
    if len(elig) == 0:
        return None, None, "no_archetype_cleared_oracle_min_sample"
    wr = wins[elig] / games[elig]
    a = wr.idxmax()
    return a, wr[a], "ORACLE_NOT_AVAILABLE_AT_DECISION_TIME"


# ================= main daily walk-forward grid =================

def run_daily_walk_forward(decisive):
    dates = sorted(decisive["date_dt"].unique())
    rows = []
    oracle_rows = []
    skip_log = []

    for T in dates[1:]:  # first date has no possible training data under any window
        test_df = get_test_slice(decisive, T)
        o_cid, o_wr, o_note = oracle(test_df)
        o_n, o_w, o_wr_actual = evaluate_selection(test_df, o_cid)
        oracle_rows.append({
            "decision_day": T.date().isoformat(), "selected_archetype": o_cid,
            "test_games": o_n, "wins": o_w, "losses": (o_n - o_w) if o_n else None,
            "win_rate": round(o_wr_actual, 4) if o_wr_actual is not None else None,
            "note": o_note,
        })

        for window_label, window_days in WINDOWS.items():
            train_df = get_train_slice(decisive, T, window_days)
            ws = WindowStats(train_df)

            training_start = train_df["date_dt"].min() if len(train_df) else None
            training_end = train_df["date_dt"].max() if len(train_df) else None
            latest_train_ts = train_df["timestamp_dt"].max() if len(train_df) else None
            first_test_ts = test_df["timestamp_dt"].min() if len(test_df) else None
            last_test_ts = test_df["timestamp_dt"].max() if len(test_df) else None

            if not ws.candidates:
                skip_log.append({"decision_day": T.date().isoformat(), "training_window": window_label,
                                  "reason": "no_candidates", "training_games": ws.total_games})
                for strat_label in ["A_most_popular", "B_or_C_wr", "D_meta_aware_ewr",
                                    "D_policy1_neutral_variant", "E_conservative_meta_aware"]:
                    label = strat_label
                    if strat_label == "B_or_C_wr":
                        label = "B_highest_historical_wr" if window_label == "full" else "C_recent_wr"
                    rows.append(_row(T, window_label, label, None, None, None, ws, None, None, None,
                                      training_start, training_end, latest_train_ts, first_test_ts, last_test_ts,
                                      "SKIPPED_NO_CANDIDATES"))
                continue

            strat_defs = [
                ("A_most_popular", strategy_A(ws)),
                (("B_highest_historical_wr" if window_label == "full" else "C_recent_wr"), strategy_BC(ws)),
                ("D_meta_aware_ewr", strategy_D(ws, "policy2")),
                ("D_policy1_neutral_variant", strategy_D(ws, "policy1_neutral")),
                ("E_conservative_meta_aware", strategy_E(ws)),
            ]
            for label, (cid, sel_metric, note) in strat_defs:
                n, w, wr = evaluate_selection(test_df, cid)
                status = "OK" if n and n > 0 else ("SKIPPED_NO_TEST_DATA" if cid is not None else "SKIPPED_NO_SELECTION")
                ewr, counters = None, None
                if label in ("D_meta_aware_ewr", "D_policy1_neutral_variant", "E_conservative_meta_aware") and cid is not None:
                    ewr = sel_metric
                    counters = ws.credible_counter_count(cid)
                rows.append(_row(T, window_label, label, cid, sel_metric, note, ws, n, w, wr,
                                  training_start, training_end, latest_train_ts, first_test_ts, last_test_ts,
                                  status, expected_win_rate=ewr, credible_counter_count=counters))

    return pd.DataFrame(rows), pd.DataFrame(oracle_rows), pd.DataFrame(skip_log)


def _row(T, window_label, strategy, cid, sel_metric, note, ws, n, w, wr,
         training_start, training_end, latest_train_ts, first_test_ts, last_test_ts,
         status, expected_win_rate=None, credible_counter_count=None):
    leak_ok = None
    if latest_train_ts is not None and first_test_ts is not None:
        leak_ok = bool(latest_train_ts < first_test_ts)
    return {
        "decision_day": T.date().isoformat(), "training_window": window_label, "strategy": strategy,
        "selected_archetype": cid,
        "training_games": ws.total_games, "test_games": n if n is not None else 0,
        "training_start": training_start.date().isoformat() if training_start is not None else None,
        "training_end": training_end.date().isoformat() if training_end is not None else None,
        "test_start": T.date().isoformat(), "test_end": T.date().isoformat(),
        "wins": w, "losses": (n - w) if (n is not None and w is not None) else None,
        "win_rate": round(wr, 4) if wr is not None else None,
        "candidate_count": len(ws.candidates),
        "selected_deck_training_games": ws.games.get(cid, None) if cid else None,
        "selected_deck_training_win_rate": round(ws.win_rate(cid), 4) if cid and ws.win_rate(cid) is not None else None,
        "selected_deck_training_share": round(ws.full_prior.get(cid, 0), 4) if cid else None,
        "expected_win_rate": round(expected_win_rate, 4) if expected_win_rate is not None else None,
        "credible_counter_count": credible_counter_count,
        "selection_note": note, "status": status,
        "decision_timestamp": pd.Timestamp(T).isoformat(),
        "latest_training_timestamp": latest_train_ts.isoformat() if latest_train_ts is not None else None,
        "first_test_timestamp": first_test_ts.isoformat() if first_test_ts is not None else None,
        "last_test_timestamp": last_test_ts.isoformat() if last_test_ts is not None else None,
        "latest_train_before_first_test": leak_ok,
    }


# ================= window comparison with day-block bootstrap =================

def block_bootstrap_ci(day_games, day_wins, n_boot=N_BOOTSTRAP):
    """Resamples DAYS (not games) with replacement -- the correct unit given
    consecutive days share heavily-overlapping training data and are not
    independent experiments. Returns (point_estimate, lo95, hi95)."""
    days = list(day_games.keys())
    if not days:
        return None, None, None
    total_g = sum(day_games.values())
    total_w = sum(day_wins.values())
    point = total_w / total_g if total_g else None
    if len(days) < 2 or total_g == 0:
        return point, None, None
    boot_wrs = []
    for _ in range(n_boot):
        sample_days = RNG.choice(days, size=len(days), replace=True)
        g = sum(day_games[d] for d in sample_days)
        w = sum(day_wins[d] for d in sample_days)
        if g > 0:
            boot_wrs.append(w / g)
    if not boot_wrs:
        return point, None, None
    lo, hi = np.percentile(boot_wrs, [2.5, 97.5])
    return point, float(lo), float(hi)


def build_window_comparison(daily_df):
    rows = []
    valid = daily_df[(daily_df["status"] == "OK")]
    for (strategy, window), g in valid.groupby(["strategy", "training_window"]):
        day_games = g.groupby("decision_day")["test_games"].sum().to_dict()
        day_wins = g.groupby("decision_day")["wins"].sum().to_dict()
        point, lo, hi = block_bootstrap_ci(day_games, day_wins)
        daily_wrs = g["win_rate"].dropna()
        rows.append({
            "strategy": strategy, "training_window": window,
            "n_decision_days": g["decision_day"].nunique(),
            "n_games": int(g["test_games"].sum()), "n_wins": int(g["wins"].sum()),
            "pooled_oos_win_rate": round(point, 4) if point is not None else None,
            "bootstrap_ci_lo": round(lo, 4) if lo is not None else None,
            "bootstrap_ci_hi": round(hi, 4) if hi is not None else None,
            "median_daily_win_rate": round(daily_wrs.median(), 4) if len(daily_wrs) else None,
            "std_daily_win_rate": round(daily_wrs.std(), 4) if len(daily_wrs) > 1 else None,
        })
    # also add oracle summary per training_window is meaningless (oracle has no window) -- add once, label window='n/a'
    return pd.DataFrame(rows).sort_values(["strategy", "training_window"])


# ================= Ogerpon -> Grimmsnarl walk-forward =================

def build_ogerpon_grimmsnarl(decisive):
    TARGET_A, TARGET_B = "Teal Mask Ogerpon ex", "Marnie's Grimmsnarl ex"
    dates = sorted(decisive["date_dt"].unique())
    rows = []
    for T in dates[1:]:
        train_df = get_train_slice(decisive, T, None)  # full history before T
        test_df = get_test_slice(decisive, T)
        pair_hist = train_df[(train_df["player_deck_cluster_id"] == TARGET_A) &
                              (train_df["opponent_deck_cluster_id"] == TARGET_B)]
        n_hist = len(pair_hist)
        w_hist = int((pair_hist["result"] == "WIN").sum())
        wr_hist = w_hist / n_hist if n_hist else None
        _, lo_hist, _ = wilson_ci(w_hist, n_hist) if n_hist else (0, 0, 0)

        grimm_train = train_df[train_df["player_deck_cluster_id"] == TARGET_B]
        grimm_share = len(grimm_train) / len(train_df) if len(train_df) else None

        ws = WindowStats(train_df)
        selected_by_D = None
        if ws.candidates:
            cid, _, _ = strategy_D(ws, "policy2")
            selected_by_D = (cid == TARGET_A)

        pair_future = test_df[(test_df["player_deck_cluster_id"] == TARGET_A) &
                               (test_df["opponent_deck_cluster_id"] == TARGET_B)]
        n_fut = len(pair_future)
        w_fut = int((pair_future["result"] == "WIN").sum()) if n_fut else None

        rows.append({
            "decision_day": T.date().isoformat(),
            "historical_games": n_hist, "historical_win_rate": round(wr_hist, 4) if wr_hist is not None else None,
            "historical_wilson_lo": round(lo_hist, 4),
            "is_credible_counter": bool(n_hist >= COUNTER_DETECTION_MIN_GAMES and lo_hist > COUNTER_DETECTION_WILSON_LO),
            "grimmsnarl_meta_share_in_training": round(grimm_share, 4) if grimm_share is not None else None,
            "selected_by_meta_aware_D": selected_by_D,
            "future_day_games": n_fut, "future_day_wins": w_fut,
            "future_day_win_rate": round(w_fut / n_fut, 4) if n_fut else None,
        })
    return pd.DataFrame(rows)


# ================= counter detection (Sec 17-18) =================

def build_counter_detection(decisive, targets):
    dates = sorted(decisive["date_dt"].unique())
    all_archetypes = decisive["player_deck_cluster_id"].unique()
    rows = []
    for target in targets:
        detection_date = None
        detection_counter = None
        detection_hist_estimate = None
        detection_hist_n = None
        for T in dates[1:]:
            train_df = get_train_slice(decisive, T, None)
            found = []
            for cand in all_archetypes:
                if cand == target:
                    continue
                pair = train_df[(train_df["player_deck_cluster_id"] == cand) &
                                 (train_df["opponent_deck_cluster_id"] == target)]
                n = len(pair)
                if n < COUNTER_DETECTION_MIN_GAMES:
                    continue
                w = int((pair["result"] == "WIN").sum())
                _, lo, _ = wilson_ci(w, n)
                if lo > COUNTER_DETECTION_WILSON_LO:
                    found.append((cand, n, w / n, lo))
            if found:
                # pick the strongest (highest wilson_lo) if multiple cross the bar simultaneously
                found.sort(key=lambda x: -x[3])
                detection_date = T
                detection_counter, detection_hist_n, hist_wr, hist_lo = found[0]
                detection_hist_estimate = hist_wr
                break

        if detection_date is None:
            rows.append({"target_archetype": target, "counter_archetype": None,
                          "detection_date": None, "historical_estimate_at_detection": None,
                          "historical_n_at_detection": None,
                          "future_oos_games": None, "future_oos_wins": None, "future_oos_win_rate": None,
                          "note": "no_credible_counter_detected_within_dataset"})
            continue

        future = decisive[(decisive["date_dt"] >= detection_date) &
                           (decisive["player_deck_cluster_id"] == detection_counter) &
                           (decisive["opponent_deck_cluster_id"] == target)]
        n_fut = len(future)
        w_fut = int((future["result"] == "WIN").sum()) if n_fut else None
        rows.append({
            "target_archetype": target, "counter_archetype": detection_counter,
            "detection_date": detection_date.date().isoformat(),
            "historical_estimate_at_detection": round(detection_hist_estimate, 4),
            "historical_n_at_detection": detection_hist_n,
            "future_oos_games": n_fut, "future_oos_wins": w_fut,
            "future_oos_win_rate": round(w_fut / n_fut, 4) if n_fut else None,
            "note": f"detected using games strictly before {detection_date.date().isoformat()}, "
                    f"evaluated on games from that date onward (inclusive)",
        })
    return pd.DataFrame(rows)


# ================= regime analysis (Sec 19) =================

def build_regime_analysis(decisive, daily_df):
    dates = sorted(decisive["date_dt"].unique())
    universe = sorted(decisive["player_deck_cluster_id"].unique())
    day_dist = {}
    for d in dates:
        counts = decisive[decisive["date_dt"] == d]["player_deck_cluster_id"].value_counts()
        vec = np.array([counts.get(u, 0) for u in universe], dtype=float)
        day_dist[d] = vec / vec.sum() if vec.sum() else vec

    js_rows = []
    for i in range(1, len(dates)):
        d, d_prev = dates[i], dates[i - 1]
        js = jensenshannon(day_dist[d_prev], day_dist[d], base=2)
        js_rows.append({"date": d.date().isoformat(), "js_divergence_vs_prev_day": float(js) if not np.isnan(js) else None})
    js_df = pd.DataFrame(js_rows)

    vals = js_df["js_divergence_vs_prev_day"].dropna()
    t1, t2 = np.percentile(vals, [33.33, 66.67])
    def classify(v):
        if v is None or np.isnan(v):
            return None
        if v <= t1:
            return "stable"
        elif v <= t2:
            return "moderately_changing"
        else:
            return "rapidly_changing"
    js_df["regime"] = js_df["js_divergence_vs_prev_day"].apply(classify)
    js_df["tercile_lo"] = round(float(t1), 6)
    js_df["tercile_hi"] = round(float(t2), 6)

    merged = daily_df[daily_df["status"] == "OK"].merge(
        js_df[["date", "regime"]], left_on="decision_day", right_on="date", how="left")
    summary = merged.groupby(["strategy", "training_window", "regime"], dropna=True).agg(
        n_days=("decision_day", "nunique"), n_games=("test_games", "sum"), n_wins=("wins", "sum")
    ).reset_index()
    summary["regime_win_rate"] = summary.apply(lambda r: round(r["n_wins"] / r["n_games"], 4) if r["n_games"] else None, axis=1)

    combined = pd.concat([js_df.assign(_section="daily_js"), summary.assign(_section="performance_by_regime")],
                          axis=0, ignore_index=True)
    return combined


# ================= high-resolution sensitivity (Sec 20, current decision only) =================

def exp_weighted_prior(decisive, T, halflife_days):
    train_df = decisive[decisive["date_dt"] < T]
    if len(train_df) == 0:
        return {}
    age_days = (T - train_df["date_dt"]).dt.days.values
    lam = math.log(2) / halflife_days
    weights = np.exp(-lam * age_days)
    tmp = pd.DataFrame({"cid": train_df["player_deck_cluster_id"].values, "w": weights})
    agg = tmp.groupby("cid")["w"].sum()
    total = agg.sum()
    return (agg / total).to_dict() if total else {}


def build_sensitivity(decisive):
    dates = sorted(decisive["date_dt"].unique())
    T = dates[-1] + pd.Timedelta(days=1)  # "today" = the day after the last observed date
    rows = []

    # (a) training window
    baseline_window = "full"
    window_picks = {}
    for wl, wd in WINDOWS.items():
        train_df = get_train_slice(decisive, T, wd)
        ws = WindowStats(train_df)
        if not ws.candidates:
            window_picks[wl] = (None, None)
            continue
        a, ewr, _ = strategy_D(ws, "policy2")
        window_picks[wl] = (a, ewr)
    baseline_a = window_picks[baseline_window][0]
    for wl, (a, ewr) in window_picks.items():
        rows.append({"variant_type": "training_window", "variant_value": wl,
                      "selected_archetype": a, "expected_win_rate": round(ewr, 4) if ewr is not None else None,
                      "changed_from_default": a != baseline_a})

    # (b) matchup min-sample threshold (full-history window)
    full_train = get_train_slice(decisive, T, None)
    ws_full = WindowStats(full_train)
    baseline_thr = MATCHUP_USABLE
    thr_picks = {}
    for thr in [20, 50, 100]:
        scored = {c: ws_full.expected_win_rate(c, ws_full.full_prior, "policy2", usable_threshold=thr) for c in ws_full.candidates}
        a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1)) if scored else None
        thr_picks[thr] = (a, scored.get(a))
    baseline_thr_a = thr_picks[baseline_thr][0]
    for thr, (a, ewr) in thr_picks.items():
        rows.append({"variant_type": "matchup_min_sample_threshold", "variant_value": thr,
                      "selected_archetype": a, "expected_win_rate": round(ewr, 4) if ewr is not None else None,
                      "changed_from_default": a != baseline_thr_a})

    # (c) uncertainty handling
    a_raw, ewr_raw, _ = strategy_D(ws_full, "policy2")
    a_cons, ewr_cons, _ = strategy_E(ws_full)
    rows.append({"variant_type": "uncertainty_handling", "variant_value": "raw_with_fallback",
                  "selected_archetype": a_raw, "expected_win_rate": round(ewr_raw, 4) if ewr_raw is not None else None,
                  "changed_from_default": False})
    rows.append({"variant_type": "uncertainty_handling", "variant_value": "conservative_wilson_lower",
                  "selected_archetype": a_cons, "expected_win_rate": round(ewr_cons, 4) if ewr_cons is not None else None,
                  "changed_from_default": a_cons != a_raw})

    # (d) meta prior type: rolling window (full-history) vs exponential recency-weighting (2 documented half-lives)
    prior_variants = {
        "rolling_full_history": ws_full.full_prior,
        "exp_weighted_halflife_7d": exp_weighted_prior(decisive, T, 7),
        "exp_weighted_halflife_14d": exp_weighted_prior(decisive, T, 14),
    }
    baseline_prior_a = None
    for label, prior in prior_variants.items():
        scored = {c: ws_full.expected_win_rate(c, prior, "policy2") for c in ws_full.candidates}
        a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1)) if scored else None
        if label == "rolling_full_history":
            baseline_prior_a = a
        rows.append({"variant_type": "meta_prior_type", "variant_value": label,
                      "selected_archetype": a, "expected_win_rate": round(scored[a], 4) if a and scored[a] is not None else None,
                      "changed_from_default": None})
    for r in rows:
        if r["variant_type"] == "meta_prior_type":
            r["changed_from_default"] = r["selected_archetype"] != baseline_prior_a

    return pd.DataFrame(rows)


# ================= main =================

def main():
    decisive = load_data()
    print(f"Loaded {len(decisive)} decisive deck-slots across {decisive['date_dt'].nunique()} calendar days.")

    daily_df, oracle_df, skip_df = run_daily_walk_forward(decisive)

    # fold oracle rows into the same schema/file so it's directly comparable in one place
    # (still clearly labeled and distinguished by training_window='n/a_oracle' -- never used as
    # a feature or input to any strategy above, purely a diagnostic ceiling per Sec 15).
    oracle_rows_full = []
    for _, r in oracle_df.iterrows():
        status = "OK" if r["test_games"] and r["test_games"] > 0 else "SKIPPED_NO_ORACLE_CANDIDATE"
        oracle_rows_full.append({
            "decision_day": r["decision_day"], "training_window": "n/a_oracle",
            "strategy": "ORACLE_NOT_AVAILABLE_AT_DECISION_TIME", "selected_archetype": r["selected_archetype"],
            "training_games": None, "test_games": r["test_games"],
            "training_start": None, "training_end": None,
            "test_start": r["decision_day"], "test_end": r["decision_day"],
            "wins": r["wins"], "losses": r["losses"], "win_rate": r["win_rate"],
            "candidate_count": None, "selected_deck_training_games": None,
            "selected_deck_training_win_rate": None, "selected_deck_training_share": None,
            "expected_win_rate": None, "credible_counter_count": None,
            "selection_note": r["note"], "status": status,
            "decision_timestamp": None, "latest_training_timestamp": None,
            "first_test_timestamp": None, "last_test_timestamp": None,
            "latest_train_before_first_test": None,
        })
    daily_df = pd.concat([daily_df, pd.DataFrame(oracle_rows_full)], axis=0, ignore_index=True)

    daily_df.to_csv(os.path.join(OUT_DIR, "daily_walk_forward.csv"), index=False)
    print(f"Wrote daily_walk_forward.csv: {len(daily_df)} rows "
          f"({(daily_df.status=='OK').sum()} OK, {(daily_df.status=='SKIPPED_NO_CANDIDATES').sum()} skipped-no-candidates, "
          f"{(daily_df.status=='SKIPPED_NO_TEST_DATA').sum()} skipped-no-test-data, "
          f"{(daily_df.status=='SKIPPED_NO_ORACLE_CANDIDATE').sum()} skipped-no-oracle-candidate).")
    print(f"Oracle rows: {len(oracle_df)}, days with 0 eligible oracle archetype: {(oracle_df.selected_archetype.isna()).sum()}")

    # leakage validation
    checked = daily_df["latest_train_before_first_test"].dropna().astype(bool)
    n_pass = int(checked.sum())
    n_fail = int((~checked).sum())
    print(f"Leakage check: {len(checked)} rows checked, {n_pass} pass (latest_train < first_test), {n_fail} FAIL")

    comparison_df = build_window_comparison(daily_df)
    comparison_df.to_csv(os.path.join(OUT_DIR, "window_comparison.csv"), index=False)
    print(f"Wrote window_comparison.csv: {len(comparison_df)} rows.")

    og_df = build_ogerpon_grimmsnarl(decisive)
    og_df.to_csv(os.path.join(OUT_DIR, "ogerpon_grimmsnarl_walk_forward.csv"), index=False)
    print(f"Wrote ogerpon_grimmsnarl_walk_forward.csv: {len(og_df)} rows.")

    counter_df = build_counter_detection(decisive, ["Marnie's Grimmsnarl ex", "Fezandipiti ex"])
    counter_df.to_csv(os.path.join(OUT_DIR, "counter_detection.csv"), index=False)
    print(f"Wrote counter_detection.csv: {len(counter_df)} rows.")
    print(counter_df.to_string(index=False))

    regime_df = build_regime_analysis(decisive, daily_df)
    regime_df.to_csv(os.path.join(OUT_DIR, "regime_analysis.csv"), index=False)
    print(f"Wrote regime_analysis.csv: {len(regime_df)} rows.")

    sens_df = build_sensitivity(decisive)
    sens_df.to_csv(os.path.join(OUT_DIR, "high_resolution_sensitivity.csv"), index=False)
    print(f"Wrote high_resolution_sensitivity.csv: {len(sens_df)} rows.")
    print(sens_df.to_string(index=False))

    print("\n" + "=" * 70 + "\nSUMMARY: window_comparison (OK rows)")
    print(comparison_df.to_string(index=False))

    print("\nDONE.")


if __name__ == "__main__":
    main()
