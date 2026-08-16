"""Mechanical proof that src/agents/dragapult_policy_v2plus.py (the shared
Prompt #5 engine) reproduces src/agents/dragapult_agent_always_first.py
(V1/BASELINE's actual production policy) EXACTLY when run at NEUTRAL
weights, before any of the four real V2-V5 profiles are trusted.

Method: play real games through the actual engine with V1 driving play (its
own return value is what actually advances the game), and at EVERY decision
V1 makes, ALSO feed the identical observation to a freshly-constructed
NEUTRAL-weighted DragapultPolicy instance and compare its returned index
list to V1's. The clone's output never touches the real game -- it is purely
observed and diffed. Because both sides receive the exact same input
sequence and (if the port is correct) compute identically, any divergence is
a genuine porting bug, not sampling noise (this engine has no RNG seed
control, but that only affects WHICH observations occur across games, not
whether two policies presented with the SAME observation agree).

Exit code 0 and "EQUIVALENCE VERIFIED" iff zero divergences across every
decision in every game played.
"""

import argparse
import sys

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

import cg.game as g  # noqa: E402
from cg.api import to_observation_class  # noqa: E402

from src.agents.dragapult_agent_always_first import agent as v1_agent, DECK as V1_DECK  # noqa: E402
from src.agents.dragapult_policy_v2plus import make_agent  # noqa: E402
from src.agents.policy_weights import NEUTRAL  # noqa: E402
from src.agents.abomasnow_agent import agent as opponent_agent, DECK as OPP_DECK  # noqa: E402


def run(n_games: int, max_steps: int) -> int:
    total_decisions = 0
    divergences = []

    for game_index in range(n_games):
        clone_agent = make_agent(NEUTRAL, adaptive=False, always_first=True)
        v1_slot0 = game_index % 2 == 0
        deck0 = V1_DECK if v1_slot0 else OPP_DECK
        deck1 = OPP_DECK if v1_slot0 else V1_DECK
        v1_slot = 0 if v1_slot0 else 1

        obs, start = g.battle_start(deck0, deck1)
        if start.errorPlayer != -1:
            raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")

        steps = 0
        try:
            while obs["current"]["result"] < 0 and steps < max_steps:
                obs.pop("search_begin_input", None)
                idx = obs["current"]["yourIndex"]
                if idx == v1_slot:
                    v1_action = v1_agent(obs)
                    clone_action = clone_agent(obs)
                    total_decisions += 1
                    if sorted(v1_action) != sorted(clone_action):
                        divergences.append(
                            {
                                "game": game_index,
                                "step": steps,
                                "context": to_observation_class(obs).select.context,
                                "v1_action": v1_action,
                                "clone_action": clone_action,
                            }
                        )
                    action = v1_action
                else:
                    action = opponent_agent(obs)
                obs = g.battle_select(action)
                steps += 1
        finally:
            g.battle_finish()

        print(f"  game {game_index + 1}/{n_games}: v1_slot={v1_slot} steps={steps} decisions_so_far={total_decisions} divergences_so_far={len(divergences)}")

    print()
    print(f"Total V1 decisions compared: {total_decisions}")
    print(f"Divergences: {len(divergences)}")
    if divergences:
        print("FIRST DIVERGENCE:")
        print(divergences[0])
        print("EQUIVALENCE FAILED")
        return 1
    print("EQUIVALENCE VERIFIED: the NEUTRAL-weighted shared engine reproduced every one "
          f"of V1's {total_decisions} real-game decisions exactly.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=15)
    parser.add_argument("--max-steps", type=int, default=2000)
    args = parser.parse_args()
    sys.exit(run(args.games, args.max_steps))


if __name__ == "__main__":
    main()
