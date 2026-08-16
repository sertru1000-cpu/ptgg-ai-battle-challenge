"""Phase 4.5b -- Post-Confirmation Re-Validation & Extended OOS.

Pre-registered continuation of Phase 4.4 (build_validated_counter_model_v1.py)
and Phase 4.5 (build_counter_aware_deck_selection_v1.py). Does NOT change any
threshold, definition, or piece of methodology from either phase -- both
scripts were re-run unchanged first (see reports/counter_revalidation_v1.md
Sec 3/4) and confirmed byte-identical to their original outputs, proving the
pipeline is deterministic given its input.

Central finding this script encodes rather than computes: NO new episode data
exists beyond the Phase 4.4/4.5 endpoint (2026-08-10). Verified two
independent ways immediately before this script was written (both outside
Python, logged here for the record):
  1. Re-downloaded kaggle/pokemon-tcg-ai-battle-episodes-index's manifest.csv
     (dataset last-updated timestamp had advanced to 2026-08-11T00:07Z, but
     its content is row-for-row identical to the original 56-day index --
     still ends 2026-08-10, still 4,603 episodes that day).
  2. Directly probed kaggle/pokemon-tcg-ai-battle-episodes-2026-08-11 via
     KaggleApi.dataset_list_files -- 403 Forbidden (dataset does not exist /
     is not yet published), consistent with the daily-dump-lags-by-a-day
     pattern already documented for this source.

Consequently "extended" in this phase's outputs means: the exact same
3,499-episode / 6,982-decisive-deck-slot dataset Phase 4.4/4.5 used, with
every genuinely new figure equal to zero and every reported number equal to
the original by construction (not by a null result -- by data unavailability).
This script's only real job is to (a) mechanically prove that equivalence,
(b) restate the original numbers under the Sec 31 required "_extended"
filenames so they can be diffed side-by-side against the originals per Sec 32,
and (c) compute the specific derived quantities (extended cumulative-horizon
tables, the ALL_AVAILABLE-vs-required-horizon gap) the report needs.

Writes:
  results/meta/counter_lifecycle_extended.csv
  results/meta/counter_oos_extended.csv
  results/meta/counter_aware_walk_forward_extended.csv
  results/meta/counter_aware_decisions_extended.csv
  results/meta/counter_aware_comparison_extended.csv
  results/meta/counter_trigger_analysis_extended.csv
  results/meta/counter_aware_leakage_audit_extended.csv
"""
from __future__ import annotations

import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd

OUT_DIR = os.path.join(REPO_ROOT, "results", "meta")

PREVIOUS_ENDPOINT = "2026-08-10"
NEW_ENDPOINT = "2026-08-10"  # identical -- confirmed no new source data exists (see docstring)
PREVIOUS_EPISODE_COUNT = 3499
NEW_EPISODE_COUNT = 0
TOTAL_EPISODE_COUNT = PREVIOUS_EPISODE_COUNT + NEW_EPISODE_COUNT

MEWTWO_HORIZONS = [25, 50, 75, 100, 150, 200]
OGERPON_HORIZONS = [25, 50, 75, 100, 150]


