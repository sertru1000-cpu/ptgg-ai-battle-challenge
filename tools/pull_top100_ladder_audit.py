"""Top-100 Real-Ladder Meta Audit -- Part A: pull raw data.

Read-only against Kaggle: no submission/agent/deck changes.

For each of the current top-N leaderboard entries (pokemon-tcg-ai-battle):
  1. competition_team_submissions(team_id) -> current live submission
     (most recent by dateSubmitted, same method as tools/pull_luca_data.py).
  2. competition_list_episodes(submission_id) -> filter to EPISODE_TYPE_PUBLIC
     (excludes the self-play validation episode).
  3. Sample up to SAMPLE_PER_TEAM episodes spread across the submission's
     episode history (first/middle/last by id) and download their replays.
  4. Extract this team's exact 60-card decklist from each sampled replay via
     the already-validated src/meta_analysis/episode_parser.py method
     (first 60-card action == deck-declare, cross-checked against
     visualize.deck), and check consistency across samples.

Checkpointed every team (results/top100_audit/pull_checkpoint.json) so a
rate-limit stall or interruption is resumable without re-pulling completed
teams. Raw JSON preserved per team in data/top100_audit/teams/<team_id>.json
-- never discarded, per this project's standing raw-data-preservation rule.
"""
from __future__ import annotations

import json
import os
import sys
import time

from kaggle.api.kaggle_api_extended import KaggleApi

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
sys.path.insert(0, ROOT)

from src.meta_analysis.episode_parser import _extract_deck, deck_hash  # noqa: E402

COMPETITION = "pokemon-tcg-ai-battle"
DATA_DIR = os.path.join(ROOT, "data", "top100_audit")
TEAMS_DIR = os.path.join(DATA_DIR, "teams")
REPLAY_DIR = os.path.join(DATA_DIR, "replays")
RESULTS_DIR = os.path.join(ROOT, "results", "top100_audit")
CHECKPOINT_PATH = os.path.join(RESULTS_DIR, "pull_checkpoint.json")
FAIL_LOG_PATH = os.path.join(RESULTS_DIR, "pull_failures.json")

os.makedirs(TEAMS_DIR, exist_ok=True)
os.makedirs(REPLAY_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

TOP_N = 100
SAMPLE_PER_TEAM = 3
SLEEP_S = 0.2


def load_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"done_team_ids": [], "results": []}


def save_checkpoint(cp):
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CHECKPOINT_PATH)


def api_retry(fn, *args, tries=4, **kwargs):
    last_ex = None
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as ex:  # noqa: BLE001
            last_ex = ex
            wait = 2 ** attempt
            print(f"    retry {attempt+1}/{tries} after error: {ex} (sleep {wait}s)")
            time.sleep(wait)
    raise last_ex


