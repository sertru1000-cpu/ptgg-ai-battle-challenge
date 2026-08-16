"""Submission-ready V5 candidate: same safety composition as V1's
src/agents/final_candidate_agent.py (safety_wrapper -> timeout_shield ->
policy), applied to the V5/ADAPTIVE policy. See main_v5.py for the Kaggle
entry point that uses this module (not submitted automatically).
"""

from src.agents.dragapult_agent_v5 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v5_adaptive")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v5_adaptive")
