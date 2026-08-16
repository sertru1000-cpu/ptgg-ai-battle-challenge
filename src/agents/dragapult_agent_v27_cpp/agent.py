"""V18 top-level policy (V17 + Block A1 opponent-archetype determinization):
routes each decision to the native C++ MCTS agent
(native_bridge.native_choose_action), falling back to the full, already-
validated pure-Python V6 agent (src/agents/dragapult_policy_v6.py) on ANY
native-path problem -- library unavailable, init failure, or a per-decision
native error. See native_bridge.py's module docstring and ../README.md for
the full architecture.

Design note (why the fallback agent is called on EVERY decision, not just
when native fails): `_fallback_agent` is a real, stateful DragapultPolicy
instance -- its scoring depends on cross-call bookkeeping (self.prize,
pre_turn_log, plan_a/plan_b) that must track the REAL game's history to stay
correct. If it were only invoked on the rare decision where native happens to
fail, its bookkeeping would be missing everything that happened before that
point (most importantly: it would never have seen the deck-declare call, so
self.prize -- fixed once and never recomputed -- would stay permanently
empty), making it an INCORRECT fallback exactly when it's needed. Calling it
unconditionally keeps its internal state a faithful, always-current mirror of
the real match regardless of which path actually decided each past move --
its own scoring logic depends only on the observation it is given each call,
never on whether its own prior return values were the ones actually applied,
so this is safe (not doubled/miscounted) as well as correct. The extra
pure-Python V6 evaluation is cheap (no search) relative to the native path's
own time budget, so this costs negligible overhead even when native succeeds.
"""

from __future__ import annotations

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import SelectContext, to_observation_class  # noqa: E402

from src.agents.dragapult_policy_v6 import DECK, make_agent as _make_v6_agent  # noqa: E402
from src.agents.policy_weights import BALANCED  # noqa: E402
from src.agents.dragapult_agent_v27_cpp import native_bridge  # noqa: E402

# `always_first=True` here is what actually answers the one-time "go first?"
# question (validated override, results/dragapult_first_second_analysis.md) --
# reused directly rather than duplicated, see module docstring for why this
# instance is always invoked regardless of which path's answer gets used.
_fallback_agent = _make_v6_agent(BALANCED, adaptive=False, always_first=True)


def agent(obs_dict: dict) -> list[int]:
    fallback_result = _fallback_agent(obs_dict)

    select = obs_dict.get("select")
    if select is None:
        return fallback_result  # deck declare -- deterministic, no search needed

    obs = to_observation_class(obs_dict)
    if obs.select is not None and obs.select.context == SelectContext.IS_FIRST:
        return fallback_result  # already the correct always-yes answer

    native_result = native_bridge.native_choose_action(obs_dict)
    if native_result is not None:
        return native_result
    return fallback_result
