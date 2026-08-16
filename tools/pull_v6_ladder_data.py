"""V6 Real Ladder Audit -- Part A: pull raw data.

Mirrors tools/pull_v2_ladder_data.py exactly (same methodology, apples-to-apples
per the V6-vs-V2 real-ladder audit instructions), targeting V6's actual Kaggle
submission instead of V2's.

V6 = V2 + the two confirmed Phantom Dive bugfixes (session 24,
PHANTOM_DIVE_V6_FIX_REPORT.md). Submission discovered via a direct live
competition_submissions() check this session (not from stale memory/registry
records, which still said "not yet submitted" as of end of session 24):
id 55475115, submitted 2026-08-13T05:29:14Z, file
challenger_v6_20260813T050318Z.tar.gz, COMPLETE, live score 731.0 at
discovery time -- i.e. this submission DID get matched into real ladder
games (not stuck at the 600.0 dormant-submission pattern seen for V2's and
V4's first attempts). Only one V6 submission exists (checked directly), so
there is no duplicate/superseded-id disambiguation needed here (unlike V2/V4).

Read-only against Kaggle: no submission, no agent/deck/config changes.
"""
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi

COMPETITION = "pokemon-tcg-ai-battle"
V6_SUBMISSION_ID = 55475115
OUT_DIR = r"C:\Users\sertru1000\Projects\PokemonGame\data\v6_ladder_audit"
REPLAY_DIR = os.path.join(OUT_DIR, "replays")

os.makedirs(REPLAY_DIR, exist_ok=True)


def main():
    api = KaggleApi()
    api.authenticate()

    subs = api.competition_submissions(COMPETITION)
    subs_dicts = [json.loads(str(s)) for s in subs]
    with open(os.path.join(OUT_DIR, "our_submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(subs_dicts, f, indent=2, default=str, ensure_ascii=False)

    target = next(s for s in subs_dicts if s["ref"] == V6_SUBMISSION_ID)
    print("Target V6 submission:", target["ref"], "score:", target["publicScore"],
          "date:", target["date"], "file:", target["fileName"])

    eps = api.competition_list_episodes(V6_SUBMISSION_ID)
    eps_dicts = [json.loads(str(e)) for e in eps]
    eps_dicts.sort(key=lambda e: e["createTime"])
    with open(os.path.join(OUT_DIR, "v6_episodes_raw.json"), "w", encoding="utf-8") as f:
        json.dump(eps_dicts, f, indent=2, ensure_ascii=False)
    print("Episodes found:", len(eps_dicts))
    print("Episode types:", {t: sum(1 for e in eps_dicts if e.get("type") == t)
                              for t in set(e.get("type") for e in eps_dicts)})
    print("Date range:", eps_dicts[0]["createTime"] if eps_dicts else None, "to",
          eps_dicts[-1]["createTime"] if eps_dicts else None)

    fail_log = []
    opponent_team_ids = {}
    for i, e in enumerate(eps_dicts):
        eid = e["id"]
        agents = e["agents"]
        v6_agent = next((a for a in agents if a["submissionId"] == V6_SUBMISSION_ID), None)
        if v6_agent is None:
            fail_log.append({"episode_id": eid, "error": "V6 submission not in agents list"})
            continue
        opp_agent = next((a for a in agents if a["submissionId"] != V6_SUBMISSION_ID), None)
        if opp_agent is not None:
            opponent_team_ids[opp_agent["teamId"]] = opp_agent["teamName"]

        replay_path = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
        if not os.path.exists(replay_path):
            try:
                api.competition_episode_replay(eid, path=REPLAY_DIR, quiet=True)
            except Exception as ex:  # noqa: BLE001
                fail_log.append({"episode_id": eid, "error": f"replay: {ex}"})

        if (i + 1) % 10 == 0:
            print(f"...{i + 1}/{len(eps_dicts)} replays done")
        time.sleep(0.15)

    with open(os.path.join(OUT_DIR, "download_failures.json"), "w", encoding="utf-8") as f:
        json.dump(fail_log, f, indent=2)
    print("Replay download done. Failures:", len(fail_log))
    print("Unique opponents faced:", len(opponent_team_ids))

    opponent_ratings = []
    for j, (tid, tname) in enumerate(opponent_team_ids.items()):
        try:
            osubs = api.competition_team_submissions(tid)
            osubs_dicts = [json.loads(str(s)) for s in osubs]
            osubs_dicts.sort(key=lambda s: s["dateSubmitted"], reverse=True)
            cur = osubs_dicts[0] if osubs_dicts else None
            opponent_ratings.append({
                "team_id": tid, "team_name": tname,
                "current_submission_id": cur["id"] if cur else None,
                "current_public_score": cur["publicScore"] if cur else None,
                "current_submission_date": cur["dateSubmitted"] if cur else None,
                "n_submissions_on_record": len(osubs_dicts),
            })
        except Exception as ex:  # noqa: BLE001
            opponent_ratings.append({"team_id": tid, "team_name": tname, "error": str(ex)})
        if (j + 1) % 10 == 0:
            print(f"...{j + 1}/{len(opponent_team_ids)} opponent ratings done")
        time.sleep(0.2)

    with open(os.path.join(OUT_DIR, "opponent_ratings_raw.json"), "w", encoding="utf-8") as f:
        json.dump(opponent_ratings, f, indent=2, ensure_ascii=False)
    print("Opponent ratings pulled:", len(opponent_ratings))


if __name__ == "__main__":
    main()
