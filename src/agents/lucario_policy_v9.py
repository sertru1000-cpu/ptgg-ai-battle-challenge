"""V9 -- STRATEGIC PIVOT: combines the generalized V6/V7/V8 decision engine
(class-based per-instance state, PolicyWeights-aware scoring, the Defensive
Retreat hook, and the Survival Retreat hook -- now EXPANDED to cover 1-Prize
Actives, see OBJECTIVE 2 below) with the Mega Lucario ex archetype (baseline
attack-planning/scoring ported from src/agents/lucario_ex_agent.py, the
already-validated notebook-port sparring agent that plays the same role for
this file that src/agents/dragapult_agent.py/V1 played for
dragapult_policy_v2plus.py..v8.py).

Does NOT modify src/agents/dragapult_policy_v8.py, dragapult_agent_v8.py,
final_candidate_agent_v8.py, main_v8.py, decks/dragapult_ex.csv, or deck.csv
(the shared Kaggle-submission-root deck file V8 depends on) -- this is a new,
fully independent module/deck/entry-point chain. V8 remains the live
experiment baseline for the Dragapult ex archetype, untouched.

WHY "JUST SWAP THE DECK PATH" DOESN'T WORK (traced, not assumed, before
writing any new logic): dragapult_policy_v8.py's main_option_proc,
hand_score, and attach_score are hard-branched on Dragapult ex's own card
IDs (Dreepy/Drakloak/Dragapult_ex/Fezandipiti_ex/Budew/etc.) and on Phantom
Dive's unique bench-wide six-target damage-counter-placement mechanic (the
subset-sum combo search FIX #1/#2/#3 all exist to correct). Checked directly
against the official card CSV: every one of Mega Lucario ex's own attacks
(Aura Jab, Mega Brave, Wild Press, Power Gem, Cosmic Beam, Accelerating Stab,
Corkscrew Punch, Confront) is ordinary single-target attack damage -- none
places damage counters. Pointing V8's engine at decks/lucario_ex.csv
unchanged would score every Lucario-specific hand/field card at the silent
default (0 in most contexts), never plan a real attack, and never retreat
correctly for this deck's own Pokemon.

WHAT CARRIES OVER UNMODIFIED (ported byte-for-byte or field-for-field from
dragapult_policy_v8.py, since none of it is Dragapult-specific): the
class-based per-instance-state pattern (V8's own stated reason: V1-style
module globals corrupt themselves if two seats share one imported module
instance, exactly as relevant here as it was there); PolicyWeights
integration; `pokemon_score`/`prize_count` (already deck-agnostic);
`_wants_defensive_retreat` (V4/V5's hook, deck-agnostic); the V8 anti-thrash
bookkeeping (STEP 4 guardrail, deck-agnostic); the V5 adaptive-opponent-model
hooks; and the DAMAGE_COUNTER / DAMAGE_COUNTER_ANY scoring block INCLUDING V6
FIX #1 (hp == 10 is the single cheapest possible kill, not a penalty) --
kept present and untouched per this phase's explicit instruction not to
delete the Phantom Dive fixes. This decklist itself never reaches that
SelectContext (no card in decks/lucario_ex.csv places damage counters,
confirmed above) so the branch is verified-inert defensive code for this
deck's OWN attacks, but two of its neighbouring lethal-detection helpers
below (`_lethal_threat_confirmed`/`_have_winning_trade`) keep a REAL, still-
load-bearing piece of the Phantom Dive fix alive: they skip attackId 154
when reading the OPPONENT's own attack list, because a V9 agent can still be
matched against a real Dragapult ex opponent on the ladder, and that
opponent's Phantom Dive would trigger the exact same fictional-Active-damage
false-positive V6/V7/V8 already fixed if this exclusion were dropped. This is
the concrete, still-relevant reason "don't delete the Phantom Dive fixes"
matters here, not just an archival instruction.

WHAT'S NEWLY PORTED FROM src/agents/lucario_ex_agent.py (this deck's own
already-validated baseline): the single-target AttackPlan search
(`_plan_attack`, replacing main_option_proc's bench-wide combo search --
there is nothing to search across multiple bench targets for a deck with no
multi-target attack), `energy_score`, and the PLAY/CARD-context scoring for
this deck's own card pool (Makuhita/Hariyama/Lunatone/Solrock/Riolu/
Mega_Lucario_ex/Switch/Premium_Power_Pro/Fighting_Gong/Poke_Pad/Hero_Cape/
Boss_Orders/Lillie_Determination). The selection tail is deliberately
lucario_ex_agent.py's own bespoke "always fill to select.maxCount regardless
of score sign" tail, NOT src.agents.common.select_top() -- that helper's
TO_BENCH/SETUP_BENCH_POKEMON negative-score-skip quirk was tuned and
validated against Dragapult ex's deck shape, never against this one;
reusing it here would be an unvalidated, unrequested behavior change on top
of the validated Lucario baseline this file exists to preserve.

OBJECTIVE 1 (deck swap) is implemented entirely in decks/lucario_ex.csv (see
V9_IMPLEMENTATION_REPORT.md) plus exactly the touch points a trace of every
consumer of the three swapped card IDs turned up:
  - Dusk_Ball -> Ultra_Ball: ZERO scoring-logic diff needed. Confirmed via
    lucario_ex_agent.py's own docstring plus direct inspection of every
    branch below: Dusk_Ball/Fighting_Gong were named deck constants with no
    card-ID-specific scoring branch anywhere in the ported source -- both
    fall through to the flat default score. Ultra_Ball inherits the same
    default, unchanged.
  - Carmine -> Judge: renamed at its one PLAY-branch score (elif card.id ==
    Judge: score = 3000, same priority tier Carmine held) plus one real,
    load-bearing fix found while tracing consumers: Premium_Power_Pro's own
    PLAY score reads `hand_counts[Judge]` (was `hand_counts[Carmine]`) to
    decide a priority tier -- left unchanged this would have silently always
    evaluated to 0 once Carmine left the decklist, a genuine, not
    hypothetical, latent bug this port catches before it could ship.
  - Gravity_Mountain -> Wally's_Compassion: Wally's Compassion is a
    SUPPORTER (EN Card Data.csv: cardId 1229, cardType=Supporter), NOT a
    Stadium as this phase's own instructions casually called it -- verified
    against the official card data before writing any scoring for it, not
    assumed. It therefore cannot reuse Gravity_Mountain's old Stadium-slot
    PLAY branch (keyed off `stadium_id`, an axis Wally's Compassion has
    nothing to do with); it gets its own new branch keyed off whether we
    currently have a damaged Mega Lucario ex on the field -- see the
    CRITICAL GUARDRAILS synergy branch below.

OBJECTIVE 2 (Survival Retreat expanded to 1-Prize Actives):
`_wants_survival_retreat` below is forked from V8's and kept
behaviour-identical for ex/megaEx Actives -- with one deliberate, explicitly
flagged extension: V8's literal gate (`not my_card.ex or my_card.megaEx:
return False`) excluded BOTH ordinary 1-Prize Pokemon AND 3-Prize Mega
Pokemon. That second exclusion was never reachable for Dragapult ex's
all-2-Prize decklist, so V8 never tested or needed to care about it; V9's
own deck has a 3-Prize flagship (Mega Lucario ex itself) that this
experiment's whole point is to protect, so leaving it uniquely EXCLUDED from
the safety net while extending that same net to ordinary 1-Prize tech cards
would be a strange, unjustified asymmetry against the experiment's own
stated goal. V9 therefore treats "ex OR megaEx" as unconditionally eligible
(a strict superset of V8's rule, not a narrower or different one -- the
literal PRE-FLIGHT non-regression requirement) and adds a genuinely NEW
conditional branch for ordinary 1-Prize Actives, gated on the same
lethal-threat-confirmed (A) + ready-bench-replacement (B) checks as before,
plus a new condition C with three alternatives:
  C1. the Active's own retreat cost is 0 (a free-retreat pivot) --
      `_one_prize_retreat_makes_sense`. Note: no card in this specific 60
      -card decklist actually has retreatCost == 0 (checked directly against
      the official card CSV: Makuhita/Riolu retreat for 2, Hariyama for 3,
      Lunatone/Solrock for 1) -- this branch is real, general, reusable code
      kept for a future decklist that includes a 0-cost pivot, not a path
      this V9 build will ever actually take. Reported as such, not silently
      implied to be exercised.
  C2. the Active is a crucial pre-evolution for this deck's own attacker
      line (Riolu -> Mega Lucario ex, Makuhita -> Hariyama) AND it is not
      currently carrying any attached Energy we would lose by retreating it
      -- `_one_prize_retreat_makes_sense`. This IS the path this decklist
      actually exercises (see V9_IMPLEMENTATION_REPORT.md for a worked
      example).
  C3. we hold a Switch in hand -- a free, cost-free swap that bypasses the
      retreat-cost question entirely, reachable even when RETREAT itself
      isn't legally offered this decision (`self.can_switch` is False) --
      `_wants_survival_swap_item`, wired into Switch's own PLAY-context
      score rather than into `do_switch`/the RETREAT option, since playing
      an Item is a structurally different SelectContext/OptionType than
      retreating. NOTE: this phase's own instructions named "Switch or
      Wally's Compassion" as example switching Items -- checked against the
      official card text and Wally's Compassion does NOT switch anything (it
      heals + returns Energy to hand for an already-Active Mega Evolution
      ex); only Switch is wired into this path. Reported as a correction,
      not silently "fixed" without a note.
If the 1-Prize Active is a plain "meat shield" (none of C1/C2/C3 hold), the
hook returns False and V9 falls back to whatever V7/V8 would already have
done -- this is the literal, intended behavior for the "do NOT trigger"
closing paragraph of Objective 2, not a separate check.

CRITICAL GUARDRAILS: the Wally's Compassion PLAY branch fires (competes for
the one-Supporter-per-turn slot at the same priority tier as Judge/Lillie's
Determination/Boss's Orders) whenever we have a currently-damaged Mega
Lucario ex anywhere on our own field (Active or Bench), and stays inert
(score -1, a dead card) otherwise -- a direct, minimal answer to "don't let
the agent avoid playing it when Mega Lucario ex is heavily damaged." The V8
anti-thrash guardrail is reused completely unmodified (see module import and
`__init__` below). No MCTS/minimax/lookahead/new architecture is introduced
anywhere in this file.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Callable

from src.agents.common import get_card
from src.agents.policy_weights import BALANCED, PolicyWeights, blend_by_opponent_aggression
from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import (  # noqa: E402
    AreaType,
    CardType,
    EnergyType,
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

_DECK_PATH = Path(__file__).resolve().parents[2] / "decks" / "lucario_ex.csv"
DECK: list[int] = [int(x) for x in _DECK_PATH.read_text().split("\n")[:60]]

_all_card = all_card_data()
_card_table = {c.cardId: c for c in _all_card}
_attack_table = {a.attackId: a for a in all_attack()}

# Decklist (named constants -- ported from src/agents/lucario_ex_agent.py,
# with the OBJECTIVE 1 upgrade: Dusk_Ball -> Ultra_Ball, Carmine -> Judge,
# Gravity_Mountain -> Wally's_Compassion. Every other card ID is unchanged.)
Makuhita = 673
Hariyama = 674
Lunatone = 675
Solrock = 676
Riolu = 677
Mega_Lucario_ex = 678
Switch = 1123
Premium_Power_Pro = 1141
Fighting_Gong = 1142
Poke_Pad = 1152
Hero_Cape = 1159
Boss_Orders = 1182
Judge = 1213  # was Carmine (1192) in the local reference deck
Lillie_Determination = 1227
Wallys_Compassion = 1229  # was Gravity_Mountain (1252) in the local reference deck
Ultra_Ball = 1121  # was Dusk_Ball (1102) -- no scoring branch needed either way
Basic_Fighting_Energy = 6

# Objective 2.C2: crucial pre-evolutions for this deck's own attacker line.
_PRE_EVOLUTION_IDS = {Riolu, Makuhita}


def no_damage_counter(pokemon: Pokemon) -> bool:
    """Checks if a target prevents placement of damage counters (via
    abilities/Energy). Ported unchanged from dragapult_policy_v8.py -- kept
    only because it still guards the (verified-inert-for-this-deck)
    DAMAGE_COUNTER/DAMAGE_COUNTER_ANY branch below, per the instruction not
    to delete the Phantom Dive fixes.
    """
    if pokemon.id == 28 or pokemon.id == 199 or pokemon.id == 203 or pokemon.id == 207 or pokemon.id == 362 or pokemon.id == 1136:
        return True
    for card in pokemon.energyCards:
        if card.id == 11 or card.id == 20:
            return True
    return False


def prize_count(pokemon: Pokemon, is_attack_damage: bool) -> int:
    """Calculates how many Prize cards a Pokemon yields upon being Knocked Out.

    Identical to dragapult_policy_v8.py's version (already deck-agnostic).
    """
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
    """Heuristically evaluates the tactical worth of targeting a specific Pokemon.

    Identical to dragapult_policy_v8.py's version (already deck-agnostic,
    already weights-aware via `prize_value_multiplier`).
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
    """Identical to dragapult_policy_v8.py's version -- deck-agnostic."""

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


