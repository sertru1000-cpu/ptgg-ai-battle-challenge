"""V11 -- MACRO-ACTION SEARCH (end-of-turn lookahead) forked from V6.

Fork lineage (Objective 1 of the governing task): this file is a strict copy
of src/agents/dragapult_policy_v6.py (V2/BALANCED engine + the two confirmed
Phantom Dive bug fixes, see that file's own docstring for the FIX #1/#2
detail -- unchanged here) with exactly one addition: a macro-action rollout
at the MAIN decision routing (Objective 2), described below. V11 plays the
EXACT SAME decklist as V6 (decks/dragapult_ex.csv) -- this task is a policy
experiment, not a deck change, and explicitly must not reuse V10's deck/setup
logic. V8/V9's survival/defensive-retreat heuristics are also explicitly not
part of this fork (V6's own `defensive_retreat_*` BALANCED-profile behavior
is retained unchanged, same as V6 -- nothing new was added on top of it).

WHY MACRO-ACTION SEARCH (not 1-step lookahead): the prior research prototype
(experiments/v6_one_step_lookahead.py, see
ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md) found that evaluating the board
immediately after a single candidate action is dominated by an "action
chaining" artifact -- V6 routinely plays several MAIN actions in one turn
(play a card, evolve, attach, THEN attack), so comparing "attack now" against
"play a card now" at the SAME decision point conflates two actions that both
lead to the same real turn a step apart (verified in that report's Part
7/9/11: 14/116 N=5 disagreements were mechanically confirmed EQUIVALENT --
the real game's different, non-attack-first sequence also won). V11 fixes
this by evaluating every top candidate ONLY at the END of the whole turn: it
applies the candidate action, then greedily auto-plays the rest of the turn
(using the engine's real `search_begin`/`search_step` sandbox, exactly as
already proven safe in that same experiment) until the turn actually ends,
and scores the resulting board -- so "attack now" and "play now, attack
later" are compared at a point where both have actually finished the turn,
not at an artificial mid-turn snapshot.

Objective 2 mechanism, in order:
  1. Score every legal MAIN option with V6's own unmodified greedy scorer
     (the existing `scores` list built by `agent()`, unchanged).
  2. Take the top `MACRO_LOOKAHEAD_TOP_N` (5) candidates by that raw score.
  3. For each: `search_begin`/`search_step` the candidate's own action, then
     -- if the turn has not ended (still our `yourIndex`, game not over) --
     keep stepping with a DISPOSABLE `copy.deepcopy` of this policy (see
     `_rollout_mode` below) making its own plain-greedy V6 choice at every
     follow-up decision, until the turn genuinely ends (attack, pass/END, or
     game over). This reuses `search_lookahead_v2._begin_shared_search` /
     `_resolve_full_chain` unchanged (the same helpers the one-step
     prototype used) rather than reimplementing the chain-stepping loop.
  4. Evaluate the resulting end-of-turn board with `post_action_state_value`
     (Our total `pokemon_score` − Opponent total `pokemon_score` + prize-diff
     term) -- ported unchanged from the same experiment's own
     `post_action_state_value`, the one function in V6's scoring surface that
     is safe to call regardless of whose turn it has become (see that
     function's docstring for why every other V6 scoring routine is NOT
     safe here).
  5. `final_candidate_score = v6_raw_score + post_action_state_value`; the
     candidate with the highest final score is executed.

`_rollout_mode`: the disposable deep-copied policy used to drive steps 3's
"rest of the turn" MUST make plain-greedy V6 decisions, not recurse into its
own macro-action search (that would branch combinatorially and blow the
per-decision timeout for no benefit -- the task asks for one flat macro
rollout per candidate, not nested search). `copy.deepcopy(self)` copies this
flag too, so it is force-set to `True` on the shadow instance right after
copying, independent of whatever the live instance's own flag is.

Safety (Objective 3): `search_end()` always runs in a `finally` block (no
leaked search sandboxes even on exception/timeout/early-break). RNG is not
independent across the 5 branches evaluated from one shared `search_begin`
root (crushing hammer coin-flips / deck-shuffle trainers touch the one
shared engine RNG stream) -- this is a known, accepted limitation for V11,
identical to the one already documented and accepted in
ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md Part 5, not re-litigated here. A
`MACRO_LOOKAHEAD_TIMEOUT_S` (0.2s) wall-clock budget covers the whole
candidate loop; exceeding it stops evaluating further candidates and either
uses the best one found so far, or -- if none finished yet -- falls back to
V6's own pure greedy choice (`select_top` over the unmodified `scores`), so
a slow/degenerate position can never take longer than one plain-greedy
decision would have. Every other decision context (deck-declare, damage
counter placement, switch-target selection, hand/trainer sub-selects, etc.)
is completely unmodified from V6 and never invokes the search sandbox.
"""

