"""Full Part 4.1 v3 analysis, operating on results/meta/episodes_summary.parquet
(the compact normalized dataset) -- never re-reads raw episode JSON.

Writes:
  results/meta/deck_stats.csv         exact deck_hash level (+ cluster_id joined)
  results/meta/matchup_matrix.csv     both EXACT (deck_hash) and ARCHETYPE (cluster_id)
                                       rows, disambiguated by a 'level' column
  results/meta/deck_variants.csv      archetype/cluster level (the "variant" unit)
  results/meta/rating_analysis.csv    overall rating-bucket win rates + per-archetype
                                       performance-by-rating-bucket
  results/meta/analysis_out_v3.txt    full plain-text summary (source for real_meta_v2.md)
  reports/meta_data_quality.md
"""
import math
import os
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd

from src.meta_analysis.card_lookup import name_of

PARQUET = os.path.join(REPO_ROOT, "results", "meta", "episodes_summary.parquet")
OUT_DIR = os.path.join(REPO_ROOT, "results", "meta")
TXT_OUT = os.path.join(OUT_DIR, "analysis_out_v3.txt")
DQ_REPORT = os.path.join(REPO_ROOT, "reports", "meta_data_quality.md")

MIN_USABLE = 50
MIN_LOW_CONF = 20
DECK_LOW_N = 30


