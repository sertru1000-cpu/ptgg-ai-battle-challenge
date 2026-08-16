"""V6 vs V2 real-ladder audit -- prize economy from full replay traces.

The existing per-decision prize columns in results/ladder_behavior_audit/*_decisions.csv
(state_before.prize_n / opp_before.prize_n) are sampled ONLY at rows where OUR agent was
asked to act (SelectContext ACTIVE for our index) -- see
src/meta_analysis/ladder_behavior_audit.py::parse_episode's `active_rows` filter. That
undercounts KOs/prize swings that happen on the opponent's turn with no intervening
decision of ours (e.g. an opponent finishing several prizes in one turn right before our
next decision, or right before game end) -- confirmed directly on a sample V6 loss
(episode 92549421: last captured our-decision prize state was our=5/opp=1, but the game's
actual reward says LOSS, meaning further prizes were taken after our last recorded
decision with no observation of it in the decision stream).

This script instead scans the FULL replay `steps` array (every environment tick, both
players' observation channels) per episode and takes the min-ever-seen prize count for
each side across the whole game -- prize counts are public information (not
hidden/opponent-only), so either channel's `current.players[i].prize` is authoritative
whenever populated, regardless of whose decision that row was.

Read-only. Writes results/v6_v2_audit/prize_economy.json.
"""
from __future__ import annotations

import json
import os

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
OUT_DIR = os.path.join(ROOT, "results", "v6_v2_audit")
os.makedirs(OUT_DIR, exist_ok=True)

TARGETS = {
    "v2": {
        "submission_id": 55449878,
        "replay_dir": os.path.join(ROOT, "data", "v2_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v2_ladder_audit", "v2_episodes_raw.json"),
    },
    "v6": {
        "submission_id": 55475115,
        "replay_dir": os.path.join(ROOT, "data", "v6_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v6_ladder_audit", "v6_episodes_raw.json"),
    },
}


def scan_episode(eid, own_idx, opp_idx, steps):
    """Returns per-turn (our_prize, opp_prize) trace using every row of both channels,
    plus derived summary stats. Prize counts only ever decrease; we keep the running
    min-seen-so-far per side as the authoritative "prizes remaining" trace, and derive
    max deficit / final margin / KOs scored from that monotonic trace directly (immune to
    which side's decision row happened to be sampled)."""
    trace = []  # (row_index, turn, our_prize, opp_prize)
    for row_i, row in enumerate(steps):
        for p in (own_idx, opp_idx):
            cur = row[p]["observation"].get("current")
            if not cur:
                continue
            pl_own = cur["players"][own_idx]
            pl_opp = cur["players"][opp_idx]
            our_prize = len(pl_own.get("prize") or [])
            opp_prize = len(pl_opp.get("prize") or [])
            turn = cur.get("turn")
            if our_prize == 0 and opp_prize == 0 and turn in (None, 0) and not trace:
                # pre-setup row (prizes not laid out yet) -- skip until first nonzero
                if pl_own.get("deckCount") in (None, 0):
                    continue
            trace.append((row_i, turn, our_prize, opp_prize))

    # keep only rows where prizes are actually laid out (six-prize start observed at least
    # once); drop the pre-setup zero rows at the very front.
    first_real = next((i for i, t in enumerate(trace) if t[2] > 0 or t[3] > 0), None)
    if first_real is None:
        return None
    trace = trace[first_real:]
    if not trace:
        return None

    start_our, start_opp = trace[0][2], trace[0][3]
    min_our_seen, min_opp_seen = start_our, start_opp
    max_deficit = 0  # our_prize - opp_prize, positive = we are BEHIND (more prizes left to lose... )
    # convention: "prizes remaining" LOWER is BETTER (closer to winning). Deficit = our_remaining - opp_remaining;
    # positive means we have MORE prizes left than opponent = we are BEHIND.
    for _, _, op, pp in trace:
        min_our_seen = min(min_our_seen, op)
        min_opp_seen = min(min_opp_seen, pp)
        deficit = op - pp
        if deficit > max_deficit:
            max_deficit = deficit

    final_our, final_opp = trace[-1][2], trace[-1][3]
    we_scored = start_opp - min_opp_seen  # prizes we took off the opponent
    they_scored = start_our - min_our_seen  # prizes opponent took off us
    final_margin = final_our - final_opp  # positive = we ended up with more prizes remaining = behind/lost

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
        ahead_at_end_wins = sum(1 for r in wins if r["final_margin_positive_means_we_ended_behind"] < 0)
        behind_games_2plus = [r for r in rows if r["max_deficit_we_faced"] >= 2]
        comebacks = [r for r in behind_games_2plus if r["result"] == "WIN"]
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
            "n_wins_ending_strictly_ahead_on_prizes": ahead_at_end_wins,
            "n_wins_total": len(wins),
            "n_losses_total": len(losses),
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
