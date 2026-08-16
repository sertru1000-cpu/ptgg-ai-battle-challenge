"""Read-only Kaggle audit: current state of V2/V3/V4/V5 (and V1 for context) on the
real pokemon-tcg-ai-battle ladder. Per the requested methodology: resolve our team via
competition_leaderboard_view, then pull submissions via competition_team_submissions,
then episodes via competition_list_episodes for each target submission.

No submission, no deck/agent change, no upload/delete. Pure data pull.
"""
import json
import os
import time

from kaggle.api.kaggle_api_extended import KaggleApi

COMPETITION = "pokemon-tcg-ai-battle"
OUT_DIR = r"C:\Users\sertru1000\Projects\PokemonGame\data\v2_v5_ladder_audit"
REPLAY_DIR = os.path.join(OUT_DIR, "replays")
os.makedirs(REPLAY_DIR, exist_ok=True)

# Known from session 18 memory -- verified fresh below, not trusted blindly.
KNOWN_IDS = {"V1": 55437549, "V2": 55449821, "V3": 55449823, "V4": 55449825, "V5": 55449827}


def main():
    api = KaggleApi()
    api.authenticate()

    # Step 1: find our team via the public leaderboard view.
    lb = api.competition_leaderboard_view(COMPETITION)
    lb_dicts = [json.loads(str(row)) for row in lb]
    with open(os.path.join(OUT_DIR, "leaderboard_raw.json"), "w", encoding="utf-8") as f:
        json.dump(lb_dicts, f, indent=2, ensure_ascii=False)
    print("Leaderboard rows:", len(lb_dicts))

    our_row = None
    for row in lb_dicts:
        tname = row.get("teamName", "")
        if "Serguei Makarov" in tname or "sergueimakarov" in tname.lower():
            our_row = row
            break
    if our_row:
        print("Found our team on leaderboard:", our_row)
    else:
        print("Our team NOT found by name match on leaderboard (may be paginated) -- "
              "falling back to team_id 16510917 confirmed via prior replay metadata.")

    our_team_id = int(our_row["teamId"]) if our_row else 16510917

    # Step 2: pull our full submission list via the team endpoint (per requested method).
    subs = api.competition_team_submissions(our_team_id)
    subs_dicts = [json.loads(str(s)) for s in subs]
    subs_dicts.sort(key=lambda s: s["dateSubmitted"])
    with open(os.path.join(OUT_DIR, "our_team_submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(subs_dicts, f, indent=2, ensure_ascii=False)
    print("Our team submissions found:", len(subs_dicts))
    for s in subs_dicts:
        print(" ", s["id"], s.get("publicScore"), s.get("status"), s.get("dateSubmitted"), s.get("fileName"))

    # Cross-check: also pull via our own authenticated competition_submissions (independent path).
    own_subs = api.competition_submissions(COMPETITION)
    own_dicts = [json.loads(str(s)) for s in own_subs]
    with open(os.path.join(OUT_DIR, "own_competition_submissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(own_dicts, f, indent=2, default=str, ensure_ascii=False)
    print("Own competition_submissions() count:", len(own_dicts))

    # Step 3: for each target version, resolve the real submission id (prefer the one
    # confirmed present in subs_dicts; fall back to KNOWN_IDS only if not found there).
    found_ids = {s["id"] for s in subs_dicts}
    targets = {}
    for ver, kid in KNOWN_IDS.items():
        if kid in found_ids:
            targets[ver] = kid
        else:
            print(f"WARNING: known id for {ver} ({kid}) not found in fresh team_submissions pull")
    print("Resolved targets:", targets)

    all_episodes = {}
    for ver, sid in targets.items():
        eps = api.competition_list_episodes(sid)
        eps_dicts = [json.loads(str(e)) for e in eps]
        all_episodes[ver] = eps_dicts
        with open(os.path.join(OUT_DIR, f"episodes_{ver}_{sid}.json"), "w", encoding="utf-8") as f:
            json.dump(eps_dicts, f, indent=2, ensure_ascii=False)
        public = [e for e in eps_dicts if e.get("type") == "EPISODE_TYPE_PUBLIC"]
        validation = [e for e in eps_dicts if e.get("type") == "EPISODE_TYPE_VALIDATION"]
        other = [e for e in eps_dicts if e.get("type") not in ("EPISODE_TYPE_PUBLIC", "EPISODE_TYPE_VALIDATION")]
        print(f"{ver} (id={sid}): total={len(eps_dicts)} PUBLIC={len(public)} VALIDATION={len(validation)} OTHER={len(other)}")

    # Step 4: download replay JSON for every PUBLIC episode of V2-V5 (skip already-downloaded).
    fail_log = []
    for ver, eps_dicts in all_episodes.items():
        public = [e for e in eps_dicts if e.get("type") == "EPISODE_TYPE_PUBLIC"]
        for i, e in enumerate(public):
            eid = e["id"]
            replay_path = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
            if not os.path.exists(replay_path):
                try:
                    api.competition_episode_replay(eid, path=REPLAY_DIR, quiet=True)
                except Exception as ex:  # noqa: BLE001
                    fail_log.append({"version": ver, "episode_id": eid, "error": str(ex)})
            time.sleep(0.15)
        print(f"{ver}: replay download pass done ({len(public)} public episodes)")

    with open(os.path.join(OUT_DIR, "download_failures.json"), "w", encoding="utf-8") as f:
        json.dump(fail_log, f, indent=2)
    print("Replay download failures:", len(fail_log))
    print("DONE. Targets:", targets)


if __name__ == "__main__":
    main()
