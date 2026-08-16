"""Phase: Kaggle Ladder ~50 Games Deep Analysis -- statistics pass.

Consumes results/agent/kaggle_ladder_games.csv (already built by
tools/build_kaggle_ladder_analysis.py) and computes every statistic the
phase prompt asks for: overall WR + CI + hypothesis test, matchup table
with Wilson CIs, going-first/second split, game-length buckets, cumulative
WR-by-game-number, decision-latency percentiles. Prints everything as JSON
so the report-writing step can consume exact numbers, not re-derive them.
"""
import json

import numpy as np
import pandas as pd
from scipy import stats

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
df = pd.read_csv(rf"{ROOT}\results\agent\kaggle_ladder_games.csv")


def wilson_ci(wins, n, z=1.96):
    if n == 0:
        return (None, None, None)
    p = wins / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


out = {}

# --- Overall ---
n = len(df)
wins = int((df["result"] == "WIN").sum())
losses = int((df["result"] == "LOSS").sum())
draws = int((df["result"] == "DRAW").sum())
wr, lo, hi = wilson_ci(wins, n)
binom = stats.binomtest(wins, n, 0.5)
out["overall"] = {
    "n": n, "wins": wins, "losses": losses, "draws": draws,
    "win_rate": wr, "wilson_lo": lo, "wilson_hi": hi,
    "binomial_p_value_vs_50pct": binom.pvalue,
}

# --- Cumulative WR by game number ---
df_sorted = df.sort_values("game_number")
cum_wins = (df_sorted["result"] == "WIN").cumsum()
cum_n = np.arange(1, n + 1)
cum_wr = cum_wins / cum_n
out["cumulative"] = [
    {"game_number": int(g), "cum_wins": int(w), "cum_n": int(cn), "cum_wr": float(wrr)}
    for g, w, cn, wrr in zip(df_sorted["game_number"], cum_wins, cum_n, cum_wr)
]

# --- Going first/second ---
gf = df[df["going_first"] == True]
gs = df[df["going_first"] == False]
gf_wins = int((gf["result"] == "WIN").sum())
gs_wins = int((gs["result"] == "WIN").sum())
gf_wr, gf_lo, gf_hi = wilson_ci(gf_wins, len(gf))
gs_wr, gs_lo, gs_hi = wilson_ci(gs_wins, len(gs))
# two-proportion z-test
if len(gf) > 0 and len(gs) > 0:
    p_pool = (gf_wins + gs_wins) / (len(gf) + len(gs))
    se = (p_pool * (1 - p_pool) * (1 / len(gf) + 1 / len(gs))) ** 0.5
    z = (gf_wr - gs_wr) / se if se > 0 else None
    p_two_prop = 2 * (1 - stats.norm.cdf(abs(z))) if z is not None else None
else:
    z, p_two_prop = None, None
out["going_first_second"] = {
    "going_first_n": len(gf), "going_first_wins": gf_wins, "going_first_wr": gf_wr,
    "going_first_wilson_lo": gf_lo, "going_first_wilson_hi": gf_hi,
    "going_second_n": len(gs), "going_second_wins": gs_wins, "going_second_wr": gs_wr,
    "going_second_wilson_lo": gs_lo, "going_second_wilson_hi": gs_hi,
    "z_stat": z, "p_value_two_proportion": p_two_prop,
    "unknown_first_player_n": int(df["going_first"].isna().sum()),
}

# --- Matchup table (opponent_matchup_key) ---
matchup_rows = []
for key, g in df.groupby("opponent_matchup_key"):
    gn = len(g)
    gw = int((g["result"] == "WIN").sum())
    gl = int((g["result"] == "LOSS").sum())
    gd = int((g["result"] == "DRAW").sum())
    p, lo_, hi_ = wilson_ci(gw, gn)
    if gn >= 20 and lo_ is not None and lo_ > 0.5:
        credibility = "STATISTICALLY_CREDIBLE"
    elif gn >= 5:
        credibility = "OBSERVED_ONLY_SMALL_N"
    else:
        credibility = "INSUFFICIENT_SAMPLE"
    matchup_rows.append({
        "opponent_matchup_key": key, "games": gn, "wins": gw, "losses": gl, "draws": gd,
        "win_rate": p, "wilson_lo": lo_, "wilson_hi": hi_, "credibility": credibility,
    })
matchup_rows.sort(key=lambda r: -r["games"])
out["matchups"] = matchup_rows

# --- Game length buckets (data-driven terciles) ---
turns = df["turns"].dropna()
q1, q2 = turns.quantile([1/3, 2/3])
def bucket(t):
    if pd.isna(t):
        return "NA"
    if t <= q1:
        return "SHORT"
    if t <= q2:
        return "MEDIUM"
    return "LONG"
df["length_bucket"] = df["turns"].apply(bucket)
length_rows = []
for b, g in df.groupby("length_bucket"):
    gn = len(g)
    gw = int((g["result"] == "WIN").sum())
    p, lo_, hi_ = wilson_ci(gw, gn)
    length_rows.append({
        "bucket": b, "games": gn, "wins": gw, "win_rate": p,
        "wilson_lo": lo_, "wilson_hi": hi_,
        "avg_turns": float(g["turns"].mean()), "avg_decision_count": float(g["decision_count"].mean()),
    })
out["game_length"] = {"thresholds_turns": {"q1_33pct": float(q1), "q2_67pct": float(q2)}, "buckets": length_rows}

# --- Decision latency (pooled across all games, from per-game aggregates already computed) ---
out["latency"] = {
    "mean_of_game_means_s": float(df["decision_duration_mean_s"].mean()),
    "mean_of_game_medians_s": float(df["decision_duration_median_s"].mean()),
    "max_overall_s": float(df["decision_duration_max_s"].max()),
    "mean_of_game_p95_s": float(df["decision_duration_p95_s"].mean()),
    "mean_of_game_p99_s": float(df["decision_duration_p99_s"].mean()),
    "total_calls_ge_1.0s": int(df["calls_ge_1.0s"].sum()),
    "total_calls_ge_1.8s": int(df["near_decision_budget_calls_ge_1.8s"].sum()),
    "total_decision_calls": int(df["decision_count"].sum()),
}

# --- Opponent rating / opponent metadata availability ---
out["data_availability"] = {
    "opponent_rating_available": False,
    "per_game_rating_before_after_available": False,
    "match_level_data_available": True,
    "agent_logs_available": True,
    "opponent_logs_available": False,
}

with open(rf"{ROOT}\results\agent\kaggle_ladder_stats.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)

print(json.dumps(out, indent=2, default=str))
