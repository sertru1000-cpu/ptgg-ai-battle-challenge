"""Kaggle Simulation competition entry point for V15 -- "Holy Grail
Baseline": V6's fixed Phantom Dive attack engine + V4's DEFENSIVE weight
profile.

NOT the active submission -- see main_v2.py's docstring for the shared
rationale (identical structure, only the imported agent module differs).
V15 exists to test, via real ladder games, whether combining V6's Phantom
Dive fixes (PHANTOM_DIVE_ARCHITECTURE_AUDIT.md sec 3.2/3.3) with V4's
higher-ELO DEFENSIVE weight profile (736.9 ELO, vs. V6's BALANCED-profile
717.4 ELO) beats both individually. Uses the same deck as V1-V8/V11-V12/V14
(decks/dragapult_ex.csv; V15 tests gameplay policy/weights, not deck
selection).
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

from src.agents.final_candidate_agent_v15 import agent as _final_agent  # noqa: E402

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
