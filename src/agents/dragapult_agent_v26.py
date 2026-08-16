"""v26 -- Self-Play Eval Edition: V20's full stack (archetype
determinization, generic opponent rollouts, PUCT, det voting) with the B1v2
P(win) evaluator -- retrained on 212K own-engine self-play games plus the
341K leader-demonstration states (combined valid AUC 0.900 vs B1v1's 0.833;
on-policy self-play slice 0.910). Thin binding, same shape as
dragapult_agent_v20.py.
"""

from src.agents.dragapult_agent_v26_cpp.agent import DECK, agent

__all__ = ["DECK", "agent"]
