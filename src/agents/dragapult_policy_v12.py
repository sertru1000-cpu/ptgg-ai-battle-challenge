"""V12 -- MATCHUP-AWARE POLICY. Forked from src/agents/dragapult_policy_v6.py
(V6/BALANCED + the two confirmed Phantom Dive bug fixes), NOT from V10's
policy or deck. Every line of the underlying engine (attack-combo subset-sum
search, hand/attach/switch scoring, the two V6 Phantom Dive fixes) is
unchanged from V6 except at the explicit matchup-aware hook points documented
below and in V12_IMPLEMENTATION_REPORT.md. Deliberately contains NO lookahead
/ search (that is V11's job, forked separately) and NO V8/V9
survival/defensive-retreat heuristics -- V6's own (V2-era) defensive-retreat
hook is carried over unmodified, exactly as in V6, and is not touched by any
V12-specific logic.

WHAT'S NEW (Objectives 2-3 of the V12 task):

1. `detect_archetype()`: a lightweight, per-decision scan of the opponent's
   Active + Bench card IDs (real engine data, `Observation.current.players[..]`,
   never hidden info) that classifies the opponent into SNIPER (the
   Dragapult ex mirror -- Dreepy/Drakloak/Dragapult ex), AGRO_TANK
   (Lucario ex / Crustle-line big hitters), or UNKNOWN (default -- also the
   correct fallback when the opponent's board is empty, e.g. before they've
   played anything).
2. `MatchupWeights`: wraps V6's existing `PolicyWeights` (kept fixed at
   BALANCED, V6's own profile -- V12 does not change V6's base tuning) with
   five new multipliers/bonuses, each identity (1.0 / 0.0) at the UNKNOWN
   profile so `MATCHUP_DEFAULT` reproduces V6's exact scoring formulas.
   Recomputed and applied at the top of every `agent()` call (per the task's
   "before it is passed to pokemon_score() and the main option loop"
   instruction), never persisted stale across turns.

One deliberate deviation from a strict line-for-line V6 copy: V6 carries a
V5-only in-battle opponent-aggression model (`_observe_opponent` /
`_compute_adaptive_weights`, gated behind `adaptive=False` and therefore dead
code whenever `adaptive` is off). That mechanism is orthogonal to this task
(archetype identity, not in-match aggression) and, wired through unchanged,
would create a latent type mismatch the moment `self.weights` stopped being a
`MatchupWeights` (every downstream call site here expects `.base.<field>`).
Removed rather than left in place with a landmine; V12 has no `adaptive` mode.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.agents.common import get_card, select_top
from src.agents.policy_weights import BALANCED, PolicyWeights
from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import (  # noqa: E402
    AreaType,
    CardType,
    Log,
    LogType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_attack,
    all_card_data,
    to_observation_class,
)

_DECK_PATH = Path(__file__).resolve().parents[2] / "decks" / "dragapult_ex.csv"
DECK: list[int] = [int(x) for x in _DECK_PATH.read_text().split("\n")[:60]]

_all_card = all_card_data()
_card_table = {c.cardId: c for c in _all_card}
_attack_table = {a.attackId: a for a in all_attack()}

# Decklist (named constants from the official notebook, identical to V1/V6).
# Confirms V12 plays the EXACT SAME deck as V6 -- see decks/dragapult_ex.csv,
# byte-identical to the file V6 reads.
Dreepy = 119
Drakloak = 120
Dragapult_ex = 121
Fezandipiti_ex = 140
Latias_ex = 184
Budew = 235
Meowth_ex = 1071
Rare_Candy = 1079
Unfair_Stamp = 1080
Buddy_Buddy_Poffin = 1086
Night_Stretcher = 1097
Crushing_Hammer = 1120
Ultra_Ball = 1121
Poke_Pad = 1152
Lucky_Helmet = 1156
Boss_Orders = 1182
Crispin = 1198
Brock_Scouting = 1210
Lillie_Determination = 1227
Team_Rocket_Watchtower = 1256
Basic_Fire_Energy = 2
Basic_Psychic_Energy = 5

UNNECESSARY = -10000000


# ---------------------------------------------------------------------------
# Objective 2: opponent archetype detection
# ---------------------------------------------------------------------------

ARCHETYPE_UNKNOWN = "UNKNOWN"
ARCHETYPE_SNIPER = "SNIPER"
ARCHETYPE_AGRO_TANK = "AGRO_TANK"

# SNIPER: the Dragapult ex mirror -- the same three card IDs as our own deck
# (id space is shared across both players; a Dreepy/Drakloak/Dragapult ex
# seen on the OPPONENT's field means Phantom Dive's 6-damage-counter bench
# spread is a real threat to us).
_SNIPER_IDS = frozenset({Dreepy, Drakloak, Dragapult_ex})

# AGRO_TANK: Lucario ex line (id verified against src/agents/lucario_ex_agent.py
# / data/official/EN Card Data.csv row 1209-1210: Riolu=677/Mega Lucario ex=678,
# MEG set) and the Crustle line (id verified against the same CSV: Dwebble/
# Crustle appear twice, once per printing -- DRI set 344/345, BLK set 532/533;
# both included since either printing is legal and card-name-based detection
# would require a lookup this hot path shouldn't pay for). Also includes
# Riolu's two other legal printings (PRE 333, SCR 974) since any Riolu is a
# reasonable early signal the Lucario ex line is being built even before the
# Mega itself hits the field.
_Riolu_PRE = 333
_Riolu_MEG = 677
_Riolu_SCR = 974
_Mega_Lucario_ex = 678
_Dwebble_DRI = 344
_Crustle_DRI = 345
_Dwebble_BLK = 532
_Crustle_BLK = 533
_AGRO_TANK_IDS = frozenset(
    {
        _Riolu_PRE,
        _Riolu_MEG,
        _Riolu_SCR,
        _Mega_Lucario_ex,
        _Dwebble_DRI,
        _Crustle_DRI,
        _Dwebble_BLK,
        _Crustle_BLK,
    }
)


def detect_archetype(op_state) -> str:
    """Classify the opponent from their currently-visible Active + Bench
    Pokemon IDs (real, non-hidden observation data). SNIPER takes priority
    over AGRO_TANK if somehow both signals are present (shouldn't happen in
    practice -- the two card pools don't overlap). Empty/no-recognized-threat
    board -> UNKNOWN, by construction (empty set intersects nothing).
    """
    op_ids: set[int] = set()
    for card in op_state.active:
        if card is not None:
            op_ids.add(card.id)
    for card in op_state.bench:
        if card is not None:
            op_ids.add(card.id)

    if op_ids & _SNIPER_IDS:
        return ARCHETYPE_SNIPER
    if op_ids & _AGRO_TANK_IDS:
        return ARCHETYPE_AGRO_TANK
    return ARCHETYPE_UNKNOWN


# ---------------------------------------------------------------------------
# Objective 3: dynamic weight shifting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchupWeights:
    """Wraps V6's `PolicyWeights` (kept at BALANCED -- V12 does not retune
    V6's own base profile) with matchup-specific adjustments. Every new field
    is identity (1.0 multiplier / 0.0 bonus) at `MATCHUP_DEFAULT`, so UNKNOWN
    reproduces V6's exact scores. See V12_IMPLEMENTATION_REPORT.md for the
    exact call sites each field touches and why.
    """

    base: PolicyWeights
    bench_hp_multiplier: float = 1.0
    evolution_stage_multiplier: float = 1.0
    low_prize_bench_penalty: float = 0.0
    tempo_bonus: float = 0.0
    energy_accel_bonus: float = 0.0


MATCHUP_DEFAULT = MatchupWeights(base=BALANCED)

# vs SNIPER (Dragapult ex mirror): evolve Dreepy/Drakloak faster (higher-HP,
# harder-to-2HKO-with-counters forms) and lean bulkier when forced to pick a
# new Active from the bench; mildly deprioritize benching Budew (our only
# low-HP, 1-prize, non-evolving Pokemon in this decklist) since it's a cheap
# target for the opponent's own Phantom Dive bench-counter spread and doesn't
# develop our board.
MATCHUP_SNIPER = MatchupWeights(
    base=BALANCED,
    bench_hp_multiplier=1.4,
    evolution_stage_multiplier=1.6,
    low_prize_bench_penalty=12000,
    tempo_bonus=0.0,
    energy_accel_bonus=0.0,
)

# vs AGRO_TANK (Lucario ex / Crustle-line big hitters): press tempo -- reward
# immediate (even partial) damage output more heavily instead of holding back
# for a cleaner future kill, and prioritize accelerating energy onto the
# Active Pokemon to keep attacking every turn.
MATCHUP_AGRO_TANK = MatchupWeights(
    base=BALANCED,
    bench_hp_multiplier=1.0,
    evolution_stage_multiplier=1.0,
    low_prize_bench_penalty=0.0,
    tempo_bonus=2000,
    energy_accel_bonus=600,
)


def matchup_weights_for(archetype: str) -> MatchupWeights:
    if archetype == ARCHETYPE_SNIPER:
        return MATCHUP_SNIPER
    if archetype == ARCHETYPE_AGRO_TANK:
        return MATCHUP_AGRO_TANK
    return MATCHUP_DEFAULT


class AttackPlan:
    attack: int = 0
    counter: list[int] = []


def no_damage_dex(id: int) -> bool:
    """Checks if the defending Pokemon possesses innate immunities preventing Dragapult ex from hitting it."""
    return id == 158 or id == 207 or id == 330 or id == 345


def no_damage_counter(pokemon: Pokemon) -> bool:
    """Checks if a target prevents placement of Phantom Dive's 6 bench damage counters (via abilities/Energy)."""
    if pokemon.id == 28 or pokemon.id == 199 or pokemon.id == 203 or pokemon.id == 207 or pokemon.id == 362 or pokemon.id == 1136:
        return True
    for card in pokemon.energyCards:
        if card.id == 11 or card.id == 20:
            return True
    return False


def prize_count(pokemon: Pokemon, is_attack_damage: bool) -> int:
    """Calculates how many Prize cards a Pokemon yields upon being Knocked Out, factoring in modifiers."""
    data = _card_table[pokemon.id]
    count = 3 if data.megaEx else 2 if data.ex else 1
    if is_attack_damage:
        for card in pokemon.energyCards:
            if card.id == 12:  # Legacy Energy
                count -= 1
        for card in pokemon.tools:
            if card.id == 1172 and "Lillie" in data.name:  # Lillie's Pearl
                count -= 1
    return max(0, count)


def pokemon_score(pokemon: Pokemon, is_attack_damage: bool, weights: MatchupWeights) -> int:
    """Heuristically evaluates the tactical worth of targeting a specific Pokemon on the opponent's field.

    Identical to V6 except: the prize-count term is scaled by
    `weights.base.prize_value_multiplier` (unchanged from V6), and the flat
    HP / evolution-stage addends are now scaled by `weights.bench_hp_multiplier`
    / `weights.evolution_stage_multiplier` respectively (both 1.0 at
    MATCHUP_DEFAULT, i.e. an exact no-op against V6).
    """
    data = _card_table[pokemon.id]
    score = prize_count(pokemon, is_attack_damage) * 1000 * weights.base.prize_value_multiplier
    score += len(pokemon.energies) * 150
    score += len(pokemon.tools) * 100
    if data.stage2:
        score += 250 * weights.evolution_stage_multiplier
    elif data.stage1:
        score += 130 * weights.evolution_stage_multiplier

    id = pokemon.id
    if id == 173 or id == 174 or id == 190 or id == 1071:
        score -= 200
    if id == 112 and len(pokemon.energies) >= 1:  # Munkidori
        score += 300
    score += pokemon.hp * weights.bench_hp_multiplier
    return score


def with_always_first(agent_fn: Callable[[dict], list[int]]) -> Callable[[dict], list[int]]:
    """Same single-decision override as V6's -- always elects to go first,
    delegates every other decision unchanged to `agent_fn`.
    """

    def wrapped(obs_dict: dict) -> list[int]:
        if obs_dict.get("select") is not None:
            obs = to_observation_class(obs_dict)
            if obs.select is not None and obs.select.context == SelectContext.IS_FIRST:
                for i, o in enumerate(obs.select.option):
                    if o.type == OptionType.YES:
                        return [i]
        return agent_fn(obs_dict)

    wrapped.__name__ = f"always_first_{getattr(agent_fn, '__name__', 'agent')}"
    return wrapped


class DragapultPolicy:
    """One independent, stateful policy instance -- same per-instance state
    isolation rationale as V6 (never share an instance's `agent` method
    across two simultaneous seats).
    """

    def __init__(self, weights: PolicyWeights):
        # `weights` is the V6 base profile (BALANCED); wrapped into a
        # MatchupWeights immediately so every downstream call site has a
        # single consistent type from turn 0 onward.
        self.base_weights = weights
        self.weights: MatchupWeights = MatchupWeights(base=weights)
        self.detected_archetype: str = ARCHETYPE_UNKNOWN

        # Cross-call state (identical to V6's).
        self.can_switch = False
        self.can_attack = False
        self.can_main_attack = False
        self.can_energy_attach = False
        self.use_support = 0
        self.bench_attacker = False
        self.pre_turn_log: list[Log] = []
        self.current_turn_log: list[Log] = []

        self.prize: list[int] = []
        self.card_counts: "defaultdict[int, int]" = defaultdict(int)
        self.serial_set: set[int] = set()
        self.plan_a = AttackPlan()
        self.plan_b = AttackPlan()

    # -- cross-call bookkeeping (identical logic to V6's) --

    def add_card_count(self, card, my_index: int):
        if card is None:
            return
        if isinstance(card, Pokemon) or card.playerIndex == my_index:
            if card.serial not in self.serial_set:
                self.card_counts[card.id] -= 1
                self.serial_set.add(card.serial)
        if isinstance(card, Pokemon):
            for c in card.energyCards:
                self.add_card_count(c, my_index)
            for c in card.tools:
                self.add_card_count(c, my_index)
            for c in card.preEvolution:
                self.add_card_count(c, my_index)

    def set_card_counts(self, obs: Observation, my_index: int):
        self.card_counts.clear()
        self.serial_set.clear()
        for id in DECK:
            self.card_counts[id] += 1

        state = obs.current
        my_state = state.players[my_index]
        for card in my_state.hand:
            self.add_card_count(card, my_index)
        for card in my_state.discard:
            self.add_card_count(card, my_index)
        for card in my_state.bench:
            self.add_card_count(card, my_index)
        for card in my_state.active:
            self.add_card_count(card, my_index)
        for card in state.stadium:
            self.add_card_count(card, my_index)
        if state.looking is not None:
            for card in state.looking:
                self.add_card_count(card, my_index)
        self.add_card_count(obs.select.effect, my_index)

    def main_option_proc(self, obs: Observation, damage: int):
        state = obs.current
        select = obs.select
        my_index = state.yourIndex
        my_state = state.players[my_index]
        op_state = state.players[1 - my_index]
        weights = self.weights

        self.can_switch = False
        self.can_attack = False
        self.can_main_attack = False
        self.can_energy_attach = False
        for o in select.option:
            if o.type == OptionType.RETREAT:
                self.can_switch = True
            elif o.type == OptionType.ATTACK:
                self.can_attack = True
                if o.attackId == 154:  # Phantom Dive
                    self.can_main_attack = True

        self.plan_a.attack = -1
        self.plan_b.attack = -1
        if not self.can_main_attack and not (self.bench_attacker and self.can_switch):
            return

        cards = [op_state.active[0]]
        for pokemon in op_state.bench:
            cards.append(pokemon)
        counter_indices = []
        ci = []
        ci.append(0)
        remain_damage = 60
        while ci:
            index = ci[-1]
            hp = cards[index].hp
            if remain_damage >= hp:
                counter_indices.append(ci.copy())
                if index < len(cards) - 1:
                    remain_damage -= hp
                    ci.append(index + 1)
                    continue
            if index == len(cards) - 1:
                ci.pop()
                if ci:
                    remain_damage += cards[ci[-1]].hp
            if ci:
                ci[-1] += 1
        counter_indices.append([])

        remain_prize = len(my_state.prize)
        plan_score = 0
        for i, pokemon in enumerate(cards):
            base_prize_count = 0
            base_score = pokemon_score(pokemon, True, weights)
            if i == 0 and self.can_main_attack:
                # V6 FIX #2: Phantom Dive (the only attack that sets
                # can_main_attack) never damages the opponent's Active --
                # see PHANTOM_DIVE_ARCHITECTURE_AUDIT.md §3.3. Using the
                # generic `damage` constant here wrongly treats the Active
                # as taking 200 damage, which both fabricates a prize and
                # can short-circuit the bench-counter combo search below.
                active_damage = 0
            else:
                active_damage = 0 if no_damage_dex(pokemon.id) else damage
            if pokemon.hp <= active_damage:
                base_prize_count += prize_count(pokemon, True)
            else:
                # V12 AGRO_TANK hook: reward immediate (even partial) damage
                # output more heavily -- `tempo_bonus` is scaled by the same
                # damage/hp ratio as the base score so it only meaningfully
                # kicks in for a real chunk of damage, not a token poke.
                # Identity 0.0 outside AGRO_TANK, so this is a no-op vs V6
                # for SNIPER/UNKNOWN.
                ratio = active_damage / pokemon.hp
                base_score *= ratio
                base_score += weights.tempo_bonus * ratio
            ci = []
            max_score = base_score
            if remain_prize <= base_prize_count:
                max_score = 50000
            else:
                for indices in counter_indices:
                    if i in indices:
                        continue
                    prize = base_prize_count
                    score = base_score
                    for index in indices:
                        prize += prize_count(cards[index], False)
                        score += pokemon_score(cards[index], False, weights)
                    if remain_prize <= prize:
                        score = 50000
                    else:
                        if prize >= 2:
                            if remain_prize <= 4:
                                score -= 1200
                        elif prize == 1:
                            score -= 300
                        else:
                            score += 1200
                    if max_score < score:
                        max_score = score
                        ci = indices
            if plan_score < max_score:
                plan_score = max_score
                self.plan_a.attack = i
                self.plan_a.counter = ci
            if i == 0:
                self.plan_b.attack = self.plan_a.attack
                self.plan_b.counter = self.plan_a.counter

    # -- V6's own (V2-era) hook: defensive retreat to deny a likely-lethal
    # heavy hit. Carried over completely unmodified -- V12 does not add,
    # tune, or otherwise touch this, per the task's explicit instruction to
    # ignore the V8/V9 survival/defensive-retreat heuristics. --

    def _wants_defensive_retreat(self, my_active: Pokemon | None, op_active: Pokemon | None) -> bool:
        if not self.weights.base.defensive_retreat_enabled:
            return False
        if self.can_attack:
            return False  # never give up a legal attack this turn to retreat defensively
        if my_active is None or op_active is None:
            return False
        op_card = _card_table.get(op_active.id)
        if op_card is None:
            return False
        op_energy_count = len(op_active.energies)
        threshold = my_active.hp * self.weights.base.defensive_retreat_hp_fraction
        for aid in op_card.attacks:
            atk = _attack_table.get(aid)
            if atk is None or atk.damage <= 0:
                continue
            if op_energy_count >= len(atk.energies) and atk.damage >= threshold:
                return True
        return False

    # -- main entry point --

    def agent(self, obs_dict: dict) -> list[int]:
        obs: Observation = to_observation_class(obs_dict)
        if obs.select is None:
            return DECK

        state = obs.current
        select = obs.select
        context = select.context
        my_index = state.yourIndex
        my_state = state.players[my_index]
        op_state = state.players[1 - my_index]

        if state.turn == 0:
            self.prize.clear()
            self.pre_turn_log.clear()
            self.current_turn_log.clear()
        else:
            for log in obs.logs:
                self.current_turn_log.append(log)
                if log.type == LogType.TURN_END:
                    self.pre_turn_log = self.current_turn_log
                    self.current_turn_log = []

        # Objective 2 + 3: detect the opponent's archetype from their
        # currently-visible board and shift weights accordingly, before any
        # scoring below runs. Recomputed every decision (not cached) since
        # the opponent's board can change as the game progresses.
        self.detected_archetype = detect_archetype(op_state)
        self.weights = matchup_weights_for(self.detected_archetype)
        weights = self.weights

        pre_ko = False
        no_item = False
        for log in self.pre_turn_log:
            if log.type == LogType.ATTACK:
                if log.attackId == 323:  # Itchy Pollen
                    no_item = True
            elif log.type == LogType.MOVE_CARD:
                if (
                    log.playerIndex == my_index
                    and (log.fromArea == AreaType.BENCH or log.fromArea == AreaType.ACTIVE)
                    and log.toArea == AreaType.DISCARD
                ):
                    pre_ko = True

        if select.deck is not None:
            self.set_card_counts(obs, my_index)
            for card in select.deck:
                self.card_counts[card.id] -= 1
            self.prize.clear()
            for id in self.card_counts:
                for _ in range(self.card_counts[id]):
                    self.prize.append(id)

        self.set_card_counts(obs, my_index)
        for id in self.prize:
            self.card_counts[id] -= 1
        deck_counts = self.card_counts

        prize_diff = len(my_state.prize) - len(op_state.prize)

        field_counts: dict[int, int] = defaultdict(int)
        hand_counts: dict[int, int] = defaultdict(int)
        discard_counts: dict[int, int] = defaultdict(int)

        active_id = 0
        self.bench_attacker = False
        can_evolve_dreepy = False
        evolve_dreepy_count = 0
        can_evolve_drakloak = False
        damage = 200
        for card in my_state.active:
            if card is None:
                continue
            active_id = card.id
            field_counts[card.id] += 1
            if not card.appearThisTurn:
                if card.id == Dreepy:
                    can_evolve_dreepy = True
                    evolve_dreepy_count += 1
                elif card.id == Drakloak:
                    can_evolve_drakloak = True
        for card in my_state.bench:
            field_counts[card.id] += 1
            if not card.appearThisTurn:
                if card.id == Dreepy:
                    can_evolve_dreepy = True
                    evolve_dreepy_count += 1
                elif card.id == Drakloak:
                    can_evolve_drakloak = True
            if card.id == Dragapult_ex and len(card.energies) >= 2:
                self.bench_attacker = True
        main_pokemon_count = field_counts[Dreepy] + field_counts[Drakloak] + field_counts[Dragapult_ex]
        no_more_dex = field_counts[Dragapult_ex] * 2 >= len(op_state.prize)

        stadium_id = 0
        for card in state.stadium:
            stadium_id = card.id

        support_count = 0

        for card in my_state.discard:
            discard_counts[card.id] += 1

        def attach_score(attach_id: int, pokemon: Pokemon, active: bool) -> int:
            energy_count = len(pokemon.energies)
            if _card_table[attach_id].cardType == CardType.TOOL:
                score = 60000
                if active:
                    score += 1000
                return score

            if pokemon.id == Budew:
                return -1
            elif pokemon.id == Meowth_ex or pokemon.id == Fezandipiti_ex or pokemon.id == Latias_ex:
                if active and not self.can_switch and not my_state.asleep and not my_state.paralyzed:
                    if self.bench_attacker or field_counts[Budew] >= 1:
                        return 22000
                    else:
                        return 18000
                else:
                    return -1
            if active and self.can_main_attack:
                return -1
            score = 20000
            if energy_count >= 2:
                if active and not self.can_switch and not my_state.asleep and not my_state.paralyzed:
                    score += 200
                else:
                    return -1
            elif energy_count == 1:
                if attach_id == pokemon.energyCards[0].id:
                    return -1
                if pokemon.id == Dragapult_ex:
                    score += 250
                elif pokemon.id == Dreepy:
                    score -= 150
                else:
                    score -= 200
                if active:
                    score += 200
            else:
                if active:
                    if self.bench_attacker:
                        score += 400
                else:
                    if pokemon.id == Dragapult_ex:
                        score += 150
                    elif pokemon.id == Dreepy:
                        score += 100
                    else:
                        score += 50
                    if self.bench_attacker:
                        score -= 200
            # V12 AGRO_TANK hook: reward accelerating energy onto the Active
            # Pokemon specifically (tempo). Identity 0.0 outside AGRO_TANK.
            if active:
                score += weights.energy_accel_bonus
            if no_more_dex and (pokemon.id == Dreepy or pokemon.id == Drakloak):
                score -= 500
            return score

        def hand_score(id: int, ignore_count: bool):
            score = 0
            if id == Dreepy:
                score = 1000 if main_pokemon_count >= 3 else 18000
            elif id == Drakloak:
                score = 20000 if can_evolve_dreepy else 3000
            elif id == Dragapult_ex:
                if no_more_dex:
                    score = UNNECESSARY
                elif can_evolve_dreepy and hand_counts[Rare_Candy] >= 1 and not no_item:
                    score = 40000
                elif can_evolve_drakloak:
                    if field_counts[id] == 0:
                        score = 30000
                    elif field_counts[id] == 1:
                        score = 10000
                    else:
                        score = 50
                else:
                    score = 50 if field_counts[id] >= 2 else 2000
            elif id == Fezandipiti_ex:
                if pre_ko:
                    score = 50000
                elif prize_diff <= -2:
                    score = 5
                elif len(op_state.prize) == 1:
                    score = UNNECESSARY
            elif id == Latias_ex:
                if active_id == Fezandipiti_ex or active_id == Meowth_ex or active_id == Dreepy:
                    score = 28000 if field_counts[Drakloak] + field_counts[Dragapult_ex] == 0 else 15000
                else:
                    score = 10
            elif id == Budew:
                if field_counts[id] + field_counts[Drakloak] + field_counts[Dragapult_ex] >= 1:
                    score = UNNECESSARY
                elif state.turn >= 2:
                    # V12 SNIPER hook: mildly deprioritize benching our only
                    # low-HP, 1-prize, non-evolving Pokemon (it's a cheap
                    # target for the opponent's own Phantom Dive bench-
                    # counter spread and doesn't develop our board). Identity
                    # 0.0 outside SNIPER.
                    score = 30000 - weights.low_prize_bench_penalty
            elif id == Meowth_ex:
                if support_count > hand_counts[Boss_Orders] or stadium_id == Team_Rocket_Watchtower:
                    score = 5
                elif state.supporterPlayed:
                    score = 40
                else:
                    score = 35000
            elif id == Rare_Candy:
                if no_more_dex:
                    score = UNNECESSARY
                elif can_evolve_dreepy and hand_counts[Dragapult_ex] >= 1:
                    score = 40000
            elif id == Unfair_Stamp:
                if pre_ko:
                    score = 80000
                elif len(op_state.prize) == 1:
                    score = UNNECESSARY
                else:
                    score = 80
            elif id == Buddy_Buddy_Poffin:
                count = deck_counts[Dreepy]
                if count == 0:
                    score = UNNECESSARY
                else:
                    if state.turn <= 2 and field_counts[Budew] == 0 and deck_counts[Budew] >= 1:
                        count += 1
                    if count >= 2:
                        score = 35000
            elif id == Night_Stretcher:
                for i in discard_counts:
                    if discard_counts[i] >= 1:
                        card_type = _card_table[i].cardType
                        if card_type == CardType.POKEMON or card_type == CardType.BASIC_ENERGY:
                            score = max(score, hand_score(i, ignore_count))
            elif id == Crushing_Hammer:
                score = 20
            elif id == Ultra_Ball:
                score = 70 if (main_pokemon_count <= 2 or field_counts[Dreepy] >= 1) else 5
            elif id == Poke_Pad:
                score = max(hand_score(Dreepy, ignore_count), hand_score(Drakloak, ignore_count))
            elif id == Lucky_Helmet:
                score = 15
            elif id == Boss_Orders:
                if self.plan_a.attack > 0:
                    score = 60000
            elif id == Crispin:
                if not ignore_count or support_count == 0:
                    if deck_counts[Basic_Fire_Energy] == 0 or deck_counts[Basic_Psychic_Energy] == 0:
                        score = 10
                    if not self.can_main_attack and not self.bench_attacker and field_counts[Dragapult_ex] >= 1:
                        score = 55000
                    else:
                        score = 25000
            elif id == Brock_Scouting:
                if not ignore_count or support_count == 0:
                    if state.turn == 2 and field_counts[Budew] + field_counts[Latias_ex] == 0:
                        score = 50000
                    else:
                        score = 30000
            elif id == Lillie_Determination:
                if not ignore_count or support_count == 0:
                    score = 45000
            elif id == Team_Rocket_Watchtower:
                if stadium_id != 0 and stadium_id != Team_Rocket_Watchtower:
                    score = 4000
            elif id == Basic_Fire_Energy or id == Basic_Psychic_Energy:
                if self.can_main_attack and (len(op_state.prize) <= 2 or (self.bench_attacker and len(op_state.prize) <= 4)):
                    score = UNNECESSARY
                else:
                    max_score = -10000
                    for pokemon in my_state.active:
                        if pokemon is None:
                            continue
                        max_score = max(max_score, attach_score(id, pokemon, True))
                    for pokemon in my_state.bench:
                        max_score = max(max_score, attach_score(id, pokemon, False))
                    score = max_score - 5000
                    if self.can_main_attack or self.bench_attacker:
                        score /= 10

            if not ignore_count and hand_counts[id] > 0:
                if id == Drakloak and hand_counts[id] < evolve_dreepy_count:
                    score -= 10
                elif id == Dreepy:
                    score -= 100
                else:
                    score -= 100000
            return score

        if context == SelectContext.MAIN:
            self.main_option_proc(obs, damage)

            self.use_support = 0
            if not state.supporterPlayed:
                support_score = 0
                for o in select.option:
                    if o.type == OptionType.PLAY:
                        card = get_card(obs, AreaType.HAND, o.index, state.yourIndex)
                        if _card_table[card.id].cardType == CardType.SUPPORTER:
                            score = hand_score(card.id, True)
                            if support_score < score:
                                support_score = score
                                self.use_support = card.id

        hand_scores = []
        negative_hand_count = 0
        for card in my_state.hand:
            score = hand_score(card.id, False)
            hand_scores.append(score)
            if score < 0:
                negative_hand_count += 1
            hand_counts[card.id] += 1
            if _card_table[card.id].cardType == CardType.SUPPORTER and card.id != Boss_Orders:
                support_count += 1

        no_draw = my_state.deckCount <= 8
        my_active = my_state.active[0] if my_state.active else None
        op_active = op_state.active[0] if op_state.active else None
        do_switch = not self.can_main_attack and (
            self.bench_attacker or (active_id != Budew and field_counts[Budew] >= 1 and state.turn >= 2)
        )
        if not do_switch:
            do_switch = self._wants_defensive_retreat(my_active, op_active)
        effect_card_id = 0 if select.effect is None else select.effect.id
        context_card_id = 0 if select.contextCard is None else select.contextCard.id

        scores: list = []
        for o in select.option:
            score = 0
            if o.type == OptionType.NUMBER:
                score = o.number
            elif o.type == OptionType.YES:
                score = -1 if context == SelectContext.IS_FIRST else 1
            elif o.type == OptionType.CARD:
                card = get_card(obs, o.area, o.index, o.playerIndex)
                if card is not None:
                    energy_count = 0
                    hp = 0
                    if isinstance(card, Pokemon):
                        energy_count = len(card.energies)
                        hp = card.hp
                    if context == SelectContext.SWITCH or context == SelectContext.TO_ACTIVE or context == SelectContext.SETUP_ACTIVE_POKEMON:
                        if o.playerIndex == my_index:
                            if card.id == Dreepy:
                                score += 10000
                            elif card.id == Drakloak:
                                score += 20000 if energy_count >= 1 else -10000
                            elif card.id == Dragapult_ex:
                                score += 50000
                            elif card.id == Budew:
                                if context != SelectContext.SWITCH:
                                    score += 100000
                                elif not self.bench_attacker:
                                    score += 30000
                            elif card.id == Fezandipiti_ex:
                                score -= 1000 / weights.base.switch_risk_tolerance
                            elif card.id == Meowth_ex:
                                score -= 2000 / weights.base.switch_risk_tolerance
                        else:
                            if self.plan_a.attack == o.index + 1:
                                score += 100000
                        score += energy_count * 1000
                        # V12 SNIPER hook: value bulkier bench replacements
                        # more when facing the mirror (survives the 6-counter
                        # spread better). Identity 1.0 outside SNIPER.
                        score += hp * (1 + weights.base.preservation_bias) * weights.bench_hp_multiplier
                    elif context == SelectContext.SETUP_BENCH_POKEMON:
                        if my_index == state.firstPlayer or card.id != Dreepy:
                            score = -1
                    elif context == SelectContext.TO_BENCH or context == SelectContext.TO_HAND:
                        score = hand_score(card.id, False)
                        hand_counts[card.id] += 1
                        if effect_card_id == Crispin:
                            score = 100000 - hand_score(card.id, True)
                    elif context == SelectContext.DISCARD:
                        hand_counts[card.id] -= 1
                        if _card_table[card.id].cardType == CardType.SUPPORTER:
                            support_count -= 1
                        score = -hand_score(card.id, False)
                    elif context == SelectContext.DAMAGE_COUNTER or context == SelectContext.DAMAGE_COUNTER_ANY:
                        if hp > 0:
                            score = 100000 - 10 * hp + pokemon_score(card, False, weights)
                            if context == SelectContext.DAMAGE_COUNTER:
                                if 210 <= hp <= 230:
                                    score += 20000 + hp * 20
                                    if o.area == AreaType.ACTIVE:
                                        score += 10000
                                elif 40 <= hp <= 90:
                                    score += 10000 + hp * 20
                                elif hp <= 30:
                                    score += -10000 + hp * 20
                                if card.id == 133 or card.id == 351:
                                    score += 30000
                            else:
                                index = o.index + 1
                                if index in self.plan_b.counter:
                                    score += 100000
                                else:
                                    remain_damage = select.remainDamageCounter * 10
                                    if 210 <= hp <= 200 + remain_damage:
                                        score += 30000
                                    elif 20 <= hp <= 60 + remain_damage:
                                        score += 10000
                                    elif hp == 10:
                                        # V6 FIX #1, carried over unchanged.
                                        score += 40000
                                if no_damage_counter(card):
                                    score = -1
                    elif context == SelectContext.ATTACH_FROM:
                        score = attach_score(context_card_id, card, o.area == AreaType.ACTIVE)
                        if card.id == Dragapult_ex:
                            score += 200
            elif o.type == OptionType.ENERGY_CARD or o.type == OptionType.ENERGY:
                if o.playerIndex != state.yourIndex:
                    score = 20 if o.area == AreaType.BENCH else 10
                    card = get_card(obs, o.area, o.index, o.playerIndex)
                    if _card_table[card.id].cardType == CardType.SPECIAL_ENERGY:
                        score += 1
            elif o.type == OptionType.PLAY:
                card = get_card(obs, AreaType.HAND, o.index, my_index)
                card_score = hand_scores[o.index]
                if card.id == Dreepy:
                    score = 51000
                elif card.id == Fezandipiti_ex:
                    score = 53000 if card_score > 0 else -1
                elif card.id == Latias_ex:
                    score = 51000 if (active_id != Drakloak and active_id != Dragapult_ex) else -1
                elif card.id == Budew:
                    score = 52000 if (field_counts[Budew] == 0 and field_counts[Dragapult_ex] == 0) else -1
                elif card.id == Meowth_ex:
                    if state.supporterPlayed or stadium_id == Team_Rocket_Watchtower:
                        score = -1
                    elif support_count == 0:
                        score = 50000
                    elif support_count == hand_counts[Boss_Orders] and not self.plan_a.attack <= 0:
                        score = 50000
                    else:
                        score = -1
                elif card.id == Rare_Candy:
                    score = -1 if no_more_dex else 75000
                elif card.id == Unfair_Stamp:
                    score = 15000
                elif card.id == Night_Stretcher:
                    score = 42000 if card_score >= 18000 else -1
                elif card.id == Crushing_Hammer:
                    score = 40000
                elif card.id == Boss_Orders:
                    score = 35000 if card.id == self.use_support else -1
                elif card.id == Lillie_Determination:
                    score = 14000 if card.id == self.use_support else -1
                elif card.id == Team_Rocket_Watchtower:
                    score = 80000 if (stadium_id > 0 or state.turn == 1) else -1
                elif no_draw:
                    score = -1
                elif card.id == Buddy_Buddy_Poffin:
                    score = 46000 if deck_counts[Dreepy] > 0 else -1
                elif card.id == Ultra_Ball:
                    score = 44000 if negative_hand_count >= 2 else -1
                elif card.id == Poke_Pad:
                    score = 45000 if deck_counts[Dreepy] + deck_counts[Drakloak] > 0 else -1
                elif card.id == Crispin or card.id == Brock_Scouting:
                    score = 35000 if card.id == self.use_support else -1
            elif o.type == OptionType.ATTACH:
                card = get_card(obs, o.area, o.index, my_index)
                pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
                score = attach_score(card.id, pokemon, o.inPlayArea == AreaType.ACTIVE)
            elif o.type == OptionType.EVOLVE:
                pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
                score += len(pokemon.energies)
                if pokemon.id == Dreepy:
                    # V12 SNIPER hook: evolve faster. Identity 1.0 outside
                    # SNIPER.
                    score += 30000 * weights.evolution_stage_multiplier
                elif field_counts[Dragapult_ex] >= 2 or (field_counts[Dragapult_ex] == 1 and len(op_state.prize) <= 2):
                    score = -1
                else:
                    score += 70000 * weights.evolution_stage_multiplier
            elif o.type == OptionType.ABILITY:
                card = get_card(obs, o.area, o.index, my_index)
                if no_draw:
                    score = -1
                elif card.id == 1267:  # Lumiose City
                    score = 1
                else:
                    score = 40000
            elif o.type == OptionType.RETREAT:
                score = 10000 if do_switch else -1
            elif o.type == OptionType.ATTACK:
                score = o.attackId

            scores.append(score)

        return select_top(select, context, scores)


def make_agent(weights: PolicyWeights, always_first: bool = True):
    """Build one independent agent(obs_dict) -> list[int] callable backed by
    a fresh DragapultPolicy instance. `weights` is the fixed V6 base profile
    (BALANCED) the policy falls back to under UNKNOWN / wraps for every
    matchup profile -- V12 does not add an `adaptive` mode (see module
    docstring). Exposes `.policy` (the live instance, useful for
    tests/inspection, including `.policy.detected_archetype`) and `.DECK`.
    """
    policy = DragapultPolicy(weights)
    fn = policy.agent
    if always_first:
        fn = with_always_first(fn)
    fn.policy = policy  # type: ignore[attr-defined]
    fn.__name__ = f"dragapult_v12_{weights.name}"
    return fn
