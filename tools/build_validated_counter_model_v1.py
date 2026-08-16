"""Phase 4.4 -- Validated Counter Model.

Builds a rigorous, time-aware counter-detection system on top of the existing
3,499-episode dataset (results/meta/episodes_summary.parquet) and Phase
4.1-4.3b outputs. Determines which historical matchup advantages are
reliable, actionable counters vs. statistical artifacts, using ONLY
statistical thresholds + temporal detection + persistence + OOS confirmation
+ expiration. No RL/MCTS/search/opponent-inference/ML. Zero new downloads.

State machine per counter pair A->B:
  UNKNOWN -> CANDIDATE -> DETECTED -> OOS_PENDING -> OOS_CONFIRMED
                                    \\-> OOS_FAILED
DETECTED is frozen: everything after detection_date uses only information
available at detection_date; OOS results never retroactively change the
detection date or thresholds (Sec 34, no hindsight contamination).

Writes:
  results/meta/counter_registry.csv
  results/meta/counter_lifecycle.csv
  results/meta/counter_matrix.csv
  results/meta/counter_oos_validation.csv
  results/meta/current_validated_counters.csv
  results/meta/counter_false_positive_analysis.csv
  results/meta/counter_detection_events.csv   (optional, transparency)
  results/meta/counter_coverage.csv           (optional)
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

# ============================================================================
# PRIMARY CONFIGURATION -- declared before running detection or looking at
# final results (Sec 35, no parameter fishing). Sensitivity variants are
# computed separately and clearly labeled as such, never used to pick the
# primary result.
# ============================================================================
Z = 1.96                                   # 95% Wilson CI -- reused exactly from Phase 4.2/4.3b
MIN_MATCHUP_SAMPLE_PRIMARY = 50            # Sec 5 -- reused from Phase 4.2's credible-counter gate
MIN_MATCHUP_SAMPLE_SENSITIVITY = [20, 100]
EFFECT_SIZE_PRIMARY = 0.60                 # Sec 7
EFFECT_SIZE_SENSITIVITY = [0.55, 0.65, 0.70]
UNIVERSE_MIN_GAMES = 20                    # floor to even enter the candidate universe (lowest sensitivity value)

META_SHARE_WINDOW_DAYS = 14                # rolling "current" window, reuses Phase 4.3b's 14d window definition
TARGET_HIGH_SHARE = 0.15                   # reused verbatim from Phase 4.2's DOMINANT_RECENT_SHARE = 15%
TARGET_MEDIUM_SHARE = 0.05                 # round split point between the project's observed archetype shares
COUNTER_MIN_META_SHARE = 0.01              # Sec 9 "practical availability" floor -- below this, purely statistical curiosity

PERSISTENCE_MIN_CONSECUTIVE = 2            # Sec 13

OOS_HORIZONS = [25, 50, 100, 150]          # Sec 15
OOS_PRIMARY_HORIZON = 25                   # smallest Sec-15 horizon; declared given this dataset's short
                                            # post-detection windows (56 calendar days total, matchup pairs
                                            # need n>=50 full-history games before they can even become
                                            # candidates, which itself consumes much of the timeline)
OOS_CONFIRM_WR = 0.55                      # Sec 16 "stronger primary criterion"
OOS_CONFIRM_WILSON_LO = 0.50
OOS_FAIL_WR = 0.50                         # Sec 17 predeclared primary failure threshold
OOS_FAIL_SENSITIVITY = [0.45, 0.48]

RNG_SEED = 20260811  # unused here (no bootstrap needed) but kept for consistency with prior phases


def wilson_ci(wins, n, z=Z):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def sample_confidence_flag(n):
    if n < 20:
        return "INSUFFICIENT"
    elif n < 50:
        return "LOW_CONFIDENCE"
    elif n < 100:
        return "USABLE"
    else:
        return "HIGH_CONFIDENCE"


def relevance_tier(share):
    if share is None or (isinstance(share, float) and np.isnan(share)):
        return None
    if share >= TARGET_HIGH_SHARE:
        return "HIGH"
    elif share >= TARGET_MEDIUM_SHARE:
        return "MEDIUM"
    else:
        return "LOW"


def load_data():
    df = pd.read_parquet(PARQUET)
    decisive = df[df["outcome_type"] == "DECISIVE"].copy()
    decisive["date_dt"] = pd.to_datetime(decisive["date"]).dt.normalize()
    decisive["timestamp_dt"] = pd.to_datetime(decisive["timestamp"])
    return decisive.sort_values("timestamp_dt")


def named_archetypes(decisive):
    ids = set(decisive["player_deck_cluster_id"].unique()) | set(decisive["opponent_deck_cluster_id"].unique())
    return sorted(a for a in ids if not str(a).startswith("UNLABELED_CLUSTER"))


def build_candidate_universe(decisive, archetypes, min_games=UNIVERSE_MIN_GAMES):
    """Every ordered pair (A,B), A!=B, among named archetypes with full-dataset
    games(A vs B) >= min_games (the most permissive sensitivity floor -- if a
    pair never reaches even this over the WHOLE dataset it cannot pass any
    sensitivity variant either, so excluding it here changes no result)."""
    pairs = []
    g = decisive.groupby(["player_deck_cluster_id", "opponent_deck_cluster_id"]).size()
    for A in archetypes:
        for B in archetypes:
            if A == B:
                continue
            n = int(g.get((A, B), 0))
            if n >= min_games:
                pairs.append((A, B, n))
    return pairs


def pair_cumulative_before(decisive, dates_idx, A, B):
    """cumulative (games, wins) for A-vs-B strictly BEFORE each date in dates_idx."""
    sub = decisive[(decisive["player_deck_cluster_id"] == A) & (decisive["opponent_deck_cluster_id"] == B)]
    daily_g = sub.groupby("date_dt").size()
    daily_w = sub[sub["result"] == "WIN"].groupby("date_dt").size()
    g = daily_g.reindex(dates_idx, fill_value=0)
    w = daily_w.reindex(dates_idx, fill_value=0)
    before_g = g.cumsum().shift(1, fill_value=0)
    before_w = w.cumsum().shift(1, fill_value=0)
    return before_g, before_w


def archetype_share_series(decisive, dates_idx, archetype, total_daily):
    """Rolling META_SHARE_WINDOW_DAYS-day share of `archetype` (player-side deck-slots),
    for the window ending strictly BEFORE each date in dates_idx."""
    sub = decisive[decisive["player_deck_cluster_id"] == archetype]
    daily = sub.groupby("date_dt").size().reindex(dates_idx, fill_value=0)
    roll_g = daily.rolling(META_SHARE_WINDOW_DAYS, min_periods=1).sum().shift(1)
    roll_total = total_daily.rolling(META_SHARE_WINDOW_DAYS, min_periods=1).sum().shift(1)
    return roll_g / roll_total.replace(0, np.nan)


def detect_pair(decisive, dates_idx, A, B, share_series, events_log):
    before_g, before_w = pair_cumulative_before(decisive, dates_idx, A, B)
    target_share = share_series[B]
    counter_share = share_series[A]

    candidate_date = None
    detection_date = None
    consecutive_pass = 0
    detection_frozen = None

    for T in dates_idx:
        n = int(before_g.loc[T])
        w = int(before_w.loc[T])
        wr, lo, hi = wilson_ci(w, n)
        stat_gate = (n >= MIN_MATCHUP_SAMPLE_PRIMARY) and (wr >= EFFECT_SIZE_PRIMARY) and (lo > 0.5)

        tshare = target_share.loc[T]
        cshare = counter_share.loc[T]
        target_ok = (not pd.isna(tshare)) and (relevance_tier(tshare) in ("MEDIUM", "HIGH"))
        counter_ok = (not pd.isna(cshare)) and (cshare >= COUNTER_MIN_META_SHARE)
        full_gate = stat_gate and target_ok and counter_ok

        if candidate_date is None and stat_gate:
            candidate_date = T

        if full_gate:
            consecutive_pass += 1
        else:
            consecutive_pass = 0

        if detection_date is None and consecutive_pass >= PERSISTENCE_MIN_CONSECUTIVE:
            detection_date = T
            detection_frozen = dict(
                games=n, wins=w, win_rate=wr, wilson_lo=lo, wilson_hi=hi,
                target_meta_share=tshare, counter_meta_share=cshare,
            )

        events_log.append({
            "counter_archetype": A, "target_archetype": B, "date": T.date().isoformat(),
            "games_before": n, "wins_before": w,
            "win_rate_before": round(wr, 4), "wilson_lo_before": round(lo, 4),
            "target_meta_share_14d": round(tshare, 4) if not pd.isna(tshare) else None,
            "counter_meta_share_14d": round(cshare, 4) if not pd.isna(cshare) else None,
            "stat_gate_pass": bool(stat_gate), "full_gate_pass": bool(full_gate),
            "consecutive_full_gate_passes": consecutive_pass,
            "is_candidate_date": T == candidate_date,
            "is_detection_date": T == detection_date,
        })

        if detection_date is not None:
            # Detection frozen -- stop advancing state for this pair (Sec 14 FREEZE).
            # (Events log continues to be filled for remaining dates by the caller's
            #  outer loop structure only if we don't break -- but Sec 14 requires
            #  freezing, so we break here; nothing past detection_date affects state.)
            break

    return candidate_date, detection_date, detection_frozen


def compute_oos(decisive, A, B, detection_date):
    fut = decisive[(decisive["date_dt"] >= detection_date) &
                    (decisive["player_deck_cluster_id"] == A) &
                    (decisive["opponent_deck_cluster_id"] == B)].sort_values("timestamp_dt")
    total_n = len(fut)
    horizon_results = {}
    for h in OOS_HORIZONS:
        if total_n < h:
            horizon_results[h] = None
            continue
        sub = fut.iloc[:h]
        w = int((sub["result"] == "WIN").sum())
        wr, lo, hi = wilson_ci(w, h)
        horizon_results[h] = dict(n=h, w=w, wr=wr, lo=lo, hi=hi)
    all_available = None
    if total_n > 0:
        w = int((fut["result"] == "WIN").sum())
        wr, lo, hi = wilson_ci(w, total_n)
        all_available = dict(n=total_n, w=w, wr=wr, lo=lo, hi=hi)
    return horizon_results, all_available, fut


def oos_status_from_primary(horizon_results):
    primary = horizon_results.get(OOS_PRIMARY_HORIZON)
    if primary is None:
        return "OOS_PENDING", "insufficient_future_games_for_primary_horizon", None
    wr, lo = primary["wr"], primary["lo"]
    if wr >= OOS_CONFIRM_WR and lo > OOS_CONFIRM_WILSON_LO:
        return "OOS_CONFIRMED", "CONFIRMED_PRIMARY_BAR", primary
    if wr < OOS_FAIL_WR:
        return "OOS_FAILED", "COLLAPSED_BELOW_50PCT", primary
    return "OOS_FAILED", "DID_NOT_CLEAR_PRIMARY_BAR", primary


def lifecycle_trend(horizon_results):
    """Classify stable/decaying/failed using Wilson-CI overlap across available
    cumulative horizons (Sec 21) -- avoids over-reacting to small win-rate wobble."""
    avail = [(h, r) for h, r in horizon_results.items() if r is not None]
    avail.sort(key=lambda x: x[0])
    if len(avail) < 2:
        return "INSUFFICIENT_HORIZONS_FOR_TREND", avail
    first_h, first_r = avail[0]
    last_h, last_r = avail[-1]
    if last_r["hi"] < 0.50:
        return "FAILED", avail
    if last_r["hi"] < first_r["lo"]:
        return "DECAYING", avail
    return "STABLE", avail


def main():
    decisive = load_data()
    dates_idx = pd.DatetimeIndex(sorted(decisive["date_dt"].unique()))
    print(f"Loaded {len(decisive)} decisive deck-slots ({len(decisive)//2} games) "
          f"across {len(dates_idx)} calendar days ({dates_idx.min().date()} to {dates_idx.max().date()}).")

    archetypes = named_archetypes(decisive)
    print(f"Named archetype universe ({len(archetypes)}): {archetypes}")

    universe = build_candidate_universe(decisive, archetypes)
    print(f"Candidate universe (full-dataset games >= {UNIVERSE_MIN_GAMES}): {len(universe)} directed pairs.")

    total_daily = decisive.groupby("date_dt").size().reindex(dates_idx, fill_value=0)
    share_series = {a: archetype_share_series(decisive, dates_idx, a, total_daily) for a in archetypes}

    # "today" = current 14-day-share snapshot as of the end of the dataset, for the
    # registry's current-relevance / expiration checks and the coverage report.
    current_share = {}
    for a in archetypes:
        sub = decisive[decisive["player_deck_cluster_id"] == a]
        daily = sub.groupby("date_dt").size().reindex(dates_idx, fill_value=0)
        window = daily.iloc[-META_SHARE_WINDOW_DAYS:]
        tot_window = total_daily.iloc[-META_SHARE_WINDOW_DAYS:]
        current_share[a] = float(window.sum() / tot_window.sum()) if tot_window.sum() else None

    events_log = []
    registry_rows = []
    oos_rows = []
    lifecycle_rows = []

    for (A, B, n_full) in universe:
        candidate_date, detection_date, frozen = detect_pair(decisive, dates_idx, A, B, share_series, events_log)

        status = "UNKNOWN"
        if candidate_date is not None:
            status = "CANDIDATE"
        oos_status = None
        oos_detail = None
        oos_games = oos_wins = oos_wr = oos_lo = None
        confirmation_date = failure_date = None
        horizon_results = {}
        all_available = None

        if detection_date is not None:
            status = "DETECTED"
            horizon_results, all_available, fut = compute_oos(decisive, A, B, detection_date)
            oos_status, oos_detail, primary = oos_status_from_primary(horizon_results)
            status = oos_status
            if primary is not None:
                oos_games, oos_wins, oos_wr, oos_lo = primary["n"], primary["w"], primary["wr"], primary["lo"]
            elif all_available is not None:
                oos_games, oos_wins, oos_wr, oos_lo = (all_available["n"], all_available["w"],
                                                         all_available["wr"], all_available["lo"])
            if oos_status == "OOS_CONFIRMED":
                confirmation_date = fut.iloc[OOS_PRIMARY_HORIZON - 1]["date_dt"].date().isoformat()
            elif oos_status == "OOS_FAILED":
                idx = min(OOS_PRIMARY_HORIZON, len(fut)) - 1
                failure_date = fut.iloc[idx]["date_dt"].date().isoformat() if len(fut) else None

            for h, r in horizon_results.items():
                if r is None:
                    continue
                oos_rows.append({
                    "counter_archetype": A, "target_archetype": B, "detection_date": detection_date.date().isoformat(),
                    "horizon_games": h, "oos_wins": r["w"], "oos_win_rate": round(r["wr"], 4),
                    "oos_wilson_lo": round(r["lo"], 4), "oos_wilson_hi": round(r["hi"], 4),
                    "is_primary_horizon": h == OOS_PRIMARY_HORIZON,
                })
            if all_available is not None:
                oos_rows.append({
                    "counter_archetype": A, "target_archetype": B, "detection_date": detection_date.date().isoformat(),
                    "horizon_games": "ALL_AVAILABLE", "oos_wins": all_available["w"],
                    "oos_win_rate": round(all_available["wr"], 4),
                    "oos_wilson_lo": round(all_available["lo"], 4), "oos_wilson_hi": round(all_available["hi"], 4),
                    "is_primary_horizon": False,
                })

            if oos_status == "OOS_CONFIRMED":
                trend, avail = lifecycle_trend(horizon_results)
                for h, r in avail:
                    lifecycle_rows.append({
                        "counter_archetype": A, "target_archetype": B,
                        "detection_date": detection_date.date().isoformat(),
                        "cumulative_horizon_games": h, "win_rate": round(r["wr"], 4),
                        "wilson_lo": round(r["lo"], 4), "wilson_hi": round(r["hi"], 4),
                        "trend_classification": trend,
                    })

        # target meta relevance NOW (current snapshot) vs AT DETECTION
        target_now_share = current_share.get(B)
        counter_now_share = current_share.get(A)
        target_now_tier = relevance_tier(target_now_share)

        final_status = status
        expired_reason = None
        if status in ("DETECTED", "OOS_PENDING", "OOS_CONFIRMED") and target_now_tier == "LOW":
            final_status = "EXPIRED_LOW_TARGET_SHARE"
            expired_reason = "target_current_14d_share_below_MEDIUM_threshold"

        registry_rows.append({
            "counter_id": f"{A} -> {B}",
            "counter_archetype": A,
            "target_archetype": B,
            "candidate_date": candidate_date.date().isoformat() if candidate_date is not None else None,
            "detection_date": detection_date.date().isoformat() if detection_date is not None else None,
            "historical_games": frozen["games"] if frozen else None,
            "historical_win_rate": round(frozen["win_rate"], 4) if frozen else None,
            "historical_wilson_lower": round(frozen["wilson_lo"], 4) if frozen else None,
            "target_meta_share_at_detection": round(frozen["target_meta_share"], 4) if frozen else None,
            "counter_meta_share_at_detection": round(frozen["counter_meta_share"], 4) if frozen else None,
            "full_dataset_games": n_full,
            "oos_status": oos_status,
            "oos_detail": oos_detail,
            "oos_primary_horizon_games": oos_games,
            "oos_primary_horizon_wins": oos_wins,
            "oos_primary_horizon_win_rate": round(oos_wr, 4) if oos_wr is not None else None,
            "oos_primary_horizon_wilson_lo": round(oos_lo, 4) if oos_lo is not None else None,
            "confirmation_date": confirmation_date,
            "failure_date": failure_date,
            "target_current_meta_share": round(target_now_share, 4) if target_now_share is not None else None,
            "target_current_relevance_tier": target_now_tier,
            "counter_current_meta_share": round(counter_now_share, 4) if counter_now_share is not None else None,
            "status": final_status,
            "expired_reason": expired_reason,
        })

    registry_df = pd.DataFrame(registry_rows).sort_values(["target_archetype", "counter_archetype"])
    registry_df.to_csv(os.path.join(OUT_DIR, "counter_registry.csv"), index=False)
    print(f"\nWrote counter_registry.csv: {len(registry_df)} rows.")
    print(registry_df["status"].value_counts().to_string())

    events_df = pd.DataFrame(events_log)
    events_df.to_csv(os.path.join(OUT_DIR, "counter_detection_events.csv"), index=False)
    print(f"Wrote counter_detection_events.csv: {len(events_df)} rows.")

    oos_df = pd.DataFrame(oos_rows)
    oos_df.to_csv(os.path.join(OUT_DIR, "counter_oos_validation.csv"), index=False)
    print(f"Wrote counter_oos_validation.csv: {len(oos_df)} rows.")

    lifecycle_df = pd.DataFrame(lifecycle_rows)
    lifecycle_df.to_csv(os.path.join(OUT_DIR, "counter_lifecycle.csv"), index=False)
    print(f"Wrote counter_lifecycle.csv: {len(lifecycle_df)} rows.")

    # ---------------- counter_matrix.csv (Sec 23): every pair in the candidate universe ----------------
    matrix_rows = []
    for r in registry_rows:
        matrix_rows.append({
            "counter_archetype": r["counter_archetype"], "target_archetype": r["target_archetype"],
            "status": r["status"],
            "historical_win_rate": r["historical_win_rate"], "historical_games": r["historical_games"],
            "historical_confidence": sample_confidence_flag(r["historical_games"]) if r["historical_games"] else None,
            "oos_win_rate": r["oos_primary_horizon_win_rate"], "oos_games": r["oos_primary_horizon_games"],
            "target_relevance_at_detection": relevance_tier(r["target_meta_share_at_detection"]),
            "target_relevance_current": r["target_current_relevance_tier"],
        })
    matrix_df = pd.DataFrame(matrix_rows).sort_values(["target_archetype", "counter_archetype"])
    matrix_df.to_csv(os.path.join(OUT_DIR, "counter_matrix.csv"), index=False)
    print(f"Wrote counter_matrix.csv: {len(matrix_df)} rows.")

    # ---------------- current_validated_counters.csv (Sec 24): actionable now ----------------
    current_valid = registry_df[registry_df["status"] == "OOS_CONFIRMED"].copy()
    current_valid = current_valid.copy()
    current_valid["confidence"] = current_valid["oos_primary_horizon_games"].apply(sample_confidence_flag)
    current_valid_out = current_valid[[
        "counter_archetype", "target_archetype", "status", "historical_win_rate",
        "oos_primary_horizon_win_rate", "confidence",
        "target_current_meta_share", "counter_current_meta_share", "confirmation_date",
    ]].rename(columns={
        "status": "current_status", "oos_primary_horizon_win_rate": "oos_win_rate",
        "target_current_meta_share": "target_current_share", "counter_current_meta_share": "counter_current_share",
        "confirmation_date": "last_confirmed",
    })
    current_valid_out.to_csv(os.path.join(OUT_DIR, "current_validated_counters.csv"), index=False)
    print(f"Wrote current_validated_counters.csv: {len(current_valid_out)} rows (OOS_CONFIRMED counters).")

    # ---------------- counter_coverage.csv (Sec 27) ----------------
    coverage_rows = []
    for a in archetypes:
        cshare = current_share.get(a)
        if cshare is None or cshare <= 0:
            continue
        n_counters = int((current_valid["target_archetype"] == a).sum())
        coverage_rows.append({
            "target_archetype": a, "current_meta_share": round(cshare, 4),
            "relevance_tier": relevance_tier(cshare),
            "validated_counter_count": n_counters,
            "covered_by_1plus": n_counters >= 1, "covered_by_2plus": n_counters >= 2,
        })
    coverage_df = pd.DataFrame(coverage_rows).sort_values("current_meta_share", ascending=False)
    coverage_df.to_csv(os.path.join(OUT_DIR, "counter_coverage.csv"), index=False)
    n_targets = len(coverage_df)
    pct_1plus = 100.0 * coverage_df["covered_by_1plus"].sum() / n_targets if n_targets else 0.0
    pct_2plus = 100.0 * coverage_df["covered_by_2plus"].sum() / n_targets if n_targets else 0.0
    print(f"Wrote counter_coverage.csv: {n_targets} current targets, "
          f"{pct_1plus:.1f}% covered by >=1 validated counter, {pct_2plus:.1f}% covered by >=2.")

    # ---------------- counter_false_positive_analysis.csv (Sec 28) ----------------
    detected_or_later = registry_df[registry_df["detection_date"].notna()]
    n_detected = len(detected_or_later)
    n_confirmed = int((registry_df["oos_status"] == "OOS_CONFIRMED").sum())
    n_failed = int((registry_df["oos_status"] == "OOS_FAILED").sum())
    n_pending = int((registry_df["oos_status"] == "OOS_PENDING").sum())
    n_expired = int((registry_df["status"] == "EXPIRED_LOW_TARGET_SHARE").sum())
    n_evaluated = n_confirmed + n_failed  # counters with a definitive OOS verdict
    false_positive_rate = (n_failed / n_evaluated) if n_evaluated else None
    confirmation_rate = (n_confirmed / n_evaluated) if n_evaluated else None
    fp_df = pd.DataFrame([{
        "total_candidates": int((registry_df["candidate_date"].notna()).sum()),
        "total_detected": n_detected,
        "oos_confirmed": n_confirmed,
        "oos_failed": n_failed,
        "oos_pending": n_pending,
        "expired_low_target_share": n_expired,
        "oos_evaluated_total": n_evaluated,
        "confirmation_rate_of_evaluated": round(confirmation_rate, 4) if confirmation_rate is not None else None,
        "false_positive_rate_of_evaluated": round(false_positive_rate, 4) if false_positive_rate is not None else None,
        "note": "pending counters excluded from confirmation/false-positive rates (Sec 28: never interpret pending as failure)",
    }])
    fp_df.to_csv(os.path.join(OUT_DIR, "counter_false_positive_analysis.csv"), index=False)
    print(f"Wrote counter_false_positive_analysis.csv.")
    print(fp_df.to_string(index=False))

    # ---------------- sensitivity analysis (Sec 5/7, clearly separate from primary) ----------------
    sens_rows = []
    for thr in MIN_MATCHUP_SAMPLE_SENSITIVITY + [MIN_MATCHUP_SAMPLE_PRIMARY]:
        # count how many full-dataset pairs clear (sample>=thr) & (win_rate>=EFFECT_SIZE_PRIMARY) & (wilson_lo>0.5), at present day
        g = decisive.groupby(["player_deck_cluster_id", "opponent_deck_cluster_id"]).agg(
            games=("result", "size"), wins=("result", lambda s: (s == "WIN").sum())).reset_index()
        g = g[g["player_deck_cluster_id"].isin(archetypes) & g["opponent_deck_cluster_id"].isin(archetypes)]
        g = g[g["games"] >= thr]
        g["wr"] = g["wins"] / g["games"]
        g["wilson_lo"] = g.apply(lambda r: wilson_ci(r["wins"], r["games"])[1], axis=1)
        n_pass = int(((g["wr"] >= EFFECT_SIZE_PRIMARY) & (g["wilson_lo"] > 0.5)).sum())
        sens_rows.append({"variant_type": "min_matchup_sample", "variant_value": thr,
                           "pairs_clearing_stat_and_effect_gate_full_dataset": n_pass,
                           "is_primary": thr == MIN_MATCHUP_SAMPLE_PRIMARY})
    for thr in EFFECT_SIZE_SENSITIVITY + [EFFECT_SIZE_PRIMARY]:
        g = decisive.groupby(["player_deck_cluster_id", "opponent_deck_cluster_id"]).agg(
            games=("result", "size"), wins=("result", lambda s: (s == "WIN").sum())).reset_index()
        g = g[g["player_deck_cluster_id"].isin(archetypes) & g["opponent_deck_cluster_id"].isin(archetypes)]
        g = g[g["games"] >= MIN_MATCHUP_SAMPLE_PRIMARY]
        g["wr"] = g["wins"] / g["games"]
        g["wilson_lo"] = g.apply(lambda r: wilson_ci(r["wins"], r["games"])[1], axis=1)
        n_pass = int(((g["wr"] >= thr) & (g["wilson_lo"] > 0.5)).sum())
        sens_rows.append({"variant_type": "effect_size_threshold", "variant_value": thr,
                           "pairs_clearing_stat_and_effect_gate_full_dataset": n_pass,
                           "is_primary": thr == EFFECT_SIZE_PRIMARY})
    for thr in OOS_FAIL_SENSITIVITY + [OOS_FAIL_WR]:
        n_would_fail = int((registry_df["oos_primary_horizon_win_rate"].notna() &
                             (registry_df["oos_primary_horizon_win_rate"] < thr)).sum())
        sens_rows.append({"variant_type": "oos_failure_threshold", "variant_value": thr,
                           "pairs_clearing_stat_and_effect_gate_full_dataset": n_would_fail,
                           "is_primary": thr == OOS_FAIL_WR})
    sens_df = pd.DataFrame(sens_rows)
    sens_df.to_csv(os.path.join(OUT_DIR, "counter_sensitivity_analysis.csv"), index=False)
    print(f"Wrote counter_sensitivity_analysis.csv: {len(sens_df)} rows.")

    print("\n" + "=" * 70)
    print("REGISTRY (all pairs that reached at least CANDIDATE):")
    show = registry_df[registry_df["candidate_date"].notna()][
        ["counter_id", "candidate_date", "detection_date", "historical_games", "historical_win_rate",
         "historical_wilson_lower", "status", "oos_primary_horizon_games", "oos_primary_horizon_win_rate"]]
    print(show.to_string(index=False))

    print("\nDONE.")
    return registry_df, events_df, oos_df, lifecycle_df, matrix_df, current_valid_out, coverage_df, fp_df, sens_df


if __name__ == "__main__":
    main()
