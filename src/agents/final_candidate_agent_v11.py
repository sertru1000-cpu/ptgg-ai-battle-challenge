"""Submission-ready V11 candidate: same safety composition as V1's
src/agents/final_candidate_agent.py (safety_wrapper -> timeout_shield ->
policy), applied to the V11/BALANCED+Phantom-Dive-fixes+macro-action-search
policy. See main_v11.py for the Kaggle entry point that uses this module
(not submitted automatically -- DO NOT SUBMIT TO KAGGLE per the governing
task, wait for explicit user approval).

Defense in depth: `timeout_shield`'s own per-decision 2.0s budget and
whole-match 600s budget sit OUTSIDE V11's own internal 0.2s macro-lookahead
timeout (src/agents/dragapult_policy_v11.py's `MACRO_LOOKAHEAD_TIMEOUT_S`) --
if the internal safeguard were ever somehow bypassed, this outer shield still
guarantees the match-level budget can never be exceeded.
"""

from src.agents.dragapult_agent_v11 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v11_macro_action_search")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v11_macro_action_search")
