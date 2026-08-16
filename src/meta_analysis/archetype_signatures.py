"""Lightweight, explicitly-heuristic archetype tagging by signature-Pokemon name match.

This is NOT a claim that these 11 names are the complete meta (Part 1 Step 4 explicitly
forbids that assumption) -- it is only a tag against the archetypes we already have outside
labels for (the 8 real live-ladder archetypes from the 2026-07-31 community snapshot, plus
the 4 local official sample decks), so that empirically-discovered deck clusters can be
cross-checked against known names where they happen to overlap. Any deck that doesn't match
is left UNLABELED rather than forced into the nearest name.
"""
from __future__ import annotations

from collections import Counter

from src.meta_analysis.card_lookup import load_card_data

CURLY_APOSTROPHE = chr(0x2019)  # U+2019 RIGHT SINGLE QUOTATION MARK, used in the card CSV


def _norm(s: str) -> str:
    return s.lower().replace(CURLY_APOSTROPHE, "'")


# archetype label -> substring(s) to match against Card Name (case-insensitive, apostrophe-normalized)
SIGNATURES = {
    "Marnie's Grimmsnarl ex": ["grimmsnarl"],
    # "kangaskhan" alone also matches the distinct "Team Rocket's Kangaskhan ex" card --
    # match the specific printings, not the bare species name.
    "Mega Kangaskhan ex": ["mega kangaskhan"],
    "Team Rocket's Kangaskhan ex": ["team rocket's kangaskhan"],
    "Fezandipiti ex": ["fezandipiti"],
    "Cynthia's Garchomp ex": ["garchomp"],
    "Dragapult ex": ["dragapult"],
    # "ogerpon" alone matches 4 distinct Mask variants -- only Teal Mask is the tracked archetype.
    "Teal Mask Ogerpon ex": ["teal mask ogerpon"],
    "Mega Lopunny ex": ["lopunny"],
    "Team Rocket's Mewtwo ex": ["mewtwo"],
    "Mega Abomasnow ex": ["abomasnow"],
    # bare "voltorb ex" is a separate printing from the Iono's-package card -- match the
    # Iono's-prefixed printings specifically to avoid conflating the two.
    "Iono's (Bellibolt/Voltorb)": ["iono's bellibolt", "iono's voltorb"],
    "Mega Lucario ex": ["lucario"],
}
SIGNATURES = {label: [_norm(s) for s in subs] for label, subs in SIGNATURES.items()}

_id_to_name_lower = None


def _index():
    global _id_to_name_lower
    if _id_to_name_lower is None:
        table = load_card_data()
        _id_to_name_lower = {cid: _norm(row["Card Name"]) for cid, row in table.items()}
    return _id_to_name_lower


def tag_deck(deck: Counter) -> tuple[str, int, list[str]]:
    """Returns (label, matched_card_count, evidence_names). label is 'UNLABELED' if no
    signature Pokemon appears at all."""
    names = _index()
    scores = {}
    evidence = {}
    for label, substrings in SIGNATURES.items():
        count = 0
        ev = []
        for cid, n in deck.items():
            nm = names.get(cid, "")
            if any(s in nm for s in substrings):
                count += n
                ev.append(names[cid])
        if count > 0:
            scores[label] = count
            evidence[label] = ev
    if not scores:
        return "UNLABELED", 0, []
    best = max(scores, key=scores.get)
    return best, scores[best], evidence[best]