from __future__ import annotations

import copy
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from src.agents.common import get_card, select_top
from src.agents.policy_weights import BALANCED, PolicyWeights, blend_by_opponent_aggression
from src.agents.search_lookahead_v2 import SearchV2Stats, _begin_shared_search, _resolve_full_chain
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
    search_end,
    to_observation_class,
)

_DECK_PATH = Path(__file__).resolve().parents[2] / "decks" / "dragapult_ex.csv"
DECK: list[int] = [int(x) for x in _DECK_PATH.read_text().split("\n")[:60]]

_all_card = all_card_data()
_card_table = {c.cardId: c for c in _all_card}
_attack_table = {a.attackId: a for a in all_attack()}

# Decklist (named constants from the official notebook, identical to V1)
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

# Objective 2/3 tuning constants (V11 macro-action search).
MACRO_LOOKAHEAD_TOP_N = 5
MACRO_LOOKAHEAD_TIMEOUT_S = 0.2
MACRO_LOOKAHEAD_MAX_CHAIN_STEPS = 30


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

    Identical to V1 except the prize-count term is scaled by
    `weights.prize_value_multiplier` (identity 1.0 at NEUTRAL/V1) -- see
    policy_weights.py's module docstring for why this specific term.
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


def _board_value(state_player, weights: PolicyWeights) -> float:
    """Sums `pokemon_score()` (above, unmodified from V6) over one side's
    Active + Bench. Ported unchanged from
    experiments/v6_one_step_lookahead.py's own `_board_value` -- see that
    module's docstring for why `pokemon_score` specifically (not any other
    V6 scoring routine) is the one safe building block to call on a
    hypothetical post-action board regardless of whose turn it has become:
    it is a pure function of a single Pokemon (HP/energy/tools/stage/id) and
    `weights`, never of `select`/`context`/`state.yourIndex`.
    """
    total = 0.0
    if state_player.active:
        p = state_player.active[0]
        if p is not None:
            total += pokemon_score(p, False, weights)
    for p in state_player.bench:
        if p is not None:
            total += pokemon_score(p, False, weights)
    return total


def post_action_state_value(obs: Observation, my_index: int, weights: PolicyWeights) -> float:
    """End-of-turn board evaluation, ported unchanged (same formula, same
    constants) from experiments/v6_one_step_lookahead.py's own
    `post_action_state_value`:

        (Our total pokemon_score) - (Opponent total pokemon_score)
        + (opp.prize_remaining - my.prize_remaining) * 1000 * weights.prize_value_multiplier

    plus a terminal-state override (+-1,000,000 / 0) for a resolved
    win/loss/draw, reused from the same lineage's `search_lookahead_v2._evaluate`.
    Safe to call on ANY post-action Observation regardless of which player's
    turn it has become, since it only reads per-side board contents and the
    prize counts -- never `select`/`context`/`state.yourIndex`-dependent
    scoring.
    """
    state = obs.current
    if state.result is not None and state.result >= 0:
        if state.result == my_index:
            return 1_000_000.0
        if state.result == 1 - my_index:
            return -1_000_000.0
        return 0.0
    me = state.players[my_index]
    opp = state.players[1 - my_index]
    prize_term = (len(opp.prize) - len(me.prize)) * 1000.0 * weights.prize_value_multiplier
    return _board_value(me, weights) - _board_value(opp, weights) + prize_term