def wilson_ci(wins, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def load_data():
    df = pd.read_parquet(os.path.join(OUT_DIR, "episodes_summary.parquet"))
    decisive = df[df["outcome_type"] == "DECISIVE"].copy()
    decisive["date_dt"] = pd.to_datetime(decisive["date"]).dt.normalize()
    return decisive


def oos_games_for(decisive, A, B, detection_date):
    fut = decisive[(decisive["date_dt"] >= pd.Timestamp(detection_date)) &
                    (decisive["player_deck_cluster_id"] == A) &
                    (decisive["opponent_deck_cluster_id"] == B)].sort_values("timestamp")
    return fut


def horizon_table(fut, horizons, counter, target, detection_date):
    rows = []
    total_n = len(fut)
    for h in horizons:
        if total_n >= h:
            sub = fut.iloc[:h]
            w = int((sub["result"] == "WIN").sum())
            wr, lo, hi = wilson_ci(w, h)
            rows.append({
                "counter_archetype": counter, "target_archetype": target,
                "detection_date": detection_date, "horizon_games": h,
                "availability": "AVAILABLE", "wins": w, "win_rate": round(wr, 4),
                "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
                "new_episodes_contributed_to_this_horizon": 0,
                "data_source": "ORIGINAL_DATASET_2026-06-16_to_2026-08-10",
            })
        else:
            rows.append({
                "counter_archetype": counter, "target_archetype": target,
                "detection_date": detection_date, "horizon_games": h,
                "availability": "INSUFFICIENT_DATA_SOURCE_EXHAUSTED",
                "wins": None, "win_rate": None, "wilson_lo": None, "wilson_hi": None,
                "new_episodes_contributed_to_this_horizon": 0,
                "data_source": f"only {total_n} post-detection games exist in the entire "
                                f"available dataset (through {NEW_ENDPOINT})",
            })
    # ALL_AVAILABLE row -- the original Phase 4.4 checkpoint horizon for pending counters
    if total_n > 0:
        w = int((fut["result"] == "WIN").sum())
        wr, lo, hi = wilson_ci(w, total_n)
        rows.append({
            "counter_archetype": counter, "target_archetype": target,
            "detection_date": detection_date, "horizon_games": "ALL_AVAILABLE",
            "availability": "AVAILABLE", "wins": w, "win_rate": round(wr, 4),
            "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
            "new_episodes_contributed_to_this_horizon": 0,
            "data_source": "ORIGINAL_DATASET_2026-06-16_to_2026-08-10",
        })
        rows[-1]["all_available_n"] = total_n
    return rows


def main():
    decisive = load_data()
    actual_max_date = decisive["date_dt"].max().date().isoformat()
    print(f"Actual latest episode date in dataset: {actual_max_date}")
    assert actual_max_date == NEW_ENDPOINT, "data endpoint assumption violated -- STOP, re-check"

    registry = pd.read_csv(os.path.join(OUT_DIR, "counter_registry.csv"))

    tracked = [
        ("Team Rocket's Mewtwo ex", "Fezandipiti ex", "2026-07-22", MEWTWO_HORIZONS, "OOS_CONFIRMED"),
        ("Teal Mask Ogerpon ex", "Marnie's Grimmsnarl ex", "2026-08-09", OGERPON_HORIZONS, "OOS_PENDING"),
        ("Mega Kangaskhan ex", "Marnie's Grimmsnarl ex", "2026-07-18", OGERPON_HORIZONS + [200], "OOS_FAILED"),
        ("Marnie's Grimmsnarl ex", "Team Rocket's Mewtwo ex", "2026-07-25", OGERPON_HORIZONS, "OOS_FAILED"),
    ]

    all_horizon_rows = []
    lifecycle_rows = []
    for A, B, det_date, horizons, orig_status in tracked:
        fut = oos_games_for(decisive, A, B, det_date)
        rows = horizon_table(fut, horizons, A, B, det_date)
        all_horizon_rows.extend(rows)
        for r in rows:
            lifecycle_rows.append({
                **{k: v for k, v in r.items() if k != "all_available_n"},
                "original_phase44_status": orig_status,
                "extended_status_this_horizon": (
                    "N/A_ORIGINAL_STATUS_UNCHANGED_NO_NEW_DATA"
                ),
                "detection_epoch": "ORIGINAL_DETECTION (frozen, not moved)",
            })
        avail = [r for r in rows if r["availability"] == "AVAILABLE" and r["horizon_games"] != "ALL_AVAILABLE"]
        all_avail_row = next((r for r in rows if r["horizon_games"] == "ALL_AVAILABLE"), None)
        n_all = all_avail_row.get("all_available_n") if all_avail_row else 0
        print(f"{A} -> {B}: detection={det_date}, horizons available={[r['horizon_games'] for r in avail]}, "
              f"ALL_AVAILABLE n={n_all}")

    oos_ext_df = pd.DataFrame([{k: v for k, v in r.items() if k != "all_available_n"} for r in all_horizon_rows])
    oos_ext_df.to_csv(os.path.join(OUT_DIR, "counter_oos_extended.csv"), index=False)
    print(f"\nWrote counter_oos_extended.csv: {len(oos_ext_df)} rows.")

    lifecycle_ext_df = pd.DataFrame(lifecycle_rows)
    lifecycle_ext_df.to_csv(os.path.join(OUT_DIR, "counter_lifecycle_extended.csv"), index=False)
    print(f"Wrote counter_lifecycle_extended.csv: {len(lifecycle_ext_df)} rows.")

    # ---------------- straight re-labels of the (byte-identical) Phase 4.5 outputs ----------------
    def copy_with_note(src_name, dst_name, extra_cols=None):
        df = pd.read_csv(os.path.join(OUT_DIR, src_name))
        df["new_episodes_included"] = 0
        df["data_endpoint"] = NEW_ENDPOINT
        if extra_cols:
            for k, v in extra_cols.items():
                df[k] = v
        df.to_csv(os.path.join(OUT_DIR, dst_name), index=False)
        print(f"Wrote {dst_name}: {len(df)} rows (identical content to {src_name}, 0 new episodes).")
        return df

    copy_with_note("counter_aware_walk_forward.csv", "counter_aware_walk_forward_extended.csv")
    copy_with_note("counter_aware_decisions.csv", "counter_aware_decisions_extended.csv")
    copy_with_note("counter_trigger_analysis.csv", "counter_trigger_analysis_extended.csv")
    copy_with_note("counter_aware_leakage_audit.csv", "counter_aware_leakage_audit_extended.csv")

    with open(os.path.join(OUT_DIR, "counter_aware_comparison.csv"), encoding="utf-8") as f:
        raw_lines = f.readlines()
    split_idx = next(i for i, ln in enumerate(raw_lines) if ln.startswith("# paired_statistical_comparisons"))
    headline_block = "".join(raw_lines[:split_idx])
    paired_block = "".join(raw_lines[split_idx + 1:])
    import io
    comp_df = pd.read_csv(io.StringIO(headline_block))
    comp_df["extended_oos_win_rate"] = comp_df["oos_win_rate"]
    comp_df["delta_extended_vs_original"] = 0.0
    comp_df["new_episodes_included"] = 0
    comp_df.to_csv(os.path.join(OUT_DIR, "counter_aware_comparison_extended.csv"), index=False)
    with open(os.path.join(OUT_DIR, "counter_aware_comparison_extended.csv"), "a", encoding="utf-8") as f:
        f.write("\n# paired_statistical_comparisons (identical to original, 0 new episodes)\n")
        f.write(paired_block)
    print(f"Wrote counter_aware_comparison_extended.csv: {len(comp_df)} headline rows + paired-comparison block.")

    print("\nDONE.")


if __name__ == "__main__":
    main()
