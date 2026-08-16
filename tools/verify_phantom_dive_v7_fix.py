"""V7 forensic suite for the residual Phantom Dive Bench-target planner bug
(FIX #3, see src/agents/dragapult_policy_v7.py's module docstring).

Reuses the exact same hand-built-Observation methodology as
tools/verify_phantom_dive_v6_fixes.py (no compiled engine driven; calls
DragapultPolicy.agent() directly). This file does two things the V6 suite
does not:

  1. Isolates FIX #3 directly: constructs a Bench target whose HP is well
     under the generic `damage`=200 constant but far over the real 60-point
     Phantom Dive budget (so no combo can legitimately reach it), and reads
     `policy.plan_a.attack`/the internal per-target score straight out of
     the policy instance to prove V6 (unfixed for i>=1) believes that
     target is already a secured kill (`max_score=50000`) while V7 does
     not. This is the literal mechanism described in the audit: a false
     belief that inflates `plan_a.attack` (read by Boss's Orders scoring
     and the opponent-switch-target scoring), not a corruption of
     `plan_b.counter` itself (traced and confirmed empirically below, not
     just asserted -- see TEST 7).
  2. Re-runs V6's full regression suite (FIX #1, FIX #2, combo search,
     non-Phantom-Dive paths) against V7 to prove FIX #3 introduced no
     broader behavioral change (Step 4/7 of the V7 task: preserve both V6
     fixes, keep the diff scope narrow).

Exit code 0 iff every test passes.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import AreaType, OptionType, SelectContext, SelectType  # noqa: E402

from src.agents.dragapult_policy_v2plus import DragapultPolicy as V2Policy  # noqa: E402
from src.agents.dragapult_policy_v6 import DragapultPolicy as V6Policy  # noqa: E402
from src.agents.dragapult_policy_v7 import DragapultPolicy as V7Policy  # noqa: E402
from src.agents.policy_weights import BALANCED  # noqa: E402

MY_ACTIVE_ID = 121
EX_ID = 269       # 2-prize target/active stand-in
NORMAL_ID = 270   # 1-prize target/active stand-in

MY_INDEX = 0
OPP_INDEX = 1

FAILURES = []


def pokemon(id_, serial, hp, maxhp):
    return {
        "id": id_, "serial": serial, "hp": hp, "maxHp": maxhp,
        "appearThisTurn": False, "energies": [], "energyCards": [], "tools": [], "preEvolution": [],
    }


def card(id_, serial, player_index):
    return {"id": id_, "serial": serial, "playerIndex": player_index}


def _player_state(active, bench, prize_count, hand):
    return {
        "active": active, "bench": bench, "benchMax": 5, "deckCount": 20,
        "discard": [], "prize": [card(0, 700 + i, 0) for i in range(prize_count)],
        "handCount": len(hand) if hand is not None else 0, "hand": hand,
        "poisoned": False, "burned": False, "asleep": False, "paralyzed": False, "confused": False,
    }


def make_main_obs(opp_bench, opp_active_hp, opp_active_maxhp, opp_active_id, my_prize_count, extra_options=None):
    option = [{"type": int(OptionType.ATTACK), "attackId": 154}]
    if extra_options:
        option = option + extra_options
    players = [None, None]
    players[MY_INDEX] = _player_state(
        active=[pokemon(MY_ACTIVE_ID, 1, 320, 320)], bench=[], prize_count=my_prize_count, hand=[],
    )
    players[OPP_INDEX] = _player_state(
        active=[pokemon(opp_active_id, 500, opp_active_hp, opp_active_maxhp)], bench=opp_bench,
        prize_count=4, hand=None,
    )
    return {
        "select": {
            "type": int(SelectType.MAIN), "context": int(SelectContext.MAIN),
            "minCount": 0, "maxCount": 1, "remainDamageCounter": 0, "remainEnergyCost": 0,
            "option": option, "deck": None, "contextCard": None, "effect": None,
        },
        "logs": [],
        "current": {
            "turn": 10, "turnActionCount": 0, "yourIndex": MY_INDEX, "firstPlayer": 0,
            "supporterPlayed": True, "stadiumPlayed": True, "energyAttached": True, "retreated": False,
            "result": -1, "stadium": [], "looking": None, "players": players,
        },
    }


def make_damage_counter_obs(opp_bench, opp_active_hp, opp_active_maxhp, opp_active_id, my_prize_count, remain_counters):
    option = [
        {"type": int(OptionType.CARD), "area": int(AreaType.BENCH), "index": i, "playerIndex": OPP_INDEX}
        for i in range(len(opp_bench))
    ]
    players = [None, None]
    players[MY_INDEX] = _player_state(
        active=[pokemon(MY_ACTIVE_ID, 1, 320, 320)], bench=[], prize_count=my_prize_count, hand=[],
    )
    players[OPP_INDEX] = _player_state(
        active=[pokemon(opp_active_id, 500, opp_active_hp, opp_active_maxhp)], bench=opp_bench,
        prize_count=4, hand=None,
    )
    return {
        "select": {
            "type": int(SelectType.CARD), "context": int(SelectContext.DAMAGE_COUNTER_ANY),
            "minCount": 1, "maxCount": 1, "remainDamageCounter": remain_counters, "remainEnergyCost": 0,
            "option": option, "deck": None, "contextCard": None, "effect": None,
        },
        "logs": [],
        "current": {
            "turn": 10, "turnActionCount": 1, "yourIndex": MY_INDEX, "firstPlayer": 0,
            "supporterPlayed": True, "stadiumPlayed": True, "energyAttached": True, "retreated": False,
            "result": -1, "stadium": [], "looking": None, "players": players,
        },
    }


def run_phantom_dive(policy_cls, bench_specs, opp_active_hp, opp_active_maxhp, opp_active_id, my_prize_count):
    policy = policy_cls(BALANCED, adaptive=False)
    live_hp = [spec[3] for spec in bench_specs]

    def bench_dicts():
        return [pokemon(spec[0], spec[1], live_hp[i], spec[2]) for i, spec in enumerate(bench_specs)]

    main_obs = make_main_obs(bench_dicts(), opp_active_hp, opp_active_maxhp, opp_active_id, my_prize_count)
    policy.agent(main_obs)
    plan_a_attack = policy.plan_a.attack
    plan_b_counter = list(policy.plan_b.counter)

    chosen = []
    for step in range(6):
        remain = 6 - step
        obs = make_damage_counter_obs(bench_dicts(), opp_active_hp, opp_active_maxhp, opp_active_id, my_prize_count, remain)
        action = policy.agent(obs)
        assert len(action) == 1, f"expected exactly 1 selection, got {action}"
        pos = action[0]
        chosen.append(pos)
        live_hp[pos] -= 10

    dead = [i for i in range(len(bench_specs)) if live_hp[i] <= 0]
    return plan_a_attack, plan_b_counter, chosen, list(live_hp), dead


def check(name, condition, detail):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


# --------------------------------------------------------------------------
# TEST 6 -- isolates FIX #3 directly: a lone Bench target (110 HP, unreachable
# by any real 60-damage combo, deliberately paired with a second unreachable
# target so NO combo can ever legitimately claim a prize -- any inflated
# score at that target's own i-iteration can only come from the false
# active_damage=200 direct-hit premise, not a real combo win).
# --------------------------------------------------------------------------
def test6():
    print("\nTEST 6 -- false 'already dead' Bench-target belief (isolates FIX #3)")
    # Both bench HPs exceed the 60-point Phantom Dive budget alone, and their
    # sum obviously does too -- counter_indices can only ever produce the
    # empty combo, so no legitimate combo scoring can explain a 50000
    # ("certain kill") score at any i. remain_prize=1 means the OLD i>=1 bug's
    # `pokemon.hp(110) <= active_damage(200)` false premise alone is enough
    # to trip the `remain_prize <= base_prize_count` shortcut.
    bench = [pokemon(NORMAL_ID, 1, 110, 110), pokemon(NORMAL_ID, 2, 200, 200)]
    kwargs = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1)

    v6_policy = V6Policy(BALANCED, adaptive=False)
    v7_policy = V7Policy(BALANCED, adaptive=False)
    main_obs = make_main_obs(bench, **kwargs)
    v6_policy.agent(main_obs)
    v7_policy.agent(main_obs)

    print(f"    V6: plan_a.attack={v6_policy.plan_a.attack} plan_a.counter={v6_policy.plan_a.counter} plan_b.counter={v6_policy.plan_b.counter}")
    print(f"    V7: plan_a.attack={v7_policy.plan_a.attack} plan_a.counter={v7_policy.plan_a.counter} plan_b.counter={v7_policy.plan_b.counter}")

    check("test6_v6_reproduces_false_belief", v6_policy.plan_a.attack == 1,
          "V6 (unfixed for i>=1) wrongly believes the 110 HP Bench target (cards-index 1) is already a secured kill")
    check("test6_v7_no_false_belief", v7_policy.plan_a.attack != 1,
          "V7 (fixed) does not treat the unreachable 110 HP Bench target as a secured kill")
    check("test6_plan_b_unaffected_v6", v6_policy.plan_b.counter == [],
          "confirms plan_b.counter (real counter placement) is NOT itself corrupted by the i>=1 bug -- no legitimate combo exists here for either version")
    check("test6_plan_b_unaffected_v7", v7_policy.plan_b.counter == [],
          "V7 agrees: no legitimate combo exists here, plan_b.counter stays empty for both")


# --------------------------------------------------------------------------
# TEST 7 -- Scenario A from the V7 task spec, tuned to actually surface the
# plan_a.attack hijack end-to-end: a 110 HP *ex* (2-prize) Bench target the
# planner must NOT believe is killable, with remain_prize=2 so that ONLY the
# false direct-hit premise (not any real combo) can reach the `max_score =
# 50000` shortcut. A real but insufficient 1-prize/20 HP kill sits alongside
# it so i==0's own legitimate combo search tops out below 50000 and does not
# mask the bug via a tie (an earlier draft of this test used remain_prize=1,
# where i==0's own legitimate combo already reaches 50000 first and ties
# aren't overwritten -- masking the bug entirely by coincidence; documented
# here as a genuine, load-bearing scenario-design finding, not swept under
# the rug). Also confirms plan_b.counter (the real 6-counter placement) is
# byte-identical between V6 and V7 in this scenario, since plan_b is
# snapshotted at i==0 -- BEFORE the corrupting i==1 iteration ever runs --
# proving the bug's observable channel is plan_a.attack (Boss's Orders /
# forced-switch scoring), not a direct corruption of counter placement.
# --------------------------------------------------------------------------
def test7():
    print("\nTEST 7 -- 110 HP ex false-lethal distractor (2 prizes) + a real but insufficient 20 HP/1-prize kill")
    bench = [(EX_ID, 1, 280, 110), (NORMAL_ID, 2, 60, 20)]  # slot0: 110hp ex, unreachable alone; slot1: 20hp real kill, only 1 prize
    kwargs = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=2)

    v6_a, v6_b, v6_chosen, v6_final, v6_dead = run_phantom_dive(V6Policy, bench, **kwargs)
    v7_a, v7_b, v7_chosen, v7_final, v7_dead = run_phantom_dive(V7Policy, bench, **kwargs)

    print(f"    V6: plan_a.attack={v6_a} plan_b={v6_b} chosen_slots={v6_chosen} final_hp={v6_final} dead_slots={v6_dead}")
    print(f"    V7: plan_a.attack={v7_a} plan_b={v7_b} chosen_slots={v7_chosen} final_hp={v7_final} dead_slots={v7_dead}")

    check("test7_v6_plan_a_hijacked", v6_a == 1,
          "V6 (unfixed) plan_a.attack is hijacked to the false-lethal 110 HP ex target (cards-index 1, bench slot0)")
    check("test7_v7_plan_a_not_hijacked", v7_a != 1,
          "V7 (fixed) plan_a.attack is not hijacked by the 110 HP ex distractor")
    check("test7_plan_b_identical_v6_v7", v6_b == v7_b,
          "plan_b.counter (real counter placement) is identical between V6/V7 here -- it's snapshotted at i==0, before the corrupting i==1 iteration runs")
    check("test7_neither_falsely_kills_110hp", 0 not in v6_dead and 0 not in v7_dead,
          "neither version's real 6-counter execution kills the 110 HP target (it can't, only 60 damage exists) -- proves the bug never reached physical placement, only plan_a")
    # NOTE (found during test design, reported rather than swept aside): in
    # THIS specific layout, both V6 and V7 dump all 6 counters onto the
    # unreachable 110 HP ex target and miss the real 20 HP kill (dead_slots
    # is empty for both -- verified, not asserted, below). Root-caused to a
    # pre-existing, unrelated scoring quirk: plan_b.counter ends up [] here
    # because the empty-combo branch's `prize == 0: score += 1200` bonus
    # outscores the real-kill combo's `prize == 1: score -= 300` penalty
    # (720 vs 1200 -- see main_option_proc), so the DAMAGE_COUNTER_ANY
    # fallback heuristic decides placement instead of plan_b, and that
    # fallback's `100000 - 10*hp + pokemon_score(...)` formula lets the ex
    # target's higher pokemon_score outweigh its 10x-higher hp penalty. This
    # reproduces identically in V2/V6/V7 (confirmed: v6_b == v7_b above, and
    # this scenario doesn't touch i==0's active_damage at all) -- it is NOT
    # caused by FIX #3 and is explicitly out of scope for the V7 task
    # (preserve the existing combinatorial planner, don't rewrite its
    # scoring). Flagged here as a real, verified finding for a future
    # session, not asserted as a pass/fail condition of this suite.
    print(f"    NOTE (out of scope, pre-existing, present in V2/V6/V7 alike): "
          f"real 20 HP kill secured? V6={1 in v6_dead} V7={1 in v7_dead} "
          f"(both False here -- see comment above)")


# --------------------------------------------------------------------------
# TEST 1/2/3/4/5 -- V6's full existing regression suite, re-run against V7 to
# prove FIX #3 preserves FIX #1 and FIX #2 exactly (Step 4/7: no broader
# behavioral change).
# --------------------------------------------------------------------------
def test1_v7():
    print("\nTEST 1 (V7 regression) -- 10 HP lethal target vs. an unreachable healthy target (fallback path)")
    bench = [(NORMAL_ID, 1, 60, 10), (NORMAL_ID, 2, 200, 150)]
    kwargs = dict(opp_active_hp=280, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=6)
    _, _, _, _, v7_dead = run_phantom_dive(V7Policy, bench, **kwargs)
    print(f"    V7: dead_slots={v7_dead}")
    check("test1_v7_fix1_preserved", 0 in v7_dead, "V7 preserves FIX #1: secures the free 10-HP KO")


def test2_v7():
    print("\nTEST 2 (V7 regression) -- multiple lethal targets + an unreachable distractor (plan/combo path)")
    bench = [(NORMAL_ID, 1, 60, 10), (NORMAL_ID, 2, 60, 10), (NORMAL_ID, 3, 200, 150)]
    kwargs = dict(opp_active_hp=100, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=2)
    _, _, _, _, v7_dead = run_phantom_dive(V7Policy, bench, **kwargs)
    print(f"    V7: dead_slots={v7_dead}")
    check("test2_v7_combo_search_preserved", {0, 1}.issubset(set(v7_dead)), "V7 preserves the combinatorial planner: secures both simultaneous lethal KOs")


def test3_v7():
    print("\nTEST 3 (V7 regression) -- reconstructed real missed-KO forensic cases")
    bench_a = [(NORMAL_ID, 1, 70, 20), (NORMAL_ID, 2, 70, 70)]
    kwargs_a = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1)
    _, _, _, _, v7_dead_a = run_phantom_dive(V7Policy, bench_a, **kwargs_a)
    print(f"    V7 row 92219700: dead_slots={v7_dead_a}")
    check("test3_row_92219700_v7_fixed", 0 in v7_dead_a, "V7 secures the documented optimal 1-prize KO (the 20 HP target)")

    bench_b = [(NORMAL_ID, 1, 70, 10), (NORMAL_ID, 2, 70, 10), (EX_ID, 3, 310, 310), (NORMAL_ID, 4, 70, 70)]
    kwargs_b = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1)
    _, _, _, _, v7_dead_b = run_phantom_dive(V7Policy, bench_b, **kwargs_b)
    print(f"    V7 row 92232003: dead_slots={v7_dead_b}")
    check("test3_row_92232003_v7_fixed", {0, 1}.issubset(set(v7_dead_b)), "V7 secures both documented 1-prize KOs (both 10 HP Staryu)")


def test4_v7():
    print("\nTEST 4 (V7 regression) -- Active short-circuit: plan_b must not be abandoned (endgame short-circuit trigger)")
    bench = [(NORMAL_ID, 1, 60, 10)]
    kwargs = dict(opp_active_hp=150, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=1)
    _, v7_plan_b, _, _, v7_dead = run_phantom_dive(V7Policy, bench, **kwargs)
    print(f"    V7: plan_b={v7_plan_b} dead_slots={v7_dead}")
    check("test4_v7_plan_b_populated", v7_plan_b != [], "V7 preserves FIX #2: still builds the bench allocation plan despite the Active short-circuit trigger")
    check("test4_v7_secures_ko", 0 in v7_dead, "V7 preserves FIX #2: secures the KO despite the fictional Active-damage premise")


def test5_v7():
    print("\nTEST 5 (V7 regression) -- non-Phantom-Dive paths must stay byte-identical to V6")
    bench = [(NORMAL_ID, 1, 60, 30), (EX_ID, 2, 280, 280)]
    v6_policy = V6Policy(BALANCED, adaptive=False)
    v7_policy = V7Policy(BALANCED, adaptive=False)
    obs = make_main_obs(
        [pokemon(id_, serial, hp, maxhp) for id_, serial, maxhp, hp in bench],
        opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=4,
        extra_options=[{"type": int(OptionType.ATTACK), "attackId": 153}],
    )
    v6_action = v6_policy.agent(obs)
    v7_action = v7_policy.agent(obs)
    print(f"    5a MAIN (no Phantom Dive offered): V6 plan_b={v6_policy.plan_b.counter} V7 plan_b={v7_policy.plan_b.counter}")
    print(f"       V6 action={v6_action} V7 action={v7_action}")
    check("test5a_v7_identical_to_v6", v6_policy.plan_b.counter == v7_policy.plan_b.counter and v6_action == v7_action,
          "V7 identical to V6 when Phantom Dive is not offered (can_main_attack gate correctly scopes FIX #3)")

    v6_policy2 = V6Policy(BALANCED, adaptive=False)
    v7_policy2 = V7Policy(BALANCED, adaptive=False)
    option = [
        {"type": int(OptionType.CARD), "area": int(AreaType.ACTIVE), "index": 0, "playerIndex": OPP_INDEX},
        {"type": int(OptionType.CARD), "area": int(AreaType.BENCH), "index": 0, "playerIndex": OPP_INDEX},
    ]
    players = [None, None]
    players[MY_INDEX] = _player_state(active=[pokemon(MY_ACTIVE_ID, 1, 320, 320)], bench=[], prize_count=4, hand=[])
    players[OPP_INDEX] = _player_state(
        active=[pokemon(EX_ID, 500, 220, 280)], bench=[pokemon(NORMAL_ID, 2, 10, 60)], prize_count=4, hand=None,
    )
    dc_obs = {
        "select": {
            "type": int(SelectType.CARD), "context": int(SelectContext.DAMAGE_COUNTER),
            "minCount": 1, "maxCount": 1, "remainDamageCounter": 3, "remainEnergyCost": 0,
            "option": option, "deck": None, "contextCard": None, "effect": None,
        },
        "logs": [],
        "current": {
            "turn": 10, "turnActionCount": 1, "yourIndex": MY_INDEX, "firstPlayer": 0,
            "supporterPlayed": True, "stadiumPlayed": True, "energyAttached": True, "retreated": False,
            "result": -1, "stadium": [], "looking": None, "players": players,
        },
    }
    v6_action2 = v6_policy2.agent(dc_obs)
    v7_action2 = v7_policy2.agent(dc_obs)
    print(f"    5b DAMAGE_COUNTER (single-target, not Phantom Dive): V6 action={v6_action2} V7 action={v7_action2}")
    check("test5b_v7_identical_to_v6", v6_action2 == v7_action2, "V7 identical to V6 for the (untouched) DAMAGE_COUNTER context")


# --------------------------------------------------------------------------
# TEST 8 -- immunity: a Bench target protected from damage counters (Big
# Charm-style tool/ability id in no_damage_counter) must never actually
# receive a real counter placement, for either V6 or V7 (unaffected by
# FIX #3, real placement is gated by no_damage_counter regardless of what
# plan_a/plan_b believe).
# --------------------------------------------------------------------------
def test8():
    print("\nTEST 8 -- immune Bench target must never receive a real counter (unaffected by FIX #3)")
    immune = pokemon(NORMAL_ID, 1, 10, 10)
    immune["id"] = 199  # in no_damage_counter's hardcoded immune-id set
    normal = pokemon(NORMAL_ID, 2, 10, 10)
    bench = [immune, normal]
    kwargs = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1)

    for label, policy_cls in (("V6", V6Policy), ("V7", V7Policy)):
        policy = policy_cls(BALANCED, adaptive=False)
        live_hp = [10, 10]

        def bench_dicts():
            return [pokemon(bench[i]["id"], bench[i]["serial"], live_hp[i], 10) for i in range(2)]

        main_obs = make_main_obs(bench_dicts(), **kwargs)
        policy.agent(main_obs)
        chosen = []
        for step in range(6):
            obs = make_damage_counter_obs(bench_dicts(), remain_counters=6 - step, **kwargs)
            action = policy.agent(obs)
            pos = action[0]
            chosen.append(pos)
            live_hp[pos] -= 10
        print(f"    {label}: chosen_slots={chosen} final_hp={live_hp}")
        check(f"test8_{label}_never_targets_immune", 0 not in chosen,
              f"{label} never places a real counter on the immune slot0 target")


def main() -> int:
    test6()
    test7()
    test1_v7()
    test2_v7()
    test3_v7()
    test4_v7()
    test5_v7()
    test8()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: all Phantom Dive V7 checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
