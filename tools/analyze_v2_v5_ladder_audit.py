"""Read-only analysis: current real-ladder state of V1/V2/V3/V4/V5/V2_resubmit.

Consumes already-pulled data/v2_v5_ladder_audit/all_episodes_by_version.json +
replays (own dir + reused data/kaggle_ladder/replays for V1) and computes, per
PUBLIC-only episode set: W/L/WR, first/second split + WR, avg turns, 2+ prize
deficit rate, comeback rate. VALIDATION episodes are always excluded.
"""
import json
import os
import statistics

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
AUDIT_DIR = os.path.join(ROOT, "data", "v2_v5_ladder_audit")
V1_REPLAY_DIR = os.path.join(ROOT, "data", "kaggle_ladder", "replays")
V2V5_REPLAY_DIR = os.path.join(AUDIT_DIR, "replays")

SUBMISSION_IDS = {
    "V1": 55437549,
    "V2": 55449821,
    "V3": 55449823,
    "V4": 55449825,
    "V5": 55449827,
    "V2_resubmit": 55449878,
}


def replay_path(eid, version):
    d = V1_REPLAY_DIR if version == "V1" else V2V5_REPLAY_DIR
    p = os.path.join(d, f"episode-{eid}-replay.json")
    return p if os.path.exists(p) else None


def parse_episode(eid, ep_meta, sub_id, version):
    our_agent = next(a for a in ep_meta["agents"] if a["submissionId"] == sub_id)
    idx = our_agent["index"]
    reward = our_agent["reward"]
    opp_agent = next(a for a in ep_meta["agents"] if a["submissionId"] != sub_id)
    opp_reward = opp_agent["reward"]
    if reward == 1 and opp_reward == -1:
        result = "WIN"
    elif reward == -1 and opp_reward == 1:
        result = "LOSS"
    elif reward == 0 and opp_reward == 0:
        result = "DRAW"
    else:
        result = "ERROR_OR_TIMEOUT"

    row = {
        "episode_id": eid,
        "create_time": ep_meta.get("createTime"),
        "result": result,
        "opponent_team_name": opp_agent.get("teamName"),
        "opponent_team_id": opp_agent.get("teamId"),
        "went_first": None,
        "turns": None,
        "max_prize_deficit": None,
        "final_prize_margin": None,
        "comeback_from_2plus": None,
        "replay_available": False,
    }

    rp = replay_path(eid, version)
    if rp is None:
        return row
    row["replay_available"] = True
    with open(rp, encoding="utf-8") as f:
        d = json.load(f)
    steps = d["steps"]

    first_player = None
    for step in steps:
        for p in (0, 1):
            cur = step[p]["observation"].get("current")
            if cur and cur.get("firstPlayer") not in (None, -1):
                first_player = cur["firstPlayer"]
    row["went_first"] = (first_player == idx) if first_player is not None else None

    turn = None
    for step in steps:
        cur = step[idx]["observation"].get("current")
        if cur and cur.get("turn") is not None:
            turn = cur["turn"]
    row["turns"] = (turn + 1) if turn is not None else None

    prize_points = []
    for step in steps:
        cur = step[idx]["observation"].get("current")
        if not cur:
            continue
        pl = cur["players"][idx]
        opp = cur["players"][1 - idx]
        our_prize = len(pl.get("prize") or [])
        opp_prize = len(opp.get("prize") or [])
        prize_points.append((our_prize, opp_prize))
    if prize_points:
        max_deficit = max(us - op for us, op in prize_points)
        final_margin = prize_points[-1][0] - prize_points[-1][1]
        row["max_prize_deficit"] = max_deficit
        row["final_prize_margin"] = final_margin
        row["comeback_from_2plus"] = bool(max_deficit >= 2 and result == "WIN")
    return row


def summarize(rows, label):
    n = len(rows)
    decisive = [r for r in rows if r["result"] in ("WIN", "LOSS")]
    wins = sum(1 for r in decisive if r["result"] == "WIN")
    losses = sum(1 for r in decisive if r["result"] == "LOSS")
    draws = sum(1 for r in rows if r["result"] == "DRAW")
    errs = sum(1 for r in rows if r["result"] == "ERROR_OR_TIMEOUT")
    wr = wins / len(decisive) if decisive else None

    first_rows = [r for r in decisive if r["went_first"] is True]
    second_rows = [r for r in decisive if r["went_first"] is False]
    unknown_first = sum(1 for r in decisive if r["went_first"] is None)

    def wr_of(gs):
        return (sum(1 for g in gs if g["result"] == "WIN") / len(gs)) if gs else None

    turns = [r["turns"] for r in rows if r["turns"] is not None]
    deficits = [r for r in rows if r["max_prize_deficit"] is not None]
    n_2plus = sum(1 for r in deficits if r["max_prize_deficit"] >= 2)
    comebacks = sum(1 for r in deficits if r["comeback_from_2plus"])

    times = sorted(r["create_time"] for r in rows if r["create_time"])

    summary = {
        "label": label,
        "n_public_total": n,
        "wins": wins, "losses": losses, "draws": draws, "errors_or_timeout": errs,
        "win_rate_decisive": wr,
        "n_going_first": len(first_rows), "win_rate_first": wr_of(first_rows),
        "n_going_second": len(second_rows), "win_rate_second": wr_of(second_rows),
        "n_first_second_unknown": unknown_first,
        "avg_turns": statistics.mean(turns) if turns else None,
        "n_games_with_prize_data": len(deficits),
        "games_2plus_deficit": n_2plus,
        "pct_2plus_deficit": (n_2plus / len(deficits)) if deficits else None,
        "comebacks_from_2plus": comebacks,
        "comeback_rate": (comebacks / n_2plus) if n_2plus else None,
        "first_game_time": times[0] if times else None,
        "last_game_time": times[-1] if times else None,
    }
    return summary


def main():
    with open(os.path.join(AUDIT_DIR, "all_episodes_by_version.json"), encoding="utf-8") as f:
        all_eps = json.load(f)

    all_rows = {}
    all_summaries = {}
    for version, sub_id in SUBMISSION_IDS.items():
        eps = all_eps.get(version, [])
        public = [e for e in eps if e.get("type") == "EPISODE_TYPE_PUBLIC"]
        rows = [parse_episode(e["id"], e, sub_id, version) for e in public]
        all_rows[version] = rows
        all_summaries[version] = summarize(rows, version)

    out_dir = os.path.join(ROOT, "results", "v2_v5_ladder_audit")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "per_game_rows.json"), "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=2, default=str, ensure_ascii=False)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, default=str, ensure_ascii=False)

    for v, s in all_summaries.items():
        print(json.dumps(s, indent=2, default=str))
        print("---")


if __name__ == "__main__":
    main()
