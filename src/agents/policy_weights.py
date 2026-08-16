"""Named strategic weight profiles shared by src/agents/dragapult_policy_v2plus.py
(Prompt #5, Part 3-4: "shared battle engine + version-specific decision policy").

Every knob here is a bounded, additive/multiplicative adjustment to a scoring
term that ALREADY EXISTS in src/agents/dragapult_agent.py (BEST_DRAGAPULT_AGENT,
V1/BASELINE, never modified) -- none of these invent a new scoring axis from
scratch. Each knob's grounding:

- `prize_value_multiplier`: scales the `prize_count(...) * 1000` term inside
  V1's own `pokemon_score()`, which is already the single dominant term in that
  formula (next-largest terms are `energy*150`/`tools*100`/`stage2 250`) --
  scaling it changes how single-mindedly the existing bench-snipe subset-sum
  planner (`main_option_proc`) chases prize-heavy targets vs. weighing
  secondary board-development factors. Does NOT touch the hard win-securing
  branches (`score = 50000` when a plan guarantees game-ending prizes) --
  those stay absolute, exactly as in V1, at every multiplier value.
- `defensive_retreat_enabled` / `defensive_retreat_hp_fraction`: V1's own
  `do_switch` boolean already retreats for two reasons (promote a charged
  bench attacker; protect Budew's setup timing) -- this adds a THIRD,
  independently gated reason: retreat to deny the opponent a likely-lethal
  (or, at a lower fraction, a heavily-damaging) hit on an active Pokemon that
  cannot itself attack this turn. Threat detection uses real engine data
  (`cg.api.all_attack()` damage figures + attached-energy counts), not a
  guess. At `defensive_retreat_enabled=False` this hook is fully inert.
- `preservation_bias`: scales the `hp` addend (relative to the fixed
  `energy_count * 1000` addend) in V1's own SWITCH/TO_ACTIVE candidate
  scoring -- a bounded reweighting of an existing two-term formula, not new
  logic. Positive = prefer bulkier replacements; negative = prefer
  attack-ready replacements.
- `switch_risk_tolerance`: divides V1's own fixed penalties for switching in
  a low-attack support Pokemon (Fezandipiti ex -1000, Meowth ex -2000) --
  >1.0 shrinks the penalty (more willing to gamble on bringing a support
  piece in), <1.0 grows it (more reluctant).

Two hooks investigated and DELIBERATELY NOT included, per the "avoid
complexity for its own sake" instruction, because they were checked against
the real engine data (see the prior session's turn) and found to be no-ops
for this specific 60-card Dragapult ex deck:
  1. Multi-attack tie-break-by-value (score=o.attackId in the MAIN ATTACK
     branch): only Dragapult ex and Dreepy have >1 attack in this decklist,
     and both already resolve correctly by attack-ID ordering coincidence
     (higher ID = higher damage for both), confirmed via `cg.api.all_attack()`.
  2. Weakness/resistance-aware KO planning: Dragapult ex's type is DRAGON
     (EnergyType 9); a full scan of all 1056 Pokemon cards in the competition
     pool found ZERO cards with weakness or resistance to DRAGON. The
     existing flat `damage=200` assumption in `main_option_proc` is already
     exactly correct for every possible target.

NEUTRAL is not a strategic profile -- it exists only so
tools/verify_v2_engine_equivalence.py can mechanically prove the refactored
engine reproduces V1's exact decisions when every hook is at its identity
value, before any of the four real profiles below are trusted.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PolicyWeights:
    name: str
    prize_value_multiplier: float = 1.0
    defensive_retreat_enabled: bool = False
    defensive_retreat_hp_fraction: float = 1.0  # trigger threshold, as a fraction of my active's current HP
    preservation_bias: float = 0.0  # roughly [-0.3, +0.3]; shifts SWITCH-target HP weighting
    switch_risk_tolerance: float = 1.0  # > 0; higher = smaller penalty for a risky support-Pokemon switch-in


# Reproduces V1 (src/agents/dragapult_agent.py) exactly -- every hook at its
# identity value. Used only by the equivalence-verification tool, never
# shipped as a real submission candidate.
NEUTRAL = PolicyWeights(name="neutral_v1_equivalent")

# V2 -- BALANCED. Hypothesis: V1 can improve by adding one narrow, high-
# confidence safety net (deny a clean likely-lethal when we can't act anyway)
# without otherwise touching its already-well-tuned priority order (KO > type
# matchup > damage > preservation > positioning > risk-avoidance >
# justified switching, per the Part 3 spec) -- everything else stays at V1's
# own values. See reports/agent_v2_v5_experiments.md Section 2.
BALANCED = PolicyWeights(
    name="v2_balanced",
    prize_value_multiplier=1.0,
    defensive_retreat_enabled=True,
    defensive_retreat_hp_fraction=1.0,  # only a clean likely-lethal, never a partial hit
    preservation_bias=0.1,
    switch_risk_tolerance=1.0,
)

# V3 -- AGGRESSIVE. Hypothesis: V1 leaves value on the table by weighing
# board-development factors (evolution stage, tool count) comparably to raw
# prize value, and by never gambling a support-Pokemon switch-in when the
# numbers otherwise favor it. Never disables the underlying EV-based scoring
# (Part 3's "aggression must still be based on expected battle value") --
# only reweights it. Defensive retreat is OFF: V3 never gives up tempo to
# protect a Pokemon, matching "less conservative switching" / "greater
# willingness to accept damage for a significant advantage."
AGGRESSIVE = PolicyWeights(
    name="v3_aggressive",
    prize_value_multiplier=1.35,
    defensive_retreat_enabled=False,
    defensive_retreat_hp_fraction=1.0,
    preservation_bias=-0.15,
    switch_risk_tolerance=1.3,
)

# V4 -- DEFENSIVE. Hypothesis: V1 sometimes leaves a high-value, already-
# spent active Pokemon exposed to a free knockout when it could retreat, and
# is agnostic between a bulky vs. attack-ready replacement when forced to
# switch. Defensive retreat fires proactively (0.6x HP threshold, not only a
# guaranteed lethal) and switch-target selection leans harder toward bulk and
# away from risky support-Pokemon switch-ins.
DEFENSIVE = PolicyWeights(
    name="v4_defensive",
    prize_value_multiplier=0.75,
    defensive_retreat_enabled=True,
    defensive_retreat_hp_fraction=0.6,
    preservation_bias=0.3,
    switch_risk_tolerance=0.6,
)


def lerp(a: float, b: float, t: float) -> float:
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


def blend_by_opponent_aggression(aggression: float, name_suffix: str) -> PolicyWeights:
    """V5 -- ADAPTIVE's core mechanism: interpolate between AGGRESSIVE and
    DEFENSIVE (never past either endpoint) based on an in-battle read of how
    aggressively the opponent has played so far this match. `aggression` is
    expected in [0, 1] (0 = opponent has thrown zero attacks per observed
    turn so far, 1 = at or above one attack per observed turn). An opponent
    read as pressuring us heavily nudges OUR stance toward DEFENSIVE
    (preserve resources against a threat); a passive opponent nudges toward
    AGGRESSIVE (safe to press an advantage). See dragapult_policy_v2plus.py's
    DragapultPolicy._compute_adaptive_weights for the confidence gate that
    decides whether to call this at all vs. falling back to BALANCED.
    """
    return PolicyWeights(
        name=f"v5_adaptive({name_suffix})",
        prize_value_multiplier=lerp(AGGRESSIVE.prize_value_multiplier, DEFENSIVE.prize_value_multiplier, aggression),
        defensive_retreat_enabled=aggression > 0.35,
        defensive_retreat_hp_fraction=lerp(1.0, DEFENSIVE.defensive_retreat_hp_fraction, aggression),
        preservation_bias=lerp(AGGRESSIVE.preservation_bias, DEFENSIVE.preservation_bias, aggression),
        switch_risk_tolerance=lerp(AGGRESSIVE.switch_risk_tolerance, DEFENSIVE.switch_risk_tolerance, aggression),
    )


__all__ = [
    "PolicyWeights",
    "NEUTRAL",
    "BALANCED",
    "AGGRESSIVE",
    "DEFENSIVE",
    "lerp",
    "blend_by_opponent_aggression",
    "replace",
]
