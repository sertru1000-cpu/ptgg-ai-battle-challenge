"""V12 -- MATCHUP-AWARE POLICY: V6/BALANCED + the two confirmed Phantom Dive
bug fixes + per-decision opponent archetype detection (SNIPER / AGRO_TANK /
UNKNOWN) with dynamic weight shifting. See
src/agents/dragapult_policy_v12.py's module docstring for exactly what
changed relative to V6, and V12_IMPLEMENTATION_REPORT.md for the specific
weight adjustments per archetype.

Thin binding: this file only selects the BALANCED weight profile (V12's
fixed base, identical to V6 -- the archetype layer adjusts *around* this, it
does not retune it) and hands it to V12's own forked engine
(src/agents/dragapult_policy_v12.py), not V6's, V10's, or any other
version's engine/deck.
"""

from src.agents.dragapult_policy_v12 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, always_first=True)
