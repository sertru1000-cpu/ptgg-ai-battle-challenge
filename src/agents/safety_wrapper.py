"""Mandatory legal-action safety layer (Phase 4.7 Section 9).

Wraps any `agent(obs_dict) -> list[int]` callable so the final returned
selection is *always* a legal one: the right count of indices, in range, no
duplicates -- even if the wrapped agent raises, returns garbage, or returns
something the engine would reject. This is applied to every agent shipped in
the final submission, including the existing hand-tuned notebook agents
(defense in depth -- those have not crashed in prior local benchmarks, but
`cg.api`'s own comments warn "new elements may be appended to the Enum
during the competition", so an untested state is always possible).

Never raises. Never returns an out-of-contract selection. Tracks counters
(`calls`, `fallback_used`, `exceptions`, `invalid_returned_by_inner`) for the
local-evaluation instrumentation required by Section 19/22 -- these counters
are cheap dict increments, not logging, so they carry no timeout/log-volume
risk and can stay on in the final submission.
"""

from typing import Callable


_OPTION_TYPE_END = 14  # cg.api.OptionType.END's raw int value; kept as a
# plain constant (not an import) so this module never depends on cg being
# importable -- the fallback path must work even in a degraded environment.


def _safe_default_selection(select) -> list[int]:
    """Deterministic legal fallback: never depends on scoring, card lookups,
    or anything that could itself fail. `select.option` holds the *raw*
    JSON option dicts (this wrapper never constructs cg.api dataclasses),
    so options are read with dict access, not attribute access."""
    n = len(select.option)
    min_count = max(0, select.minCount)
    if min_count > 0:
        return list(range(min(min_count, n)))
    # minCount == 0: prefer an explicit END option (do nothing) if offered,
    # otherwise take nothing -- both are always legal when minCount is 0.
    for i, o in enumerate(select.option):
        try:
            if isinstance(o, dict) and o.get("type") == _OPTION_TYPE_END:
                return [i]
        except Exception:  # noqa: BLE001
            pass
    return []


def _is_valid_selection(select, chosen) -> bool:
    if not isinstance(chosen, list):
        return False
    n = len(select.option)
    if len(chosen) != len(set(chosen)):
        return False
    if not (select.minCount <= len(chosen) <= select.maxCount):
        return False
    return all(isinstance(i, int) and 0 <= i < n for i in chosen)


def wrap_agent(inner_agent: Callable[[dict], list[int]], name: str = "agent"):
    """Return a safety-wrapped agent(obs_dict) -> list[int].

    On the very first call (obs["select"] is None), the inner agent's return
    value IS the 60-card deck declaration, not option indices -- passed
    through unchanged (deck legality is validated offline by
    tools/deck_validator.py before ever reaching this wrapper, per Phase 4.7
    Section 7).
    """
    stats = {"calls": 0, "fallback_used": 0, "exceptions": 0, "invalid_returned_by_inner": 0}

    def safe_agent(obs_dict: dict) -> list[int]:
        stats["calls"] += 1
        select = obs_dict.get("select") if isinstance(obs_dict, dict) else None

        if select is None:
            try:
                deck = inner_agent(obs_dict)
                if isinstance(deck, list) and len(deck) == 60:
                    return deck
            except Exception:  # noqa: BLE001
                stats["exceptions"] += 1
            # No safe deterministic deck fallback exists here by design --
            # an agent with an invalid/missing deck should fail loudly during
            # local testing (Section 18 smoke test), not silently ship a
            # different deck than the one validated offline.
            raise RuntimeError(f"{name}: failed to produce a 60-card deck on the initial call")

        # Reconstruct just enough of the select contract to validate/fallback
        # without importing cg.api here (keeps this module import-light and
        # usable even before ensure_cg_on_path() has run elsewhere).
        class _Select:
            option = select["option"]
            minCount = select["minCount"]
            maxCount = select["maxCount"]

        try:
            chosen = inner_agent(obs_dict)
        except Exception:  # noqa: BLE001
            stats["exceptions"] += 1
            stats["fallback_used"] += 1
            return _safe_default_selection(_Select)

        if _is_valid_selection(_Select, chosen):
            return chosen

        stats["invalid_returned_by_inner"] += 1
        stats["fallback_used"] += 1
        return _safe_default_selection(_Select)

    safe_agent.stats = stats  # type: ignore[attr-defined]
    safe_agent.__name__ = f"safe_{name}"
    return safe_agent
