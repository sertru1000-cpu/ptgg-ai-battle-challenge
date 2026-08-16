"""Downloads the FULL public episode history of the top-100 ladder's
Dragapult-playing teams (19 teams, ~700 episodes) -- the raw material for
both the V19 heuristic spec (how leaders actually play Munkidori/Judge/
Jamming Tower) and B1's training set (P(win) from top-level demonstrations).

Reuses tools/pull_top100_ladder_audit.py's exact validated mechanism:
per-team episode lists are ALREADY on disk (data/top100_audit/teams/
{team_id}_episodes.json, pulled 2026-08-13); this script only downloads the
replay JSONs that aren't already local (data/top100_audit/replays/ holds ~3
per team from the audit; new files go to data/leader_episodes/). Sequential
with retry/backoff (the Kaggle API 429s under concurrency -- established in
the Phase 4.1 pulls), checkpointed via file existence (a partial run simply
resumes by skipping what exists).

Usage:
    python tools/pull_leader_episodes.py [--max-per-team N]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AUDIT_DIR = REPO_ROOT / "data" / "top100_audit"
TEAMS_DIR = AUDIT_DIR / "teams"
AUDIT_REPLAYS = AUDIT_DIR / "replays"
OUT_DIR = REPO_ROOT / "data" / "leader_episodes"
LEADERBOARD_CSV = REPO_ROOT / "results" / "top100_audit" / "leaderboard_decks.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-per-team", type=int, default=100)
    args = parser.parse_args()

    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(open(LEADERBOARD_CSV, encoding="utf-8")))
    drag_teams = [r for r in rows if "Dragapult" in r.get("archetype", "")]
    print(f"Dragapult teams: {len(drag_teams)}")

    todo: list[int] = []
    for team in drag_teams:
        team_id = team["team_id"]
        submission_id = int(team["submission_id"])
        eps_path = TEAMS_DIR / f"{team_id}_episodes.json"
        if not eps_path.exists():
            print(f"  [skip] no episode list for team {team['team_name']} ({team_id})")
            continue
        eps = json.load(open(eps_path, encoding="utf-8"))
        public_done = [
            e for e in eps
            if e.get("type") == "EPISODE_TYPE_PUBLIC" and e.get("state") == "COMPLETED"
            and any(a.get("submissionId") == submission_id for a in e.get("agents", []))
        ]
        public_done.sort(key=lambda e: e["id"])
        selected = public_done[-args.max_per_team:]  # most recent = current-meta play
        todo.extend(e["id"] for e in selected)
        print(f"  {team['rank']:>3} {team['team_name']}: {len(selected)} episodes queued")

    todo = sorted(set(todo))
    already = {p.name for p in AUDIT_REPLAYS.glob("episode-*-replay.json")}
    already |= {p.name for p in OUT_DIR.glob("episode-*-replay.json")}
    remaining = [eid for eid in todo if f"episode-{eid}-replay.json" not in already]
    print(f"Total unique episodes: {len(todo)}; already local: {len(todo) - len(remaining)}; to download: {len(remaining)}")

    ok = fail = 0
    t0 = time.time()
    for i, eid in enumerate(remaining):
        target = OUT_DIR / f"episode-{eid}-replay.json"
        for attempt in range(4):
            try:
                api.competition_episode_replay(eid, path=str(OUT_DIR), quiet=True)
                break
            except Exception as ex:  # noqa: BLE001 -- log-and-retry, never crash the batch
                wait = 5.0 * (2 ** attempt)
                print(f"  [retry {attempt + 1}] episode {eid}: {ex} (sleeping {wait:.0f}s)", flush=True)
                time.sleep(wait)
        if target.exists():
            ok += 1
        else:
            fail += 1
            print(f"  [FAIL] episode {eid} not downloaded after retries", flush=True)
        if (i + 1) % 25 == 0:
            rate = (i + 1) / max(1e-9, time.time() - t0) * 60
            print(f"[{i + 1}/{len(remaining)}] ok={ok} fail={fail} rate={rate:.1f}/min", flush=True)
        time.sleep(0.4)  # stay under the API's burst limits

    print(f"Done: ok={ok} fail={fail} in {(time.time() - t0) / 60:.1f} min. Dir: {OUT_DIR}")


if __name__ == "__main__":
    main()
