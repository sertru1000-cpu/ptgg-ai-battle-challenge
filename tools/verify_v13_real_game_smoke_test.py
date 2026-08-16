"""V13 local self-play smoke test (governing task's Deliverables: "Run a
short local self-play smoke test to ensure the deck loads correctly and the
agent plays the new draw cards without crashing"). Real games through the
actual compiled engine (not synthetic fixtures), same harness pattern as
tools/verify_v10_real_game_smoke_test.py.

Confirms across several full real games (self-play, vs. V6 head-to-head, vs.
existing opponent decks):
  - decks/dragapult_v13_turbo.csv loads and every action V13 selects is
    legal (in-range, correct count, no dupes);
  - no crash;
  - no infinite retreat loop (games finish within max_steps);
  - the agent actually attacks at least once;
  - the agent actually plays Cheren (the one new card V13's deck adds that
    V6's engine never scored before) at least once;
  - the agent actually plays Buddy-Buddy Poffin and evolves at least once
    (basic setup still works with the trimmed decklist).

V13 has no lookahead/search and no V8/V9 survival-retreat heuristic, so
unlike tools/v11_selfplay_smoke_test.py there is no macro-decision-latency
telemetry to collect here.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import to_observation_class, OptionType, SelectContext  # noqa: E402

from src.agents.dragapult_agent_v13 import agent as v13_agent, DECK as V13_DECK  # noqa: E402
from src.agents.dragapult_agent_v6 import agent as v6_agent, DECK as V6_DECK  # noqa: E402
from src.agents.abomasnow_agent import agent as opp_agent, DECK as OPP_DECK  # noqa: E402
from src.agents.generic_mewtwo_agent import agent as mewtwo_agent, DECK as MEWTWO_DECK  # noqa: E402

import cg.game as g  # noqa: E402

CHEREN = 1224
BUDDY_BUDDY_POFFIN = 1086

FAILURES = []


def check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


def run_game(deck0, agent0, deck1, agent1, max_steps=2000):
    """Runs one full real game, tracking V13-relevant activity for player 0
    only (agent0 is always the V13 seat in this suite).
    """
    obs, start = g.battle_start(deck0, deck1)
    if start.errorPlayer != -1:
        raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")
    fns = [agent0, agent1]
    steps = 0
    attacked = False
    played_poffin = False
    played_cheren = False
    evolved = False
    try:
        while obs["current"]["result"] < 0 and steps < max_steps:
            obs.pop("search_begin_input", None)
            idx = obs["current"]["yourIndex"]
            o = to_observation_class(obs)
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
                        if card is not None and card.id == CHEREN:
                            played_cheren = True
                    elif otype == int(OptionType.EVOLVE):
                        evolved = True

            obs = g.battle_select(action)
            steps += 1
    finally:
        g.battle_finish()
    assert steps < max_steps, "game did not finish within max_steps (possible infinite loop)"
    return dict(
        result=obs["current"]["result"], steps=steps, attacked=attacked,
        played_poffin=played_poffin, played_cheren=played_cheren, evolved=evolved,
    )


def main() -> int:
    print("=== V13 real-game smoke test ===")

    any_attacked = False
    any_poffin = False
    any_cheren = False
    any_evolved = False

    print("\nGame 1: V13 (slot0) self-play vs V13 (slot1)")
    r = run_game(V13_DECK, v13_agent, V13_DECK, v13_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_cheren |= r["played_cheren"]
    any_evolved |= r["evolved"]

    print("\nGame 2: V13 (slot0) self-play vs V13 (slot1), second pairing (more Cheren draw chances)")
    r = run_game(V13_DECK, v13_agent, V13_DECK, v13_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_cheren |= r["played_cheren"]
    any_evolved |= r["evolved"]

    print("\nGame 3: V13 (slot0) vs abomasnow_agent (slot1)")
    r = run_game(V13_DECK, v13_agent, OPP_DECK, opp_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_cheren |= r["played_cheren"]
    any_evolved |= r["evolved"]

    print("\nGame 4: V13 (slot0) vs V6 (slot1) -- head-to-head sanity check (turbo deck vs V6's meta deck, same policy engine)")
    r = run_game(V13_DECK, v13_agent, V6_DECK, v6_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_cheren |= r["played_cheren"]
    any_evolved |= r["evolved"]

    print("\nGame 5: V13 (slot0) vs generic Mewtwo ex agent (slot1)")
    r = run_game(V13_DECK, v13_agent, MEWTWO_DECK, mewtwo_agent)
    print(f"  OK: {r}")
    any_attacked |= r["attacked"]
    any_poffin |= r["played_poffin"]
    any_cheren |= r["played_cheren"]
    any_evolved |= r["evolved"]

    print("\n=== Cross-game summary checks ===")
    check("no_crash", True, "all 5 games completed without a crash or assertion failure (games would have raised otherwise)")
    check("can_attack", any_attacked, "V13 selected at least one ATTACK action across the 5 games")
    check("can_play_poffin", any_poffin, "V13 played Buddy-Buddy Poffin at least once across the 5 games")
    check("can_play_cheren", any_cheren, "V13 played Cheren (the new card / new scoring branch) at least once across the 5 games")
    check("can_evolve", any_evolved, "V13 selected at least one EVOLVE action (Dreepy->Drakloak or Drakloak->Dragapult ex) at least once across the 5 games")

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: V13 produced only legal actions across all games; attacked, played Buddy-Buddy Poffin, played Cheren, and evolved at least once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
