"""Plan-vs-fallback audit for Phantom Dive's main_option_proc (Part 5C/Part 6).

Source-level finding (confirmed by reading src/agents/dragapult_policy_v6.py /
dragapult_policy_v2plus.py directly, both byte-identical outside the two marked V6
fixes): main_option_proc's `self.plan_b` is captured ONLY once, at loop iteration
i==0 (the opponent's Active Pokemon), via:

    if i == 0 and self.can_main_attack:      # V6 fix #2 gate
        active_damage = 0                     # V6: always 0 for Phantom Dive
    else:
        active_damage = 0 if no_damage_dex(...) else damage   # V2: damage constant (200)
    if pokemon.hp <= active_damage:
        base_prize_count += prize_count(pokemon, True)
    ...
    if remain_prize <= base_prize_count:
        max_score = 50000          # SHORT-CIRCUITS -- skips the indices/combo loop below,
    else:                          # leaving `ci` at its fresh-initialized `[]`
        for indices in counter_indices: ...   # genuine bench-combo search, sets `ci`
    if plan_score < max_score:
        plan_score = max_score; self.plan_a.attack = i; self.plan_a.counter = ci
    if i == 0:
        self.plan_b.attack = self.plan_a.attack
        self.plan_b.counter = self.plan_a.counter   # <-- snapshotted HERE, i==0 only

V2 (broken): active_damage = 200 (generic constant) at i==0. If the opponent's
Active has hp<=200 (the common case), base_prize_count = prize_count(op_active)
(1/2/3). The shortcut `remain_prize <= base_prize_count` fires whenever OUR OWN
remaining prize count is already down to that Pokemon's prize value or below --
i.e. almost by definition, ENDGAME (we are 1-3 prizes from winning). When it
fires, self.plan_b.counter is left `[]` (empty) for the ENTIRE Phantom Dive
attack, forcing every one of the up to 6 DAMAGE_COUNTER_ANY sub-decisions onto
the per-counter fallback heuristic (fix #1's target) instead of a real bench
combo plan.

V6 (fixed): active_damage = 0 unconditionally at i==0 when Phantom Dive is
offered. `pokemon.hp <= 0` is never true for a live Active, so base_prize_count
stays 0 and `remain_prize <= 0` is never true (remain_prize>=1 in any ongoing
game) -- the shortcut can structurally never fire. self.plan_b.counter is
therefore ALWAYS computed via the genuine bench-only combo search (indices
excluding i=0) for every single Phantom Dive attack, regardless of our own
remaining prize count.

This script empirically measures, from real replay data, how often V2's
shortcut CONDITION was actually met at real Phantom Dive attack decisions (a
direct, mechanical proxy for "plan_b.counter was empty"), and confirms V6's
predicted 0%-empty rate is consistent with its replay behavior (no
instrumentation of the live object -- this is a source-level deduction,
verified against real per-attack remain_prize/active_hp/active_prize inputs).

Read-only. Writes results/v6_v2_audit/plan_vs_fallback.json.
"""
from __future__ import annotations

import json
import os

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()
import cg.api as api  # noqa: E402

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
OUT_DIR = os.path.join(ROOT, "results", "v6_v2_audit")
os.makedirs(OUT_DIR, exist_ok=True)

CARDS = {c.cardId: c for c in api.all_card_data()}

TARGETS = {
    "v2": {
        "submission_id": 55449878,
        "replay_dir": os.path.join(ROOT, "data", "v2_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v2_ladder_audit", "v2_episodes_raw.json"),
        "active_damage_const": 200,  # V2's generic `damage` constant fed into main_option_proc for Phantom Dive
    },
    "v6": {
        "submission_id": 55475115,
        "replay_dir": os.path.join(ROOT, "data", "v6_ladder_audit", "replays"),
        "episodes_file": os.path.join(ROOT, "data", "v6_ladder_audit", "v6_episodes_raw.json"),
        "active_damage_const": 0,  # V6 fix #2: always 0 for Phantom Dive
    },
}


def prize_value(card_id):
    cd = CARDS.get(card_id)
    if cd is None or cd.cardType != 0:
        return None
    return 3 if cd.megaEx else 2 if cd.ex else 1


