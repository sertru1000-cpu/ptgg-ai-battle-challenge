"""V10 Test 1 -- deck loading (V10_IMPLEMENTATION_REPORT.md / governing task's
LOCAL VALIDATION Test 1).

Confirms:
  - V10 loads successfully through the full agent chain (main_v10.py ->
    final_candidate_agent_v10 -> dragapult_agent_v10 -> dragapult_policy_v10).
  - decks/dragapult_ex_v10.csv contains exactly 60 cards and is engine-legal
    (via tools/deck_validator.py's real battle_start check).
  - Buddy-Buddy Poffin x4 is present.
  - Munkidori is present.
  - Dragapult ex is present.
  - No Mega Lucario ex (or any Lucario) card ID appears anywhere in the deck.

Exit code 0 iff every check passes.
"""

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.deck_validator import validate_deck  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {detail}")
    if not condition:
        FAILURES.append(name)
    return condition


# Card IDs relevant to this check (named constants, same values as
# src/agents/dragapult_policy_v10.py / lucario_policy_v9.py).
BUDDY_BUDDY_POFFIN = 1086
MUNKIDORI = 112
DRAGAPULT_EX = 121
MEGA_LUCARIO_EX = 678  # decks/lucario_ex.csv's headline card (src/agents/lucario_policy_v9.py's own Mega_Lucario_ex constant) -- must never appear in V10's deck


def main() -> int:
    print("=== TEST 1 -- V10 deck loading ===")

    from src.agents.dragapult_policy_v10 import DECK as policy_deck
    from src.agents.dragapult_agent_v10 import DECK as agent_deck
    from src.agents.final_candidate_agent_v10 import DECK as final_deck
    import main_v10

    check("chain_consistent", policy_deck == agent_deck == final_deck == main_v10.DECK,
          "DECK constant identical across dragapult_policy_v10 -> dragapult_agent_v10 -> "
          "final_candidate_agent_v10 -> main_v10 (the full runtime import chain)")

    deck = policy_deck
    check("deck_len_60", len(deck) == 60, f"deck has {len(deck)} cards (must be exactly 60)")

    legal, msg = validate_deck(deck)
    check("deck_legal", legal, f"tools/deck_validator.py (real battle_start): {msg}")

    counts = Counter(deck)
    check("poffin_x4", counts[BUDDY_BUDDY_POFFIN] == 4,
          f"Buddy-Buddy Poffin (id={BUDDY_BUDDY_POFFIN}) count = {counts[BUDDY_BUDDY_POFFIN]} (must be 4)")
    check("munkidori_present", counts[MUNKIDORI] >= 1,
          f"Munkidori (id={MUNKIDORI}) count = {counts[MUNKIDORI]} (must be >=1)")
    check("dragapult_ex_present", counts[DRAGAPULT_EX] >= 1,
          f"Dragapult ex (id={DRAGAPULT_EX}) count = {counts[DRAGAPULT_EX]} (must be >=1)")
    check("no_lucario", counts[MEGA_LUCARIO_EX] == 0,
          f"Mega Lucario ex (id={MEGA_LUCARIO_EX}) count = {counts[MEGA_LUCARIO_EX]} (must be 0)")

    # Cross-check against the raw CSV directly too (not just the imported constant).
    csv_path = REPO / "decks" / "dragapult_ex_v10.csv"
    csv_deck = [int(x) for x in csv_path.read_text().split("\n")[:60]]
    check("csv_matches_runtime_deck", csv_deck == deck,
          "decks/dragapult_ex_v10.csv on disk matches the DECK the running agent actually plays")

    # Also confirm V10's deck differs from V8/V9's decks (this is a real,
    # deliberate deck change, not an accidental no-op).
    from src.agents.dragapult_policy_v8 import DECK as v8_deck
    from src.agents.lucario_policy_v9 import DECK as v9_deck
    check("differs_from_v8_deck", deck != v8_deck, "V10's deck is different from V8's decks/dragapult_ex.csv (a real modernization, not a copy)")
    check("differs_from_v9_deck", deck != v9_deck, "V10's deck is different from V9's decks/lucario_ex.csv (V10 is Dragapult-based, not Lucario)")
    check("v9_actually_contains_lucario_for_contrast", MEGA_LUCARIO_EX in v9_deck,
          f"sanity check on the constant itself: id={MEGA_LUCARIO_EX} really is present in V9's own deck (proves this isn't a vacuously-true id)")

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: all V10 deck-loading checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
