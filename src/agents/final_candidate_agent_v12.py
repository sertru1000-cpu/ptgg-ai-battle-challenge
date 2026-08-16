"""Submission-ready V12 candidate: same safety composition as V6's
src/agents/final_candidate_agent_v6.py (safety_wrapper -> timeout_shield ->
policy), applied to the V12/BALANCED+Phantom-Dive-fixes+matchup-aware policy.
See main_v12.py for the Kaggle entry point that uses this module (not
submitted automatically).
"""

from src.agents.dragapult_agent_v12 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v12_matchup_aware")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v12_matchup_aware")
