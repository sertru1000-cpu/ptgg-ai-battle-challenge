"""V16 -- XGBoost-informed BALANCED profile. See
src/agents/dragapult_policy_v16.py's module docstring for exactly what
changed relative to V6 and how the trained win-probability model is wired in.

Thin binding: this file only selects the BALANCED weight profile (V16's
starting point before its per-decision XGBoost-driven reweighting kicks in)
and hands it to V16's own forked engine (src/agents/dragapult_policy_v16.py),
not V6's own policy module.
"""

from src.agents.dragapult_policy_v16 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
