"""V4 -- DEFENSIVE. See src/agents/policy_weights.py for the exact weight
values and their justification, and reports/agent_v2_v5_experiments.md
Section 4 for the full hypothesis/evidence writeup.

Thin binding: this file only selects the DEFENSIVE weight profile and hands
it to the shared engine (src/agents/dragapult_policy_v2plus.py).
"""

from src.agents.dragapult_policy_v2plus import DECK, make_agent
from src.agents.policy_weights import DEFENSIVE

agent = make_agent(DEFENSIVE, adaptive=False, always_first=True)
