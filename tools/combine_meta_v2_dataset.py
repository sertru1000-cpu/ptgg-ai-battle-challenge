"""Combine the pilot main-sample (1,000 episodes, reports/real_meta_pilot_v1.md) with
the meta-v2 incremental sample (up to 8,000 episodes, tools/download_and_parse_meta_v2.py)
into one canonical dataset for Part 4.1 analysis.

- Joins fresh min_score/sum_score/avg_score from the full 278,457-row manifest for
  EVERY episode (pilot_episodes_v1.csv doesn't carry these; meta_v2_episodes.csv
  does but re-joining from the manifest for both keeps a single source of truth).
- Merges the two deck registries (label/composition are already consistent since
  both used the same tag_deck() function) into one, recomputing n_games_seen /
  dates_seen over the COMBINED episode set (not just summed, to stay correct if a
  deck happened to appear in both sub-samples).
- Runs deterministic UNLABELED clustering (src/meta_analysis/deck_clustering.py)
  once over the combined registry and attaches a 'cluster_id' column (equal to
  'label' for already-labeled decks, 'UNLABELED_CLUSTER_NN' otherwise).
- Assigns a 'period' (EARLY/MIDDLE/RECENT) to every episode from its date (pilot
  rows only have 'week', not 'period', so recomputed here for consistency).

Writes:
  strategy/meta_analysis/meta_v2_combined_episodes.csv
  strategy/meta_analysis/meta_v2_combined_deck_registry.csv   (includes cluster_id)
"""
import csv
import os
import sys
from collections import defaultdict
from datetime import date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.meta_analysis.deck_clustering import cluster_unlabeled_decks

MANIFEST = os.path.join(REPO_ROOT, "data", "episode_manifests", "all_episodes_manifest.csv")
PILOT_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_episodes_v1.csv")
PILOT_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_deck_registry_v1.csv")
V2_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_episodes.csv")
V2_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_deck_registry.csv")

OUT_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_combined_episodes.csv")
OUT_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_combined_deck_registry.csv")

WEEK_START = date(2026, 6, 16)


def period_of(d: str) -> str:
    idx = min((date.fromisoformat(d) - WEEK_START).days // 7, 7)
    if idx <= 2:
        return "EARLY"
    elif idx <= 4:
        return "MIDDLE"
    else:
        return "RECENT"


def main():
    with open(MANIFEST, newline="") as f:
        manifest = {r["episode_id"]: r for r in csv.DictReader(f)}
    print(f"Loaded manifest: {len(manifest)} rows")

    episodes = []
    with open(PILOT_EPISODES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("sample_type") != "stratified":
                continue  # exclude the 40 anomaly-tail episodes from the main weighted dataset
            episodes.append(r)
    n_pilot = len(episodes)

    if os.path.exists(V2_EPISODES):
        with open(V2_EPISODES, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                episodes.append(r)
    n_v2 = len(episodes) - n_pilot
    print(f"Pilot main-sample episodes: {n_pilot}, meta_v2 episodes so far: {n_v2}")

    out_rows = []
    missing_manifest = 0
    for e in episodes:
        m = manifest.get(e["episode_id"])
        if m is None:
            missing_manifest += 1
            continue
        out_rows.append({
            "episode_id": e["episode_id"],
            "date": e["date"],
            "period": period_of(e["date"]),
            "size_bytes": m["size_bytes"],
            "avg_score": m["avg_score"],
            "min_score": m["min_score"],
            "sum_score": m["sum_score"],
            "team0": e.get("team0"),
            "team1": e.get("team1"),
            "winner": e.get("winner"),
            "outcome_type": e.get("outcome_type"),
            "first_player": e.get("first_player"),
            "n_steps": e.get("n_steps"),
            "final_turn_p0": e.get("final_turn_p0"),
            "final_turn_p1": e.get("final_turn_p1"),
            "deck0_hash": e.get("deck0_hash"),
            "deck1_hash": e.get("deck1_hash"),
            "deck0_ncards": e.get("deck0_ncards"),
            "deck1_ncards": e.get("deck1_ncards"),
        })
    if missing_manifest:
        print(f"WARNING: {missing_manifest} episodes had no manifest match (skipped)")

    fieldnames = list(out_rows[0].keys())
    with open(OUT_EPISODES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {OUT_EPISODES}: {len(out_rows)} rows")

    # ---- merge deck registries, recompute n_games_seen/dates_seen over combined set ----
    registry = {}
    for path in (PILOT_DECKS, V2_DECKS):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                h = r["deck_hash"]
                if h not in registry:
                    registry[h] = dict(r)
                    registry[h]["n_games_seen"] = 0
                    registry[h]["dates_seen"] = set()

    game_count = defaultdict(int)
    dates_seen = defaultdict(set)
    for e in out_rows:
        for hkey in ("deck0_hash", "deck1_hash"):
            h = e[hkey]
            if h:
                game_count[h] += 1
                dates_seen[h].add(e["date"])
    for h, d in registry.items():
        d["n_games_seen"] = game_count.get(h, 0)
        d["dates_seen"] = dates_seen.get(h, set())

    n_unlabeled_before = sum(1 for d in registry.values() if d["label"] == "UNLABELED")
    hash_to_cluster, cluster_info = cluster_unlabeled_decks(registry)
    for h, d in registry.items():
        d["cluster_id"] = hash_to_cluster.get(h, d["label"])
    print(f"UNLABELED decks: {n_unlabeled_before}, resolved into {len(cluster_info)} clusters")

    deck_rows = []
    for d in registry.values():
        d = dict(d)
        d["dates_seen"] = ";".join(sorted(d["dates_seen"]))
        deck_rows.append(d)
    deck_rows.sort(key=lambda d: -int(d["n_games_seen"]))
    fieldnames = ["deck_hash", "label", "cluster_id", "matched_signature_count", "evidence",
                  "n_unique_card_ids", "n_total_cards", "composition", "n_games_seen", "dates_seen"]
    with open(OUT_DECKS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(deck_rows)
    print(f"Wrote {OUT_DECKS}: {len(deck_rows)} decks")

    by_period = defaultdict(int)
    for e in out_rows:
        by_period[e["period"]] += 1
    print("Episodes by period:", dict(by_period))


if __name__ == "__main__":
    main()
