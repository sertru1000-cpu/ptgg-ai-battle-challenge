"""Search V2 (Competitive V2, Part A3-A5): fixes the linked-decision-chain bug
found in Search V1 (`src/agents/search_lookahead.py`, kept unmodified as the
V1 reference -- see `results/search_v2_audit.md` for the full audit).

V1's bug (source-verified in the audit, not just inferred from the win-rate
regression): for a candidate attack, V1 called exactly one `search_step` and
evaluated whatever came back -- which, for attacks like Dragapult ex's
Phantom Dive (places bench damage counters via a SEPARATE
`SelectContext.DamageCounter` select) or Mega Lucario ex's Aura Jab (attaches
discarded Energy via a separate `SelectContext.SelectAttachTo` select chain),
is an artificial intermediate state, not the attack's real/complete outcome.

V2's fix: after the candidate action, keep calling `search_step` -- driven by
the SAME real heuristic agent function, evaluated on the hypothetical
observation -- for as long as the resulting decision still belongs to ME
(`observation.current.yourIndex == my_index`). This is not a heuristic
guess: verified against the C++ engine source (results/search_v2_audit.md
section "reusable decision-chain semantics") that damage-counter placement,
prize-taking, and select-and-attach effects are ALL addressed back to the
acting player, and that the chain only ever hands control to the opponent
once something outside my own action requires THEIR choice (e.g. they must
promote a new active after their own Pokemon is KO'd) -- which is exactly
the point a hypothetical rollout can no longer say anything about without
guessing the opponent's own (hidden-information-dependent) strategy, so it is
also the right place to stop and evaluate.

A hard step cap (`max_chain_steps`) guards against any pathological long
same-player chain -- defensive only, per Part A4's "no crash" requirement;
nothing in the engine source suggests this should ever be needed in practice
for the decision types currently in scope (see Part A5 scope below).

Scope (Part A5 -- deliberately narrow, not "search every action"): only
MAIN-context decisions offering 2+ distinct ATTACK options are search-
augmented, same scope as V1. This session's audit did not find evidence that
extending scope (KO-target selection, evolution, retreat, trainer plays) is
needed to test the core "does completing the chain fix the regression"
hypothesis -- extending scope is left as a documented follow-up, not
undertaken here, to keep this a single, attributable change vs. V1.
"""

import random
from dataclasses import asdict, dataclass, field

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import (  # noqa: E402
    Observation,
    OptionType,
    SelectContext,
    search_begin,
    search_end,
    search_step,
    to_observation_class,
)


@dataclass
class SearchV2Stats:
    """Mutable counters an experiment script can inspect after a game/batch."""

    attack_decisions_seen: int = 0
    searches_attempted: int = 0
    searches_succeeded: int = 0
    searches_failed: int = 0
    search_changed_choice: int = 0
    chain_lengths: list[int] = field(default_factory=list)
    chain_cap_hit: int = 0


def _evaluate(obs: Observation, my_index: int) -> float:
    """Identical to Search V1's evaluation function -- deliberately UNCHANGED
    so that any measured win-rate difference between V1 and V2 (or V2 vs.
    heuristic-only) is attributable to the chain-completion fix, not to a
    simultaneous evaluation-function change (see audit doc section 5)."""
    state = obs.current
    if state.result is not None and state.result >= 0:
        if state.result == my_index:
            return 1_000_000.0
        if state.result == 1 - my_index:
            return -1_000_000.0
        return 0.0

    me = state.players[my_index]
    opp = state.players[1 - my_index]
    score = (len(opp.prize) - len(me.prize)) * 1000.0
    opp_active_hp = opp.active[0].hp if opp.active and opp.active[0] is not None else 0
    me_active_hp = me.active[0].hp if me.active and me.active[0] is not None else 0
    score += (me_active_hp - opp_active_hp) * 1.0
    score += (len(me.bench) - len(opp.bench)) * 10.0
    return score


