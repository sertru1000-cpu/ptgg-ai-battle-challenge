"""Phase 4.5 -- Counter-Aware Deck Selection.

Evaluates whether explicitly consuming Phase 4.4's OOS_CONFIRMED counter
registry improves out-of-sample deck selection over the strongest Phase
4.3b baselines. Strictly a consumer of the frozen Phase 4.4 registry: no
new counter discovery, no promotion of OOS_PENDING/OOS_FAILED counters, no
RL/MCTS/search/opponent-modeling/agent code. Zero new episode downloads.

Two experiments, kept structurally separate throughout every output file:
  Experiment A (PRIMARY, strict deployable): a counter may only influence a
    decision on/after the calendar day AFTER its Phase-4.4 confirmation_date
    (the earliest moment its OOS_CONFIRMED status could actually have been
    known). This is what "counter_active" means in every non-FROZEN row.
  Experiment B (FROZEN-RULE DIAGNOSTIC): the currently-known confirmed rule
    applied retroactively to the whole dataset, purely to ask "how useful
    would this rule have been had we always known it." Never mixed into the
    primary comparison numbers.

Writes:
  results/meta/counter_aware_walk_forward.csv
  results/meta/counter_aware_decisions.csv
  results/meta/counter_aware_comparison.csv
  results/meta/counter_trigger_analysis.csv
  results/meta/counter_selection_changes.csv
  results/meta/counter_regret_analysis.csv
  results/meta/counter_aware_sensitivity.csv
  results/meta/counter_aware_leakage_audit.csv
"""
from __future__ import annotations

import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import numpy as np
import pandas as pd

OUT_DIR = os.path.join(REPO_ROOT, "results", "meta")
PARQUET = os.path.join(OUT_DIR, "episodes_summary.parquet")
REGISTRY_CSV = os.path.join(OUT_DIR, "counter_registry.csv")

# ============================================================================
# PRIMARY CONFIGURATION -- declared before running the evaluation (Sec 26:
# "primary configuration must be fixed before evaluating"). Sensitivity
# variants are computed separately in counter_aware_sensitivity.csv.
# ============================================================================
TRAINING_WINDOW_DAYS = 14        # Phase 4.3b's own declared "best deployable" window (51.29% C, sig. E)
CANDIDATE_MIN_GAMES = 50         # reused verbatim from Phase 4.3b
MATCHUP_INSUFFICIENT = 20        # reused verbatim from Phase 4.3b / 4.4
MATCHUP_USABLE = 50
MATCHUP_HIGH = 100
SHRINKAGE_K = 30
ORACLE_MIN_TEST_GAMES = 10       # reused verbatim from Phase 4.3b; also used as the "best deployable" regret floor

TARGET_ACTIVATION_THRESHOLD_PRIMARY = 0.05     # Sec 9
TARGET_ACTIVATION_SENSITIVITY = [0.02, 0.10]
COUNTER_MIN_META_SHARE = 0.01                  # Sec 10, reused verbatim from Phase 4.4's counter-availability floor
COUNTER_MIN_META_SHARE_SENSITIVITY = [0.005, 0.02]
COUNTER_MIN_TRAINING_GAMES = CANDIDATE_MIN_GAMES  # Sec 10: counter itself must be a legitimate, selectable candidate

N_BOOTSTRAP = 2000
RNG = np.random.default_rng(20260811)  # same seed as Phase 4.3b, for consistency


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


def load_confirmed_registry():
    reg = pd.read_csv(REGISTRY_CSV)
    confirmed = reg[reg["status"] == "OOS_CONFIRMED"].copy()
    confirmed["confirmation_date_dt"] = pd.to_datetime(confirmed["confirmation_date"])
    return reg, confirmed


class WindowStats:
    """Identical construction to Phase 4.3b's WindowStats -- recency is
    entirely encoded by the training slice passed in (always 14d, this phase)."""

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

    def matchup_estimate(self, a, b, mode="conservative"):
        n = self.pair_games.get((a, b), 0)
        w = self.pair_wins.get((a, b), 0)
        conf = confidence_flag(n)
        if n > 0:
            _, lo, _ = wilson_ci(w, n)
            if mode == "conservative":
                return lo, conf, "wilson_lo"
            return w / n, conf, "empirical"
        fb = np.clip(self.shrinkage(a) - self.shrinkage(b) + 0.5, 0.05, 0.95)
        return fb, conf, "fallback_shrinkage"

    def expected_win_rate(self, a, prior, mode="conservative"):
        total, weight_seen = 0.0, 0.0
        for b, pb in prior.items():
            est, _, _ = self.matchup_estimate(a, b, mode)
            total += pb * est
            weight_seen += pb
        return total / weight_seen if weight_seen > 0 else None


def strategy_most_popular(ws):
    if not ws.candidates:
        return None, None
    a = max(ws.candidates, key=lambda c: ws.full_prior.get(c, 0))
    return a, ws.full_prior.get(a)


