"""V17 -- C++ MCTS Edition. Thin binding: re-exports DECK/agent from
src/agents/dragapult_agent_v17_cpp/agent.py (analogous role to every other
dragapult_agent_vN.py's `from ...policy_vN import DECK, make_agent`), except
V17's "policy" is a package (native C++ MCTS + a pure-Python V6 fallback)
rather than a single make_agent() call -- see that package's README.md for
the full architecture.
"""

from src.agents.dragapult_agent_v17_cpp.agent import DECK, agent

__all__ = ["DECK", "agent"]
