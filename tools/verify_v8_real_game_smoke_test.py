"""Ad hoc local validation for V8: real games through the actual compiled
engine (not the synthetic fixtures in verify_v8_survival_retreat.py),
mirroring tools/verify_v6_real_game_smoke_test.py's harness. Confirms V8
produces only legal actions across full real games (self-play, vs. V7 head to
head, vs. an existing opponent), and reports whether the new survival-retreat
hook and Phantom Dive were ever exercised for real (informational only --
both depend on real draws/board development, not guaranteed every game).
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

import cg.game as g  # noqa: E402
from cg.api import to_observation_class, SelectContext  # noqa: E402

from src.agents.dragapult_agent_v8 import agent as v8_agent, DECK as V8_DECK  # noqa: E402
from src.agents.dragapult_agent_v7 import agent as v7_agent, DECK as V7_DECK  # noqa: E402
from src.agents.abomasnow_agent import agent as opp_agent, DECK as OPP_DECK  # noqa: E402
from src.agents.lucario_ex_agent import agent as lucario_agent, DECK as LUCARIO_DECK  # noqa: E402
from src.agents.generic_mewtwo_agent import agent as mewtwo_agent, DECK as MEWTWO_DECK  # noqa: E402


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
    v8_policy = v8_agent.policy  # type: ignore[attr-defined]

    print("Game 1: V8 (slot0) self-play vs V8 (slot1)")
    result, steps, pd = run_game(V8_DECK, v8_agent, V8_DECK, v8_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0)={pd}")
    print(f"  survival_retreat_log so far (slot0 instance): {len(v8_policy.survival_retreat_log)} entries")

    print("Game 2: V8 (slot0) vs abomasnow_agent (slot1)")
    result, steps, pd = run_game(V8_DECK, v8_agent, OPP_DECK, opp_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0)={pd}")
    print(f"  survival_retreat_log so far (slot0 instance): {len(v8_policy.survival_retreat_log)} entries")

    print("Game 3: V8 (slot0) vs V7 (slot1) -- head to head sanity check")
    result, steps, pd = run_game(V8_DECK, v8_agent, V7_DECK, v7_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0, V8)={pd}")
    print(f"  survival_retreat_log so far (slot0 instance): {len(v8_policy.survival_retreat_log)} entries")

    print("Game 4: V8 (slot0) vs Mega Lucario ex agent (slot1) -- a hard-hitting attacker, best real-game chance of a guaranteed lethal on our Active")
    result, steps, pd = run_game(V8_DECK, v8_agent, LUCARIO_DECK, lucario_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0)={pd}")
    print(f"  survival_retreat_log so far (slot0 instance): {len(v8_policy.survival_retreat_log)} entries")

    print("Game 5: V8 (slot0) vs generic Mewtwo ex agent (slot1)")
    result, steps, pd = run_game(V8_DECK, v8_agent, MEWTWO_DECK, mewtwo_agent)
    print(f"  OK: result={result} steps={steps} phantom_dive_counter_selects(slot0)={pd}")
    print(f"  survival_retreat_log so far (slot0 instance): {len(v8_policy.survival_retreat_log)} entries")

    print(f"\nTotal survival-retreat activations across all 5 games (slot0 V8 instance, cumulative/shared instance): {len(v8_policy.survival_retreat_log)}")
    for entry in v8_policy.survival_retreat_log:
        print(f"    {entry}")

    print("\nSMOKE TEST: PASS -- V8 produced only legal actions across all 5 games.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
