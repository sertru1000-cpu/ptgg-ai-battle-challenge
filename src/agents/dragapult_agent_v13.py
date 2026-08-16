"""V13 -- TURBO CONSISTENCY DECK, V6/BALANCED engine. See
src/agents/dragapult_policy_v13.py's module docstring for exactly what
changed relative to V6 (the deck, plus the one new Cheren scoring branch)
and V13_IMPLEMENTATION_REPORT.md for the full decklist diff and rationale.

Thin binding: this file only selects the BALANCED weight profile (identical
to V2/V6 -- this is a deck-selection experiment, not a weight retune) and
hands it to V13's own forked engine (src/agents/dragapult_policy_v13.py),
not V6's src/agents/dragapult_policy_v6.py (untouched) and not V10's
src/agents/dragapult_policy_v10.py (untouched, and never imported here).
"""

from src.agents.dragapult_policy_v13 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
