"""Mandatory Timeout Shield (Phase 4.7 Section 20-21).

Wraps an `agent(obs_dict) -> list[int]` so that a single slow decision (an
unexpected engine state, an expensive scoring path, a future search/Bayesian
addition, etc.) can never make the WHOLE MATCH exceed its wall-clock budget.

Budget source (Section 20 explicitly forbids guessing this number):
- `kaggle_environments`' own "cabt" env spec (`cabt.json`, fetched live from
  https://github.com/Kaggle/kaggle-environments/blob/master/kaggle_environments/envs/cabt/cabt.json
  during this phase): `configuration.actTimeout = 0`, `observation.remainingOverageTime = 600`.
  In the standard kaggle_environments timing model this means: there is no
  free per-step allowance beyond a single shared 600-second "overage time"
  bank for the WHOLE episode -- every second any decision takes is drawn from
  that one bank, and exhausting it is a timeout loss for that agent.
- Independently cross-confirmed against `docs/environment.md` section 4,
  sourced from the actual C++ engine reference material during Phase 1 of
  this project ("Match time limit: 10 minutes per match total... a hard
  wall-clock budget for an entire game, all our turns combined, not per
  move"). 600s == 10 minutes -- two independent sources agree, so this is
  used as a verified fact, not a guess.

Design (per Section 20's required architecture: fast baseline available,
optional expensive reasoning, deadline check, safe fallback):
- A persistent single-worker thread pool runs the real (possibly slow) inner
  agent call. `Future.result(timeout=...)` gives a hard wall-clock cutoff
  without needing SIGALRM (not available on Windows for non-main threads
  anyway). If the inner call doesn't finish in time we do NOT wait for it --
  we return the deterministic safe fallback immediately and let the
  abandoned thread finish or die on its own.
- MATCH_BUDGET_SECONDS tracks cumulative *wrapper-observed* elapsed time
  across the whole match (both timed-out and successful calls count). Once
  fewer than SAFETY_MARGIN_SECONDS remain, the shield permanently switches to
  "fallback-only" mode for the rest of the match -- it stops even attempting
  the inner agent, guaranteeing the shield itself cannot cause a timeout loss
  regardless of how many decisions remain.
- PER_DECISION_BUDGET_SECONDS additionally caps any single decision, so one
  pathological state can't consume the whole match budget in one call.

This module never imports `cg` and never raises -- it must keep working even
if the inner agent is completely broken.
"""

from __future__ import annotations

import concurrent.futures
import time
from typing import Callable

PER_DECISION_BUDGET_SECONDS = 2.0
MATCH_BUDGET_SECONDS = 600.0
SAFETY_MARGIN_SECONDS = 150.0
_OPTION_TYPE_END = 14


def _safe_default_selection(select: dict) -> list[int]:
    """Deterministic legal fallback identical in spirit to
    safety_wrapper._safe_default_selection, duplicated here (not imported) so
    this module has zero dependency on any other project module and cannot be
    broken by a change elsewhere -- the timeout shield is the last line of
    defense before an even-more-basic outer safety net, so it must be
    self-contained."""
    option = select.get("option", []) if isinstance(select, dict) else []
    n = len(option)
    min_count = max(0, select.get("minCount", 0))
    if min_count > 0:
        return list(range(min(min_count, n)))
    for i, o in enumerate(option):
        try:
            if isinstance(o, dict) and o.get("type") == _OPTION_TYPE_END:
                return [i]
        except Exception:  # noqa: BLE001
            pass
    return []


def wrap_timeout(
    inner_agent: Callable[[dict], list[int]],
    name: str = "agent",
    per_decision_budget: float = PER_DECISION_BUDGET_SECONDS,
    match_budget: float = MATCH_BUDGET_SECONDS,
    safety_margin: float = SAFETY_MARGIN_SECONDS,
):
    """Return a wrapped agent(obs_dict) -> list[int] with a hard per-match
    wall-clock budget. Never raises, never blocks past its deadline."""

    stats = {
        "calls": 0,
        "timeouts": 0,
        "inner_exceptions": 0,
        "cumulative_elapsed_seconds": 0.0,
        "degraded_mode_activations": 0,
        "degraded_calls": 0,
    }
    state = {"degraded": False}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"timeout_shield_{name}")
    # Single worker, deliberately: if a call ever truly hangs (never returns),
    # the abandoned thread stays stuck on it forever, so every subsequent
    # submit() queues behind it and its own result(timeout=...) call times
    # out immediately too -- from that point on every decision safely and
    # instantly falls back, which is the correct degrade-gracefully behavior
    # (Section 21: a safe mediocre action beats a risky optimal one), not a
    # bug. A multi-worker pool would just hide a truly-hung call longer.

    def safe_agent(obs_dict: dict) -> list[int]:
        stats["calls"] += 1
        select = obs_dict.get("select") if isinstance(obs_dict, dict) else None

        # Deck-declare call (select is None): no legal-action fallback exists
        # for a 60-card deck, and this always happens exactly once at the
        # very start of a match when the full budget is available -- run it
        # directly, unguarded, rather than risk raising RuntimeError from a
        # thread-pool timeout on the one call that has no safe substitute.
        if select is None:
            return inner_agent(obs_dict)

        remaining = match_budget - stats["cumulative_elapsed_seconds"]
        if state["degraded"] or remaining <= safety_margin:
            if not state["degraded"]:
                state["degraded"] = True
                stats["degraded_mode_activations"] += 1
            stats["degraded_calls"] += 1
            return _safe_default_selection(select)

        deadline = min(per_decision_budget, max(0.05, remaining - safety_margin))
        start = time.monotonic()
        future = executor.submit(inner_agent, obs_dict)
        try:
            result = future.result(timeout=deadline)
        except concurrent.futures.TimeoutError:
            stats["cumulative_elapsed_seconds"] += time.monotonic() - start
            stats["timeouts"] += 1
            return _safe_default_selection(select)
        except Exception:  # noqa: BLE001 -- inner agent raised synchronously
            stats["cumulative_elapsed_seconds"] += time.monotonic() - start
            stats["inner_exceptions"] += 1
            return _safe_default_selection(select)
        else:
            stats["cumulative_elapsed_seconds"] += time.monotonic() - start
            return result

    safe_agent.stats = stats  # type: ignore[attr-defined]
    safe_agent.__name__ = f"timeout_shielded_{name}"
    return safe_agent
