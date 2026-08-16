"""Select the incremental ~8,000-episode sample needed to bring the combined
real-meta dataset (existing 1,000-episode pilot main sample + this selection) to
~9,000 episodes weighted 70% RECENT / 20% MIDDLE / 10% EARLY.

Does NOT re-select the 1,000 pilot main-sample episodes (already downloaded and
parsed, see reports/real_meta_pilot_v1.md) -- only the shortfall needed per period
after crediting that existing sample. Excludes the pilot's 40 anomaly episodes from
period targets (they were a deliberately biased short/long-tail sub-sample, not
representative -- see episode_sampling_plan.md).

Stratifies evenly by calendar day within each period (equal count per day, random
draw within day), seeded RNG for reproducibility. Does not download anything --
only writes data/episode_manifests/meta_v2_selection.csv for the batch
download+parse pipeline (tools/download_and_parse_meta_v2.py) to consume.
"""
import csv
import os
import random
from collections import defaultdict
from datetime import date, timedelta

random.seed(20260811)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "data", "episode_manifests", "all_episodes_manifest.csv")
PILOT_SELECTION = os.path.join(REPO_ROOT, "data", "episode_manifests", "pilot_selection.csv")
OUT = os.path.join(REPO_ROOT, "data", "episode_manifests", "meta_v2_selection.csv")

WEEK_START = date(2026, 6, 16)
N_WEEKS = 8
TARGET_TOTAL = 9000
TARGET_SHARE = {"EARLY": 0.10, "MIDDLE": 0.20, "RECENT": 0.70}


def period(d: str) -> str:
    dd = date.fromisoformat(d)
    idx = min((dd - WEEK_START).days // 7, N_WEEKS - 1)
    if idx <= 2:
        return "EARLY"
    elif idx <= 4:
        return "MIDDLE"
    else:
        return "RECENT"


def main():
    with open(MANIFEST, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["size_bytes"] = int(r["size_bytes"])
        r["period"] = period(r["date"])

    with open(PILOT_SELECTION, newline="") as f:
        pilot_rows = list(csv.DictReader(f))
    pilot_main_ids = {r["episode_id"] for r in pilot_rows if r["sample_type"] == "stratified"}
    already_used_ids = {r["episode_id"] for r in pilot_rows}  # exclude anomaly too, never re-download

    existing_by_period = defaultdict(int)
    for r in pilot_rows:
        if r["sample_type"] == "stratified":
            existing_by_period[period(r["date"])] += 1

    targets = {p: round(TARGET_TOTAL * TARGET_SHARE[p]) for p in TARGET_SHARE}
    shortfall = {p: max(0, targets[p] - existing_by_period[p]) for p in targets}

    print("Existing pilot main-sample by period:", dict(existing_by_period))
    print("Combined targets:", targets)
    print("New-download shortfall by period:", shortfall)

    by_period_day = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["episode_id"] in already_used_ids:
            continue
        by_period_day[r["period"]][r["date"]].append(r)

    selected = []
    for p, need in shortfall.items():
        if need <= 0:
            continue
        days = sorted(by_period_day[p].keys())
        n_days = len(days)
        # even split across days in this period, remainder distributed to the first few days
        base = need // n_days
        rem = need % n_days
        picked_ids = set()
        for i, d in enumerate(days):
            k = base + (1 if i < rem else 0)
            pool = by_period_day[p][d]
            k = min(k, len(pool))
            picks = random.sample(pool, k)
            for r in picks:
                selected.append({
                    "episode_id": r["episode_id"], "date": r["date"],
                    "size_bytes": r["size_bytes"], "avg_score": r["avg_score"],
                    "min_score": r["min_score"], "sum_score": r["sum_score"],
                    "period": p, "sample_type": "meta_v2",
                })
                picked_ids.add(r["episode_id"])
        actual = len(picked_ids)
        if actual < need:
            print(f"  WARNING: {p} short by {need - actual} (day pools exhausted)")

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["episode_id", "date", "size_bytes", "avg_score",
                                           "min_score", "sum_score", "period", "sample_type"])
        w.writeheader()
        w.writerows(selected)

    total_bytes = sum(s["size_bytes"] for s in selected)
    by_p = defaultdict(int)
    for s in selected:
        by_p[s["period"]] += 1
    print(f"\nSelected {len(selected)} NEW episodes -> {OUT}")
    print("By period:", dict(by_p))
    print(f"Estimated new download volume: {total_bytes/1e9:.2f} GB")
    combined_total = len(selected) + len(pilot_main_ids)
    print(f"Combined dataset size (new + existing pilot main): {combined_total}")


if __name__ == "__main__":
    main()
