"""Incremental/streaming extraction pipeline for Part 4.1 v3.

Architecture (per the phase-4.1-v3 prompt's explicit requirement):
  episode source -> fetch one/small batch -> extract only required fields ->
  append normalized record -> discard raw episode -> next episode.

Two input streams feed the same output:
  1. REUSE stream (data/episode_manifests/meta_v3_reuse_selection.csv, 1,125
     episodes): already downloaded+parsed in prior sessions (pilot / meta_v2
     attempts). No network call, no raw JSON re-read -- normalized fields are
     read straight from the existing compact per-episode CSVs and the deck
     registries (composition lookup by deck_hash), which is itself already a
     "discard the raw episode, keep the compact record" outcome from before.
  2. NEW stream (data/episode_manifests/meta_v3_new_selection.csv, ~2,375
     episodes): genuinely streamed -- one Kaggle API call fetches one episode's
     raw JSON, it is parsed immediately, the normalized fields are appended, and
     the raw file is deleted before the next episode is fetched. Never more than
     one raw episode file resident at a time for this stream.

Never loads more than one batch of raw JSON at a time, never holds a full
raw-episode list in memory -- only the compact normalized records accumulate.

Output (append-only, resumable):
  strategy/meta_analysis/meta_v3_episodes.csv   canonical normalized long-format-ready
                                                 store (superset of the parquet fields
                                                 so the parquet builder never re-parses)
  strategy/meta_analysis/meta_v3_deck_registry.csv
  results/meta/processing_checkpoint.json       processed/successful/failed counts +
                                                 last_processed_episode_id/timestamp
  results/meta/processing_failures.csv          episode_id, stage, reason (append-only)

Resumable: on restart, episode_ids already present in meta_v3_episodes.csv are
skipped for BOTH streams.
"""
import csv
import json
import os
import socket
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

socket.setdefaulttimeout(30)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.meta_analysis.episode_parser import parse_episode_file, deck_hash
from src.meta_analysis.archetype_signatures import tag_deck

os.environ.setdefault("KAGGLE_CONFIG_DIR", os.path.expanduser("~/.kaggle"))

REUSE_SELECTION = os.path.join(REPO_ROOT, "data", "episode_manifests", "meta_v3_reuse_selection.csv")
NEW_SELECTION = os.path.join(REPO_ROOT, "data", "episode_manifests", "meta_v3_new_selection.csv")
PILOT_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_episodes_v1.csv")
PILOT_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_deck_registry_v1.csv")
V2_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_episodes.csv")
V2_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_deck_registry.csv")
MANIFEST = os.path.join(REPO_ROOT, "data", "episode_manifests", "all_episodes_manifest.csv")
RAW_DIR = os.path.join(REPO_ROOT, "data", "episode_pilot")

OUT_EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v3_episodes.csv")
OUT_DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v3_deck_registry.csv")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "meta")
CHECKPOINT = os.path.join(RESULTS_DIR, "processing_checkpoint.json")
FAILURES = os.path.join(RESULTS_DIR, "processing_failures.csv")

BATCH_SIZE = 200          # persistence cadence, per spec section 8 (100-250)
CHECKPOINT_EVERY = 50     # finer-grained checkpoint within a batch
SLEEP_PER_CALL = 0.4      # matches the proven ~30 episodes/min sequential rate

EPISODE_FIELDS = [
    "episode_id", "date", "period", "timestamp",
    "team0", "team1", "min_score", "sum_score",
    "winner", "outcome_type", "first_player", "n_steps",
    "final_turn_p0", "final_turn_p1",
    "deck0_hash", "deck1_hash", "deck0_ncards", "deck1_ncards",
    "source",  # "pilot" | "meta_v2_reuse" | "new"
]

_deck_registry = {}  # deck_hash -> {label, composition, n_games_seen, dates_seen}
_shared_api = None


def get_api():
    global _shared_api
    if _shared_api is None:
        from kaggle.api.kaggle_api_extended import KaggleApi
        _shared_api = KaggleApi()
        _shared_api.authenticate()
    return _shared_api


