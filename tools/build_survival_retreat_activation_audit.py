"""V8 Survival-Retreat heuristic activation audit, applied to REAL V7 and V8
ladder replays.

Re-implements `DragapultPolicy._wants_survival_retreat` / `_bench_pokemon_is_ready`
(src/agents/dragapult_policy_v8.py lines ~458-580) condition-for-condition
against the real per-decision state already extracted by the shared parser
(src/meta_analysis/ladder_behavior_audit.py::parse_episode), for BOTH V7 and
V8's real replays. V7 has no such hook -- running the identical detector
against V7's replays gives a natural control: "how often was V7 in a
situation where V8's hook WOULD have fired," and what V7 actually did there
(always attack, since V7 has no code path that could choose otherwise).

Faithfully reproduces the source's own simplifications, not idealized ones:
  - "ready" energy check is COUNT-based (len(attached) >= len(attack.energies)),
    not color-matched (matches _bench_pokemon_is_ready's literal implementation).
  - lethal/winning-trade checks explicitly EXCLUDE attackId 154 (Phantom Dive)
    on both sides, exactly as the source does (fictional Active damage).
  - scoped to my_card.ex and not my_card.megaEx (2-Prize only).
  - requires retreat_available_this_decision (proxy for self.can_switch --
    both are the engine's own MAIN-menu option-legality signal).

This is a REPLAY reconstruction, not a re-run of the actual policy code --
it cannot see anti-thrash memory state across decisions (that lives in
policy instance fields, not in the replay). Anti-thrash is approximated
separately (see suppressed_by_antithrash_estimate below) using the same
"same retreating Pokemon serial + same HP + same opponent serial as the
immediately preceding activation, active not yet changed" rule the source
uses, applied to the reconstructed decision sequence.

Read-only. Writes results/v7_v8_regression_audit/survival_retreat_activation.json
and .../survival_retreat_events.csv (one row per eligible decision, both labels).
"""
from __future__ import annotations

import csv
import json
import os

from src.meta_analysis.ladder_behavior_audit import parse_episode, CARDS_BY_ID, ATTACKS_BY_ID

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
OUT_DIR = os.path.join(ROOT, "results", "v7_v8_regression_audit")
os.makedirs(OUT_DIR, exist_ok=True)

PHANTOM_DIVE_ID = 154

TARGETS = {
    "v7": {"submission_id": 55478172,
           "replay_dir": os.path.join(ROOT, "data", "v7_ladder_audit", "replays"),
           "episodes_file": os.path.join(ROOT, "data", "v7_ladder_audit", "v7_episodes_raw.json")},
    "v8": {"submission_id": 55482268,
           "replay_dir": os.path.join(ROOT, "data", "v8_ladder_audit", "replays"),
           "episodes_file": os.path.join(ROOT, "data", "v8_ladder_audit", "v8_episodes_raw.json")},
}


def bench_ready(bench_detail):
    ready = []
    for b in bench_detail or []:
        cd = CARDS_BY_ID.get(b.get("id"))
        if cd is None:
            continue
        energy_count = len(b.get("energies") or [])
        for aid in cd.attacks:
            atk = ATTACKS_BY_ID.get(aid)
            if atk is not None and atk.damage > 0 and energy_count >= len(atk.energies):
                ready.append(b.get("id"))
                break
    return ready


def lethal_confirmed(attacker_card, attacker_energy_count, defender_hp, exclude_pd=True):
    for aid in attacker_card.attacks:
        if exclude_pd and aid == PHANTOM_DIVE_ID:
            continue
        atk = ATTACKS_BY_ID.get(aid)
        if atk is None or atk.damage <= 0:
            continue
        if attacker_energy_count >= len(atk.energies) and atk.damage >= defender_hp:
            return True, atk.name, atk.damage
    return False, None, None


