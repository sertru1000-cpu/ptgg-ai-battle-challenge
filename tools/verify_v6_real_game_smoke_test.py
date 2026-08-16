"""Ad hoc local validation for V6: real games through the actual compiled
engine (not the synthetic fixtures in verify_phantom_dive_v6_fixes.py),
mirroring tools/verify_v2_engine_equivalence.py's harness. Confirms V6
produces only legal actions across full real games, both self-play and vs.
an existing opponent, and specifically checks whether Phantom Dive was ever
exercised for real by V6 in these games (informational only -- Phantom Dive
usage depends on real draws/board development, not guaranteed every game).
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

import cg.game as g  # noqa: E402
from cg.api import to_observation_class, SelectContext  # noqa: E402

from src.agents.dragapult_agent_v6 import agent as v6_agent, DECK as V6_DECK  # noqa: E402
from src.agents.dragapult_agent_v2 import agent as v2_agent, DECK as V2_DECK  # noqa: E402
from src.agents.abomasnow_agent import agent as opp_agent, DECK as OPP_DECK  # noqa: E402


def run_game(deck0, agent0, deck1, agent1, max_steps=2000):
    obs, start = g.battle_start(deck0, deck1)
    if start.errorPlayer != -1:
        raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")
    fns = [agent0, agent1]
    steps = 0
    phantom_dive_counter_selects = 0
    try:
        while obs["current"]["result"] < 0 and steps < max_steps:
            obs.pop("search_begin_input", None)
            idx = obs["current"]["yourIndex"]
            o = to_observation_class(obs)
            if idx == 0 and o.select is not None and o.select.context == SelectContext.DAMAGE_COUNTER_ANY:
                phantom_dive_counter_selects += 1
            action = fns[idx](obs)
            assert isinstance(action, list), f"non-list action: {action}"
            opts = obs["select"]["option"]
            mn, mx = obs["select"]["minCount"], obs["select"]["maxCount"]
            assert mn <= len(action) <= mx, f"action length {len(action)} not in [{mn},{mx}]"
            assert len(set(action)) == len(action), f"duplicate indices: {action}"
            assert all(0 <= i < len(opts) for i in action), f"out-of-range index in {action}"
            obs = g.battle_select(action)
            steps += 1
    finally:
        g.battle_finish()
    assert steps < max_steps, "game did not finish within max_steps"
    return obs["current"]["result"], steps, phantom_dive_counter_selects


def main() -> int:
    print("Game 1: V6 (slot0) self-play vs V6 (slot1)")
    result, steps, pd = run_game(V6_DECK, v6_agent, V6_DECK, v6_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0)={pd}")

    print("Game 2: V6 (slot0) vs abomasnow_agent (slot1)")
    result, steps, pd = run_game(V6_DECK, v6_agent, OPP_DECK, opp_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0)={pd}")

    print("Game 3: V6 (slot0) vs V2 (slot1) -- head to head sanity check")
    result, steps, pd = run_game(V6_DECK, v6_agent, V2_DECK, v2_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0, V6)={pd}")

    print("\nSMOKE TEST: PASS -- V6 produced only legal actions across all games.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
