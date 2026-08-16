"""Phantom Dive forensic audit -- V6 real Kaggle ladder games.

Byte-for-byte the same methodology as tools/build_phantom_dive_forensic.py
(V2's baseline: 149 attacks, 63 opportunities, 33 converted, 30 missed, 52.4%
conversion), retargeted at V6's real ladder data so the two are directly
apples-to-apples comparable per the V6-vs-V2 real-ladder audit instructions.
Only the SUBMISSION id and the input/output paths differ; every immunity
rule, allocation-optimality search, and classification threshold is
identical to the V2 script (V6 changes DAMAGE_COUNTER_ANY fallback scoring
and the i==0 active-damage contamination inside dragapult_policy_v6.py --
none of that affects what this script measures, which is real bench-target
HP/prize/immunity state and V6's actual observed counter placements from
the replay, not V6's internal scoring).

Reads data/v6_ladder_audit/{v6_episodes_raw.json,replays/}. Writes
results/phantom_dive_forensic_v6/{events,missed_ko_examples}.csv and
phantom_dive_summary.json.
Read-only against Kaggle and against V6 -- no agent/weight/deck changes.
"""
from __future__ import annotations

import csv
import itertools
import json
import os

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()
import cg.api as api  # noqa: E402

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
REPLAY_DIR = os.path.join(ROOT, "data", "v6_ladder_audit", "replays")
EPMETA_FILE = os.path.join(ROOT, "data", "v6_ladder_audit", "v6_episodes_raw.json")
V6_SUB = 55475115
OUT_DIR = os.path.join(ROOT, "results", "phantom_dive_forensic_v6")
os.makedirs(OUT_DIR, exist_ok=True)

CARDS = {c.cardId: c for c in api.all_card_data()}
DRAGAPULT_EX_ID = 121
ATTACKER = CARDS[DRAGAPULT_EX_ID]
assert ATTACKER.ex and ATTACKER.tera and not ATTACKER.basic and not ATTACKER.skills, \
    "Dragapult ex properties changed -- immunity logic below assumes ex=True,tera=True,basic=False,skills=[]"

SELF_IMMUNE_VS_EX_OR_TERA_ATTACKER = {345, 330, 207, 28, 362}  # Crustle, Sylveon, Milotic ex, Poltchageist, Misty's Magikarp
TEAM_BENCH_SHIELD_CARDS = {74}  # Rabsca "Spherical Shield"
BATTLE_CAGE_STADIUM_ID = 1264
NEUTRALIZATION_ZONE_STADIUM_ID = 1247
SPECIAL_ENERGY_CARD_TYPE = 6


def prize_value(card_id):
    cd = CARDS.get(card_id)
    if cd is None or cd.cardType != 0:
        return None
    return 3 if cd.megaEx else 2 if cd.ex else 1


def has_rule_box(card_id):
    cd = CARDS.get(card_id)
    return bool(cd and (cd.ex or cd.megaEx))


def is_immune(target_card_id, opp_all_board_card_ids, stadium_ids):
    if target_card_id in SELF_IMMUNE_VS_EX_OR_TERA_ATTACKER:
        return True, "self-ability (ex/tera-attacker immunity)"
    if TEAM_BENCH_SHIELD_CARDS & opp_all_board_card_ids:
        return True, "Rabsca team-wide bench shield in play"
    if BATTLE_CAGE_STADIUM_ID in stadium_ids:
        return True, "Battle Cage stadium blocks attack-effect damage counters to bench"
    if NEUTRALIZATION_ZONE_STADIUM_ID in stadium_ids and not has_rule_box(target_card_id):
        return True, "Neutralization Zone blocks ex-attacker damage to non-rule-box Pokemon"
    return False, None


