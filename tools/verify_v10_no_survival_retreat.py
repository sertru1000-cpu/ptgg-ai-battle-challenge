"""V10 Test 3 -- Survival Retreat removal (V10_IMPLEMENTATION_REPORT.md /
governing task's LOCAL VALIDATION Test 3).

Replays V8's own "lethal_ready_bench_dragapult" scenario (the exact fixture
V8_RETREAT_HEURISTIC_AUDIT.md's Step 9 / tools/verify_v8_survival_retreat.py
uses to prove the Survival Retreat hook fires) against V10, and asserts:

  1. STRUCTURAL: V10Policy has no `_wants_survival_retreat` /
     `_bench_pokemon_is_ready` methods and no `survival_retreat_log`
     attribute at all -- the V8/V9 code was never copied into this file, so
     there is nothing to "disable"; it is simply absent.
  2. BEHAVIORAL: on the exact scenario where V8 forcibly overrides ATTACK
     with RETREAT (a legal attack is on offer, but the Active faces a
     confirmed visible lethal hit with a ready Bench replacement), V10 does
     NOT retreat -- it attacks, exactly like V7 would (V10's engine IS V7's
     engine). Confirmed against V8's own behavior on the identical fixture
     (V8 retreats, V10 does not) so this is a real behavioral contrast, not
     just an absence-of-crash check.
  3. GENERIC PRE-V8 RETREAT STILL WORKS: this test does NOT claim RETREAT is
     never selected by V10 -- only that the V8/V9 hard-coded Survival Retreat
     bonus/override is gone. V4/V5's own pre-existing `_wants_defensive_retreat`
     hook (byte-identical in V10, since it was never touched by V8 either) is
     exercised directly to prove ordinary defensive retreat logic still fires
     when its own (different, narrower) conditions are met -- specifically,
     when no legal attack is on offer at all, which is the one situation
     `_wants_defensive_retreat` itself is written to handle (it explicitly
     returns False whenever `self.can_attack` is True -- see V4/V5's own
     "never give up a legal attack this turn to retreat defensively" comment
     in dragapult_policy_v10.py).

Exit code 0 iff every check passes.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from src.agents.dragapult_policy_v8 import DragapultPolicy as V8Policy  # noqa: E402
from src.agents.dragapult_policy_v10 import DragapultPolicy as V10Policy  # noqa: E402
from src.agents.policy_weights import BALANCED, PolicyWeights  # noqa: E402
from dataclasses import replace  # noqa: E402

import verify_v8_survival_retreat as v8sr  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


# -- 1. structural absence -----------------------------------------------


def test1_structural_absence():
    print("\n=== TEST 1 -- V8/V9 Survival Retreat code is structurally absent from V10 ===")
    check("no_wants_survival_retreat", not hasattr(V10Policy, "_wants_survival_retreat"),
          "V10Policy has no `_wants_survival_retreat` method")
    check("no_bench_pokemon_is_ready", not hasattr(V10Policy, "_bench_pokemon_is_ready"),
          "V10Policy has no `_bench_pokemon_is_ready` method")
    policy = V10Policy(BALANCED, adaptive=False)
    check("no_survival_retreat_log", not hasattr(policy, "survival_retreat_log"),
          "a fresh V10Policy instance has no `survival_retreat_log` attribute")
    check("no_pending_flag", not hasattr(policy, "_survival_retreat_pending"),
          "a fresh V10Policy instance has no `_survival_retreat_pending` anti-thrash bookkeeping (V8-only state)")
    check("has_defensive_retreat", hasattr(V10Policy, "_wants_defensive_retreat"),
          "V10Policy DOES still have `_wants_defensive_retreat` -- the generic, pre-V8 (V4/V5) hook is preserved, not removed")


# -- 2. behavioral contrast on V8's own fixture ---------------------------


def test2_behavioral_contrast():
    print("\n=== TEST 2 -- V8's own 'lethal_ready_bench_dragapult' fixture: V8 retreats, V10 attacks ===")
    # Exact parameters from tools/verify_v8_survival_retreat.py's
    # part_b_scenarios(), "lethal_ready_bench_dragapult": a 2-Prize Dragapult
    # ex Active facing a confirmed, currently-visible lethal hit (230dmg >=
    # 200 remaining hp), with a genuinely playable ready Bench replacement
    # (Dreepy, energy=1, affords Petty Grudge). A legal ATTACK (Jet Headbutt,
    # attackId 153) is also on offer, so V7/V10's own `_wants_defensive_retreat`
    # cannot fire here either (it unconditionally bails when `can_attack` is
    # True) -- isolating this specifically to the V8 Survival Retreat hook.
    DRAGAPULT_EX, EX_ID, DREEPY = v8sr.DRAGAPULT_EX, v8sr.EX_ID, v8sr.DREEPY
    ready_dreepy = (DREEPY, 70, 70, 1)

    my_active = v8sr._pokemon(DRAGAPULT_EX, 1, 200, 320, 1)
    bench = [v8sr._pokemon(ready_dreepy[0], 10, ready_dreepy[1], ready_dreepy[2], ready_dreepy[3])]
    op_active = v8sr._pokemon(EX_ID, 500, 280, 280, 4)
    obs = v8sr.make_retreat_obs(my_active, bench, op_active, [153], can_switch=True)

    v8_policy = V8Policy(BALANCED, adaptive=False)
    v10_policy = V10Policy(BALANCED, adaptive=False)
    v8_action = v8_policy.agent(obs)
    v10_action = v10_policy.agent(obs)

    v8_retreats = 0 in v8_action
    v10_retreats = 0 in v10_action
    print(f"    V8  action={v8_action} retreat_chosen={v8_retreats} (V8's Survival Retreat SHOULD fire here)")
    print(f"    V10 action={v10_action} retreat_chosen={v10_retreats} (V10 must NOT retreat -- no Survival Retreat code exists)")

    check("v8_fires_on_own_fixture", v8_retreats,
          "sanity check: V8 really does force RETREAT on this exact scenario (confirms the fixture is a valid positive control, not a vacuous test)")
    check("v10_does_not_retreat", not v10_retreats,
          "V10 does NOT retreat on the identical scenario -- the hard-coded Survival Retreat override is unreachable")
    check("v10_attacks_instead", 1 in v10_action or (len(v10_action) == 1 and v10_action[0] != 0),
          f"V10 selects the non-retreat option (attack) instead: action={v10_action}")


# -- 3. generic pre-V8 retreat logic still functions -----------------------


def test3_generic_retreat_preserved():
    print("\n=== TEST 3 -- generic pre-V8 `_wants_defensive_retreat` (V4/V5 hook) still fires in V10 ===")
    # No ATTACK option offered at all (can_attack=False) -- the one condition
    # under which `_wants_defensive_retreat` is actually allowed to run past
    # its own "never give up a legal attack" guard. Opponent's only attack
    # (230 dmg) comfortably clears BALANCED's defensive_retreat_hp_fraction
    # threshold against our Active's max HP.
    DRAGAPULT_EX, EX_ID, DREEPY = v8sr.DRAGAPULT_EX, v8sr.EX_ID, v8sr.DREEPY
    ready_dreepy = (DREEPY, 70, 70, 1)

    my_active = v8sr._pokemon(DRAGAPULT_EX, 1, 200, 320, 0)  # 0 energy: cannot afford Jet Headbutt or Phantom Dive
    bench = [v8sr._pokemon(ready_dreepy[0], 10, ready_dreepy[1], ready_dreepy[2], ready_dreepy[3])]
    op_active = v8sr._pokemon(EX_ID, 500, 280, 280, 4)
    obs = v8sr.make_retreat_obs(my_active, bench, op_active, [], can_switch=True)  # attack_ids=[] -> can_attack stays False

    v10_policy = V10Policy(BALANCED, adaptive=False)
    action = v10_policy.agent(obs)
    retreats = 0 in action
    print(f"    V10 action={action} retreat_chosen={retreats} (no attack legal, opponent hits for 230>=hp-fraction threshold)")
    check("v10_generic_defensive_retreat_fires", retreats,
          "V10's generic, pre-V8 `_wants_defensive_retreat` hook (V4/V5, untouched) still fires when its own conditions are met -- "
          "the Survival Retreat REMOVAL did not also remove ordinary retreat logic")


def main() -> int:
    test1_structural_absence()
    test2_behavioral_contrast()
    test3_generic_retreat_preserved()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: all V10 Survival Retreat ablation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
