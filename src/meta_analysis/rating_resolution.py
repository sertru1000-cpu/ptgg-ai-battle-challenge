"""Resolve per-side ratings from the manifest's order-independent (min_score,
sum_score) pair, and fit a simple partial-pooled logistic regression of win
probability on rating difference.

WHY THIS IS NEEDED: the episode manifest gives (avg_score, min_score, sum_score)
per episode -- i.e. the two players' scores as an unordered pair (score_lo =
min_score, score_hi = sum_score - min_score) -- but never says which score belongs
to player 0 vs player 1. The raw episode JSON itself has no score/rating field at
all (verified directly). So "own rating" / "opponent rating" per deck cannot be
read off directly; it must be INFERRED.

METHOD (deck-based alternating assignment, a simple EM-style procedure):
  1. Initialize every deck_hash's rating estimate to the dataset's grand mean score.
  2. Repeat a fixed number of passes: for each episode, assign (score_lo, score_hi)
     to (deck0, deck1) in whichever of the 2 possible orders minimizes total
     absolute deviation from the current per-deck rating estimates; then recompute
     each deck's rating estimate as the mean of its assigned scores this pass.
  3. This converges deck rating estimates without ever needing to track individual
     agent/team identity over time (which would be too sparse in a sampled subset
     of a 278k-episode ladder -- most teams appear only a handful of times in any
     sample this size, deck_hash usage is much denser, see real_meta_pilot_v1.md).

This produces an INFERRED per-episode-per-side rating assignment. It is NOT a
verified fact -- it is a statistical resolution of an genuinely ambiguous signal,
and its own internal consistency (does the higher-assigned-rating side actually win
more often?) is reported as a validation check, not proof of correctness.

The logistic regression is a minimal pure-Python 1D Newton-Raphson fit (no
external ML dependency) of P(win) = sigmoid(beta * rating_diff), then, holding
beta fixed, a per-archetype intercept alpha_label fit the same way -- i.e. each
archetype's estimated win probability against an equal-rated opponent,
sigmoid(alpha_label), independent of matchmaking-induced rating gaps.
"""
from __future__ import annotations

import math
from collections import defaultdict


def resolve_ratings(episodes: list[dict], n_passes: int = 8) -> dict:
    """episodes: list of dicts with 'deck0_hash','deck1_hash','min_score','sum_score'
    (strings or floats/None). Returns dict episode_index -> (rating0, rating1, confident:bool)
    for episodes where scores were present and parseable."""
    valid = []
    scored = {}
    all_scores = []
    for i, e in enumerate(episodes):
        try:
            lo = float(e["min_score"])
            tot = float(e["sum_score"])
        except (TypeError, ValueError, KeyError):
            continue
        hi = tot - lo
        if hi < lo:
            lo, hi = hi, lo
        valid.append(i)
        scored[i] = (lo, hi)
        all_scores.append(lo)
        all_scores.append(hi)

    if not valid:
        return {}

    grand_mean = sum(all_scores) / len(all_scores)
    deck_rating = defaultdict(lambda: grand_mean)
    deck_ids_seen = set()
    for i in valid:
        deck_ids_seen.add(episodes[i]["deck0_hash"])
        deck_ids_seen.add(episodes[i]["deck1_hash"])
    for d in deck_ids_seen:
        deck_rating[d] = grand_mean

    assignment = {}  # i -> (r0, r1)
    for _ in range(n_passes):
        sums = defaultdict(float)
        counts = defaultdict(int)
        for i in valid:
            d0 = episodes[i]["deck0_hash"]
            d1 = episodes[i]["deck1_hash"]
            lo, hi = scored[i]
            cost_a = abs(deck_rating[d0] - lo) + abs(deck_rating[d1] - hi)   # d0=lo, d1=hi
            cost_b = abs(deck_rating[d0] - hi) + abs(deck_rating[d1] - lo)   # d0=hi, d1=lo
            if cost_a <= cost_b:
                r0, r1 = lo, hi
            else:
                r0, r1 = hi, lo
            assignment[i] = (r0, r1, abs(cost_a - cost_b))
            sums[d0] += r0
            counts[d0] += 1
            sums[d1] += r1
            counts[d1] += 1
        for d in deck_ids_seen:
            if counts[d] > 0:
                deck_rating[d] = sums[d] / counts[d]

    # confidence: normalize |cost_a - cost_b| by the score gap itself (a wash when
    # the two players are near-identically rated, genuinely ambiguous when the gap
    # is large but the deck-rating-based cost difference is still small)
    result = {}
    for i in valid:
        r0, r1, cost_gap = assignment[i]
        gap = abs(r0 - r1)
        confident = (gap < 1e-6) or (cost_gap / max(gap, 1e-6) > 0.25)
        result[i] = (r0, r1, confident)
    return result, dict(deck_rating)


def _sigmoid(x):
    if x < -700:
        return 0.0
    if x > 700:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def fit_1d_logistic(xs: list[float], ys: list[int], max_iter: int = 50, l2: float = 1e-4):
    """Fit P(y=1) = sigmoid(a + b*x) via Newton-Raphson (2 params). Pure Python,
    no numpy. Returns (a, b). l2 is a tiny ridge penalty for numerical stability
    on small/degenerate samples."""
    a, b = 0.0, 0.0
    n = len(xs)
    if n < 5:
        return a, b
    for _ in range(max_iter):
        g_a = g_b = 0.0
        h_aa = h_ab = h_bb = 0.0
        for x, y in zip(xs, ys):
            p = _sigmoid(a + b * x)
            err = y - p
            g_a += err
            g_b += err * x
            w = p * (1 - p)
            h_aa += w
            h_ab += w * x
            h_bb += w * x * x
        g_a -= l2 * a
        g_b -= l2 * b
        h_aa += l2
        h_bb += l2
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        da = (g_a * h_bb - g_b * h_ab) / det
        db = (h_aa * g_b - h_ab * g_a) / det
        a += da
        b += db
        if abs(da) < 1e-8 and abs(db) < 1e-8:
            break
    return a, b


def fit_pooled_beta(xs: list[float], ys: list[int]) -> float:
    """Global beta (rating_diff -> win prob slope), intercept-free assumption
    relaxed by fitting both then discarding the pooled intercept (the per-label fit
    below re-fits its own intercept holding beta fixed)."""
    a, b = fit_1d_logistic(xs, ys)
    return b


def fit_label_intercept(xs: list[float], ys: list[int], beta: float, max_iter: int = 50, l2: float = 1e-4):
    """Fix beta (global rating-diff slope), fit only alpha (per-archetype intercept)
    via 1D Newton-Raphson. Returns alpha; sigmoid(alpha) is the archetype's
    estimated win probability at rating_diff=0 (an equal-rated opponent)."""
    a = 0.0
    n = len(xs)
    if n < 5:
        return None
    for _ in range(max_iter):
        g = 0.0
        h = 0.0
        for x, y in zip(xs, ys):
            p = _sigmoid(a + beta * x)
            g += (y - p)
            h += p * (1 - p)
        g -= l2 * a
        h += l2
        if h < 1e-12:
            break
        da = g / h
        a += da
        if abs(da) < 1e-8:
            break
    return a
