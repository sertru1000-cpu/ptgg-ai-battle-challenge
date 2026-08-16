"""V16 -- XGBoost-informed BALANCED profile, forked from V6
(src/agents/dragapult_policy_v6.py) with the same two confirmed Phantom Dive
bug fixes. Every line is identical to V6 EXCEPT the changes marked "V16
XGBOOST HOOK" below. Diff against dragapult_policy_v6.py to see the exact
delta.

INTEGRATION DESIGN (read before touching this file):

The trained model (src/agents/xgb_model.json, src/ml/train_xgboost.py) is a
whole-BOARD win-probability regressor: (87-float vectorized Observation) ->
P(the acting player wins). It does NOT score individual candidate Pokemon or
individual Options the way `pokemon_score()` does -- those functions only
ever see a single `Pokemon` object, never a full `Observation`, so there is
no sound way to route the model's output through them directly without a much
larger refactor of `main_option_proc`'s prize-trade subset-sum planner.

Rejected alternative: per-candidate-move batching via the Search API
(`cg.api.search_begin/search_step`, as src/agents/search_lookahead*.py does)
to materialize a real resulting Observation per candidate ATTACK option, then
batch-score them all in one `predict_proba` call. This is the "fully batched"
shape Objective 2 recommends, but search_lookahead_v2's own dev history
(ENGINE_CLONE_LOOKAHEAD_AUDIT.md) shows this API is easy to get subtly wrong
(a real ID-chaining bug was found and fixed there) and costs real per-call
time -- too much refactoring risk for a "stability over complex feature
engineering" R&D pass. Descoped per Objective 2's own explicit fallback:
"If batching requires too much refactoring, ensure single-row inference is
highly optimized."

What this file actually does instead: ONE single-row `predict_proba` call per
decision (`self._xgb_win_prob(obs)`, called once at the top of `agent()`,
never inside a loop over options), on the CURRENT observed state. The
resulting win-probability is fed into the EXISTING, already-validated
AGGRESSIVE<->DEFENSIVE interpolation mechanism V5 uses
(`policy_weights.blend_by_opponent_aggression`) -- repurposed here with a
self-assessed-win-probability signal instead of V5's opponent-aggression
signal, but the same lerp/clamp logic, so no new interpolation code was
written. Winning big -> lean AGGRESSIVE (press the advantage, per V3's own
hypothesis about leaving value on the table). Losing -> lean DEFENSIVE
(preserve resources, matches V4/V5's existing rationale). This changes
`prize_value_multiplier` / `defensive_retreat_enabled` /
`defensive_retreat_hp_fraction` / `preservation_bias` / `switch_risk_tolerance`
all at once, consistently, through code that was already exercised by V5.

Never allowed to crash or block a legal move: `_xgb_win_prob` wraps model
loading and inference in try/except and returns a neutral 0.5 on ANY failure
(model file missing, malformed vector, xgboost import error, ...). This is
defense in depth -- `final_candidate_agent_v16.py` additionally wraps the
whole agent in `safety_wrapper`/`timeout_shield`, same as V14.

MODULE-LEVEL `ML_AVAILABLE` FLAG (added after the initial R&D pass, per an
explicit "Kaggle's cabt sandbox might not have xgboost installed, and
requirements.txt might be ignored -- a crash on `import xgboost` loses a
submission slot" requirement): `import xgboost` and `load_model()` happen
ONCE at module-import time (see the eager-load comment below for why it's
eager, not lazy) inside `_load_xgb_model_once()`, which sets the module
global `ML_AVAILABLE` to True/False and never lets an exception propagate out
of module import. When `ML_AVAILABLE` is False, `agent()` skips calling the
model entirely (no point) and sets `self.weights = BALANCED` -- V6's own
exact, most road-tested static profile, deliberately NOT a new/different
profile (e.g. DEFENSIVE) at the exact moment we're already in a degraded
runtime state. A one-time `sys.stderr` warning is printed the moment
unavailability is detected (import time), not per-decision -- a real match
has hundreds of decisions, and per-decision logging would just be noise once
the situation is already known and static for the rest of the process.

A SECOND, independent degrade path exists for the rarer case where xgboost
imports fine but a specific `predict_proba` call fails mid-match (malformed
vector, unexpected engine-side data): `_xgb_win_prob`'s own try/except
catches that, prints its own one-time warning, and permanently flips
`ML_AVAILABLE` to False for the rest of the process (matches
`timeout_shield.py`'s own "once degraded, stay degraded" precedent) rather
than silently retrying every decision.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Callable

from src.agents.common import get_card, select_top
from src.agents.policy_weights import BALANCED, PolicyWeights, blend_by_opponent_aggression
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

# Decklist (named constants from the official notebook, identical to V1/V6)
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

# -- V16 XGBOOST HOOK: model path + EAGER module-import-time load ------------
# Loaded once, at import time (same pattern as `_all_card`/`_attack_table`
# above) -- NOT lazily on first use. Measured cold cost: `import xgboost` +
# `XGBClassifier.load_model()` takes ~1.9s the first time in a process, which
# blew the <1.0s per-decision latency budget (and nearly tripped
# timeout_shield's 2.0s cutoff) when this was originally lazy-loaded inside
# `_xgb_win_prob`, landing on whichever real decision happened to be first to
# need a win-probability. Paying that cost once at module-import time (before
# any match-budget clock starts, exactly like the existing `_card_table`
# pattern below) means every real per-decision call only pays for
# vectorize()+predict_proba(), which is sub-millisecond.
_XGB_MODEL_PATH = Path(__file__).resolve().parent / "xgb_model.json"
_xgb_model = None
ML_AVAILABLE = False  # flipped True by _load_xgb_model_once() on success; the
# single source of truth `agent()` checks before ever touching the model.


def _warn_fallback(reason: str) -> None:
    print(
        f"[dragapult_policy_v16] WARNING: XGBoost unavailable ({reason}) -- "
        f"falling back to static BALANCED weights for the rest of this process.",
        file=sys.stderr,
    )


def _load_xgb_model_once():
    global _xgb_model, ML_AVAILABLE
    try:
        import xgboost as xgb  # may raise ImportError if not installed (e.g. Kaggle sandbox)

        from src.ml.vectorizer import MISSING

        model = xgb.XGBClassifier(missing=MISSING)
        model.load_model(str(_XGB_MODEL_PATH))  # may raise if xgb_model.json is missing/corrupt
        _xgb_model = model
        ML_AVAILABLE = True
    except Exception as exc:  # noqa: BLE001 -- missing/corrupt model or missing xgboost must never crash the agent
        ML_AVAILABLE = False
        _warn_fallback(f"{type(exc).__name__}: {exc}")


_load_xgb_model_once()


def _get_xgb_model():
    return _xgb_model


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


def pokemon_score(pokemon: Pokemon, is_attack_damage: bool, weights: PolicyWeights) -> int:
    """Heuristically evaluates the tactical worth of targeting a specific Pokemon on the opponent's field.

    Unchanged from V6 -- see this file's module docstring for why the XGBoost
    model is NOT routed through this function (it only ever sees a single
    Pokemon, never the full board Observation the model was trained on).
    """
    data = _card_table[pokemon.id]
    score = prize_count(pokemon, is_attack_damage) * 1000 * weights.prize_value_multiplier
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


def with_always_first(agent_fn: Callable[[dict], list[int]]) -> Callable[[dict], list[int]]:
    """Same single-decision override as V6's -- always elects to go first."""

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
    """One independent, stateful policy instance -- identical contract to V6's.
    Construct one per agent identity; never share an instance's `agent`
    method across two simultaneous seats.
    """

    def __init__(self, weights: PolicyWeights, adaptive: bool = False):
        self.weights = weights
        self.adaptive = adaptive

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

        # V16 XGBOOST HOOK: last computed win-probability, exposed for
        # tests/inspection (e.g. tests/test_xgb_latency.py). None means the
        # model was unavailable for this decision (static BALANCED fallback
        # was used instead) -- never a guessed/neutral number standing in
        # for "the model ran and said 0.5".
        self.last_win_prob: float | None = None

        # V5-vintage fields kept (harmless/unused since adaptive defaults to
        # False for V16's shipped binding) so DragapultPolicy's shape matches
        # V6's exactly; not used by the XGBoost hook below.
        self.opp_turns_observed = 0
        self.opp_attacks = 0
        self.opp_retreats = 0
        self.opp_low_hp_press = 0
        self.opp_low_hp_retreat = 0
        self._watch_serial: int | None = None

    # -- V16 XGBOOST HOOK: single-row current-state win-probability --------

    def _xgb_win_prob(self, obs: Observation) -> float | None:
        """P(the current acting player wins), from the trained value model.

        ONE call per decision, on the CURRENT observed state (not per
        candidate option -- see module docstring for why full per-candidate
        batching was descoped). Returns None if the model is unavailable
        (caller must fall back to a static profile, never guess a neutral
        probability and pretend the model ran). Never raises: a
        `predict_proba` failure mid-match (rarer than an import-time
        failure, but possible -- malformed vector, unexpected engine data)
        prints its own one-time warning and PERMANENTLY flips module-global
        `ML_AVAILABLE` to False, matching timeout_shield.py's own
        "once degraded, stay degraded" precedent rather than silently
        retrying (and potentially re-failing) every subsequent decision.
        """
        global ML_AVAILABLE
        if not ML_AVAILABLE:
            return None
        model = _get_xgb_model()
        if model is None:
            return None
        try:
            from src.ml.vectorizer import ObservationVectorizer

            vec = ObservationVectorizer().vectorize(obs)
            proba = model.predict_proba([vec])[0][1]
            return float(proba)
        except Exception as exc:  # noqa: BLE001
            ML_AVAILABLE = False
            _warn_fallback(f"predict_proba failed mid-match, {type(exc).__name__}: {exc}")
            return None

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
                active_damage = 0
            else:
                active_damage = 0 if no_damage_dex(pokemon.id) else damage
            if pokemon.hp <= active_damage:
                base_prize_count += prize_count(pokemon, True)
            else:
                base_score *= active_damage / pokemon.hp
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

    def _wants_defensive_retreat(self, my_active: Pokemon | None, op_active: Pokemon | None) -> bool:
        if not self.weights.defensive_retreat_enabled:
            return False
        if self.can_attack:
            return False
        if my_active is None or op_active is None:
            return False
        op_card = _card_table.get(op_active.id)
        if op_card is None:
            return False
        op_energy_count = len(op_active.energies)
        threshold = my_active.hp * self.weights.defensive_retreat_hp_fraction
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

        # V16 XGBOOST HOOK: one single-row inference per decision, blended
        # into the SAME AGGRESSIVE<->DEFENSIVE interpolation V5 uses for its
        # opponent-aggression signal -- see module docstring for the mapping
        # (winning big -> lean AGGRESSIVE; losing -> lean DEFENSIVE).
        # ML_AVAILABLE gate: if xgboost/the model is unavailable (Kaggle
        # sandbox missing the package, corrupt model file, ...), skip the
        # model entirely and use the static BALANCED profile V16 was forked
        # from -- never guess a neutral win-probability and blend on it.
        if ML_AVAILABLE:
            self.last_win_prob = self._xgb_win_prob(obs)
        else:
            self.last_win_prob = None

        if self.last_win_prob is not None:
            pseudo_aggression = max(0.0, min(1.0, 1.0 - self.last_win_prob))
            self.weights = blend_by_opponent_aggression(pseudo_aggression, f"xgb_win_prob={self.last_win_prob:.3f}")
        else:
            self.weights = BALANCED
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
                    score = 30000
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
                                score -= 1000 / weights.switch_risk_tolerance
                            elif card.id == Meowth_ex:
                                score -= 2000 / weights.switch_risk_tolerance
                        else:
                            if self.plan_a.attack == o.index + 1:
                                score += 100000
                        score += energy_count * 1000
                        score += hp * (1 + weights.preservation_bias)
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
                    score += 30000
                elif field_counts[Dragapult_ex] >= 2 or (field_counts[Dragapult_ex] == 1 and len(op_state.prize) <= 2):
                    score = -1
                else:
                    score += 70000
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


def make_agent(weights: PolicyWeights, adaptive: bool = False, always_first: bool = True):
    """Build one independent agent(obs_dict) -> list[int] callable backed by
    a fresh DragapultPolicy instance. Exposes `.policy` (the live instance,
    useful for tests/inspection -- e.g. `.policy.last_win_prob`) and `.DECK`.
    """
    policy = DragapultPolicy(weights, adaptive=adaptive)
    fn = policy.agent
    if always_first:
        fn = with_always_first(fn)
    fn.policy = policy  # type: ignore[attr-defined]
    fn.__name__ = f"dragapult_v16_{weights.name}"
    return fn
