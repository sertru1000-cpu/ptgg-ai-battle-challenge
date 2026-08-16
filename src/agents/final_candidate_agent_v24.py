"""Submission-ready v24 candidate: same safety composition as every other
final_candidate_agent_vN.py (safety_wrapper -> timeout_shield -> policy),
applied to v24's self-play-eval policy. See main_v24.py for the Kaggle entry
point (not submitted automatically -- wait for explicit user approval).
"""

from src.agents.dragapult_agent_v24 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v24_selfplay_eval")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v24_selfplay_eval")
