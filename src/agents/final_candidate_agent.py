"""Final Phase 4.7 submission candidate.

Deck/policy selection (Layer A, results/agent/final_agent_policy.csv,
tools/build_agent_layer_a_deck_selection_v1.py): Dragapult ex, tie-broken
over the statistically-indistinguishable Mega Lucario ex point estimate by
real-ladder sample size/precision. Team Rocket's Mewtwo ex -- the deck with
the single OOS_CONFIRMED validated counter (results/meta/
final_validated_counters.csv) -- was NOT selected: it has no competitive
gameplay policy (only a generic policy exists, tested dramatically weaker:
3/25 vs a sparring opponent the Dragapult agent beats 64% of the time, 2/20
in a direct head-to-head). Per Phase 4.7 Section 36 ("prefer robust over
complex/under-tested"), this is the existing, thoroughly-tested hand-tuned
agent, not a new one -- see reports/final_agent_v1.md for the full writeup.

Going First/Second (Section 6-7): USED. `dragapult_agent_always_first`
('dragapult_fix_v1') is an already-validated single-decision override
(results/dragapult_first_second_analysis.md, experiments/
dragapult_first_variant.md, both from an earlier session) that always elects
to go first instead of the official notebook's unconditional "always
second" -- a controlled 1000-games/condition local experiment found this
significantly better vs. Abomasnow (67.1% vs 56.3%, z=-4.97) and never
significantly worse against any tested opponent. This phase's own
Going-First/Second re-analysis against the real ladder dataset
(results/agent/going_first_second_analysis.csv) found a corroborating
pooled first-player advantage. Every other decision is delegated unchanged
to the real, unmodified src.agents.dragapult_agent -- this is a one-line
behavioral override, not a rewrite.

Safety layers (Section 19-22), composed outermost to innermost:
  safety_wrapper (legal-action net, never returns an illegal selection)
    -> timeout_shield (hard per-match wall-clock budget, Section 20)
      -> dragapult_agent_always_first.agent (Layer B policy)
"""

from src.agents.dragapult_agent_always_first import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_always_first")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_always_first")
