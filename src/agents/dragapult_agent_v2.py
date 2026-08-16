"""V2 -- BALANCED. See src/agents/policy_weights.py for the exact weight
values and their justification, and reports/agent_v2_v5_experiments.md
Section 2 for the full hypothesis/evidence writeup.

Thin binding: this file only selects the BALANCED weight profile and hands
it to the shared engine (src/agents/dragapult_policy_v2plus.py). It does not
duplicate any scoring logic -- V1's src/agents/dragapult_agent.py is never
imported or modified here.
"""

from src.agents.dragapult_policy_v2plus import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
