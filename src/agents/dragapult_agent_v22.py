"""V22 -- V20's Block-B stack + B4-lite (soft-minimax rollout widening: the
first two decision points of every rollout branch the actor's top-2 options,
each branch scored by the B1 eval, continuing from the best-for-the-actor
branch -- adversarial depth exactly at the reply to the root candidate).
Thin binding, same shape as dragapult_agent_v20.py.
"""

from src.agents.dragapult_agent_v22_cpp.agent import DECK, agent

__all__ = ["DECK", "agent"]
