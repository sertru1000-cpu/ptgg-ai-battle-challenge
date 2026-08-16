"""Baseline agent #5: Mega Lucario ex.

Ported from the official sample notebook
`sample_notebooks/a-sample-rule-based-agent-mega-lucario-ex-deck.ipynb`
("Intermediate Level"). Behavior-preserving port: scoring/planning logic
unchanged, refactored only to use src.agents.common's shared get_card()
helper and load its deck from an explicit path (decks/lucario_ex.csv,
built directly from the notebook's named-constant decklist counts, summed
to exactly 60 and confirmed legal via battle_start: errorType=0).

Faithfully preserves two notebook properties that might look like omissions
but are not porting bugs:
- Dusk_Ball (1102) and Fighting_Gong (1142) are named deck constants with no
  card-ID-specific scoring branch anywhere in the notebook -- they fall
  through to the generic per-option-type default score, same as here.
- The selection tail is NOT src.agents.common.select_top() -- like
  Abomasnow ex and Iono's, this notebook always fills to select.maxCount
  regardless of score sign (select.minCount is never consulted). Unlike
  those two, it has one extra stateful hook after sorting (before
  truncating to maxCount): if the top-ranked MAIN-context option is an
  ABILITY use of Lunatone, `ability_used` is set for the rest of the turn.
  That hook is preserved verbatim below rather than folded into a shared
  helper.

Known limitation carried over from the notebook, not fixed here: uses
cross-call `global` state (plan, pre_turn, ability_used), so two players
sharing the same imported module instance (a mirror match) would corrupt
each other's tracking. Not used in a mirror-match pairing this phase.
"""

from collections import defaultdict
from pathlib import Path

from src.agents.common import get_card
from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import (  # noqa: E402
    AreaType,
    CardType,
    EnergyType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_card_data,
    to_observation_class,
)

_DECK_PATH = Path(__file__).resolve().parents[2] / "decks" / "lucario_ex.csv"
DECK: list[int] = [int(x) for x in _DECK_PATH.read_text().split("\n")[:60]]

_all_card = all_card_data()
_card_table = {c.cardId: c for c in _all_card}

# Decklist (named constants from the notebook)
Makuhita = 673
Hariyama = 674
Lunatone = 675
Solrock = 676
Riolu = 677
Mega_Lucario_ex = 678
Dusk_Ball = 1102
Switch = 1123
Premium_Power_Pro = 1141
Fighting_Gong = 1142
Poke_Pad = 1152
Hero_Cape = 1159
Boss_Orders = 1182
Carmine = 1192
Lillie_Determination = 1227
Gravity_Mountain = 1252
Basic_Fighting_Energy = 6


class AttackPlan:
    attacker: int = -1
    target: int = -1
    attack_index: int = -1
    remain_hp: int = -1
    energy: bool = False


plan = AttackPlan()
pre_turn = 0
ability_used = False


def prize_count(pokemon: Pokemon) -> int:
    """Calculates how many Prize cards a Pokemon yields upon being Knocked Out, factoring in modifiers."""
    data = _card_table[pokemon.id]
    count = 3 if data.megaEx else 2 if data.ex else 1
    for card in pokemon.energyCards:
        if card.id == 12:  # Legacy Energy
            count -= 1
    for card in pokemon.tools:
        if card.id == 1172 and "Lillie" in data.name:  # Lillie's Pearl
            count -= 1
    return max(0, count)


def pokemon_score(pokemon: Pokemon) -> int:
    """Heuristically evaluates the tactical worth of targeting a specific Pokemon on the opponent's field."""
    data = _card_table[pokemon.id]
    score = prize_count(pokemon) * 1000
    score += len(pokemon.energies) * 150
    score += len(pokemon.tools) * 100
    if data.stage2:
        score += 250
    elif data.stage1:
        score += 130

    id = pokemon.id
    if id == 173 or id == 174 or id == 190 or id == 1071:
        score -= 200
    if id == 112 and len(pokemon.energies) >= 1:  # Munkidori
        score += 300
    score += pokemon.hp
    return score


