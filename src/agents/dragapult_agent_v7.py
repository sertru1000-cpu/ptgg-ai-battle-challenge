"""V7 -- V6 + the residual Phantom Dive Bench-target planner fix (FIX #3).
See src/agents/dragapult_policy_v7.py's module docstring for exactly what
changed relative to V6, and PHANTOM_DIVE_ARCHITECTURE_AUDIT.md for the
forensic basis.

Thin binding: this file only selects the BALANCED weight profile (identical
to V2/V6 -- this is a controlled A/B experiment, not a retune) and hands it
to V7's own forked engine (src/agents/dragapult_policy_v7.py), not V6's
src/agents/dragapult_policy_v6.py (untouched, still the live submission).
"""

from src.agents.dragapult_policy_v7 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
