"""Kaggle Simulation competition entry point for V14 -- DYNAMIC GAME-PHASE
POLICY (forked from V6/BALANCED + the two confirmed Phantom Dive bug fixes).

NOT the active submission -- see main_v2.py's docstring for the shared
rationale (identical structure, only the imported agent module differs).
V14 tests, via local self-play and (pending approval) real ladder games,
whether modulating V6's scoring weights by detected game phase (EARLY/MID/
LATE, from both players' own remaining prize counts) improves on V6's
single-static-profile decision-making, with no lookahead/search and none of
V8/V9's survival/defensive-retreat heuristics. Uses the same deck as V1-V8/
V11/V12 (decks/dragapult_ex.csv, byte-identical to the shared root
deck.csv) -- this task tests gameplay policy, not deck selection.
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

from src.agents.final_candidate_agent_v14 import agent as _final_agent  # noqa: E402

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
