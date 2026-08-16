"""Experiment 1: Going First / Second Analysis.

Research-only script. Reads results/meta/episodes_summary.parquet (never modified).
Writes ONLY to results/agent/going_first_second_analysis.csv.

Methodology:
- Filter to outcome_type == 'DECISIVE'.
- Archetype-level: named archetypes only (exclude 'UNLABELED' and any
  'UNLABELED_CLUSTER_*' -- those are not real pickable decks).
- Floor of games >= 30 per condition (first / second) before a row is reported at all.
- Wilson 95% CIs for each win rate.
- "Advantage" = P(win|first) - P(win|second), CI via the Wald two-independent-
  proportions normal approximation (documented explicitly, since the two groups
  -- games where the archetype was first vs. games where it was second -- are
  disjoint sets of episodes, not paired observations).
- Pooled (whole-dataset) advantage computed the same way, over all decisive
  deck-slots regardless of archetype.
- "credible" = Wilson-style significance proxy for the *advantage*: the Wald CI
  on the advantage lies entirely on one side of zero AND both group sizes clear
  the >=30 floor.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
PARQUET_PATH = REPO_ROOT / "results" / "meta" / "episodes_summary.parquet"
OUT_PATH = REPO_ROOT / "results" / "agent" / "going_first_second_analysis.csv"

MIN_GAMES = 30
Z = 1.959963984540054  # 95% two-sided normal quantile


def wilson_ci(k: int, n: int, z: float = Z):
    if n == 0:
        return (float("nan"), float("nan"))
    phat = k / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return max(0.0, lo), min(1.0, hi)


def wald_diff_ci(k1: int, n1: int, k2: int, n2: int, z: float = Z):
    """Two-independent-proportions Wald CI for p1 - p2."""
    if n1 == 0 or n2 == 0:
        return (float("nan"), float("nan"), float("nan"))
    p1, p2 = k1 / n1, k2 / n2
    diff = p1 - p2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return diff, diff - z * se, diff + z * se


def make_row(level, label, gf, wf, gs, ws):
    wr_f = wf / gf if gf else float("nan")
    wr_s = ws / gs if gs else float("nan")
    wlo_f, whi_f = wilson_ci(wf, gf) if gf else (float("nan"), float("nan"))
    wlo_s, whi_s = wilson_ci(ws, gs) if gs else (float("nan"), float("nan"))
    adv, adv_lo, adv_hi = wald_diff_ci(wf, gf, ws, gs)
    credible = bool(
        gf >= MIN_GAMES
        and gs >= MIN_GAMES
        and not math.isnan(adv_lo)
        and not math.isnan(adv_hi)
        and ((adv_lo > 0 and adv_hi > 0) or (adv_lo < 0 and adv_hi < 0))
    )
    return {
        "level": level,
        "archetype_or_matchup": label,
        "games_first": gf,
        "wins_first": wf,
        "wr_first": wr_f,
        "wilson_lo_first": wlo_f,
        "wilson_hi_first": whi_f,
        "games_second": gs,
        "wins_second": ws,
        "wr_second": wr_s,
        "wilson_lo_second": wlo_s,
        "wilson_hi_second": whi_s,
        "advantage": adv,
        "advantage_ci_lo": adv_lo,
        "advantage_ci_hi": adv_hi,
        "credible": credible,
    }


def main():
    df = pd.read_parquet(PARQUET_PATH)
    dec = df[df["outcome_type"] == "DECISIVE"].copy()
    dec["is_win"] = (dec["result"] == "WIN").astype(int)

    # --- verified-fact checks (printed, ASCII-only) ---
    n_total = len(df)
    n_dec = len(dec)
    n_dec_episodes = dec["episode_id"].nunique()
    fp_notnull = dec["first_player"].notna().sum()
    pairing = dec.groupby("episode_id")["first_player"].sum()
    n_exactly_one_true = int((pairing == 1).sum())
    print("VERIFIED FACT: total rows in parquet =", n_total)
    print("VERIFIED FACT: DECISIVE rows =", n_dec, "spanning", n_dec_episodes, "episodes")
    print("VERIFIED FACT: first_player non-null on ALL decisive rows =", fp_notnull == n_dec, f"({fp_notnull}/{n_dec})")
    print(
        "VERIFIED FACT: episodes with exactly one side first_player=True =",
        n_exactly_one_true, "/", len(pairing),
        "(" + str(n_exactly_one_true == len(pairing)) + ")",
    )

    rows = []

    # --- pooled (whole dataset) ---
    fp_true = dec[dec["first_player"] == True]
    fp_false = dec[dec["first_player"] == False]
    rows.append(
        make_row(
            "POOLED", "ALL_DECISIVE_GAMES",
            len(fp_true), int(fp_true["is_win"].sum()),
            len(fp_false), int(fp_false["is_win"].sum()),
        )
    )

    # --- archetype level ---
    named = dec[
        (dec["player_deck_label"] != "UNLABELED")
        & (~dec["player_deck_label"].str.startswith("UNLABELED_CLUSTER"))
    ]
    for label, g in named.groupby("player_deck_label"):
        gf = g[g["first_player"] == True]
        gs = g[g["first_player"] == False]
        if len(gf) >= MIN_GAMES and len(gs) >= MIN_GAMES:
            rows.append(
                make_row(
                    "ARCHETYPE", label,
                    len(gf), int(gf["is_win"].sum()),
                    len(gs), int(gs["is_win"].sum()),
                )
            )

    # --- matchup level (player_deck_label vs opponent_deck_label), named only ---
    named_matchup = dec[
        (dec["player_deck_label"] != "UNLABELED")
        & (~dec["player_deck_label"].str.startswith("UNLABELED_CLUSTER"))
        & (dec["opponent_deck_label"] != "UNLABELED")
        & (~dec["opponent_deck_label"].str.startswith("UNLABELED_CLUSTER"))
    ]
    for (p_label, o_label), g in named_matchup.groupby(["player_deck_label", "opponent_deck_label"]):
        gf = g[g["first_player"] == True]
        gs = g[g["first_player"] == False]
        if len(gf) >= MIN_GAMES and len(gs) >= MIN_GAMES:
            label = f"{p_label} vs {o_label}"
            rows.append(
                make_row(
                    "MATCHUP", label,
                    len(gf), int(gf["is_win"].sum()),
                    len(gs), int(gs["is_win"].sum()),
                )
            )

    out = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print("Wrote", OUT_PATH, "rows=", len(out))
    print("Archetype rows meeting >=30/>=30 floor:", (out["level"] == "ARCHETYPE").sum())
    print("Matchup rows meeting >=30/>=30 floor:", (out["level"] == "MATCHUP").sum())
    print("Credible rows (any level):", int(out["credible"].sum()))
    # print a plain-ASCII summary table without special characters
    for _, r in out.iterrows():
        print(
            r["level"], "|", r["archetype_or_matchup"].encode("ascii", "replace").decode("ascii"),
            "| gf=", r["games_first"], "wr_f=%.3f" % r["wr_first"],
            "| gs=", r["games_second"], "wr_s=%.3f" % r["wr_second"],
            "| adv=%.4f [%.4f, %.4f]" % (r["advantage"], r["advantage_ci_lo"], r["advantage_ci_hi"]),
            "| credible=", r["credible"],
        )


if __name__ == "__main__":
    main()
