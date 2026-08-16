"""V2-vs-Luca real-ladder behavioral audit -- Part B: parse both agents through the IDENTICAL
shared pipeline (src/meta_analysis/ladder_behavior_audit.py).

Run against:
  - Luca: data/luca_audit/replays/ (already pulled, session 19), submission 55447414, 69 real
    EPISODE_TYPE_PUBLIC games (+1 validation, excluded).
  - V2 Balanced: data/v2_ladder_audit/replays/ (pulled this session), submission 55449878
    (the one of the two identical-build V2 submissions that actually has real games -- see
    tools/pull_v2_ladder_data.py docstring), 43 real EPISODE_TYPE_PUBLIC games (+1 validation,
    excluded).

Writes, per agent, to results/ladder_behavior_audit/<label>_{games,decisions,
missed_knockouts}.csv -- raw, per-decision, never discarded after aggregation.
"""
from __future__ import annotations

import csv
import json
import os

from src.meta_analysis.ladder_behavior_audit import parse_episode, find_missed_knockouts

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
OUT_DIR = os.path.join(ROOT, "results", "ladder_behavior_audit")
os.makedirs(OUT_DIR, exist_ok=True)

TARGETS = [
    {
        "label": "luca",
        "submission_id": 55447414,
        "replay_dir": os.path.join(ROOT, "data", "luca_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "luca_audit", "luca_episodes_raw.json"),
        "opponent_ratings_file": os.path.join(ROOT, "data", "luca_audit", "opponent_ratings_raw.json"),
    },
    {
        "label": "v2",
        "submission_id": 55449878,
        "replay_dir": os.path.join(ROOT, "data", "v2_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v2_ladder_audit", "v2_episodes_raw.json"),
        "opponent_ratings_file": os.path.join(ROOT, "data", "v2_ladder_audit", "opponent_ratings_raw.json"),
    },
    {
        "label": "v6",
        "submission_id": 55475115,
        "replay_dir": os.path.join(ROOT, "data", "v6_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v6_ladder_audit", "v6_episodes_raw.json"),
        "opponent_ratings_file": os.path.join(ROOT, "data", "v6_ladder_audit", "opponent_ratings_raw.json"),
    },
    {
        "label": "v7",
        "submission_id": 55478172,
        "replay_dir": os.path.join(ROOT, "data", "v7_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v7_ladder_audit", "v7_episodes_raw.json"),
        "opponent_ratings_file": os.path.join(ROOT, "data", "v7_ladder_audit", "opponent_ratings_raw.json"),
    },
    {
        "label": "v8",
        "submission_id": 55482268,
        "replay_dir": os.path.join(ROOT, "data", "v8_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v8_ladder_audit", "v8_episodes_raw.json"),
        "opponent_ratings_file": os.path.join(ROOT, "data", "v8_ladder_audit", "opponent_ratings_raw.json"),
    },
]


def flatten_decision(d, episode_id, opponent_score, result, went_first):
    threat = d.get("opp_threat") or {}
    detail = d.get("action_detail") or {}
    return {
        "episode_id": episode_id, "opponent_current_score": opponent_score,
        "result": result, "went_first": went_first,
        "decision_index": d["decision_index"], "turn": d["turn"],
        "select_context_name": d["select_context_name"], "n_options": d["n_options"],
        "category": d["category"], "action_class": d["action_class"],
        "action_card_id": detail.get("card_id"),
        "chosen_option_types": ";".join(d["chosen_option_types"]),
        "n_available_attacks": len(d["available_attack_ids"]),
        "n_chosen_attacks": len(d["chosen_attack_ids"]),
        "our_active_id": d["state_before"].get("active_id"),
        "our_active_hp": d["state_before"].get("active_hp"),
        "our_active_maxhp": d["state_before"].get("active_maxhp"),
        "our_active_prize_value": d["our_active_prize_value"],
        "our_active_damaged": d["our_active_damaged"],
        "our_bench_n": d["state_before"].get("bench_n"),
        "our_prize_n": d["state_before"].get("prize_n"),
        "retreat_available_this_decision": d["retreat_available_this_decision"],
        "bench_target_exists": d["bench_target_exists"],
        "our_active_retreat_cost": d["our_active_retreat_cost"],
        "our_active_energy_loss_if_retreated": d["our_active_energy_loss_if_retreated"],
        "bench_ready_attackers": d["bench_ready_attackers"],
        "opp_active_id": d["opp_before"].get("active_id"),
        "opp_active_hp": d["opp_before"].get("active_hp"),
        "opp_prize_n": d["opp_before"].get("prize_n"),
        "opp_active_id_after": d["opp_after"].get("active_id"),
        "opp_active_hp_after": d["opp_after"].get("active_hp"),
        "opp_prize_n_after": d["opp_after"].get("prize_n"),
        "opp_lethal_now": threat.get("lethal_now"),
        "opp_lethal_with_one_more_energy": threat.get("lethal_with_one_more_energy"),
        "opp_best_attack_name": threat.get("best_attack_name"),
        "opp_best_attack_damage": threat.get("best_attack_damage"),
        "our_active_changed_since_prev_own_decision": d["our_active_changed_since_prev_own_decision"],
    }


def run_target(target):
    label = target["label"]
    with open(target["episodes_file"], encoding="utf-8") as f:
        eps_meta = json.load(f)
    with open(target["opponent_ratings_file"], encoding="utf-8") as f:
        opp_ratings = {r["team_id"]: r for r in json.load(f)}

    games = []
    all_decisions = []
    all_missed_ko = []
    n_validation_excluded = 0
    for e in eps_meta:
        if e.get("type") == "EPISODE_TYPE_VALIDATION":
            n_validation_excluded += 1
            continue
        eid = e["id"]
        parsed = parse_episode(eid, e, target["replay_dir"], target["submission_id"], label)
        if parsed is None:
            continue
        mko = find_missed_knockouts(parsed["decisions"])
        all_missed_ko.extend(mko)
        decs = parsed["decisions"]
        opp_rating_info = opp_ratings.get(parsed["opponent_team_id"], {})
        opp_score = opp_rating_info.get("current_public_score")

        prize_points = [(d["state_before"]["prize_n"], d["opp_before"]["prize_n"]) for d in decs if d["state_before"].get("prize_n") is not None]
        max_deficit = max((us - op for us, op in prize_points), default=0)
        final_margin = (prize_points[-1][0] - prize_points[-1][1]) if prize_points else None
        comeback = bool(prize_points) and max_deficit >= 2 and parsed["result"] == "WIN"

        retreat_avail_decisions = [d for d in decs if d["retreat_available_this_decision"]]
        retreat_chosen_decisions = [d for d in decs if "RETREAT" in d["chosen_option_types"]]
        attack_avail_decisions = [d for d in decs if d["available_attack_ids"]]
        attack_chosen = sum(1 for d in attack_avail_decisions if d["chosen_attack_ids"])
        turns_with_attack_avail = set(d["turn"] for d in attack_avail_decisions)
        turns_with_attack_chosen = set(d["turn"] for d in decs if d["chosen_attack_ids"])
        turn_attack_rate = (len(turns_with_attack_avail & turns_with_attack_chosen) / len(turns_with_attack_avail)) if turns_with_attack_avail else None

        action_counts = {}
        for d in decs:
            ac = d["action_class"]
            if ac:
                action_counts[ac] = action_counts.get(ac, 0) + 1

        row = {
            "episode_id": eid, "label": label,
            "create_time": parsed["create_time"],
            "opponent_team_id": parsed["opponent_team_id"],
            "opponent_team_name": parsed["opponent_team_name"],
            "opponent_current_score": opp_score,
            "result": parsed["result"],
            "went_first": parsed["went_first"],
            "n_turns": parsed["n_turns"],
            "n_steps": parsed["n_steps"],
            "n_decisions": parsed["n_decisions"],
            "deck_own_hash": parsed["deck_own_hash"],
            "deck_own_archetype": parsed["deck_own_archetype"],
            "deck_opp_hash": parsed["deck_opp_hash"],
            "deck_opp_archetype": parsed["deck_opp_archetype"],
            "retreat_available_decisions": len(retreat_avail_decisions),
            "retreat_chosen": len(retreat_chosen_decisions),
            "attack_available_decisions": len(attack_avail_decisions),
            "attack_chosen_when_available": attack_chosen,
            "turns_with_attack_available": len(turns_with_attack_avail),
            "turn_attack_rate": turn_attack_rate,
            "missed_ko_confirmed": sum(1 for m in mko if m["evidence_level"] == "CONFIRMED"),
            "missed_ko_possible": sum(1 for m in mko if m["evidence_level"] == "POSSIBLE"),
            "max_prize_deficit_faced": max_deficit,
            "final_prize_margin_positive_means_behind": final_margin,
            "comeback_from_2plus_deficit": comeback,
            **{f"action_count_{k}": v for k, v in action_counts.items()},
        }
        games.append(row)
        for d in decs:
            all_decisions.append(flatten_decision(d, eid, opp_score, parsed["result"], parsed["went_first"]))

    action_class_keys = sorted(set(k for g in games for k in g if k.startswith("action_count_")))
    fieldnames = list(games[0].keys()) if games else []
    for k in action_class_keys:
        if k not in fieldnames:
            fieldnames.append(k)
    with open(os.path.join(OUT_DIR, f"{label}_games.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for g in games:
            w.writerow({k: g.get(k, 0 if k.startswith("action_count_") else "") for k in fieldnames})

    with open(os.path.join(OUT_DIR, f"{label}_decisions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_decisions[0].keys()))
        w.writeheader()
        w.writerows(all_decisions)

    with open(os.path.join(OUT_DIR, f"{label}_missed_knockouts.csv"), "w", newline="", encoding="utf-8") as f:
        if all_missed_ko:
            w = csv.DictWriter(f, fieldnames=list(all_missed_ko[0].keys()))
            w.writeheader()
            w.writerows(all_missed_ko)
        else:
            f.write("no_missed_knockouts_found\n")

    print(f"[{label}] games={len(games)} decisions={len(all_decisions)} "
          f"missed_ko={len(all_missed_ko)} validation_excluded={n_validation_excluded}")
    return games, all_decisions


def main():
    for target in TARGETS:
        run_target(target)


if __name__ == "__main__":
    main()
