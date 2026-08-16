"""Local entry point for V13 -- TURBO CONSISTENCY DECK: the V6/BALANCED
policy engine (unmodified except for one new Cheren scoring branch --
see src/agents/dragapult_policy_v13.py's module docstring) piloting a
brick-proof, maximal-draw/maximal-search decklist purpose-built for a
greedy, one-ply policy (decks/dragapult_v13_turbo.csv). See
V13_IMPLEMENTATION_REPORT.md for the full decklist diff, rationale, and
local validation writeup.

NOT submitted to Kaggle this phase, per the governing task's explicit
instruction -- local build/validation only. Does not modify main_v6.py or
any file it imports, and does not import or execute any V8/V9
survival/defensive-retreat code or any V10/V11 lookahead/search code.

Same structure as main_v9.py/main_v10.py's deliberate deck.csv caution: the
shared repo-root `deck.csv` holds V1-V8's decklist (decks/dragapult_ex.csv),
which is NOT V13's deck -- trusting it blindly would silently run V13 with
the wrong 60 cards. This file only trusts a `deck.csv` sitting alongside it
if its contents actually match V13's turbo decklist; otherwise it falls back
to the already-loaded, always-correct DECK constant from the agent chain
below. It never writes to the shared deck.csv.
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

from src.agents.final_candidate_agent_v13 import DECK as _EXPECTED_DECK, agent as _final_agent  # noqa: E402

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
    # locally, since decks/dragapult_v13_turbo.csv is the single source of
    # truth) -- use the already-validated deck the rest of this agent plays,
    # rather than risk silently declaring a different (wrong) deck.
    return _EXPECTED_DECK


_DECK = _read_deck_csv()
DECK = _DECK  # exposed for tools/tournament.py's local-harness convention; unused by the Kaggle grader


def agent(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is None:
        return _DECK
    return _final_agent(obs_dict)
