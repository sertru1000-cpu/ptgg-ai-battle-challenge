"""V7 Real Ladder Audit -- Part A: pull raw data.

Mirrors tools/pull_v6_ladder_data.py exactly, targeting V7's actual Kaggle
submission (id 55478172, challenger_v7_20260813T082207Z.tar.gz, submitted
2026-08-13T08:24:09Z, live score 594.3 at discovery time -- a catastrophic
drop from V6's 722.6). This is a rapid crash-diagnosis pull, not a full
statistical audit.

Read-only against Kaggle: no submission, no agent/deck/config changes.
"""
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi

COMPETITION = "pokemon-tcg-ai-battle"
V7_SUBMISSION_ID = 55478172
OUT_DIR = r"C:\Users\sertru1000\Projects\PokemonGame\data\v7_ladder_audit"
REPLAY_DIR = os.path.join(OUT_DIR, "replays")

os.makedirs(REPLAY_DIR, exist_ok=True)


def main():
    api = KaggleApi()
    api.authenticate()

    subs = api.competition_submissions(COMPETITION)
    subs_dicts = [json.loads(str(s)) for s in subs]
    with open(os.path.join(OUT_DIR, "our_submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(subs_dicts, f, indent=2, default=str, ensure_ascii=False)

    target = next(s for s in subs_dicts if s["ref"] == V7_SUBMISSION_ID)
    print("Target V7 submission:", target["ref"], "score:", target["publicScore"],
          "date:", target["date"], "file:", target["fileName"])

    eps = api.competition_list_episodes(V7_SUBMISSION_ID)
    eps_dicts = [json.loads(str(e)) for e in eps]
    eps_dicts.sort(key=lambda e: e["createTime"])
    with open(os.path.join(OUT_DIR, "v7_episodes_raw.json"), "w", encoding="utf-8") as f:
        json.dump(eps_dicts, f, indent=2, ensure_ascii=False)
    print("Episodes found:", len(eps_dicts))
    print("Episode types:", {t: sum(1 for e in eps_dicts if e.get("type") == t)
                              for t in set(e.get("type") for e in eps_dicts)})
    print("Date range:", eps_dicts[0]["createTime"] if eps_dicts else None, "to",
          eps_dicts[-1]["createTime"] if eps_dicts else None)

    fail_log = []
    for i, e in enumerate(eps_dicts):
        eid = e["id"]
        agents = e["agents"]
        v7_agent = next((a for a in agents if a["submissionId"] == V7_SUBMISSION_ID), None)
        if v7_agent is None:
            fail_log.append({"episode_id": eid, "error": "V7 submission not in agents list"})
            continue

        replay_path = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
        if not os.path.exists(replay_path):
            try:
                api.competition_episode_replay(eid, path=REPLAY_DIR, quiet=True)
            except Exception as ex:  # noqa: BLE001
                fail_log.append({"episode_id": eid, "error": f"replay: {ex}"})

        print(f"...{i + 1}/{len(eps_dicts)} replays done")
        time.sleep(0.15)

    with open(os.path.join(OUT_DIR, "download_failures.json"), "w", encoding="utf-8") as f:
        json.dump(fail_log, f, indent=2)
    print("Replay download done. Failures:", len(fail_log))


if __name__ == "__main__":
    main()
