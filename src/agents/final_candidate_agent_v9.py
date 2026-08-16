"""Submission-ready V9 candidate: same safety composition as V8's
src/agents/final_candidate_agent_v8.py (safety_wrapper -> timeout_shield ->
policy), applied to the V9/BALANCED Mega Lucario ex + expanded-Survival-
Retreat policy. See main_v9.py for the local entry point (not submitted to
Kaggle this phase -- see V9_IMPLEMENTATION_REPORT.md).
"""

from src.agents.lucario_agent_v9 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="lucario_v9_survival_retreat")
agent = wrap_agent(_timeout_shielded_agent, name="lucario_v9_survival_retreat")
