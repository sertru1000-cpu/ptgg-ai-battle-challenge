"""Kaggle Simulation competition entry point for V2 -- BALANCED (Prompt #5).

NOT the active submission -- src/agents/dragapult_agent.py (V1/BASELINE,
final_submission.tar.gz) remains the Champion. This file exists so V2 can be
packaged and submitted independently and controllably, on explicit user
request, via a dedicated submission slot. See
reports/agent_v2_v5_experiments.md Section 7 ("How to submit each version").

Identical structure to main.py (deck.csv loading convention, the
`__file__`-free sys.path setup from the Phase 4.7.1 Kaggle runtime hotfix --
see reports/kaggle_runtime_hotfix_v1.md) -- only the imported agent module
differs. Uses the same deck (decks/dragapult_ex.csv) as V1: Prompt #5 tests a
gameplay-policy hypothesis, not a deck-selection hypothesis, so the deck axis
is deliberately held constant across V1-V5 for a clean comparison.
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

from src.agents.final_candidate_agent_v2 import agent as _final_agent  # noqa: E402

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
