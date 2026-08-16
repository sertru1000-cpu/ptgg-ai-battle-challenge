"""Phase 4.3 -- Opponent-Aware Deck Selection & Walk-Forward Evaluation.

Reads ONLY results/meta/episodes_summary.parquet (the canonical 3,499-episode
Phase 4.1 dataset) plus results/meta/archetype_features.csv and
results/meta/archetype_matchups.csv (Phase 4.2, used only for the descriptive
counter-analysis, NOT for any walk-forward decision -- every backtest decision
below is recomputed from TRAIN-only slices of the raw parquet to guarantee no
temporal leakage). No new episodes are downloaded. Rating is never used.

This is an EVALUATION script -- no RL/MCTS/search/agent/gameplay policy.

Writes:
  results/meta/evaluation_windows.csv
  results/meta/deck_selection_backtest.csv
  results/meta/strategy_comparison.csv
  results/meta/counter_analysis.csv
  results/meta/strategy_sensitivity.csv
  results/meta/current_deck_recommendation.csv
"""
from __future__ import annotations

import math
import os
import sys
from itertools import combinations

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon
from scipy.spatial.distance import jensenshannon

OUT_DIR = os.path.join(REPO_ROOT, "results", "meta")
PARQUET = os.path.join(OUT_DIR, "episodes_summary.parquet")

# ================= documented constants =================
CANDIDATE_MIN_GAMES = 50          # Sec 10: minimum historical evidence to be selectable at all
RECENT_MIN_GAMES = 20             # min sample within the "recent-within-train" window (Strategy C/E/F)
MATCHUP_INSUFFICIENT = 20         # Sec 9 tiers, kept identical to Phase 4.2 for consistency
MATCHUP_USABLE = 50
MATCHUP_HIGH = 100
SHRINKAGE_K = 30                  # same Beta-Binomial shrinkage as Phase 4.2
DOMINANT_SHARE_THRESHOLD = 0.15   # Strategy F: recent-within-train share defining "dominant opponent"
ORACLE_MIN_TEST_GAMES = 20        # oracle must itself clear a minimal sample floor, not just be lucky

BASELINE_STRATEGY = "A_most_popular"