def wilson_ci(wins, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


class Tee:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def p(self, *args):
        s = " ".join(str(a) for a in args)
        print(s)
        self.f.write(s + "\n")

    def close(self):
        self.f.close()


def confidence_flag(n):
    if n < MIN_LOW_CONF:
        return "INSUFFICIENT"
    elif n < MIN_USABLE:
        return "LOW_CONFIDENCE"
    else:
        return "USABLE"


def main():
    df = pd.read_parquet(PARQUET)
    out = Tee(TXT_OUT)
    n_episodes = df["episode_id"].nunique()
    out.p("=" * 78)
    out.p(f"DATASET: {len(df)} side-rows ({n_episodes} episodes)")
    out.p(f"Date range: {df['date'].min()} to {df['date'].max()}")
    out.p(f"By period (episode-level, side=0 rows only to avoid double count): "
          f"{df[df['side']==0]['period'].value_counts().to_dict()}")

    decisive = df[df["outcome_type"] == "DECISIVE"].copy()
    draws = df[df["outcome_type"] == "DRAW"]
    errors = df[df["outcome_type"] == "ERROR_OR_TIMEOUT"]
    out.p(f"outcome_type (episode-level): DECISIVE={decisive['episode_id'].nunique()} "
          f"DRAW={draws['episode_id'].nunique()} ERROR_OR_TIMEOUT={errors['episode_id'].nunique()}")

    # ================= DATA QUALITY REPORT =================
    n_ep = n_episodes
    ep0 = df[df["side"] == 0]
    dup_ids = ep0["episode_id"][ep0["episode_id"].duplicated()].tolist()
    missing_rating = df["player_rating"].isna().sum()
    missing_deck = df["player_deck_hash"].isna().sum()
    missing_result = df["result"].isna().sum()
    missing_timestamp = df["timestamp"].isna().sum() + (df["timestamp"] == "").sum()
    missing_length = df["game_length"].isna().sum()
    suspicious_rating = df[df["player_rating"].notna() & (df["player_rating"] <= 0)]
    suspicious_length = df[df["game_length"].notna() & (df["game_length"].astype(float) <= 0)]
    same_player_opp = ep0[ep0["player_id"] == ep0["opponent_id"]]
    n_unique_players = pd.concat([ep0["player_id"], ep0["opponent_id"]]).nunique()
    n_unique_decks = pd.concat([ep0["player_deck_hash"], ep0["opponent_deck_hash"]]).nunique()
    incomplete = df[df["player_rating"].isna() | df["player_deck_hash"].isna() |
                     df["result"].isna() | df["game_length"].isna()]
    pct_incomplete = len(incomplete) / len(df) * 100 if len(df) else 0

    with open(DQ_REPORT, "w", encoding="utf-8") as f:
        f.write(f"""# Meta Data Quality Report (Part 4.1 v3)

Generated from `results/meta/episodes_summary.parquet` ({len(df)} side-rows,
{n_ep} episodes). Source: incremental streaming extraction
(`tools/extract_meta_v3.py`), reusing {ep0['source'].str.contains('reuse').sum()}
episodes already downloaded/parsed in earlier sessions plus
{(ep0['source']=='new').sum()} newly streamed this session.

## Attempted / parsed / failed

- Episodes captured in the final dataset: **{n_ep}**
- Download/parse failures logged (see `results/meta/processing_failures.csv` for
  per-episode episode_id + stage + reason): see checkpoint file
  `results/meta/processing_checkpoint.json` for the authoritative
  processed/successful/failed counts from the streaming run.
- Duplicate episode_ids found: **{len(dup_ids)}** {"(" + str(dup_ids[:10]) + ")" if dup_ids else "(none)"}

## Missing fields (of {len(df)} side-rows)

| Field | Missing | % |
|---|---|---|
| player_rating (INFERRED, see caveat below) | {missing_rating} | {missing_rating/len(df)*100:.2f}% |
| player_deck_hash | {missing_deck} | {missing_deck/len(df)*100:.2f}% |
| result | {missing_result} | {missing_result/len(df)*100:.2f}% |
| timestamp | {missing_timestamp} | {missing_timestamp/len(df)*100:.2f}% |
| game_length | {missing_length} | {missing_length/len(df)*100:.2f}% |

**{pct_incomplete:.2f}%** of side-rows are missing at least one of
{{player_rating, player_deck_hash, result, game_length}}.

## IMPORTANT CAVEAT: player_rating / opponent_rating are INFERRED, not observed

The raw episode data (and the Kaggle manifest) never records which of a match's two
scores belongs to which side -- only an unordered pair
(`min_score`, `sum_score - min_score`) per episode, and the episode JSON itself has
no rating field at all (confirmed by direct inspection). `player_rating` /
`opponent_rating` here are the output of a statistical resolution method
(deck-based alternating assignment, see `src/meta_analysis/rating_resolution.py`)
that was validated against a labeled-outcome check (does the inferred-higher-rated
side actually win more often?) and found to show **no signal reliably above chance**
(~49-53% in every test run, including restricted to frequently-seen teams/decks).
Treat every rating-based number in this report as a labeled, low-confidence
**INFERRED** estimate, not a verified fact -- this is the single most important data
quality caveat in this dataset.

## Suspicious values

- `player_rating <= 0`: {len(suspicious_rating)} rows
- `game_length <= 0`: {len(suspicious_length)} rows
- identical player_id / opponent_id in the same episode: {len(same_player_opp)} rows
- impossible `result` values (outside WIN/LOSS/DRAW/ERROR_OR_TIMEOUT/null): 0 (validated by construction in `result_for_side()`)

No suspicious records were removed -- flagged only, per the standing process rule
against silently discarding data. If any of the above counts are non-zero they are
visible in this report for manual follow-up, not filtered out of the analysis
dataset.

## Coverage

- Date range: {df['date'].min()} to {df['date'].max()}
- Unique players (team names, both sides pooled): {n_unique_players}
- Unique exact decklists (deck_hash, both sides pooled): {n_unique_decks}
- Period breakdown (episodes): {ep0['period'].value_counts().to_dict()}
""")
    out.p(f"\nWrote {DQ_REPORT}")

    # ================= DECK STATS (exact deck_hash level) =================
    deck_rows = []
    grp = decisive.groupby("player_deck_hash")
    total_slots = len(decisive)
    for dh, g in grp:
        wins = (g["result"] == "WIN").sum()
        losses = (g["result"] == "LOSS").sum()
        n = len(g)
        p, lo, hi = wilson_ci(wins, n)
        fp = g[g["first_player"] == True]
        sp = g[g["first_player"] == False]
        fp_wr = (fp["result"] == "WIN").mean() if len(fp) else None
        sp_wr = (sp["result"] == "WIN").mean() if len(sp) else None
        deck_rows.append({
            "deck_hash": dh,
            "label": g["player_deck_label"].iloc[0],
            "cluster_id": g["player_deck_cluster_id"].iloc[0],
            "games": n, "share_pct": round(n / total_slots * 100, 3),
            "wins": int(wins), "losses": int(losses),
            "win_rate": round(p, 4), "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
            "first_player_win_rate": round(fp_wr, 4) if fp_wr is not None else "",
            "second_player_win_rate": round(sp_wr, 4) if sp_wr is not None else "",
            "avg_player_rating_inferred": round(g["player_rating"].mean(), 1) if g["player_rating"].notna().any() else "",
            "avg_opponent_rating_inferred": round(g["opponent_rating"].mean(), 1) if g["opponent_rating"].notna().any() else "",
            "avg_game_length": round(g["game_length"].astype(float).mean(), 1),
            "confidence": confidence_flag(n),
        })
    deck_df = pd.DataFrame(deck_rows).sort_values("games", ascending=False)
    deck_df.to_csv(os.path.join(OUT_DIR, "deck_stats.csv"), index=False)
    out.p(f"\nWrote deck_stats.csv: {len(deck_df)} exact decks")
    out.p("\nTOP 20 EXACT DECKS:")
    out.p(deck_df.head(20).to_string(index=False))

    # ================= ARCHETYPE/CLUSTER LEVEL =================
    cgrp = decisive.groupby("player_deck_cluster_id")
    ctotal = len(decisive)
    cluster_rows = []
    for cid, g in cgrp:
        wins = (g["result"] == "WIN").sum()
        n = len(g)
        p, lo, hi = wilson_ci(wins, n)
        cluster_rows.append({
            "cluster_id": cid, "games": n, "share_pct": round(n / ctotal * 100, 3),
            "win_rate": round(p, 4), "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
            "n_exact_decks": g["player_deck_hash"].nunique(),
            "avg_player_rating_inferred": round(g["player_rating"].mean(), 1) if g["player_rating"].notna().any() else None,
            "confidence": confidence_flag(n),
        })
    cluster_df = pd.DataFrame(cluster_rows).sort_values("games", ascending=False)
    out.p(f"\n{'='*78}\nARCHETYPE/CLUSTER LEVEL (n={len(cluster_df)})")
    out.p(cluster_df.head(30).to_string(index=False))

    # ---- temporal drift for major archetypes (games >= DECK_LOW_N overall) ----
    major = cluster_df[cluster_df["games"] >= DECK_LOW_N]["cluster_id"].tolist()
    out.p(f"\n{'='*78}\nTEMPORAL DRIFT for {len(major)} major archetypes (>= {DECK_LOW_N} games overall)")
    temporal_rows = []
    for cid in major:
        row = {"cluster_id": cid}
        for period in ["EARLY", "MIDDLE", "RECENT"]:
            pg = decisive[(decisive["player_deck_cluster_id"] == cid) & (decisive["period"] == period)]
            period_total = len(decisive[decisive["period"] == period])
            share = len(pg) / period_total * 100 if period_total else 0
            wr = (pg["result"] == "WIN").mean() if len(pg) else None
            row[f"share_{period.lower()}_pct"] = round(share, 2)
            row[f"n_{period.lower()}"] = len(pg)
            row[f"win_rate_{period.lower()}"] = round(wr, 3) if wr is not None else None
        temporal_rows.append(row)
    temporal_df = pd.DataFrame(temporal_rows)
    out.p(temporal_df.to_string(index=False))

    # ================= MATCHUP MATRIX (exact + archetype, one file) =================
    out.p(f"\n{'='*78}\nMATCHUP MATRIX")
    matchup_rows = []
    for level, col in [("EXACT", "player_deck_hash"), ("ARCHETYPE", "player_deck_cluster_id")]:
        opp_col = "opponent_deck_hash" if level == "EXACT" else "opponent_deck_cluster_id"
        m = defaultdict(lambda: {"games": 0, "wins": 0})
        for _, row in decisive.iterrows():
            key = (row[col], row[opp_col])
            m[key]["games"] += 1
            if row["result"] == "WIN":
                m[key]["wins"] += 1
        seen_pairs = set()
        for (a, b), s in m.items():
            pk = tuple(sorted([a, b]))
            if pk in seen_pairs or a == b:
                continue
            other = m.get((b, a), {"games": 0, "wins": 0})
            total_n = s["games"] + other["games"]
            if total_n == 0:
                continue
            seen_pairs.add(pk)
            p, lo, hi = wilson_ci(s["wins"], s["games"])
            matchup_rows.append({
                "level": level, "player_deck_hash": a, "opponent_deck_hash": b,
                "games": s["games"], "wins": s["wins"], "losses": s["games"] - s["wins"],
                "win_rate": round(p, 4), "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
                "confidence": confidence_flag(s["games"]),
            })
    matchup_df = pd.DataFrame(matchup_rows).sort_values(["level", "games"], ascending=[True, False])
    matchup_df.to_csv(os.path.join(OUT_DIR, "matchup_matrix.csv"), index=False)
    out.p(f"Wrote matchup_matrix.csv: {len(matchup_df)} rows "
          f"(EXACT={sum(matchup_df.level=='EXACT')}, ARCHETYPE={sum(matchup_df.level=='ARCHETYPE')})")
    arch_mm = matchup_df[matchup_df.level == "ARCHETYPE"]
    usable = arch_mm[arch_mm.confidence == "USABLE"]
    out.p(f"ARCHETYPE-level pairs: USABLE(>={MIN_USABLE})={len(usable)}, "
          f"LOW_CONFIDENCE({MIN_LOW_CONF}-{MIN_USABLE-1})={sum(arch_mm.confidence=='LOW_CONFIDENCE')}, "
          f"INSUFFICIENT(<{MIN_LOW_CONF})={sum(arch_mm.confidence=='INSUFFICIENT')}")
    out.p("\nMost lopsided USABLE archetype matchups:")
    lop = usable.copy()
    lop["dist"] = (lop["win_rate"] - 0.5).abs()
    out.p(lop.sort_values("dist", ascending=False).head(15).drop(columns="dist").to_string(index=False))

    # ================= DECK VARIANTS (archetype/cluster level) =================
    out.p(f"\n{'='*78}\nDECK VARIANTS")
    variant_rows = []
    deck_hash_composition = df.drop_duplicates("player_deck_hash").set_index("player_deck_hash")["player_deck_list"]
    for cid in cluster_df[cluster_df["games"] >= DECK_LOW_N]["cluster_id"]:
        member_hashes = deck_df[deck_df["cluster_id"] == cid].sort_values("games", ascending=False)
        if member_hashes.empty:
            continue
        total_games = member_hashes["games"].sum()
        rep = member_hashes.iloc[0]
        card_presence = Counter()
        n_variants = len(member_hashes)
        for dh in member_hashes["deck_hash"]:
            comp = deck_hash_composition.get(dh, "")
            if not isinstance(comp, str) or not comp:
                continue
            for pair in comp.split(";"):
                if not pair:
                    continue
                cid_, cnt = pair.split(":")
                card_presence[int(cid_)] += 1
        tech = sorted([c for c, cnt in card_presence.items() if cnt < n_variants],
                       key=lambda c: -card_presence[c])[:6]
        key_diffs = "; ".join(f"{name_of(c)} ({card_presence[c]}/{n_variants})" for c in tech)
        variant_rows.append({
            "variant_id": cid, "representative_deck_hash": rep["deck_hash"],
            "n_exact_variants": n_variants, "games": int(total_games),
            "share_pct": round(total_games / ctotal * 100, 3),
            "win_rate": round(member_hashes["wins"].sum() / total_games, 4) if total_games else "",
            "key_card_differences": key_diffs,
            "clustering_method": "deterministic: exact-set match on headline (ex/Mega ex) Pokemon names",
        })
    variant_df = pd.DataFrame(variant_rows).sort_values("games", ascending=False)
    variant_df.to_csv(os.path.join(OUT_DIR, "deck_variants.csv"), index=False)
    out.p(f"Wrote deck_variants.csv: {len(variant_df)} archetype/cluster variants "
          f"(>= {DECK_LOW_N} games each)")
    out.p("NOTE: variant identity = deterministic clustering by shared headline-Pokemon "
          "signature (src/meta_analysis/deck_clustering.py), not a learned/statistical "
          "clustering model -- documented explicitly per the prompt's instruction not to "
          "invent archetypes the data doesn't support.")

    # ================= RATING ANALYSIS =================
    out.p(f"\n{'='*78}\nRATING ANALYSIS")
    rated = decisive[decisive["player_rating"].notna()].copy()
    out.p(f"Decisive episodes with resolved (INFERRED) rating: {rated['episode_id'].nunique()}")
    if len(rated):
        out.p(f"player_rating distribution: min={rated.player_rating.min():.1f} "
              f"p25={rated.player_rating.quantile(.25):.1f} median={rated.player_rating.median():.1f} "
              f"p75={rated.player_rating.quantile(.75):.1f} max={rated.player_rating.max():.1f} "
              f"mean={rated.player_rating.mean():.1f}")
        rated["rating_bucket"] = pd.qcut(rated["player_rating"], 5, duplicates="drop")
        rating_rows = []
        for bucket, g in rated.groupby("rating_bucket", observed=True):
            wins = (g["result"] == "WIN").sum()
            n = len(g)
            p, lo, hi = wilson_ci(wins, n)
            rating_rows.append({
                "row_type": "OVERALL_BUCKET", "key": str(bucket), "games": n,
                "win_rate": round(p, 4), "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
                "avg_player_rating": round(g["player_rating"].mean(), 1),
                "avg_opponent_rating": round(g["opponent_rating"].mean(), 1),
                "avg_rating_diff": round((g["player_rating"] - g["opponent_rating"]).mean(), 1),
                "avg_game_length": round(g["game_length"].astype(float).mean(), 1),
                "confidence": confidence_flag(n),
            })
        # per-archetype x rating-bucket performance for major archetypes
        for cid in major:
            g_all = rated[rated["player_deck_cluster_id"] == cid]
            if len(g_all) < DECK_LOW_N:
                continue
            for bucket, g in g_all.groupby(pd.qcut(g_all["player_rating"], min(3, g_all["player_rating"].nunique()),
                                                     duplicates="drop"), observed=True):
                wins = (g["result"] == "WIN").sum()
                n = len(g)
                p, lo, hi = wilson_ci(wins, n)
                rating_rows.append({
                    "row_type": "DECK_BY_BUCKET", "key": f"{cid} | {bucket}", "games": n,
                    "win_rate": round(p, 4), "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
                    "avg_player_rating": round(g["player_rating"].mean(), 1),
                    "avg_opponent_rating": round(g["opponent_rating"].mean(), 1),
                    "avg_rating_diff": round((g["player_rating"] - g["opponent_rating"]).mean(), 1),
                    "avg_game_length": round(g["game_length"].astype(float).mean(), 1),
                    "confidence": confidence_flag(n),
                })
        rating_df = pd.DataFrame(rating_rows)
        rating_df.to_csv(os.path.join(OUT_DIR, "rating_analysis.csv"), index=False)
        out.p(f"Wrote rating_analysis.csv: {len(rating_df)} rows")
        out.p(rating_df[rating_df.row_type == "OVERALL_BUCKET"].to_string(index=False))

    # ================= SHORT-GAME ANALYSIS =================
    out.p(f"\n{'='*78}\nSHORT-GAME ANALYSIS")
    lengths = decisive["game_length"].astype(float)
    out.p(f"game_length distribution (decisive, side=0 rows would double count -- using all rows/2 implicitly "
          f"via episode-level dedup): n={decisive['episode_id'].nunique()} "
          f"p5={lengths.quantile(.05):.0f} p25={lengths.quantile(.25):.0f} median={lengths.median():.0f} "
          f"p75={lengths.quantile(.75):.0f} p95={lengths.quantile(.95):.0f}")
    short_threshold = lengths.quantile(0.10)
    out.p(f"Short-game threshold (10th percentile): {short_threshold:.0f} steps")
    short = decisive[decisive["game_length"].astype(float) <= short_threshold]
    short_by_cluster = short.groupby("player_deck_cluster_id").agg(
        games=("result", "size"), win_rate=("result", lambda s: (s == "WIN").mean())
    ).reset_index().sort_values("games", ascending=False)
    short_by_cluster["confidence"] = short_by_cluster["games"].apply(confidence_flag)
    out.p(f"Short games (<= {short_threshold:.0f} steps): {len(short)} side-rows")
    out.p(short_by_cluster.head(15).to_string(index=False))

    out.p("\nDONE.")
    out.close()


if __name__ == "__main__":
    main()
