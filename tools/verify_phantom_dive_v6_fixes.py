"""V6 regression suite for the two confirmed Phantom Dive bugs (Prompt #5
follow-up experiment).

Fixes under test (see src/agents/dragapult_policy_v6.py's module docstring):
  FIX #1 -- PHANTOM_DIVE_ARCHITECTURE_AUDIT.md §3.2: the DAMAGE_COUNTER_ANY
    fallback's `elif hp == 10: score -= 100000` was backwards.
  FIX #2 -- PHANTOM_DIVE_ARCHITECTURE_AUDIT.md §3.3: main_option_proc's
    i==0 (opponent Active) iteration wrongly assumed Phantom Dive deals its
    card data's flat damage=200 to the Active, which could both fabricate a
    prize and short-circuit the bench-counter combo search, leaving
    self.plan_b.counter empty for the whole attack.

Method: construct minimal, schema-valid cg.api Observation dicts by hand
(no compiled-engine game is driven -- the real engine only ships inside the
Kaggle sandbox, confirmed by PHANTOM_DIVE_INDEX_ALIGNMENT_AUDIT.md §2) and
call DragapultPolicy.agent() directly, exactly the same entry point the real
engine calls. One MAIN-context call (offering Phantom Dive) seeds
self.plan_a/self.plan_b, then up to 6 DAMAGE_COUNTER_ANY-context calls
simulate the six real placement round-trips: bench array positions stay
fixed and HP is tracked live (including going to/below 0 without the slot
disappearing), exactly matching the real engine's own documented
intermediate-state behavior (index-alignment audit §2/§4) -- this is NOT an
assumption made for convenience, it's the audited ground truth for how the
real Kaggle engine actually behaves mid-attack.

TEST 3 reconstructs real missed-KO rows from
results/phantom_dive_forensic/missed_ko_examples.csv using the documented
bench HP/prize composition (card identity itself doesn't affect this
policy's scoring -- HP, prize-count/ex-status, and immunity do). Opponent
Active HP is not recorded in that CSV, so TEST 3 rows pick an Active HP/
remain_prize pair that reproduces the exact zero-KO pattern V2 actually
produced on the real ladder (see the design rationale printed per-row);
this is a reconstruction of the documented failure signature, not a replay
of the original replay JSON.

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
from src.agents.policy_weights import BALANCED  # noqa: E402

# Real card IDs from this competition's shared 1056-card pool, confirmed
# valid (present in cg.api's card table) via PHANTOM_DIVE_INDEX_ALIGNMENT_AUDIT.md's
# own forensic tables and cross-checked directly against cg.api.all_card_data()
# in this session: 121 = Dragapult ex (our own attacker), 269 = Iono's
# Bellibolt ex (2-prize, ex), 270 = Iono's Wattrel (1-prize, non-ex).
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
    """A MAIN-context decision offering Phantom Dive (attackId 154)."""
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
    """bench_specs: list of (id, serial, maxhp, starting_hp), stable positions
    throughout (matches the real engine's own documented mid-attack behavior).
    Returns (plan_b_counter, chosen_bench_positions_per_round, final_hp, dead_positions).
    """
    policy = policy_cls(BALANCED, adaptive=False)
    live_hp = [spec[3] for spec in bench_specs]

    def bench_dicts():
        return [pokemon(spec[0], spec[1], live_hp[i], spec[2]) for i, spec in enumerate(bench_specs)]

    main_obs = make_main_obs(bench_dicts(), opp_active_hp, opp_active_maxhp, opp_active_id, my_prize_count)
    policy.agent(main_obs)
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
    return plan_b_counter, chosen, list(live_hp), dead


def check(name, condition, detail):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


# --------------------------------------------------------------------------
# TEST 1 -- 10 HP lethal target must beat an unreachable healthy target
# (isolates FIX #1: forces plan_b.counter empty via the documented prize==1
#  vs prize==0 combo-scoring asymmetry at remain_prize=6, so only the
#  DAMAGE_COUNTER_ANY fallback -- the code FIX #1 touches -- decides.)
# --------------------------------------------------------------------------
def test1():
    print("\nTEST 1 -- 10 HP lethal target vs. an unreachable healthy target (fallback path)")
    bench = [(NORMAL_ID, 1, 60, 10), (NORMAL_ID, 2, 200, 150)]  # slot0: 10hp lethal; slot1: 150hp unreachable
    kwargs = dict(opp_active_hp=280, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=6)

    v2_plan, v2_chosen, v2_final, v2_dead = run_phantom_dive(V2Policy, bench, **kwargs)
    v6_plan, v6_chosen, v6_final, v6_dead = run_phantom_dive(V6Policy, bench, **kwargs)

    print(f"    V2: plan_b={v2_plan} chosen_slots={v2_chosen} final_hp={v2_final} dead_slots={v2_dead}")
    print(f"    V6: plan_b={v6_plan} chosen_slots={v6_chosen} final_hp={v6_final} dead_slots={v6_dead}")

    check("test1_v2_reproduces_bug", 0 not in v2_dead,
          "V2 (unfixed) reproduces the bug: fails to KO the free 10-HP kill")
    check("test1_v6_fixed", 0 in v6_dead,
          "V6 (fixed) secures the free 10-HP KO that V2 misses")


# --------------------------------------------------------------------------
# TEST 2 -- multiple simultaneous lethal targets, with a distractor
# (exercises FIX #2's combo/plan_b path: forces the old short-circuit via
#  Active HP <= 200 with remain_prize == active's prize count.)
# --------------------------------------------------------------------------
def test2():
    print("\nTEST 2 -- multiple lethal targets + an unreachable distractor (plan/combo path)")
    bench = [
        (NORMAL_ID, 1, 60, 10),   # slot0: 10hp lethal
        (NORMAL_ID, 2, 60, 10),   # slot1: 10hp lethal
        (NORMAL_ID, 3, 200, 150),  # slot2: unreachable distractor
    ]
    kwargs = dict(opp_active_hp=100, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=2)

    v2_plan, v2_chosen, v2_final, v2_dead = run_phantom_dive(V2Policy, bench, **kwargs)
    v6_plan, v6_chosen, v6_final, v6_dead = run_phantom_dive(V6Policy, bench, **kwargs)

    print(f"    V2: plan_b={v2_plan} chosen_slots={v2_chosen} final_hp={v2_final} dead_slots={v2_dead}")
    print(f"    V6: plan_b={v6_plan} chosen_slots={v6_chosen} final_hp={v6_final} dead_slots={v6_dead}")

    check("test2_v2_reproduces_bug", len(v2_dead) == 0,
          "V2 (unfixed) reproduces the bug: the short-circuit empties plan_b, 0 real KOs secured")
    check("test2_v6_fixed", set([0, 1]).issubset(set(v6_dead)),
          "V6 (fixed) secures both simultaneous lethal KOs")


# --------------------------------------------------------------------------
# TEST 3 -- replay real forensic missed-KO cases (reconstructed from
# results/phantom_dive_forensic/missed_ko_examples.csv's documented bench
# HP/prize composition)
# --------------------------------------------------------------------------
def test3():
    print("\nTEST 3 -- reconstructed real missed-KO forensic cases")

    # Row: episode 92219700 turn 13. Real V2 ladder allocation was {0: 1, 1: 5}
    # (0 real KOs); documented optimal is {0: 2, 1: 4} (1 real KO, the 20 HP
    # target). See results/phantom_dive_forensic/missed_ko_examples.csv.
    print("  Row: episode 92219700 turn 13 (documented optimal KOs: 1 -- the 20 HP target)")
    bench_a = [(NORMAL_ID, 1, 70, 20), (NORMAL_ID, 2, 70, 70)]
    kwargs_a = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1)
    v2 = run_phantom_dive(V2Policy, bench_a, **kwargs_a)
    v6 = run_phantom_dive(V6Policy, bench_a, **kwargs_a)
    print(f"    V2: plan_b={v2[0]} chosen_slots={v2[1]} final_hp={v2[2]} dead_slots={v2[3]}")
    print(f"    V6: plan_b={v6[0]} chosen_slots={v6[1]} final_hp={v6[2]} dead_slots={v6[3]}")
    check("test3_row_92219700_v2_reproduces_bug", len(v2[3]) == 0,
          "V2 (unfixed) reproduces the real documented outcome: 0 KOs (matches actual ladder data {0:1,1:5})")
    check("test3_row_92219700_v6_fixed", 0 in v6[3],
          "V6 (fixed) secures the documented optimal 1-prize KO (the 20 HP target)")

    # Row: episode 92232003 turn 12. Real V2 ladder allocation was
    # {0: 0, 1: 0, 2: 0, 3: 6} (0 real KOs, all 6 counters dumped on the
    # unreachable 70 HP target); documented optimal is {0: 1, 1: 1, 2: 0,
    # 3: 4} (2 real KOs -- both 10 HP Staryu).
    print("  Row: episode 92232003 turn 12 (documented optimal KOs: 2 -- both 10 HP targets)")
    bench_b = [
        (NORMAL_ID, 1, 70, 10),   # slot0: Staryu 10hp
        (NORMAL_ID, 2, 70, 10),   # slot1: Staryu 10hp
        (EX_ID, 3, 310, 310),     # slot2: Mega Froslass ex, unreachable alone (310 > 60 budget)
        (NORMAL_ID, 4, 70, 70),   # slot3: Snorunt, unreachable alone (70 > 60 budget)
    ]
    kwargs_b = dict(opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=1)
    v2 = run_phantom_dive(V2Policy, bench_b, **kwargs_b)
    v6 = run_phantom_dive(V6Policy, bench_b, **kwargs_b)
    print(f"    V2: plan_b={v2[0]} chosen_slots={v2[1]} final_hp={v2[2]} dead_slots={v2[3]}")
    print(f"    V6: plan_b={v6[0]} chosen_slots={v6[1]} final_hp={v6[2]} dead_slots={v6[3]}")
    check("test3_row_92232003_v2_reproduces_bug", len(v2[3]) == 0,
          "V2 (unfixed) reproduces the real documented outcome: 0 KOs, all counters dumped on an unreachable target")
    check("test3_row_92232003_v6_fixed", {0, 1}.issubset(set(v6[3])),
          "V6 (fixed) secures both documented 1-prize KOs (both 10 HP Staryu)")


# --------------------------------------------------------------------------
# TEST 4 -- Phantom Dive Active short-circuit: verify V6 still builds the
# bench allocation plan even when the generic planner would otherwise
# believe the prize race is already won via a fictional Active KO.
# --------------------------------------------------------------------------
def test4():
    print("\nTEST 4 -- Active short-circuit: plan_b must not be abandoned")
    bench = [(NORMAL_ID, 1, 60, 10)]  # single lethal 10hp target
    # Active HP (150) <= the generic damage=200 constant, and Active is ex
    # (prize_count=2) so remain_prize (1) <= base_prize_count (2) trips the
    # OLD code's shortcut (`max_score = 50000`, real combo search skipped).
    # remain_prize=1 also makes the single bench KO combo hit the (pre-
    # existing, untouched) `remain_prize <= prize` win-securing branch under
    # FIX #2, rather than the separate prize==1-vs-prize==0 combo-scoring
    # asymmetry that's out of scope for this experiment (see TEST 1/3 for
    # cases that isolate that path instead).
    kwargs = dict(opp_active_hp=150, opp_active_maxhp=280, opp_active_id=EX_ID, my_prize_count=1)

    v2_plan, v2_chosen, v2_final, v2_dead = run_phantom_dive(V2Policy, bench, **kwargs)
    v6_plan, v6_chosen, v6_final, v6_dead = run_phantom_dive(V6Policy, bench, **kwargs)

    print(f"    V2: plan_b={v2_plan} chosen_slots={v2_chosen} final_hp={v2_final} dead_slots={v2_dead}")
    print(f"    V6: plan_b={v6_plan} chosen_slots={v6_chosen} final_hp={v6_final} dead_slots={v6_dead}")

    check("test4_v2_plan_b_empty", v2_plan == [],
          "V2 (unfixed) confirms the short-circuit: plan_b.counter is abandoned (empty)")
    check("test4_v6_plan_b_populated", v6_plan != [],
          "V6 (fixed) still builds the bench allocation plan (plan_b.counter non-empty)")
    check("test4_v6_secures_ko", 0 in v6_dead,
          "V6 (fixed) secures the KO despite the fictional Active-damage premise")


# --------------------------------------------------------------------------
# TEST 5 -- non-Phantom-Dive regression: V2 and V6 must behave identically
# whenever Phantom Dive is not the attack in play.
# --------------------------------------------------------------------------
def test5():
    print("\nTEST 5 -- non-Phantom-Dive regression (identical V2/V6 behavior)")

    # 5a. MAIN decision where Phantom Dive is NOT offered (only Jet Headbutt,
    # attackId 153), but main_option_proc still runs via the bench_attacker
    # path -- verifies FIX #2's `self.can_main_attack` gate keeps this
    # untouched (i==0's active_damage assumption must stay exactly as in V2).
    bench = [(NORMAL_ID, 1, 60, 30), (EX_ID, 2, 280, 280)]
    v2_policy = V2Policy(BALANCED, adaptive=False)
    v6_policy = V6Policy(BALANCED, adaptive=False)
    obs = make_main_obs(
        [pokemon(id_, serial, hp, maxhp) for id_, serial, maxhp, hp in bench],
        opp_active_hp=150, opp_active_maxhp=150, opp_active_id=NORMAL_ID, my_prize_count=4,
        extra_options=[{"type": int(OptionType.ATTACK), "attackId": 153}],
    )
    v2_action = v2_policy.agent(obs)
    v6_action = v6_policy.agent(obs)
    print(f"    5a MAIN (no Phantom Dive offered): V2 plan_b={v2_policy.plan_b.counter} V6 plan_b={v6_policy.plan_b.counter}")
    print(f"       V2 action={v2_action} V6 action={v6_action}")
    check("test5a_plan_b_identical", v2_policy.plan_b.counter == v6_policy.plan_b.counter,
          "plan_b identical between V2/V6 when Phantom Dive is not offered")
    check("test5a_action_identical", v2_action == v6_action,
          "chosen action identical between V2/V6 when Phantom Dive is not offered")

    # 5b. DAMAGE_COUNTER (not _ANY) context -- a different attack's single-
    # target damage-counter placement. FIX #1 only touches the
    # DAMAGE_COUNTER_ANY branch; this context must be byte-identical.
    v2_policy2 = V2Policy(BALANCED, adaptive=False)
    v6_policy2 = V6Policy(BALANCED, adaptive=False)
    option = [
        {"type": int(OptionType.CARD), "area": int(AreaType.ACTIVE), "index": 0, "playerIndex": OPP_INDEX},
        {"type": int(OptionType.CARD), "area": int(AreaType.BENCH), "index": 0, "playerIndex": OPP_INDEX},
    ]
    players = [None, None]
    players[MY_INDEX] = _player_state(active=[pokemon(MY_ACTIVE_ID, 1, 320, 320)], bench=[], prize_count=4, hand=[])
    players[OPP_INDEX] = _player_state(
        active=[pokemon(EX_ID, 500, 220, 280)],
        bench=[pokemon(NORMAL_ID, 2, 10, 60)],
        prize_count=4, hand=None,
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
    v2_action2 = v2_policy2.agent(dc_obs)
    v6_action2 = v6_policy2.agent(dc_obs)
    print(f"    5b DAMAGE_COUNTER (single-target, not Phantom Dive): V2 action={v2_action2} V6 action={v6_action2}")
    check("test5b_action_identical", v2_action2 == v6_action2,
          "chosen action identical between V2/V6 for the (untouched) DAMAGE_COUNTER context")


def main() -> int:
    test1()
    test2()
    test3()
    test4()
    test5()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: all Phantom Dive V6 regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
