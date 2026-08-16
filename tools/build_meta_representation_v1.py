"""Phase 4.2 -- Meta Representation & Opponent Archetype Model.

Builds a compact, statistically grounded representation of the meta from the
already-processed Phase 4.1 outputs. Reads ONLY results/meta/episodes_summary.parquet
(the canonical 3,499-episode / 6,998-side-row dataset) -- no new raw episode downloads,
no rating feature used anywhere in the outputs below.

Writes:
  results/meta/deck_to_archetype.csv
  results/meta/archetype_features.csv
  results/meta/archetype_matchups.csv
  results/meta/meta_prior.csv
  results/meta/meta_graph.json
  results/meta/opponent_archetypes.json

Design choices are documented inline where a threshold or rule is chosen, and
summarized in reports/meta_representation_v1.md.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd

from src.meta_analysis.card_lookup import name_of
from src.meta_analysis.deck_clustering import deck_signature

OUT_DIR = os.path.join(REPO_ROOT, "results", "meta")
PARQUET = os.path.join(OUT_DIR, "episodes_summary.parquet")

# ---- documented thresholds (inspected against actual distribution, see report) ----
CONF_INSUFFICIENT = 20   # < this -> INSUFFICIENT
CONF_USABLE = 50         # [LOW_CONFIDENCE, this) -> LOW_CONFIDENCE, [this, CONF_HIGH) -> USABLE
CONF_HIGH = 100          # >= this -> HIGH_CONFIDENCE
# same 4-tier scheme reused for both archetype-level sample size and matchup-pair
# sample size -- the underlying statistical logic (how much a proportion estimate
# should be trusted) is identical in both cases.

SHRINKAGE_K = 30  # pseudo-games pulled toward 0.5 in the Beta-Binomial shrinkage estimator
# rationale: the pooled dataset is exactly 50/50 wins/losses by construction (every
# decisive game contributes one WIN row and one LOSS row), so 0.5 is the natural prior
# mean. K=30 means an archetype with ~30 games gets pulled about halfway back toward
# 0.5; an archetype with 1000s of games is barely shrunk at all. This directly
# implements the "don't let tiny samples look artificially strong" requirement (Sec 5).

COUNTER_MIN_GAMES = CONF_USABLE          # must be at least USABLE sample to call a counter "credible"
COUNTER_WILSON_LO_MIN = 0.50             # 95% CI lower bound must clear 50% (excludes coin-flip)

DRIFT_STRONG = 10.0    # percentage points
DRIFT_MODERATE = 3.0
WR_CHANGE_MEANINGFUL = 5.0  # percentage points, win-rate change threshold

SHORT_GAME_DELTA_THRESHOLD = 10.0  # percentage points
SHORT_GAME_MIN_SAMPLE = 20         # below this, short-game class is UNCERTAIN regardless of delta

DOMINANT_RECENT_SHARE = 15.0       # percent, recent-period usage share
FILTER_MIN_RECENT_GAMES = CONF_INSUFFICIENT  # meta_prior filtered version excludes < 20 recent games


def wilson_ci(wins, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def confidence_flag(n):
    if n < CONF_INSUFFICIENT:
        return "INSUFFICIENT"
    elif n < CONF_USABLE:
        return "LOW_CONFIDENCE"
    elif n < CONF_HIGH:
        return "USABLE"
    else:
        return "HIGH_CONFIDENCE"


def shrinkage_wr(wins, n, k=SHRINKAGE_K, prior=0.5):
    return (wins + k * prior) / (n + k)


def drift_class(pp_change):
    if pp_change is None:
        return "INSUFFICIENT_DATA"
    if pp_change >= DRIFT_STRONG:
        return "strongly rising"
    if pp_change >= DRIFT_MODERATE:
        return "moderately rising"
    if pp_change <= -DRIFT_STRONG:
        return "strongly declining"
    if pp_change <= -DRIFT_MODERATE:
        return "moderately declining"
    return "stable"


def wr_change_class(pp_change):
    if pp_change is None:
        return "INSUFFICIENT_DATA"
    if pp_change >= WR_CHANGE_MEANINGFUL:
        return "meaningful increase"
    if pp_change <= -WR_CHANGE_MEANINGFUL:
        return "meaningful decrease"
    return "stable"


def parse_composition(comp: str) -> Counter:
    deck = Counter()
    if not isinstance(comp, str) or not comp:
        return deck
    for pair in comp.split(";"):
        if not pair:
            continue
        cid, cnt = pair.split(":")
        deck[int(cid)] = int(cnt)
    return deck


def decklist_to_names(comp: str) -> str:
    deck = parse_composition(comp)
    names = []
    for cid, cnt in sorted(deck.items(), key=lambda kv: name_of(kv[0])):
        names.append(f"{name_of(cid)} x{cnt}")
    return "; ".join(names)


def main():
    df = pd.read_parquet(PARQUET)
    decisive = df[df["outcome_type"] == "DECISIVE"].copy()
    decisive["game_length_f"] = decisive["game_length"].astype(float)
    total_decisive = len(decisive)  # deck-slot / side-row count, 6982

    print(f"Loaded {len(df)} side-rows ({df['episode_id'].nunique()} episodes); "
          f"{total_decisive} decisive deck-slots.")

    short_threshold = decisive["game_length_f"].quantile(0.10)
    print(f"Short-game threshold (10th pct, recomputed from source): {short_threshold:.1f} steps")

    # ================= 1. Deck registry (exact_deck_hash -> archetype) =================
    # Build from BOTH player_* and opponent_* columns so every deck that ever appeared
    # on either side is covered, not just decks that were the "player" side at least once.
    reg_a = df[["player_deck_hash", "player_deck_list", "player_deck_cluster_id", "player_deck_label"]].rename(
        columns={"player_deck_hash": "hash", "player_deck_list": "list",
                 "player_deck_cluster_id": "cluster_id", "player_deck_label": "label"})
    reg_b = df[["opponent_deck_hash", "opponent_deck_list", "opponent_deck_cluster_id", "opponent_deck_label"]].rename(
        columns={"opponent_deck_hash": "hash", "opponent_deck_list": "list",
                 "opponent_deck_cluster_id": "cluster_id", "opponent_deck_label": "label"})
    registry = pd.concat([reg_a, reg_b]).drop_duplicates(subset=["hash"]).set_index("hash")
    print(f"Deck registry: {len(registry)} unique exact decklists.")

    # games-seen per exact deck (decisive, player-side occurrences only, matches deck_stats.csv convention)
    deck_games = decisive.groupby("player_deck_hash").size().to_dict()

    # ================= 2. Archetype names =================
    def archetype_name_for(cluster_id, rep_hash):
        if not cluster_id.startswith("UNLABELED_CLUSTER"):
            return cluster_id
        comp = registry.loc[rep_hash, "list"] if rep_hash in registry.index else ""
        deck = parse_composition(comp)
        sig = deck_signature(deck)
        return " / ".join(sig) if sig else cluster_id

    # representative exact deck per archetype = highest-games-seen deck in that cluster
    cluster_to_hashes = {}
    for h, row in registry.iterrows():
        cluster_to_hashes.setdefault(row["cluster_id"], []).append(h)
    rep_hash_by_cluster = {}
    for cid, hashes in cluster_to_hashes.items():
        rep_hash_by_cluster[cid] = max(hashes, key=lambda h: deck_games.get(h, 0))

    archetype_name_by_cluster = {cid: archetype_name_for(cid, rep_hash_by_cluster[cid])
                                  for cid in cluster_to_hashes}

    # ================= 3. deck_to_archetype.csv =================
    dta_rows = []
    for h, row in registry.iterrows():
        comp = row["list"]
        cid = row["cluster_id"]
        if not isinstance(comp, str) or not comp or not isinstance(cid, str) or not cid:
            dta_rows.append({"exact_deck_hash": h, "exact_deck_list": comp or "",
                              "archetype_id": "UNKNOWN", "archetype_name": "UNKNOWN"})
            continue
        dta_rows.append({
            "exact_deck_hash": h,
            "exact_deck_list": comp,
            "archetype_id": cid,
            "archetype_name": archetype_name_by_cluster.get(cid, cid),
        })
    dta_df = pd.DataFrame(dta_rows).sort_values("exact_deck_hash")
    dta_df.to_csv(os.path.join(OUT_DIR, "deck_to_archetype.csv"), index=False)
    n_unknown = (dta_df["archetype_id"] == "UNKNOWN").sum()
    print(f"Wrote deck_to_archetype.csv: {len(dta_df)} rows, {n_unknown} UNKNOWN.")

    # ================= 4. Archetype base stats (per period) =================
    period_totals = {p: len(decisive[decisive["period"] == p]) for p in ["EARLY", "MIDDLE", "RECENT"]}

    arch_rows = {}
    for cid, g in decisive.groupby("player_deck_cluster_id"):
        n = len(g)
        wins = int((g["result"] == "WIN").sum())
        p, lo, hi = wilson_ci(wins, n)
        exact_count = g["player_deck_hash"].nunique()
        rep_hash = rep_hash_by_cluster.get(cid, g["player_deck_hash"].iloc[0])

        per_period = {}
        for period in ["EARLY", "MIDDLE", "RECENT"]:
            pg = g[g["period"] == period]
            pn = len(pg)
            ptot = period_totals[period]
            pshare = (pn / ptot * 100) if ptot else None
            pwr = (pg["result"] == "WIN").mean() if pn else None
            per_period[period] = {"games": pn, "share": pshare, "win_rate": pwr}

        arch_rows[cid] = {
            "archetype_id": cid,
            "archetype_name": archetype_name_by_cluster.get(cid, cid),
            "representative_deck_hash": rep_hash,
            "representative_deck_list": decklist_to_names(registry.loc[rep_hash, "list"]) if rep_hash in registry.index else "",
            "exact_deck_count": int(exact_count),
            "games": n,
            "wins": wins,
            "losses": n - wins,
            "usage_share": round(n / total_decisive * 100, 4),
            "win_rate": round(p, 4),
            "win_rate_wilson_lo": round(lo, 4),
            "win_rate_wilson_hi": round(hi, 4),
            "shrinkage_win_rate": round(shrinkage_wr(wins, n), 4),
            "confidence": confidence_flag(n),
            "early_games": per_period["EARLY"]["games"],
            "early_share": round(per_period["EARLY"]["share"], 4) if per_period["EARLY"]["share"] is not None else None,
            "early_win_rate": round(per_period["EARLY"]["win_rate"], 4) if per_period["EARLY"]["win_rate"] is not None else None,
            "middle_games": per_period["MIDDLE"]["games"],
            "middle_share": round(per_period["MIDDLE"]["share"], 4) if per_period["MIDDLE"]["share"] is not None else None,
            "middle_win_rate": round(per_period["MIDDLE"]["win_rate"], 4) if per_period["MIDDLE"]["win_rate"] is not None else None,
            "recent_games": per_period["RECENT"]["games"],
            "recent_share": round(per_period["RECENT"]["share"], 4) if per_period["RECENT"]["share"] is not None else None,
            "recent_win_rate": round(per_period["RECENT"]["win_rate"], 4) if per_period["RECENT"]["win_rate"] is not None else None,
        }

    # strength_class: computed after seeing the actual wilson-bound distribution (see report Sec 4/13)
    # STRONG: sample confidence >= USABLE (n>=50) AND wilson_lo > 0.50 (CI clears coin flip)
    # WEAK:   sample confidence >= USABLE (n>=50) AND wilson_hi < 0.50 (CI clears coin flip, below)
    # AVERAGE: sample confidence >= USABLE (n>=50), CI straddles 0.50 (neither STRONG nor WEAK)
    # UNCERTAIN: n < 50 (LOW_CONFIDENCE or INSUFFICIENT) -- sample too small to say anything about strength
    for cid, row in arch_rows.items():
        n = row["games"]
        if n < CONF_USABLE:
            row["strength_class"] = "LOW_SAMPLE_UNCERTAIN"
        elif row["win_rate_wilson_lo"] > 0.50:
            row["strength_class"] = "HIGH_CONFIDENCE_STRONG"
        elif row["win_rate_wilson_hi"] < 0.50:
            row["strength_class"] = "HIGH_CONFIDENCE_WEAK"
        else:
            row["strength_class"] = "HIGH_USAGE_AVERAGE"

    # temporal_change / drift (early -> recent), only where both periods have data
    for cid, row in arch_rows.items():
        if row["early_share"] is not None and row["recent_share"] is not None:
            row["share_change_early_to_recent"] = round(row["recent_share"] - row["early_share"], 4)
        else:
            row["share_change_early_to_recent"] = None
        if row["early_win_rate"] is not None and row["recent_win_rate"] is not None:
            row["win_rate_change_early_to_recent"] = round(
                (row["recent_win_rate"] - row["early_win_rate"]) * 100, 4)
        else:
            row["win_rate_change_early_to_recent"] = None
        row["meta_trend"] = drift_class(row["share_change_early_to_recent"])
        row["win_rate_trend"] = wr_change_class(row["win_rate_change_early_to_recent"])

    # ================= 5. Short-game profile =================
    short = decisive[decisive["game_length_f"] <= short_threshold]
    short_grp = short.groupby("player_deck_cluster_id").agg(
        short_games=("result", "size"),
        short_wins=("result", lambda s: (s == "WIN").sum()),
    )
    for cid, row in arch_rows.items():
        if cid in short_grp.index:
            sg = int(short_grp.loc[cid, "short_games"])
            sw = int(short_grp.loc[cid, "short_wins"])
        else:
            sg, sw = 0, 0
        overall_wr = row["win_rate"]
        if sg >= SHORT_GAME_MIN_SAMPLE:
            swr = sw / sg
            delta_pp = round((swr - overall_wr) * 100, 2)
            if delta_pp >= SHORT_GAME_DELTA_THRESHOLD:
                cls = "short_game_advantaged"
            elif delta_pp <= -SHORT_GAME_DELTA_THRESHOLD:
                cls = "short_game_disadvantaged"
            else:
                cls = "neutral"
            row["short_game_win_rate"] = round(swr, 4)
            row["short_game_delta_pp"] = delta_pp
        else:
            row["short_game_win_rate"] = None
            row["short_game_delta_pp"] = None
            cls = "uncertain"
        row["short_game_sample"] = sg
        row["short_game_class"] = cls

    # ================= 6. Matchups (archetype-level, directional single row per pair) =================
    decisive_recent = decisive[decisive["period"] == "RECENT"]

    def build_pair_stats(frame):
        m = {}
        for (a, b), g in frame.groupby(["player_deck_cluster_id", "opponent_deck_cluster_id"]):
            if a == b:
                continue
            m[(a, b)] = {"games": len(g), "wins": int((g["result"] == "WIN").sum())}
        return m

    m_overall = build_pair_stats(decisive)
    m_recent = build_pair_stats(decisive_recent)

    seen = set()
    matchup_rows = []
    counters_credible = []  # (winner_cid, loser_cid, games, win_rate, wilson_lo)
    for (a, b), s in m_overall.items():
        key = tuple(sorted([a, b]))
        if key in seen:
            continue
        seen.add(key)
        games_a, wins_a = s["games"], s["wins"]
        other = m_overall.get((b, a), {"games": 0, "wins": 0})
        # sanity cross-check: games should match from both perspectives (mirror rows of the same episodes)
        games_mismatch = games_a != other["games"]
        games = games_a  # authoritative count (mirror should be identical)
        wins_a_final = wins_a
        wins_b_final = games - wins_a_final  # guarantees wins_A + wins_B == games exactly (no draws in decisive)

        # canonical ordering: A = archetype with more overall games (ties: alphabetical)
        games_A_total = arch_rows[a]["games"]
        games_B_total = arch_rows[b]["games"]
        if (games_A_total, a) >= (games_B_total, b):
            A, B = a, b
            wA, wB = wins_a_final, wins_b_final
        else:
            A, B = b, a
            wA, wB = wins_b_final, wins_a_final

        p_a, lo_a, hi_a = wilson_ci(wA, games)
        p_b = wB / games if games else 0.0
        conf = confidence_flag(games)

        rs = m_recent.get((A, B), {"games": 0, "wins": 0})
        rs_other = m_recent.get((B, A), {"games": 0, "wins": 0})
        games_recent = rs["games"]
        wins_A_recent = rs["wins"]
        if games_recent == 0 and rs_other["games"] > 0:
            games_recent = rs_other["games"]
            wins_A_recent = games_recent - rs_other["wins"]
        wr_A_recent = round(wins_A_recent / games_recent, 4) if games_recent else None
        conf_recent = confidence_flag(games_recent)

        credible_A_over_B = games >= COUNTER_MIN_GAMES and lo_a > COUNTER_WILSON_LO_MIN
        credible_B_over_A = games >= COUNTER_MIN_GAMES and (1 - p_a) > COUNTER_WILSON_LO_MIN and (
            wilson_ci(wB, games)[1] > COUNTER_WILSON_LO_MIN)

        if credible_A_over_B:
            counters_credible.append((A, B, games, p_a, lo_a))
        if credible_B_over_A:
            _, lo_b, _ = wilson_ci(wB, games)
            counters_credible.append((B, A, games, p_b, lo_b))

        matchup_rows.append({
            "archetype_A": A, "archetype_B": B,
            "games": games, "wins_A": wA, "wins_B": wB,
            "win_rate_A": round(p_a, 4), "win_rate_B": round(p_b, 4),
            "win_rate_A_wilson_lo": round(lo_a, 4), "win_rate_A_wilson_hi": round(hi_a, 4),
            "sample_confidence": conf,
            "games_recent": games_recent, "win_rate_A_recent": wr_A_recent,
            "sample_confidence_recent": conf_recent,
            "credible_counter_A_over_B": credible_A_over_B,
            "credible_counter_B_over_A": credible_B_over_A,
            "games_mismatch_flag": games_mismatch,
        })

    matchup_df = pd.DataFrame(matchup_rows).sort_values("games", ascending=False)
    matchup_df.to_csv(os.path.join(OUT_DIR, "archetype_matchups.csv"), index=False)
    n_mismatch = matchup_df["games_mismatch_flag"].sum()
    print(f"Wrote archetype_matchups.csv: {len(matchup_df)} unordered pairs "
          f"({(matchup_df.sample_confidence=='HIGH_CONFIDENCE').sum()} HIGH_CONFIDENCE, "
          f"{(matchup_df.sample_confidence=='USABLE').sum()} USABLE, "
          f"{(matchup_df.sample_confidence=='LOW_CONFIDENCE').sum()} LOW_CONFIDENCE, "
          f"{(matchup_df.sample_confidence=='INSUFFICIENT').sum()} INSUFFICIENT); "
          f"games-mirror mismatches: {n_mismatch}")

    # counter_targets / countered_by per archetype
    counter_targets = {}
    countered_by = {}
    for winner, loser, games, wr, lo in counters_credible:
        counter_targets.setdefault(winner, []).append(
            {"opponent_archetype_id": loser, "games": games, "win_rate": round(wr, 4), "wilson_lo": round(lo, 4)})
        countered_by.setdefault(loser, []).append(
            {"opponent_archetype_id": winner, "games": games, "win_rate": round(wr, 4), "wilson_lo": round(lo, 4)})

    for cid, row in arch_rows.items():
        row["credible_counter_count"] = len(counter_targets.get(cid, []))
        row["credible_countered_by_count"] = len(countered_by.get(cid, []))

    # ================= 7. Recent-meta tags (Sec 11, non-exclusive tags) =================
    dominant_ids = set()
    for cid, row in arch_rows.items():
        rc = row["recent_games"]
        tags = []
        if confidence_flag(rc) in ("USABLE", "HIGH_CONFIDENCE") and (row["recent_share"] or 0) >= DOMINANT_RECENT_SHARE:
            tags.append("CURRENT_DOMINANT")
            dominant_ids.add(cid)
        arch_rows[cid]["_tags_pending_dominant"] = tags  # finalize counter tag after dominant set is known

    for cid, row in arch_rows.items():
        tags = row["_tags_pending_dominant"]
        rc = row["recent_games"]
        sc = row["share_change_early_to_recent"]
        if confidence_flag(rc) != "INSUFFICIENT":
            if sc is not None and sc >= DRIFT_MODERATE:
                tags.append("CURRENT_RISING")
            if sc is not None and sc <= -DRIFT_MODERATE:
                tags.append("CURRENT_DECLINING")
        # CURRENT_COUNTER: credibly counters a CURRENT_DOMINANT archetype, prefer recent-period evidence
        counters_a_dominant = False
        for tgt in counter_targets.get(cid, []):
            if tgt["opponent_archetype_id"] in dominant_ids:
                counters_a_dominant = True
                break
        if counters_a_dominant:
            tags.append("CURRENT_COUNTER")
        if confidence_flag(rc) == "INSUFFICIENT":
            tags.append("CURRENT_UNCERTAIN")
        row["meta_tags"] = ";".join(tags)
        del row["_tags_pending_dominant"]

    # ================= 8. Write archetype_features.csv =================
    feat_cols = [
        "archetype_id", "archetype_name", "games", "exact_deck_count", "usage_share",
        "win_rate", "win_rate_wilson_lo", "win_rate_wilson_hi", "shrinkage_win_rate", "confidence",
        "strength_class", "early_share", "middle_share", "recent_share",
        "early_win_rate", "middle_win_rate", "recent_win_rate", "recent_games",
        "share_change_early_to_recent", "win_rate_change_early_to_recent", "meta_trend", "win_rate_trend",
        "short_game_win_rate", "short_game_delta_pp", "short_game_sample", "short_game_class",
        "credible_counter_count", "credible_countered_by_count", "meta_tags",
    ]
    feat_rows = [{c: arch_rows[cid].get(c) for c in feat_cols} for cid in arch_rows]
    feat_df = pd.DataFrame(feat_rows).sort_values("games", ascending=False)
    feat_df.to_csv(os.path.join(OUT_DIR, "archetype_features.csv"), index=False)
    print(f"Wrote archetype_features.csv: {len(feat_df)} archetypes.")

    # also write full canonical representation (Sec 4 required fields) as a companion file
    canon_cols = ["archetype_id", "archetype_name", "representative_deck_hash", "representative_deck_list",
                  "exact_deck_count", "games", "usage_share", "wins", "losses", "win_rate",
                  "early_share", "middle_share", "recent_share", "early_win_rate", "middle_win_rate", "recent_win_rate"]
    canon_rows = [{c: arch_rows[cid].get(c) for c in canon_cols} for cid in arch_rows]
    canon_df = pd.DataFrame(canon_rows).sort_values("games", ascending=False)
    canon_df.to_csv(os.path.join(OUT_DIR, "archetype_canonical.csv"), index=False)
    print(f"Wrote archetype_canonical.csv: {len(canon_df)} archetypes.")

    # ================= 9. meta_prior.csv (RECENT period only) =================
    recent_total = period_totals["RECENT"]
    prior_rows = []
    sum_raw = sum(row["recent_games"] for row in arch_rows.values())
    for cid, row in arch_rows.items():
        rg = row["recent_games"]
        prior_raw = rg / sum_raw if sum_raw else 0.0
        included = rg >= FILTER_MIN_RECENT_GAMES
        prior_rows.append({
            "archetype_id": cid,
            "archetype_name": row["archetype_name"],
            "recent_games": rg,
            "recent_share_of_period": row["recent_share"],
            "prior_raw": round(prior_raw, 6),
            "included_in_filtered": included,
        })
    prior_df = pd.DataFrame(prior_rows)
    included_sum = prior_df.loc[prior_df["included_in_filtered"], "recent_games"].sum()
    prior_df["prior_filtered"] = prior_df.apply(
        lambda r: round(r["recent_games"] / included_sum, 6) if r["included_in_filtered"] and included_sum else 0.0,
        axis=1)
    prior_df = prior_df.sort_values("recent_games", ascending=False)
    prior_df.to_csv(os.path.join(OUT_DIR, "meta_prior.csv"), index=False)
    print(f"Wrote meta_prior.csv: {len(prior_df)} rows, sum(prior_raw)={prior_df['prior_raw'].sum():.6f}, "
          f"sum(prior_filtered)={prior_df['prior_filtered'].sum():.6f} over "
          f"{int(prior_df['included_in_filtered'].sum())} included archetypes "
          f"(recent_total deck-slots={recent_total}, sum recent_games={sum_raw})")

    # ================= 10. meta_graph.json =================
    nodes = []
    for cid, row in arch_rows.items():
        nodes.append({
            "id": cid, "name": row["archetype_name"],
            "usage_share": row["usage_share"], "recent_share": row["recent_share"],
            "win_rate": row["win_rate"], "recent_win_rate": row["recent_win_rate"],
            "game_count": row["games"], "confidence": row["confidence"],
            "strength_class": row["strength_class"], "meta_tags": row["meta_tags"].split(";") if row["meta_tags"] else [],
        })
    edges = []
    for _, r in matchup_df.iterrows():
        edges.append({
            "source": r["archetype_A"], "target": r["archetype_B"],
            "games": int(r["games"]),
            "win_rate_source_over_target": r["win_rate_A"],
            "win_rate_target_over_source": r["win_rate_B"],
            "confidence": r["sample_confidence"],
            "games_recent": int(r["games_recent"]),
            "win_rate_source_over_target_recent": r["win_rate_A_recent"],
            "confidence_recent": r["sample_confidence_recent"],
            "credible_counter_source_over_target": bool(r["credible_counter_A_over_B"]),
            "credible_counter_target_over_source": bool(r["credible_counter_B_over_A"]),
        })

    # simple, interpretable, non-composite graph metrics (Sec 10): degree = # observed
    # opponents at all, credible_degree = # credible-counter edges touching this node
    degree = {cid: 0 for cid in arch_rows}
    credible_degree = {cid: 0 for cid in arch_rows}
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
        if e["credible_counter_source_over_target"] or e["credible_counter_target_over_source"]:
            credible_degree[e["source"]] += 1
            credible_degree[e["target"]] += 1
    for n in nodes:
        n["observed_opponent_degree"] = degree[n["id"]]
        n["credible_matchup_degree"] = credible_degree[n["id"]]

    graph = {
        "generated_from": "results/meta/episodes_summary.parquet (3,499 episodes, 6,982 decisive deck-slots)",
        "node_count": len(nodes), "edge_count": len(edges),
        "confidence_thresholds": {"INSUFFICIENT": f"<{CONF_INSUFFICIENT}", "LOW_CONFIDENCE": f"{CONF_INSUFFICIENT}-{CONF_USABLE-1}",
                                   "USABLE": f"{CONF_USABLE}-{CONF_HIGH-1}", "HIGH_CONFIDENCE": f">={CONF_HIGH}"},
        "nodes": nodes, "edges": edges,
    }
    with open(os.path.join(OUT_DIR, "meta_graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    isolated = sum(1 for n in nodes if n["observed_opponent_degree"] == 0)
    print(f"Wrote meta_graph.json: {len(nodes)} nodes, {len(edges)} edges, {isolated} isolated nodes (0 observed opponents).")

    # ================= 11. opponent_archetypes.json =================
    matchup_vector_by_cid = {cid: [] for cid in arch_rows}
    for _, r in matchup_df.iterrows():
        A, B = r["archetype_A"], r["archetype_B"]
        matchup_vector_by_cid[A].append({
            "opponent_archetype_id": B, "games": int(r["games"]), "win_rate": r["win_rate_A"],
            "wilson_lo": r["win_rate_A_wilson_lo"], "wilson_hi": r["win_rate_A_wilson_hi"],
            "confidence": r["sample_confidence"], "games_recent": int(r["games_recent"]),
            "win_rate_recent": r["win_rate_A_recent"], "confidence_recent": r["sample_confidence_recent"],
            "credible_counter": bool(r["credible_counter_A_over_B"]),
        })
        matchup_vector_by_cid[B].append({
            "opponent_archetype_id": A, "games": int(r["games"]), "win_rate": r["win_rate_B"],
            "wilson_lo": round(1 - r["win_rate_A_wilson_hi"], 4), "wilson_hi": round(1 - r["win_rate_A_wilson_lo"], 4),
            "confidence": r["sample_confidence"], "games_recent": int(r["games_recent"]),
            "win_rate_recent": round(1 - r["win_rate_A_recent"], 4) if r["win_rate_A_recent"] is not None else None,
            "confidence_recent": r["sample_confidence_recent"],
            "credible_counter": bool(r["credible_counter_B_over_A"]),
        })

    prior_by_cid = {r["archetype_id"]: r["prior_raw"] for r in prior_rows}

    profiles = {}
    for cid, row in arch_rows.items():
        profiles[cid] = {
            "identity": {
                "archetype_id": cid, "archetype_name": row["archetype_name"],
                "representative_deck_hash": row["representative_deck_hash"],
                "exact_deck_count": row["exact_deck_count"],
            },
            "popularity": {
                "usage_share": row["usage_share"], "games": row["games"],
                "recent_share": row["recent_share"], "recent_games": row["recent_games"],
            },
            "strength": {
                "win_rate": row["win_rate"], "wilson_lo": row["win_rate_wilson_lo"],
                "wilson_hi": row["win_rate_wilson_hi"], "shrinkage_win_rate": row["shrinkage_win_rate"],
                "strength_class": row["strength_class"], "confidence": row["confidence"],
            },
            "recent_strength": {
                "recent_win_rate": row["recent_win_rate"],
                "recent_confidence": confidence_flag(row["recent_games"]),
            },
            "trend": {
                "share_change_early_to_recent_pp": row["share_change_early_to_recent"],
                "win_rate_change_early_to_recent_pp": row["win_rate_change_early_to_recent"],
                "meta_trend_class": row["meta_trend"], "win_rate_trend_class": row["win_rate_trend"],
                "meta_tags": row["meta_tags"].split(";") if row["meta_tags"] else [],
            },
            "matchup_vector": matchup_vector_by_cid[cid],
            "counter_targets": counter_targets.get(cid, []),
            "countered_by": countered_by.get(cid, []),
            "short_game_profile": {
                "short_game_win_rate": row["short_game_win_rate"], "short_game_delta_pp": row["short_game_delta_pp"],
                "short_game_sample": row["short_game_sample"], "short_game_class": row["short_game_class"],
            },
            "uncertainty": {
                "overall_confidence": row["confidence"],
                "recent_confidence": confidence_flag(row["recent_games"]),
                "notes": "rating is NOT used anywhere in this profile (Phase 4.1 found it structurally "
                         "unresolvable from this data source); win_rate/strength reflect raw outcome rates only.",
            },
        }

    opponent_doc = {
        "generated_from": "results/meta/episodes_summary.parquet (3,499 episodes, Phase 4.1 canonical dataset)",
        "rating_used": False,
        "confidence_thresholds": {"INSUFFICIENT": f"<{CONF_INSUFFICIENT}", "LOW_CONFIDENCE": f"{CONF_INSUFFICIENT}-{CONF_USABLE-1}",
                                   "USABLE": f"{CONF_USABLE}-{CONF_HIGH-1}", "HIGH_CONFIDENCE": f">={CONF_HIGH}"},
        "shrinkage_k": SHRINKAGE_K,
        "short_game_threshold_steps": short_threshold,
        "counter_credibility_rule": f"games >= {COUNTER_MIN_GAMES} AND wilson_lo(win_rate) > {COUNTER_WILSON_LO_MIN}",
        "meta_prior_recent": prior_by_cid,
        "interface_schema": {
            "OpponentState": {
                "observed_deck": "list[card_id] or partial observation of opponent's played cards",
                "inferred_archetype": "archetype_id (str) -- NOT implemented this phase, future inference target",
                "archetype_confidence": "float or category -- NOT implemented this phase",
                "meta_prior": "dict[archetype_id -> float], see meta_prior_recent above (RECENT-period prior)",
                "matchup_vector": "list of {opponent_archetype_id, win_rate, confidence} for the player's own deck, see profiles[*].matchup_vector",
                "temporal_context": "which period (EARLY/MIDDLE/RECENT) the current game should be treated as, for selecting the right prior",
            },
        },
        "profiles": profiles,
    }
    with open(os.path.join(OUT_DIR, "opponent_archetypes.json"), "w", encoding="utf-8") as f:
        json.dump(opponent_doc, f, indent=2)
    print(f"Wrote opponent_archetypes.json: {len(profiles)} profiles.")

    # ================= 12. Validation =================
    print("\n" + "=" * 70 + "\nVALIDATION")
    sum_arch_games = sum(row["games"] for row in arch_rows.values())
    print(f"sum(archetype games)={sum_arch_games} vs total decisive deck-slots={total_decisive} "
          f"-> {'OK' if sum_arch_games == total_decisive else 'MISMATCH'}")

    prior_sum = prior_df["prior_raw"].sum()
    print(f"sum(meta_prior.prior_raw)={prior_sum:.6f} -> {'OK' if abs(prior_sum-1.0) < 1e-6 else 'MISMATCH'}")
    filt_sum = prior_df["prior_filtered"].sum()
    print(f"sum(meta_prior.prior_filtered over included)={filt_sum:.6f} -> {'OK' if abs(filt_sum-1.0) < 1e-6 else 'MISMATCH'}")

    bad_matchups = matchup_df[(matchup_df["wins_A"] + matchup_df["wins_B"]) != matchup_df["games"]]
    print(f"matchup rows where wins_A+wins_B != games: {len(bad_matchups)} -> {'OK' if len(bad_matchups)==0 else 'MISMATCH'}")
    print(f"matchup rows with games-mirror cross-check mismatch (informational only): {n_mismatch}")

    dup_map = dta_df.groupby("exact_deck_hash").size()
    print(f"deck_to_archetype hashes mapped to >1 row: {(dup_map>1).sum()} -> "
          f"{'OK' if (dup_map>1).sum()==0 else 'MISMATCH'}")
    print(f"deck_to_archetype UNKNOWN count: {n_unknown}")

    print("\nDONE.")


if __name__ == "__main__":
    main()
