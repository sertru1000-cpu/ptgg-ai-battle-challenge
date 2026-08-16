"""V8 vs V7 rapid regression audit -- Part A: pull raw data for BOTH submissions.

Mirrors tools/pull_v6_ladder_data.py exactly (same methodology: full episode list,
replay download, opponent current-rating pull), applied to V7 and V8's real
Kaggle submissions so the two are apples-to-apples comparable.

V7 = submission 55478172 (challenger_v7_20260813T082207Z.tar.gz, live score 610.3
at audit time -- a prior pull existed at data/v7_ladder_audit/ from an earlier
rapid crash-diagnosis pass, 27/29 replays, no opponent-rating pull -- this
refreshes it to full completeness).
V8 = submission 55482268 (challenger_v8_20260813T115034Z.tar.gz, live score 569.4
at audit time) -- first pull for this submission.

Read-only against Kaggle: no submission, no agent/deck/config changes.
"""
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi

COMPETITION = "pokemon-tcg-ai-battle"
TARGETS = {
    "v7": {"submission_id": 55478172, "out_dir": r"C:\Users\sertru1000\Projects\PokemonGame\data\v7_ladder_audit"},
    "v8": {"submission_id": 55482268, "out_dir": r"C:\Users\sertru1000\Projects\PokemonGame\data\v8_ladder_audit"},
}


def pull_one(api, label, sub_id, out_dir):
    replay_dir = os.path.join(out_dir, "replays")
    os.makedirs(replay_dir, exist_ok=True)

    subs = api.competition_submissions(COMPETITION)
    subs_dicts = [json.loads(str(s)) for s in subs]
    with open(os.path.join(out_dir, "our_submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(subs_dicts, f, indent=2, default=str, ensure_ascii=False)

    target = next(s for s in subs_dicts if s["ref"] == sub_id)
    print(f"[{label}] Target submission:", target["ref"], "score:", target["publicScore"],
          "date:", target["date"], "file:", target["fileName"])

    eps = api.competition_list_episodes(sub_id)
    eps_dicts = [json.loads(str(e)) for e in eps]
    eps_dicts.sort(key=lambda e: e["createTime"])
    with open(os.path.join(out_dir, f"{label}_episodes_raw.json"), "w", encoding="utf-8") as f:
        json.dump(eps_dicts, f, indent=2, ensure_ascii=False)
    print(f"[{label}] Episodes found:", len(eps_dicts))
    print(f"[{label}] Episode types:", {t: sum(1 for e in eps_dicts if e.get("type") == t)
                                          for t in set(e.get("type") for e in eps_dicts)})

    fail_log = []
    opponent_team_ids = {}
    for i, e in enumerate(eps_dicts):
        eid = e["id"]
        agents = e["agents"]
        own_agent = next((a for a in agents if a["submissionId"] == sub_id), None)
        if own_agent is None:
            fail_log.append({"episode_id": eid, "error": "own submission not in agents list"})
            continue
        opp_agent = next((a for a in agents if a["submissionId"] != sub_id), None)
        if opp_agent is not None:
            opponent_team_ids[opp_agent["teamId"]] = opp_agent["teamName"]

        replay_path = os.path.join(replay_dir, f"episode-{eid}-replay.json")
        if not os.path.exists(replay_path):
            try:
                api.competition_episode_replay(eid, path=replay_dir, quiet=True)
            except Exception as ex:  # noqa: BLE001
                fail_log.append({"episode_id": eid, "error": f"replay: {ex}"})

        if (i + 1) % 10 == 0:
            print(f"[{label}] ...{i + 1}/{len(eps_dicts)} replays done")
        time.sleep(0.15)

    with open(os.path.join(out_dir, "download_failures.json"), "w", encoding="utf-8") as f:
        json.dump(fail_log, f, indent=2)
    print(f"[{label}] Replay download done. Failures:", len(fail_log))
    print(f"[{label}] Unique opponents faced:", len(opponent_team_ids))

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
            print(f"[{label}] ...{j + 1}/{len(opponent_team_ids)} opponent ratings done")
        time.sleep(0.2)

    with open(os.path.join(out_dir, "opponent_ratings_raw.json"), "w", encoding="utf-8") as f:
        json.dump(opponent_ratings, f, indent=2, ensure_ascii=False)
    print(f"[{label}] Opponent ratings pulled:", len(opponent_ratings))


def main():
    api = KaggleApi()
    api.authenticate()
    for label, cfg in TARGETS.items():
        pull_one(api, label, cfg["submission_id"], cfg["out_dir"])


if __name__ == "__main__":
    main()
