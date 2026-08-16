"""V15 -- "Holy Grail Baseline": V6's fixed Phantom Dive attack engine +
V4's DEFENSIVE weight profile. See src/agents/dragapult_policy_v15.py's
module docstring for confirmation the engine fork carries zero logic changes
from V6, and src/agents/policy_weights.py for the DEFENSIVE profile's exact
values and justification.

Thin binding: this file only selects the DEFENSIVE weight profile and hands
it to V15's own forked engine (src/agents/dragapult_policy_v15.py, a strict
copy of V6's engine -- not the shared src/agents/dragapult_policy_v2plus.py
used by V2/V3/V4/V5).
"""

from src.agents.dragapult_policy_v15 import DECK, make_agent
from src.agents.policy_weights import DEFENSIVE

agent = make_agent(DEFENSIVE, adaptive=False, always_first=True)