def wilson_ci(wins, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def confidence_flag(n):
    if n < MATCHUP_INSUFFICIENT:
        return "INSUFFICIENT"
    elif n < MATCHUP_USABLE:
        return "LOW_CONFIDENCE"
    elif n < MATCHUP_HIGH:
        return "USABLE"
    else:
        return "HIGH_CONFIDENCE"


def shrinkage_wr(wins, n, k=SHRINKAGE_K, prior=0.5):
    return (wins + k * prior) / (n + k)


# ================= data loading =================

def load_data():
    df = pd.read_parquet(PARQUET)
    decisive = df[df["outcome_type"] == "DECISIVE"].copy()
    decisive["date_dt"] = pd.to_datetime(decisive["date"])
    min_date = decisive["date_dt"].min()
    decisive["week"] = ((decisive["date_dt"] - min_date).dt.days // 7) + 1
    return decisive


# ================= evaluation windows =================

def build_windows(decisive):
    windows = []
    max_week = int(decisive["week"].max())
    # rolling weekly windows (primary evaluation set)
    for tw in range(2, max_week + 1):
        train_weeks = list(range(1, tw))
        test_weeks = [tw]
        windows.append({
            "window_id": f"ROLL_W{tw}", "scheme": "rolling_weekly",
            "train_weeks": train_weeks, "test_weeks": test_weeks,
        })
    # coarse period-based windows (matches the phase prompt's literal example, secondary/confirmatory)
    windows.append({"window_id": "COARSE_A_early_to_middle", "scheme": "coarse_period",
                     "train_weeks": [1, 2, 3], "test_weeks": [4, 5]})
    windows.append({"window_id": "COARSE_B_earlymid_to_recent", "scheme": "coarse_period",
                     "train_weeks": [1, 2, 3, 4, 5], "test_weeks": [6, 7, 8]})
    return windows


# ================= per-window stats bundle =================

class WindowStats:
    def __init__(self, train_df):
        self.train_df = train_df
        self.total_games = len(train_df)
        g = train_df.groupby("player_deck_cluster_id")
        self.games = g.size().to_dict()
        self.wins = g.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False).to_dict()
        self.candidates = {cid for cid, n in self.games.items() if n >= CANDIDATE_MIN_GAMES}
        self.full_prior = {cid: n / self.total_games for cid, n in self.games.items()} if self.total_games else {}

        max_train_week = train_df["week"].max()
        self.recent_df = train_df[train_df["week"] == max_train_week]
        self.recent_total = len(self.recent_df)
        rg = self.recent_df.groupby("player_deck_cluster_id")
        self.recent_games = rg.size().to_dict()
        self.recent_wins = rg.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False).to_dict() if self.recent_total else {}
        self.recent_prior = {cid: n / self.recent_total for cid, n in self.recent_games.items()} if self.recent_total else {}

        pg = train_df.groupby(["player_deck_cluster_id", "opponent_deck_cluster_id"])
        self.pair_games = pg.size().to_dict()
        self.pair_wins = pg.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False).to_dict()

        self.dominant_set = {cid for cid, p in self.recent_prior.items() if p >= DOMINANT_SHARE_THRESHOLD}

    def win_rate(self, cid):
        n = self.games.get(cid, 0)
        return (self.wins.get(cid, 0) / n) if n else None

    def recent_win_rate(self, cid):
        n = self.recent_games.get(cid, 0)
        return (self.recent_wins.get(cid, 0) / n) if n else None

    def shrinkage(self, cid):
        return shrinkage_wr(self.wins.get(cid, 0), self.games.get(cid, 0))

    def matchup_estimate(self, a, b, mode):
        """mode in {'policy2', 'policy1_neutral', 'conservative'}. Returns (estimate, confidence, method)."""
        n = self.pair_games.get((a, b), 0)
        w = self.pair_wins.get((a, b), 0)
        conf = confidence_flag(n)
        usable = conf in ("USABLE", "HIGH_CONFIDENCE")

        if mode == "conservative":
            if n > 0:
                _, lo, _ = wilson_ci(w, n)
                return lo, conf, "wilson_lo"
            fallback = np.clip(self.shrinkage(a) - self.shrinkage(b) + 0.5, 0.05, 0.95)
            return fallback, conf, "fallback_policy2"

        if usable:
            return w / n, conf, "empirical"
        if mode == "policy1_neutral":
            return 0.5, conf, "fallback_policy1_neutral"
        # default: policy2, conservative estimate from broader archetype strength
        fallback = np.clip(self.shrinkage(a) - self.shrinkage(b) + 0.5, 0.05, 0.95)
        return fallback, conf, "fallback_policy2"

    def expected_win_rate(self, a, prior, mode):
        total, weight_seen = 0.0, 0.0
        for b, pb in prior.items():
            est, _, _ = self.matchup_estimate(a, b, mode)
            total += pb * est
            weight_seen += pb
        return total / weight_seen if weight_seen > 0 else None


# ================= strategies =================

def strategy_A(ws: WindowStats):
    if not ws.candidates:
        return None, None, "no_candidates"
    a = max(ws.candidates, key=lambda c: ws.full_prior.get(c, 0))
    return a, ws.full_prior.get(a), "argmax_usage_share"


def strategy_B(ws: WindowStats):
    if not ws.candidates:
        return None, None, "no_candidates"
    a = max(ws.candidates, key=lambda c: (ws.win_rate(c), ws.games.get(c, 0)))
    return a, ws.win_rate(a), "argmax_full_history_win_rate"


def strategy_C(ws: WindowStats):
    recent_candidates = {c for c in ws.candidates if ws.recent_games.get(c, 0) >= RECENT_MIN_GAMES}
    if not recent_candidates:
        a, ewr, _ = strategy_B(ws)
        return a, ewr, "fallback_to_B_insufficient_recent_sample"
    a = max(recent_candidates, key=lambda c: (ws.recent_win_rate(c), ws.recent_games.get(c, 0)))
    return a, ws.recent_win_rate(a), "argmax_recent_window_win_rate"


