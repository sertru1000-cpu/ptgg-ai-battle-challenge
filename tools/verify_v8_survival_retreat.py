"""V8 validation suite for the new 2-Prize Defensive Retreat / Survival
heuristic (`DragapultPolicy._wants_survival_retreat` /
`_bench_pokemon_is_ready` in src/agents/dragapult_policy_v8.py).

Two parts, matching V8_RETREAT_HEURISTIC_AUDIT.md's Step 7 / Step 9:

  PART A (Step 7 -- regression protection): re-runs V7's own Phantom Dive
  regression fixtures (tools/verify_phantom_dive_v7_fix.py) against V8,
  asserting byte-identical output to V7 on every one. None of those fixtures
  offer a RETREAT option, so the new hook's `if not self.can_switch: return
  False` gate should make it fully inert there -- this proves that directly
  rather than assuming it.

  PART B (Step 9 -- validation scenarios): ~30 hand-built MAIN-context
  scenarios covering every category the phase prompt lists (guaranteed
  lethal + ready/not-ready/empty Bench, no-lethal, 1-Prize exclusion,
  3-Prize/Mega ex exclusion, expensive-vs-cheap retreat, winning-trade guard,
  multiple 2-Prize Actives from the real decklist, boundary conditions), each
  asserting the actual top-scored MAIN action (not just an internal flag).

  PART C (Step 4/9 -- anti-thrash guardrail): a multi-call sequence directly
  exercising the STEP 4 critical guardrail end-to-end through `agent()`,
  proving both that a stale repeat is blocked and that genuinely new
  information (HP change) un-blocks it.

Exit code 0 iff every check passes.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import OptionType, SelectContext, SelectType  # noqa: E402

from src.agents.dragapult_policy_v7 import DragapultPolicy as V7Policy  # noqa: E402
from src.agents.dragapult_policy_v8 import DragapultPolicy as V8Policy  # noqa: E402
from src.agents.policy_weights import BALANCED  # noqa: E402

import verify_phantom_dive_v7_fix as pd7  # noqa: E402

MY_INDEX = 0
OPP_INDEX = 1

# Real decklist card IDs (src/agents/dragapult_policy_v8.py's own constants).
DRAGAPULT_EX = 121   # ex, 2-Prize. attacks: 153 Jet Headbutt 70dmg/[0], 154 Phantom Dive 200dmg/[2,5]
FEZANDIPITI_EX = 140  # ex, 2-Prize. attack: 183 Cruel Arrow 0dmg/[0,0,0] (never a trade opportunity)
LATIAS_EX = 184       # ex, 2-Prize. attack: 243 Eon Blade 200dmg/[5,5,0]
MEOWTH_EX = 1071      # ex, 2-Prize. attack: 1546 Tuck Tail 60dmg/[0,0,0]
DREEPY = 119          # non-ex, 1-Prize. attacks: 150 Petty Grudge 10dmg/[5], 151 Bite 40dmg/[2,5]
DRAKLOAK = 120        # non-ex, 1-Prize. attack: 152 Dragon Headbutt 70dmg/[2,5]
BUDEW = 235           # non-ex, 1-Prize. attack: 323 Itchy Pollen 10dmg/[] (zero-cost)
MEGA_VENUSAUR_EX = 652  # megaEx (3-Prize). attack: 941 240dmg/[1,1,1,1] -- not in our deck, used only to
                         # prove the 3-Prize/Mega exclusion boundary against a real card in the engine's pool.

# Opponent stand-ins (same cards used by tools/verify_phantom_dive_v7_fix.py; real
# attack data queried live against cg.api.all_attack(), not guessed):
EX_ID = 269    # Iono's Bellibolt ex, 2-Prize. attack 368 Thunderous Bolt 230dmg/[4,4,4,0]
NORMAL_ID = 270  # Iono's Wattrel, 1-Prize. attack 369 Quick Attack 10dmg/[4]

FAILURES = []


def check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


# ---------------------------------------------------------------------------
# PART A -- Phantom Dive regression: V7 vs V8 must be byte-identical on every
# one of V7's own fixtures (none offer RETREAT, so this also mechanically
# confirms the new hook cannot activate outside a MAIN decision that offers
# retreat at all).
# ---------------------------------------------------------------------------


def part_a_phantom_dive_regression() -> None:
    print("\n=== PART A -- Phantom Dive regression: V7 vs V8 byte-identical ===")

    def run_and_compare(name, bench, **kwargs):
        v7 = pd7.run_phantom_dive(V7Policy, bench, **kwargs)
        v8 = pd7.run_phantom_dive(V8Policy, bench, **kwargs)
        check(f"parta_{name}_identical", v7 == v8, f"{name}: V7 {v7} == V8 {v8}")

    run_and_compare(
        "test1_10hp_fallback",
        [(NORMAL_ID, 1, 60, 10), (NORMAL_ID, 2, 200, 150)],
        opp_active_hp=280, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=6,
    )
    run_and_compare(
        "test2_combo_plan",
        [(NORMAL_ID, 1, 60, 10), (NORMAL_ID, 2, 60, 10), (NORMAL_ID, 3, 200, 150)],
        opp_active_hp=100, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=2,
    )
    run_and_compare(
        "test3a_forensic",
        [(NORMAL_ID, 1, 70, 20), (NORMAL_ID, 2, 70, 70)],
        opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1,
    )
    run_and_compare(
        "test3b_forensic",
        [(NORMAL_ID, 1, 70, 10), (NORMAL_ID, 2, 70, 10), (EX_ID, 3, 310, 310), (NORMAL_ID, 4, 70, 70)],
        opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1,
    )
    run_and_compare(
        "test4_active_shortcircuit",
        [(NORMAL_ID, 1, 60, 10)],
        opp_active_hp=150, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=1,
    )
    run_and_compare(
        "test8_immune_target",
        [(199, 1, 10, 10), (NORMAL_ID, 2, 10, 10)],
        opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1,
    )

    # TEST 6/7 (plan_a inspection, not the run_phantom_dive() harness) and 5a/5b
    # (non-Phantom-Dive MAIN/DAMAGE_COUNTER paths) re-run directly.
    bench67 = [pd7.pokemon(EX_ID, 1, 280, 110), pd7.pokemon(NORMAL_ID, 2, 60, 20)]
    main_obs = pd7.make_main_obs(bench67, opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=2)
    v7p, v8p = V7Policy(BALANCED, adaptive=False), V8Policy(BALANCED, adaptive=False)
    v7p.agent(main_obs)
    v8p.agent(main_obs)
    check("parta_test7_plan_a_identical", v7p.plan_a.attack == v8p.plan_a.attack, f"plan_a.attack V7={v7p.plan_a.attack} V8={v8p.plan_a.attack}")
    check("parta_test7_plan_b_identical", v7p.plan_b.counter == v8p.plan_b.counter, f"plan_b.counter V7={v7p.plan_b.counter} V8={v8p.plan_b.counter}")

    bench5 = [(NORMAL_ID, 1, 60, 30), (EX_ID, 2, 280, 280)]
    obs5a = pd7.make_main_obs(
        [pd7.pokemon(id_, serial, hp, maxhp) for id_, serial, maxhp, hp in bench5],
        opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=4,
        extra_options=[{"type": int(OptionType.ATTACK), "attackId": 153}],
    )
    v7p2, v8p2 = V7Policy(BALANCED, adaptive=False), V8Policy(BALANCED, adaptive=False)
    a7 = v7p2.agent(obs5a)
    a8 = v8p2.agent(obs5a)
    check("parta_test5a_identical", a7 == a8 and v7p2.plan_b.counter == v8p2.plan_b.counter, f"5a (no RETREAT offered) V7 action={a7} V8 action={a8}")


# ---------------------------------------------------------------------------
# PART B -- fixture builders + scenario table for the new hook itself.
# ---------------------------------------------------------------------------


def _pokemon(id_, serial, hp, maxhp, energy_count):
    return {
        "id": id_, "serial": serial, "hp": hp, "maxHp": maxhp,
        "appearThisTurn": False, "energies": [0] * energy_count, "energyCards": [], "tools": [], "preEvolution": [],
    }


def _card(id_, serial, player_index):
    return {"id": id_, "serial": serial, "playerIndex": player_index}


def _player_state(active, bench, prize_count, hand):
    return {
        "active": active, "bench": bench, "benchMax": 5, "deckCount": 20,
        "discard": [], "prize": [_card(0, 700 + i, 0) for i in range(prize_count)],
        "handCount": len(hand) if hand is not None else 0, "hand": hand,
        "poisoned": False, "burned": False, "asleep": False, "paralyzed": False, "confused": False,
    }


def make_retreat_obs(
    my_active, bench, op_active, attack_ids, can_switch=True, my_prize=6, op_prize=6, turn=10,
):
    option = []
    if can_switch:
        option.append({"type": int(OptionType.RETREAT)})
    for aid in attack_ids:
        option.append({"type": int(OptionType.ATTACK), "attackId": aid})
    players = [None, None]
    players[MY_INDEX] = _player_state(active=[my_active], bench=bench, prize_count=my_prize, hand=[])
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


def run_scenario(name, *, my_id, my_hp, my_maxhp, my_energy, bench_specs, op_id, op_hp, op_maxhp,
                  op_energy, attack_ids, can_switch=True, retreat_expected: bool):
    my_active = _pokemon(my_id, 1, my_hp, my_maxhp, my_energy)
    bench = [_pokemon(bid, 10 + i, bhp, bmaxhp, benergy) for i, (bid, bhp, bmaxhp, benergy) in enumerate(bench_specs)]
    op_active = _pokemon(op_id, 500, op_hp, op_maxhp, op_energy)
    obs = make_retreat_obs(my_active, bench, op_active, attack_ids, can_switch=can_switch)
    policy = V8Policy(BALANCED, adaptive=False)
    action = policy.agent(obs)
    retreat_idx = 0 if can_switch else None
    retreat_chosen = retreat_idx is not None and retreat_idx in action
    print(f"    {name}: action={action} retreat_chosen={retreat_chosen} (expected {retreat_expected})")
    check(f"partb_{name}", retreat_chosen == retreat_expected,
          f"{name}: expected retreat_chosen={retreat_expected}, got {retreat_chosen}")


def part_b_scenarios() -> None:
    print("\n=== PART B -- survival-retreat scenario table (Step 9) ===")

    ready_dreepy = (DREEPY, 70, 70, 1)         # affords Petty Grudge (10dmg/[5]) -- "ready"
    unready_dreepy = (DREEPY, 70, 70, 0)       # can't afford either attack -- not ready
    ready_drakloak = (DRAKLOAK, 90, 90, 2)     # affords Dragon Headbutt (70dmg/[2,5])
    unready_fezandipiti = (FEZANDIPITI_EX, 210, 210, 3)  # damage=0 attack never counts as "ready"
    ready_budew_zero_cost = (BUDEW, 30, 30, 0)  # Itchy Pollen 10dmg/[] -- ready even at 0 energy

    # -- 1. guaranteed visible lethal + ready 2-Prize replacement --------------
    run_scenario(
        "lethal_ready_bench_dragapult", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=True,
    )
    run_scenario(
        "lethal_ready_bench_multiple_candidates", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[unready_fezandipiti, ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=True,
    )
    run_scenario(
        "lethal_ready_bench_zero_cost_attack", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[ready_budew_zero_cost], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=True,
    )

    # -- 2. guaranteed visible lethal + NO playable replacement -----------------
    run_scenario(
        "lethal_empty_bench", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=False,
    )
    run_scenario(
        "lethal_bench_present_but_not_ready", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[unready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=False,
    )
    run_scenario(
        "lethal_bench_only_zero_damage_support", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[unready_fezandipiti], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=False,
    )

    # -- 3. no lethal + good attack opportunity ---------------------------------
    run_scenario(
        "no_lethal_op_energy_insufficient", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=3,
        attack_ids=[153], retreat_expected=False,
    )
    run_scenario(
        "no_lethal_hp_too_high", my_id=DRAGAPULT_EX, my_hp=231, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=False,
    )

    # -- 4. 1-Prize Active + lethal (STEP 5 exclusion) --------------------------
    run_scenario(
        "one_prize_active_excluded_dreepy", my_id=DREEPY, my_hp=60, my_maxhp=70, my_energy=1,
        bench_specs=[ready_drakloak], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[150], retreat_expected=False,
    )
    run_scenario(
        "one_prize_active_excluded_drakloak", my_id=DRAKLOAK, my_hp=90, my_maxhp=90, my_energy=2,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[152], retreat_expected=False,
    )

    # -- 5. 3-Prize Mega ex Active (STEP 5's literal-reading boundary) ----------
    run_scenario(
        "mega_ex_excluded", my_id=MEGA_VENUSAUR_EX, my_hp=230, my_maxhp=380, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[941], retreat_expected=False,
    )

    # -- 6. 2-Prize Active + lethal but expensive retreat (STEP 6) --------------
    # retreatCost(Dragapult ex)=1; energy=2 attached (a real, meaningful, multi-
    # turn investment) is NOT fully wiped (cost 1 < energy 2). Documents the
    # "moderately costly" side of STEP 6, still expected to retreat.
    run_scenario(
        "moderate_retreat_cost_still_retreats", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=2,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=True,
    )
    # Latias ex: retreatCost=2, energy=2 -> a full energy wipe (cost >= energy,
    # a genuinely "expensive" retreat per STEP 6's own framing) but the Bench
    # replacement IS genuinely ready, so per this design's documented reasoning
    # (E dominates; see V8_RETREAT_HEURISTIC_AUDIT.md) it still retreats rather
    # than donating 2 Prizes to a confirmed lethal hit.
    run_scenario(
        "full_energy_wipe_retreat_still_fires_with_ready_bench", my_id=LATIAS_EX, my_hp=180, my_maxhp=210, my_energy=2,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[243], retreat_expected=True,
    )
    # Same full-wipe-cost Latias ex, but now paired with STEP 6's own literal
    # negative example (bench NOT genuinely ready) -- E is what actually blocks
    # it, exactly as the phase prompt's own worked example is structured.
    run_scenario(
        "full_energy_wipe_plus_unready_bench_blocks", my_id=LATIAS_EX, my_hp=180, my_maxhp=210, my_energy=2,
        bench_specs=[unready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[243], retreat_expected=False,
    )

    # -- 7. winning-trade guard: attacking secures a KO too, so keep attacking --
    run_scenario(
        "winning_trade_blocks_retreat", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=60, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=False,
    )
    # Same low opponent HP, but now we can't actually AFFORD the trade attack
    # (0 energy) -- the trade guard must not fire on an attack we can't use,
    # so the survival retreat should still trigger.
    run_scenario(
        "unaffordable_trade_does_not_block_retreat", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=0,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=60, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=True,
    )
    # Fezandipiti ex's only attack deals 0 damage -- can never trigger the
    # trade guard regardless of opponent HP.
    run_scenario(
        "zero_damage_attacker_never_trades", my_id=FEZANDIPITI_EX, my_hp=150, my_maxhp=210, my_energy=3,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=10, op_maxhp=280, op_energy=4,
        attack_ids=[183], retreat_expected=True,
    )

    # -- 7b. Phantom Dive mirror-match regression (found by real self-play,
    # Step 9 -- see V8_RETREAT_HEURISTIC_AUDIT.md Known Limitations). Phantom
    # Dive's card-data `damage=200` is fictional for the Active (it never
    # damages the Active, only the Bench) -- the lethal-detection and trade-
    # guard loops must both special-case attackId 154 (Phantom Dive) exactly
    # like this file's own pre-existing V6 FIX #2 / V7 FIX #3 already does
    # inside `main_option_proc`, or they falsely treat it as a real threat.
    run_scenario(
        "phantom_dive_is_not_a_real_lethal_threat_to_active",
        my_id=DRAGAPULT_EX, my_hp=150, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=DRAGAPULT_EX, op_hp=280, op_maxhp=320, op_energy=2,
        attack_ids=[153], retreat_expected=False,
    )
    run_scenario(
        "phantom_dive_is_not_a_real_trade_opportunity",
        my_id=DRAGAPULT_EX, my_hp=150, my_maxhp=320, my_energy=2,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=100, op_maxhp=280, op_energy=4,
        attack_ids=[153, 154], retreat_expected=True,
    )

    # -- 8. can_switch legality gate ---------------------------------------------
    run_scenario(
        "retreat_illegal_this_decision", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], can_switch=False, retreat_expected=False,
    )

    # -- 9. boundary conditions on the lethal threshold (>=, not >) -------------
    run_scenario(
        "boundary_damage_equals_hp_is_lethal", my_id=DRAGAPULT_EX, my_hp=230, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=True,
    )
    run_scenario(
        "boundary_damage_one_below_hp_not_lethal", my_id=DRAGAPULT_EX, my_hp=231, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[153], retreat_expected=False,
    )

    # -- 10. can_attack False (no ATTACK offered at all) still degrades gracefully
    run_scenario(
        "no_attack_offered_still_retreats", my_id=DRAGAPULT_EX, my_hp=200, my_maxhp=320, my_energy=1,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[], retreat_expected=True,
    )

    # -- 11. generality across every 2-Prize ex Active in the real decklist -----
    run_scenario(
        "generality_fezandipiti_ex", my_id=FEZANDIPITI_EX, my_hp=150, my_maxhp=210, my_energy=3,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[183], retreat_expected=True,
    )
    run_scenario(
        "generality_latias_ex", my_id=LATIAS_EX, my_hp=180, my_maxhp=210, my_energy=2,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[243], retreat_expected=True,
    )
    run_scenario(
        "generality_meowth_ex", my_id=MEOWTH_EX, my_hp=100, my_maxhp=170, my_energy=2,
        bench_specs=[ready_dreepy], op_id=EX_ID, op_hp=280, op_maxhp=280, op_energy=4,
        attack_ids=[1546], retreat_expected=True,
    )

    # -- 12. opponent is only 1-Prize but still hits hard enough to be lethal ---
    run_scenario(
        "lethal_from_1prize_opponent", my_id=FEZANDIPITI_EX, my_hp=10, my_maxhp=210, my_energy=3,
        bench_specs=[ready_dreepy], op_id=NORMAL_ID, op_hp=60, op_maxhp=60, op_energy=1,
        attack_ids=[183], retreat_expected=True,
    )
    run_scenario(
        "not_lethal_from_1prize_opponent", my_id=FEZANDIPITI_EX, my_hp=11, my_maxhp=210, my_energy=3,
        bench_specs=[ready_dreepy], op_id=NORMAL_ID, op_hp=60, op_maxhp=60, op_energy=1,
        attack_ids=[183], retreat_expected=False,
    )


# ---------------------------------------------------------------------------
# PART C -- STEP 4 anti-thrash guardrail, exercised end-to-end through
# agent() across a simulated multi-turn sequence (not just the isolated
# method), including the positive (blocked) and negative (un-blocked) cases.
# ---------------------------------------------------------------------------


def part_c_anti_thrash() -> None:
    print("\n=== PART C -- anti-thrash guardrail (Step 4), multi-call sequence ===")
    policy = V8Policy(BALANCED, adaptive=False)

    # Deliberately retreats INTO a second 2-Prize ex (Meowth ex), not a
    # 1-Prize Pokemon -- otherwise STEP 5's exclusion, not the anti-thrash
    # guard, would be the reason a repeat never re-fires, which would prove
    # nothing about STEP 4 specifically.
    ready_meowth = (MEOWTH_EX, 170, 170, 3)   # affords Tuck Tail (60dmg/[0,0,0])
    ready_dreepy = (DREEPY, 70, 70, 1)

    # Turn N: Dragapult ex (serial=1) is lethally threatened, Meowth ex
    # (serial=10) is ready on the bench. Fires -> RETREAT chosen.
    my_active = _pokemon(DRAGAPULT_EX, 1, 200, 320, 1)
    op_active = _pokemon(EX_ID, 500, 280, 280, 4)
    meowth_bench = _pokemon(ready_meowth[0], 10, ready_meowth[1], ready_meowth[2], ready_meowth[3])
    obs1 = make_retreat_obs(my_active, [meowth_bench], op_active, [153], turn=10)
    action1 = policy.agent(obs1)
    check("partc_turn_n_fires", 0 in action1, f"turn N: RETREAT chosen (action={action1})")
    check("partc_pending_set", policy._survival_retreat_pending is True, "pending flag set after firing")

    # Simulate the retreat resolving: a later call now shows Meowth ex
    # (serial=10) as the Active. Bookkeeping should snapshot it and clear the
    # pending flag -- a no-op MAIN call (no RETREAT offered) purely to let
    # the bookkeeping run, exactly as it would on the resulting Active's own
    # subsequent decisions.
    meowth_active = _pokemon(MEOWTH_EX, 10, 170, 170, 3)
    obs2 = make_retreat_obs(meowth_active, [], op_active, [1546], can_switch=False, turn=10)
    policy.agent(obs2)
    check("partc_pending_resolved", policy._survival_retreat_pending is False, "pending flag cleared once the new Active (serial=10) is observed")
    check("partc_snapshot_serial", policy._last_survival_retreat_serial == 10, f"snapshotted serial=10, got {policy._last_survival_retreat_serial}")
    check("partc_snapshot_hp", policy._last_survival_retreat_hp == 170, f"snapshotted hp=170, got {policy._last_survival_retreat_hp}")
    check("partc_snapshot_op_serial", policy._last_survival_retreat_op_serial == 500, f"snapshotted op_serial=500, got {policy._last_survival_retreat_op_serial}")

    # Turn N+2: Meowth ex (serial=10) is STILL active, STILL at 170 HP
    # (nothing happened to it), facing the SAME opponent Pokemon (serial=500),
    # which is STILL lethally threatening it (Thunderous Bolt 230 >= 170). A
    # second ready Bench replacement (Dreepy) exists, and Meowth ex still
    # can't trade (Tuck Tail 60 < opponent's 280 HP). Per STEP 4, this MUST
    # NOT re-fire -- nothing has actually changed since we already retreated
    # to save this exact Pokemon from this exact threat.
    dreepy_bench = _pokemon(ready_dreepy[0], 11, ready_dreepy[1], ready_dreepy[2], ready_dreepy[3])
    obs3 = make_retreat_obs(meowth_active, [dreepy_bench], op_active, [1546], turn=12)
    action3 = policy.agent(obs3)
    check("partc_stale_repeat_blocked", 0 not in action3, f"turn N+2 (unchanged state): RETREAT NOT chosen (action={action3}) -- anti-thrash guard held")

    # Turn N+4: the SAME Meowth ex (serial=10) took some non-lethal chip
    # damage (170 -> 140 HP) -- genuinely new information. The guard must NOT
    # block this: it should be free to retreat again if the threat is still
    # lethal (230 >= 140, still true).
    meowth_damaged = _pokemon(MEOWTH_EX, 10, 140, 170, 3)
    obs4 = make_retreat_obs(meowth_damaged, [dreepy_bench], op_active, [1546], turn=14)
    action4 = policy.agent(obs4)
    check("partc_new_info_unblocks", 0 in action4, f"turn N+4 (HP changed 170->140, new info): RETREAT chosen again (action={action4})")


def main() -> int:
    part_a_phantom_dive_regression()
    part_b_scenarios()
    part_c_anti_thrash()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print(f"PASS: all V8 survival-retreat checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
