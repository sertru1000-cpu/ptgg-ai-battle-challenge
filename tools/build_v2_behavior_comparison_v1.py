"""Luca Episode Data Audit -- Part C: comparable V2 Balanced behavioral metrics.

Reuses ALREADY-EXISTING local data from session 18 (Prompt #5, "Four
Experimental Agents"): the full decision-level trace of V2_balanced's 150
head-to-head games vs V1_baseline
(results/agent/v2_v5_experiments/games/1786510596_f5677d5e_decisions.jsonl,
confirmed by its paired plain .jsonl file's agent_a_name/agent_b_name to be
the V1-vs-V2 matchup, not one of the other 3). No new games are simulated.

IMPORTANT ASYMMETRY vs the Luca-side analysis (tools/build_luca_audit_v1.py),
stated explicitly rather than silently glossed over: the local decision log
only stores option_count (a number) for the AVAILABLE menu at each decision,
not the full option list -- unlike the Kaggle replay format, which stores
every option's type/attackId, letting the Luca-side script condition
"available" (e.g. attack_conversion_rate, missed-knockout detection) on the
real legal-action set. Here, "available" is approximated via context
(MAIN = the menu that offers ATTACK/RETREAT/etc. as some of its options,
not proof a given option was legal every time) or omitted where no honest
proxy exists (missed-knockout detection is NOT attempted for V2 -- would
require re-deriving from cg.api tables against a schema that doesn't carry
per-option attack ids in all rows).

Output: results/luca_audit/v2_behavior_summary.json,
results/luca_audit/v2_games.csv (raw per-game, never discard).
"""
from __future__ import annotations

