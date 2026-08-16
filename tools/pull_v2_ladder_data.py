"""V2 Real Ladder Audit -- Part A: pull raw data.

Targets V2 Balanced's ACTUAL active Kaggle submission. Two submissions exist
for the identical V2 build (same fileName challenger_v2_20260812T053030Z.tar.gz,
same totalBytes -- confirmed byte-identical artifact, resubmitted 3 minutes
apart on 2026-08-12): id 55449821 (05:31:13Z) and id 55449878 (05:34:31Z).
Checked directly via competition_list_episodes before committing to either:
55449821 has ONLY the self-play validation episode (0 real ladder games,
score stuck at the 600.0 starting baseline) -- it was evidently superseded
before Kaggle's matchmaking ever paired it into a real game. 55449878 has
43 real EPISODE_TYPE_PUBLIC games (score 699.8 at last check). This script
therefore targets 55449878 only. Since both are the same code, this is not a
version-selection judgment call -- it's "use the one that actually has data."

Read-only against Kaggle: no submission, no agent/deck/config changes.
"""
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi

COMPETITION = "pokemon-tcg-ai-battle"
V2_SUBMISSION_ID = 55449878
V2_SUBMISSION_ID_DORMANT = 55449821  # same build, 0 real games -- recorded for the report, not pulled
OUT_DIR = r"C:\Users\sertru1000\Projects\PokemonGame\data\v2_ladder_audit"
REPLAY_DIR = os.path.join(OUT_DIR, "replays")

os.makedirs(REPLAY_DIR, exist_ok=True)


def main():
    api = KaggleApi()
    api.authenticate()

    subs = api.competition_submissions(COMPETITION)
    subs_dicts = [json.loads(str(s)) for s in subs]
    with open(os.path.join(OUT_DIR, "our_submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(subs_dicts, f, indent=2, default=str, ensure_ascii=False)

    target = next(s for s in subs_dicts if s["ref"] == V2_SUBMISSION_ID)
    print("Target V2 submission:", target["ref"], "score:", target["publicScore"],
          "date:", target["date"], "file:", target["fileName"])

    eps = api.competition_list_episodes(V2_SUBMISSION_ID)
    eps_dicts = [json.loads(str(e)) for e in eps]
    eps_dicts.sort(key=lambda e: e["createTime"])
    with open(os.path.join(OUT_DIR, "v2_episodes_raw.json"), "w", encoding="utf-8") as f:
        json.dump(eps_dicts, f, indent=2, ensure_ascii=False)
    print("Episodes found:", len(eps_dicts))
    print("Date range:", eps_dicts[0]["createTime"] if eps_dicts else None, "to",
          eps_dicts[-1]["createTime"] if eps_dicts else None)

    fail_log = []
    opponent_team_ids = {}
    for i, e in enumerate(eps_dicts):
        eid = e["id"]
        agents = e["agents"]
        v2_agent = next((a for a in agents if a["submissionId"] == V2_SUBMISSION_ID), None)
        if v2_agent is None:
            fail_log.append({"episode_id": eid, "error": "V2 submission not in agents list"})
            continue
        opp_agent = next((a for a in agents if a["submissionId"] != V2_SUBMISSION_ID), None)
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
