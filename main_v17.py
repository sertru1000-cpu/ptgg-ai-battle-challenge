"""Kaggle Simulation competition entry point for V17 -- C++ MCTS Edition.

Native Monte Carlo Tree Search (Selection/Expansion/Simulation/
Backpropagation) implemented in C++, calling the competition engine's native
SearchBegin/SearchStep/SearchEnd C ABI directly (bypassing Python/ctypes/JSON
marshalling for every simulated branch -- see
src/agents/dragapult_agent_v17_cpp/README.md for the full architecture),
using V6's own exact scoring math (src/agents/dragapult_policy_v6.py, ported
line-for-line to C++) as both the rollout default policy and the leaf/backup
evaluation function. Falls back to the pure-Python V6 agent whenever the
native library is unavailable or errors for any reason.

NOT the active submission, and NOT submitted to Kaggle by this task --
explicit user approval required first. See main_v2.py's docstring for the
shared entry-point structure (identical, only the imported agent module
differs). Uses V6's exact deck (decks/dragapult_ex.csv) -- same fork lineage
as V11 (governing task Objective 1: a search/architecture experiment, not a
deck change).
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

from src.agents.final_candidate_agent_v17 import agent as _final_agent  # noqa: E402

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
