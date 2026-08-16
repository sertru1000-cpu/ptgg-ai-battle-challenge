"""Phase 12: the smallest practical search-enhanced agent.

Wraps an existing heuristic agent unchanged for every decision EXCEPT choosing
which attack to use when 2+ distinct attacks are legally offered in the same
MAIN-context decision. For that one high-impact decision, it uses the official
Search API (docs/search_api.md) to look one ply ahead: actually resolve each
candidate attack against a determinized hypothetical state and compare the
real resulting board state (prize swing, opponent HP left, own HP left)
instead of trusting the heuristic's own attack-choice scoring. Every other
decision (which Pokemon to attach to, which trainer to play, retreats,
setup, etc.) is delegated to the wrapped agent completely unmodified.

Determinization (see docs/search_api.md section 1 and 8): own hidden zones
(deck order, prize identity) are sampled from the agent's own known 60-card
decklist, same approach as the official RL/MCTS sample notebook
(`random.sample(full_decklist, count)`). Opponent hidden zones are
determinized from `opponent_deck_hint` -- in this local-research context we
actually know the opponent's decklist (it's one of our own ported baseline
decks), so we use it directly rather than inventing a blind-guess strategy;
this is an explicit simplification appropriate for *local* experimentation
only, flagged here so it is never mistaken for a technique that would work
against an unknown live-ladder opponent (a real submission would need an
actual opponent model, out of scope for this phase per the project's
no-opponent-modeling-yet rule).

Any error from the Search API (typed ValueError, unexpected state, etc.)
falls back to the wrapped heuristic's own unmodified decision -- search is
strictly advisory and must never be able to make the agent worse than the
baseline by crashing or stalling.
"""

import random
from dataclasses import dataclass

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
class SearchStats:
    """Mutable counters an experiment script can inspect after a game/batch."""

    attack_decisions_seen: int = 0
    searches_attempted: int = 0
    searches_succeeded: int = 0
    searches_failed: int = 0
    search_changed_choice: int = 0


def _evaluate(obs: Observation, my_index: int) -> float:
    """Cheap, self-contained position evaluation from information already
    visible to my_index -- no hidden-info reads. Higher is better for
    my_index. Deliberately simple (prize race + board health), not a
    reimplementation of either heuristic agent's own scoring.
    """
    state = obs.current
    if state.result is not None and state.result >= 0:
        if state.result == my_index:
            return 1_000_000.0
        if state.result == 1 - my_index:
            return -1_000_000.0
        return 0.0  # draw

    me = state.players[my_index]
    opp = state.players[1 - my_index]
    # Fewer of MY remaining prizes = I'm closer to winning; fewer of OPPONENT's
    # remaining prizes = they're closer to winning.
    score = (len(opp.prize) - len(me.prize)) * 1000.0
    opp_active_hp = opp.active[0].hp if opp.active and opp.active[0] is not None else 0
    me_active_hp = me.active[0].hp if me.active and me.active[0] is not None else 0
    score += (me_active_hp - opp_active_hp) * 1.0
    score += (len(me.bench) - len(opp.bench)) * 10.0
    return score


def _begin_shared_search(obs: Observation, my_deck: list[int], opponent_deck_hint: list[int]):
    """One determinization per real decision, shared across every candidate
    action evaluated this decision (so candidates are compared against the
    SAME hypothetical hidden state, not independently re-randomized guesses
    -- re-randomizing per candidate would make the 1-ply comparison noisy
    and unfair)."""
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


def make_search_augmented_agent(base_agent_fn, base_deck: list[int], opponent_deck_hint: list[int], stats: SearchStats | None = None):
    """Returns an agent(obs_dict) function: base_agent_fn unchanged for every
    decision except multi-attack MAIN choices, where it 1-ply-searches each
    candidate attack and picks the best by _evaluate().
    """
    if stats is None:
        stats = SearchStats()

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
                                result_state = search_step(root.searchId, [idx])
                                score = _evaluate(result_state.observation, my_index)
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
