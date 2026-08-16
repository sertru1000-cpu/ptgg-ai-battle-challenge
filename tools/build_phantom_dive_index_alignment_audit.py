"""Phantom Dive index-alignment forensic audit -- Hypothesis 3.4 from
PHANTOM_DIVE_ARCHITECTURE_AUDIT.md section 3.4.

Investigation only. Does NOT change any agent/weight/deck code. Read-only against the
already-downloaded V2 real-ladder replay data (data/v2_ladder_audit/replays/), reusing the
same Phantom Dive detection convention as tools/build_phantom_dive_forensic.py (MAIN-context
select choosing {"type":13,"attackId":154}, followed by up to 6 sequential
SelectContext.DAMAGE_COUNTER_ANY (14) single-counter placements).

Question being tested: does the Kaggle `cg` engine remove a benched Pokemon from
op_state.bench mid-attack (before all 6 counters are placed), shifting the raw positional
indices of the remaining bench slots -- and if so, does V2's target-consult logic
(dragapult_policy_v2plus.py:784-786, `index = o.index + 1; if index in self.plan_b.counter`)
get fooled by that shift, since both the captured plan and the live consult use raw
positional indices, never Pokemon serial/identity.

For every real Phantom Dive event found, this script records, at each of the 6 sub-steps, the
FULL live bench array exactly as the engine offered it for that specific select (position ->
serial/id/hp), plus the raw index actually chosen. This lets us directly observe (not infer)
whether bench array length/serial-at-position ever changes between two consecutive counter
placements within the same attack.

Writes results/phantom_dive_index_alignment/{index_alignment_events.json,
lethal_before_counter6_examples.csv, bench_array_shift_log.csv}.
"""
from __future__ import annotations

import json
import os

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
REPLAY_DIR = os.path.join(ROOT, "data", "v2_ladder_audit", "replays")
EPMETA_FILE = os.path.join(ROOT, "data", "v2_ladder_audit", "v2_episodes_raw.json")
V2_SUB = 55449878
OUT_DIR = os.path.join(ROOT, "results", "phantom_dive_index_alignment")
os.makedirs(OUT_DIR, exist_ok=True)


def bench_snapshot(cur, opp_idx):
    """Raw bench array exactly as the engine reports it (position -> dict or None),
    no filtering, no reordering -- this IS the thing V2's o.index refers into."""
    if not cur:
        return None
    opp = cur["players"][opp_idx]
    return list(opp.get("bench") or [])


def snap_summary(bench):
    """[(position, serial, card_id, hp) for occupied slots] -- keeps raw position."""
    out = []
    for pos, b in enumerate(bench):
        if b:
            out.append({"pos": pos, "serial": b.get("serial"), "card_id": b.get("id"), "hp": b.get("hp")})
        else:
            out.append({"pos": pos, "serial": None, "card_id": None, "hp": None})
    return out