def strategy_D(ws: WindowStats, mode="policy2"):
    if not ws.candidates:
        return None, None, "no_candidates"
    scored = {c: ws.expected_win_rate(c, ws.full_prior, mode) for c in ws.candidates}
    a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
    label = "argmax_EWR_full_history_prior" + ("_policy1_neutral" if mode == "policy1_neutral" else "_policy2_fallback")
    return a, scored[a], label


def strategy_E(ws: WindowStats):
    if not ws.candidates:
        return None, None, "no_candidates"
    if ws.recent_total >= RECENT_MIN_GAMES and ws.recent_prior:
        prior, note = ws.recent_prior, "argmax_EWR_recent_prior"
    else:
        prior, note = ws.full_prior, "fallback_to_full_history_prior_insufficient_recent_data"
    scored = {c: ws.expected_win_rate(c, prior, "policy2") for c in ws.candidates}
    a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
    return a, scored[a], note


def strategy_F(ws: WindowStats):
    if not ws.candidates:
        return None, None, "no_candidates"
    if not ws.dominant_set:
        a, ewr, note = strategy_D(ws, mode="policy2")
        return a, ewr, "fallback_to_D_no_dominant_archetype_this_window"
    dom_total = sum(ws.recent_prior.get(c, 0) for c in ws.dominant_set)
    dom_prior = {c: ws.recent_prior.get(c, 0) / dom_total for c in ws.dominant_set} if dom_total else {}
    scored = {c: ws.expected_win_rate(c, dom_prior, "policy2") for c in ws.candidates}
    a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
    return a, scored[a], f"argmax_EWR_vs_dominant_set({sorted(ws.dominant_set)})"


def strategy_G(ws: WindowStats):
    if not ws.candidates:
        return None, None, "no_candidates"
    scored = {c: ws.expected_win_rate(c, ws.full_prior, "conservative") for c in ws.candidates}
    a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
    return a, scored[a], "argmax_conservative_EWR_wilson_lo_full_history_prior"


STRATEGIES = {
    "A_most_popular": strategy_A,
    "B_highest_historical_wr": strategy_B,
    "C_recent_wr": strategy_C,
    "D_meta_aware_full_history": lambda ws: strategy_D(ws, mode="policy2"),
    "D_policy1_neutral_variant": lambda ws: strategy_D(ws, mode="policy1_neutral"),
    "E_recent_meta_aware": strategy_E,
    "F_anti_meta": strategy_F,
    "G_conservative_meta_aware": strategy_G,
}


def oracle(test_df):
    g = test_df.groupby("player_deck_cluster_id")
    games = g.size()
    wins = g.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False)
    elig = games[games >= ORACLE_MIN_TEST_GAMES].index
    if len(elig) == 0:
        return None, None, "no_archetype_cleared_oracle_min_sample"
    wr = (wins[elig] / games[elig])
    a = wr.idxmax()
    return a, wr[a], "ORACLE_NOT_AVAILABLE_AT_DECISION_TIME"


# ================= backtest driver =================

def evaluate_selection(test_df, cid):
    if cid is None:
        return None, None, None
    sub = test_df[test_df["player_deck_cluster_id"] == cid]
    n = len(sub)
    if n == 0:
        return 0, 0, None
    w = int((sub["result"] == "WIN").sum())
    return n, w, w / n


