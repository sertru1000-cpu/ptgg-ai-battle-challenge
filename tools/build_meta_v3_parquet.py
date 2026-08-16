"""Build the required results/meta/episodes_summary.parquet from the compact
meta_v3_episodes.csv + meta_v3_deck_registry.csv (never touches raw episode JSON --
that was already discarded by tools/extract_meta_v3.py).

Long format: one row PER SIDE per episode (2 rows/episode), matching the schema
requested in the phase-4.1-v3 prompt section 5 (player_id/opponent_id,
player_rating/opponent_rating, player_deck_hash/opponent_deck_hash,
player_deck_list/opponent_deck_list, result, game_length, turn_count). Fields not
present in the source are left null and reported as missing in the data-quality
report, not invented.

Also runs (over the whole combined dataset, once):
  - UNLABELED deck clustering (src/meta_analysis/deck_clustering.py)
  - INFERRED rating resolution (src/meta_analysis/rating_resolution.py) -- see that
    module's docstring and reports/meta_data_quality.md for the important caveat
    that this resolution showed NO validated signal above chance on this data.

Writes:
  results/meta/episodes_summary.parquet
  strategy/meta_analysis/meta_v3_combined_deck_registry.csv  (adds cluster_id)
"""
import csv
import os
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd

from src.meta_analysis.deck_clustering import cluster_unlabeled_decks
from src.meta_analysis.rating_resolution import resolve_ratings

EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v3_episodes.csv")
DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v3_deck_registry.csv")
OUT_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v3_combined_deck_registry.csv")
OUT_PARQUET = os.path.join(REPO_ROOT, "results", "meta", "episodes_summary.parquet")


def result_for_side(winner, outcome_type, side):
    if outcome_type == "DRAW":
        return "DRAW"
    if outcome_type == "ERROR_OR_TIMEOUT":
        return "ERROR_OR_TIMEOUT"
    if winner in ("", None):
        return None
    return "WIN" if int(winner) == side else "LOSS"


def main():
    with open(EPISODES, encoding="utf-8", newline="") as f:
        episodes = list(csv.DictReader(f))
    with open(DECKS, encoding="utf-8", newline="") as f:
        decks = {r["deck_hash"]: r for r in csv.DictReader(f)}

    # duplicate episode_id check (structural integrity, reported not silently fixed)
    ids_seen = defaultdict(int)
    for e in episodes:
        ids_seen[e["episode_id"]] += 1
    dup_ids = {k: v for k, v in ids_seen.items() if v > 1}

    n_unlabeled = sum(1 for d in decks.values() if d["label"] == "UNLABELED")
    hash_to_cluster, cluster_info = cluster_unlabeled_decks(decks)
    for h, d in decks.items():
        d["cluster_id"] = hash_to_cluster.get(h, d["label"])
    deck_rows = []
    for d in decks.values():
        d2 = dict(d)
        deck_rows.append(d2)
    with open(OUT_DECKS, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["deck_hash", "label", "cluster_id", "matched_signature_count", "evidence",
                      "n_unique_card_ids", "n_total_cards", "composition", "n_games_seen", "dates_seen"]
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(deck_rows)
    print(f"UNLABELED decks: {n_unlabeled} -> {len(cluster_info)} clusters "
          f"(written to {OUT_DECKS})")

    decisive_with_scores = [e for e in episodes
                             if e["outcome_type"] == "DECISIVE" and e.get("min_score") not in (None, "")]
    resolved, deck_rating_est = resolve_ratings(decisive_with_scores)
    ep_rating = {}
    for i, e in enumerate(decisive_with_scores):
        if i in resolved:
            r0, r1, conf = resolved[i]
            ep_rating[e["episode_id"]] = (r0, r1, conf)
    print(f"Rating resolution: {len(resolved)}/{len(decisive_with_scores)} decisive-with-score "
          f"episodes resolved (INFERRED, see rating_resolution.py docstring for the validated "
          f"near-null-signal caveat)")

    long_rows = []
    for e in episodes:
        rr = ep_rating.get(e["episode_id"])
        for side, dk, ok, tk, fk in ((0, "deck0_hash", "deck1_hash", "team0", "team1"),
                                      (1, "deck1_hash", "deck0_hash", "team1", "team0")):
            player_deck_hash = e[dk]
            opp_deck_hash = e[ok]
            player_deck_meta = decks.get(player_deck_hash, {})
            opp_deck_meta = decks.get(opp_deck_hash, {})
            if rr:
                r0, r1, conf = rr
                player_rating, opp_rating = (r0, r1) if side == 0 else (r1, r0)
            else:
                player_rating, opp_rating, conf = None, None, None
            turn_count = e["final_turn_p0"] if side == 0 else e["final_turn_p1"]
            long_rows.append({
                "episode_id": e["episode_id"],
                "timestamp": e["timestamp"],
                "date": e["date"],
                "period": e["period"],
                "side": side,
                "player_id": e.get(tk),
                "opponent_id": e.get(fk),
                "player_rating": player_rating,
                "opponent_rating": opp_rating,
                "rating_inferred": rr is not None,
                "rating_resolution_confident": conf,
                "player_deck_hash": player_deck_hash,
                "opponent_deck_hash": opp_deck_hash,
                "player_deck_list": player_deck_meta.get("composition"),
                "opponent_deck_list": opp_deck_meta.get("composition"),
                "player_deck_label": player_deck_meta.get("label"),
                "player_deck_cluster_id": player_deck_meta.get("cluster_id"),
                "opponent_deck_label": opp_deck_meta.get("label"),
                "opponent_deck_cluster_id": opp_deck_meta.get("cluster_id"),
                "result": result_for_side(e["winner"], e["outcome_type"], side),
                "outcome_type": e["outcome_type"],
                "game_length": e.get("n_steps"),
                "turn_count": turn_count,
                "first_player": (e.get("first_player") not in ("", None)) and int(e["first_player"]) == side,
                "source": e.get("source"),
            })

    df = pd.DataFrame(long_rows)
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"Wrote {OUT_PARQUET}: {len(df)} rows ({len(episodes)} episodes x 2 sides)")
    print(f"Duplicate episode_ids in source: {len(dup_ids)} "
          f"{'(' + str(list(dup_ids.items())[:5]) + ')' if dup_ids else ''}")

    # quick missingness summary printed here; full report built by analyze_meta_v3.py
    for col in ["player_rating", "player_deck_hash", "result", "game_length", "timestamp"]:
        n_missing = df[col].isna().sum()
        print(f"  missing {col}: {n_missing}/{len(df)} ({n_missing/len(df)*100:.2f}%)")


if __name__ == "__main__":
    main()
