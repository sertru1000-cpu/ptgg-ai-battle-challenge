"""Phase: Kaggle Ladder ~50 Games Deep Analysis -- read-only data pull.

Downloads, for the current production submission (id resolved from
`competition_submissions`, not hardcoded), every episode's full replay JSON
and our own agent's per-step stdout/stderr/duration log. Opponent logs are
not retrievable (403 Forbidden -- confirmed by direct test, not assumed).

Read-only against Kaggle: no submission, no agent/deck/config changes.
"""
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi

COMPETITION = "pokemon-tcg-ai-battle"
OUT_DIR = r"C:\Users\sertru1000\Projects\PokemonGame\data\kaggle_ladder"
REPLAY_DIR = os.path.join(OUT_DIR, "replays")
LOG_DIR = os.path.join(OUT_DIR, "agent_logs")

os.makedirs(REPLAY_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def main():
    api = KaggleApi()
    api.authenticate()

    subs = api.competition_submissions(COMPETITION)
    subs_sorted = sorted(subs, key=lambda s: s.date, reverse=True)
    with open(os.path.join(OUT_DIR, "submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump([json.loads(str(s)) for s in subs_sorted], f, indent=2, default=str)

    # Current production submission = latest COMPLETE (status) submission.
    complete = [s for s in subs_sorted if str(s.status) == "SubmissionStatus.COMPLETE"]
    assert complete, "no COMPLETE submission found"
    target = complete[0]
    target_id = json.loads(str(target))["ref"]
    print("Target submission id:", target_id, "score:", json.loads(str(target)).get("publicScore"))

    eps = api.competition_list_episodes(target_id)
    eps_dicts = [json.loads(str(e)) for e in eps]
    with open(os.path.join(OUT_DIR, "episodes_raw.json"), "w", encoding="utf-8") as f:
        json.dump(eps_dicts, f, indent=2, ensure_ascii=False)
    print("Episodes found:", len(eps_dicts))

    our_index_by_episode = {}
    fail_log = []
    for i, e in enumerate(eps_dicts):
        eid = e["id"]
        agents = e["agents"]
        our_agent = next((a for a in agents if a["submissionId"] == target_id), None)
        if our_agent is None:
            fail_log.append({"episode_id": eid, "error": "our submission not in agents list"})
            continue
        our_index = our_agent["index"]
        our_index_by_episode[eid] = our_index

        replay_path = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
        if not os.path.exists(replay_path):
            try:
                api.competition_episode_replay(eid, path=REPLAY_DIR, quiet=True)
            except Exception as ex:  # noqa: BLE001
                fail_log.append({"episode_id": eid, "error": f"replay: {ex}"})

        log_path = os.path.join(LOG_DIR, f"episode-{eid}-agent-{our_index}-logs.json")
        if not os.path.exists(log_path):
            try:
                api.competition_episode_agent_logs(eid, our_index, path=LOG_DIR, quiet=True)
            except Exception as ex:  # noqa: BLE001
                fail_log.append({"episode_id": eid, "error": f"log: {ex}"})

        if (i + 1) % 10 == 0:
            print(f"...{i + 1}/{len(eps_dicts)} done")
        time.sleep(0.15)  # gentle pacing, avoid 429s (per session-4 memory finding)

    with open(os.path.join(OUT_DIR, "our_index_by_episode.json"), "w", encoding="utf-8") as f:
        json.dump(our_index_by_episode, f, indent=2)
    with open(os.path.join(OUT_DIR, "download_failures.json"), "w", encoding="utf-8") as f:
        json.dump(fail_log, f, indent=2)

    print("Done. Failures:", len(fail_log))
    print("Target submission id:", target_id)


if __name__ == "__main__":
    main()