def optimal_allocation(targets, counters=6, per_counter=10):
    eligible = [t for t in targets if not t["immune"]]
    if not eligible:
        return 0, [], {}, []
    n = len(eligible)
    best_prize = -1
    best_results = []
    for alloc in itertools.product(range(counters + 1), repeat=n):
        if sum(alloc) != counters:
            continue
        kos = []
        prize = 0
        for t, c in zip(eligible, alloc):
            if c * per_counter >= t["hp"]:
                kos.append(t["slot"])
                prize += t["prize"] or 0
        if prize > best_prize:
            best_prize = prize
            best_results = [(dict(zip((t["slot"] for t in eligible), alloc)), tuple(sorted(kos)))]
        elif prize == best_prize and prize > 0:
            key = tuple(sorted(kos))
            if not any(r[1] == key for r in best_results):
                best_results.append((dict(zip((t["slot"] for t in eligible), alloc)), key))
    if best_prize <= 0:
        return 0, [], {}, []
    best_kills = list(best_results[0][1])
    return best_prize, best_kills, best_results[0][0], best_results


def bench_snapshot(cur, opp_idx):
    if not cur:
        return None
    opp = cur["players"][opp_idx]
    bench = [b for b in (opp.get("bench") or [])]
    return bench


def find_phantom_dive_events(eid, idx, opp_idx, steps):
    events = []
    n = len(steps)
    k = 0
    while k < n:
        prev_sel = steps[k - 1][idx]["observation"].get("select") if k - 1 >= 0 else None
        act = steps[k][idx]["action"]
        if prev_sel and isinstance(act, list) and prev_sel.get("context") == 0:
            opts = prev_sel.get("option", [])
            chosen = [opts[c] for c in act if isinstance(c, int) and 0 <= c < len(opts) and isinstance(opts[c], dict)]
            is_phantom_dive = any(o.get("type") == 13 and o.get("attackId") == 154 for o in chosen)
            if is_phantom_dive:
                pre_cur = steps[k][idx]["observation"].get("current")
                pre_bench = bench_snapshot(pre_cur, opp_idx) or []
                turn = pre_cur.get("turn") if pre_cur else None
                stadium_ids = {s.get("id") for s in (pre_cur.get("stadium") or []) if s} if pre_cur else set()
                opp_all_ids = set()
                if pre_cur:
                    opp_p = pre_cur["players"][opp_idx]
                    if opp_p.get("active"):
                        opp_all_ids |= {a.get("id") for a in opp_p["active"] if a}
                    opp_all_ids |= {b.get("id") for b in (opp_p.get("bench") or []) if b}

                pre_targets = []
                for slot_i, b in enumerate(pre_bench):
                    if not b:
                        continue
                    cid = b.get("id")
                    hp = b.get("hp")
                    serial = b.get("serial")
                    immune, why = is_immune(cid, opp_all_ids, stadium_ids)
                    pre_targets.append({
                        "slot": slot_i, "serial": serial, "card_id": cid,
                        "card_name": CARDS[cid].name if cid in CARDS else f"UNKNOWN({cid})",
                        "hp": hp, "maxhp": b.get("maxHp"),
                        "prize": prize_value(cid), "immune": immune, "immune_reason": why,
                    })

                placements = []
                j = k + 1
                counters_placed = 0
                live_bench_by_serial = {t["serial"]: dict(t) for t in pre_targets}
                while j < n and counters_placed < 6:
                    sel_j = steps[j - 1][idx]["observation"].get("select")
                    if not sel_j or sel_j.get("context") not in (13, 14):
                        break
                    act_j = steps[j][idx]["action"]
                    opts_j = sel_j.get("option", [])
                    chosen_j = [opts_j[c] for c in act_j if isinstance(c, int) and 0 <= c < len(opts_j) and isinstance(opts_j[c], dict)] if isinstance(act_j, list) else []
                    if not chosen_j:
                        break
                    o = chosen_j[0]
                    live_bench_now = bench_snapshot(steps[j - 1][idx]["observation"].get("current"), opp_idx) or []
                    tgt_idx = o.get("index")
                    tgt = live_bench_now[tgt_idx] if tgt_idx is not None and 0 <= tgt_idx < len(live_bench_now) and live_bench_now[tgt_idx] else None
                    serial = tgt.get("serial") if tgt else None
                    placements.append(serial)
                    counters_placed += 1
                    j += 1

                counts_by_serial = {}
                for s in placements:
                    if s is not None:
                        counts_by_serial[s] = counts_by_serial.get(s, 0) + 1
                actual_kos = []
                actual_prize = 0
                for t in pre_targets:
                    c = counts_by_serial.get(t["serial"], 0)
                    if c * 10 >= t["hp"] and t["hp"] > 0:
                        actual_kos.append(t["slot"])
                        actual_prize += t["prize"] or 0

                best_prize, best_kills, best_alloc_by_slot, all_max = optimal_allocation(pre_targets)

                events.append({
                    "episode_id": eid, "turn": turn, "decision_step": k,
                    "pre_targets": pre_targets,
                    "counters_observed": counters_placed,
                    "actual_counts_by_slot": {t["slot"]: counts_by_serial.get(t["serial"], 0) for t in pre_targets},
                    "actual_kos_slots": actual_kos,
                    "actual_prize": actual_prize,
                    "best_prize": best_prize,
                    "best_kos_slots": best_kills,
                    "best_alloc_by_slot": best_alloc_by_slot,
                    "n_max_equivalent_allocations": len(all_max),
                })
                k = j
                continue
        k += 1
    return events