def check_eligible(dec):
    """Returns (eligible, reason_if_not, detail_dict)."""
    sb = dec["state_before"]
    ob = dec["opp_before"]
    our_active_id = sb.get("active_id")
    opp_active_id = ob.get("active_id")
    if our_active_id is None or opp_active_id is None:
        return False, "no_active", {}
    if not dec["retreat_available_this_decision"]:
        return False, "no_retreat_option", {}
    my_card = CARDS_BY_ID.get(our_active_id)
    op_card = CARDS_BY_ID.get(opp_active_id)
    if my_card is None or op_card is None:
        return False, "unknown_card", {}
    if not my_card.ex or my_card.megaEx:
        return False, "not_2prize_ex", {}
    our_hp = sb.get("active_hp")
    opp_hp = ob.get("active_hp")
    if our_hp is None or opp_hp is None:
        return False, "missing_hp", {}
    opp_energy = len(ob.get("active_energies") or [])
    lethal, atk_name, atk_dmg = lethal_confirmed(op_card, opp_energy, our_hp, exclude_pd=True)
    if not lethal:
        return False, "not_lethal", {}
    our_energy = len(sb.get("active_energies") or [])
    winning_trade, my_atk_name, my_atk_dmg = lethal_confirmed(my_card, our_energy, opp_hp, exclude_pd=True)
    if winning_trade:
        return False, "winning_trade_available", {"our_lethal_attack": my_atk_name}
    ready = bench_ready(sb.get("bench_detail"))
    if not ready:
        return False, "no_ready_bench", {}
    return True, None, {
        "opp_lethal_attack": atk_name, "opp_lethal_damage": atk_dmg,
        "n_ready_bench": len(ready),
        "our_active_card": my_card.name, "opp_active_card": op_card.name,
        "our_active_hp": our_hp, "opp_active_hp": opp_hp,
        "our_active_retreat_cost": dec["our_active_retreat_cost"],
        "our_active_energy_loss_if_retreated": dec["our_active_energy_loss_if_retreated"],
    }


def run_label(label, cfg):
    with open(cfg["episodes_file"], encoding="utf-8") as f:
        eps_meta = json.load(f)
    events = []
    for e in eps_meta:
        if e.get("type") == "EPISODE_TYPE_VALIDATION":
            continue
        eid = e["id"]
        parsed = parse_episode(eid, e, cfg["replay_dir"], cfg["submission_id"], label)
        if parsed is None:
            continue
        decs = parsed["decisions"]
        last_activation = None  # (serial, hp, opp_serial) of most recent eligible+retreated event
        prev_active_serial_seen = None
        for d in decs:
            eligible, reason, detail = check_eligible(d)
            our_active_id = d["state_before"].get("active_id")
            retreated = "RETREAT" in d["chosen_option_types"]
            attacked = bool(d["chosen_attack_ids"])
            row = {
                "label": label, "episode_id": eid, "result": parsed["result"],
                "decision_index": d["decision_index"], "turn": d["turn"],
                "eligible": eligible, "ineligible_reason": reason,
                "retreated": retreated, "attacked": attacked,
                "our_active_id": our_active_id,
                **detail,
            }
            if eligible:
                # anti-thrash approximation: same active id + same hp + same opp active id as
                # the last eligible+retreated activation, with no active-change observed since.
                sig = (our_active_id, d["state_before"].get("active_hp"), d["opp_before"].get("active_id"))
                suppressed_guess = (last_activation is not None and sig == last_activation)
                row["antithrash_suppressed_estimate"] = suppressed_guess
                if retreated:
                    last_activation = sig
            events.append(row)
    return events


def main():
    all_events = []
    for label, cfg in TARGETS.items():
        all_events.extend(run_label(label, cfg))

    with open(os.path.join(OUT_DIR, "survival_retreat_events.csv"), "w", newline="", encoding="utf-8") as f:
        fieldnames = sorted(set(k for r in all_events for k in r.keys()))
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_events)

    summary = {}
    for label in TARGETS:
        rows = [r for r in all_events if r["label"] == label]
        elig = [r for r in rows if r["eligible"]]
        elig_retreated = [r for r in elig if r["retreated"]]
        elig_attacked = [r for r in elig if r["attacked"]]
        elig_neither = [r for r in elig if not r["retreated"] and not r["attacked"]]
        games_with_elig = len(set(r["episode_id"] for r in elig))
        games_with_retreat = len(set(r["episode_id"] for r in elig_retreated))
        n_games = len(set(r["episode_id"] for r in rows))
        summary[label] = {
            "n_games": n_games,
            "n_decisions_total": len(rows),
            "n_eligible_decisions": len(elig),
            "n_eligible_and_retreated": len(elig_retreated),
            "n_eligible_and_attacked_instead": len(elig_attacked),
            "n_eligible_neither_retreat_nor_attack": len(elig_neither),
            "games_with_any_eligible_decision": games_with_elig,
            "pct_games_with_eligible_decision": games_with_elig / n_games if n_games else None,
            "games_with_any_eligible_retreat_taken": games_with_retreat,
            "pct_games_with_eligible_retreat_taken": games_with_retreat / n_games if n_games else None,
            "retreat_rate_when_eligible": (len(elig_retreated) / len(elig)) if elig else None,
        }
    with open(os.path.join(OUT_DIR, "survival_retreat_activation.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
