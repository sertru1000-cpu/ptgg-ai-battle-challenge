"""Full Part 4.1 analysis over the combined meta-v2 dataset (pilot main-sample +
meta-v2 scale-up). Reads:
  strategy/meta_analysis/meta_v2_combined_episodes.csv
  strategy/meta_analysis/meta_v2_combined_deck_registry.csv   (has cluster_id)

Writes:
  results/meta/deck_stats.csv        one row per exact deck_hash
  results/meta/matchup_matrix.csv    archetype/cluster x archetype/cluster
  results/meta/deck_variants.csv     one row per exact deck within top archetypes
  results/meta/rating_analysis.csv   one row per archetype/cluster (INFERRED rating fields)

Also prints a full plain-text summary (analysis_out_v2.txt) used to write
reports/real_meta_v2.md -- every number in that report should be traceable to this
output, not hand-typed.
"""
import csv
import math
import os
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.meta_analysis.card_lookup import name_of
from src.meta_analysis.rating_resolution import (
    resolve_ratings, fit_1d_logistic, fit_label_intercept, _sigmoid,
)

EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_combined_episodes.csv")
DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "meta_v2_combined_deck_registry.csv")
OUT_DIR = os.path.join(REPO_ROOT, "results", "meta")
TXT_OUT = os.path.join(REPO_ROOT, "results", "meta", "analysis_out_v2.txt")

