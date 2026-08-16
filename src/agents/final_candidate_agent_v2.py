"""Submission-ready V2 candidate: same safety composition as V1's
src/agents/final_candidate_agent.py (safety_wrapper -> timeout_shield ->
policy), applied to the V2/BALANCED policy instead of V1's unmodified
dragapult_agent_always_first. See main_v2.py for the Kaggle entry point that
uses this module (not submitted automatically).
"""

from src.agents.dragapult_agent_v2 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v2_balanced")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v2_balanced")
