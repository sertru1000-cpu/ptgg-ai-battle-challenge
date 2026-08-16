"""Kaggle Simulation competition entry point for V9 -- STRATEGIC PIVOT
EXPERIMENT: the Mega Lucario ex archetype (Objective 1: the verified,
Luca-audit-upgraded decklist, decks/lucario_ex.csv) piloted by the
generalized V6/V7/V8 decision engine, including the Survival Retreat
heuristic now expanded to cover 1-Prize Actives under specific conditions
(Objective 2). See src/agents/lucario_policy_v9.py's module docstring for
the full design rationale and V9_IMPLEMENTATION_REPORT.md for the
validation writeup.

NOT the active submission -- not yet submitted to Kaggle this phase (see
V9_IMPLEMENTATION_REPORT.md). Same structure as main_v8.py, only the
imported agent module differs -- with one deliberate difference: main_v8.py
reads a shared repo-root `deck.csv` for the very first (select is None)
call, which is fine for V8 because that file is Dragapult ex's own decklist.
V9 must NOT read that same shared file (it holds the WRONG deck for this
agent, and overwriting it would break V8's own local testing/staging --
explicitly out of scope here). Instead, this file trusts a `deck.csv`
sitting alongside it ONLY if its contents actually match the Lucario
decklist the rest of this agent plays (e.g. once a future Kaggle packaging
step drops a matching copy into this submission's own staging directory);
otherwise it falls back to the already-loaded, always-correct DECK constant
from the agent chain below.
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

from src.agents.final_candidate_agent_v9 import DECK as _EXPECTED_DECK, agent as _final_agent  # noqa: E402

_DECK_PATH = "deck.csv"
_DECK_PATH_FALLBACK = "/kaggle_simulations/agent/deck.csv"


def _read_deck_csv() -> list[int]:
    for candidate in (_DECK_PATH, _DECK_PATH_FALLBACK):
        if not os.path.exists(candidate):
            continue
        with open(candidate, "r") as f:
            lines = f.read().split("\n")
        try:
            deck = [int(lines[i]) for i in range(60)]
        except (ValueError, IndexError):
            continue
        if deck == _EXPECTED_DECK:
            return deck
    # No matching deck.csv found alongside this entry point (the normal case
    # locally, since decks/lucario_ex.csv is the single source of truth) --
    # use the already-validated deck the rest of this agent plays, rather
    # than risk silently declaring a different deck than we actually pilot.
    return _EXPECTED_DECK


_DECK = _read_deck_csv()
DECK = _DECK  # exposed for tools/tournament.py's local-harness convention; unused by the Kaggle grader


def agent(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is None:
        return _DECK
    return _final_agent(obs_dict)
