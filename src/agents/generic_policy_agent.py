"""Deck-agnostic in-game gameplay policy (Phase 4.7, Layer B).

Unlike the four notebook-derived agents in this package (dragapult_agent.py,
abomasnow_agent.py, iono_agent.py, lucario_ex_agent.py), which hard-code
knowledge of specific card IDs for one specific decklist, this module scores
every legal option using only generic signals available from `cg.api`'s
CardData/Attack/Pokemon dataclasses (HP, weakness/resistance, ex/megaEx prize
value, energy counts, card type, and a light keyword read of card text). It
works unmodified against any legal 60-card deck via `make_agent(deck)`.

This exists because Phase 4.6's validated evidence identifies favorable
*decks* (e.g. Team Rocket's Mewtwo ex), not favorable *play sequences* for
those decks -- we have no hand-tuned notebook-quality heuristic for most
current-meta archetypes, and hand-authoring one under a multi-day deadline is
exactly the "complex + fragile + under-tested" failure mode Phase 4.7's own
instructions warn against. A single generic policy, tested once, is reused
across every candidate deck instead.

Strategic priority hierarchy (Phase 4.7 Section 10), implemented as
non-overlapping score bands so the priority order is enforced structurally,
not just by convention. `BAND_SCORE` is the single point of configuration if
the ordering needs to change.
"""

from collections import defaultdict
from pathlib import Path
from typing import Callable

from src.agents.common import get_card, select_top
from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import (  # noqa: E402
    AreaType,
    CardData,
    CardType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_attack,
    all_card_data,
)

REASON = {
    "WINNING_ATTACK": "WINNING_ATTACK",
    "PREVENT_LOSS": "PREVENT_LOSS",
    "GUARANTEED_KO": "GUARANTEED_KO",
    "PRIZE_EFFICIENT_ATTACK": "PRIZE_EFFICIENT_ATTACK",
    "SETUP_EVOLUTION": "SETUP_EVOLUTION",
    "ENERGY_ACCELERATION": "ENERGY_ACCELERATION",
    "DRAW_CONSISTENCY": "DRAW_CONSISTENCY",
    "BOARD_DEVELOPMENT": "BOARD_DEVELOPMENT",
    "DISRUPTION": "DISRUPTION",
    "FALLBACK": "FALLBACK",
}

# Ordered highest-to-lowest priority; gaps (100,000+) comfortably exceed any
# in-band tie-breaker delta added below, so bands never cross.
BAND_SCORE = {
    REASON["WINNING_ATTACK"]: 1_000_000,
    REASON["PREVENT_LOSS"]: 500_000,
    REASON["GUARANTEED_KO"]: 200_000,
    REASON["PRIZE_EFFICIENT_ATTACK"]: 50_000,
    REASON["SETUP_EVOLUTION"]: 20_000,
    REASON["ENERGY_ACCELERATION"]: 10_000,
    REASON["DRAW_CONSISTENCY"]: 8_000,
    REASON["BOARD_DEVELOPMENT"]: 5_000,
    REASON["DISRUPTION"]: 3_000,
    REASON["FALLBACK"]: 0,
}

_WEAKNESS_MULTIPLIER = 2  # heuristic estimate (modern-era default); the exact
# per-attack modifier lives in the engine's compiled C++ and is not read here
# -- see reports/final_agent_v1.md Section 6 for this approximation's scope.
_RESISTANCE_REDUCTION = 20

_DRAW_KEYWORDS = ("draw", "look at the top")
_SEARCH_KEYWORDS = ("search your deck", "search your discard")
_DISRUPT_KEYWORDS = ("opponent's", "switch out", "each of your opponent", "discard a random card from your opponent")


def _card_table() -> dict[int, CardData]:
    return {c.cardId: c for c in all_card_data()}


def _attack_table():
    return {a.attackId: a for a in all_attack()}


def prize_value(card_data: CardData) -> int:
    """Prizes the opponent takes if this Pokemon is Knocked Out."""
    return 3 if card_data.megaEx else 2 if card_data.ex else 1


