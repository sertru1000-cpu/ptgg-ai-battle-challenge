from src.agents.dragapult_agent_v27 import DECK, agent as _base_agent
from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout

_timeout_shielded_agent = wrap_timeout(_base_agent, name="dragapult_v27")
agent = wrap_agent(_timeout_shielded_agent, name="dragapult_v27")
