"""Luca Episode Data Audit -- Part A: pull raw data.

Downloads, for Luca's CURRENT live submission (id resolved dynamically via
competition_team_submissions, not hardcoded -- confirmed 55447414 / score
1232.4 as of 2026-08-12), every episode's full replay JSON. Agent stdout/
stderr logs are NOT retrievable for a team we don't own (confirmed 403
Forbidden this session, symmetric with the already-known "opponent logs are
403" finding from session 16) -- all behavioral analysis must come from the
replay JSON alone (action/observation/visualize), same as the historical
bulk-episode-dataset analysis already done in sessions 4-11.

Also resolves each unique opponent's current publicScore via
competition_team_submissions(team_id) -- confirmed this endpoint is public
(works for any team_id, not just our own).

Read-only against Kaggle: no submission, no agent/deck/config changes.
"""
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi

COMPETITION = "pokemon-tcg-ai-battle"
LUCA_TEAM_ID = 16448747
OUT_DIR = r"C:\Users\sertru1000\Projects\PokemonGame\data\luca_audit"
REPLAY_DIR = os.path.join(OUT_DIR, "replays")

os.makedirs(REPLAY_DIR, exist_ok=True)


def main():
    api = KaggleApi()
    api.authenticate()

    subs = api.competition_team_submissions(LUCA_TEAM_ID)
    subs_dicts = [json.loads(str(s)) for s in subs]
    subs_dicts.sort(key=lambda s: s["dateSubmitted"], reverse=True)
    with open(os.path.join(OUT_DIR, "luca_submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(subs_dicts, f, indent=2, ensure_ascii=False)
    target = subs_dicts[0]
    target_id = target["id"]
    print("Luca's current (highest-score-relevant, most recent) submission:", target_id,
          "score:", target["publicScore"], "submitted:", target["dateSubmitted"])
    print("All Luca submissions on record:", [(s["id"], s["publicScore"], s["dateSubmitted"]) for s in subs_dicts])

    eps = api.competition_list_episodes(target_id)
    eps_dicts = [json.loads(str(e)) for e in eps]
    with open(os.path.join(OUT_DIR, "luca_episodes_raw.json"), "w", encoding="utf-8") as f:
        json.dump(eps_dicts, f, indent=2, ensure_ascii=False)
    print("Episodes found for target submission:", len(eps_dicts))

    fail_log = []
    opponent_team_ids = {}
    for i, e in enumerate(eps_dicts):
        eid = e["id"]
        agents = e["agents"]
        luca_agent = next((a for a in agents if a["submissionId"] == target_id), None)
        if luca_agent is None:
            fail_log.append({"episode_id": eid, "error": "Luca's submission not in agents list"})
            continue
        opp_agent = next((a for a in agents if a["submissionId"] != target_id), None)
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

    # Pull each unique opponent's current publicScore (public endpoint, confirmed works
    # for arbitrary team_id, not just our own team).
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
    print("Target submission id:", target_id)


if __name__ == "__main__":
    main()
