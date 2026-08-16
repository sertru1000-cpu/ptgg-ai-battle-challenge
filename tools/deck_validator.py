"""Part B.1: the smallest reliable automated deck-legality validator.

candidate deck -> battle_start(candidate, candidate) -> legal / illegal

Deliberately thin: `battle_start` IS the authoritative legality check (see
reports/competition_data_audit.md section 3 for the exact 5 rules it
enforces, read directly from Api.h's ApiBattleStart) -- this module adds
nothing beyond calling it correctly and decoding the (errorPlayer, errorType)
result into a readable message. No deck-generation, no optimization: per
Part B.1's instruction, this exists only to answer "is this candidate deck
legal", one deck (or pair) at a time.
"""

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

import cg.game as g  # noqa: E402

ERROR_MESSAGES = {
    1: "invalid card ID (not in the engine's 1267-card pool)",
    2: "more than 4 copies of a non-basic-energy card with the same name",
    3: "no Basic Pokemon in the deck",
    4: "more than 1 ACE SPEC card",
}


def validate_deck(deck: list[int], other_deck: list[int] | None = None) -> tuple[bool, str]:
    """Checks `deck`'s legality via a real battle_start call.

    other_deck defaults to a copy of `deck` itself (mirror match) so a
    single deck can be validated standalone without needing a second one.
    Returns (is_legal, message).
    """
    if len(deck) != 60:
        return False, f"deck has {len(deck)} cards, must be exactly 60"

    opponent = other_deck if other_deck is not None else list(deck)
    obs, start = g.battle_start(deck, opponent)
    try:
        if start.errorPlayer == -1:
            return True, "legal (errorType=0)"
        if start.errorPlayer == 0:
            reason = ERROR_MESSAGES.get(start.errorType, f"unknown errorType={start.errorType}")
            return False, f"illegal: {reason}"
        # errorPlayer == 1 means the *other_deck* was the illegal one, not `deck`.
        reason = ERROR_MESSAGES.get(start.errorType, f"unknown errorType={start.errorType}")
        return True, f"deck itself legal, but other_deck illegal: {reason}"
    finally:
        if start.errorPlayer == -1:
            g.battle_finish()


def load_deck_csv(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split("\n")[:60]]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck_csv", help="path to a 60-line deck.csv to validate")
    args = parser.parse_args()

    deck = load_deck_csv(args.deck_csv)
    legal, msg = validate_deck(deck)
    print(f"{args.deck_csv}: {'LEGAL' if legal else 'ILLEGAL'} -- {msg}")
