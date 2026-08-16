"""V11 -- V6/BALANCED + Phantom Dive bug fixes + macro-action search
(end-of-turn lookahead). See src/agents/dragapult_policy_v11.py's module
docstring for exactly what was added relative to V6.

Thin binding: this file only selects the BALANCED weight profile (identical
to V6 -- this is a search/architecture experiment, not a retune) and hands
it to V11's own forked engine (src/agents/dragapult_policy_v11.py).
"""

from src.agents.dragapult_policy_v11 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