def agent(obs_dict: dict) -> list[int]:
    obs: Observation = to_observation_class(obs_dict)
    if obs.select is None:
        return DECK

    global plan, pre_turn, ability_used

    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]
    my_prize = len(my_state.prize)

    if pre_turn != state.turn:
        pre_turn = state.turn
        plan = AttackPlan()
        ability_used = False

    field_counts: dict[int, int] = defaultdict(int)
    hand_counts: dict[int, int] = defaultdict(int)
    discard_counts: dict[int, int] = defaultdict(int)

    attacker1 = False
    attacker2 = False
    for card in my_state.active + my_state.bench:
        if card is None:
            continue
        field_counts[card.id] += 1
        if card.id == Makuhita or card.id == Hariyama:
            if len(card.energies) >= 3:
                attacker2 = True
        elif card.id == Riolu or card.id == Mega_Lucario_ex:
            if len(card.energies) >= 2:
                attacker1 = True

    for card in my_state.hand:
        hand_counts[card.id] += 1

    for card in my_state.discard:
        discard_counts[card.id] += 1

    stadium_id = 0
    for card in state.stadium:
        stadium_id = card.id

    can_attack = False
    if context == SelectContext.MAIN:
        can_switch = False
        can_op_switch = False
        can_use_mega_brave = False
        for o in select.option:
            if o.type == OptionType.PLAY:
                card = get_card(obs, AreaType.HAND, o.index, my_index)
                if card.id == Switch:
                    can_switch = True
                elif card.id == Boss_Orders:
                    can_op_switch = True
            elif o.type == OptionType.EVOLVE:
                card = get_card(obs, AreaType.HAND, o.index, my_index)
                if card.id == Hariyama:
                    can_op_switch = True
            elif o.type == OptionType.RETREAT:
                can_switch = True
            elif o.type == OptionType.ATTACK:
                can_attack = True
                if o.attackId == 983:  # Mega Brave
                    can_use_mega_brave = True

        my_cards = [my_state.active[0]]
        for pokemon in my_state.bench:
            my_cards.append(pokemon)
        op_cards = [op_state.active[0]]
        for pokemon in op_state.bench:
            op_cards.append(pokemon)

        if state.turn >= 2:
            best_score = -1
            for i, my_pokemon in enumerate(my_cards):
                if i != 0 and not can_switch:
                    break
                for a in range(2):
                    energy_required = 0
                    base_damage = 0
                    base_score = 0
                    if my_pokemon.id == Mega_Lucario_ex:
                        if a == 0:
                            energy_required = 1
                            base_damage = 130
                            base_score += 60 * min(3, discard_counts[Basic_Fighting_Energy])
                        else:
                            energy_required = 2
                            base_damage = 270
                        if my_prize == 2 or my_prize == 3:
                            base_score -= 500
                    elif a == 1:
                        break
                    elif my_pokemon.id == Hariyama:
                        energy_required = 3
                        base_damage = 210
                    elif my_pokemon.id == Makuhita:
                        for o in select.option:
                            if o.type == OptionType.EVOLVE:
                                index = o.inPlayIndex
                                if o.inPlayArea == AreaType.BENCH:
                                    index += 1
                                if index == i:
                                    break
                        else:
                            break
                        base_score -= 100
                        energy_required = 3
                        base_damage = 210
                    elif my_pokemon.id == Solrock:
                        if field_counts[Lunatone] >= 1:
                            energy_required = 1
                            base_damage = 70

                    if base_damage <= 0:
                        continue

                    more_energy = False
                    energy_count = len(my_pokemon.energies)
                    if a == 1 and i == 0 and energy_count >= 2 and not can_use_mega_brave:
                        break
                    if energy_count < energy_required:
                        if hand_counts[Basic_Fighting_Energy] >= 1 and not state.energyAttached:
                            energy_count += 1
                            if energy_count < energy_required:
                                continue
                            else:
                                more_energy = True
                        else:
                            continue

                    for j, op_pokemon in enumerate(op_cards):
                        if j != 0 and not can_op_switch:
                            break
                        damage = base_damage
                        data = _card_table[op_pokemon.id]
                        if data.weakness == EnergyType.FIGHTING:
                            damage *= 2
                        elif data.resistance == EnergyType.FIGHTING:
                            damage -= 30
                        prize = 0
                        score = pokemon_score(op_pokemon)
                        if op_pokemon.hp <= damage:
                            prize = prize_count(op_pokemon)
                        else:
                            score *= damage / op_pokemon.hp
                        score += base_score

                        if len(op_state.prize) <= prize:
                            score = 50000

                        if i == 0:
                            score += 220
                        if j == 0:
                            score += 300
                        score += energy_count
                        if best_score < score:
                            best_score = score
                            plan.attacker = i
                            plan.target = j
                            plan.attack_index = a
                            plan.remain_hp = op_pokemon.hp - damage
                            plan.energy = more_energy

    def energy_score(pokemon: Pokemon, active: bool) -> int:
        energy_count = len(pokemon.energies)
        score = 8000
        if active:
            score += 10
        if pokemon.id == Makuhita or pokemon.id == Hariyama:
            if pokemon.id == Hariyama:
                score += 1
            if energy_count < 3:
                score += 100
            if attacker2:
                score -= 50
        elif pokemon.id == Lunatone:
            score -= 100
        elif pokemon.id == Solrock:
            if energy_count < 1:
                score += 20
            else:
                score -= 100
        elif pokemon.id == Riolu or pokemon.id == Mega_Lucario_ex:
            if pokemon.id == Mega_Lucario_ex:
                score += 1
            if energy_count < 2:
                score += 100
            if attacker1:
                score -= 50
        return score

    scores: list = []
    for o in select.option:
        score = 0
        if o.type == OptionType.NUMBER:
            score = o.number
        elif o.type == OptionType.YES:
            score = 1
        elif o.type == OptionType.CARD:
            card = get_card(obs, o.area, o.index, o.playerIndex)
            if card is not None:
                energy_count = 0
                if isinstance(card, Pokemon):
                    energy_count = len(card.energies)
                if context == SelectContext.SWITCH or context == SelectContext.TO_ACTIVE:
                    if o.playerIndex == my_index:
                        score += energy_count * 2
                        if o.index == plan.attacker - 1:
                            score += 100
                        if card.id == Mega_Lucario_ex:
                            if my_prize == 2 or my_prize == 3:
                                score += 8
                            else:
                                score += 20
                        elif card.id == Hariyama and energy_count >= 2:
                            score += 15
                        elif card.id == Makuhita and energy_count >= 2:
                            score += 10
                        elif card.id == Solrock:
                            score += 5
                        elif card.id == Riolu:
                            score += 4
                    else:
                        if o.index == plan.target - 1:
                            score += 100
                elif context == SelectContext.SETUP_ACTIVE_POKEMON:
                    if card.id == Solrock:
                        score = 2 if state.firstPlayer == my_index else 4
                    elif card.id == Riolu:
                        score = 3
                    elif card.id == Makuhita:
                        score = 1
                elif context == SelectContext.TO_HAND:
                    score = 200 - hand_counts[card.id] * 100
                    if card.id == Makuhita:
                        score += -10 if field_counts[card.id] >= 1 else 10
                    elif card.id == Hariyama:
                        score += 20 if field_counts[Makuhita] >= 1 else -20
                    elif card.id == Lunatone:
                        score += -250 if field_counts[card.id] >= 1 else 60
                    elif card.id == Solrock:
                        score += -250 if field_counts[card.id] >= 1 else 50
                    elif card.id == Riolu:
                        if field_counts[card.id] + field_counts[Mega_Lucario_ex] >= 2:
                            score -= 150
                        elif field_counts[card.id] + field_counts[Mega_Lucario_ex] >= 1:
                            score -= 3
                        else:
                            score += 40
                    elif card.id == Mega_Lucario_ex:
                        score += 40 if field_counts[Riolu] >= 1 else -15
                    elif card.id == Basic_Fighting_Energy:
                        score += 30 if (not ability_used or not state.energyAttached) else -1
                elif context == SelectContext.ATTACH_FROM:
                    score = energy_score(card, o.area == AreaType.ACTIVE)
        elif o.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, o.index, my_index)
            data = _card_table[card.id]
            if data.cardType == CardType.POKEMON:
                score = 20000
                if card.id == Lunatone or card.id == Solrock:
                    if field_counts[card.id] >= 1:
                        score = -1
                elif card.id == Riolu:
                    if field_counts[card.id] + field_counts[Mega_Lucario_ex] >= 2:
                        score = -1
            else:
                score = 10000
                if card.id == Switch:
                    score = -1 if plan.attacker <= 0 else 6000
                elif card.id == Premium_Power_Pro:
                    if state.supporterPlayed and plan.remain_hp <= 0:
                        score = -1
                    elif not can_attack:
                        if not state.supporterPlayed and hand_counts[Carmine] > 0 and hand_counts[Lillie_Determination] == 0:
                            score = 3050
                        else:
                            score = -1
                    else:
                        score = 5000
                elif card.id == Boss_Orders:
                    score = 3200 if plan.target >= 1 else -1
                elif card.id == Carmine:
                    score = 3000
                elif card.id == Lillie_Determination:
                    score = 3100
                elif card.id == Gravity_Mountain:
                    if stadium_id == 0:
                        score = -1
        elif o.type == OptionType.ATTACH:
            card = get_card(obs, AreaType.HAND, o.index, my_index)
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            if card.id == Hero_Cape:
                score = 7000
                if pokemon.id == Riolu:
                    score += 100
                elif pokemon.id == Mega_Lucario_ex:
                    score += 200
            else:
                score = energy_score(pokemon, o.inPlayArea == AreaType.ACTIVE)
                if o.inPlayArea == AreaType.ACTIVE:
                    if plan.attacker == 0 and plan.energy:
                        score += 200
                else:
                    if plan.attacker == 1 + o.inPlayIndex and plan.energy:
                        score += 200
        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            score = 9000 + len(pokemon.energies)
            if pokemon.id == Makuhita and plan.target == 0:
                score = -1
        elif o.type == OptionType.ABILITY:
            card = get_card(obs, o.area, o.index, my_index)
            if card.id == 1267:  # Lumiose City
                score = 1
            else:
                score = 30000
        elif o.type == OptionType.RETREAT:
            score = 2000 if plan.attacker >= 1 else -1
        elif o.type == OptionType.ATTACK:
            score = 1000
            if plan.attack_index == 1:
                if o.attackId == 983:  # Mega Brave
                    score += 100
            else:
                if o.attackId != 983:
                    score += 100

        scores.append(score)

    desc_indices = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
    if context == SelectContext.MAIN and desc_indices:
        o = select.option[desc_indices[0]]
        if o.type == OptionType.ABILITY:
            card = get_card(obs, o.area, o.index, my_index)
            if card.id == Lunatone:
                ability_used = True
    return desc_indices[: select.maxCount]
