"""V6 -- BALANCED + the two confirmed Phantom Dive bug fixes. See
src/agents/dragapult_policy_v6.py's module docstring for exactly what
changed relative to V2, and PHANTOM_DIVE_ARCHITECTURE_AUDIT.md /
PHANTOM_DIVE_INDEX_ALIGNMENT_AUDIT.md for the forensic basis.

Thin binding: this file only selects the BALANCED weight profile (identical
to V2 -- this is a controlled A/B experiment, not a retune) and hands it to
V6's own forked engine (src/agents/dragapult_policy_v6.py), not the shared
src/agents/dragapult_policy_v2plus.py used by V2/V3/V4/V5.
"""

from src.agents.dragapult_policy_v6 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
