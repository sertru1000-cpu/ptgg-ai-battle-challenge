"""V8 -- V7 + exactly ONE new strategic addition: a context-aware 2-Prize
Defensive Retreat / Survival heuristic. See src/agents/dragapult_policy_v8.py's
module docstring for exactly what changed relative to V7, and
V8_RETREAT_HEURISTIC_AUDIT.md for the full design/validation writeup.

Thin binding: this file only selects the BALANCED weight profile (identical
to V2/V6/V7 -- this is a controlled A/B experiment, not a retune) and hands it
to V8's own forked engine (src/agents/dragapult_policy_v8.py), not V7's
src/agents/dragapult_policy_v7.py (untouched, still the prior experiment
baseline).
"""

from src.agents.dragapult_policy_v8 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