class AttackPlan:
    """Single-target attack plan (attacker index into [active]+bench, target
    index into [op_active]+op_bench, attack_index 0/1) -- ported from
    lucario_ex_agent.py's own AttackPlan, a fundamentally different shape
    than dragapult_policy_v8.py's counter-combo AttackPlan (which has no
    single 'target', only a bench-wide 'counter' placement list) because
    this deck's attacks are ordinary single-target damage, never a bench-
    wide combo. `counter` is kept as an always-empty field solely so the
    ported (and verified-inert) DAMAGE_COUNTER_ANY branch below has
    something safe to read instead of crashing if that SelectContext is ever
    somehow reached; `_plan_attack` never writes to it.
    """

    attacker: int = -1
    target: int = -1
    attack_index: int = -1
    remain_hp: int = -1
    energy: bool = False
    counter: list[int] = []


class LucarioPolicy:
    """One independent, stateful policy instance -- same rationale as
    dragapult_policy_v8.py's DragapultPolicy (never share one instance's
    `agent` method across two simultaneous seats).
    """

    def __init__(self, weights: PolicyWeights, adaptive: bool = False):
        self.weights = weights
        self.adaptive = adaptive

        self.can_switch = False
        self.can_attack = False
        self.pre_turn_log: list[Log] = []
        self.current_turn_log: list[Log] = []

        self.plan = AttackPlan()
        self.ability_used = False
        self.pre_turn = -1

        # V5-style in-battle opponent model (ported unchanged; harmless for
        # non-adaptive instances).
        self.opp_turns_observed = 0
        self.opp_attacks = 0
        self.opp_retreats = 0
        self.opp_low_hp_press = 0
        self.opp_low_hp_retreat = 0
        self._watch_serial: int | None = None

        # V8-style anti-thrash memory for `_wants_survival_retreat` (ported
        # unchanged -- deck-agnostic).
        self._prev_active_serial: int | None = None
        self._survival_retreat_pending = False
        self._survival_retreat_op_serial: int | None = None
        self._last_survival_retreat_serial: int | None = None
        self._last_survival_retreat_hp: int | None = None
        self._last_survival_retreat_op_serial: int | None = None
        self.survival_retreat_log: list[dict] = []  # local-only instrumentation

    # -- shared lethal-threat / winning-trade helpers ------------------
    # Extracted once so `_wants_survival_retreat` (RETREAT-context path) and
    # `_wants_survival_swap_item` (Switch-item path, OBJECTIVE 2.C3) can't
    # drift out of sync with each other.

    @staticmethod
    def _lethal_threat_confirmed(my_active: Pokemon, op_active: Pokemon, op_card) -> bool:
        op_energy_count = len(op_active.energies)
        for aid in op_card.attacks:
            if aid == 154:
                # Phantom Dive's card-data damage=200 is fictional for the
                # Active (Bench-only effect) -- still relevant here if we
                # ever face a real Dragapult ex opponent. See module
                # docstring.
                continue
            atk = _attack_table.get(aid)
            if atk is None or atk.damage <= 0:
                continue
            if op_energy_count >= len(atk.energies) and atk.damage >= my_active.hp:
                return True
        return False

    @staticmethod
    def _have_winning_trade(my_active: Pokemon, op_active: Pokemon, my_card) -> bool:
        my_energy_count = len(my_active.energies)
        for aid in my_card.attacks:
            if aid == 154:
                continue  # inert for this deck (no card here has this attack ID); kept for parity.
            atk = _attack_table.get(aid)
            if atk is None or atk.damage <= 0:
                continue
            if my_energy_count >= len(atk.energies) and atk.damage >= op_active.hp:
                return True
        return False

    @staticmethod
    def _bench_pokemon_is_ready(pokemon: Pokemon) -> bool:
        """Identical logic to dragapult_policy_v8.py's version -- deck-agnostic."""
        card = _card_table.get(pokemon.id)
        if card is None:
            return False
        energy_count = len(pokemon.energies)
        for aid in card.attacks:
            atk = _attack_table.get(aid)
            if atk is not None and atk.damage > 0 and energy_count >= len(atk.energies):
                return True
        return False

    # -- V4/V5 hook: defensive retreat to deny a likely-lethal/heavy hit --
    # Ported unchanged from dragapult_policy_v8.py (deck-agnostic). Note the
    # same known, NOT-fixed-here latent inaccuracy V8 itself flagged: this
    # hook (unlike `_lethal_threat_confirmed` above) does not exclude
    # attackId 154 -- left as-is per the surgical, smallest-change-necessary
    # scope, matching V8's own choice not to touch it either.

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

    # -- OBJECTIVE 2: Survival Retreat, expanded to 1-Prize Actives -------

    def _one_prize_retreat_makes_sense(self, my_active: Pokemon, my_card) -> bool:
        """C: for an ordinary 1-Prize Active, retreating must make strategic
        sense on its own terms (unlike a 2/3-Prize Active, where avoiding the
        prize loss alone already justifies it). True under either:
          C1. retreat cost is 0 (a free-retreat pivot); or
          C2. the Active is a crucial pre-evolution for this deck's own
              attacker line (Riolu/Makuhita) AND it is not currently
              carrying any Energy we'd lose by retreating it.
        C3 (a Switch in hand) is handled separately by
        `_wants_survival_swap_item`, since it bypasses this question
        entirely rather than answering it.
        """
        retreat_cost = my_card.retreatCost
        if retreat_cost <= 0:
            return True
        if my_active.id in _PRE_EVOLUTION_IDS:
            energy_lost = min(retreat_cost, len(my_active.energies))
            return energy_lost == 0
        return False  # a plain 1-Prize "meat shield" -- do not trigger

    def _wants_survival_retreat(
        self, my_active: Pokemon | None, op_active: Pokemon | None, my_bench: list[Pokemon]
    ) -> bool:
        if my_active is None or op_active is None:
            return False
        if not self.can_switch:
            return False

        my_card = _card_table.get(my_active.id)
        op_card = _card_table.get(op_active.id)
        if my_card is None or op_card is None:
            return False

        # A (OBJECTIVE 2): ex/megaEx Actives stay unconditionally eligible
        # (V8's own behaviour, now literally including our 3-Prize Mega
        # Lucario ex -- see module docstring for why this is a deliberate,
        # flagged extension, not a regression). An ordinary 1-Prize Active
        # only qualifies if C holds.
        if not (my_card.ex or my_card.megaEx):
            if not self._one_prize_retreat_makes_sense(my_active, my_card):
                return False

        # B/C (threat): the opponent's Active must have a realistically
        # available attack (energy already visibly attached) whose damage
        # meets or exceeds our Active's current HP.
        if not self._lethal_threat_confirmed(my_active, op_active, op_card):
            return False

        # Do not give up a winning trade.
        if self._have_winning_trade(my_active, op_active, my_card):
            return False

        # D/E: at least one genuinely playable Bench replacement must exist.
        ready_bench = [p for p in my_bench if self._bench_pokemon_is_ready(p)]
        if not ready_bench:
            return False

        retreat_cost = my_card.retreatCost
        energy_lost = min(retreat_cost, len(my_active.energies))

        if self._survival_retreat_pending:
            return True

        if (
            self._last_survival_retreat_serial is not None
            and my_active.serial == self._last_survival_retreat_serial
            and my_active.hp == self._last_survival_retreat_hp
            and op_active.serial == self._last_survival_retreat_op_serial
        ):
            return False

        self.survival_retreat_log.append(
            {
                "my_active_id": my_active.id,
                "my_active_serial": my_active.serial,
                "my_active_hp": my_active.hp,
                "prizes_at_stake": prize_count(my_active, True),
                "op_active_id": op_active.id,
                "op_active_energy_count": len(op_active.energies),
                "retreat_cost": retreat_cost,
                "energy_lost_estimate": energy_lost,
                "bench_replacement_ids": [p.id for p in ready_bench],
                "bench_replacement_can_attack": True,
                "one_prize_path": not (my_card.ex or my_card.megaEx),
            }
        )
        return True

    def _wants_survival_swap_item(
        self,
        my_active: Pokemon | None,
        op_active: Pokemon | None,
        my_bench: list[Pokemon],
        hand_counts: "defaultdict[int, int]",
    ) -> bool:
        """OBJECTIVE 2.C3: even when RETREAT itself isn't legally offered
        this decision (self.can_switch is False -- e.g. our Active can't
        afford its own retreat cost), holding a Switch in hand is a second,
        cost-free escape route (Switch has no attached-Energy cost at all).
        Reuses the same threat (A/B) checks as `_wants_survival_retreat`;
        the "does retreating make sense" question (C) is moot here because
        Switch bypasses the very cost that question is about. Only
        meaningful when self.can_switch is False -- if RETREAT is already
        legal, `_wants_survival_retreat` is the live code path for this
        situation, not this method.
        """
        if self.can_switch or hand_counts[Switch] <= 0:
            return False
        if my_active is None or op_active is None:
            return False
        my_card = _card_table.get(my_active.id)
        op_card = _card_table.get(op_active.id)
        if my_card is None or op_card is None:
            return False
        if not self._lethal_threat_confirmed(my_active, op_active, op_card):
            return False
        if self._have_winning_trade(my_active, op_active, my_card):
            return False
        return any(self._bench_pokemon_is_ready(p) for p in my_bench)

    # -- V5 hook: lightweight, explicit, uncertainty-aware opponent model --
    # Ported unchanged from dragapult_policy_v8.py (deck-agnostic).

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
                self._watch_serial = None
            elif on_bench:
                self.opp_low_hp_retreat += 1
                self._watch_serial = None
            elif still_active:
                self.opp_low_hp_press += 1
                self._watch_serial = None

        if op_active is not None and self._watch_serial is None and op_active.maxHp > 0 and op_active.hp <= 0.3 * op_active.maxHp:
            self._watch_serial = op_active.serial

    def _compute_adaptive_weights(self) -> PolicyWeights:
        min_observations = 3
        if self.opp_turns_observed < min_observations:
            return BALANCED
        aggression = self.opp_attacks / max(1, self.opp_turns_observed)
        w = blend_by_opponent_aggression(aggression, f"agg={aggression:.2f},n={self.opp_turns_observed}")
        total_low_hp_obs = self.opp_low_hp_retreat + self.opp_low_hp_press
        if total_low_hp_obs >= 2 and (self.opp_low_hp_retreat / total_low_hp_obs) >= 0.66:
            w = replace(w, switch_risk_tolerance=w.switch_risk_tolerance * 0.85)
        return w

    # -- attack planner (replaces main_option_proc: single-target search) --

    def _plan_attack(self, obs: Observation) -> tuple[bool, bool]:
        """Ported from lucario_ex_agent.py's own inline MAIN-block attack
        search, restructured as a method writing into self.plan (instead of
        the module-level `plan` global) and using the weights-aware
        pokemon_score/prize_count above. Returns (can_switch_for_plan,
        can_op_switch) -- two locals the original computed inline and used
        only within this same search; kept as a return value rather than
        instance state because nothing outside this method needs them
        (unlike self.can_switch, which V8's generic hooks below DO need, and
        which means something narrower: "RETREAT is legally offered right
        now" -- see the note in `agent()`).
        """
        state = obs.current
        select = obs.select
        my_index = state.yourIndex
        my_state = state.players[my_index]
        op_state = state.players[1 - my_index]
        my_prize = len(my_state.prize)
        weights = self.weights

        field_counts: dict[int, int] = defaultdict(int)
        for card in my_state.active + my_state.bench:
            if card is not None:
                field_counts[card.id] += 1

        discard_counts: dict[int, int] = defaultdict(int)
        for card in my_state.discard:
            discard_counts[card.id] += 1

        hand_counts: dict[int, int] = defaultdict(int)
        for card in my_state.hand:
            hand_counts[card.id] += 1

        can_switch_for_plan = False
        can_op_switch = False
        can_use_mega_brave = False
        self.can_attack = False
        for o in select.option:
            if o.type == OptionType.PLAY:
                card = get_card(obs, AreaType.HAND, o.index, my_index)
                if card.id == Switch:
                    can_switch_for_plan = True
                elif card.id == Boss_Orders:
                    can_op_switch = True
            elif o.type == OptionType.EVOLVE:
                card = get_card(obs, AreaType.HAND, o.index, my_index)
                if card.id == Hariyama:
                    can_op_switch = True
            elif o.type == OptionType.RETREAT:
                can_switch_for_plan = True
                self.can_switch = True
            elif o.type == OptionType.ATTACK:
                self.can_attack = True
                if o.attackId == 983:  # Mega Brave
                    can_use_mega_brave = True

        self.plan = AttackPlan()

        my_cards = [my_state.active[0]] + list(my_state.bench)
        op_cards = [op_state.active[0]] + list(op_state.bench)

        if state.turn < 2:
            return can_switch_for_plan, can_op_switch

        best_score = -1
        for i, my_pokemon in enumerate(my_cards):
            if i != 0 and not can_switch_for_plan:
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
                    score = pokemon_score(op_pokemon, True, weights)
                    if op_pokemon.hp <= damage:
                        prize = prize_count(op_pokemon, True)
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
                        self.plan.attacker = i
                        self.plan.target = j
                        self.plan.attack_index = a
                        self.plan.remain_hp = op_pokemon.hp - damage
                        self.plan.energy = more_energy

        return can_switch_for_plan, can_op_switch

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
            self.pre_turn_log.clear()
            self.current_turn_log.clear()
            self.pre_turn = 0
            self.ability_used = False
            # V8-style: a new game means the anti-thrash memory below refers
            # to a previous, unrelated battle.
            self._prev_active_serial = None
            self._survival_retreat_pending = False
            self._survival_retreat_op_serial = None
            self._last_survival_retreat_serial = None
            self._last_survival_retreat_hp = None
            self._last_survival_retreat_op_serial = None
        else:
            for log in obs.logs:
                self.current_turn_log.append(log)
                if log.type == LogType.TURN_END:
                    self.pre_turn_log = self.current_turn_log
                    self.current_turn_log = []

        if self.pre_turn != state.turn:
            self.pre_turn = state.turn
            self.plan = AttackPlan()
            self.ability_used = False

        if self.adaptive:
            self._observe_opponent(obs, my_index, op_state)
            self.weights = self._compute_adaptive_weights()
        weights = self.weights

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

        self.can_switch = False
        can_op_switch = False
        if context == SelectContext.MAIN:
            _, can_op_switch = self._plan_attack(obs)
        else:
            # Non-MAIN decisions still need self.can_switch/self.can_attack
            # current for the hooks below (e.g. a DAMAGE_COUNTER or CARD
            # select mid-turn); a lightweight legality scan is enough here,
            # the full attack search only matters at the MAIN decision.
            self.can_attack = False
            for o in select.option:
                if o.type == OptionType.RETREAT:
                    self.can_switch = True
                elif o.type == OptionType.ATTACK:
                    self.can_attack = True

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

        my_active = my_state.active[0] if my_state.active else None
        op_active = op_state.active[0] if op_state.active else None

        # V8-style anti-thrash bookkeeping (deck-agnostic, ported unchanged).
        current_active_serial = my_active.serial if my_active is not None else None
        if (
            self._survival_retreat_pending
            and current_active_serial is not None
            and current_active_serial != self._prev_active_serial
        ):
            self._last_survival_retreat_serial = current_active_serial
            self._last_survival_retreat_hp = my_active.hp
            self._last_survival_retreat_op_serial = self._survival_retreat_op_serial
            self._survival_retreat_pending = False
        self._prev_active_serial = current_active_serial

        do_switch = self.plan.attacker >= 1
        if not do_switch:
            do_switch = self._wants_defensive_retreat(my_active, op_active)
        if not do_switch and context == SelectContext.MAIN:
            do_switch = self._wants_survival_retreat(my_active, op_active, my_state.bench)
            if do_switch:
                self._survival_retreat_pending = True
                self._survival_retreat_op_serial = op_active.serial if op_active is not None else None

        wants_survival_swap = False
        if context == SelectContext.MAIN:
            wants_survival_swap = self._wants_survival_swap_item(my_active, op_active, my_state.bench, hand_counts)

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
                    hp = 0
                    if isinstance(card, Pokemon):
                        energy_count = len(card.energies)
                        hp = card.hp
                    if context == SelectContext.SWITCH or context == SelectContext.TO_ACTIVE:
                        if o.playerIndex == my_index:
                            score += energy_count * 2
                            if o.index == self.plan.attacker - 1:
                                score += 100
                            if card.id == Mega_Lucario_ex:
                                if len(my_state.prize) == 2 or len(my_state.prize) == 3:
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
                            if o.index == self.plan.target - 1:
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
                            score += 30 if (not self.ability_used or not state.energyAttached) else -1
                    elif context == SelectContext.ATTACH_FROM:
                        score = energy_score(card, o.area == AreaType.ACTIVE)
                    elif context == SelectContext.DAMAGE_COUNTER or context == SelectContext.DAMAGE_COUNTER_ANY:
                        # Verified-inert for this decklist (no Lucario attack
                        # places damage counters) -- kept, including V6 FIX
                        # #1 (hp==10), per the instruction not to delete the
                        # Phantom Dive fixes. See module docstring.
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
                                if index in self.plan.counter:
                                    score += 100000
                                else:
                                    remain_damage = select.remainDamageCounter * 10
                                    if 210 <= hp <= 200 + remain_damage:
                                        score += 30000
                                    elif 20 <= hp <= 60 + remain_damage:
                                        score += 10000
                                    elif hp == 10:
                                        # V6 FIX #1 (inherited): a target at
                                        # exactly 10 HP is the cheapest
                                        # possible kill, not a penalty.
                                        score += 40000
                            if no_damage_counter(card):
                                score = -1
            elif o.type == OptionType.PLAY:
                card = get_card(obs, AreaType.HAND, o.index, my_index)
                if card.id == Switch:
                    score = 6000 if (self.plan.attacker >= 1 or wants_survival_swap) else -1
                elif card.id == Premium_Power_Pro:
                    if state.supporterPlayed and self.plan.remain_hp <= 0:
                        score = -1
                    elif not self.can_attack:
                        if not state.supporterPlayed and hand_counts[Judge] > 0 and hand_counts[Lillie_Determination] == 0:
                            score = 3050
                        else:
                            score = -1
                    else:
                        score = 5000
                elif card.id == Boss_Orders:
                    score = 3200 if self.plan.target >= 1 else -1
                elif card.id == Judge:
                    score = 3000
                elif card.id == Lillie_Determination:
                    score = 3100
                elif card.id == Wallys_Compassion:
                    mega_field = [p for p in ([my_state.active[0]] if my_state.active else []) + list(my_state.bench) if p is not None]
                    mega_damaged = any(p.id == Mega_Lucario_ex and p.hp < p.maxHp for p in mega_field)
                    score = 3150 if mega_damaged else -1
                else:
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
                        if self.plan.attacker == 0 and self.plan.energy:
                            score += 200
                    else:
                        if self.plan.attacker == 1 + o.inPlayIndex and self.plan.energy:
                            score += 200
            elif o.type == OptionType.EVOLVE:
                pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
                score = 9000 + len(pokemon.energies)
                if pokemon.id == Makuhita and self.plan.target == 0:
                    score = -1
            elif o.type == OptionType.ABILITY:
                card = get_card(obs, o.area, o.index, my_index)
                if card.id == 1267:  # Lumiose City
                    score = 1
                else:
                    score = 30000
            elif o.type == OptionType.RETREAT:
                score = 2000 if do_switch else -1
            elif o.type == OptionType.ATTACK:
                score = 1000
                if self.plan.attack_index == 1:
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
                    self.ability_used = True
        return desc_indices[: select.maxCount]


def make_agent(weights: PolicyWeights, adaptive: bool = False, always_first: bool = True):
    """Build one independent agent(obs_dict) -> list[int] callable backed by
    a fresh LucarioPolicy instance. Same shape as
    dragapult_policy_v8.py's make_agent().
    """
    policy = LucarioPolicy(weights, adaptive=adaptive)
    fn = policy.agent
    if always_first:
        fn = with_always_first(fn)
    fn.policy = policy  # type: ignore[attr-defined]
    fn.__name__ = f"lucario_{weights.name}"
    return fn
