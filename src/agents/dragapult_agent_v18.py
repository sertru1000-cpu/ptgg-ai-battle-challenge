"""V18 -- C++ MCTS + opponent-archetype determinization (Block A1). Thin
binding: re-exports DECK/agent from src/agents/dragapult_agent_v18_cpp/agent.py
(same shape as dragapult_agent_v17.py's binding to its package -- see that
package's README.md and opponent_model.py for what changed vs V17).
"""

from src.agents.dragapult_agent_v18_cpp.agent import DECK, agent

__all__ = ["DECK", "agent"]
