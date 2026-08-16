"""V19 -- the leader Dragapult decklist (rank-#2 "flg"'s exact 60, shared
identically by 11+ top-100 teams) on V6's engine with heuristic support for
the new cards. See src/agents/dragapult_policy_v19.py's module docstring for
the exact deck and policy delta, and results/leader_diff/deck_diff.md for the
evidence behind the list.

Thin binding: BALANCED weights, V19's own forked engine. Pure Python, no
native MCTS -- the ladder showed V17's search adds ~nothing over the plain
heuristic (679.9 vs 683.7), so the deck+policy change ships without doubling
into the C++ port.
"""

from src.agents.dragapult_policy_v19 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