def strategy_recent_wr(ws):
    if not ws.candidates:
        return None, None
    a = max(ws.candidates, key=lambda c: (ws.win_rate(c), ws.games.get(c, 0)))
    return a, ws.win_rate(a)


def strategy_conservative(ws):
    if not ws.candidates:
        return None, None, {}
    scored = {c: ws.expected_win_rate(c, ws.full_prior, "conservative") for c in ws.candidates}
    a = max(scored, key=lambda c: (scored[c] if scored[c] is not None else -1))
    return a, scored[a], scored


def counter_rows_available_at(confirmed, T, mode):
    """mode='primary' -> Experiment A (strict, time-gated); mode='frozen' -> Experiment B (always available)."""
    if mode == "frozen":
        return confirmed
    # Experiment A: only rows whose confirmation was known BEFORE this decision day
    # (T's own calendar day is excluded -- confirmation happened sometime during that
    # day's data collection, so a decision made "as of the start of T" could not yet
    # have relied on it; the rule becomes usable starting the NEXT calendar day).
    return confirmed[confirmed["confirmation_date_dt"] < T]


def counter_aware_score(ws, confirmed_rows, activation_threshold=TARGET_ACTIVATION_THRESHOLD_PRIMARY,
                         counter_share_floor=COUNTER_MIN_META_SHARE, contribution_field="oos_primary_horizon_win_rate"):
    """Returns dict a -> (final_score, base_score, contribution, triggers[list of dicts])."""
    if not ws.candidates:
        return {}
    out = {}
    by_counter = {}
    for _, row in confirmed_rows.iterrows():
        by_counter.setdefault(row["counter_archetype"], []).append(row)

    for a in ws.candidates:
        base = ws.expected_win_rate(a, ws.full_prior, "conservative")
        contribution = 0.0
        triggers = []
        a_share = ws.full_prior.get(a, 0.0)
        for row in by_counter.get(a, []):
            B = row["target_archetype"]
            tshare = ws.full_prior.get(B, 0.0)
            if tshare < activation_threshold:
                continue
            if a_share < counter_share_floor:
                continue
            if ws.games.get(a, 0) < COUNTER_MIN_TRAINING_GAMES:
                continue
            baseline_est, _, method = ws.matchup_estimate(a, B, "conservative")
            oos_est = float(row[contribution_field])
            contrib = tshare * (oos_est - baseline_est)
            contribution += contrib
            triggers.append({
                "target_archetype": B, "target_meta_share": tshare, "counter_oos_estimate": oos_est,
                "baseline_matchup_estimate": baseline_est, "baseline_method": method, "contribution": contrib,
            })
        final = (base if base is not None else 0.0) + contribution
        out[a] = (final, base, contribution, triggers)
    return out


def strategy_counter_aware(ws, confirmed_rows, **kwargs):
    scored = counter_aware_score(ws, confirmed_rows, **kwargs)
    if not scored:
        return None, None, None, None, []
    a = max(scored, key=lambda c: scored[c][0])
    final, base, contribution, triggers = scored[a]
    return a, final, base, contribution, triggers


def detect_opportunities(ws, confirmed_rows, activation_threshold=TARGET_ACTIVATION_THRESHOLD_PRIMARY,
                          counter_share_floor=COUNTER_MIN_META_SHARE):
    """An 'opportunity' (Sec 21) exists whenever a confirmed counter's full
    eligibility gate clears -- target share, counter viability, counter training
    games -- INDEPENDENT of whether that counter archetype ends up winning the
    argmax. This must not be confused with 'counter_active' (Sec 19), which
    describes only the actually-selected deck's own trigger status."""
    opps = []
    for _, row in confirmed_rows.iterrows():
        A, B = row["counter_archetype"], row["target_archetype"]
        if A not in ws.candidates:
            continue
        tshare = ws.full_prior.get(B, 0.0)
        a_share = ws.full_prior.get(A, 0.0)
        if tshare < activation_threshold or a_share < counter_share_floor:
            continue
        if ws.games.get(A, 0) < COUNTER_MIN_TRAINING_GAMES:
            continue
        opps.append({"counter_archetype": A, "target_archetype": B, "target_meta_share": tshare})
    return opps


def strategy_counter_only(ws, confirmed_rows, base_pick, activation_threshold=TARGET_ACTIVATION_THRESHOLD_PRIMARY,
                           counter_share_floor=COUNTER_MIN_META_SHARE):
    """Selects the validated counter archetype outright when its target opportunity
    qualifies; otherwise falls back to the base (Conservative Meta-Aware) pick.
    Diagnostic only -- tests standalone value of the raw override rule."""
    qualifying = []
    for _, row in confirmed_rows.iterrows():
        A, B = row["counter_archetype"], row["target_archetype"]
        if A not in ws.candidates:
            continue
        tshare = ws.full_prior.get(B, 0.0)
        a_share = ws.full_prior.get(A, 0.0)
        if tshare < activation_threshold or a_share < counter_share_floor:
            continue
        if ws.games.get(A, 0) < COUNTER_MIN_TRAINING_GAMES:
            continue
        qualifying.append((A, B, tshare, float(row["oos_primary_horizon_win_rate"])))
    if qualifying:
        qualifying.sort(key=lambda x: -x[3])
        A, B, tshare, oos_wr = qualifying[0]
        return A, True, B, tshare
    return base_pick, False, None, None


