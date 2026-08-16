"""Kaggle Simulation competition entry point for V18 -- C++ MCTS +
opponent-archetype determinization (Block A1).

V17's native MCTS unchanged except for how the opponent's hidden zones are
determinized per search: instead of always assuming a mirror match (our own
deck), the opponent's archetype is classified from their visible board and
discard, and hidden zones are sampled from that archetype's real
replay-derived canonical decklist minus everything of theirs already visible
(see src/agents/dragapult_agent_v18_cpp/opponent_model.py). Falls back to the
pure-Python V6 agent whenever the native library is unavailable or errors.

NOT the active submission, and NOT submitted to Kaggle by this task --
explicit user approval required first. Uses V6's exact deck
(decks/dragapult_ex.csv), same fork lineage as V17.
"""

import importlib.util
import os
import sys


def _ensure_submission_root_importable() -> None:
    if importlib.util.find_spec("src") is not None:
        return
    for candidate in (os.getcwd(), "/kaggle_simulations/agent"):
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)
        if importlib.util.find_spec("src") is not None:
            return


_ensure_submission_root_importable()

from src.agents.final_candidate_agent_v18 import agent as _final_agent  # noqa: E402

_DECK_PATH = "deck.csv"
_DECK_PATH_FALLBACK = "/kaggle_simulations/agent/deck.csv"


def _read_deck_csv() -> list[int]:
    file_path = _DECK_PATH if os.path.exists(_DECK_PATH) else _DECK_PATH_FALLBACK
    with open(file_path, "r") as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


_DECK = _read_deck_csv()
DECK = _DECK  # exposed for tools/tournament.py's local-harness convention; unused by the Kaggle grader


def agent(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is None:
        return _DECK
    return _final_agent(obs_dict)
