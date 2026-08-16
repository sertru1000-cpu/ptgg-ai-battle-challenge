"""Selection for Part 4.1 v3 (streaming/incremental, adaptive ~3,500-episode first pass).

New spec (supersedes the earlier 70/20/10, 9,000-episode plan): stratify
RECENT 55-60% / MIDDLE 25-30% / EARLY 10-15%, first-pass target ~3,500.

Targets: EARLY=500, MIDDLE=1000, RECENT=2000 (sums to exactly 3,500; 14.3/28.6/57.1%,
within the requested bands).

Reuses already-downloaded+parsed data at zero extra cost instead of re-downloading:
  - pilot main sample (reports/real_meta_pilot_v1.md, 1,000 episodes: 375 EARLY /
    250 MIDDLE / 375 RECENT) -- all reused.
  - meta_v2 episodes downloaded in the prior (superseded) 9,000-episode attempt
    (468 episodes, all EARLY as it happens, since that attempt filled EARLY
    shortfall first) -- reused up to the 125 needed to bring EARLY to 500 total.

Only the genuine shortfall needs a NEW download: 750 MIDDLE + 1,625 RECENT = 2,375
episodes -- this is what tools/extract_meta_v3.py actually fetches. Writes
data/episode_manifests/meta_v3_new_selection.csv (episodes still needing download)
and reports the full v3 composition (reused + new) to stdout.
"""
import csv
import os
import random
from collections import defaultdict
from datetime import date

random.seed(20260812)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "data", "episode_manifests", "all_episodes_manifest.csv")
PILOT_SELECTION = os.path.join(REPO_ROOT, "data", "episode_manifests", "pilot_selection.csv")
V2_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_episodes.csv")
OUT_NEW = os.path.join(REPO_ROOT, "data", "episode_manifests", "meta_v3_new_selection.csv")
OUT_REUSE = os.path.join(REPO_ROOT, "data", "episode_manifests", "meta_v3_reuse_selection.csv")

WEEK_START = date(2026, 6, 16)
N_WEEKS = 8
TARGETS = {"EARLY": 500, "MIDDLE": 1000, "RECENT": 2000}


def period_of(d: str) -> str:
    idx = min((date.fromisoformat(d) - WEEK_START).days // 7, N_WEEKS - 1)
    if idx <= 2:
        return "EARLY"
    elif idx <= 4:
        return "MIDDLE"
    else:
        return "RECENT"


def main():
    with open(PILOT_SELECTION, newline="") as f:
        pilot_rows = [r for r in csv.DictReader(f) if r["sample_type"] == "stratified"]
    pilot_by_period = defaultdict(list)
    for r in pilot_rows:
        pilot_by_period[period_of(r["date"])].append(r["episode_id"])

    v2_rows = []
    if os.path.exists(V2_EPISODES):
        with open(V2_EPISODES, encoding="utf-8", newline="") as f:
            v2_rows = list(csv.DictReader(f))
    v2_by_period = defaultdict(list)
    for r in v2_rows:
        v2_by_period[r["period"]].append(r["episode_id"])

    print("Pilot main-sample by period:", {p: len(v) for p, v in pilot_by_period.items()})
    print("meta_v2 (prior attempt) by period:", {p: len(v) for p, v in v2_by_period.items()})
    print("Targets:", TARGETS)

    reuse_ids = defaultdict(list)  # period -> [episode_id, ...] (source: pilot or v2)
    already_used = set()
    for p in TARGETS:
        pool = list(pilot_by_period[p])
        random.shuffle(pool)
        take = pool[:TARGETS[p]]
        reuse_ids[p].extend(take)
        already_used.update(take)

    for p in TARGETS:
        need_more = TARGETS[p] - len(reuse_ids[p])
        if need_more <= 0:
            continue
        pool = [eid for eid in v2_by_period[p] if eid not in already_used]
        random.shuffle(pool)
        take = pool[:need_more]
        reuse_ids[p].extend(take)
        already_used.update(take)

    shortfall = {p: TARGETS[p] - len(reuse_ids[p]) for p in TARGETS}
    print("Reused from existing downloads:", {p: len(v) for p, v in reuse_ids.items()})
    print("Shortfall requiring NEW download:", shortfall)

    # write reuse selection (source markers so extract_meta_v3.py knows which CSV to pull from)
    pilot_id_set = {r["episode_id"] for r in pilot_rows}
    reuse_rows = []
    for p, ids in reuse_ids.items():
        for eid in ids:
            src = "pilot" if eid in pilot_id_set else "meta_v2"
            reuse_rows.append({"episode_id": eid, "period": p, "source": src})
    with open(OUT_REUSE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["episode_id", "period", "source"])
        w.writeheader()
        w.writerows(reuse_rows)
    print(f"Wrote {OUT_REUSE}: {len(reuse_rows)} reused episodes")

    # ---- select NEW episodes for the shortfall, stratified evenly by day within period ----
    with open(MANIFEST, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["size_bytes"] = int(r["size_bytes"])
        r["period"] = period_of(r["date"])

    by_period_day = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["episode_id"] in already_used:
            continue
        by_period_day[r["period"]][r["date"]].append(r)

    new_selected = []
    for p, need in shortfall.items():
        if need <= 0:
            continue
        days = sorted(by_period_day[p].keys())
        n_days = len(days)
        base = need // n_days
        rem = need % n_days
        for i, d in enumerate(days):
            k = min(base + (1 if i < rem else 0), len(by_period_day[p][d]))
            picks = random.sample(by_period_day[p][d], k)
            for r in picks:
                new_selected.append({
                    "episode_id": r["episode_id"], "date": r["date"], "period": p,
                    "size_bytes": r["size_bytes"], "avg_score": r["avg_score"],
                    "min_score": r["min_score"], "sum_score": r["sum_score"],
                })

    with open(OUT_NEW, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["episode_id", "date", "period", "size_bytes",
                                           "avg_score", "min_score", "sum_score"])
        w.writeheader()
        w.writerows(new_selected)

    total_bytes = sum(r["size_bytes"] for r in new_selected)
    print(f"\nWrote {OUT_NEW}: {len(new_selected)} NEW episodes to download")
    print(f"Estimated new download volume: {total_bytes/1e9:.2f} GB")
    print(f"Total v3 dataset size: {sum(len(v) for v in reuse_ids.values()) + len(new_selected)}")
    earliest = min(r["date"] for r in rows)
    latest = max(r["date"] for r in rows)
    print(f"Manifest date range: {earliest} to {latest}")


if __name__ == "__main__":
    main()