def main():
    epmeta = json.load(open(EPMETA_FILE, encoding="utf-8"))
    all_events = []
    for e in epmeta:
        if e.get("type") != "EPISODE_TYPE_PUBLIC":
            continue
        eid = e["id"]
        rp = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
        if not os.path.exists(rp):
            continue
        own_agent = next(a for a in e["agents"] if a["submissionId"] == V6_SUB)
        idx = own_agent["index"]
        opp_idx = 1 - idx
        d = json.load(open(rp, encoding="utf-8"))
        steps = d["steps"]
        rewards = d["rewards"]
        result = "WIN" if rewards[idx] == 1 else "LOSS" if rewards[idx] == -1 else "OTHER"
        evs = find_phantom_dive_events(eid, idx, opp_idx, steps)
        for ev in evs:
            ev["game_result"] = result
        all_events.extend(evs)

    total = len(all_events)
    no_targets = [e for e in all_events if not e["pre_targets"]]
    with_targets = [e for e in all_events if e["pre_targets"]]
    no_ko_opportunity = [e for e in with_targets if e["best_prize"] == 0]
    with_ko_opportunity = [e for e in with_targets if e["best_prize"] > 0]
    converted = [e for e in with_ko_opportunity if e["actual_prize"] >= e["best_prize"] and set(e["best_kos_slots"]) <= set(e["actual_kos_slots"])]
    achieved_any_ko = [e for e in with_ko_opportunity if e["actual_kos_slots"]]
    achieved_optimal_prize = [e for e in with_ko_opportunity if e["actual_prize"] >= e["best_prize"]]
    missed = [e for e in with_ko_opportunity if e["actual_prize"] < e["best_prize"]]

    n_immune_targets_total = sum(1 for e in all_events for t in e["pre_targets"] if t["immune"])
    n_naive_ko_opportunity = sum(
        1 for e in with_targets
        if any(t["hp"] <= 60 for t in e["pre_targets"])
    )

    active_ko_count = 0
    bench_ko_count = sum(len(e["actual_kos_slots"]) for e in with_targets)
    one_prize_kos = sum(1 for e in with_targets for slot in e["actual_kos_slots"]
                         for t in e["pre_targets"] if t["slot"] == slot and t["prize"] == 1)
    two_prize_kos = sum(1 for e in with_targets for slot in e["actual_kos_slots"]
                         for t in e["pre_targets"] if t["slot"] == slot and t["prize"] == 2)
    multi_ko_opportunities = sum(1 for e in with_ko_opportunity if len(e["best_kos_slots"]) >= 2)
    multi_ko_achieved = sum(1 for e in with_targets if len(e["actual_kos_slots"]) >= 2)

    summary = {
        "total_phantom_dive_attacks": total,
        "events_with_no_bench_targets_at_all": len(no_targets),
        "events_with_bench_targets": len(with_targets),
        "naive_ko_opportunity_count_ignoring_immunity": n_naive_ko_opportunity,
        "immune_target_instances_total": n_immune_targets_total,
        "phantom_dive_with_no_immunity_adjusted_ko_opportunity": len(no_ko_opportunity),
        "phantom_dive_with_at_least_one_ko_opportunity": len(with_ko_opportunity),
        "ko_opportunities_converted_achieved_optimal_prize": len(achieved_optimal_prize),
        "ko_opportunities_with_any_ko_landed": len(achieved_any_ko),
        "ko_opportunities_missed_value": len(missed),
        "opportunity_to_ko_conversion_rate": (len(achieved_optimal_prize) / len(with_ko_opportunity)) if with_ko_opportunity else None,
        "missed_ko_rate_when_ko_available": (len(missed) / len(with_ko_opportunity)) if with_ko_opportunity else None,
        "active_kos_via_phantom_dive": active_ko_count,
        "bench_kos_landed_total": bench_ko_count,
        "one_prize_kos_landed": one_prize_kos,
        "two_prize_kos_landed": two_prize_kos,
        "multi_ko_opportunities_available": multi_ko_opportunities,
        "multi_ko_actually_achieved": multi_ko_achieved,
        "prize_value_lost_to_missed_kos": sum(e["best_prize"] - e["actual_prize"] for e in missed),
    }

    rows = []
    for e in all_events:
        rows.append({
            "episode_id": e["episode_id"], "turn": e["turn"], "game_result": e["game_result"],
            "n_bench_targets": len(e["pre_targets"]),
            "bench_targets": "; ".join(f"{t['card_name']}(hp={t['hp']}/{t['maxhp']},prize={t['prize']},immune={t['immune']})" for t in e["pre_targets"]),
            "counters_observed": e["counters_observed"],
            "best_prize_achievable": e["best_prize"],
            "best_kos_slots": e["best_kos_slots"],
            "actual_kos_slots": e["actual_kos_slots"],
            "actual_prize": e["actual_prize"],
            "prize_shortfall": e["best_prize"] - e["actual_prize"],
            "n_max_equivalent_allocations": e["n_max_equivalent_allocations"],
        })
    with open(os.path.join(OUT_DIR, "events.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        w.writerows(rows)

    ex_rows = []
    for e in sorted(missed, key=lambda e: -(e["best_prize"] - e["actual_prize"])):
        ex_rows.append({
            "episode_id": e["episode_id"], "turn": e["turn"], "game_result": e["game_result"],
            "opponent_bench_pre_attack": "; ".join(f"slot{t['slot']}:{t['card_name']} hp={t['hp']}/{t['maxhp']} prize={t['prize']} immune={t['immune']}({t['immune_reason']})" for t in e["pre_targets"]),
            "v6_actual_allocation_by_slot": e["actual_counts_by_slot"],
            "v6_actual_kos": [t["card_name"] for t in e["pre_targets"] if t["slot"] in e["actual_kos_slots"]],
            "v6_actual_prize": e["actual_prize"],
            "optimal_allocation_by_slot": e["best_alloc_by_slot"],
            "optimal_kos": [t["card_name"] for t in e["pre_targets"] if t["slot"] in e["best_kos_slots"]],
            "optimal_prize": e["best_prize"],
            "prize_difference": e["best_prize"] - e["actual_prize"],
        })
    with open(os.path.join(OUT_DIR, "missed_ko_examples.csv"), "w", newline="", encoding="utf-8") as f:
        if ex_rows:
            w = csv.DictWriter(f, fieldnames=list(ex_rows[0].keys()))
            w.writeheader()
            w.writerows(ex_rows)
        else:
            f.write("no_missed_ko_events_found\n")

    with open(os.path.join(OUT_DIR, "phantom_dive_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))
    print(f"\nmissed examples written: {len(ex_rows)}")
    return summary, all_events, ex_rows


if __name__ == "__main__":
    main()