def find_pd_main_decisions(eid, idx, opp_idx, steps):
    """Every MAIN-context select where Phantom Dive (attackId=154) was among the
    offered options (not just chosen) AND was the one actually chosen -- these are
    exactly the points where main_option_proc runs with can_main_attack=True."""
    out = []
    n = len(steps)
    k = 0
    while k < n:
        prev_sel = steps[k - 1][idx]["observation"].get("select") if k - 1 >= 0 else None
        act = steps[k][idx]["action"]
        if prev_sel and isinstance(act, list) and prev_sel.get("context") == 0:
            opts = prev_sel.get("option", [])
            chosen = [opts[c] for c in act if isinstance(c, int) and 0 <= c < len(opts) and isinstance(opts[c], dict)]
            is_pd = any(o.get("type") == 13 and o.get("attackId") == 154 for o in chosen)
            if is_pd:
                pre_cur = steps[k][idx]["observation"].get("current")
                if pre_cur:
                    my_state = pre_cur["players"][idx]
                    op_state = pre_cur["players"][opp_idx]
                    op_active_list = op_state.get("active") or []
                    op_active = op_active_list[0] if op_active_list and op_active_list[0] else None
                    out.append({
                        "episode_id": eid, "turn": pre_cur.get("turn"),
                        "our_remain_prize": len(my_state.get("prize") or []),
                        "op_active_id": op_active.get("id") if op_active else None,
                        "op_active_hp": op_active.get("hp") if op_active else None,
                        "op_active_prize_value": prize_value(op_active.get("id")) if op_active else None,
                    })
            # advance past this attack's sub-selects the same way the forensic script does
            j = k + 1
            counters_placed = 0
            while j < n and counters_placed < 6:
                sel_j = steps[j - 1][idx]["observation"].get("select")
                if not sel_j or sel_j.get("context") not in (13, 14):
                    break
                act_j = steps[j][idx]["action"]
                if not isinstance(act_j, list) or not act_j:
                    break
                counters_placed += 1
                j += 1
            if is_pd:
                k = j
                continue
        k += 1
    return out


def run(label, cfg):
    with open(cfg["episodes_file"], encoding="utf-8") as f:
        eps = json.load(f)
    events = []
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
        events.extend(find_pd_main_decisions(eid, idx, opp_idx, d["steps"]))

    active_damage = cfg["active_damage_const"]
    for ev in events:
        hp = ev["op_active_hp"]
        prize = ev["op_active_prize_value"]
        active_genuinely_dead = (hp is not None and hp <= 0)
        active_dies_under_false_premise = (hp is not None and hp <= active_damage)
        # "falsely" treated as dead = the i==0 shortcut's false premise fires on a target
        # that is NOT actually already at 0 HP -- this is the real V2 bug signature.
        # (hp==0 cases are legitimately already-dead and would correctly satisfy either
        # V2's or V6's condition -- not evidence of the bug, just a live game state.)
        falsely_treated_as_dead = active_dies_under_false_premise and not active_genuinely_dead
        base_prize_count = (prize or 0) if active_dies_under_false_premise else 0
        ev["op_active_genuinely_dead_at_decision"] = active_genuinely_dead
        ev["active_treated_as_dead_by_i0_iteration"] = active_dies_under_false_premise
        ev["falsely_treated_as_dead_while_still_alive"] = falsely_treated_as_dead
        ev["shortcut_condition_met_plan_b_empty"] = (
            active_dies_under_false_premise and ev["our_remain_prize"] <= base_prize_count
        )
        ev["shortcut_via_false_premise_while_alive"] = (
            falsely_treated_as_dead and ev["our_remain_prize"] <= base_prize_count
        )

    n = len(events)
    n_empty = sum(1 for e in events if e["shortcut_condition_met_plan_b_empty"])
    n_empty_false_premise = sum(1 for e in events if e["shortcut_via_false_premise_while_alive"])
    n_active_treated_dead = sum(1 for e in events if e["active_treated_as_dead_by_i0_iteration"])
    n_falsely_treated_dead = sum(1 for e in events if e["falsely_treated_as_dead_while_still_alive"])
    n_genuinely_dead = sum(1 for e in events if e["op_active_genuinely_dead_at_decision"])
    return {
        "label": label, "n_phantom_dive_main_decisions": n,
        "n_op_active_genuinely_dead_at_decision_time": n_genuinely_dead,
        "n_events_where_plan_b_counter_empty": n_empty,
        "pct_plan_b_empty": (n_empty / n) if n else None,
        "n_events_where_plan_b_empty_via_false_premise_while_alive": n_empty_false_premise,
        "pct_plan_b_empty_via_false_premise_while_alive": (n_empty_false_premise / n) if n else None,
        "n_events_where_active_falsely_treated_as_dead_while_alive": n_falsely_treated_dead,
        "pct_active_falsely_treated_as_dead_while_alive": (n_falsely_treated_dead / n) if n else None,
        "events": events,
    }


def main():
    out = {}
    for label, cfg in TARGETS.items():
        out[label] = run(label, cfg)
        summary = {k: v for k, v in out[label].items() if k != "events"}
        print(label, json.dumps(summary, indent=2, default=str))
    with open(os.path.join(OUT_DIR, "plan_vs_fallback.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
