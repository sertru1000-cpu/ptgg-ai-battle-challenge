"""Research prototype: does 1-step engine-backed lookahead improve V6's
decisions vs. its existing greedy policy?

Answers exactly one question (see ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md
for the full write-up): "Can one-step engine-backed lookahead improve the
decisions of our proven V6 greedy agent without requiring a new heuristic?"

ISOLATION / SAFETY CONTRACT
----------------------------
- This module is NEVER imported by main.py, main_v6.py, main_v10.py, or any
  of their transitive imports (grep-verified before writing this file --
  see ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 5 for the exact "do not touch"
  file list: main.py + final_candidate_agent.py + dragapult_agent_always_first.py
  + dragapult_agent.py + safety_wrapper.py + timeout_shield.py).
- It does not edit, subclass, or monkeypatch anything for longer than a
  single function call (see `capture_v6_scores` docstring for the one
  runtime attribute swap this module performs, and why it is safe).
- It never calls `battle_select` on the real match. All engine interaction
  goes through `search_begin`/`search_step`/`search_end` against the
  private search sandbox (`apiDataType == 2`), exactly as already proven
  safe and non-destructive in `ENGINE_CLONE_LOOKAHEAD_AUDIT.md` and already
  used in production-adjacent research code by `search_lookahead_v2.py`.
- Nothing here submits to Kaggle, modifies `decks/dragapult_ex.csv`,
  modifies `src/agents/policy_weights.py`, or introduces MCTS/minimax/
  multi-turn search/a value model. It is a flat 1-ply evaluate-and-pick,
  reusing V6's OWN existing scoring building blocks for the post-action
  state value (see `post_action_state_value` docstring) -- no new
  evaluation function is invented.

ARCHITECTURE (mirrors ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 9's "smallest
viable future simulation architecture", reusing `search_lookahead_v2.py`'s
already-audited chain-resolution/determinization helpers rather than
reimplementing them):

    capture V6's real per-candidate scores (score capture, below)
        |
        v
    rank candidates by V6's own score; take top N
        |
        v
    ONE search_begin()  (shared root clone, ~0.3ms measured in the audit)
        |
        v
    for each of the N candidates:
        search_step(root, candidate)             (candidate's own action)
        + _resolve_full_chain(...)                (same-player follow-up
                                                     selects, e.g. Phantom
                                                     Dive's damage-counter
                                                     placements -- REUSED
                                                     unchanged from
                                                     search_lookahead_v2.py)
        -> post_action_state_value(resulting obs)  (V6-native board value)
        lookahead_score = v6_current_action_score + post_action_state_value
        |
        v
    search_end()
        |
        v
    argmax(lookahead_score) across the N candidates  ==  V6_LOOKAHEAD's pick
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Optional

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import (  # noqa: E402
    AreaType,
    Observation,
    OptionType,
    SelectContext,
    search_end,
    to_observation_class,
)

import src.agents.dragapult_policy_v6 as v6policy  # noqa: E402
from src.agents.common import get_card  # noqa: E402
from src.agents.dragapult_policy_v6 import DragapultPolicy, pokemon_score  # noqa: E402
from src.agents.policy_weights import PolicyWeights  # noqa: E402

# Reused, unmodified, from the already-audited Search V2 infrastructure
# (results/search_v2_audit.md) -- see this module's docstring for why we
# import rather than reimplement.
from src.agents.search_lookahead_v2 import (  # noqa: E402
    SearchV2Stats,
    _begin_shared_search,
    _resolve_full_chain,
)

# ---------------------------------------------------------------------------
# Part 5 (research prompt): RNG safety classification.
#
# Sourced from GROUND TRUTH, not memory: `data/official/EN Card Data.csv`'s
# "Effect Explanation" column (trainer cards) and `cg.api.all_attack()`'s
# `.text`/`.damage` fields (Pokemon attacks), both queried directly against
# the real engine/card database for every one of the 21 unique card IDs in
# `decks/dragapult_ex.csv` -- see
# ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md Part 5 for the full per-card
# table this was derived from.
#
# Findings:
#   - None of this deck's 9 distinct attacks (Petty Grudge, Bite, Dragon
#     Headbutt, Jet Headbutt, Phantom Dive, Cruel Arrow, Eon Blade, Itchy
#     Pollen, Tuck Tail) has coin-flip or other random-outcome text --
#     ATTACK options are always DETERMINISTIC in this deck.
#   - Crushing Hammer (1120) is the ONLY card whose own immediate effect is
#     a coin flip ("Flip a coin. If heads, discard an Energy from 1 of your
#     opponent's Pokemon.") -- RNG_DEPENDENT (direct/outcome-random).
#   - Buddy-Buddy Poffin (1086), Ultra Ball (1121), Poke Pad (1152),
#     Crispin (1198), and Brock's Scouting (1210) all end their effect text
#     with "...shuffle your deck." The SEARCH portion of each (which card to
#     find) is a deterministic agent choice, but the shuffle itself consumes
#     the shared native `Game::rng` (ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 5)
#     -- flagged RNG_DEPENDENT for a DIFFERENT reason than Crushing Hammer:
#     not because THIS decision's outcome is uncertain, but because
#     evaluating it perturbs the one shared RNG stream that every other
#     candidate branched from the same root will also read from if their own
#     resolution touches RNG-consuming code, and because it makes the
#     resulting deck order (and therefore any future draw within the SAME
#     resolved chain) statistically contaminated relative to a true
#     independent branch. See the report for how this is handled (not
#     silently ignored).
RNG_DIRECT_CARD_IDS = {1120}  # Crushing Hammer
RNG_SHUFFLE_CARD_IDS = {1086, 1121, 1152, 1198, 1210}  # Buddy-Buddy Poffin, Ultra Ball, Poke Pad, Crispin, Brock's Scouting


def classify_option_rng(option, obs: Observation) -> str:
    """Returns "DETERMINISTIC" / "RNG_DEPENDENT" / "UNKNOWN" for a single
    candidate `select.option` entry, per Part 5 of the governing research
    prompt. Never silently treats an unclassified option type as safe --
    anything not explicitly reasoned about above returns UNKNOWN.
    """
    try:
        # `to_observation_class` does not coerce raw JSON ints into their
        # IntEnum types (confirmed empirically here, matching
        # tools/tournament.py's own comment about `log.type`/`log.reason`
        # being raw ints for the same reason) -- `==` against an IntEnum
        # member still works either way, but anything needing `.name` below
        # must go through an explicit `OptionType(...)` coercion first.
        if option.type == OptionType.ATTACK:
            return "DETERMINISTIC"
        if option.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, option.index, obs.current.yourIndex)
            if card is None:
                return "UNKNOWN"
            if card.id in RNG_DIRECT_CARD_IDS or card.id in RNG_SHUFFLE_CARD_IDS:
                return "RNG_DEPENDENT"
            return "DETERMINISTIC"
        if option.type in (OptionType.RETREAT, OptionType.ATTACH, OptionType.EVOLVE, OptionType.ABILITY):
            # Retreat/attach/evolve/ability-activation have no coin-flip or
            # other stochastic component anywhere in this deck's card data
            # (verified the same way as attacks, above).
            return "DETERMINISTIC"
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# V6 score capture (Part 1/2 of the research prompt: "receive the same
# candidate action set... compute the normal V6 score for every candidate").
# ---------------------------------------------------------------------------


def capture_v6_scores(policy: DragapultPolicy, obs_dict: dict):
    """Runs V6's REAL, unmodified `DragapultPolicy.agent()` on `obs_dict`
    and additionally recovers the full per-option score list it computes
    internally but does not normally return (only the argmax survives past
    `select_top`).

    Mechanism: `dragapult_policy_v6.py` imports `select_top` once into its
    own module namespace (`from src.agents.common import get_card,
    select_top`, dragapult_policy_v6.py:52) and `DragapultPolicy.agent()`
    always ends by calling that name
    (dragapult_policy_v6.py:921 `return select_top(select, context, scores)`).
    This function temporarily replaces THAT one module-level attribute
    (`v6policy.select_top`, i.e. `dragapult_policy_v6.select_top` -- NOT
    `src.agents.common.select_top` itself, which is never touched) with a
    thin recording wrapper that calls straight through to the real,
    unmodified `select_top`, then restores the original attribute in a
    `finally` block before this function returns. No file is edited, no
    scoring logic is duplicated or reimplemented (the real `select_top` and
    the real per-option `score` computation both still run exactly as
    written), and the swap window is exactly one Python call -- if this
    function raises before `agent()` returns, the `finally` still restores
    the original before the exception propagates.

    Not thread-safe (global attribute swap on a module object) -- fine for
    this synchronous, single-process prototype; documented rather than
    hidden. Never reachable from `main.py`'s chain: that chain never imports
    `dragapult_policy_v6` at all (it imports `dragapult_agent.py`, a
    separate, never-touched V1 module -- see ENGINE_CLONE_LOOKAHEAD_AUDIT.md
    Part 5).
    """
    captured: dict = {}
    original = v6policy.select_top

    def _capturing_select_top(select, context, scores):
        captured["select"] = select
        captured["context"] = context
        captured["scores"] = list(scores)
        return original(select, context, scores)

    v6policy.select_top = _capturing_select_top
    try:
        chosen = policy.agent(obs_dict)
    finally:
        v6policy.select_top = original
    return captured.get("select"), captured.get("context"), captured.get("scores"), chosen


# ---------------------------------------------------------------------------
# Part 3 of the research prompt: post-action state evaluation, built ONLY
# from V6's own existing scoring building blocks -- see docstrings below for
# exactly which V6 code is reused and what the one new piece of glue code is.
# ---------------------------------------------------------------------------


def _board_value(state_player, weights: PolicyWeights) -> float:
    """Sums V6's own, completely unmodified `pokemon_score()`
    (dragapult_policy_v6.py:140-162) over one side's Active + Bench.

    Why this specific V6 function is the one safe building block: every
    OTHER scoring routine in V6 (`main_option_proc`, the inline `scores[]`
    loop in `agent()`, `hand_score`, `attach_score`) is a function of
    (obs, select, context) -- "given these legal options, which is best" --
    and calling any of them against a hypothetical post-action Observation
    would silently evaluate the WRONG player's legal options once the
    simulated action ends our turn (exactly the turn-boundary hazard Part 3
    of the research prompt warns about: `main_option_proc`/`agent()` read
    `state.yourIndex` and `select.option`, both of which describe the
    OPPONENT once control has passed to them -- there is no "evaluate this
    board from my perspective, regardless of whose turn it is" entry point
    anywhere in `dragapult_policy_v6.py`). `pokemon_score(pokemon,
    is_attack_damage, weights)` is the one exception: it is a pure function
    of a single `Pokemon` object (its HP, energy count, tool count,
    evolution stage, card id) plus the policy's own `weights` -- it never
    reads `select`, `context`, or `state.yourIndex`, so it is safe to call
    on EITHER side's board, in EITHER player's post-action position,
    without risk of silently scoring the wrong player's options.
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
    """The `post_action_state_value` term the research prompt's Part 3
    structure (`current_action_score + post_action_state_value`) asks for.

    Composition -- every numeric building block is lifted unchanged from
    code that already exists in this repo; the ONLY new code is the
    additive combination itself:

    1. `_board_value(me) - _board_value(opp)`: V6's own `pokemon_score()`
       (see `_board_value` docstring), summed per side. This is safe across
       the turn boundary (does not depend on whose decision comes next).
    2. `(len(opp.prize) - len(me.prize)) * 1000.0 * weights.prize_value_multiplier`:
       NOT a new heuristic -- this is V6's own existing prize-differential
       variable, `prize_diff = len(my_state.prize) - len(op_state.prize)`
       (dragapult_policy_v6.py:487, already computed and consumed by V6's
       own `hand_score` every real decision), applied at the whole-game
       level with V6's own sign convention flipped to "positive = good for
       me" (my_state.prize DEcreasing as I take prizes is good for me, so
       `opp.prize - me.prize` is the "ahead" direction) and scaled by
       exactly the same `* 1000 * weights.prize_value_multiplier` factor
       `pokemon_score()` already uses internally for its own
       `prize_count(...)` term (dragapult_policy_v6.py:148) -- i.e. the
       scale is not invented, it is copied from the one place V6 already
       assigns a numeric weight to "one prize card is worth how many
       points."
    3. Terminal states (`state.result` resolved): scored +-1,000,000 / 0,
       reused verbatim from `search_lookahead_v2._evaluate` (the ONLY prior
       lookahead code in this repo, already audited) for the same reason it
       used this convention: a resolved win/loss must dominate any
       heuristic board value, and this is not a new invention specific to
       this prototype.

    This is deliberately NOT a claim that V6 "has" a state evaluator --
    Part 3 of the research prompt is explicit that if V6 cannot safely
    evaluate a simulated state, the correct response is to report the
    limitation rather than invent a new heuristic. What this function does
    is the narrowest thing that clears that bar: it introduces zero new
    SCORING VALUES (every number/weight is copied from code that already
    assigns it), and the one genuinely new piece of logic is the decision to
    SUM `pokemon_score` across a whole board and ADD it to the existing
    per-decision action score, which is reported plainly in
    ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md as a designed judgment call,
    not as "V6's own function."
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


# ---------------------------------------------------------------------------
# Part 2/4 of the research prompt: the actual lookahead decision.
# ---------------------------------------------------------------------------


@dataclass
class CandidateResult:
    index: int
    option_type: str
    attack_id: Optional[int]
    card_id: Optional[int]
    area: Optional[str]
    in_play_area: Optional[str]
    v6_score: float
    rng_class: str
    lookahead_score: Optional[float]
    chain_steps: Optional[int]
    error: Optional[str]


@dataclass
class LookaheadDecision:
    context: str
    n_options: int
    top_n_requested: int
    top_n_evaluated: int
    v6_choice: list
    lookahead_choice: Optional[list]
    disagreement: bool
    candidates: list  # list[CandidateResult]
    root_clone_latency_s: Optional[float]
    total_latency_s: float
    fallback_reason: Optional[str]


IN_SCOPE_CONTEXT = SelectContext.MAIN


def _safe_enum_name(enum_cls, value) -> Optional[str]:
    """`to_observation_class` leaves several scalar fields (option.type,
    option.area, select.context, ...) as raw ints rather than coerced
    IntEnum instances (confirmed empirically -- see `classify_option_rng`'s
    comment). This coerces defensively for logging only; never used for a
    decision-affecting comparison (those all use plain `==`, which works on
    raw ints against IntEnum members either way)."""
    if value is None:
        return None
    try:
        return enum_cls(value).name
    except Exception:
        return str(value)


def evaluate_decision_with_lookahead(
    policy: DragapultPolicy,
    obs_dict: dict,
    my_deck: list,
    opponent_deck_hint: list,
    top_n: int = 5,
    max_chain_steps: int = 20,
) -> Optional[LookaheadDecision]:
    """Shadow-evaluates ONE real decision against the SAME live engine
    state `obs_dict` describes.

    Returns the real V6 choice unchanged (`.v6_choice` -- callers should
    ALWAYS feed this, not `.lookahead_choice`, back into the real game when
    running in shadow/non-interfering mode; see the runner script) alongside
    what V6+1-step-lookahead would have picked, for logging/comparison.

    Scope (deliberately narrow, matching search_lookahead_v2.py's own Part
    A5 scoping rationale, generalized from "2+ ATTACK options" to "any
    single-slot MAIN decision with 2+ options" -- MAIN is where V6's own
    heterogeneous action scoring lives, per
    ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md Part 1: attack, retreat,
    evolve, attach, and trainer-play candidates are all scored into ONE
    `scores` list and compared against each other at this exact decision
    point): returns None (out of scope, caller should just use
    `policy.agent(obs_dict)` / the real choice) for anything that is not a
    `MAIN`-context, `maxCount == 1`, 2+-option decision.

    Isolation from the REAL policy instance's cross-call state: each
    candidate's same-player chain resolution is driven by a fresh
    `copy.deepcopy(policy)` ("shadow policy"), never the live `policy`
    instance itself. This is deliberately different from
    `search_lookahead_v2.make_search_v2_agent`, which reuses the SAME
    `base_agent_fn`/policy instance for chain-driving -- see
    ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md Part 2/9 for why that is a
    real (if partially self-healing) state-contamination risk this
    prototype avoids: `DragapultPolicy` holds no ctypes/native handles (only
    plain Python ints/lists/dicts/sets), so `copy.deepcopy` on it is valid
    and cheap -- this is NOT the same "deepcopy is invalid" case
    ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 3 found for the ctypes `c_void_p`
    engine handle; that finding was about the ENGINE boundary, not about
    this policy object, which never touches ctypes at all.
    """
    t_total_start = time.perf_counter()
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return None

    select, context, scores, v6_choice = capture_v6_scores(policy, obs_dict)
    if select is None or context != IN_SCOPE_CONTEXT or select.maxCount != 1 or len(select.option) < 2:
        return None

    my_index = obs.current.yourIndex
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    top_indices = ranked[: min(top_n, len(ranked))]

    root = None
    root_latency = None
    try:
        t0 = time.perf_counter()
        root = _begin_shared_search(obs, my_deck, opponent_deck_hint)
        root_latency = time.perf_counter() - t0
    except Exception as e:
        return LookaheadDecision(
            context=SelectContext(context).name,
            n_options=len(select.option),
            top_n_requested=top_n,
            top_n_evaluated=0,
            v6_choice=v6_choice,
            lookahead_choice=None,
            disagreement=False,
            candidates=[],
            root_clone_latency_s=None,
            total_latency_s=time.perf_counter() - t_total_start,
            fallback_reason=f"search_begin failed: {type(e).__name__}: {e}",
        )

    stats = SearchV2Stats()
    candidates: list[CandidateResult] = []
    best_index = None
    best_total = float("-inf")
    try:
        for idx in top_indices:
            option = select.option[idx]
            rng_class = classify_option_rng(option, obs)
            shadow_policy = copy.deepcopy(policy)
            try:
                final_obs = _resolve_full_chain(root.searchId, [idx], my_index, shadow_policy.agent, max_chain_steps, stats)
                chain_steps = stats.chain_lengths[-1]
                post_value = post_action_state_value(final_obs, my_index, policy.weights)
                total = scores[idx] + post_value
                candidates.append(CandidateResult(
                    idx, OptionType(option.type).name, option.attackId, option.cardId,
                    _safe_enum_name(AreaType, option.area), _safe_enum_name(AreaType, option.inPlayArea),
                    scores[idx], rng_class, total, chain_steps, None,
                ))
                if total > best_total:
                    best_total = total
                    best_index = idx
            except Exception as e:
                candidates.append(CandidateResult(
                    idx, OptionType(option.type).name, option.attackId, option.cardId,
                    _safe_enum_name(AreaType, option.area), _safe_enum_name(AreaType, option.inPlayArea),
                    scores[idx], rng_class, None, None, f"{type(e).__name__}: {e}",
                ))
    finally:
        try:
            search_end()
        except Exception:
            pass

    lookahead_choice = [best_index] if best_index is not None else None
    disagreement = lookahead_choice is not None and lookahead_choice != v6_choice
    return LookaheadDecision(
        context=SelectContext(context).name,
        n_options=len(select.option),
        top_n_requested=top_n,
        top_n_evaluated=len(top_indices),
        v6_choice=v6_choice,
        lookahead_choice=lookahead_choice,
        disagreement=disagreement,
        candidates=candidates,
        root_clone_latency_s=root_latency,
        total_latency_s=time.perf_counter() - t_total_start,
        fallback_reason=None if best_index is not None else "no candidate simulation succeeded",
    )
