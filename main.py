"""Kaggle Simulation competition entry point (pokemon-tcg-ai-battle).

Loads deck.csv using the exact official convention (cwd-relative "deck.csv",
falling back to "/kaggle_simulations/agent/deck.csv" at inference time --
identical to every official sample notebook, see
data/official/sample_submission/sample_submission/main.py). All gameplay
decisions are delegated to src.agents.final_candidate_agent.agent, which
composes (outermost to innermost):

    safety_wrapper      -- legal-action net, invalid_actions == 0 invariant
      -> timeout_shield  -- hard per-match wall-clock budget (Section 20)
        -> dragapult_agent_always_first -- Layer B policy (deck: Dragapult ex)

See reports/final_agent_v1.md for the full Phase 4.7 writeup: deck selection
(Layer A), Going First/Second, Bayesian opponent prediction, the ablation
ladder, and submission packaging/smoke-test results. See
reports/kaggle_runtime_hotfix_v1.md for the Phase 4.7.1 runtime-compatibility
fix this file's import setup below implements (root cause: Kaggle executes
main.py's source via a bare `exec()`, which never defines `__file__` in the
resulting namespace -- unlike a normal `python main.py` invocation or a
regularly `import`ed module, both of which always have `__file__` set).
"""

import importlib.util
import os
import sys


def _ensure_submission_root_importable() -> None:
    """Make this submission's sibling packages (src/, cg/) importable
    WITHOUT ever referencing `__file__` -- Kaggle's exec()-based agent
    runner does not define it for main.py's own top-level code (confirmed
    live: `NameError: name '__file__' is not defined` at the old
    `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` line).

    Tries, in order, and stops at the first candidate that actually makes
    `src` importable:
      1. No change at all. The official sample main.py does
         `from cg.api import ...` with zero path setup and is known to
         work on Kaggle, which means the platform's own agent runner most
         likely already puts the submission directory on sys.path (or
         chdirs into it) before exec'ing -- in which case `cg` (bundled
         alongside main.py) and `src` (also bundled alongside main.py) are
         BOTH already importable with no help from this function at all.
      2. The current working directory -- NOT assumed to be correct on its
         own (Section 6.C of the hotfix spec explicitly warns against that
         assumption), only tried as a fallback and verified before use.
      3. Kaggle's own documented, stable submission path,
         `/kaggle_simulations/agent` -- not a guess: this is the exact
         absolute path the live Kaggle error traceback showed main.py
         actually running from, and the same path every official sample
         notebook already hardcodes as its deck.csv fallback.
    None of these read `__file__`.
    """
    if importlib.util.find_spec("src") is not None:
        return  # already importable -- most likely path on real Kaggle, see (1) above

    for candidate in (os.getcwd(), "/kaggle_simulations/agent"):
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)
        if importlib.util.find_spec("src") is not None:
            return
    # If none of the candidates worked, leave sys.path as amended anyway --
    # the import below will then raise a clear, honest ModuleNotFoundError
    # instead of this function silently masking the problem.


_ensure_submission_root_importable()

from src.agents.final_candidate_agent import agent as _final_agent  # noqa: E402

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
    """Implement Your Pokemon Trading Card Game Agent.

    Each element in the returned list must be >= 0 and < len(obs.select.option).
    The list length must be between obs.select.minCount and obs.select.maxCount
    (inclusive), with no duplicate elements.
    """
    if obs_dict.get("select") is None:
        # Initial selection: return the packaged deck.csv content directly
        # (not final_candidate_agent's own internally-loaded DECK constant),
        # so the deck actually played always matches the deck.csv shipped in
        # this submission archive, even if the two loading paths could ever
        # diverge.
        return _DECK
    return _final_agent(obs_dict)
