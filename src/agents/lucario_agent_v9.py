"""V9 -- STRATEGIC PIVOT: Mega Lucario ex archetype + the generalized V6/V7/
V8 decision engine (weights, defensive retreat, the now 1-Prize-expanded
Survival Retreat heuristic). See src/agents/lucario_policy_v9.py's module
docstring for the full design rationale and V9_IMPLEMENTATION_REPORT.md for
the validation writeup.

Thin binding: this file only selects the BALANCED weight profile (same
choice V6/V7/V8 made for the Dragapult ex engine -- this is a controlled
experiment isolating the deck+heuristic change, not a fresh retune) and
hands it to V9's own engine (src/agents/lucario_policy_v9.py). Does not
touch dragapult_agent_v8.py or any Dragapult ex file.
"""

from src.agents.lucario_policy_v9 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
