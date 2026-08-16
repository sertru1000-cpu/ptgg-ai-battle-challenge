"""Helpers shared verbatim (in spirit) across all four official sample-notebook
heuristic agents. Ported here once instead of duplicated per agent module.
"""

from pathlib import Path

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import AreaType, Card, Observation, Pokemon, SelectContext, SelectData  # noqa: E402


def get_card(obs: Observation, area: AreaType, index: int, player_index: int) -> Pokemon | Card | None:
    """Look up the Card/Pokemon object a given (area, index, player) option refers to.

    Identical helper to the one duplicated in all four official notebooks.
    """
    ps = obs.current.players[player_index]
    match area:
        case AreaType.DECK:
            return obs.select.deck[index]
        case AreaType.HAND:
            return ps.hand[index]
        case AreaType.DISCARD:
            return ps.discard[index]
        case AreaType.ACTIVE:
            return ps.active[index]
        case AreaType.BENCH:
            return ps.bench[index]
        case AreaType.PRIZE:
            return ps.prize[index]
        case AreaType.STADIUM:
            return obs.current.stadium[index]
        case AreaType.LOOKING:
            return obs.current.looking[index]
        case _:
            return None


def load_deck_csv(path: str | Path) -> list[int]:
    """Read a 60-line deck.csv (one card ID per line) into list[int].

    Takes an explicit path rather than the notebooks' cwd-relative "deck.csv" +
    "/kaggle_simulations/agent/deck.csv" fallback: our tournament harness runs
    two agent modules in the same process, so a relative path would collide
    between them. (Each real submission's main.py keeps its own relative-path
    loading logic for Kaggle grading; that's independent of this helper.)
    """
    path = Path(path)
    lines = path.read_text().split("\n")
    deck = [int(lines[i]) for i in range(60)]
    return deck


def select_top_simple(select: SelectData, scores: list[int]) -> list[int]:
    """Exact port of the plain tail used by the Mega Abomasnow ex and Iono's
    notebooks: always return the top select.maxCount indices by score,
    regardless of sign, and select.minCount is never consulted.

    Deliberately NOT the same as select_top() below: those two notebooks will
    always fill a bench/hand selection to maxCount even with only
    negative-scoring candidates left, whereas Dragapult ex's tail (see
    select_top()) can decline down to minCount in that situation. This is a
    genuine behavioral difference between the official agents, not an
    oversight -- preserve it per-deck rather than unifying it away.
    """
    if len(scores) < 1:
        return []
    order = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
    return order[: select.maxCount]


def select_top(select: SelectData, context: SelectContext, scores: list[int]) -> list[int]:
    """Sort options by score descending, return the top select.maxCount indices.

    Exact port of the tail duplicated across all four official notebooks,
    INCLUDING its narrow quirk: skipping a negative-score option past
    select.minCount is only done for SelectContext.TO_BENCH and
    SETUP_BENCH_POKEMON. For every other context, the top maxCount indices are
    always returned regardless of sign. This is preserved deliberately rather
    than generalized, since the official agents rely on it (e.g. always fully
    filling non-bench selections even when every candidate scores negative).
    """
    if len(scores) < 1:
        return []
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    output: list[int] = []
    for i in range(select.maxCount):
        idx, score = ranked[i]
        if (
            score >= 0
            or select.minCount > i
            or (context != SelectContext.TO_BENCH and context != SelectContext.SETUP_BENCH_POKEMON)
        ):
            output.append(idx)
    return output
