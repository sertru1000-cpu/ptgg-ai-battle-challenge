"""Parse all downloaded pilot episodes into structured CSVs for analysis.

Reads data/episode_pilot/<date>/<episode_id>.json (whatever has been downloaded so far --
safe to run before the full pilot download finishes, for incremental checks).

Writes:
  strategy/meta_analysis/pilot_episodes_v1.csv       one row per episode
  strategy/meta_analysis/pilot_deck_registry_v1.csv  one row per unique deck_hash seen
"""
import csv
import os
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.meta_analysis.episode_parser import parse_episode_file
from src.meta_analysis.archetype_signatures import tag_deck

SELECTION = os.path.join(REPO_ROOT, "data", "episode_manifests", "pilot_selection.csv")
PILOT_DIR = os.path.join(REPO_ROOT, "data", "episode_pilot")
OUT_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_episodes_v1.csv")
OUT_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_deck_registry_v1.csv")


def main():
    with open(SELECTION, newline="") as f:
        selection = {r["episode_id"]: r for r in csv.DictReader(f)}

    deck_registry = {}  # hash -> dict(label, evidence, deck_counter, n_seen, dates, episode_ids)
    episode_rows = []
    parse_errors = []

    n_total = len(selection)
    n_found = 0
    for episode_id, sel in selection.items():
        path = os.path.join(PILOT_DIR, sel["date"], f"{episode_id}.json")
        if not os.path.exists(path):
            continue
        n_found += 1
        try:
            rec = parse_episode_file(path, sel["date"])
        except Exception as e:
            parse_errors.append((episode_id, str(e)))
            continue

        for hsh, deck in ((rec.deck0_hash, rec.deck0), (rec.deck1_hash, rec.deck1)):
            if hsh not in deck_registry and len(deck) > 0:
                label, matched_n, evidence = tag_deck(deck)
                deck_registry[hsh] = {
                    "deck_hash": hsh, "label": label, "matched_signature_count": matched_n,
                    "evidence": ",".join(sorted(set(evidence))),
                    "n_unique_card_ids": len(deck), "n_total_cards": sum(deck.values()),
                    "composition": ";".join(f"{cid}:{c}" for cid, c in sorted(deck.items())),
                    "n_games_seen": 0, "dates_seen": set(),
                }
            if hsh in deck_registry:
                deck_registry[hsh]["n_games_seen"] += 1
                deck_registry[hsh]["dates_seen"].add(rec.date)

        episode_rows.append({
            "episode_id": rec.episode_id, "date": rec.date,
            "week": sel["week"], "quintile": sel["quintile"], "sample_type": sel["sample_type"],
            "size_bytes": sel["size_bytes"],
            "team0": rec.team_names[0] if rec.team_names else None,
            "team1": rec.team_names[1] if len(rec.team_names or []) > 1 else None,
            "winner": rec.winner, "outcome_type": rec.outcome_type,
            "first_player": rec.first_player, "n_steps": rec.n_steps,
            "final_turn_p0": rec.final_turn_p0, "final_turn_p1": rec.final_turn_p1,
            "deck0_hash": rec.deck0_hash, "deck1_hash": rec.deck1_hash,
            "deck0_ncards": sum(rec.deck0.values()), "deck1_ncards": sum(rec.deck1.values()),
            "deck0_source": rec.deck0_source, "deck1_source": rec.deck1_source,
        })

    os.makedirs(os.path.dirname(OUT_EPISODES), exist_ok=True)
    with open(OUT_EPISODES, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(episode_rows[0].keys()))
        w.writeheader()
        w.writerows(episode_rows)

    deck_rows = []
    for d in deck_registry.values():
        d = dict(d)
        d["dates_seen"] = ";".join(sorted(d["dates_seen"]))
        deck_rows.append(d)
    deck_rows.sort(key=lambda d: -d["n_games_seen"])
    with open(OUT_DECKS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(deck_rows[0].keys()))
        w.writeheader()
        w.writerows(deck_rows)

    print(f"Episodes found on disk: {n_found}/{n_total}")
    print(f"Parsed OK: {len(episode_rows)}, errors: {len(parse_errors)}")
    if parse_errors:
        print("First few errors:", parse_errors[:5])
    print(f"Unique decks seen: {len(deck_registry)}")
    print(f"Wrote {OUT_EPISODES}")
    print(f"Wrote {OUT_DECKS}")


if __name__ == "__main__":
    main()
