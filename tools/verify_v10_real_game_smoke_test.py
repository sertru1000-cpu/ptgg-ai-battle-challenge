"""V10 Test 4 -- basic gameplay smoke test (V10_IMPLEMENTATION_REPORT.md /
governing task's LOCAL VALIDATION Test 4). Real games through the actual
compiled engine (not synthetic fixtures), mirroring
tools/verify_v8_real_game_smoke_test.py's harness.

Confirms across several full real games (self-play, vs. V7 head-to-head, vs.
existing opponents):
  - no crash;
  - every action V10 selects is legal (in-range, correct count, no dupes);
  - no infinite retreat loop (games finish within max_steps);
  - the agent actually attacks at least once;
  - the agent actually plays Buddy-Buddy Poffin at least once;
  - the agent actually evolves Dreepy->Drakloak or Drakloak->Dragapult ex
    (or plays Dragapult ex via Rare Candy... note: V10's deck has no Rare
    Candy, so this checks the EVOLVE option specifically) at least once
    somewhere across the games;
  - normal turns execute (TURN_END-style progress, i.e. steps > 0 and the
    game reaches a result).
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

import cg.game as g  # noqa: E402
from cg.api import to_observation_class, OptionType, SelectContext  # noqa: E402

from src.agents.dragapult_agent_v10 import agent as v10_agent, DECK as V10_DECK  # noqa: E402
from src.agents.dragapult_agent_v7 import agent as v7_agent, DECK as V7_DECK  # noqa: E402
from src.agents.abomasnow_agent import agent as opp_agent, DECK as OPP_DECK  # noqa: E402
from src.agents.generic_mewtwo_agent import agent as mewtwo_agent, DECK as MEWTWO_DECK  # noqa: E402

BUDDY_BUDDY_POFFIN = 1086
DRAGAPULT_EX = 121
DRAKLOAK = 120

FAILURES = []


def check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


def run_game(deck0, agent0, deck1, agent1, max_steps=2000):
    """Runs one full real game, tracking V10-relevant activity for player 0
    only (agent0 is always the V10 seat in this suite).
    """
    obs, start = g.battle_start(deck0, deck1)
    if start.errorPlayer != -1:
        raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")
    fns = [agent0, agent1]
    steps = 0
    attacked = False
    played_poffin = False
    evolved = False
    phantom_dive_counter_selects = 0
    try:
        while obs["current"]["result"] < 0 and steps < max_steps:
            obs.pop("search_begin_input", None)
            idx = obs["current"]["yourIndex"]
            o = to_observation_class(obs)
            if idx == 0 and o.select is not None:
                if o.select.context == SelectContext.DAMAGE_COUNTER_ANY:
                    phantom_dive_counter_selects += 1
            action = fns[idx](obs)
            assert isinstance(action, list), f"non-list action: {action}"
            opts = obs["select"]["option"]
            mn, mx = obs["select"]["minCount"], obs["select"]["maxCount"]
            assert mn <= len(action) <= mx, f"action length {len(action)} not in [{mn},{mx}]"
            assert len(set(action)) == len(action), f"duplicate indices: {action}"
            assert all(0 <= i < len(opts) for i in action), f"out-of-range index in {action}"

            if idx == 0:
                for i in action:
                    opt = opts[i]
                    otype = opt.get("type")
                    if otype == int(OptionType.ATTACK):
                        attacked = True
                    elif otype == int(OptionType.PLAY):
                        card = o.current.players[0].hand[opt["index"]] if o.select is not None else None
                        if card is not None and card.id == BUDDY_BUDDY_POFFIN:
                            played_poffin = True
                    elif otype == int(OptionType.EVOLVE):
                        evolved = True

            obs = g.battle_select(action)
            steps += 1
    finally:
        g.battle_finish()
    assert steps < max_steps, "game did not finish within max_steps (possible infinite loop)"
    return dict(
        result=obs["current"]["result"], steps=steps, attacked=attacked,
        played_poffin=played_poffin, evolved=evolved,
        phantom_dive_counter_selects=phantom_dive_counter_selects,
    )


def main() -> int:
    print("=== TEST 4 -- V10 real-game smoke test ===")

    any_attacked = False
    any_poffin = False
    any_evolved = False

    print("\nGame 1: V10 (slot0) self-play vs V10 (slot1)")
    r = run_game(V10_DECK, v10_agent, V10_DECK, v10_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_evolved |= r["evolved"]

    print("\nGame 2: V10 (slot0) vs abomasnow_agent (slot1)")
    r = run_game(V10_DECK, v10_agent, OPP_DECK, opp_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_evolved |= r["evolved"]

    print("\nGame 3: V10 (slot0) vs V7 (slot1) -- head-to-head sanity check (V10's own deck vs V7's old deck)")
    r = run_game(V10_DECK, v10_agent, V7_DECK, v7_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_evolved |= r["evolved"]

    print("\nGame 4: V10 (slot0) vs generic Mewtwo ex agent (slot1)")
    r = run_game(V10_DECK, v10_agent, MEWTWO_DECK, mewtwo_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_evolved |= r["evolved"]

    print("\n=== Cross-game summary checks ===")
    check("no_crash", True, "all 4 games completed without a crash or assertion failure (games would have raised otherwise)")
    check("can_attack", any_attacked, "V10 selected at least one ATTACK action across the 4 games")
    check("can_play_poffin", any_poffin, "V10 played Buddy-Buddy Poffin at least once across the 4 games")
    check("can_evolve", any_evolved, "V10 selected at least one EVOLVE action (Dreepy->Drakloak or Drakloak->Dragapult ex) across the 4 games")

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: V10 produced only legal actions across all games; attacked, played Buddy-Buddy Poffin, and evolved at least once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
