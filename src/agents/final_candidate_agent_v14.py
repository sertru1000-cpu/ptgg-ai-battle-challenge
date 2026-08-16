"""Submission-ready V14 candidate: same safety composition as V6's
src/agents/final_candidate_agent_v6.py (safety_wrapper -> timeout_shield ->
policy), applied to the V14/BALANCED+dynamic-game-phase-weights policy. See
main_v14.py for the Kaggle entry point that uses this module (not submitted
automatically).
"""

from src.agents.dragapult_agent_v14 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v14_dynamic_phase")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v14_dynamic_phase")
