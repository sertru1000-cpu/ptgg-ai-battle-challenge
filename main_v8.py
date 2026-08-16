"""Kaggle Simulation competition entry point for V8 -- V7 + exactly ONE new
strategic addition: a context-aware 2-Prize Defensive Retreat / Survival
heuristic (see src/agents/dragapult_policy_v8.py's module docstring and
V8_RETREAT_HEURISTIC_AUDIT.md).

NOT the active submission -- see main_v2.py's docstring for the shared
rationale (identical structure, only the imported agent module differs). V8
exists to test, via local scenario validation (per
V8_RETREAT_HEURISTIC_AUDIT.md; not yet submitted to the real ladder), the
hypothesis that V2/V6/V7 sometimes incorrectly attack instead of retreating a
2-Prize Active facing a guaranteed, currently-visible lethal hit when a
genuinely playable Bench replacement exists. Uses the same deck as V1-V7
(this experiment tests gameplay policy, not deck selection). V7 itself is
untouched and remains the prior experiment baseline.
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

from src.agents.final_candidate_agent_v8 import agent as _final_agent  # noqa: E402

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
