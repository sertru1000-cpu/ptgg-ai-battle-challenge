"""V21 -- Leader Imitation (BC) on the leader decklist. Thin binding to
src/agents/dragapult_policy_v21.py (BC ranker over single-pick options,
V19 policy as fallback/lethal-guard). Pure Python, no native code.
"""

from src.agents.dragapult_policy_v21 import DECK, make_agent

agent = make_agent(always_first=True)

__all__ = ["DECK", "agent"]
