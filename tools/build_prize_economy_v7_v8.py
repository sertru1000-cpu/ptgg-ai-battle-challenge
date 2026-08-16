"""V7 vs V8 real-ladder audit -- prize economy from full replay traces.

Byte-for-byte the same methodology as tools/build_prize_economy_v2_v6.py
(full-replay-trace scan, min-ever-seen-prize-count-per-side, immune to which
side's decision row happened to be sampled), retargeted at V7/V8.

Read-only. Writes results/v7_v8_regression_audit/prize_economy.json.
"""
from __future__ import annotations

import json
import os

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
OUT_DIR = os.path.join(ROOT, "results", "v7_v8_regression_audit")
os.makedirs(OUT_DIR, exist_ok=True)

TARGETS = {
    "v7": {
        "submission_id": 55478172,
        "replay_dir": os.path.join(ROOT, "data", "v7_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v7_ladder_audit", "v7_episodes_raw.json"),
    },
    "v8": {
        "submission_id": 55482268,
        "replay_dir": os.path.join(ROOT, "data", "v8_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v8_ladder_audit", "v8_episodes_raw.json"),
    },
}


def scan_episode(eid, own_idx, opp_idx, steps):
    """Reads each side's prize count ONLY from that side's OWN observation
    channel (row[own_idx] for our count, row[opp_idx] for opponent's count) --
    NOT the cross-observer view used by the original build_prize_economy_v2_v6.py
    (row[p]["observation"]["current"]["players"][other_idx] for either p).

    BUG FOUND THIS SESSION, not present in the original script's own docstring
    claim ("either channel is authoritative regardless of whose decision row
    it was"): a player's channel only gets a freshly-updated `observation.
    current` on ticks where THAT player is being asked to act/observe;
    off-turn ticks can carry a STALE snapshot of the opponent's prize count
    that lags behind the opponent's own self-reported value at the identical
    row_i. Concretely verified on V8 episode 92642676 (a real LOSS):
    reading opponent prize count via OUR channel showed a frozen "3" for
    ~50 consecutive rows while the opponent's OWN channel showed it correctly
    dropping 5->2 over the same span -- blending both into one "min-ever-seen"
    trace (the original approach) fabricated a false "opponent already at 0
    prizes" reading that contradicted the actual terminal reward ([-1,1], a
    V8 loss) by a wide margin. Self-view-only avoids this: each side's own
    resource count is guaranteed freshest in that side's own channel.
    """
    trace = []
    for row_i, row in enumerate(steps):
        cur_own = row[own_idx]["observation"].get("current")
        cur_opp = row[opp_idx]["observation"].get("current")
        our_prize = len(cur_own["players"][own_idx].get("prize") or []) if cur_own else None
        opp_prize = len(cur_opp["players"][opp_idx].get("prize") or []) if cur_opp else None
        turn = (cur_own or cur_opp or {}).get("turn")
        deck_n = (cur_own or {}).get("players", [{}])[own_idx].get("deckCount") if cur_own else None
        if our_prize in (None,) or opp_prize in (None,):
            continue
        if our_prize == 0 and opp_prize == 0 and turn in (None, 0) and not trace:
            if deck_n in (None, 0):
                continue
        trace.append((row_i, turn, our_prize, opp_prize))

    first_real = next((i for i, t in enumerate(trace) if t[2] > 0 or t[3] > 0), None)
    if first_real is None:
        return None
    trace = trace[first_real:]
    if not trace:
        return None

    start_our, start_opp = trace[0][2], trace[0][3]
    min_our_seen, min_opp_seen = start_our, start_opp
    max_deficit = 0
    for _, _, op, pp in trace:
        min_our_seen = min(min_our_seen, op)
        min_opp_seen = min(min_opp_seen, pp)
        deficit = op - pp
        if deficit > max_deficit:
            max_deficit = deficit

    final_our, final_opp = trace[-1][2], trace[-1][3]
    we_scored = start_opp - min_opp_seen
    they_scored = start_our - min_our_seen
    final_margin = final_our - final_opp

    return {
        "episode_id": eid,
        "start_prizes": start_our,
        "final_our_prize_remaining": final_our,
        "final_opp_prize_remaining": final_opp,
        "we_scored_prizes": we_scored,
        "opponent_scored_prizes": they_scored,
        "max_deficit_we_faced": max_deficit,
        "final_margin_positive_means_we_ended_behind": final_margin,
        "n_trace_rows": len(trace),
    }


def run(label, cfg):
    with open(cfg["episodes_file"], encoding="utf-8") as f:
        eps = json.load(f)
    results = []
    for e in eps:
        if e.get("type") != "EPISODE_TYPE_PUBLIC":
            continue
        eid = e["id"]
        rp = os.path.join(cfg["replay_dir"], f"episode-{eid}-replay.json")
        if not os.path.exists(rp):
            continue
        with open(rp, encoding="utf-8") as f:
            d = json.load(f)
        own_agent = next(a for a in e["agents"] if a["submissionId"] == cfg["submission_id"])
        idx = own_agent["index"]
        opp_idx = 1 - idx
        rewards = d["rewards"]
        result = "WIN" if rewards[idx] == 1 else "LOSS" if rewards[idx] == -1 else "OTHER"
        r = scan_episode(eid, idx, opp_idx, d["steps"])
        if r is None:
            continue
        r["result"] = result
        results.append(r)
    return results


def main():
    out = {}
    for label, cfg in TARGETS.items():
        rows = run(label, cfg)
        n = len(rows)
        we_scored = sum(r["we_scored_prizes"] for r in rows)
        opp_scored = sum(r["opponent_scored_prizes"] for r in rows)
        max_deficits = [r["max_deficit_we_faced"] for r in rows]
        final_margins = [r["final_margin_positive_means_we_ended_behind"] for r in rows]
        wins = [r for r in rows if r["result"] == "WIN"]
        losses = [r for r in rows if r["result"] == "LOSS"]
        behind_games_2plus = [r for r in rows if r["max_deficit_we_faced"] >= 2]
        comebacks = [r for r in behind_games_2plus if r["result"] == "WIN"]
        zero_prize_games = [r for r in rows if r["final_our_prize_remaining"] == 6 - r["we_scored_prizes"] and r["we_scored_prizes"] == 0]
        opp_zero_games = [r for r in rows if r["opponent_scored_prizes"] == 0]
        out[label] = {
            "n_games": n,
            "we_scored_prizes_total": we_scored,
            "we_scored_prizes_per_game": we_scored / n if n else None,
            "opponent_scored_prizes_total": opp_scored,
            "opponent_scored_prizes_per_game": opp_scored / n if n else None,
            "max_deficit_mean": sum(max_deficits) / n if n else None,
            "max_deficit_max": max(max_deficits) if max_deficits else None,
            "n_games_faced_2plus_deficit": len(behind_games_2plus),
            "n_comebacks_from_2plus_deficit": len(comebacks),
            "comeback_rate_from_2plus_deficit": (len(comebacks) / len(behind_games_2plus)) if behind_games_2plus else None,
            "final_margin_mean": sum(final_margins) / n if n else None,
            "n_wins_total": len(wins),
            "n_losses_total": len(losses),
            "n_games_we_scored_zero": sum(1 for r in rows if r["we_scored_prizes"] == 0),
            "n_games_opponent_scored_zero": len(opp_zero_games),
            "per_game": rows,
        }
    with open(os.path.join(OUT_DIR, "prize_economy.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    for label in out:
        o = dict(out[label])
        o.pop("per_game")
        print(label, json.dumps(o, indent=2, default=str))


if __name__ == "__main__":
    main()
