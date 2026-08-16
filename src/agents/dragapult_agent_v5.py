"""V5 -- ADAPTIVE. See src/agents/dragapult_policy_v2plus.py's
DragapultPolicy._observe_opponent / _compute_adaptive_weights for the actual
in-battle opponent-model mechanism, and reports/agent_v2_v5_experiments.md
Section 5 for the full hypothesis/evidence writeup.

Thin binding: this file only enables `adaptive=True` on the shared engine
(src/agents/dragapult_policy_v2plus.py) -- the weight profile is recomputed
every decision from the live in-battle opponent read (starting from
BALANCED until >=3 opponent turns have been observed, per the "avoid
assuming a pattern is certain after one observation" requirement), not fixed
at construction time like V2/V3/V4.
"""

from src.agents.dragapult_policy_v2plus import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=True, always_first=True)
