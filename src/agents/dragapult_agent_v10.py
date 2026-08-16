"""V10 -- STRICT ABLATION STUDY: the V6/V7 engine (all three Phantom Dive
fixes, no V8/V9 Survival Retreat heuristic) piloting a modernized Dragapult ex
decklist. See src/agents/dragapult_policy_v10.py's module docstring for the
full design rationale and V10_IMPLEMENTATION_REPORT.md for the validation
writeup.

Thin binding: this file only selects the BALANCED weight profile (identical
to V2/V6/V7/V8 -- this is a controlled ablation, not a retune) and hands it
to V10's own engine (src/agents/dragapult_policy_v10.py), not V7's
src/agents/dragapult_policy_v7.py (untouched, still the prior experiment
baseline) and not V8's src/agents/dragapult_policy_v8.py (untouched --
V10 does not import or execute any V8/V9 code path).
"""

from src.agents.dragapult_policy_v10 import DECK, make_agent
from src.agents.policy_weights import BALANCED

agent = make_agent(BALANCED, adaptive=False, always_first=True)