def main():
    api = KaggleApi()
    api.authenticate()

    with open(os.path.join(DATA_DIR, "leaderboard_raw.json"), "r", encoding="utf-8") as f:
        lb = json.load(f)
    entries = lb[:TOP_N]

    cp = load_checkpoint()
    done_ids = set(cp["done_team_ids"])
    fail_log = []
    if os.path.exists(FAIL_LOG_PATH):
        with open(FAIL_LOG_PATH, "r", encoding="utf-8") as f:
            fail_log = json.load(f)

    for rank, entry in enumerate(entries, start=1):
        team_id = entry["teamId"]
        if team_id in done_ids:
            continue
        team_name = entry["teamName"]
        rating = entry["score"]
        print(f"[{rank}/{len(entries)}] team_id={team_id} name={team_name!r} rating={rating}")

        record = {
            "rank": rank, "team_id": team_id, "team_name": team_name, "rating": rating,
            "leaderboard_submission_date": entry["submissionDate"],
        }
        try:
            subs = api_retry(api.competition_team_submissions, team_id)
            subs_dicts = [json.loads(str(s)) for s in subs]
            subs_dicts.sort(key=lambda s: s["dateSubmitted"], reverse=True)
            if not subs_dicts:
                record["status"] = "NO_SUBMISSIONS"
                cp["results"].append(record)
                done_ids.add(team_id)
                save_checkpoint(cp)
                continue
            target = subs_dicts[0]
            target_id = target["id"]
            record["submission_id"] = target_id
            record["submission_public_score"] = target.get("publicScore")
            record["submission_date"] = target.get("dateSubmitted")
            record["n_submissions_on_record"] = len(subs_dicts)

            time.sleep(SLEEP_S)
            eps = api_retry(api.competition_list_episodes, target_id)
            eps_dicts = [json.loads(str(e)) for e in eps]
            public_eps = [e for e in eps_dicts if e.get("type") == "EPISODE_TYPE_PUBLIC"
                          and e.get("state") == "COMPLETED"]
            record["n_episodes_total"] = len(eps_dicts)
            record["n_episodes_public_completed"] = len(public_eps)

            with open(os.path.join(TEAMS_DIR, f"{team_id}_episodes.json"), "w", encoding="utf-8") as f:
                json.dump(eps_dicts, f, indent=2, ensure_ascii=False)

            if not public_eps:
                record["status"] = "NO_PUBLIC_EPISODES"
                cp["results"].append(record)
                done_ids.add(team_id)
                save_checkpoint(cp)
                continue

            public_eps.sort(key=lambda e: e["id"])
            n = len(public_eps)
            if n <= SAMPLE_PER_TEAM:
                sample = public_eps
            else:
                idxs = sorted({0, n // 2, n - 1})
                sample = [public_eps[i] for i in idxs]

            deck_hashes = []
            deck_compositions = {}
            sample_info = []
            for ep in sample:
                eid = ep["id"]
                agents = ep["agents"]
                mine = next((a for a in agents if a["submissionId"] == target_id), None)
                if mine is None:
                    sample_info.append({"episode_id": eid, "error": "submission not in agents"})
                    continue
                my_idx = mine["index"]

                replay_path = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
                if not os.path.exists(replay_path):
                    time.sleep(SLEEP_S)
                    try:
                        api_retry(api.competition_episode_replay, eid, path=REPLAY_DIR, quiet=True)
                    except Exception as ex:  # noqa: BLE001
                        sample_info.append({"episode_id": eid, "error": f"replay dl: {ex}"})
                        continue

                if not os.path.exists(replay_path):
                    sample_info.append({"episode_id": eid, "error": "replay file missing after dl"})
                    continue

                with open(replay_path, "r", encoding="utf-8") as rf:
                    rdata = json.load(rf)
                steps = rdata["steps"]
                deck, src = _extract_deck(steps, my_idx)
                if not deck:
                    sample_info.append({"episode_id": eid, "error": "deck extraction empty"})
                    continue
                h = deck_hash(deck)
                deck_hashes.append(h)
                deck_compositions[h] = ";".join(f"{cid}:{cnt}" for cid, cnt in sorted(deck.items()))
                sample_info.append({"episode_id": eid, "deck_hash": h, "deck_source": src,
                                     "my_index": my_idx, "opponent_team": next(
                                         (a["teamName"] for a in agents if a["submissionId"] != target_id), None)})

            record["sample_info"] = sample_info
            record["deck_hashes_seen"] = list(dict.fromkeys(deck_hashes))
            record["deck_consistent"] = len(set(deck_hashes)) == 1 if deck_hashes else None
            record["deck_compositions"] = deck_compositions
            record["status"] = "OK" if deck_hashes else "DECK_EXTRACTION_FAILED"

            cp["results"].append(record)
            done_ids.add(team_id)
            cp["done_team_ids"] = list(done_ids)
            save_checkpoint(cp)

        except Exception as ex:  # noqa: BLE001
            print(f"  FAILED: {ex}")
            fail_log.append({"team_id": team_id, "rank": rank, "error": str(ex)})
            with open(FAIL_LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(fail_log, f, indent=2)
            # do not mark done -- resumable retry next run
        time.sleep(SLEEP_S)

    print("DONE. Teams completed:", len(cp["results"]), "Failures:", len(fail_log))


if __name__ == "__main__":
    main()