def estimate_damage(attack, attacker_data: CardData, defender_data: CardData) -> int:
    """Heuristic damage estimate: base attack damage adjusted for a simple
    weakness/resistance model. Deliberately approximate -- see module
    docstring; safe because it only ever influences *scoring*, never
    legality (the engine has already filtered options to legal ones)."""
    dmg = attack.damage
    if defender_data.weakness is not None and defender_data.weakness == attacker_data.energyType:
        dmg *= _WEAKNESS_MULTIPLIER
    if defender_data.resistance is not None and defender_data.resistance == attacker_data.energyType:
        dmg = max(0, dmg - _RESISTANCE_REDUCTION)
    return dmg


def _text_has_any(text: str | None, keywords: tuple[str, ...]) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(k in low for k in keywords)


def _in_danger(pokemon: Pokemon, card_data: CardData, my_state) -> bool:
    """Very rough 'is my active Pokemon in immediate danger' signal, used
    only for the PREVENT_LOSS band: badly damaged relative to max HP, or
    afflicted with a status condition."""
    if card_data.hp <= 0:
        return False
    hp_frac = pokemon.hp / max(1, pokemon.maxHp)
    return hp_frac <= 0.34 or my_state.asleep or my_state.paralyzed or my_state.confused


def make_agent(deck: list[int]) -> Callable[[dict], list[int]]:
    """Build a self-contained `agent(obs_dict) -> list[int]` closure bound to
    `deck`. Cross-call state lives in the closure, not module globals, so
    multiple decks (or a mirror match) can each get an independent agent
    instance -- unlike the notebook-derived agents in this package, which use
    module-level globals and are documented as unsafe for mirror matches."""

    card_table = _card_table()
    attack_table = _attack_table()

    stats = {"reason_counts": defaultdict(int), "calls": 0}

    def score_option(obs: Observation, index: int, option) -> tuple[int, str]:
        state = obs.current
        select = obs.select
        my_index = state.yourIndex
        my_state = state.players[my_index]
        op_state = state.players[1 - my_index]
        context = select.context

        my_active = my_state.active[0] if my_state.active else None
        op_active = op_state.active[0] if op_state.active else None
        my_remaining_prizes = len(my_state.prize)

        t = option.type

        if t == OptionType.END:
            return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]

        if t == OptionType.YES:
            if context == SelectContext.IS_FIRST:
                # Going second grants the extra first-turn draw in this
                # ruleset; the one notebook-derived agent explicitly tuned
                # for competitive play (dragapult_agent.py) makes the same
                # choice. Everything else defaults to accepting.
                return BAND_SCORE[REASON["PRIZE_EFFICIENT_ATTACK"]], "DECLINE_GO_FIRST"
            return BAND_SCORE[REASON["SETUP_EVOLUTION"]], "ACCEPT_BENEFICIAL_YESNO"

        if t == OptionType.NO:
            if context == SelectContext.IS_FIRST:
                return BAND_SCORE[REASON["SETUP_EVOLUTION"]], "DECLINE_GO_FIRST_NO_BRANCH"
            return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]

        if t == OptionType.ATTACK:
            attack = attack_table.get(option.attackId)
            attacker_data = card_table.get(my_active.id) if my_active else None
            if attack is None or my_active is None or op_active is None or attacker_data is None:
                return BAND_SCORE[REASON["PRIZE_EFFICIENT_ATTACK"]], REASON["PRIZE_EFFICIENT_ATTACK"]
            defender_data = card_table[op_active.id]
            dmg = estimate_damage(attack, attacker_data, defender_data)
            is_ko = dmg >= op_active.hp
            if is_ko and prize_value(defender_data) >= my_remaining_prizes:
                return BAND_SCORE[REASON["WINNING_ATTACK"]] + dmg, REASON["WINNING_ATTACK"]
            if is_ko:
                return BAND_SCORE[REASON["GUARANTEED_KO"]] + dmg, REASON["GUARANTEED_KO"]
            return BAND_SCORE[REASON["PRIZE_EFFICIENT_ATTACK"]] + dmg, REASON["PRIZE_EFFICIENT_ATTACK"]

        if t == OptionType.RETREAT:
            if my_active is not None:
                data = card_table.get(my_active.id)
                if data is not None and _in_danger(my_active, data, my_state):
                    return BAND_SCORE[REASON["PREVENT_LOSS"]], REASON["PREVENT_LOSS"]
            return BAND_SCORE[REASON["FALLBACK"]] - 1, REASON["FALLBACK"]

        if t == OptionType.EVOLVE:
            pokemon = get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
            evolved_card = get_card(obs, option.area, option.index, my_index)
            bonus = 0
            if evolved_card is not None:
                data = card_table.get(evolved_card.id)
                if data is not None:
                    bonus = 300 if data.stage2 else 150 if data.stage1 else 0
            energy_bonus = len(pokemon.energies) if isinstance(pokemon, Pokemon) else 0
            return BAND_SCORE[REASON["SETUP_EVOLUTION"]] + bonus + energy_bonus, REASON["SETUP_EVOLUTION"]

        if t == OptionType.ATTACH:
            card = get_card(obs, option.area, option.index, my_index)
            pokemon = get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
            if card is None or not isinstance(pokemon, Pokemon):
                return BAND_SCORE[REASON["ENERGY_ACCELERATION"]], REASON["ENERGY_ACCELERATION"]
            data = card_table.get(card.id)
            is_tool = data is not None and data.cardType == CardType.TOOL
            is_active = option.inPlayArea == AreaType.ACTIVE
            bonus = 500 if is_tool else 0
            bonus += 200 if is_active else 0
            bonus -= 50 * len(pokemon.energies)  # prefer under-developed attachments first
            return BAND_SCORE[REASON["ENERGY_ACCELERATION"]] + bonus, REASON["ENERGY_ACCELERATION"]

        if t == OptionType.ABILITY:
            danger_of_deckout = my_state.deckCount <= 3
            if danger_of_deckout:
                return BAND_SCORE[REASON["FALLBACK"]], "ABILITY_DECKOUT_RISK"
            return BAND_SCORE[REASON["DRAW_CONSISTENCY"]], REASON["DRAW_CONSISTENCY"]

        if t == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            data = card_table.get(card.id) if card is not None else None
            if data is None:
                return BAND_SCORE[REASON["BOARD_DEVELOPMENT"]], REASON["BOARD_DEVELOPMENT"]
            if data.cardType == CardType.POKEMON:
                return BAND_SCORE[REASON["SETUP_EVOLUTION"]] - 100, REASON["SETUP_EVOLUTION"]
            if data.cardType == CardType.SUPPORTER:
                if _text_has_any(_skill_text(data), _DISRUPT_KEYWORDS):
                    return BAND_SCORE[REASON["DISRUPTION"]] + 1000, REASON["DISRUPTION"]
                return BAND_SCORE[REASON["DRAW_CONSISTENCY"]] + 500, REASON["DRAW_CONSISTENCY"]
            if data.cardType == CardType.STADIUM:
                return BAND_SCORE[REASON["BOARD_DEVELOPMENT"]] + 100, REASON["BOARD_DEVELOPMENT"]
            if data.cardType == CardType.TOOL:
                return BAND_SCORE[REASON["BOARD_DEVELOPMENT"]] + 200, REASON["BOARD_DEVELOPMENT"]
            # ITEM (includes basic/special energy played as items in some flows)
            if _text_has_any(_skill_text(data), _DRAW_KEYWORDS):
                return BAND_SCORE[REASON["DRAW_CONSISTENCY"]], REASON["DRAW_CONSISTENCY"]
            if _text_has_any(_skill_text(data), _SEARCH_KEYWORDS):
                return BAND_SCORE[REASON["ENERGY_ACCELERATION"]] + 300, REASON["ENERGY_ACCELERATION"]
            return BAND_SCORE[REASON["BOARD_DEVELOPMENT"]], REASON["BOARD_DEVELOPMENT"]

        if t == OptionType.CARD:
            card = get_card(obs, option.area, option.index, option.playerIndex)
            if context in (SelectContext.SWITCH, SelectContext.TO_ACTIVE, SelectContext.SETUP_ACTIVE_POKEMON):
                if isinstance(card, Pokemon) and option.playerIndex == my_index:
                    data = card_table.get(card.id)
                    stage_bonus = 300 if data and data.stage2 else 150 if data and data.stage1 else 0
                    return (
                        BAND_SCORE[REASON["SETUP_EVOLUTION"]] + stage_bonus + card.hp + 50 * len(card.energies),
                        REASON["SETUP_EVOLUTION"],
                    )
                return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]
            if context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH, SelectContext.TO_FIELD):
                if isinstance(card, Pokemon):
                    data = card_table.get(card.id)
                    stage_bonus = 200 if data and data.stage2 else 100 if data and data.stage1 else 0
                    return BAND_SCORE[REASON["BOARD_DEVELOPMENT"]] + stage_bonus, REASON["BOARD_DEVELOPMENT"]
                return BAND_SCORE[REASON["BOARD_DEVELOPMENT"]], REASON["BOARD_DEVELOPMENT"]
            if context in (SelectContext.DAMAGE_COUNTER, SelectContext.DAMAGE_COUNTER_ANY, SelectContext.DAMAGE):
                # Prefer piling damage onto whichever opposing Pokemon is
                # closest to a KO (maximizes near-term KO opportunities).
                if isinstance(card, Pokemon) and option.playerIndex != my_index:
                    data = card_table.get(card.id)
                    prize = prize_value(data) if data else 1
                    return BAND_SCORE[REASON["GUARANTEED_KO"]] - card.hp + prize * 50, REASON["GUARANTEED_KO"]
                return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]
            if context in (SelectContext.DISCARD, SelectContext.DISCARD_CARD_OR_ATTACHED_CARD):
                data = card_table.get(card.id) if card is not None else None
                if data is None:
                    return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]
                # Discard the least valuable card first: basic energy < item <
                # tool < pokemon < supporter (rough generic ordering).
                rank = {
                    CardType.BASIC_ENERGY: 0,
                    CardType.SPECIAL_ENERGY: 1,
                    CardType.ITEM: 2,
                    CardType.TOOL: 3,
                    CardType.POKEMON: 4,
                    CardType.STADIUM: 4,
                    CardType.SUPPORTER: 5,
                }.get(data.cardType, 3)
                return BAND_SCORE[REASON["FALLBACK"]] + (5 - rank) * 10, "DISCARD_LEAST_VALUABLE"
            if context in (SelectContext.EVOLVES_FROM, SelectContext.EVOLVES_TO, SelectContext.ATTACH_FROM, SelectContext.ATTACH_TO):
                if isinstance(card, Pokemon):
                    return BAND_SCORE[REASON["ENERGY_ACCELERATION"]] - 50 * len(card.energies), REASON["ENERGY_ACCELERATION"]
                return BAND_SCORE[REASON["ENERGY_ACCELERATION"]], REASON["ENERGY_ACCELERATION"]
            if context == SelectContext.TO_HAND:
                return BAND_SCORE[REASON["DRAW_CONSISTENCY"]], REASON["DRAW_CONSISTENCY"]
            # Any other CARD context not explicitly modeled: neutral fallback.
            return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]

        if t in (OptionType.ENERGY, OptionType.ENERGY_CARD, OptionType.TOOL_CARD):
            return BAND_SCORE[REASON["ENERGY_ACCELERATION"]], REASON["ENERGY_ACCELERATION"]

        if t == OptionType.NUMBER:
            return option.number or 0, "NUMBER"

        if t == OptionType.SKILL:
            return BAND_SCORE[REASON["DRAW_CONSISTENCY"]], REASON["DRAW_CONSISTENCY"]

        if t == OptionType.SPECIAL_CONDITION:
            return BAND_SCORE[REASON["PREVENT_LOSS"]], REASON["PREVENT_LOSS"]

        if t == OptionType.DISCARD:
            return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]

        # Unmodeled OptionType (including any appended during the
        # competition per cg.api's own comments): safe neutral score, never
        # a crash.
        return BAND_SCORE[REASON["FALLBACK"]], REASON["FALLBACK"]

    def _skill_text(data: CardData) -> str | None:
        return " ".join(s.text for s in data.skills) if data.skills else None

    def agent(obs_dict: dict) -> list[int]:
        stats["calls"] += 1
        from cg.api import to_observation_class

        obs: Observation = to_observation_class(obs_dict)
        if obs.select is None:
            return list(deck)

        select = obs.select
        scores: list[int] = []
        last_reason = REASON["FALLBACK"]
        for i, option in enumerate(select.option):
            try:
                score, reason = score_option(obs, i, option)
            except Exception:  # noqa: BLE001 - a scoring bug must never crash the agent
                score, reason = BAND_SCORE[REASON["FALLBACK"]], "SCORE_EXCEPTION_FALLBACK"
            scores.append(score)
            if i == 0 or score > BAND_SCORE[REASON["FALLBACK"]]:
                last_reason = reason
        stats["reason_counts"][last_reason] += 1
        return select_top(select, select.context, scores)

    agent.stats = stats  # type: ignore[attr-defined]
    return agent