def evaluate_selection(test_df, cid):
    if cid is None:
        return 0, None, None
    sub = test_df[test_df["player_deck_cluster_id"] == cid]
    n = len(sub)
    if n == 0:
        return 0, 0, None
    w = int((sub["result"] == "WIN").sum())
    return n, w, w / n


def oracle_pick(test_df):
    if len(test_df) == 0:
        return None, None, None, None
    g = test_df.groupby("player_deck_cluster_id")
    games = g.size()
    wins = g.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False)
    elig = games[games >= ORACLE_MIN_TEST_GAMES].index
    if len(elig) == 0:
        return None, None, None, None
    wr = wins[elig] / games[elig]
    a = wr.idxmax()
    return a, int(games[a]), int(wins[a]), float(wr[a])


def best_deployable(test_df, candidates):
    """Regret ceiling: best test-day performer AMONG archetypes that were actually
    selectable that day (candidates, i.e. cleared the training-window candidacy floor),
    with enough test-day games to be a meaningful comparison. Deliberately NOT the
    Oracle (Sec 23) -- Oracle has no candidacy requirement at all."""
    if len(test_df) == 0 or not candidates:
        return None, None
    g = test_df[test_df["player_deck_cluster_id"].isin(candidates)].groupby("player_deck_cluster_id")
    if len(g) == 0:
        return None, None
    games = g.size()
    wins = g.apply(lambda x: int((x["result"] == "WIN").sum()), include_groups=False)
    elig = games[games >= ORACLE_MIN_TEST_GAMES].index
    if len(elig) == 0:
        return None, None
    wr = wins[elig] / games[elig]
    a = wr.idxmax()
    return a, float(wr[a])


def block_bootstrap_pooled(day_games, day_wins, n_boot=N_BOOTSTRAP):
    days = list(day_games.keys())
    if not days:
        return None, None, None
    total_g, total_w = sum(day_games.values()), sum(day_wins.values())
    point = total_w / total_g if total_g else None
    if len(days) < 2 or total_g == 0:
        return point, None, None
    boots = []
    for _ in range(n_boot):
        sample = RNG.choice(days, size=len(days), replace=True)
        g = sum(day_games[d] for d in sample)
        w = sum(day_wins[d] for d in sample)
        if g > 0:
            boots.append(w / g)
    if not boots:
        return point, None, None
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def paired_block_bootstrap_diff(day_games_1, day_wins_1, day_games_2, day_wins_2, n_boot=N_BOOTSTRAP):
    """Paired day-block bootstrap for a DIFFERENCE in pooled win rate between two
    strategies evaluated on (a subset of) the same decision days. Resamples day
    indices jointly so the pairing is preserved in every replicate."""
    common_days = sorted(set(day_games_1) & set(day_games_2))
    if len(common_days) < 2:
        return None, None, None, None
    g1 = sum(day_games_1[d] for d in common_days); w1 = sum(day_wins_1[d] for d in common_days)
    g2 = sum(day_games_2[d] for d in common_days); w2 = sum(day_wins_2[d] for d in common_days)
    point1 = w1 / g1 if g1 else None
    point2 = w2 / g2 if g2 else None
    if point1 is None or point2 is None:
        return None, None, None, None
    diff_point = point1 - point2
    boots = []
    for _ in range(n_boot):
        sample = RNG.choice(common_days, size=len(common_days), replace=True)
        gg1 = sum(day_games_1[d] for d in sample); ww1 = sum(day_wins_1[d] for d in sample)
        gg2 = sum(day_games_2[d] for d in sample); ww2 = sum(day_wins_2[d] for d in sample)
        if gg1 > 0 and gg2 > 0:
            boots.append(ww1 / gg1 - ww2 / gg2)
    if not boots:
        return diff_point, None, None, None
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p_value = 2 * min(np.mean(np.array(boots) <= 0), np.mean(np.array(boots) >= 0))
    p_value = min(1.0, p_value)
    return diff_point, float(lo), float(hi), float(p_value)


# ============================================================================
# main walk-forward
# ============================================================================