def find_events(eid, idx, opp_idx, steps):
    events = []
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
                pre_bench = bench_snapshot(pre_cur, opp_idx) or []
                turn = pre_cur.get("turn") if pre_cur else None

                pre_targets = {}
                for pos, b in enumerate(pre_bench):
                    if not b:
                        continue
                    pre_targets[b.get("serial")] = {
                        "pos_at_main": pos, "card_id": b.get("id"), "hp": b.get("hp"), "maxhp": b.get("maxHp"),
                    }

                # walk the up-to-6 sub-selects, recording the FULL live bench snapshot
                # offered at each one (before that counter is chosen), plus the chosen
                # raw index and the resolved serial at that index.
                steps_log = []
                cum_damage_by_serial = {}
                j = k + 1
                counters_placed = 0
                while j < n and counters_placed < 6:
                    sel_j = steps[j - 1][idx]["observation"].get("select")
                    if not sel_j or sel_j.get("context") not in (13, 14):
                        break
                    act_j = steps[j][idx]["action"]
                    opts_j = sel_j.get("option", [])
                    chosen_j = (
                        [opts_j[c] for c in act_j if isinstance(c, int) and 0 <= c < len(opts_j) and isinstance(opts_j[c], dict)]
                        if isinstance(act_j, list) else []
                    )
                    if not chosen_j:
                        break
                    o = chosen_j[0]
                    live_bench_pre = bench_snapshot(steps[j - 1][idx]["observation"].get("current"), opp_idx) or []
                    tgt_idx = o.get("index")
                    tgt = live_bench_pre[tgt_idx] if tgt_idx is not None and 0 <= tgt_idx < len(live_bench_pre) and live_bench_pre[tgt_idx] else None
                    tgt_serial = tgt.get("serial") if tgt else None
                    hp_before = tgt.get("hp") if tgt else None
                    if tgt_serial is not None:
                        cum_damage_by_serial[tgt_serial] = cum_damage_by_serial.get(tgt_serial, 0) + 10
                    steps_log.append({
                        "counter_num": counters_placed + 1,
                        "chosen_raw_index": tgt_idx,
                        "resolved_serial": tgt_serial,
                        "resolved_card_id": tgt.get("id") if tgt else None,
                        "hp_at_selection_time": hp_before,
                        "cum_damage_after_this_counter": cum_damage_by_serial.get(tgt_serial) if tgt_serial is not None else None,
                        "hp_would_be_after_this_counter": (
                            (pre_targets[tgt_serial]["hp"] - cum_damage_by_serial[tgt_serial])
                            if tgt_serial in pre_targets else None
                        ),
                        "live_bench_snapshot_before_this_counter": snap_summary(live_bench_pre),
                        "bench_array_length_before_this_counter": len(live_bench_pre),
                    })
                    counters_placed += 1
                    j += 1

                # post-attack snapshot: state as of the next observation available for us
                # (start of the next decision), reflecting the engine's fully-resolved
                # end-of-attack board (KOs applied, prizes taken, etc. if that already happened)
                post_bench = None
                if j < n:
                    post_cur = steps[j][idx]["observation"].get("current") or steps[j - 1][idx]["observation"].get("current")
                    post_bench = bench_snapshot(post_cur, opp_idx)

                # -- derive: did any target go non-positive (lethal) before all 6 counters
                # were placed, per our own cumulative-damage tracking (works even if the
                # engine removes the mon from the array, since we track cumulative counters
                # placed on that serial regardless of whether it's still visible) --
                lethal_before_6 = []
                for serial, info in pre_targets.items():
                    dmg_at_step = {}
                    running = 0
                    for s in steps_log:
                        if s["resolved_serial"] == serial:
                            running += 10
                        dmg_at_step[s["counter_num"]] = running
                    for cnum, dmg in dmg_at_step.items():
                        if dmg >= info["hp"] and info["hp"] > 0 and cnum < 6:
                            lethal_before_6.append({
                                "serial": serial, "card_id": info["card_id"], "pre_hp": info["hp"],
                                "lethal_at_counter_num": cnum,
                            })
                            break

                # -- derive: did the bench array itself change shape (length, or
                # serial-at-position) between any two consecutive sub-steps? This is the
                # direct, model-free evidence of mid-attack removal/compaction. --
                array_shift_events = []
                for a, b in zip(steps_log, steps_log[1:]):
                    snap_a = a["live_bench_snapshot_before_this_counter"]
                    snap_b = b["live_bench_snapshot_before_this_counter"]
                    if len(snap_a) != len(snap_b):
                        array_shift_events.append({
                            "between_counters": (a["counter_num"], b["counter_num"]),
                            "kind": "array_length_changed",
                            "len_before": len(snap_a), "len_after": len(snap_b),
                        })
                        continue
                    for sa, sb in zip(snap_a, snap_b):
                        if sa["pos"] == sb["pos"] and sa["serial"] is not None and sb["serial"] is not None and sa["serial"] != sb["serial"]:
                            array_shift_events.append({
                                "between_counters": (a["counter_num"], b["counter_num"]),
                                "kind": "serial_at_position_changed",
                                "pos": sa["pos"], "serial_before": sa["serial"], "serial_after": sb["serial"],
                            })
                        if sa["serial"] is not None and sb["serial"] is None and sa["pos"] == sb["pos"]:
                            array_shift_events.append({
                                "between_counters": (a["counter_num"], b["counter_num"]),
                                "kind": "slot_emptied_in_place",
                                "pos": sa["pos"], "serial_removed": sa["serial"],
                            })

                events.append({
                    "episode_id": eid, "turn": turn, "decision_step": k,
                    "pre_targets_by_serial": pre_targets,
                    "n_bench_targets": len(pre_targets),
                    "counters_placed": counters_placed,
                    "steps_log": steps_log,
                    "post_attack_bench": snap_summary(post_bench) if post_bench is not None else None,
                    "lethal_before_counter6": lethal_before_6,
                    "array_shift_events": array_shift_events,
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
        own_agent = next(a for a in e["agents"] if a["submissionId"] == V2_SUB)
        idx = own_agent["index"]
        opp_idx = 1 - idx
        d = json.load(open(rp, encoding="utf-8"))
        steps = d["steps"]
        evs = find_events(eid, idx, opp_idx, steps)
        all_events.extend(evs)

    with_multi_bench = [e for e in all_events if e["n_bench_targets"] >= 2]
    lethal_before_6_events = [e for e in all_events if e["lethal_before_counter6"]]
    array_shift_total = sum(len(e["array_shift_events"]) for e in all_events)
    events_with_array_shift = [e for e in all_events if e["array_shift_events"]]

    print(f"total phantom dive events: {len(all_events)}")
    print(f"events with >=2 bench targets present pre-attack: {len(with_multi_bench)}")
    print(f"events with a target going lethal before counter #6 (our cumulative-damage tracking): {len(lethal_before_6_events)}")
    print(f"events where the live bench array itself changed shape/serial-at-position between two consecutive sub-steps: {len(events_with_array_shift)}")
    print(f"total raw array-shift anomalies detected: {array_shift_total}")

    with open(os.path.join(OUT_DIR, "index_alignment_events.json"), "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=2, default=str)

    import csv
    rows = []
    for e in lethal_before_6_events:
        for L in e["lethal_before_counter6"]:
            rows.append({
                "episode_id": e["episode_id"], "turn": e["turn"], "n_bench_targets": e["n_bench_targets"],
                "counters_placed_total": e["counters_placed"],
                "target_serial": L["serial"], "target_card_id": L["card_id"], "target_pre_hp": L["pre_hp"],
                "lethal_at_counter_num": L["lethal_at_counter_num"],
                "any_array_shift_in_this_event": bool(e["array_shift_events"]),
            })
    with open(os.path.join(OUT_DIR, "lethal_before_counter6_examples.csv"), "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        else:
            f.write("no_lethal_before_counter6_events_found\n")

    shift_rows = []
    for e in events_with_array_shift:
        for s in e["array_shift_events"]:
            shift_rows.append({"episode_id": e["episode_id"], "turn": e["turn"], **s})
    with open(os.path.join(OUT_DIR, "bench_array_shift_log.csv"), "w", newline="", encoding="utf-8") as f:
        if shift_rows:
            w = csv.DictWriter(f, fieldnames=list(shift_rows[0].keys()))
            w.writeheader()
            w.writerows(shift_rows)
        else:
            f.write("no_array_shift_events_found\n")

    return all_events


if __name__ == "__main__":
    main()
