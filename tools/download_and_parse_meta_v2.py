"""Disk-safe batched download + parse + cleanup for the meta-v2 scale-up
(data/episode_manifests/meta_v2_selection.csv, ~8,000 episodes).

Disk is tight (~41GB free, full weighted sample would need ~37GB if kept raw).
This script processes in batches: download a batch, parse each file immediately
(deck extraction/hash/archetype tag + join manifest rating fields), append to the
incremental output CSVs, THEN DELETE the batch's raw JSON files before starting the
next batch. Peak extra disk usage stays at ~1 batch (~2-3GB), not 37GB.

Downloads SEQUENTIALLY (not threaded) -- an earlier ThreadPoolExecutor version (4-6
workers) was empirically SLOWER and more error-prone (429s) than tools/download_pilot.py's
plain sequential loop, most likely due to contention in the shared KaggleApi client's
underlying connection handling. Matches download_pilot.py's proven ~30 episodes/min.

Resumable: on restart, skips episode_ids already present in the output episodes CSV.

Writes (append-safe, never overwritten across runs):
  strategy/meta_analysis/meta_v2_episodes.csv        one row per episode
  strategy/meta_analysis/meta_v2_deck_registry.csv   one row per unique deck_hash (rewritten each batch, derived from full running state)
"""
import csv
import os
import socket
import sys
import time

socket.setdefaulttimeout(30)  # avoid an indefinitely-hung network call stalling the process
from collections import defaultdict

os.environ.setdefault("KAGGLE_CONFIG_DIR", os.path.expanduser("~/.kaggle"))
from kaggle.api.kaggle_api_extended import KaggleApi

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.meta_analysis.episode_parser import parse_episode_file
from src.meta_analysis.archetype_signatures import tag_deck

SELECTION = os.path.join(REPO_ROOT, "data", "episode_manifests", "meta_v2_selection.csv")
RAW_DIR = os.path.join(REPO_ROOT, "data", "episode_pilot")  # same tree as pilot, dedup-friendly
OUT_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_episodes.csv")
OUT_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_deck_registry.csv")

BATCH_SIZE = 500
SLEEP_PER_CALL = 0.4  # matches tools/download_pilot.py's proven ~30 episodes/min sequential rate

EPISODE_FIELDS = [
    "episode_id", "date", "period", "size_bytes", "avg_score", "min_score", "sum_score",
    "team0", "team1", "winner", "outcome_type", "first_player", "n_steps",
    "final_turn_p0", "final_turn_p1",
    "deck0_hash", "deck1_hash", "deck0_ncards", "deck1_ncards",
    "deck0_source", "deck1_source",
]

_shared_api = None


def get_api():
    global _shared_api
    if _shared_api is None:
        _shared_api = KaggleApi()
        _shared_api.authenticate()
    return _shared_api


def download_one(sel):
    api = get_api()
    date_, episode_id = sel["date"], sel["episode_id"]
    slug = f"kaggle/pokemon-tcg-ai-battle-episodes-{date_}"
    outdir = os.path.join(RAW_DIR, date_)
    os.makedirs(outdir, exist_ok=True)
    fname = f"{episode_id}.json"
    local_path = os.path.join(outdir, fname)
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return sel, local_path, None
    last_err = None
    for attempt in range(6):
        try:
            api.dataset_download_file(slug, fname, path=outdir, force=True, quiet=True)
            time.sleep(SLEEP_PER_CALL)
            return sel, local_path, None
        except Exception as e:
            last_err = e
            is_429 = "429" in str(e)
            wait = (15 * (attempt + 1)) if is_429 else (4 * (attempt + 1))
            time.sleep(wait)
    return sel, local_path, last_err


def load_done_ids():
    if not os.path.exists(OUT_EPISODES):
        return set()
    with open(OUT_EPISODES, encoding="utf-8", newline="") as f:
        return {r["episode_id"] for r in csv.DictReader(f)}