def main():
    decisive = load_data()
    registry, confirmed = load_confirmed_registry()
    print(f"Loaded {len(decisive)} decisive deck-slots ({len(decisive)//2} games) across "
          f"{decisive['date_dt'].nunique()} calendar days.")
    print(f"OOS_CONFIRMED counters consumed (frozen Phase 4.4 artifact): {len(confirmed)}")
    print(confirmed[["counter_archetype", "target_archetype", "oos_primary_horizon_win_rate",
                      "oos_primary_horizon_wilson_lo", "confirmation_date"]].to_string(index=False))

    # mechanical negative-control protection check (Sec 27)
    banned = registry[registry["status"].isin(["OOS_FAILED", "OOS_PENDING"])][
        ["counter_archetype", "target_archetype", "status"]]
    assert not set(zip(confirmed["counter_archetype"], confirmed["target_archetype"])) & \
           set(zip(banned["counter_archetype"], banned["target_archetype"])), \
        "A non-CONFIRMED counter leaked into the confirmed set!"
    print(f"Negative-control protection: {len(banned)} non-confirmed rows in registry, "
          f"0 overlap with confirmed set (mechanically verified).")

    dates = sorted(decisive["date_dt"].unique())
    wf_rows = []
    decision_log_rows = []
    leak_checks = {"temporal": [0, 0], "counter_info_availability": [0, 0]}  # [checked, failures]

    for T in dates[1:]:
        lo_bound = T - pd.Timedelta(days=TRAINING_WINDOW_DAYS)
        train_df = decisive[(decisive["date_dt"] < T) & (decisive["date_dt"] >= lo_bound)]
        test_df = decisive[decisive["date_dt"] == T]
        ws = WindowStats(train_df)

        latest_train_ts = train_df["timestamp_dt"].max() if len(train_df) else None
        first_test_ts = test_df["timestamp_dt"].min() if len(test_df) else None
        leak_ok = bool(latest_train_ts < first_test_ts) if (latest_train_ts is not None and first_test_ts is not None) else None
        if leak_ok is not None:
            leak_checks["temporal"][0] += 1
            if not leak_ok:
                leak_checks["temporal"][1] += 1

        if not ws.candidates:
            for strat in ["A_most_popular", "B_recent_wr", "C_conservative_meta_aware",
                          "D_counter_aware", "Counter_Only", "ORACLE"]:
                wf_rows.append(_row(T, strat, "PRIMARY", None, ws, None, None, None,
                                     "SKIPPED_NO_CANDIDATES", latest_train_ts, first_test_ts))
            for strat in ["D_counter_aware", "Counter_Only"]:
                wf_rows.append(_row(T, strat, "FROZEN_DIAGNOSTIC", None, ws, None, None, None,
                                     "SKIPPED_NO_CANDIDATES", latest_train_ts, first_test_ts))
            continue

        a_pick, a_score = strategy_most_popular(ws)
        b_pick, b_score = strategy_recent_wr(ws)
        c_pick, c_score, c_scored_all = strategy_conservative(ws)

        conf_primary = counter_rows_available_at(confirmed, T, "primary")
        conf_frozen = counter_rows_available_at(confirmed, T, "frozen")

        # mechanical check: counter info must never be used before its confirmation date+1
        leak_checks["counter_info_availability"][0] += 1
        if len(conf_primary) > 0:
            if (conf_primary["confirmation_date_dt"] >= T).any():
                leak_checks["counter_info_availability"][1] += 1

        d_pick_p, d_final_p, d_base_p, d_contrib_p, d_trig_p = strategy_counter_aware(ws, conf_primary)
        d_pick_f, d_final_f, d_base_f, d_contrib_f, d_trig_f = strategy_counter_aware(ws, conf_frozen)

        opps_p = detect_opportunities(ws, conf_primary)
        opps_f = detect_opportunities(ws, conf_frozen)

        co_pick_p, co_trig_p, co_target_p, co_tshare_p = strategy_counter_only(ws, conf_primary, c_pick)
        co_pick_f, co_trig_f, co_target_f, co_tshare_f = strategy_counter_only(ws, conf_frozen, c_pick)

        o_pick, o_n, o_w, o_wr = oracle_pick(test_df)

        for strat, pick, extra in [
            ("A_most_popular", a_pick, {"base_score": a_score, "counter_contribution": None, "final_score": a_score}),
            ("B_recent_wr", b_pick, {"base_score": b_score, "counter_contribution": None, "final_score": b_score}),
            ("C_conservative_meta_aware", c_pick, {"base_score": c_score, "counter_contribution": None, "final_score": c_score}),
        ]:
            n, w, wr = evaluate_selection(test_df, pick)
            wf_rows.append(_row(T, strat, "PRIMARY", pick, ws, n, w, wr, "OK" if n else "SKIPPED_NO_TEST_DATA",
                                 latest_train_ts, first_test_ts, **extra))

        # D_counter_aware -- PRIMARY (Experiment A)
        # target_archetype/target_meta_share describe the OPPORTUNITY (Sec 21, independent
        # of which archetype won); counter_active/counter_archetype describe whether the
        # counter actually influenced the SELECTED deck's own score (Sec 19).
        n, w, wr = evaluate_selection(test_df, d_pick_p)
        target_p = opps_p[0]["target_archetype"] if opps_p else None
        tshare_p = opps_p[0]["target_meta_share"] if opps_p else None
        wf_rows.append(_row(T, "D_counter_aware", "PRIMARY", d_pick_p, ws, n, w, wr,
                             "OK" if n else "SKIPPED_NO_TEST_DATA", latest_train_ts, first_test_ts,
                             base_score=d_base_p, counter_contribution=d_contrib_p, final_score=d_final_p,
                             counter_active=bool(d_trig_p), counter_archetype=(d_pick_p if d_trig_p else None),
                             target_archetype=target_p, target_meta_share=tshare_p, is_opportunity=bool(opps_p)))
        # D_counter_aware -- FROZEN_DIAGNOSTIC (Experiment B)
        n, w, wr = evaluate_selection(test_df, d_pick_f)
        target_f = opps_f[0]["target_archetype"] if opps_f else None
        tshare_f = opps_f[0]["target_meta_share"] if opps_f else None
        wf_rows.append(_row(T, "D_counter_aware", "FROZEN_DIAGNOSTIC", d_pick_f, ws, n, w, wr,
                             "OK" if n else "SKIPPED_NO_TEST_DATA", latest_train_ts, first_test_ts,
                             base_score=d_base_f, counter_contribution=d_contrib_f, final_score=d_final_f,
                             counter_active=bool(d_trig_f), counter_archetype=(d_pick_f if d_trig_f else None),
                             target_archetype=target_f, target_meta_share=tshare_f, is_opportunity=bool(opps_f)))

        # Counter_Only -- PRIMARY & FROZEN
        n, w, wr = evaluate_selection(test_df, co_pick_p)
        wf_rows.append(_row(T, "Counter_Only", "PRIMARY", co_pick_p, ws, n, w, wr,
                             "OK" if n else "SKIPPED_NO_TEST_DATA", latest_train_ts, first_test_ts,
                             counter_active=co_trig_p, counter_archetype=(co_pick_p if co_trig_p else None),
                             target_archetype=co_target_p, target_meta_share=co_tshare_p))
        n, w, wr = evaluate_selection(test_df, co_pick_f)
        wf_rows.append(_row(T, "Counter_Only", "FROZEN_DIAGNOSTIC", co_pick_f, ws, n, w, wr,
                             "OK" if n else "SKIPPED_NO_TEST_DATA", latest_train_ts, first_test_ts,
                             counter_active=co_trig_f, counter_archetype=(co_pick_f if co_trig_f else None),
                             target_archetype=co_target_f, target_meta_share=co_tshare_f))

        # Oracle (diagnostic ceiling, not used for selection)
        wf_rows.append(_row(T, "ORACLE", "PRIMARY", o_pick, ws, o_n, o_w, o_wr,
                             "OK" if o_n else "SKIPPED_NO_ORACLE_CANDIDATE", latest_train_ts, first_test_ts))

        # best-deployable regret ceiling stashed on every PRIMARY row via a side table
        bd_pick, bd_wr = best_deployable(test_df, ws.candidates)
        wf_rows.append(_row(T, "BEST_DEPLOYABLE", "PRIMARY", bd_pick, ws, None, None, bd_wr,
                             "OK" if bd_wr is not None else "SKIPPED_NO_ELIGIBLE_CANDIDATE",
                             latest_train_ts, first_test_ts))

        # per-decision audit log (Sec 16) -- Counter-Aware only, both experiments
        for exp_label, pick, final, base, contrib, trig in [
            ("PRIMARY", d_pick_p, d_final_p, d_base_p, d_contrib_p, d_trig_p),
            ("FROZEN_DIAGNOSTIC", d_pick_f, d_final_f, d_base_f, d_contrib_f, d_trig_f),
        ]:
            if trig:
                for t in trig:
                    decision_log_rows.append({
                        "decision_day": T.date().isoformat(), "experiment": exp_label,
                        "counter_triggered": True, "target_archetype": t["target_archetype"],
                        "target_meta_share": round(t["target_meta_share"], 4),
                        "counter_archetype": pick,
                        "counter_oos_win_rate": round(t["counter_oos_estimate"], 4),
                        "counter_oos_games": int(confirmed.loc[confirmed["counter_archetype"] == pick,
                                                                 "oos_primary_horizon_games"].iloc[0]) if pick in set(confirmed["counter_archetype"]) else None,
                        "base_expected_win_rate": round(base, 4) if base is not None else None,
                        "counter_adjustment": round(t["contribution"], 4),
                        "final_expected_win_rate": round(final, 4) if final is not None else None,
                        "selected_archetype": pick,
                    })
            else:
                decision_log_rows.append({
                    "decision_day": T.date().isoformat(), "experiment": exp_label,
                    "counter_triggered": False, "target_archetype": None, "target_meta_share": None,
                    "counter_archetype": None, "counter_oos_win_rate": None, "counter_oos_games": None,
                    "base_expected_win_rate": round(base, 4) if base is not None else None,
                    "counter_adjustment": 0.0,
                    "final_expected_win_rate": round(final, 4) if final is not None else None,
                    "selected_archetype": pick,
                })

    wf_df = pd.DataFrame(wf_rows)
    wf_df.to_csv(os.path.join(OUT_DIR, "counter_aware_walk_forward.csv"), index=False)
    print(f"\nWrote counter_aware_walk_forward.csv: {len(wf_df)} rows.")

    dec_df = pd.DataFrame(decision_log_rows)
    dec_df.to_csv(os.path.join(OUT_DIR, "counter_aware_decisions.csv"), index=False)
    print(f"Wrote counter_aware_decisions.csv: {len(dec_df)} rows.")

    # ---------------- leakage audit ----------------
    leak_rows = [
        {"check_type": "temporal_train_before_test", "total_checked": leak_checks["temporal"][0],
         "failures": leak_checks["temporal"][1]},
        {"check_type": "counter_info_not_used_before_confirmation", "total_checked": leak_checks["counter_info_availability"][0],
         "failures": leak_checks["counter_info_availability"][1]},
    ]
    leak_df = pd.DataFrame(leak_rows)
    leak_df.to_csv(os.path.join(OUT_DIR, "counter_aware_leakage_audit.csv"), index=False)
    print(f"Wrote counter_aware_leakage_audit.csv:\n{leak_df.to_string(index=False)}")

    # ---------------- headline comparison (Sec 34) ----------------
    primary = wf_df[(wf_df["experiment"] == "PRIMARY") & (wf_df["status"] == "OK")]
    comp_rows = []
    day_stats = {}
    for strat in ["A_most_popular", "B_recent_wr", "C_conservative_meta_aware", "D_counter_aware", "Counter_Only", "ORACLE"]:
        g = primary[primary["strategy"] == strat]
        dg = g.groupby("decision_day")["test_games"].sum().to_dict()
        dw = g.groupby("decision_day")["wins"].sum().to_dict()
        day_stats[strat] = (dg, dw)
        point, lo, hi = block_bootstrap_pooled(dg, dw)
        daily_wrs = g["win_rate"].dropna()
        comp_rows.append({
            "strategy": strat, "oos_win_rate": round(point, 4) if point is not None else None,
            "games": int(g["test_games"].sum()), "wins": int(g["wins"].sum()),
            "decision_days": g["decision_day"].nunique(),
            "bootstrap_ci_lo": round(lo, 4) if lo is not None else None,
            "bootstrap_ci_hi": round(hi, 4) if hi is not None else None,
            "median_daily_win_rate": round(daily_wrs.median(), 4) if len(daily_wrs) else None,
            "std_daily_win_rate": round(daily_wrs.std(), 4) if len(daily_wrs) > 1 else None,
        })
    comp_df = pd.DataFrame(comp_rows)
    recent_wr_row = comp_df[comp_df["strategy"] == "B_recent_wr"].iloc[0]
    comp_df["delta_vs_recent_wr"] = (comp_df["oos_win_rate"] - recent_wr_row["oos_win_rate"]).round(4)

    # paired comparisons vs Recent WR / Most Popular / Conservative
    dg_d, dw_d = day_stats["D_counter_aware"]
    stat_rows = []
    for opponent in ["B_recent_wr", "A_most_popular", "C_conservative_meta_aware"]:
        dg_o, dw_o = day_stats[opponent]
        diff, lo, hi, p = paired_block_bootstrap_diff(dg_d, dw_d, dg_o, dw_o)
        stat_rows.append({"comparison": f"D_counter_aware vs {opponent}", "abs_difference": round(diff, 4) if diff is not None else None,
                           "ci_lo": round(lo, 4) if lo is not None else None, "ci_hi": round(hi, 4) if hi is not None else None,
                           "p_value": round(p, 4) if p is not None else None,
                           "significant_95pct": bool(lo is not None and hi is not None and (lo > 0 or hi < 0))})
    stat_df = pd.DataFrame(stat_rows)

    comp_df.to_csv(os.path.join(OUT_DIR, "counter_aware_comparison.csv"), index=False)
    print(f"\nWrote counter_aware_comparison.csv:\n{comp_df.to_string(index=False)}")
    print(f"\nPaired comparisons (day-block bootstrap):\n{stat_df.to_string(index=False)}")
    # append stat rows to the comparison file as a labeled second block for a single source of truth
    with open(os.path.join(OUT_DIR, "counter_aware_comparison.csv"), "a", encoding="utf-8") as f:
        f.write("\n# paired_statistical_comparisons\n")
        stat_df.to_csv(f, index=False)

    # ---------------- counter trigger analysis (Sec 19) ----------------
    d_primary = primary[primary["strategy"] == "D_counter_aware"]
    trig_rows = []
    for active_flag, label in [(True, "ACTIVE"), (False, "INACTIVE")]:
        sub = d_primary[d_primary["counter_active"] == active_flag]
        n, w = int(sub["test_games"].sum()), int(sub["wins"].sum())
        trig_rows.append({"counter_status": label, "decision_days": sub["decision_day"].nunique(),
                           "games": n, "wins": w, "win_rate": round(w / n, 4) if n else None})
    trig_df = pd.DataFrame(trig_rows)
    active_wr = trig_df.loc[trig_df["counter_status"] == "ACTIVE", "win_rate"].iloc[0]
    inactive_wr = trig_df.loc[trig_df["counter_status"] == "INACTIVE", "win_rate"].iloc[0]
    trig_df["incremental_vs_inactive"] = trig_df["win_rate"] - inactive_wr if inactive_wr is not None else None
    trig_df.to_csv(os.path.join(OUT_DIR, "counter_trigger_analysis.csv"), index=False)
    print(f"\nWrote counter_trigger_analysis.csv:\n{trig_df.to_string(index=False)}")

    # ---------------- selection changes (Sec 21-22) ----------------
    c_rows = primary[primary["strategy"] == "C_conservative_meta_aware"][["decision_day", "selected_archetype"]].rename(
        columns={"selected_archetype": "base_selected_archetype"})
    d_rows = primary[primary["strategy"] == "D_counter_aware"][
        ["decision_day", "selected_archetype", "counter_active", "target_meta_share", "is_opportunity"]].rename(
        columns={"selected_archetype": "counter_aware_selected_archetype"})
    sel_df = c_rows.merge(d_rows, on="decision_day", how="outer")
    sel_df["selection_changed"] = sel_df["base_selected_archetype"] != sel_df["counter_aware_selected_archetype"]
    sel_df.to_csv(os.path.join(OUT_DIR, "counter_selection_changes.csv"), index=False)
    n_opportunities = int(sel_df["is_opportunity"].sum())
    n_triggered = int(sel_df["counter_active"].fillna(False).sum())
    n_changed = int(sel_df["selection_changed"].sum())
    n_total_decisions = len(sel_df)
    print(f"\nWrote counter_selection_changes.csv: {n_total_decisions} decisions, "
          f"{n_opportunities} opportunities, {n_triggered} counter-triggered, "
          f"{n_changed} selection changes ({100*n_changed/n_total_decisions:.2f}%).")

    # ---------------- regret analysis (Sec 23) ----------------
    bd = primary[primary["strategy"] == "BEST_DEPLOYABLE"][["decision_day", "win_rate"]].rename(
        columns={"win_rate": "best_deployable_win_rate"})
    regret_rows = []
    for strat in ["A_most_popular", "B_recent_wr", "C_conservative_meta_aware", "D_counter_aware", "Counter_Only"]:
        g = primary[primary["strategy"] == strat][["decision_day", "win_rate"]].rename(columns={"win_rate": "chosen_win_rate"})
        m = g.merge(bd, on="decision_day", how="inner").dropna()
        m["regret"] = m["best_deployable_win_rate"] - m["chosen_win_rate"]
        m["strategy"] = strat
        regret_rows.append(m)
    regret_df = pd.concat(regret_rows, axis=0, ignore_index=True)
    regret_df.to_csv(os.path.join(OUT_DIR, "counter_regret_analysis.csv"), index=False)
    regret_summary = regret_df.groupby("strategy")["regret"].agg(
        mean_regret="mean", median_regret="median", p95_regret=lambda s: s.quantile(0.95), n_days="count")
    print(f"\nWrote counter_regret_analysis.csv. Summary:\n{regret_summary.to_string()}")

    # ---------------- sensitivity analysis (Sec 26) ----------------
    sens_rows = []
    baseline_wr = comp_df.loc[comp_df["strategy"] == "D_counter_aware", "oos_win_rate"].iloc[0]

    def rerun_primary_D(activation_threshold=TARGET_ACTIVATION_THRESHOLD_PRIMARY,
                         counter_share_floor=COUNTER_MIN_META_SHARE, contribution_field="oos_primary_horizon_win_rate"):
        dg, dw = {}, {}
        for T in dates[1:]:
            lo_bound = T - pd.Timedelta(days=TRAINING_WINDOW_DAYS)
            train_df = decisive[(decisive["date_dt"] < T) & (decisive["date_dt"] >= lo_bound)]
            test_df = decisive[decisive["date_dt"] == T]
            ws = WindowStats(train_df)
            if not ws.candidates:
                continue
            conf_primary = counter_rows_available_at(confirmed, T, "primary")
            pick, _, _, _, _ = strategy_counter_aware(ws, conf_primary, activation_threshold=activation_threshold,
                                                       counter_share_floor=counter_share_floor,
                                                       contribution_field=contribution_field)
            n, w, wr = evaluate_selection(test_df, pick)
            if n:
                dg[T.date().isoformat()] = n
                dw[T.date().isoformat()] = w
        point, lo, hi = block_bootstrap_pooled(dg, dw)
        return point

    for thr in TARGET_ACTIVATION_SENSITIVITY + [TARGET_ACTIVATION_THRESHOLD_PRIMARY]:
        wr = rerun_primary_D(activation_threshold=thr)
        sens_rows.append({"variant_type": "target_share_threshold", "variant_value": thr,
                           "counter_aware_oos_win_rate": round(wr, 4) if wr is not None else None,
                           "delta_vs_primary": round(wr - baseline_wr, 4) if wr is not None else None,
                           "is_primary": thr == TARGET_ACTIVATION_THRESHOLD_PRIMARY})
    for thr in COUNTER_MIN_META_SHARE_SENSITIVITY + [COUNTER_MIN_META_SHARE]:
        wr = rerun_primary_D(counter_share_floor=thr)
        sens_rows.append({"variant_type": "counter_share_threshold", "variant_value": thr,
                           "counter_aware_oos_win_rate": round(wr, 4) if wr is not None else None,
                           "delta_vs_primary": round(wr - baseline_wr, 4) if wr is not None else None,
                           "is_primary": thr == COUNTER_MIN_META_SHARE})
    for field, label in [("oos_primary_horizon_win_rate", "raw_oos_win_rate"),
                          ("oos_primary_horizon_wilson_lo", "conservative_oos_wilson_lo")]:
        wr = rerun_primary_D(contribution_field=field)
        sens_rows.append({"variant_type": "counter_contribution_estimate", "variant_value": label,
                           "counter_aware_oos_win_rate": round(wr, 4) if wr is not None else None,
                           "delta_vs_primary": round(wr - baseline_wr, 4) if wr is not None else None,
                           "is_primary": field == "oos_primary_horizon_win_rate"})
    sens_df = pd.DataFrame(sens_rows)
    sens_df.to_csv(os.path.join(OUT_DIR, "counter_aware_sensitivity.csv"), index=False)
    print(f"\nWrote counter_aware_sensitivity.csv:\n{sens_df.to_string(index=False)}")

    # ---------------- Fezandipiti / Mewtwo specific analysis (Sec 20) -- printed for the report ----------------
    print("\n" + "=" * 70 + "\nFezandipiti / Mewtwo opponent-specific analysis (both experiments):")
    for exp_label in ["PRIMARY", "FROZEN_DIAGNOSTIC"]:
        d_exp = wf_df[(wf_df["experiment"] == exp_label) & (wf_df["strategy"] == "D_counter_aware") &
                      (wf_df["status"] == "OK")]
        mewtwo_days = d_exp[d_exp["selected_archetype"] == "Team Rocket's Mewtwo ex"]["decision_day"].tolist()
        opp_games = decisive[(decisive["date_dt"].astype(str).isin(mewtwo_days)) &
                              (decisive["player_deck_cluster_id"] == "Team Rocket's Mewtwo ex") &
                              (decisive["opponent_deck_cluster_id"] == "Fezandipiti ex")]
        n_opp, w_opp = len(opp_games), int((opp_games["result"] == "WIN").sum())
        print(f"[{exp_label}] Mewtwo-selected days: {len(mewtwo_days)}; "
              f"of those, Mewtwo-vs-Fezandipiti games: {n_opp}, wins: {w_opp}, "
              f"win rate: {round(w_opp/n_opp,4) if n_opp else None}")

    print("\nDONE.")
    return wf_df, dec_df, comp_df, stat_df, trig_df, sel_df, regret_df, sens_df, leak_df


