"""Kaggle Simulation competition entry point for V23 -- Self-Play Eval Edition.

V18's native C++ MCTS (archetype-conditioned determinization, generic
opponent rollouts) with the Block-B stack: B1 -- rollout/leaf evaluation by a
learned P(win) model (XGBoost, 161 trees, trained on 341K decision states
from the top-100 ladder teams' real games, embedded as static C++ arrays --
zero runtime ML dependencies); B2 -- PUCT selection with V6-greedy softmax
priors; B3 -- determinization-majority voting. Falls back to the pure-Python
V6 agent whenever the native library is unavailable or errors.

NOT the active submission, and NOT submitted to Kaggle by this task --
explicit user approval required first. Uses V6's exact deck
(decks/dragapult_ex.csv), same lineage as V17/V18.
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

from src.agents.final_candidate_agent_v23 import agent as _final_agent  # noqa: E402

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