def run_backtest(decisive, windows):
    rows = []
    for win in windows:
        train_df = decisive[decisive["week"].isin(win["train_weeks"])]
        test_df = decisive[decisive["week"].isin(win["test_weeks"])]
        ws = WindowStats(train_df)

        for strat_name, fn in STRATEGIES.items():
            cid, sel_ewr, note = fn(ws)
            n, w, wr = evaluate_selection(test_df, cid)
            rows.append({
                "window_id": win["window_id"], "scheme": win["scheme"],
                "train_weeks": ",".join(map(str, win["train_weeks"])),
                "test_weeks": ",".join(map(str, win["test_weeks"])),
                "train_games": ws.total_games, "test_total_games": len(test_df),
                "n_candidates": len(ws.candidates),
                "strategy": strat_name, "selected_archetype": cid,
                "selection_time_expected_win_rate": round(sel_ewr, 4) if sel_ewr is not None else None,
                "selection_note": note,
                "test_games": n, "test_wins": w,
                "test_win_rate": round(wr, 4) if wr is not None else None,
                "is_oracle": False,
            })

        o_cid, o_wr, o_note = oracle(test_df)
        o_n, o_w, o_wr_actual = evaluate_selection(test_df, o_cid)
        rows.append({
            "window_id": win["window_id"], "scheme": win["scheme"],
            "train_weeks": ",".join(map(str, win["train_weeks"])),
            "test_weeks": ",".join(map(str, win["test_weeks"])),
            "train_games": ws.total_games, "test_total_games": len(test_df),
            "n_candidates": len(ws.candidates),
            "strategy": "ORACLE_NOT_AVAILABLE_AT_DECISION_TIME", "selected_archetype": o_cid,
            "selection_time_expected_win_rate": None,
            "selection_note": o_note,
            "test_games": o_n, "test_wins": o_w,
            "test_win_rate": round(o_wr_actual, 4) if o_wr_actual is not None else None,
            "is_oracle": True,
        })
    return pd.DataFrame(rows)


# ================= strategy comparison / statistics =================

def two_proportion_z(w1, n1, w2, n2):
    if n1 == 0 or n2 == 0:
        return None, None
    p1, p2 = w1 / n1, w2 / n2
    p_pool = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    from scipy.stats import norm
    p_value = 2 * (1 - norm.cdf(abs(z)))
    return z, p_value


def build_strategy_comparison(backtest_df):
    out_rows = []
    for scheme in backtest_df["scheme"].unique():
        sdf = backtest_df[backtest_df["scheme"] == scheme]
        baseline = sdf[sdf["strategy"] == BASELINE_STRATEGY].set_index("window_id")

        for strat in sorted(sdf["strategy"].unique()):
            g = sdf[sdf["strategy"] == strat]
            valid = g[g["test_games"] > 0]
            n_periods_total = len(g)
            n_periods_valid = len(valid)
            total_games = int(valid["test_games"].sum())
            total_wins = int(valid["test_wins"].sum())
            pooled_wr = total_wins / total_games if total_games else None
            mean_wr = valid["test_win_rate"].mean() if n_periods_valid else None
            median_wr = valid["test_win_rate"].median() if n_periods_valid else None
            worst_wr = valid["test_win_rate"].min() if n_periods_valid else None
            best_wr = valid["test_win_rate"].max() if n_periods_valid else None

            # paired comparison vs baseline (same window_id, both must have valid test data)
            gi = g.set_index("window_id")
            paired_wins_strat, paired_wins_base = [], []
            for wid in gi.index:
                if wid in baseline.index:
                    sv = gi.loc[wid, "test_win_rate"]
                    bv = baseline.loc[wid, "test_win_rate"]
                    if pd.notna(sv) and pd.notna(bv):
                        paired_wins_strat.append(sv)
                        paired_wins_base.append(bv)
            n_paired = len(paired_wins_strat)
            mean_diff = float(np.mean(np.array(paired_wins_strat) - np.array(paired_wins_base))) if n_paired else None

            sign_p, wilcoxon_p = None, None
            if n_paired >= 1 and strat != BASELINE_STRATEGY:
                diffs = np.array(paired_wins_strat) - np.array(paired_wins_base)
                n_nonzero = int(np.sum(diffs != 0))
                n_wins = int(np.sum(diffs > 0))
                if n_nonzero > 0:
                    sign_p = binomtest(n_wins, n_nonzero, 0.5).pvalue
                if n_nonzero >= 2:
                    try:
                        wilcoxon_p = wilcoxon(diffs[diffs != 0]).pvalue
                    except ValueError:
                        wilcoxon_p = None

            base_row = baseline.loc[:, ["test_games", "test_wins"]].sum() if strat != BASELINE_STRATEGY else None
            z, z_p = (None, None)
            if strat != BASELINE_STRATEGY and total_games and base_row is not None and base_row["test_games"] > 0:
                z, z_p = two_proportion_z(total_wins, total_games, int(base_row["test_wins"]), int(base_row["test_games"]))

            out_rows.append({
                "scheme": scheme, "strategy": strat,
                "n_periods": n_periods_total, "n_periods_with_test_data": n_periods_valid,
                "total_games": total_games, "total_wins": total_wins, "total_losses": total_games - total_wins,
                "pooled_out_of_sample_win_rate": round(pooled_wr, 4) if pooled_wr is not None else None,
                "mean_period_win_rate": round(mean_wr, 4) if mean_wr is not None else None,
                "median_period_win_rate": round(median_wr, 4) if median_wr is not None else None,
                "worst_period_win_rate": round(worst_wr, 4) if worst_wr is not None else None,
                "best_period_win_rate": round(best_wr, 4) if best_wr is not None else None,
                "n_paired_periods_vs_baseline": n_paired,
                "mean_paired_diff_vs_baseline": round(mean_diff, 4) if mean_diff is not None else None,
                "sign_test_p_value_vs_baseline": round(sign_p, 4) if sign_p is not None else None,
                "wilcoxon_p_value_vs_baseline": round(wilcoxon_p, 4) if wilcoxon_p is not None else None,
                "pooled_two_proportion_z": round(z, 4) if z is not None else None,
                "pooled_two_proportion_p_value": round(z_p, 4) if z_p is not None else None,
            })
    return pd.DataFrame(out_rows)


