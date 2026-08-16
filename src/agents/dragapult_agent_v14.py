"""V14 -- DYNAMIC GAME-PHASE POLICY. See src/agents/dragapult_policy_v14.py's
module docstring for exactly what changed relative to V6, and
V14_IMPLEMENTATION_REPORT.md for the phase thresholds and weight multipliers.

Thin binding: this file only selects the BALANCED weight profile (identical
base tuning to V6 -- V14 does not retune V6's own profile, it modulates it
dynamically by game phase) and hands it to V14's own forked engine
(src/agents/dragapult_policy_v14.py), not V6's own policy module.
"""

from src.agents.dragapult_policy_v14 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, always_first=True)
