"""Submission-ready V18 candidate: same safety composition as every other
final_candidate_agent_vN.py (safety_wrapper -> timeout_shield -> policy),
applied to V18's policy (V17's native C++ MCTS plus Block A1: opponent-
archetype-conditioned hidden-zone determinization with discard accounting --
see src/agents/dragapult_agent_v18_cpp/opponent_model.py). See main_v18.py
for the Kaggle entry point (not submitted automatically -- wait for explicit
user approval). The four defense layers are identical to
final_candidate_agent_v17.py's; see that module's docstring.
"""

from src.agents.dragapult_agent_v18 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v18_arch_det")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v18_arch_det")
