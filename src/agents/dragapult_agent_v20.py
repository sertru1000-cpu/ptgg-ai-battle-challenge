"""V20 -- Block B stack on V18's architecture: B1 learned P(win) evaluation
(XGBoost forest trained on 341K states from top-100 ladder games, embedded as
static C++ arrays), B2 PUCT selection with V6-greedy priors, B3
determinization voting. Same deck and Block-A determinization as V18. Thin
binding, same shape as dragapult_agent_v18.py.
"""

from src.agents.dragapult_agent_v20_cpp.agent import DECK, agent

__all__ = ["DECK", "agent"]
