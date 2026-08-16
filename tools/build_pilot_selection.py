"""Select a ~1000-episode pilot sample from the full 278,457-row episode manifest,
stratified by (week x size-quintile), plus a small separate targeted anomaly sample
of extreme-short and extreme-long episodes for the game-length investigation.

Does not download any episode content -- only selects episode_ids and writes the
selection to data/episode_manifests/pilot_selection.csv for tools/download_pilot.py
to consume.
"""
import csv
import os
import random
from collections import defaultdict
from datetime import date, timedelta

random.seed(20260811)  # fixed for reproducibility of *which* episodes were sampled

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "data", "episode_manifests", "all_episodes_manifest.csv")
OUT = os.path.join(REPO_ROOT, "data", "episode_manifests", "pilot_selection.csv")

WEEK_START = date(2026, 6, 16)
N_WEEKS = 8
QUINTILES = 5
PER_CELL = 25            # 8 weeks x 5 quintiles x 25 = 1000
ANOMALY_SHORT_N = 20     # extra, separate sub-sample
ANOMALY_LONG_N = 20
SHORT_THRESHOLD = 200_000
LONG_THRESHOLD = 20_000_000


def week_index(d: str) -> int:
    dd = date.fromisoformat(d)
    idx = (dd - WEEK_START).days // 7
    return min(idx, N_WEEKS - 1)


def main():
    with open(MANIFEST, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["size_bytes"] = int(r["size_bytes"])
        r["week"] = week_index(r["date"])

    by_week = defaultdict(list)
    for r in rows:
        by_week[r["week"]].append(r)

    selected = []
    used_ids = set()

    # --- main stratified sample: week x size-quintile ---
    for w in range(N_WEEKS):
        wk_rows = sorted(by_week[w], key=lambda r: r["size_bytes"])
        n = len(wk_rows)
        for q in range(QUINTILES):
            lo = n * q // QUINTILES
            hi = n * (q + 1) // QUINTILES
            bucket = wk_rows[lo:hi]
            k = min(PER_CELL, len(bucket))
            picks = random.sample(bucket, k)
            for r in picks:
                selected.append({
                    "episode_id": r["episode_id"], "date": r["date"],
                    "size_bytes": r["size_bytes"], "avg_score": r["avg_score"],
                    "week": w, "quintile": q, "sample_type": "stratified",
                })
                used_ids.add(r["episode_id"])

    # --- targeted anomaly sub-sample (excluded from main meta stats) ---
    short_pool = [r for r in rows if r["size_bytes"] < SHORT_THRESHOLD and r["episode_id"] not in used_ids]
    long_pool = [r for r in rows if r["size_bytes"] > LONG_THRESHOLD and r["episode_id"] not in used_ids]
    for r in random.sample(short_pool, min(ANOMALY_SHORT_N, len(short_pool))):
        selected.append({
            "episode_id": r["episode_id"], "date": r["date"],
            "size_bytes": r["size_bytes"], "avg_score": r["avg_score"],
            "week": r["week"], "quintile": -1, "sample_type": "anomaly_short",
        })
    for r in random.sample(long_pool, min(ANOMALY_LONG_N, len(long_pool))):
        selected.append({
            "episode_id": r["episode_id"], "date": r["date"],
            "size_bytes": r["size_bytes"], "avg_score": r["avg_score"],
            "week": r["week"], "quintile": -1, "sample_type": "anomaly_long",
        })

    with open(OUT, "w", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=["episode_id", "date", "size_bytes", "avg_score", "week", "quintile", "sample_type"])
        w_.writeheader()
        w_.writerows(selected)

    print(f"Selected {len(selected)} episodes -> {OUT}")
    by_type = defaultdict(int)
    for s in selected:
        by_type[s["sample_type"]] += 1
    print(dict(by_type))
    total_bytes = sum(s["size_bytes"] for s in selected)
    print(f"Estimated download volume: {total_bytes/1e9:.2f} GB")


if __name__ == "__main__":
    main()
