"""Submission-ready V10 candidate: same safety composition as V1's
src/agents/final_candidate_agent.py (safety_wrapper -> timeout_shield ->
policy), applied to the V10/BALANCED V6-baseline-ablation + modernized-
Dragapult-deck policy. See main_v10.py for the local entry point (NOT
submitted to Kaggle this phase -- see V10_IMPLEMENTATION_REPORT.md).
"""

from src.agents.dragapult_agent_v10 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v10_survival_retreat_ablation")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v10_survival_retreat_ablation")