def load_done_ids():
    if not os.path.exists(OUT_EPISODES):
        return set()
    with open(OUT_EPISODES, encoding="utf-8", newline="") as f:
        return {r["episode_id"] for r in csv.DictReader(f)}


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
                  "n_unique_card_ids", "n_total_cards", "composition", "n_games_seen", "dates_seen"]
    with open(OUT_DECKS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def register_deck(hsh, deck_counter):
    """deck_counter: Counter(card_id -> count). Updates the running registry
    (n_games_seen incremented by caller, this only creates the entry)."""
    if hsh not in _deck_registry and len(deck_counter) > 0:
        label, matched_n, evidence = tag_deck(deck_counter)
        _deck_registry[hsh] = {
            "deck_hash": hsh, "label": label, "matched_signature_count": matched_n,
            "evidence": ",".join(sorted(set(evidence))),
            "n_unique_card_ids": len(deck_counter), "n_total_cards": sum(deck_counter.values()),
            "composition": ";".join(f"{cid}:{c}" for cid, c in sorted(deck_counter.items())),
            "n_games_seen": 0, "dates_seen": set(),
        }
    return _deck_registry.get(hsh)


def bump_deck(hsh, date_str):
    if hsh in _deck_registry:
        _deck_registry[hsh]["n_games_seen"] += 1
        _deck_registry[hsh]["dates_seen"].add(date_str)


def append_episode_rows(rows):
    write_header = not os.path.exists(OUT_EPISODES)
    with open(OUT_EPISODES, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EPISODE_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def append_failure(episode_id, stage, reason):
    write_header = not os.path.exists(FAILURES)
    with open(FAILURES, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["episode_id", "stage", "reason", "logged_at"])
        w.writerow([episode_id, stage, str(reason)[:300], datetime.now(timezone.utc).isoformat()])


def write_checkpoint(processed, successful, failed, last_id, last_ts):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump({
            "processed_count": processed, "successful_count": successful,
            "failed_count": failed, "last_processed_episode_id": last_id,
            "last_processed_timestamp": last_ts,
            "checkpoint_written_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)


# ============================= REUSE STREAM =============================

def run_reuse_stream(done_ids, manifest):
    """Materialize already-processed episodes' normalized fields from the
    existing compact CSVs -- no network, no raw JSON. Still one-record-at-a-time
    in spirit (iterates and appends per source row, never builds a giant joined
    DataFrame of raw episode content)."""
    if not os.path.exists(REUSE_SELECTION):
        print("No reuse selection found, skipping reuse stream.")
        return 0, 0

    with open(REUSE_SELECTION, newline="") as f:
        reuse = list(csv.DictReader(f))
    reuse_ids = {r["episode_id"]: r for r in reuse}
    print(f"Reuse stream: {len(reuse)} episodes requested, "
          f"{sum(1 for i in reuse_ids if i in done_ids)} already materialized")

    # source lookups, built once (small: 1,000 + 468 rows each)
    def load_csv(path, keyfield):
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8", newline="") as f:
            return {r[keyfield]: r for r in csv.DictReader(f)}

    pilot_ep = load_csv(PILOT_EPISODES, "episode_id")
    v2_ep = load_csv(V2_EPISODES, "episode_id")
    pilot_decks = load_csv(PILOT_DECKS, "deck_hash")
    v2_decks = load_csv(V2_DECKS, "deck_hash")

    n_ok, n_fail = 0, 0
    batch_out = []
    for eid, sel in reuse_ids.items():
        if eid in done_ids:
            continue
        src_ep = pilot_ep.get(eid) if sel["source"] == "pilot" else v2_ep.get(eid)
        if src_ep is None:
            append_failure(eid, "reuse_lookup", f"not found in {sel['source']} episodes CSV")
            n_fail += 1
            continue
        m = manifest.get(eid)
        if m is None:
            append_failure(eid, "reuse_lookup", "not found in full manifest")
            n_fail += 1
            continue

        deck_table = pilot_decks if sel["source"] == "pilot" else v2_decks
        for hkey, ckey in (("deck0_hash", "deck0"), ("deck1_hash", "deck1")):
            hsh = src_ep.get(hkey)
            if not hsh:
                continue
            drow = deck_table.get(hsh)
            if hsh not in _deck_registry and drow:
                _deck_registry[hsh] = {
                    "deck_hash": hsh, "label": drow.get("label", "UNLABELED"),
                    "matched_signature_count": drow.get("matched_signature_count", 0),
                    "evidence": drow.get("evidence", ""),
                    "n_unique_card_ids": drow.get("n_unique_card_ids", 0),
                    "n_total_cards": drow.get("n_total_cards", 0),
                    "composition": drow.get("composition", ""),
                    "n_games_seen": 0, "dates_seen": set(),
                }
            bump_deck(hsh, src_ep["date"])

        batch_out.append({
            "episode_id": eid, "date": src_ep["date"], "period": sel["period"],
            "timestamp": m.get("create_time", ""),
            "team0": src_ep.get("team0"), "team1": src_ep.get("team1"),
            "min_score": m.get("min_score"), "sum_score": m.get("sum_score"),
            "winner": src_ep.get("winner"), "outcome_type": src_ep.get("outcome_type"),
            "first_player": src_ep.get("first_player"), "n_steps": src_ep.get("n_steps"),
            "final_turn_p0": src_ep.get("final_turn_p0"), "final_turn_p1": src_ep.get("final_turn_p1"),
            "deck0_hash": src_ep.get("deck0_hash"), "deck1_hash": src_ep.get("deck1_hash"),
            "deck0_ncards": src_ep.get("deck0_ncards"), "deck1_ncards": src_ep.get("deck1_ncards"),
            "source": sel["source"] + "_reuse",
        })
        n_ok += 1
        if len(batch_out) >= BATCH_SIZE:
            append_episode_rows(batch_out)
            save_deck_registry(_deck_registry)
            batch_out = []

    if batch_out:
        append_episode_rows(batch_out)
        save_deck_registry(_deck_registry)
    print(f"Reuse stream done: {n_ok} materialized, {n_fail} failed lookups")
    return n_ok, n_fail


# ============================== NEW STREAM ==============================

def download_one(sel):
    api = get_api()
    date_, episode_id = sel["date"], sel["episode_id"]
    slug = f"kaggle/pokemon-tcg-ai-battle-episodes-{date_}"
    outdir = os.path.join(RAW_DIR, date_)
    os.makedirs(outdir, exist_ok=True)
    fname = f"{episode_id}.json"
    local_path = os.path.join(outdir, fname)
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path, None
    last_err = None
    for attempt in range(6):
        try:
            api.dataset_download_file(slug, fname, path=outdir, force=True, quiet=True)
            time.sleep(SLEEP_PER_CALL)
            return local_path, None
        except Exception as e:
            last_err = e
            is_429 = "429" in str(e)
            time.sleep((15 * (attempt + 1)) if is_429 else (4 * (attempt + 1)))
    return local_path, last_err


def run_new_stream(done_ids, manifest, start_processed, start_ok, start_fail):
    if not os.path.exists(NEW_SELECTION):
        print("No new-download selection found, skipping new stream.")
        return
    with open(NEW_SELECTION, newline="") as f:
        selection = list(csv.DictReader(f))
    todo = [s for s in selection if s["episode_id"] not in done_ids]
    print(f"New stream: {len(selection)} total, {len(selection)-len(todo)} already done, {len(todo)} remaining")

    processed, successful, failed = start_processed, start_ok, start_fail
    batch_out = []
    t0 = time.time()
    for i, sel in enumerate(todo, start=1):
        eid, date_ = sel["episode_id"], sel["date"]
        path, dl_err = download_one(sel)
        processed += 1

        if dl_err:
            failed += 1
            append_failure(eid, "download", dl_err)
        else:
            try:
                rec = parse_episode_file(path, date_)
            except Exception as e:
                failed += 1
                append_failure(eid, "parse", e)
                rec = None
            finally:
                try:
                    os.remove(path)  # discard raw episode immediately after extraction
                except OSError:
                    pass

            if rec is not None:
                if len(rec.deck0) == 0 or len(rec.deck1) == 0:
                    failed += 1
                    append_failure(eid, "validate", "missing/empty deck (deck0 or deck1)")
                else:
                    for hsh, deck in ((rec.deck0_hash, rec.deck0), (rec.deck1_hash, rec.deck1)):
                        register_deck(hsh, deck)
                        bump_deck(hsh, rec.date)
                    m = manifest.get(eid, {})
                    batch_out.append({
                        "episode_id": rec.episode_id, "date": rec.date, "period": sel["period"],
                        "timestamp": m.get("create_time", ""),
                        "team0": rec.team_names[0] if rec.team_names else None,
                        "team1": rec.team_names[1] if len(rec.team_names or []) > 1 else None,
                        "min_score": sel.get("min_score"), "sum_score": sel.get("sum_score"),
                        "winner": rec.winner, "outcome_type": rec.outcome_type,
                        "first_player": rec.first_player, "n_steps": rec.n_steps,
                        "final_turn_p0": rec.final_turn_p0, "final_turn_p1": rec.final_turn_p1,
                        "deck0_hash": rec.deck0_hash, "deck1_hash": rec.deck1_hash,
                        "deck0_ncards": sum(rec.deck0.values()), "deck1_ncards": sum(rec.deck1.values()),
                        "source": "new",
                    })
                    successful += 1

        # raw episode object (rec, path contents) goes out of scope here -- discarded

        if processed % CHECKPOINT_EVERY == 0 or i == len(todo):
            if batch_out:
                append_episode_rows(batch_out)
                save_deck_registry(_deck_registry)
                batch_out = []
            write_checkpoint(processed, successful, failed, eid, sel.get("date"))
            rate = (i / (time.time() - t0) * 60) if time.time() > t0 else 0
            print(f"  [{i}/{len(todo)}] processed={processed} ok={successful} failed={failed} "
                  f"rate={rate:.1f}/min", flush=True)

    if batch_out:
        append_episode_rows(batch_out)
        save_deck_registry(_deck_registry)
    print(f"New stream done: processed={processed} successful={successful} failed={failed}")


def main():
    with open(MANIFEST, newline="") as f:
        manifest = {r["episode_id"]: r for r in csv.DictReader(f)}
    print(f"Loaded manifest: {len(manifest)} rows (not held per-episode raw data, just the index)")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    _deck_registry.update(load_deck_registry())
    done_ids = load_done_ids()
    print(f"Already-materialized episodes (resumed): {len(done_ids)}")

    n_reuse_ok, n_reuse_fail = run_reuse_stream(done_ids, manifest)
    done_ids = load_done_ids()  # refresh after reuse stream

    run_new_stream(done_ids, manifest, start_processed=len(done_ids),
                   start_ok=len(done_ids), start_fail=n_reuse_fail)

    final_done = load_done_ids()
    print(f"\nFINAL: {len(final_done)} episodes in {OUT_EPISODES}")


if __name__ == "__main__":
    main()
