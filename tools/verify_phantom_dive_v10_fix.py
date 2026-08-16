"""V10 Test 2 -- Phantom Dive fix preservation (V10_IMPLEMENTATION_REPORT.md /
governing task's LOCAL VALIDATION Test 2).

V10's policy engine (src/agents/dragapult_policy_v10.py) is a byte-identical
fork of V7's (verified separately: `diff src/agents/dragapult_policy_v7.py
src/agents/dragapult_policy_v10.py` differs only in the module docstring and
the `_DECK_PATH` constant -- no scoring logic changed at all). This suite
proves that fact operationally rather than just asserting it: it re-runs every
one of tools/verify_phantom_dive_v7_fix.py's TEST 1-8 fixtures directly against
V10Policy and checks for the exact same pass/fail outcomes documented there,
specifically:

  - TEST 1: the V6 FIX #1 hp==10 anti-KO-penalty fix is active (a 10 HP
    lethal target is secured, not penalized below unreachable targets).
  - TEST 6/7: the V6 FIX #2 / V7 FIX #3 Active/Bench damage-premise
    separation is active (an unreachable Bench target well under the false
    flat `damage=200` constant is NOT treated as an already-secured kill --
    i.e. Phantom Dive's planner does not believe it deals 200 damage to a
    single Bench target).
  - TEST 2/3/4/5/8: the combinatorial target planner's other behavior
    (multi-target combo search, Active short-circuit handling, non-Phantom-
    Dive paths, immune-target exclusion) is unchanged from V7.

Exit code 0 iff every check passes.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from src.agents.dragapult_policy_v7 import DragapultPolicy as V7Policy  # noqa: E402
from src.agents.dragapult_policy_v10 import DragapultPolicy as V10Policy  # noqa: E402
from src.agents.policy_weights import BALANCED  # noqa: E402

import verify_phantom_dive_v7_fix as pd7  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


def run_and_compare(name, bench, **kwargs):
    v7 = pd7.run_phantom_dive(V7Policy, bench, **kwargs)
    v10 = pd7.run_phantom_dive(V10Policy, bench, **kwargs)
    check(f"{name}_identical_to_v7", v7 == v10, f"{name}: V7 {v7} == V10 {v10}")
    return v10


def test1_hp10_fix_preserved():
    print("\n=== TEST 1 -- V6 FIX #1 (hp==10 anti-KO-penalty) preserved in V10 ===")
    bench = [(pd7.NORMAL_ID, 1, 60, 10), (pd7.NORMAL_ID, 2, 200, 150)]
    kwargs = dict(opp_active_hp=280, opp_active_maxhp=280, opp_active_id=pd7.EX_ID, my_prize_count=6)
    _, _, _, _, v10_dead = run_and_compare("test1_10hp_fallback", bench, **kwargs)
    check("test1_v10_secures_10hp_ko", 0 in v10_dead, "V10 secures the free 10-HP KO (FIX #1 still active, not the old `score -= 100000` regression)")


def test6_active_bench_separation_preserved():
    print("\n=== TEST 6 -- V6 FIX #2 / V7 FIX #3 (Active/Bench damage separation) preserved in V10 ===")
    bench = [pd7.pokemon(pd7.NORMAL_ID, 1, 110, 110), pd7.pokemon(pd7.NORMAL_ID, 2, 200, 200)]
    kwargs = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=pd7.NORMAL_ID, my_prize_count=1)

    v7_policy = V7Policy(BALANCED, adaptive=False)
    v10_policy = V10Policy(BALANCED, adaptive=False)
    main_obs = pd7.make_main_obs(bench, **kwargs)
    v7_policy.agent(main_obs)
    v10_policy.agent(main_obs)

    print(f"    V7:  plan_a.attack={v7_policy.plan_a.attack} plan_b.counter={v7_policy.plan_b.counter}")
    print(f"    V10: plan_a.attack={v10_policy.plan_a.attack} plan_b.counter={v10_policy.plan_b.counter}")
    check("test6_v10_no_false_belief", v10_policy.plan_a.attack != 1,
          "V10 does not treat the unreachable 110 HP Bench target as a secured kill (the contamination bug this fix removes)")
    check("test6_matches_v7", v7_policy.plan_a.attack == v10_policy.plan_a.attack and v7_policy.plan_b.counter == v10_policy.plan_b.counter,
          "V10's planner state is identical to V7's on this exact fixture")


def test7_hijack_regression():
    print("\n=== TEST 7 -- 110 HP ex false-lethal distractor: plan_a.attack not hijacked in V10 ===")
    bench = [(pd7.EX_ID, 1, 280, 110), (pd7.NORMAL_ID, 2, 60, 20)]
    kwargs = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=pd7.NORMAL_ID, my_prize_count=2)
    v10_a, v10_b, v10_chosen, v10_final, v10_dead = run_and_compare("test7_hijack", bench, **kwargs)
    check("test7_v10_not_hijacked", v10_a != 1, "V10's plan_a.attack is not hijacked by the 110 HP ex distractor (matches V7's fixed behavior)")


def test2345_8_regression():
    print("\n=== TEST 2/3/4/5/8 -- remaining V7 regression fixtures byte-identical in V10 ===")
    run_and_compare("test2_combo_plan", [(pd7.NORMAL_ID, 1, 60, 10), (pd7.NORMAL_ID, 2, 60, 10), (pd7.NORMAL_ID, 3, 200, 150)],
                     opp_active_hp=100, opp_active_maxhp=280, opp_active_id=pd7.EX_ID, my_prize_count=2)
    run_and_compare("test3a_forensic", [(pd7.NORMAL_ID, 1, 70, 20), (pd7.NORMAL_ID, 2, 70, 70)],
                     opp_active_hp=150, opp_active_maxhp=150, opp_active_id=pd7.NORMAL_ID, my_prize_count=1)
    run_and_compare("test3b_forensic", [(pd7.NORMAL_ID, 1, 70, 10), (pd7.NORMAL_ID, 2, 70, 10), (pd7.EX_ID, 3, 310, 310), (pd7.NORMAL_ID, 4, 70, 70)],
                     opp_active_hp=150, opp_active_maxhp=150, opp_active_id=pd7.NORMAL_ID, my_prize_count=1)
    run_and_compare("test4_active_shortcircuit", [(pd7.NORMAL_ID, 1, 60, 10)],
                     opp_active_hp=150, opp_active_maxhp=280, opp_active_id=pd7.EX_ID, my_prize_count=1)
    run_and_compare("test8_immune_target", [(199, 1, 10, 10), (pd7.NORMAL_ID, 2, 10, 10)],
                     opp_active_hp=150, opp_active_maxhp=150, opp_active_id=pd7.NORMAL_ID, my_prize_count=1)

    # TEST 5 (non-Phantom-Dive MAIN path) direct byte-identity check.
    bench = [(pd7.NORMAL_ID, 1, 60, 30), (pd7.EX_ID, 2, 280, 280)]
    v7_policy = V7Policy(BALANCED, adaptive=False)
    v10_policy = V10Policy(BALANCED, adaptive=False)
    obs = pd7.make_main_obs(
        [pd7.pokemon(id_, serial, hp, maxhp) for id_, serial, maxhp, hp in bench],
        opp_active_hp=150, opp_active_maxhp=150, opp_active_id=pd7.NORMAL_ID, my_prize_count=4,
        extra_options=[{"type": int(pd7.OptionType.ATTACK), "attackId": 153}],
    )
    v7_action = v7_policy.agent(obs)
    v10_action = v10_policy.agent(obs)
    check("test5_v10_identical_to_v7", v7_policy.plan_b.counter == v10_policy.plan_b.counter and v7_action == v10_action,
          "V10 identical to V7 when Phantom Dive is not offered (can_main_attack gate correctly scopes the fixes)")


def main() -> int:
    test1_hp10_fix_preserved()
    test6_active_bench_separation_preserved()
    test7_hijack_regression()
    test2345_8_regression()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: all V10 Phantom Dive preservation checks passed (V10 byte-identical to V7 on every fixture).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