# ================= regime-change (JS divergence) analysis =================

def build_regime_analysis(decisive, backtest_df):
    weeks = sorted(decisive["week"].unique())
    universe = sorted(decisive["player_deck_cluster_id"].unique())
    week_dist = {}
    for wk in weeks:
        wdf = decisive[decisive["week"] == wk]
        counts = wdf["player_deck_cluster_id"].value_counts()
        vec = np.array([counts.get(u, 0) for u in universe], dtype=float)
        week_dist[wk] = vec / vec.sum() if vec.sum() else vec

    js_by_test_week = {}
    for wk in weeks:
        if wk - 1 in week_dist:
            js_by_test_week[wk] = jensenshannon(week_dist[wk - 1], week_dist[wk], base=2)

    js_vals = [v for v in js_by_test_week.values() if not np.isnan(v)]
    median_js = float(np.median(js_vals)) if js_vals else None

    rows = []
    for wk, js in js_by_test_week.items():
        regime = None
        if median_js is not None and not np.isnan(js):
            regime = "HIGH_CHANGE" if js >= median_js else "LOW_CHANGE"
        rows.append({"test_week": wk, "js_divergence_vs_prev_week": round(float(js), 6) if not np.isnan(js) else None,
                      "median_js_divergence": round(median_js, 6) if median_js is not None else None,
                      "regime": regime})
    regime_df = pd.DataFrame(rows)

    roll = backtest_df[backtest_df["scheme"] == "rolling_weekly"].copy()
    roll["test_week"] = roll["test_weeks"].astype(int)
    roll = roll.merge(regime_df[["test_week", "regime", "js_divergence_vs_prev_week"]], on="test_week", how="left")

    summary_rows = []
    base = roll[roll["strategy"] == BASELINE_STRATEGY].set_index("window_id")["test_win_rate"]
    for strat in sorted(roll["strategy"].unique()):
        if strat == BASELINE_STRATEGY:
            continue
        sdf = roll[roll["strategy"] == strat].set_index("window_id")
        adv = (sdf["test_win_rate"] - base).dropna()
        merged = roll[roll["strategy"] == strat].set_index("window_id")[["regime"]].join(adv.rename("advantage"))
        for regime_label in ["HIGH_CHANGE", "LOW_CHANGE"]:
            vals = merged[merged["regime"] == regime_label]["advantage"].dropna()
            summary_rows.append({
                "strategy": strat, "regime": regime_label, "n_periods": len(vals),
                "mean_advantage_vs_A": round(float(vals.mean()), 4) if len(vals) else None,
            })
    regime_summary_df = pd.DataFrame(summary_rows)
    return regime_df, regime_summary_df


# ================= counter analysis (descriptive, full-history) =================

