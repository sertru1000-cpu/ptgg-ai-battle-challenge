"""Submission-ready V6 candidate: same safety composition as V1's
src/agents/final_candidate_agent.py (safety_wrapper -> timeout_shield ->
policy), applied to the V6/BALANCED+Phantom-Dive-fixes policy. See
main_v6.py for the Kaggle entry point that uses this module (not submitted
automatically).
"""

from src.agents.dragapult_agent_v6 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v6_balanced_phantom_dive_fix")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v6_balanced_phantom_dive_fix")