def _begin_shared_search(obs: Observation, my_deck: list[int], opponent_deck_hint: list[int]):
    """Unchanged from Search V1 -- one determinization per real decision,
    shared across every candidate action evaluated this decision."""
    state = obs.current
    my_index = state.yourIndex
    me = state.players[my_index]
    opp = state.players[1 - my_index]

    opponent_active_facedown = bool(opp.active) and opp.active[0] is None
    opponent_active_guess = [random.choice(opponent_deck_hint)] if opponent_active_facedown else []

    return search_begin(
        obs,
        your_deck=random.sample(my_deck, me.deckCount) if me.deckCount <= len(my_deck) else list(my_deck)[: me.deckCount],
        your_prize=random.sample(my_deck, len(me.prize)) if len(me.prize) <= len(my_deck) else list(my_deck)[: len(me.prize)],
        opponent_deck=random.sample(opponent_deck_hint, opp.deckCount) if opp.deckCount <= len(opponent_deck_hint) else list(opponent_deck_hint)[: opp.deckCount],
        opponent_prize=random.sample(opponent_deck_hint, len(opp.prize)) if len(opp.prize) <= len(opponent_deck_hint) else list(opponent_deck_hint)[: len(opp.prize)],
        opponent_hand=random.sample(opponent_deck_hint, opp.handCount) if opp.handCount <= len(opponent_deck_hint) else list(opponent_deck_hint)[: opp.handCount],
        opponent_active=opponent_active_guess,
    )


def _resolve_full_chain(search_id: int, first_action: list[int], my_index: int, base_agent_fn, max_chain_steps: int, stats: SearchV2Stats):
    """Steps the search forward starting with `first_action`, then keeps
    stepping -- using base_agent_fn's own decision on each hypothetical
    observation -- for as long as it's still my_index's decision. Returns the
    final Observation once control passes to the opponent, the game ends, or
    the step cap is hit (whichever first).
    """
    result_state = search_step(search_id, first_action)
    steps = 1
    while steps < max_chain_steps:
        obs = result_state.observation
        state = obs.current
        if state.result is not None and state.result >= 0:
            break
        if state.yourIndex != my_index:
            break
        # Still my own decision, consequent on the action I just took -- ask
        # the SAME real heuristic what it would do here (round-tripped back
        # to a plain dict, since search results are Observation dataclass
        # instances but every agent's entry point expects a raw obs_dict).
        sub_obs_dict = asdict(obs)
        sub_action = base_agent_fn(sub_obs_dict)
        # IMPORTANT: search_step returns a NEW searchId identifying the
        # resulting position (confirmed empirically: searchId increments
        # every call) -- must chain off result_state.searchId here, NOT the
        # original root `search_id` parameter, or every "next" call silently
        # re-branches from the ORIGINAL position instead of advancing,
        # producing an apparent stuck loop (caught during Search V2
        # development this session -- see results/search_v2_audit.md).
        result_state = search_step(result_state.searchId, sub_action)
        steps += 1
    else:
        stats.chain_cap_hit += 1
    stats.chain_lengths.append(steps)
    return result_state.observation


def make_search_v2_agent(base_agent_fn, base_deck: list[int], opponent_deck_hint: list[int], stats: SearchV2Stats | None = None, max_chain_steps: int = 20):
    """Returns an agent(obs_dict) function: base_agent_fn unchanged for every
    decision except multi-attack MAIN choices, where each candidate attack is
    evaluated after its FULL same-player decision chain resolves (Search V2),
    not just the first select (Search V1's bug).
    """
    if stats is None:
        stats = SearchV2Stats()

    def agent(obs_dict: dict) -> list[int]:
        if obs_dict.get("select") is None:
            return base_deck

        obs = to_observation_class(obs_dict)
        select = obs.select
        if select is not None and select.context == SelectContext.MAIN and select.maxCount == 1:
            attack_indices = [i for i, o in enumerate(select.option) if o.type == OptionType.ATTACK]
            if len(attack_indices) >= 2:
                stats.attack_decisions_seen += 1
                my_index = obs.current.yourIndex
                best_index = None
                best_score = float("-inf")
                any_success = False
                try:
                    root = _begin_shared_search(obs, base_deck, opponent_deck_hint)
                except Exception:
                    root = None
                if root is not None:
                    try:
                        for idx in attack_indices:
                            stats.searches_attempted += 1
                            try:
                                final_obs = _resolve_full_chain(root.searchId, [idx], my_index, base_agent_fn, max_chain_steps, stats)
                                score = _evaluate(final_obs, my_index)
                                stats.searches_succeeded += 1
                                any_success = True
                            except Exception:
                                stats.searches_failed += 1
                                continue
                            if score > best_score:
                                best_score = score
                                best_index = idx
                    finally:
                        try:
                            search_end()
                        except Exception:
                            pass
                if any_success and best_index is not None:
                    heuristic_choice = base_agent_fn(obs_dict)
                    if heuristic_choice != [best_index]:
                        stats.search_changed_choice += 1
                    return [best_index]

        return base_agent_fn(obs_dict)

    return agent