def append_episode_rows(rows):
    write_header = not os.path.exists(OUT_EPISODES)
    with open(OUT_EPISODES, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EPISODE_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def load_deck_registry():
    reg = {}
    if os.path.exists(OUT_DECKS):
        with open(OUT_DECKS, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                r["n_games_seen"] = int(r["n_games_seen"])
                r["dates_seen"] = set(r["dates_seen"].split(";")) if r["dates_seen"] else set()
                reg[r["deck_hash"]] = r
    return reg


def save_deck_registry(reg):
    rows = []
    for d in reg.values():
        d = dict(d)
        d["dates_seen"] = ";".join(sorted(d["dates_seen"]))
        rows.append(d)
    rows.sort(key=lambda d: -d["n_games_seen"])
    if not rows:
        return
    fieldnames = ["deck_hash", "label", "matched_signature_count", "evidence",
                  "n_unique_card_ids", "n_total_cards", "composition",
                  "n_games_seen", "dates_seen"]
    with open(OUT_DECKS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    with open(SELECTION, newline="") as f:
        selection = list(csv.DictReader(f))

    done_ids = load_done_ids()
    todo = [s for s in selection if s["episode_id"] not in done_ids]
    print(f"Total selection: {len(selection)}, already done: {len(done_ids)}, remaining: {len(todo)}")

    deck_registry = load_deck_registry()
    print(f"Loaded existing deck registry: {len(deck_registry)} decks")

    n_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
    t_start = time.time()
    total_parsed = 0
    total_dl_errors = 0
    total_parse_errors = 0

    for bi in range(n_batches):
        batch = todo[bi * BATCH_SIZE:(bi + 1) * BATCH_SIZE]
        t_batch = time.time()
        results = []
        for sel in batch:
            results.append(download_one(sel))
            if len(results) % 50 == 0:
                print(f"  ...{len(results)}/{len(batch)} downloads done in batch {bi+1} "
                      f"({time.time()-t_batch:.0f}s elapsed)", flush=True)

        dl_errors = [(sel["episode_id"], err) for sel, path, err in results if err]
        total_dl_errors += len(dl_errors)
        t_dl = time.time()

        episode_rows = []
        paths_to_delete = []
        for sel, path, err in results:
            if err or not os.path.exists(path):
                continue
            try:
                rec = parse_episode_file(path, sel["date"])
            except Exception as e:
                total_parse_errors += 1
                paths_to_delete.append(path)
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
                "episode_id": rec.episode_id, "date": rec.date, "period": sel["period"],
                "size_bytes": sel["size_bytes"], "avg_score": sel["avg_score"],
                "min_score": sel["min_score"], "sum_score": sel["sum_score"],
                "team0": rec.team_names[0] if rec.team_names else None,
                "team1": rec.team_names[1] if len(rec.team_names or []) > 1 else None,
                "winner": rec.winner, "outcome_type": rec.outcome_type,
                "first_player": rec.first_player, "n_steps": rec.n_steps,
                "final_turn_p0": rec.final_turn_p0, "final_turn_p1": rec.final_turn_p1,
                "deck0_hash": rec.deck0_hash, "deck1_hash": rec.deck1_hash,
                "deck0_ncards": sum(rec.deck0.values()), "deck1_ncards": sum(rec.deck1.values()),
                "deck0_source": rec.deck0_source, "deck1_source": rec.deck1_source,
            })
            paths_to_delete.append(path)

        append_episode_rows(episode_rows)
        save_deck_registry(deck_registry)
        total_parsed += len(episode_rows)

        # disk cleanup -- delete this batch's raw JSON now that it's captured in the CSVs
        for p in paths_to_delete:
            try:
                os.remove(p)
            except OSError:
                pass

        elapsed = time.time() - t_start
        print(f"[batch {bi+1}/{n_batches}] dl={t_dl-t_batch:.0f}s parse+cleanup={time.time()-t_dl:.0f}s "
              f"parsed={len(episode_rows)} dl_errors={len(dl_errors)} "
              f"total_parsed={total_parsed}/{len(todo)} elapsed={elapsed/60:.1f}min", flush=True)
        if dl_errors:
            print(f"  sample dl errors: {dl_errors[:3]}", flush=True)

    print(f"\nDONE. total_parsed={total_parsed} dl_errors={total_dl_errors} parse_errors={total_parse_errors} "
          f"wall={ (time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    main()