def _row(T, strategy, experiment, selected, ws, n, w, wr, status, latest_train_ts, first_test_ts,
         base_score=None, counter_contribution=None, final_score=None,
         counter_active=None, counter_archetype=None, target_archetype=None, target_meta_share=None,
         is_opportunity=False):
    leak_ok = None
    if latest_train_ts is not None and first_test_ts is not None:
        leak_ok = bool(latest_train_ts < first_test_ts)
    return {
        "decision_day": T.date().isoformat(), "strategy": strategy, "experiment": experiment,
        "selected_archetype": selected, "training_window": f"{TRAINING_WINDOW_DAYS}d",
        "training_games": ws.total_games, "test_games": n if n is not None else 0,
        "wins": w, "losses": (n - w) if (n is not None and w is not None) else None,
        "win_rate": round(wr, 4) if wr is not None else None,
        "target_meta_share": round(target_meta_share, 4) if target_meta_share is not None else None,
        "is_opportunity": bool(is_opportunity),
        "counter_active": bool(counter_active) if counter_active is not None else False,
        "counter_archetype": counter_archetype, "target_archetype": target_archetype,
        "base_score": round(base_score, 4) if base_score is not None else None,
        "counter_contribution": round(counter_contribution, 4) if counter_contribution is not None else None,
        "final_score": round(final_score, 4) if final_score is not None else None,
        "status": status, "latest_training_timestamp": latest_train_ts.isoformat() if latest_train_ts is not None else None,
        "first_test_timestamp": first_test_ts.isoformat() if first_test_ts is not None else None,
        "latest_train_before_first_test": leak_ok,
    }


if __name__ == "__main__":
    main()
