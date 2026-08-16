"""Submission-ready V17 candidate: same safety composition as every other
final_candidate_agent_vN.py (safety_wrapper -> timeout_shield -> policy),
applied to V17's native-C++-MCTS-with-pure-Python-V6-fallback policy. See
main_v17.py for the Kaggle entry point that uses this module (not submitted
automatically -- DO NOT SUBMIT TO KAGGLE per the governing task, wait for
explicit user approval).

Defense in depth, deliberately layered for a native-code agent specifically:
(1) the C++ MCTS's own internal per-decision time budget, which itself
reserves a safety buffer before ever spending it on simulation (cpp/mcts.hpp,
McTsConfig::safety_buffer_ms); (2) src/agents/dragapult_agent_v17_cpp's own
whole-call try/except, falling back to the pure-Python V6 agent on ANY native
error (library missing, init failure, per-decision exception) -- the same
role dragapult_policy_v11.py's `_macro_lookahead_choice` returning None
plays, just guarding a strictly higher-risk failure mode (a native
library, not just a Python search timeout); (3) this module's timeout_shield
(2.0s/decision, 600s/match, identical composition/budgets to every other
version); (4) safety_wrapper's legal-action validation as the final,
scoring-independent backstop. No layer assumes any other layer is sufficient
on its own.
"""

from src.agents.dragapult_agent_v17 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v17_cpp_mcts")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v17_cpp_mcts")