def with_always_first(agent_fn: Callable[[dict], list[int]]) -> Callable[[dict], list[int]]:
    """Same single-decision override as src/agents/dragapult_agent_always_first.py
    (validated: results/dragapult_first_second_analysis.md), reusable across
    every weight profile: always elects to go first, delegates every other
    decision unchanged to `agent_fn`.
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
    """One independent, stateful policy instance. Construct one per agent
    identity (V2/V3/V4/V5 each get their own); never share an instance's
    `agent` method across two simultaneous seats.
    """

    def __init__(self, weights: PolicyWeights, adaptive: bool = False):
        self.weights = weights
        self.adaptive = adaptive

        # Cross-call state (mirrors V1's module-level globals exactly, now
        # scoped per-instance instead of per-module).
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

        # V5-only in-battle opponent model. Harmless (never read/written) for
        # non-adaptive instances.
        self.opp_turns_observed = 0
        self.opp_attacks = 0
        self.opp_retreats = 0
        self.opp_low_hp_press = 0
        self.opp_low_hp_retreat = 0
        self._watch_serial: int | None = None

        # V11-only macro-action search state. `_rollout_mode` is False on
        # the one "live" instance actually deciding real games; forced True
        # on every disposable deepcopy used to greedily drive a candidate's
        # rest-of-turn rollout (see module docstring: this must NOT recurse
        # into another macro search). `macro_decision_latencies_ms` and
        # `macro_stats` are diagnostics only -- never read by the decision
        # logic itself, safe to leave on a shadow copy unused.
        self._rollout_mode = False
        self.macro_decision_latencies_ms: list[float] = []
        self.macro_fallback_count = 0
        self.macro_used_count = 0
        self.macro_stats = SearchV2Stats()

    # -- cross-call bookkeeping (identical logic to V1's module functions) --

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

    # -- V4/V5 hook: defensive retreat to deny a likely-lethal/heavy hit --

    def _wants_defensive_retreat(self, my_active: Pokemon | None, op_active: Pokemon | None) -> bool:
        if not self.weights.defensive_retreat_enabled:
            return False
        if self.can_attack:
            return False  # never give up a legal attack this turn to retreat defensively
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

    # -- V5 hook: lightweight, explicit, uncertainty-aware opponent model --

    def _observe_opponent(self, obs: Observation, my_index: int, op_state) -> None:
        op_index = 1 - my_index
        for log in obs.logs:
            if log.playerIndex == op_index:
                if log.type == LogType.ATTACK:
                    self.opp_attacks += 1
                elif log.type == LogType.SWITCH:
                    self.opp_retreats += 1
                elif log.type == LogType.TURN_END:
                    self.opp_turns_observed += 1

        op_active = op_state.active[0] if op_state.active else None
        if self._watch_serial is not None:
            still_active = op_active is not None and op_active.serial == self._watch_serial
            on_bench = any(p.serial == self._watch_serial for p in op_state.bench)
            in_discard = any(c.serial == self._watch_serial for c in op_state.discard)
            if in_discard:
                self._watch_serial = None  # knocked out mid-observation: inconclusive, drop
            elif on_bench:
                self.opp_low_hp_retreat += 1
                self._watch_serial = None
            elif still_active:
                self.opp_low_hp_press += 1
                self._watch_serial = None
            # else: not yet resolved (e.g. currently in a `looking` zone), keep watching

        if op_active is not None and self._watch_serial is None and op_active.maxHp > 0 and op_active.hp <= 0.3 * op_active.maxHp:
            self._watch_serial = op_active.serial

    def _compute_adaptive_weights(self) -> PolicyWeights:
        min_observations = 3
        if self.opp_turns_observed < min_observations:
            return BALANCED  # not enough evidence yet -- do not assume a pattern after one observation
        aggression = self.opp_attacks / max(1, self.opp_turns_observed)
        w = blend_by_opponent_aggression(aggression, f"agg={aggression:.2f},n={self.opp_turns_observed}")
        total_low_hp_obs = self.opp_low_hp_retreat + self.opp_low_hp_press
        if total_low_hp_obs >= 2 and (self.opp_low_hp_retreat / total_low_hp_obs) >= 0.66:
            # Opponent reliably protects wounded Pokemon by retreating them:
            # lean a little more risk-averse on our own switch-ins too.
            w = replace(w, switch_risk_tolerance=w.switch_risk_tolerance * 0.85)
        return w

    # -- V11 hook: macro-action search (end-of-turn lookahead) --

    def _macro_lookahead_choice(self, obs: Observation, select, scores: list) -> Optional[list[int]]:
        """Objective 2: rank MAIN options by V6's own raw `scores`, roll the
        top `MACRO_LOOKAHEAD_TOP_N` candidates each out to the end of the
        turn via the engine's real search sandbox, and return the index of
        whichever reaches the best end-of-turn board value plus its own raw
        score. Returns None (caller falls back to plain `select_top`) if the
        rollout could not run at all (search_begin failure, timeout before
        even one candidate finished) -- this is always a safe, legal
        fallback since `select_top(select, context, scores)` is exactly
        V6's own unmodified choice over the same options.
        """
        if self._rollout_mode:
            return None  # never recurse into another macro search

        t_start = time.perf_counter()
        my_index = obs.current.yourIndex
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        top_indices = ranked[: min(MACRO_LOOKAHEAD_TOP_N, len(ranked))]

        try:
            root = _begin_shared_search(obs, DECK, DECK)
        except Exception:
            self.macro_fallback_count += 1
            return None

        best_index = None
        best_total = float("-inf")
        try:
            for idx in top_indices:
                if time.perf_counter() - t_start >= MACRO_LOOKAHEAD_TIMEOUT_S:
                    break
                shadow_policy = copy.deepcopy(self)
                shadow_policy._rollout_mode = True
                try:
                    final_obs = _resolve_full_chain(
                        root.searchId, [idx], my_index, shadow_policy.agent,
                        MACRO_LOOKAHEAD_MAX_CHAIN_STEPS, self.macro_stats,
                    )
                    total = scores[idx] + post_action_state_value(final_obs, my_index, self.weights)
                except Exception:
                    continue
                if total > best_total:
                    best_total = total
                    best_index = idx
        finally:
            try:
                search_end()
            except Exception:
                pass

        self.macro_decision_latencies_ms.append((time.perf_counter() - t_start) * 1000.0)
        if best_index is None:
            self.macro_fallback_count += 1
            return None
        self.macro_used_count += 1
        return [best_index]

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

        if self.adaptive:
            self._observe_opponent(obs, my_index, op_state)
            self.weights = self._compute_adaptive_weights()
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
                                        # V6 FIX #1: a target at exactly 10
                                        # HP dies to a single damage counter
                                        # -- the cheapest possible kill on
                                        # offer. Was `score -= 100000`
                                        # (backwards, see
                                        # PHANTOM_DIVE_ARCHITECTURE_AUDIT.md
                                        # §3.2). +40000 keeps this in the
                                        # same additive-bonus unit scale as
                                        # the two buckets above while making
                                        # it strictly dominate both (30000
                                        # and 10000), since no other bucket
                                        # represents a guaranteed kill.
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

        if context == SelectContext.MAIN and select.maxCount == 1 and len(select.option) >= 2:
            macro_choice = self._macro_lookahead_choice(obs, select, scores)
            if macro_choice is not None:
                return macro_choice

        return select_top(select, context, scores)


def make_agent(weights: PolicyWeights, adaptive: bool = False, always_first: bool = True):
    """Build one independent agent(obs_dict) -> list[int] callable backed by
    a fresh DragapultPolicy instance. Exposes `.policy` (the live instance,
    useful for tests/inspection) and `.DECK`.
    """
    policy = DragapultPolicy(weights, adaptive=adaptive)
    fn = policy.agent
    if always_first:
        fn = with_always_first(fn)
    fn.policy = policy  # type: ignore[attr-defined]
    fn.__name__ = f"dragapult_{weights.name}"
    return fn
