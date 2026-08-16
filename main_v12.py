"""Kaggle Simulation competition entry point for V12 -- MATCHUP-AWARE POLICY:
V6/BALANCED + the two confirmed Phantom Dive bug fixes + per-decision
opponent archetype detection (SNIPER / AGRO_TANK / UNKNOWN) with dynamic
weight shifting (src/agents/dragapult_policy_v12.py's module docstring).

NOT the active submission, and NOT submitted to Kaggle by this task --
explicit user approval required first. See main_v2.py's docstring for the
shared entry-point structure (identical, only the imported agent module
differs). Uses the exact same deck as V6/V1-V8/V11 (decks/dragapult_ex.csv,
NOT V10's deck) -- V12 is a decision-policy experiment, not a deck change.
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

from src.agents.final_candidate_agent_v12 import agent as _final_agent  # noqa: E402

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