def build_counter_analysis(target_archetypes):
    feat = pd.read_csv(os.path.join(OUT_DIR, "archetype_features.csv"))
    mm = pd.read_csv(os.path.join(OUT_DIR, "archetype_matchups.csv"))
    feat_idx = feat.set_index("archetype_id")

    rows = []
    for target in target_archetypes:
        if target not in feat_idx.index:
            continue
        beats_target = mm[(mm["archetype_B"] == target) & (mm["credible_counter_A_over_B"])]
        beats_target2 = mm[(mm["archetype_A"] == target) & (mm["credible_counter_B_over_A"])]
        found = []
        for _, r in beats_target.iterrows():
            found.append((r["archetype_A"], r["games"], r["win_rate_A"], r["win_rate_A_wilson_lo"]))
        for _, r in beats_target2.iterrows():
            found.append((r["archetype_B"], r["games"], r["win_rate_B"], round(1 - r["win_rate_A_wilson_hi"], 4)))

        if not found:
            rows.append({"target_archetype": target, "target_recent_share": feat_idx.loc[target, "recent_share"],
                         "counter_archetype": None, "counter_games": None, "counter_win_rate": None,
                         "counter_wilson_lo": None, "counter_overall_share": None, "counter_recent_share": None,
                         "counter_recent_games": None, "verdict": "NO_CREDIBLE_COUNTER_FOUND"})
            continue

        for counter, games, wr, lo in found:
            crow = feat_idx.loc[counter] if counter in feat_idx.index else None
            counter_recent_games = crow["recent_games"] if crow is not None else None
            counter_recent_share = crow["recent_share"] if crow is not None else None
            counter_overall_share = crow["usage_share"] if crow is not None else None
            if counter_recent_games is not None and counter_recent_games >= RECENT_MIN_GAMES:
                verdict = "STRONG_AND_RELEVANT"
            else:
                verdict = "STRONG_BUT_RARE"
            rows.append({
                "target_archetype": target, "target_recent_share": feat_idx.loc[target, "recent_share"],
                "counter_archetype": counter, "counter_games": games, "counter_win_rate": wr,
                "counter_wilson_lo": lo, "counter_overall_share": counter_overall_share,
                "counter_recent_share": counter_recent_share, "counter_recent_games": counter_recent_games,
                "verdict": verdict,
            })
    return pd.DataFrame(rows).sort_values(["target_archetype", "counter_win_rate"], ascending=[True, False])


# ================= sensitivity analysis (current, all-data decision) =================

def build_sensitivity(decisive):
    rows = []
    full_ws = WindowStats(decisive)

    def best_D(ws, usable_threshold, mode):
        global MATCHUP_USABLE
        old = MATCHUP_USABLE
        try:
            MATCHUP_USABLE = usable_threshold
            scored = {c: ws.expected_win_rate(c, ws.full_prior, mode) for c in ws.candidates}
        finally:
            MATCHUP_USABLE = old
        if not scored:
            return None, None
        a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
        return a, scored[a]

    # (a) vary matchup min-sample threshold used to trust an empirical matchup estimate
    baseline_a, baseline_ewr = best_D(full_ws, MATCHUP_USABLE, "policy2")
    for thr in [20, 50, 100]:
        a, ewr = best_D(full_ws, thr, "policy2")
        rows.append({"variant_type": "matchup_min_sample_threshold", "variant_value": thr,
                      "selected_archetype": a, "expected_win_rate": round(ewr, 4) if ewr is not None else None,
                      "changed_from_default": a != baseline_a})

    # (b) vary recency of the opponent-distribution prior used for the E-style selection
    n_total = len(decisive)
    decisive_sorted = decisive.sort_values("date_dt")
    variants = {
        "full_history": decisive_sorted,
        "recent_50pct": decisive_sorted.iloc[n_total // 2:],
        "recent_25pct": decisive_sorted.iloc[int(n_total * 0.75):],
        "recent_period_weeks6to8": decisive_sorted[decisive_sorted["period"] == "RECENT"] if "period" in decisive_sorted.columns else decisive_sorted[decisive_sorted["week"] >= 6],
    }
    baseline_e_a = None
    for label, subset in variants.items():
        prior_counts = subset["player_deck_cluster_id"].value_counts()
        prior_total = len(subset)
        prior = {cid: n / prior_total for cid, n in prior_counts.items()} if prior_total else {}
        scored = {c: full_ws.expected_win_rate(c, prior, "policy2") for c in full_ws.candidates}
        a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1)) if scored else None
        if label == "recent_period_weeks6to8":
            baseline_e_a = a
        rows.append({"variant_type": "prior_recency", "variant_value": label,
                      "selected_archetype": a, "expected_win_rate": round(scored[a], 4) if a and scored[a] is not None else None,
                      "changed_from_default": None})
    for r in rows:
        if r["variant_type"] == "prior_recency":
            r["changed_from_default"] = r["selected_archetype"] != baseline_e_a

    # (c) uncertainty handling: raw/fallback (D) vs conservative Wilson-lower (G), full-history prior
    a_raw, ewr_raw = best_D(full_ws, MATCHUP_USABLE, "policy2")
    a_cons, ewr_cons = best_D(full_ws, MATCHUP_USABLE, "conservative")
    rows.append({"variant_type": "uncertainty_handling", "variant_value": "raw_empirical_with_fallback",
                  "selected_archetype": a_raw, "expected_win_rate": round(ewr_raw, 4) if ewr_raw is not None else None,
                  "changed_from_default": False})
    rows.append({"variant_type": "uncertainty_handling", "variant_value": "conservative_wilson_lower_bound",
                  "selected_archetype": a_cons, "expected_win_rate": round(ewr_cons, 4) if ewr_cons is not None else None,
                  "changed_from_default": a_cons != a_raw})

    return pd.DataFrame(rows)