LOW_N = 30  # threshold below which a cell/deck/archetype gets a LOW-N flag


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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = Tee(TXT_OUT)

    with open(EPISODES, encoding="utf-8", newline="") as f:
        episodes = list(csv.DictReader(f))
    with open(DECKS, encoding="utf-8", newline="") as f:
        decks = {r["deck_hash"]: r for r in csv.DictReader(f)}

    decisive = [e for e in episodes if e["outcome_type"] == "DECISIVE"]
    draws = [e for e in episodes if e["outcome_type"] == "DRAW"]
    errors = [e for e in episodes if e["outcome_type"] == "ERROR_OR_TIMEOUT"]

    out.p("=" * 78)
    out.p(f"COMBINED DATASET: {len(episodes)} episodes "
          f"(decisive={len(decisive)}, draw={len(draws)}, error/timeout={len(errors)})")
    out.p(f"Unique exact decks: {len(decks)}")
    by_period = Counter(e["period"] for e in episodes)
    out.p("By period:", dict(by_period))

    # ================= RATING RESOLUTION (INFERRED) =================
    out.p("\n" + "=" * 78)
    out.p("RATING RESOLUTION (deck-based alternating-assignment EM; see "
          "src/meta_analysis/rating_resolution.py for method)")
    with_scores = [e for e in decisive if e.get("min_score") not in (None, "")]
    resolved, deck_rating_est = resolve_ratings(with_scores)
    out.p(f"Decisive episodes with score data: {len(with_scores)}/{len(decisive)}")
    n_conf = sum(1 for i, (r0, r1, c) in resolved.items() if c)
    out.p(f"'Confident' assignments (cost-gap heuristic): {n_conf}/{len(resolved)}")

    higher_wins, total_pairs = 0, 0
    for i, e in enumerate(with_scores):
        if i not in resolved:
            continue
        r0, r1, conf = resolved[i]
        if r0 == r1:
            continue
        total_pairs += 1
        winner = e["winner"]
        if winner in ("", None):
            continue
        higher_side = 0 if r0 > r1 else 1
        if int(winner) == higher_side:
            higher_wins += 1
    val_p, val_lo, val_hi = wilson_ci(higher_wins, total_pairs)
    out.p(f"VALIDATION CHECK: higher-assigned-rating side win rate = {higher_wins}/{total_pairs} "
          f"= {val_p:.3f} [{val_lo:.3f},{val_hi:.3f}] (should be well above 0.5 if resolution "
          f"is recovering real rating information; near 0.5 means NOT reliably resolved)")

    # pooled logistic: win ~ sigmoid(a + b*rating_diff), b = global slope
    xs, ys = [], []
    for i, e in enumerate(with_scores):
        if i not in resolved:
            continue
        r0, r1, conf = resolved[i]
        winner = e["winner"]
        if winner in ("", None):
            continue
        xs.append(r0 - r1); ys.append(1 if int(winner) == 0 else 0)
        xs.append(r1 - r0); ys.append(1 if int(winner) == 1 else 0)
    a_pooled, beta = fit_1d_logistic(xs, ys)
    out.p(f"Pooled logistic fit: intercept={a_pooled:.5f} beta(rating_diff slope)={beta:.6f}")
    out.p(f"  Implied P(win) at rating_diff=0: {_sigmoid(a_pooled):.3f}")
    out.p(f"  Implied P(win) at rating_diff=+100: {_sigmoid(a_pooled + beta*100):.3f}")
    out.p(f"  Implied P(win) at rating_diff=-100: {_sigmoid(a_pooled + beta*-100):.3f}")

    # per-episode-per-side own/opp rating lookup for deck_stats
    ep_rating = {}  # index -> (r0, r1) or None
    for i in range(len(with_scores)):
        if i in resolved:
            r0, r1, conf = resolved[i]
            ep_rating[with_scores[i]["episode_id"]] = (r0, r1, conf)

    # ================= EXACT-DECK STATS =================
    deck_games = defaultdict(lambda: {"decisive": 0, "wins": 0, "fp_games": 0, "fp_wins": 0,
                                       "sp_games": 0, "sp_wins": 0, "steps": [],
                                       "own_ratings": [], "opp_ratings": [],
                                       "draws": 0, "errors": 0, "recent_games": 0})
    total_deck_slots_decisive = 0
    for e in decisive:
        total_deck_slots_decisive += 2
        for side, hkey in ((0, "deck0_hash"), (1, "deck1_hash")):
            h = e[hkey]
            if not h:
                continue
            d = deck_games[h]
            d["decisive"] += 1
            won = e["winner"] not in ("", None) and int(e["winner"]) == side
            if won:
                d["wins"] += 1
            fp = e.get("first_player")
            if fp not in ("", None):
                if int(fp) == side:
                    d["fp_games"] += 1
                    if won:
                        d["fp_wins"] += 1
                else:
                    d["sp_games"] += 1
                    if won:
                        d["sp_wins"] += 1
            d["steps"].append(int(e["n_steps"]))
            if e["period"] == "RECENT":
                d["recent_games"] += 1
            rr = ep_rating.get(e["episode_id"])
            if rr:
                r0, r1, conf = rr
                own, opp = (r0, r1) if side == 0 else (r1, r0)
                d["own_ratings"].append(own)
                d["opp_ratings"].append(opp)
    for e in draws:
        for hkey in ("deck0_hash", "deck1_hash"):
            h = e[hkey]
            if h:
                deck_games[h]["draws"] += 1
    for e in errors:
        for hkey in ("deck0_hash", "deck1_hash"):
            h = e[hkey]
            if h:
                deck_games[h]["errors"] += 1

    deck_rows = []
    for h, d in deck_games.items():
        meta = decks.get(h, {})
        games = d["decisive"]
        wr = d["wins"] / games if games else 0
        fp_wr = d["fp_wins"] / d["fp_games"] if d["fp_games"] else None
        sp_wr = d["sp_wins"] / d["sp_games"] if d["sp_games"] else None
        avg_steps = sum(d["steps"]) / len(d["steps"]) if d["steps"] else None
        avg_own = sum(d["own_ratings"]) / len(d["own_ratings"]) if d["own_ratings"] else None
        avg_opp = sum(d["opp_ratings"]) / len(d["opp_ratings"]) if d["opp_ratings"] else None
        deck_rows.append({
            "deck_hash": h, "label": meta.get("label", "UNLABELED"),
            "cluster_id": meta.get("cluster_id", "UNLABELED"),
            "games_decisive": games,
            "usage_share_pct": round(games / total_deck_slots_decisive * 100, 3) if total_deck_slots_decisive else 0,
            "wins": d["wins"], "losses": games - d["wins"], "draws": d["draws"], "errors": d["errors"],
            "raw_win_rate": round(wr, 4),
            "first_player_win_rate": round(fp_wr, 4) if fp_wr is not None else "",
            "first_player_games": d["fp_games"],
            "second_player_win_rate": round(sp_wr, 4) if sp_wr is not None else "",
            "second_player_games": d["sp_games"],
            "avg_own_rating_inferred": round(avg_own, 1) if avg_own is not None else "",
            "avg_opp_rating_inferred": round(avg_opp, 1) if avg_opp is not None else "",
            "avg_game_length_steps": round(avg_steps, 1) if avg_steps is not None else "",
            "recent_games": d["recent_games"],
            "low_n_flag": games < LOW_N,
        })
    deck_rows.sort(key=lambda r: -r["games_decisive"])
    with open(os.path.join(OUT_DIR, "deck_stats.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(deck_rows[0].keys()))
        w.writeheader()
        w.writerows(deck_rows)
    out.p("\n" + "=" * 78)
    out.p(f"Wrote deck_stats.csv: {len(deck_rows)} exact decks")
    out.p("\nTOP 25 EXACT DECKS BY GAME COUNT:")
    out.p(f"{'hash':17} {'label':26} {'games':>6} {'usage%':>7} {'winrate':>8} {'fp_wr':>7} {'sp_wr':>7}")
    for r in deck_rows[:25]:
        out.p(f"{r['deck_hash']:17} {r['label'][:26]:26} {r['games_decisive']:6d} "
              f"{r['usage_share_pct']:7.2f} {r['raw_win_rate']:8.3f} "
              f"{r['first_player_win_rate'] if r['first_player_win_rate']!='' else float('nan'):7.3f} "
              f"{r['second_player_win_rate'] if r['second_player_win_rate']!='' else float('nan'):7.3f}")

    # ================= ARCHETYPE / CLUSTER LEVEL =================
    label_stats = defaultdict(lambda: {"games": 0, "wins": 0, "n_decks": set(), "steps": [],
                                        "own_ratings": [], "opp_ratings": [], "recent_games": 0,
                                        "early_games": 0, "middle_games": 0})
    for e in decisive:
        for side, hkey in ((0, "deck0_hash"), (1, "deck1_hash")):
            h = e[hkey]
            if not h:
                continue
            cid = decks.get(h, {}).get("cluster_id", "UNLABELED")
            s = label_stats[cid]
            s["games"] += 1
            s["n_decks"].add(h)
            if e["winner"] not in ("", None) and int(e["winner"]) == side:
                s["wins"] += 1
            s["steps"].append(int(e["n_steps"]))
            if e["period"] == "RECENT":
                s["recent_games"] += 1
            elif e["period"] == "EARLY":
                s["early_games"] += 1
            else:
                s["middle_games"] += 1
            rr = ep_rating.get(e["episode_id"])
            if rr:
                r0, r1, conf = rr
                own, opp = (r0, r1) if side == 0 else (r1, r0)
                s["own_ratings"].append(own)
                s["opp_ratings"].append(opp)

    total_slots = sum(s["games"] for s in label_stats.values())

    # per-archetype rating-adjusted intercept (partial-pooled logistic, beta fixed from pooled fit)
    label_xy = defaultdict(lambda: ([], []))
    for i, e in enumerate(with_scores):
        if i not in resolved or e["winner"] in ("", None):
            continue
        r0, r1, conf = resolved[i]
        for side, hkey in ((0, "deck0_hash"), (1, "deck1_hash")):
            h = e[hkey]
            if not h:
                continue
            cid = decks.get(h, {}).get("cluster_id", "UNLABELED")
            own, opp = (r0, r1) if side == 0 else (r1, r0)
            y = 1 if int(e["winner"]) == side else 0
            label_xy[cid][0].append(own - opp)
            label_xy[cid][1].append(y)

    out.p("\n" + "=" * 78)
    out.p("ARCHETYPE/CLUSTER-LEVEL FREQUENCY + WIN RATE (DECISIVE games, both sides pooled)")
    out.p(f"{'label':30} {'games':>6} {'decks':>6} {'usage%':>7} {'raw_wr':>7} "
          f"{'wilson_lo':>9} {'wilson_hi':>9} {'adj_wr':>7} {'avg_own':>8} {'avg_opp':>8}")
    rating_rows = []
    ranked_labels = sorted(label_stats.items(), key=lambda kv: -kv[1]["games"])
    for label, s in ranked_labels:
        p, lo, hi = wilson_ci(s["wins"], s["games"])
        usage = s["games"] / total_slots * 100 if total_slots else 0
        avg_own = sum(s["own_ratings"]) / len(s["own_ratings"]) if s["own_ratings"] else None
        avg_opp = sum(s["opp_ratings"]) / len(s["opp_ratings"]) if s["opp_ratings"] else None
        xs_l, ys_l = label_xy.get(label, ([], []))
        adj_wr = None
        if len(xs_l) >= LOW_N:
            alpha = fit_label_intercept(xs_l, ys_l, beta)
            if alpha is not None:
                adj_wr = _sigmoid(alpha)
        low_n = s["games"] < LOW_N
        out.p(f"{label[:30]:30} {s['games']:6d} {len(s['n_decks']):6d} {usage:7.2f} {p:7.3f} "
              f"{lo:9.3f} {hi:9.3f} "
              f"{(adj_wr if adj_wr is not None else float('nan')):7.3f} "
              f"{(avg_own if avg_own is not None else float('nan')):8.1f} "
              f"{(avg_opp if avg_opp is not None else float('nan')):8.1f}"
              f"{'  [LOW-N]' if low_n else ''}")
        rating_rows.append({
            "cluster_id": label, "games_decisive": s["games"], "n_exact_decks": len(s["n_decks"]),
            "usage_share_pct": round(usage, 3), "raw_win_rate": round(p, 4),
            "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
            "rating_adjusted_win_prob": round(adj_wr, 4) if adj_wr is not None else "",
            "avg_own_rating_inferred": round(avg_own, 1) if avg_own is not None else "",
            "avg_opp_rating_inferred": round(avg_opp, 1) if avg_opp is not None else "",
            "n_resolved_episodes": len(xs_l),
            "early_games": s["early_games"], "middle_games": s["middle_games"], "recent_games": s["recent_games"],
            "low_n_flag": low_n,
        })
    with open(os.path.join(OUT_DIR, "rating_analysis.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rating_rows[0].keys()))
        w.writeheader()
        w.writerows(rating_rows)
    out.p(f"\nWrote rating_analysis.csv: {len(rating_rows)} archetypes/clusters")

    # ================= TEMPORAL: EARLY/MIDDLE/RECENT SHARE =================
    out.p("\n" + "=" * 78)
    out.p("TEMPORAL: archetype/cluster share of games by period (ALL episodes incl. non-decisive, both sides)")
    period_label_games = defaultdict(lambda: defaultdict(int))
    period_totals = defaultdict(int)
    for e in episodes:
        for hkey in ("deck0_hash", "deck1_hash"):
            h = e[hkey]
            cid = decks.get(h, {}).get("cluster_id", "UNLABELED") if h else "UNLABELED"
            period_label_games[e["period"]][cid] += 1
            period_totals[e["period"]] += 1
    for p in ["EARLY", "MIDDLE", "RECENT"]:
        out.p(f"\n  {p} (n={period_totals[p]} deck-slots):")
        top = sorted(period_label_games[p].items(), key=lambda kv: -kv[1])[:15]
        for label, cnt in top:
            out.p(f"    {label[:32]:32} {cnt:6d}  ({cnt/period_totals[p]*100:.1f}%)")

    # ================= MATCHUP MATRIX (cluster_id x cluster_id) =================
    out.p("\n" + "=" * 78)
    out.p("MATCHUP MATRIX (cluster_id vs cluster_id, DECISIVE games)")
    matchup = defaultdict(lambda: {"games": 0, "wins_row": 0, "rating_diffs": []})
    for i, e in enumerate(decisive):
        l0 = decks.get(e["deck0_hash"], {}).get("cluster_id", "UNLABELED")
        l1 = decks.get(e["deck1_hash"], {}).get("cluster_id", "UNLABELED")
        w = e["winner"]
        rr = ep_rating.get(e["episode_id"])
        for (row, col, row_side) in [(l0, l1, 0), (l1, l0, 1)]:
            m = matchup[(row, col)]
            m["games"] += 1
            if w not in ("", None) and int(w) == row_side:
                m["wins_row"] += 1
            if rr:
                r0, r1, conf = rr
                own, opp = (r0, r1) if row_side == 0 else (r1, r0)
                m["rating_diffs"].append(own - opp)

    matchup_rows = []
    labels_seen = sorted(set(k[0] for k in matchup) | set(k[1] for k in matchup))
    for l0 in labels_seen:
        for l1 in labels_seen:
            if l0 >= l1:
                continue
            m = matchup.get((l0, l1))
            if not m or m["games"] == 0:
                continue
            p, lo, hi = wilson_ci(m["wins_row"], m["games"])
            avg_rd = sum(m["rating_diffs"]) / len(m["rating_diffs"]) if m["rating_diffs"] else None
            low_n = m["games"] < LOW_N
            matchup_rows.append({
                "row_label": l0, "col_label": l1, "games": m["games"], "wins_row": m["wins_row"],
                "losses_row": m["games"] - m["wins_row"], "row_win_rate": round(p, 4),
                "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
                "avg_rating_diff_row_minus_col_inferred": round(avg_rd, 1) if avg_rd is not None else "",
                "low_n_flag": low_n,
            })
    matchup_rows.sort(key=lambda r: -r["games"])
    with open(os.path.join(OUT_DIR, "matchup_matrix.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(matchup_rows[0].keys()))
        w.writeheader()
        w.writerows(matchup_rows)
    out.p(f"Wrote matchup_matrix.csv: {len(matchup_rows)} pairs")
    n_adequate = sum(1 for r in matchup_rows if not r["low_n_flag"])
    out.p(f"Pairs with n>={LOW_N} (not LOW-N): {n_adequate}/{len(matchup_rows)}")
    out.p("\nTop 25 highest-n matchup cells:")
    for r in matchup_rows[:25]:
        flag = "  [LOW-N]" if r["low_n_flag"] else ""
        out.p(f"  {r['row_label'][:26]} vs {r['col_label'][:26]}: n={r['games']} "
              f"row_wr={r['row_win_rate']:.3f} [{r['wilson_lo']:.3f},{r['wilson_hi']:.3f}]{flag}")
    out.p("\nMost lopsided ADEQUATE-N (>=30) matchup cells (row win rate farthest from 0.5):")
    adequate = [r for r in matchup_rows if not r["low_n_flag"]]
    adequate.sort(key=lambda r: -abs(r["row_win_rate"] - 0.5))
    for r in adequate[:15]:
        out.p(f"  {r['row_label'][:26]} vs {r['col_label'][:26]}: n={r['games']} "
              f"row_wr={r['row_win_rate']:.3f} [{r['wilson_lo']:.3f},{r['wilson_hi']:.3f}]")

    # ================= DECK VARIATION within top archetypes =================
    out.p("\n" + "=" * 78)
    out.p("DECK VARIATION within top archetypes/clusters")
    cluster_to_hashes = defaultdict(list)
    for h, d in decks.items():
        cluster_to_hashes[d.get("cluster_id", "UNLABELED")].append(d)

    variant_rows = []
    top_clusters = [l for l, s in ranked_labels if s["games"] >= LOW_N][:20]
    for label in top_clusters:
        variants = cluster_to_hashes[label]
        variants_by_games = sorted(variants, key=lambda d: -int(d["n_games_seen"]))
        total_games = sum(int(d["n_games_seen"]) for d in variants)
        if total_games == 0:
            continue
        top_share = int(variants_by_games[0]["n_games_seen"]) / total_games
        card_presence = Counter()
        for d in variants:
            pairs = [tuple(map(int, pr.split(":"))) for pr in d["composition"].split(";") if pr]
            for cid, cnt in pairs:
                card_presence[cid] += 1
        n_variants = len(variants)
        core = [cid for cid, cnt in card_presence.items() if cnt == n_variants]
        tech = sorted([cid for cid, cnt in card_presence.items() if cnt < n_variants],
                       key=lambda cid: -card_presence[cid])
        out.p(f"\n  {label}: {n_variants} distinct decklists, {total_games} games, top-list share={top_share:.2f}")
        out.p(f"    core cards (in all {n_variants} lists): {len(core)}")
        out.p(f"    top tech/variable cards: "
              f"{[(name_of(cid), f'{card_presence[cid]}/{n_variants}') for cid in tech[:8]]}")
        for rank, d in enumerate(variants_by_games[:15], start=1):
            variant_rows.append({
                "cluster_id": label, "deck_hash": d["deck_hash"], "rank_within_cluster": rank,
                "n_games_seen": d["n_games_seen"],
                "share_of_cluster_games": round(int(d["n_games_seen"]) / total_games, 4),
            })
    with open(os.path.join(OUT_DIR, "deck_variants.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(variant_rows[0].keys()))
        w.writeheader()
        w.writerows(variant_rows)
    out.p(f"\nWrote deck_variants.csv: {len(variant_rows)} rows across {len(top_clusters)} archetypes")

    # ================= GAME LENGTH / SHORT-GAME CHECK =================
    out.p("\n" + "=" * 78)
    out.p("GAME LENGTH DISTRIBUTION (main weighted sample, DECISIVE)")
    steps = sorted(int(e["n_steps"]) for e in decisive)
    n = len(steps)
    if n:
        out.p(f"  n={n} min={steps[0]} p5={steps[n//20]} p25={steps[n//4]} median={steps[n//2]} "
              f"p75={steps[3*n//4]} p95={steps[19*n//20]} max={steps[-1]}")
    short_cut = 20
    short_games = [e for e in decisive if int(e["n_steps"]) < short_cut]
    out.p(f"  DECISIVE games with n_steps < {short_cut}: {len(short_games)}/{len(decisive)} "
          f"({len(short_games)/len(decisive)*100:.2f}%)")
    if short_games:
        by_label = Counter()
        for e in short_games:
            for hkey in ("deck0_hash", "deck1_hash"):
                h = e[hkey]
                by_label[decks.get(h, {}).get("cluster_id", "UNLABELED")] += 1
        out.p(f"  short-game deck/cluster distribution: {by_label.most_common(10)}")
    out.p(f"  outcome_type breakdown (ALL episodes): "
          f"{dict(Counter(e['outcome_type'] for e in episodes))}")
    # error/timeout correlation with period and rating
    err_by_period = Counter(e["period"] for e in errors)
    out.p(f"  ERROR_OR_TIMEOUT by period: {dict(err_by_period)}")

    out.p("\nDONE.")
    out.close()


if __name__ == "__main__":
    main()
