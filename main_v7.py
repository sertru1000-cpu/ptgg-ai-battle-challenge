"""Kaggle Simulation competition entry point for V7 -- V6 + the residual
Phantom Dive Bench-target planner fix (FIX #3).

NOT the active submission -- see main_v2.py's docstring for the shared
rationale (identical structure, only the imported agent module differs).
V7 exists to test, via real ladder games, whether fixing the remaining
false-200-damage-to-Bench-target premise in
PHANTOM_DIVE_ARCHITECTURE_AUDIT.md §3.3 (the same defect class as V6's own
FIX #2, but for i>=1 instead of i==0) further improves Phantom Dive KO
conversion on top of V6's already-confirmed ~82.4%. Uses the same deck as
V1-V6 (this experiment tests gameplay policy, not deck selection). V6 itself
is untouched and remains the live ladder submission.
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

from src.agents.final_candidate_agent_v7 import agent as _final_agent  # noqa: E402

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
