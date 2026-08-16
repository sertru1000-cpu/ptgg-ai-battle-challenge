"""Deterministic clustering of UNLABELED exact decklists into archetype families.

Method (documented per Part 4's requirement to state the methodology): decks that
already match a known signature Pokemon (src/meta_analysis/archetype_signatures.py)
keep that label. For the remainder, cluster by the EXACT SET of "headline" Pokemon
names present in the list -- Pokemon with Rule == "Pokemon ex" or "Mega Pokemon ex"
in the official card data (i.e. the special-rule attacker(s) that define a deck's
identity, the same convention the 12 known archetype names already use, e.g.
"Marnie's Grimmsnarl ex"). Two exact decklists land in the same cluster iff they
share the identical multiset of headline-Pokemon names -- no similarity threshold,
no ML, fully deterministic and reproducible from the card data + decklist alone.

Decks with NO headline (ex/Mega) Pokemon at all fall back to clustering by the set
of ALL Pokemon names present (rare -- most competitive lists run at least one ex/
Mega attacker, per Part 1's deck-variance findings), still exact-set-match, still
deterministic.

Cluster IDs are assigned UNLABELED_CLUSTER_01, 02, ... ordered by descending total
game count, so cluster numbering has a stable, interpretable meaning (lower number
= more games) rather than being an artifact of dict/hash ordering.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from src.meta_analysis.card_lookup import load_card_data

_headline_names_cache = None
_pokemon_names_cache = None


def _classify():
    global _headline_names_cache, _pokemon_names_cache
    if _headline_names_cache is not None:
        return
    table = load_card_data()
    headline = {}   # card_id -> name, for ex/Mega ex Pokemon
    pokemon = {}    # card_id -> name, for any Pokemon (HP != n/a)
    for cid, row in table.items():
        hp = row.get("HP", "n/a")
        if hp and hp != "n/a":
            pokemon[cid] = row["Card Name"]
            rule = row.get("Rule", "n/a")
            # Rule column only takes 4 values in this dataset: "n/a", "ACE SPEC",
            # "Pokemon ex", "Mega Pokemon ex" (the latter two contain a mojibake
            # U+FFFD in place of the accented e when read via errors="replace" --
            # match by exclusion instead of a literal accented-e string).
            if rule not in ("n/a", "ACE SPEC"):
                headline[cid] = row["Card Name"]
    _headline_names_cache = headline
    _pokemon_names_cache = pokemon


def deck_signature(deck: Counter) -> tuple[str, ...]:
    """Returns a stable, sorted tuple of headline-Pokemon names present in the deck
    (falls back to all-Pokemon names if the deck has no headline Pokemon)."""
    _classify()
    headline_names = sorted({_headline_names_cache[cid] for cid in deck if cid in _headline_names_cache})
    if headline_names:
        return tuple(headline_names)
    all_pokemon_names = sorted({_pokemon_names_cache[cid] for cid in deck if cid in _pokemon_names_cache})
    return tuple(all_pokemon_names)


def cluster_unlabeled_decks(deck_registry: dict) -> dict:
    """deck_registry: deck_hash -> dict with at least 'label', 'composition' (str
    "cid:count;cid:count..."), 'n_games_seen'. Mutates nothing; returns
    deck_hash -> cluster_id for every UNLABELED deck (labeled decks are not
    remapped -- caller should use their existing 'label' as-is)."""
    unlabeled = {h: d for h, d in deck_registry.items() if d["label"] == "UNLABELED"}

    sig_to_hashes = defaultdict(list)
    for hsh, d in unlabeled.items():
        deck = Counter()
        for pair in d["composition"].split(";"):
            if not pair:
                continue
            cid, cnt = pair.split(":")
            deck[int(cid)] = int(cnt)
        sig = deck_signature(deck)
        sig_to_hashes[sig].append(hsh)

    # order clusters by total games (descending) for stable, meaningful numbering
    sig_games = []
    for sig, hashes in sig_to_hashes.items():
        total_games = sum(int(unlabeled[h]["n_games_seen"]) for h in hashes)
        sig_games.append((sig, hashes, total_games))
    sig_games.sort(key=lambda t: -t[2])

    hash_to_cluster = {}
    cluster_info = {}
    for i, (sig, hashes, total_games) in enumerate(sig_games, start=1):
        cluster_id = f"UNLABELED_CLUSTER_{i:02d}"
        cluster_info[cluster_id] = {
            "cluster_id": cluster_id,
            "signature": ", ".join(sig) if sig else "(no Pokemon signature found)",
            "n_exact_variants": len(hashes),
            "n_games": total_games,
            "deck_hashes": hashes,
        }
        for h in hashes:
            hash_to_cluster[h] = cluster_id

    return hash_to_cluster, cluster_info
