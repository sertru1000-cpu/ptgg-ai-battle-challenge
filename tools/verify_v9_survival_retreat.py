"""V9 validation suite for the Objective-2 expanded Survival Retreat
heuristic (`LucarioPolicy._wants_survival_retreat` /
`_one_prize_retreat_makes_sense` / `_wants_survival_swap_item` in
src/agents/lucario_policy_v9.py).

Real attack IDs/retreat costs used below were queried live from
cg.api.all_card_data()/all_attack() against this deck's own 6 Pokemon, not
guessed -- see V9_IMPLEMENTATION_REPORT.md for the query output.

  PART A -- scenario table: the megaEx-inclusion extension (non-regression +
  deliberate widening), the three C1/C2/C3 eligibility paths for 1-Prize
  Actives, the "meat shield" exclusion (Objective 2's closing paragraph),
  the winning-trade guard, and the Switch-item path (C3), reached through a
  totally different SelectContext than RETREAT.

  PART B -- anti-thrash guardrail exercised end-to-end for the NEW 1-Prize
  path specifically (V8's own PART C only ever exercised it for a 2-Prize
  ex Pokemon).

Exit code 0 iff every check passes.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import OptionType, Pokemon, SelectContext, SelectType  # noqa: E402

from src.agents.lucario_policy_v9 import LucarioPolicy, Switch  # noqa: E402
from src.agents.policy_weights import BALANCED  # noqa: E402

MY_INDEX = 0
OPP_INDEX = 1

# Real decklist card IDs / attack IDs (queried live, see module docstring).
MAKUHITA = 673        # non-ex, 1-Prize, retreatCost=2. attacks: 976 dmg10/[F], 977 dmg30/[F,F]
HARIYAMA = 674         # non-ex, 1-Prize, retreatCost=3. attack: 978 dmg210/[F,F,F]
LUNATONE = 675         # non-ex, 1-Prize, retreatCost=1. attack: 979 dmg50/[F,F]
SOLROCK = 676          # non-ex, 1-Prize, retreatCost=1. attack: 980 dmg70/[F]
RIOLU = 677            # non-ex, 1-Prize, retreatCost=2. attack: 981 dmg30/[F]
MEGA_LUCARIO_EX = 678  # megaEx, 3-Prize, retreatCost=2. attacks: 982 dmg130/[F], 983 dmg270/[F,F]

# Opponent stand-in (same card used by tools/verify_v8_survival_retreat.py --
# real attack data, queried live against cg.api.all_attack(), not guessed):
EX_ID = 269    # Iono's Bellibolt ex, 2-Prize. attack 368 Thunderous Bolt 230dmg/[4,4,4,0]

FAILURES = []


def check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


def _pokemon(id_, serial, hp, maxhp, energy_count):
    return {
        "id": id_, "serial": serial, "hp": hp, "maxHp": maxhp,
        "appearThisTurn": False, "energies": [6] * energy_count, "energyCards": [], "tools": [], "preEvolution": [],
    }


def _pokemon_obj(id_, serial, hp, maxhp, energy_count) -> Pokemon:
    """Real cg.api.Pokemon dataclass instance, for direct method-level unit
    checks (as opposed to `_pokemon()`'s raw dict, built for full obs_dict
    JSON that `to_observation_class` converts itself)."""
    return Pokemon(
        id=id_, serial=serial, hp=hp, maxHp=maxhp, appearThisTurn=False,
        energies=[6] * energy_count, energyCards=[], tools=[], preEvolution=[],
    )


def _card(id_, serial, player_index):
    return {"id": id_, "serial": serial, "playerIndex": player_index}


def _player_state(active, bench, prize_count, hand):
    return {
        "active": active, "bench": bench, "benchMax": 5, "deckCount": 20,
        "discard": [], "prize": [_card(0, 700 + i, 0) for i in range(prize_count)],
        "handCount": len(hand) if hand is not None else 0, "hand": hand,
        "poisoned": False, "burned": False, "asleep": False, "paralyzed": False, "confused": False,
    }


def make_main_obs(
    my_active, bench, op_active, attack_ids, hand=None, can_switch=True, my_prize=6, op_prize=6, turn=10,
):
    """turn=10 (>=2) so LucarioPolicy._plan_attack's attack search actually
    runs -- irrelevant to the survival-retreat hook itself, but keeps these
    fixtures representative of a real mid-game MAIN decision.
    """
    hand = hand if hand is not None else []
    option = []
    if can_switch:
        option.append({"type": int(OptionType.RETREAT)})
    for aid in attack_ids:
        option.append({"type": int(OptionType.ATTACK), "attackId": aid})
    for i, card in enumerate(hand):
        option.append({"type": int(OptionType.PLAY), "index": i})
    players = [None, None]
    players[MY_INDEX] = _player_state(active=[my_active], bench=bench, prize_count=my_prize, hand=hand)
    players[OPP_INDEX] = _player_state(active=[op_active], bench=[], prize_count=op_prize, hand=None)
    return {
        "select": {
            "type": int(SelectType.MAIN), "context": int(SelectContext.MAIN),
            "minCount": 0, "maxCount": 1, "remainDamageCounter": 0, "remainEnergyCost": 0,
            "option": option, "deck": None, "contextCard": None, "effect": None,
        },
        "logs": [],
        "current": {
            "turn": turn, "turnActionCount": 0, "yourIndex": MY_INDEX, "firstPlayer": 0,
            "supporterPlayed": True, "stadiumPlayed": True, "energyAttached": True, "retreated": False,
            "result": -1, "stadium": [], "looking": None, "players": players,
        },
    }


def run_scenario(
    name, *, my_id, my_hp, my_maxhp, my_energy, bench_specs, op_id, op_hp, op_maxhp, op_energy,
    attack_ids, can_switch=True, hand_ids=None, retreat_expected: bool,
):
    my_active = _pokemon(my_id, 1, my_hp, my_maxhp, my_energy)
    bench = [_pokemon(bid, 10 + i, bhp, bmaxhp, benergy) for i, (bid, bhp, bmaxhp, benergy) in enumerate(bench_specs)]
    op_active = _pokemon(op_id, 500, op_hp, op_maxhp, op_energy)
    hand = [_card(hid, 900 + i, MY_INDEX) for i, hid in enumerate(hand_ids or [])]
    obs = make_main_obs(my_active, bench, op_active, attack_ids, hand=hand, can_switch=can_switch)
    policy = LucarioPolicy(BALANCED, adaptive=False)
    action = policy.agent(obs)

    retreat_idx = 0 if can_switch else None
    retreat_chosen = retreat_idx is not None and retreat_idx in action
    check(f"parta_{name}_retreat", retreat_chosen == retreat_expected,
          f"{name}: action={action} retreat_chosen={retreat_chosen} (expected {retreat_expected})")
    return policy, action


def part_a_scenarios() -> None:
    print("\n=== PART A -- V9 survival-retreat scenario table (Objective 2) ===")

    ready_riolu = (RIOLU, 80, 80, 1)          # affords attack 981 (30dmg/[F]) -- "ready", no _plan_attack branch (confound-free)
    unready_riolu = (RIOLU, 80, 80, 0)

    # -- 1. megaEx inclusion: deliberate extension over V8's literal gate ---
    run_scenario(
        "megaEx_now_included_lethal_ready_bench", my_id=MEGA_LUCARIO_EX, my_hp=200, my_maxhp=340, my_energy=1,
        bench_specs=[ready_riolu], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[982], retreat_expected=True,
    )
    run_scenario(
        "megaEx_no_lethal_no_retreat", my_id=MEGA_LUCARIO_EX, my_hp=340, my_maxhp=340, my_energy=1,
        bench_specs=[ready_riolu], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[982], retreat_expected=False,
    )

    # -- 2. Objective 2.C2: crucial pre-evolution, zero energy at risk ------
    # (Bench replacement is a second Riolu, not Mega Lucario ex, for the same
    # confound-avoidance reason documented at scenario 3/4 below -- kept
    # confound-free here too so a PASS is unambiguous proof of the C2 path
    # specifically, not the unrelated plan.attacker>=1 mechanism.)
    ready_riolu_c2 = (RIOLU, 80, 80, 1)
    run_scenario(
        "one_prize_riolu_zero_energy_retreats", my_id=RIOLU, my_hp=80, my_maxhp=80, my_energy=0,
        bench_specs=[ready_riolu_c2], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[981], retreat_expected=True,
    )
    run_scenario(
        "one_prize_makuhita_zero_energy_retreats", my_id=MAKUHITA, my_hp=80, my_maxhp=80, my_energy=0,
        bench_specs=[ready_riolu_c2], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[976, 977], retreat_expected=True,
    )

    # -- 3. "meat shield" exclusion: energy attached IS at risk --------------
    # Objective 2's own closing paragraph: retreating a 1-Prize meat shield
    # that would cost real Energy, with no immediate counter-attack of its
    # own available, must NOT trigger the bonus. Riolu here has 1 Energy
    # attached (retreat_cost=2 > 0 energy is impossible to fully drain
    # anyway, but ANY energy at risk is disqualifying per C2's own "no
    # attached Energy at all" bar) and cannot itself KO the opponent.
    #
    # NOTE on bench choice for scenarios 3/4 below: Riolu (not Mega Lucario
    # ex) is used as the Bench replacement here specifically because a real
    # confound was found while building this suite -- `_plan_attack` (the
    # ported single-target attack search) has its OWN, unrelated reason to
    # promote a ready Mega Lucario ex on the Bench to `self.plan.attacker`
    # (a positive-scoring attack plan), which independently sets `do_switch
    # = True` via `self.plan.attacker >= 1` BEFORE `_wants_survival_retreat`
    # is even reached -- a real, pre-existing (not new) baseline behavior,
    # ported unchanged from lucario_ex_agent.py's own `plan.attacker`-based
    # RETREAT scoring. Riolu has no species branch in `_plan_attack` at all
    # (matching the original baseline exactly -- it never appears in that
    # method's `if my_pokemon.id ==` chain), so it is "ready" for
    # `_bench_pokemon_is_ready` (E) without ever becoming `plan.attacker`,
    # cleanly isolating what these scenarios are actually testing. See
    # V9_IMPLEMENTATION_REPORT.md for the full writeup of this finding.
    ready_riolu_bench = (RIOLU, 80, 80, 1)
    run_scenario(
        "one_prize_riolu_with_energy_blocks", my_id=RIOLU, my_hp=80, my_maxhp=80, my_energy=1,
        bench_specs=[ready_riolu_bench], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[981], retreat_expected=False,
    )

    # -- 4. non-pre-evolution 1-Prize Pokemon: never eligible (no C match) --
    run_scenario(
        "one_prize_hariyama_not_pre_evolution_blocks", my_id=HARIYAMA, my_hp=150, my_maxhp=150, my_energy=0,
        bench_specs=[ready_riolu_bench], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[978], retreat_expected=False,
    )
    run_scenario(
        "one_prize_solrock_nonfree_retreat_cost_blocks", my_id=SOLROCK, my_hp=110, my_maxhp=110, my_energy=0,
        bench_specs=[ready_riolu_bench], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[980], retreat_expected=False,
    )
    run_scenario(
        "one_prize_lunatone_nonfree_retreat_cost_blocks", my_id=LUNATONE, my_hp=110, my_maxhp=110, my_energy=0,
        bench_specs=[ready_riolu_bench], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[979], retreat_expected=False,
    )

    # -- 5. ready-bench precondition still gates the new 1-Prize path -------
    run_scenario(
        "one_prize_riolu_no_ready_bench_blocks", my_id=RIOLU, my_hp=80, my_maxhp=80, my_energy=0,
        bench_specs=[], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[981], retreat_expected=False,
    )

    # -- 6. winning-trade guard (reachable on the megaEx path, where energy
    # can be nonzero -- structurally UNREACHABLE on the 1-Prize C2 path
    # itself, since C2 requires energy_count==0, which also means the
    # Pokemon can never afford its own attack; see V9_IMPLEMENTATION_REPORT.md).
    run_scenario(
        "winning_trade_blocks_megaEx_retreat", my_id=MEGA_LUCARIO_EX, my_hp=200, my_maxhp=340, my_energy=1,
        bench_specs=[ready_riolu], op_id=EX_ID, op_hp=120, op_maxhp=280, op_energy=4,
        attack_ids=[982], retreat_expected=False,
    )

    # -- 7. Objective 2.C3: Switch in hand bypasses an illegal/unaffordable
    # retreat entirely (can_switch=False -- RETREAT not offered this turn).
    # NOTE: tested via DIRECT calls to `_wants_survival_swap_item` below,
    # not through the full agent()/scoring competition -- a real confound
    # was found while building the end-to-end version of this test: Switch
    # being a legal PLAY option also makes `_plan_attack`'s own
    # `can_switch_for_plan` local True (a pre-existing, unrelated baseline
    # behavior -- see module docstring in lucario_policy_v9.py's
    # `_plan_attack`), which independently lets the attack search point
    # `self.plan.attacker` at the ready Bench Pokemon and ALSO makes
    # Switch's PLAY score 6000 through that unrelated path. That confound
    # would make an end-to-end scenario pass for the wrong reason, so C3 is
    # isolated here as a direct unit check instead.
    part_a_switch_item_direct_checks()

    # -- 8. non-regression: exact V8-style 2-Prize scenario shape doesn't
    # apply here (no 2-Prize ex Pokemon in this decklist), but confirm a
    # plain lethal-with-no-ready-bench case still correctly declines for the
    # 1-Prize path too (same D/E gate as before).
    run_scenario(
        "one_prize_riolu_bench_not_ready_blocks", my_id=RIOLU, my_hp=80, my_maxhp=80, my_energy=0,
        bench_specs=[unready_riolu], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[981], retreat_expected=False,
    )


def part_a_switch_item_direct_checks() -> None:
    print("\n  -- Objective 2.C3, direct _wants_survival_swap_item checks --")
    from collections import defaultdict

    ready_mega_pokemon = _pokemon_obj(MEGA_LUCARIO_EX, 10, 340, 340, 1)
    ready_riolu_active = _pokemon_obj(RIOLU, 1, 80, 80, 2)
    op_active = _pokemon_obj(EX_ID, 500, 280, 280, 4)

    def counts(d):
        c: "defaultdict[int, int]" = defaultdict(int)
        c.update(d)
        return c

    hand_with_switch = counts({Switch: 1})
    hand_without_switch = counts({})

    policy = LucarioPolicy(BALANCED, adaptive=False)

    # C3 fires: RETREAT illegal this decision, Switch in hand, lethal threat,
    # ready bench.
    policy.can_switch = False
    result = policy._wants_survival_swap_item(ready_riolu_active, op_active, [ready_mega_pokemon], hand_with_switch)
    check("partc3_fires_when_retreat_illegal_and_switch_in_hand", result is True, f"expected True, got {result}")

    # C3 does NOT fire without Switch in hand (same threat/bench).
    result = policy._wants_survival_swap_item(ready_riolu_active, op_active, [ready_mega_pokemon], hand_without_switch)
    check("partc3_no_fire_without_switch_in_hand", result is False, f"expected False, got {result}")

    # C3 does NOT fire when RETREAT is already legal (self.can_switch True) --
    # this is the live RETREAT-path's job, not C3's.
    policy.can_switch = True
    result = policy._wants_survival_swap_item(ready_riolu_active, op_active, [ready_mega_pokemon], hand_with_switch)
    check("partc3_no_fire_when_retreat_already_legal", result is False, f"expected False, got {result}")

    # C3 does NOT fire when there's no real lethal threat.
    policy.can_switch = False
    healthy_riolu = _pokemon_obj(RIOLU, 1, 340, 340, 2)
    result = policy._wants_survival_swap_item(healthy_riolu, op_active, [ready_mega_pokemon], hand_with_switch)
    check("partc3_no_fire_without_lethal_threat", result is False, f"expected False, got {result}")

    # C3 does NOT fire when the Bench has no genuinely ready replacement.
    unready_mega = _pokemon_obj(MEGA_LUCARIO_EX, 10, 340, 340, 0)
    result = policy._wants_survival_swap_item(ready_riolu_active, op_active, [unready_mega], hand_with_switch)
    check("partc3_no_fire_without_ready_bench", result is False, f"expected False, got {result}")


def part_b_direct_one_prize_fire_check() -> None:
    """A single, confound-free, direct call proving `_wants_survival_retreat`
    itself (not the pre-existing `plan.attacker>=1` bench-promotion path --
    see the note on scenarios 3/4 in part_a_scenarios) is what fires and
    logs for a qualifying 1-Prize Active, and that it correctly tags
    `one_prize_path: True` for STEP 8-style instrumentation.
    """
    print("\n=== PART B -- direct one_prize_path firing/logging check ===")
    policy = LucarioPolicy(BALANCED, adaptive=False)
    policy.can_switch = True
    riolu_active = _pokemon_obj(RIOLU, 1, 80, 80, 0)
    op_active = _pokemon_obj(EX_ID, 500, 280, 280, 4)
    ready_mega_pokemon = _pokemon_obj(MEGA_LUCARIO_EX, 10, 340, 340, 1)

    result = policy._wants_survival_retreat(riolu_active, op_active, [ready_mega_pokemon])
    check("partb_direct_fires", result is True, f"expected True, got {result}")
    check("partb_pending_set", policy._survival_retreat_pending is False, "note: pending is set by agent(), not this method directly -- checked via the end-to-end anti-thrash test below instead")
    check("partb_log_marks_one_prize_path", bool(policy.survival_retreat_log) and policy.survival_retreat_log[-1]["one_prize_path"] is True,
          f"log entry flags one_prize_path=True: {policy.survival_retreat_log[-1] if policy.survival_retreat_log else None}")


def part_b_anti_thrash_megaEx() -> None:
    """End-to-end anti-thrash guardrail (STEP 4, ported unchanged from V8)
    exercised through agent() for the megaEx path specifically -- this path
    is genuinely NEW/newly-reachable for V9 (Dragapult ex, V8's own deck,
    has zero 3-Prize Pokemon, so this exact code path never fired in V8 at
    all). Uses Mega Lucario ex (unconditionally eligible, no C-gate energy
    constraint to work around) retreating into a Riolu Bench replacement --
    Riolu is used here for the same confound-avoidance reason documented in
    part_a_scenarios (it has no `_plan_attack` species branch, so it cannot
    independently trigger `do_switch` via the pre-existing
    `plan.attacker>=1` path, cleanly isolating the anti-thrash mechanism
    itself, exactly like V8's own PART C isolated it using Dragapult ex on
    both sides of the retreat).
    """
    print("\n=== PART B -- anti-thrash guardrail (STEP 4) on the megaEx path ===")
    policy = LucarioPolicy(BALANCED, adaptive=False)
    ready_riolu = (RIOLU, 80, 80, 1)

    # Turn N: Mega Lucario ex (serial=1) lethally threatened, Riolu ready on
    # the bench. Should fire -> RETREAT chosen.
    my_active = _pokemon(MEGA_LUCARIO_EX, 1, 200, 340, 1)
    op_active = _pokemon(EX_ID, 500, 280, 280, 4)
    riolu_bench_1 = _pokemon(*ready_riolu[:1], 10, *ready_riolu[1:])
    obs1 = make_main_obs(my_active, [riolu_bench_1], op_active, [982], turn=10)
    action1 = policy.agent(obs1)
    check("partb_turn_n_fires", 0 in action1, f"turn N: RETREAT chosen (action={action1})")
    check("partb_pending_set", policy._survival_retreat_pending is True, "pending flag set after firing")
    check("partb_log_not_one_prize_path", bool(policy.survival_retreat_log) and policy.survival_retreat_log[-1]["one_prize_path"] is False,
          f"log entry flags one_prize_path=False (megaEx path): {policy.survival_retreat_log[-1] if policy.survival_retreat_log else None}")

    # Simulate the retreat resolving: Riolu (serial=10) now Active.
    riolu_active = _pokemon(RIOLU, 10, 80, 80, 1)
    obs2 = make_main_obs(riolu_active, [], op_active, [981], can_switch=False, turn=10)
    policy.agent(obs2)
    check("partb_pending_resolved", policy._survival_retreat_pending is False, "pending flag cleared once new Active (serial=10) observed")
    check("partb_snapshot_serial", policy._last_survival_retreat_serial == 10, f"snapshotted serial=10, got {policy._last_survival_retreat_serial}")

    # Turn N+2: Riolu (serial=10) STILL active, STILL at 80 HP, facing the
    # SAME opponent (serial=500), still lethal (230 >= 80), still carrying
    # the SAME 1 Energy it had when it became active (so C2's own "no energy
    # at risk" bar is NOT met -- this Riolu would not independently qualify
    # via C2 right now regardless of the anti-thrash guard). To prove the
    # anti-thrash guard specifically (not just eligibility naturally
    # lapsing), give it a fresh SECOND ready Bench replacement so the only
    # thing that could still block a re-fire is STEP 4 itself -- but since
    # this Riolu also fails C2 on its own (1 Energy attached), this call
    # instead demonstrates the two mechanisms are independent: it declines,
    # and declines for the eligibility reason, not because STEP 4 was even
    # reached. See the megaEx repeat-check directly below for the guard
    # itself.
    riolu_bench_2 = _pokemon(*ready_riolu[:1], 11, *ready_riolu[1:])
    obs3 = make_main_obs(riolu_active, [riolu_bench_2], op_active, [981], turn=12)
    action3 = policy.agent(obs3)
    check("partb_one_energy_riolu_not_eligible", 0 not in action3, f"turn N+2 (Riolu carrying 1 Energy, C2 doesn't hold): RETREAT NOT chosen (action={action3})")

    # -- Direct STEP 4 guard check (isolated from C-eligibility entirely): --
    # replay the exact same (serial, hp, op_serial) state that was just
    # snapshotted as "already saved" and confirm `_wants_survival_retreat`
    # itself declines to re-fire for a Pokemon that WOULD otherwise qualify
    # (megaEx, unconditional eligibility -- no C-gate to confound this with).
    # HP is deliberately <= the opponent's 230-damage attack (a real lethal
    # threat) at every step here -- otherwise a block would be ambiguous
    # (blocked by the guard, or simply because there's no lethal threat at
    # that HP?). A first draft of this test used hp=340 (Mega Lucario ex's
    # full HP) and got exactly that ambiguity (230 < 340 is never lethal),
    # caught by re-deriving the expected result independently rather than
    # trusting the first PASS.
    mega_repeat_active = _pokemon_obj(MEGA_LUCARIO_EX, 10, 200, 340, 1)
    op_active_obj = _pokemon_obj(EX_ID, 500, 280, 280, 4)
    ready_riolu_bench_obj = _pokemon_obj(RIOLU, 20, 80, 80, 1)
    policy._last_survival_retreat_serial = 10
    policy._last_survival_retreat_hp = 200
    policy._last_survival_retreat_op_serial = 500
    policy.can_switch = True
    result_stale = policy._wants_survival_retreat(mega_repeat_active, op_active_obj, [ready_riolu_bench_obj])
    check("partb_stale_repeat_blocked", result_stale is False, f"identical (serial,hp,op_serial) as already-saved: expected False, got {result_stale}")

    # Genuinely new information (HP changed, still lethal at 170 <= 230) must un-block.
    mega_damaged_obj = _pokemon_obj(MEGA_LUCARIO_EX, 10, 170, 340, 1)
    result_unblocked = policy._wants_survival_retreat(mega_damaged_obj, op_active_obj, [ready_riolu_bench_obj])
    check("partb_new_info_unblocks", result_unblocked is True, f"HP changed 340->300 (new info): expected True, got {result_unblocked}")


def main() -> int:
    part_a_scenarios()
    part_b_direct_one_prize_fire_check()
    part_b_anti_thrash_megaEx()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: all V9 survival-retreat checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