# ================= current recommendation (all data, deploy-time) =================

def build_current_recommendation(decisive):
    # Matchup estimates use ALL available history (most reliable pairwise data); the
    # opponent-distribution prior uses Phase 4.1/4.2's canonical RECENT period (weeks
    # 6-8, period=='RECENT') rather than the backtest's relative "last 1 week of train"
    # definition -- for a one-shot "decide today" call there is no walk-forward
    # constraint requiring a train-relative window, and RECENT is the already-validated,
    # much larger (~4,000 deck-slot) current-meta sample from Phase 4.2, so reusing it
    # avoids re-deriving a noisier single-week estimate and stays consistent with the
    # existing meta_prior.csv / archetype_features.csv recent-period numbers.
    ws = WindowStats(decisive)  # full dataset as TRAIN -- there is no future data beyond this point
    feat = pd.read_csv(os.path.join(OUT_DIR, "archetype_features.csv")).set_index("archetype_id")

    recent_df = decisive[decisive["period"] == "RECENT"]
    recent_total = len(recent_df)
    rg = recent_df.groupby("player_deck_cluster_id")
    recent_games = rg.size().to_dict()
    recent_wins = rg.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False).to_dict() if recent_total else {}
    recent_prior = {cid: n / recent_total for cid, n in recent_games.items()} if recent_total else {}

    current_candidates = {c for c in ws.candidates if recent_games.get(c, 0) >= RECENT_MIN_GAMES}
    prior = recent_prior if recent_total >= RECENT_MIN_GAMES else ws.full_prior

    rows = []
    for c in current_candidates:
        ewr = ws.expected_win_rate(c, prior, "policy2")
        ewr_cons = ws.expected_win_rate(c, prior, "conservative")
        counters = feat.loc[c, "credible_counter_count"] if c in feat.index else None
        countered_by = feat.loc[c, "credible_countered_by_count"] if c in feat.index else None
        rg_c = recent_games.get(c, 0)
        rw_c = recent_wins.get(c, 0)
        rows.append({
            "archetype": c,
            "recent_share": round(recent_prior.get(c, 0), 4),
            "recent_games": rg_c,
            "recent_win_rate": round(rw_c / rg_c, 4) if rg_c else None,
            "expected_win_rate_vs_current_meta": round(ewr, 4) if ewr is not None else None,
            "conservative_expected_win_rate_vs_current_meta": round(ewr_cons, 4) if ewr_cons is not None else None,
            "credible_counters_this_deck_has": int(counters) if counters is not None else None,
            "credible_counters_against_this_deck": int(countered_by) if countered_by is not None else None,
            "overall_confidence": confidence_flag(ws.games.get(c, 0)),
        })
    rec_df = pd.DataFrame(rows).sort_values("expected_win_rate_vs_current_meta", ascending=False).reset_index(drop=True)
    rec_df.insert(0, "rank", rec_df.index + 1)
    return rec_df


