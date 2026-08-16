"""Submission-ready V22 candidate: same safety composition as every other
final_candidate_agent_vN.py (safety_wrapper -> timeout_shield -> policy),
applied to V22's B4-lite policy. Not submitted automatically.
"""

from src.agents.dragapult_agent_v22 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v22_b4lite")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v22_b4lite")
