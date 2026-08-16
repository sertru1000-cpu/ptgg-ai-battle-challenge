"""Ablation B: the new deck-agnostic generic policy (generic_policy_agent.py)
bound to the existing Dragapult ex decklist. Deck held constant vs the
existing hand-tuned dragapult_agent.py so a tournament between the two
isolates the effect of the gameplay-policy change alone.
"""

from pathlib import Path

from src.agents.common import load_deck_csv
from src.agents.generic_policy_agent import make_agent

_DECK_PATH = Path(__file__).resolve().parents[2] / "decks" / "dragapult_ex.csv"
DECK: list[int] = load_deck_csv(_DECK_PATH)

agent = make_agent(DECK)
