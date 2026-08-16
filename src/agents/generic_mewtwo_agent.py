"""Ablation C: the new deck-agnostic generic policy bound to a real,
legal, engine-verified Team Rocket's Mewtwo ex decklist -- Phase 4.6's single
OOS_CONFIRMED validated-counter deck (Team Rocket's Mewtwo ex -> Fezandipiti
ex, 84.0-84.6% OOS win rate). The decklist is not hand-constructed: it is the
representative exact 60-card list (hash 58c4d89cf8edc355, 349 games, 30
observed exact variants) for the "Team Rocket's Mewtwo ex" archetype cluster
in results/meta/deck_variants.csv / deck_to_archetype.csv, i.e. a real list
actually played on the ladder during the analyzed window -- reused here
verbatim, not redesigned. Confirmed legal via tools/deck_validator.py
(errorType=0) before being wired into any tournament.
"""

from pathlib import Path

from src.agents.common import load_deck_csv
from src.agents.generic_policy_agent import make_agent

_DECK_PATH = Path(__file__).resolve().parents[2] / "decks" / "team_rockets_mewtwo_ex.csv"
DECK: list[int] = load_deck_csv(_DECK_PATH)

agent = make_agent(DECK)
