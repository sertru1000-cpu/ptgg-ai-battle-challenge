"""Small statistics helpers for comparing win rates between conditions.

Not a general stats library -- just the two things this project's experiment
discipline requires repeatedly (see [[feedback-ptcg-process]]): a Wald 95% CI
on a single proportion, and a two-proportion z-test to tell "likely real
difference" from "probably noise" per Phase 9 of the Competitive V1 prompt.
"""

import math


def wald_ci(x: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% (by default) Wald confidence interval for a win rate x/n."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = x / n
    se = math.sqrt(p * (1 - p) / n)
    lo, hi = p - z * se, p + z * se
    return (max(0.0, lo), min(1.0, hi))


def two_proportion_ztest(x1: int, n1: int, x2: int, n2: int) -> float:
    """Two-proportion pooled z-test statistic. |z| > 1.96 ~ p<0.05 (two-tailed)."""
    if n1 == 0 or n2 == 0:
        return float("nan")
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return float("nan")
    return (p2 - p1) / se


def summarize(label: str, x: int, n: int) -> str:
    if n == 0:
        return f"{label}: no games"
    p = x / n
    lo, hi = wald_ci(x, n)
    return f"{label}: {p:.4f} ({x}/{n}) 95% CI=[{lo:.3f},{hi:.3f}]"


def compare(label: str, x1: int, n1: int, x2: int, n2: int, name1: str = "A", name2: str = "B") -> str:
    p1, p2 = (x1 / n1 if n1 else float("nan")), (x2 / n2 if n2 else float("nan"))
    z = two_proportion_ztest(x1, n1, x2, n2)
    sig = "SIGNIFICANT (|z|>1.96)" if abs(z) > 1.96 else "not significant"
    return f"{label}: {name1}={p1:.4f} (n={n1}) vs {name2}={p2:.4f} (n={n2})  z={z:.2f}  {sig}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("x1", type=int)
    parser.add_argument("n1", type=int)
    parser.add_argument("x2", type=int, nargs="?", default=None)
    parser.add_argument("n2", type=int, nargs="?", default=None)
    args = parser.parse_args()

    print(summarize("condition 1", args.x1, args.n1))
    if args.x2 is not None and args.n2 is not None:
        print(summarize("condition 2", args.x2, args.n2))
        print(compare("comparison", args.x1, args.n1, args.x2, args.n2))
