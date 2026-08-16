"""Block-A1 opponent archetype model: classify the opponent's archetype from
their VISIBLE cards only (board + attachments + discard + their stadium --
never hidden info), then build the hidden-zone sampling pool the native MCTS
determinizes from: that archetype's canonical 60-card list minus everything
of theirs we can already see.

Replaces V17's blanket mirror-match assumption (opponent hidden zones sampled
from OUR OWN deck), which was correct only vs the Dragapult mirror; against
every other archetype the simulated opponent drew from the wrong 60 cards.
V17's meta-gauntlet baseline this must move: Mega Kangaskhan 9/20,
Fezandipiti 17/20, Marnie's Grimmsnarl 18/20 (results/v17_meta_gauntlet/).

Classification method (deliberately simple/deterministic, same spirit as
src/meta_analysis/archetype_signatures.py but ID-based so it needs no card
CSV at runtime):
  - weight every card id by 1/(number of archetype FAMILIES whose canonical
    list contains it) -- generic staples (Buddy-Buddy Poffin, Night
    Stretcher, basic energies...) shared by many families contribute little,
    family-unique cards (Marnie's Impidimp, Spikemuth Gym...) contribute 1.0;
  - per candidate deck, score = sum over visible ids of
    min(visible_count, deck_count) * weight;
  - accept the best deck only if its score clears MIN_EVIDENCE and beats the
    best deck of any OTHER family by MARGIN (variants of one family never
    compete -- a mirror opponent matching several Dragapult variants at once
    must not fall back just because those variants are close to each other);
  - otherwise return None: caller falls back to the V17 mirror assumption
    (still improved by the discard subtraction, which V17 never did).
"""

from __future__ import annotations

from collections import Counter

from src.agents.dragapult_agent_v23_cpp.archetype_decks import ARCHETYPE_DECKS

# One unique signature card (weight 1.0) is enough evidence: several families
# are identifiable from the very first Pokemon they bench (Marnie's Impidimp,
# Abra, Dwebble...). MARGIN below keeps a single shared-but-rare card from
# flipping the label between two close families.
MIN_EVIDENCE = 1.0
MARGIN = 0.35

_DECK_COUNTERS: list[tuple[str, str, Counter]] = [
    (family, variant, Counter(cards)) for family, variant, _src, cards in ARCHETYPE_DECKS
]

# id -> 1/(number of distinct families containing it)
_FAMILY_SETS: dict[str, set[int]] = {}
for _family, _variant, _counter in _DECK_COUNTERS:
    _FAMILY_SETS.setdefault(_family, set()).update(_counter.keys())
_ID_WEIGHT: dict[int, float] = {}
for _ids in _FAMILY_SETS.values():
    for _cid in _ids:
        _ID_WEIGHT[_cid] = _ID_WEIGHT.get(_cid, 0.0) + 1.0
_ID_WEIGHT = {cid: 1.0 / n for cid, n in _ID_WEIGHT.items()}


def classify(visible: Counter) -> tuple[str, str, Counter] | None:
    """visible: multiset of the opponent's visible card ids. Returns
    (family, variant, deck_counter) for the best-matching canonical deck, or
    None if the evidence is insufficient/ambiguous (caller uses the mirror
    fallback)."""
    if not visible:
        return None
    best: tuple[float, str, str, Counter] | None = None
    best_per_family: dict[str, float] = {}
    for family, variant, deck in _DECK_COUNTERS:
        score = 0.0
        for cid, vis_n in visible.items():
            deck_n = deck.get(cid, 0)
            if deck_n:
                score += min(vis_n, deck_n) * _ID_WEIGHT.get(cid, 0.0)
        if score > best_per_family.get(family, 0.0):
            best_per_family[family] = score
        if best is None or score > best[0]:
            best = (score, family, variant, deck)
    assert best is not None
    best_score, family, variant, deck = best
    if best_score < MIN_EVIDENCE:
        return None
    runner_up = max((s for f, s in best_per_family.items() if f != family), default=0.0)
    if best_score - runner_up < MARGIN:
        return None
    return family, variant, deck


def build_hidden_pool(visible: Counter, mirror_deck: list[int]) -> tuple[list[int], str, str]:
    """Returns (pool, family_label, variant_label) where pool is the list of
    card ids the opponent's hidden zones (deck + hand + prizes) should be
    sampled from: the classified archetype's canonical 60 (or `mirror_deck`
    on fallback) minus every visible card of theirs, element-wise with floor
    0. The native side shuffles/deals this pool and pads with its energy
    filler if the pool runs short (canonical list != the opponent's real
    variant), exactly as it already padded V17's mirror pool."""
    match = classify(visible)
    if match is None:
        family, variant, deck = "MIRROR_FALLBACK", "our_v6_mirror", Counter(mirror_deck)
    else:
        family, variant, deck = match
    remaining = deck.copy()
    remaining.subtract(visible)
    pool: list[int] = []
    for cid, n in remaining.items():
        if n > 0:
            pool.extend([cid] * n)
    return pool, family, variant
