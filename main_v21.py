"""Kaggle Simulation competition entry point for V21 -- Leader Imitation (BC).

V6's proven heuristic engine adapted to the exact 60-card Dragapult list
played identically by 11+ of the top-100 ladder's Dragapult teams (including
rank #2, rating 1217), with heuristic support for the new cards (Munkidori's
Adrena-Brain + {D} Energy, Judge, Dawn, Jamming Tower) -- see
src/agents/dragapult_policy_v19.py. Pure Python, no native code.

NOT the active submission, and NOT submitted to Kaggle by this task --
explicit user approval required first. Uses decks/dragapult_ex_v19.csv.
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

from src.agents.final_candidate_agent_v21 import agent as _final_agent  # noqa: E402

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