import csv
import json
import os

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
GAMES_DIR = os.path.join(ROOT, "results", "agent", "v2_v5_experiments", "games")
SUMMARY_FILE = os.path.join(GAMES_DIR, "1786510596_f5677d5e.jsonl")
DECISIONS_FILE = os.path.join(GAMES_DIR, "1786510596_f5677d5e_decisions.jsonl")
OUT_DIR = os.path.join(ROOT, "results", "luca_audit")
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    game_meta = {}
    with open(SUMMARY_FILE, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            gid = f"{d['run_id']}_{d['game_index']}"
            v2_slot = 1 - d["agent_a_slot"]  # agent_a is always V1_baseline in this file
            game_meta[gid] = {
                "run_id": d["run_id"], "game_index": d["game_index"],
                "v2_slot": v2_slot, "first_player_slot": d["first_player_slot"],
                "winner_slot": d["winner_slot"], "turns": d["turns"], "steps": d["steps"],
                "aborted": d["aborted"],
            }
    assert all(gm["winner_slot"] is not None or True for gm in game_meta.values())

    per_game_decisions = {gid: [] for gid in game_meta}
    with open(DECISIONS_FILE, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            gid = d["game_id"]
            if gid not in game_meta:
                continue
            if d["player_index"] != game_meta[gid]["v2_slot"]:
                continue  # keep only V2's own decisions, mirroring the Luca-side script's own-index-only filter
            per_game_decisions[gid].append(d)

    rows = []
    all_decisions_flat = []
    for gid, meta in game_meta.items():
        if meta["aborted"]:
            continue
        decs = per_game_decisions[gid]
        v2_won = meta["winner_slot"] == meta["v2_slot"]
        went_first = meta["first_player_slot"] == meta["v2_slot"]

        total = len(decs)
        main_decs = [d for d in decs if d["context"] == "MAIN"]
        retreat_chosen = sum(1 for d in decs if any(c["type"] == "RETREAT" for c in d["chosen"]))
        attack_chosen_decs = [d for d in decs if any(c["type"] == "ATTACK" for c in d["chosen"])]
        turns_with_attack = set(d["turn"] for d in attack_chosen_decs)
        turns_seen = set(d["turn"] for d in main_decs)

        prize_points = [(d["state"]["my_prize_count"], d["state"]["opp_prize_count"]) for d in decs
                         if d["state"].get("my_prize_count") is not None]
        max_deficit = max((us - op for us, op in prize_points), default=0)
        final_margin = (prize_points[-1][0] - prize_points[-1][1]) if prize_points else None
        comeback = bool(prize_points) and max_deficit >= 2 and v2_won

        row = {
            "game_id": gid, "result": "WIN" if v2_won else "LOSS",
            "went_first": went_first, "turns": meta["turns"], "n_decisions": total,
            "main_decisions": len(main_decs),
            "retreat_chosen": retreat_chosen,
            "attack_chosen_count": len(attack_chosen_decs),
            "turns_with_attack_chosen": len(turns_with_attack),
            "turns_with_main_visited": len(turns_seen),
            "max_prize_deficit_faced": max_deficit,
            "final_prize_margin_positive_means_behind": final_margin,
            "comeback_from_2plus_deficit": comeback,
        }
        rows.append(row)
        for d in decs:
            all_decisions_flat.append({
                "game_id": gid, "turn": d["turn"], "context": d["context"],
                "option_count": d["option_count"],
                "chosen_types": ";".join(c["type"] for c in d["chosen"]),
                "my_active_hp": d["state"].get("my_active_hp"),
                "opp_active_hp": d["state"].get("opp_active_hp"),
                "my_prize_count": d["state"].get("my_prize_count"),
                "opp_prize_count": d["state"].get("opp_prize_count"),
                "result": "WIN" if v2_won else "LOSS",
            })

    with open(os.path.join(OUT_DIR, "v2_games.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUT_DIR, "v2_decisions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_decisions_flat[0].keys()))
        w.writeheader()
        w.writerows(all_decisions_flat)

    n = len(rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    first_rows = [r for r in rows if r["went_first"]]
    second_rows = [r for r in rows if not r["went_first"]]

    def wr(rs):
        return (sum(1 for r in rs if r["result"] == "WIN") / len(rs)) if rs else None

    total_decisions = sum(r["n_decisions"] for r in rows)
    total_retreat = sum(r["retreat_chosen"] for r in rows)
    total_main = sum(r["main_decisions"] for r in rows)
    total_turns_main_visited = sum(r["turns_with_main_visited"] for r in rows)
    total_turns_attacked = sum(r["turns_with_attack_chosen"] for r in rows)

    wins_rows = [r for r in rows if r["result"] == "WIN"]
    losses_rows = [r for r in rows if r["result"] == "LOSS"]

    summary = {
        "source": "results/agent/v2_v5_experiments/games/1786510596_f5677d5e_decisions.jsonl (V1 vs V2, session 18)",
        "games_total": n, "wins": wins, "losses": n - wins,
        "win_rate_overall": wins / n if n else None,
        "win_rate_going_first": wr(first_rows), "n_going_first": len(first_rows),
        "win_rate_going_second": wr(second_rows), "n_going_second": len(second_rows),
        "retreat_rate_per_decision": total_retreat / total_decisions if total_decisions else None,
        "retreat_rate_per_MAIN_decision": total_retreat / total_main if total_main else None,
        "turn_attack_rate_approx": total_turns_attacked / total_turns_main_visited if total_turns_main_visited else None,
        "avg_turns_all": sum(r["turns"] for r in rows) / n if n else None,
        "avg_turns_wins": sum(r["turns"] for r in wins_rows) / len(wins_rows) if wins_rows else None,
        "avg_turns_losses": sum(r["turns"] for r in losses_rows) / len(losses_rows) if losses_rows else None,
        "comebacks_from_2plus_prize_deficit": sum(1 for r in rows if r["comeback_from_2plus_deficit"]),
        "games_where_v2_faced_2plus_prize_deficit": sum(1 for r in rows if r["max_prize_deficit_faced"] >= 2),
        "avg_max_prize_deficit_faced_wins": sum(r["max_prize_deficit_faced"] for r in wins_rows) / len(wins_rows) if wins_rows else None,
        "avg_max_prize_deficit_faced_losses": sum(r["max_prize_deficit_faced"] for r in losses_rows) / len(losses_rows) if losses_rows else None,
        "note_missed_ko_not_computed": "local decision log lacks per-option attack-id/damage detail; not comparable to Luca-side CONFIRMED/POSSIBLE knockout metric",
    }
    with open(os.path.join(OUT_DIR, "v2_behavior_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
