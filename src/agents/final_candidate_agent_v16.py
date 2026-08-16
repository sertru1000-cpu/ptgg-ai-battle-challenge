"""Submission-ready V16 candidate: same safety composition as V6's
src/agents/final_candidate_agent_v6.py (safety_wrapper -> timeout_shield ->
policy), applied to the V16/BALANCED+XGBoost-win-probability policy. See
main_v16.py for the Kaggle entry point that uses this module (not submitted
automatically). The timeout_shield's PER_DECISION_BUDGET_SECONDS=2.0s hard
cutoff is the outer safety net for the XGBoost inference call in particular:
if model loading/inference ever misbehaves beyond
src/agents/dragapult_policy_v16.py's own try/except, this wrapper still
guarantees a legal move within budget.
"""

from src.agents.dragapult_agent_v16 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v16_xgb")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v16_xgb")
