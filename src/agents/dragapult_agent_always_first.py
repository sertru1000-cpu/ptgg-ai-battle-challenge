"""Experimental variant of src/agents/dragapult_agent.py (BEST_DRAGAPULT_AGENT):
a single-decision override that always elects to go FIRST, instead of the
official notebook's unconditional "always go second".

Motivation (see results/dragapult_first_second_analysis.md, Phase 4): a
controlled 1000-games/condition experiment found going first is a
statistically significant, sizeable improvement for Dragapult ex
specifically vs. Abomasnow ex (67.1% vs 56.3%, z=-4.97) and directionally
positive (not yet significant at this sample size) vs. Iono's and random.

This is NOT a rewrite of dragapult_agent.py -- every decision except the
IS_FIRST yes/no is delegated unchanged to the real, unmodified
src.agents.dragapult_agent.agent(). BEST_DRAGAPULT_AGENT
(src/agents/dragapult_agent.py) is never overwritten or modified by this
file; this module exists purely as an experimental candidate to be
benchmarked against it (experiments/dragapult_first_variant.md), and is
only promoted if the comparison justifies it.
"""

from src.agents import dragapult_agent
from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import OptionType, SelectContext, to_observation_class  # noqa: E402

DECK: list[int] = dragapult_agent.DECK


def agent(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is not None:
        obs = to_observation_class(obs_dict)
        if obs.select is not None and obs.select.context == SelectContext.IS_FIRST:
            for i, o in enumerate(obs.select.option):
                if o.type == OptionType.YES:
                    return [i]
    return dragapult_agent.agent(obs_dict)