# ================= main =================

def main():
    decisive = load_data()
    print(f"Loaded {len(decisive)} decisive deck-slots across {decisive['week'].max()} weeks.")

    windows = build_windows(decisive)
    win_df = pd.DataFrame([{
        "window_id": w["window_id"], "scheme": w["scheme"],
        "train_weeks": ",".join(map(str, w["train_weeks"])), "test_weeks": ",".join(map(str, w["test_weeks"])),
    } for w in windows])
    win_df.to_csv(os.path.join(OUT_DIR, "evaluation_windows.csv"), index=False)
    print(f"Wrote evaluation_windows.csv: {len(win_df)} windows "
          f"({sum(win_df.scheme=='rolling_weekly')} rolling_weekly, {sum(win_df.scheme=='coarse_period')} coarse_period).")

    backtest_df = run_backtest(decisive, windows)
    backtest_df.to_csv(os.path.join(OUT_DIR, "deck_selection_backtest.csv"), index=False)
    print(f"Wrote deck_selection_backtest.csv: {len(backtest_df)} rows.")

    comparison_df = build_strategy_comparison(backtest_df)
    comparison_df.to_csv(os.path.join(OUT_DIR, "strategy_comparison.csv"), index=False)
    print(f"Wrote strategy_comparison.csv: {len(comparison_df)} rows.")

    regime_df, regime_summary_df = build_regime_analysis(decisive, backtest_df)
    combined_regime = pd.concat([regime_df.assign(_section="js_by_week"),
                                  regime_summary_df.assign(_section="advantage_by_regime")], axis=0, ignore_index=True)
    combined_regime.to_csv(os.path.join(OUT_DIR, "regime_analysis.csv"), index=False)
    print(f"Wrote regime_analysis.csv: {len(regime_df)} weekly JS rows + {len(regime_summary_df)} regime-summary rows.")

    target_archetypes = ["Marnie's Grimmsnarl ex", "Fezandipiti ex", "Mega Kangaskhan ex",
                          "Mega Lopunny ex", "Team Rocket's Mewtwo ex", "Teal Mask Ogerpon ex",
                          "Dragapult ex", "Cynthia's Garchomp ex", "Mega Lucario ex"]
    counter_df = build_counter_analysis(target_archetypes)
    counter_df.to_csv(os.path.join(OUT_DIR, "counter_analysis.csv"), index=False)
    print(f"Wrote counter_analysis.csv: {len(counter_df)} rows.")

    sens_df = build_sensitivity(decisive)
    sens_df.to_csv(os.path.join(OUT_DIR, "strategy_sensitivity.csv"), index=False)
    print(f"Wrote strategy_sensitivity.csv: {len(sens_df)} rows.")

    rec_df = build_current_recommendation(decisive)
    rec_df.to_csv(os.path.join(OUT_DIR, "current_deck_recommendation.csv"), index=False)
    print(f"Wrote current_deck_recommendation.csv: {len(rec_df)} candidate archetypes.")
    print(rec_df.to_string(index=False))

    # ---- validation ----
    print("\n" + "=" * 70 + "\nVALIDATION")
    roll = backtest_df[(backtest_df["scheme"] == "rolling_weekly") & (~backtest_df["is_oracle"])]
    print(f"rolling_weekly windows: {roll['window_id'].nunique()} (expect 7)")
    print(f"strategies per window: {roll.groupby('window_id').size().unique()} (expect 8 each)")
    zero_test = roll[roll["test_games"] == 0]
    print(f"strategy-window picks with 0 test games (unmeasurable, excluded from aggregates): {len(zero_test)} / {len(roll)}")
    bad_wr = roll[(roll["test_games"] > 0) & (roll["test_wins"] > roll["test_games"])]
    print(f"rows with wins > games (should be 0): {len(bad_wr)}")
    print("DONE.")


if __name__ == "__main__":
    main()
