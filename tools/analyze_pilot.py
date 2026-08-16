"""Compute all the Part-1 pilot analyses (deck/archetype frequency, matchup matrix,
temporal comparison, deck variance, game length) from the parsed pilot CSVs and dump
plain-text summaries used to write reports/real_meta_pilot_v1.md.

Reads:
  strategy/meta_analysis/pilot_episodes_v1.csv
  strategy/meta_analysis/pilot_deck_registry_v1.csv
"""
import csv
import math
import os
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from src.meta_analysis.card_lookup import name_of

EPISODES = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_episodes_v1.csv")
DECKS = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "pilot_deck_registry_v1.csv")


def wilson_ci(wins, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def main():
    with open(EPISODES, encoding="utf-8", newline="") as f:
        episodes = list(csv.DictReader(f))
    with open(DECKS, encoding="utf-8", newline="") as f:
        decks = {r["deck_hash"]: r for r in csv.DictReader(f)}

    main_eps = [e for e in episodes if e["sample_type"] == "stratified"]
    anomaly_short = [e for e in episodes if e["sample_type"] == "anomaly_short"]
    anomaly_long = [e for e in episodes if e["sample_type"] == "anomaly_long"]
    # Win-rate stats use DECISIVE-only games -- DRAW and ERROR_OR_TIMEOUT are not a clean
    # binary win/loss trial (one side crashing isn't a deck-strength signal).
    decisive_main = [e for e in main_eps if e.get("outcome_type") == "DECISIVE"]

    print("=" * 70)
    print(f"TOTAL episodes parsed: {len(episodes)} (main={len(main_eps)}, "
          f"anomaly_short={len(anomaly_short)}, anomaly_long={len(anomaly_long)})")
    print(f"Unique decks seen: {len(decks)}")

    print("\n" + "=" * 70)
    print("OUTCOME TYPE BREAKDOWN (per sample_type)")
    for name, rows in [("stratified", main_eps), ("anomaly_short", anomaly_short), ("anomaly_long", anomaly_long)]:
        c = Counter(r.get("outcome_type", "?") for r in rows)
        print(f"  {name} (n={len(rows)}): {dict(c)}")

    # ---------- deck-level (main sample, DECISIVE games only for win rate) ----------
    deck_stats = defaultdict(lambda: {"games": 0, "wins": 0, "steps": []})
    for e in decisive_main:
        for side, hsh_key in ((0, "deck0_hash"), (1, "deck1_hash")):
            hsh = e[hsh_key]
            deck_stats[hsh]["games"] += 1
            if int(e["winner"]) == side:
                deck_stats[hsh]["wins"] += 1
            deck_stats[hsh]["steps"].append(int(e["n_steps"]))

    print("\n" + "=" * 70)
    print("TOP 20 DECKS BY GAME COUNT (main stratified sample, DECISIVE games only)")
    print(f"{'hash':17} {'label':28} {'games':>6} {'winrate':>8} {'avg_steps':>10}")
    ranked = sorted(deck_stats.items(), key=lambda kv: -kv[1]["games"])
    for hsh, s in ranked[:20]:
        label = decks.get(hsh, {}).get("label", "?")
        wr = s["wins"] / s["games"] if s["games"] else 0
        avg_steps = sum(s["steps"]) / len(s["steps"])
        print(f"{hsh:17} {label:28} {s['games']:6d} {wr:8.3f} {avg_steps:10.1f}")

    # ---------- archetype/label-level (main sample, DECISIVE games only for win rate) ----------
    label_stats = defaultdict(lambda: {"games": 0, "wins": 0, "n_decks": set()})
    for e in decisive_main:
        for side, hsh_key in ((0, "deck0_hash"), (1, "deck1_hash")):
            hsh = e[hsh_key]
            label = decks.get(hsh, {}).get("label", "UNLABELED")
            label_stats[label]["games"] += 1
            label_stats[label]["n_decks"].add(hsh)
            if int(e["winner"]) == side:
                label_stats[label]["wins"] += 1

    print("\n" + "=" * 70)
    print("ARCHETYPE-LEVEL FREQUENCY + WIN RATE (main stratified sample, DECISIVE games only, both sides pooled)")
    print(f"{'label':28} {'games':>6} {'n_decks':>8} {'winrate':>8} {'wilson_lo':>10} {'wilson_hi':>10}")
    total_games_pooled = sum(s["games"] for s in label_stats.values())
    for label, s in sorted(label_stats.items(), key=lambda kv: -kv[1]["games"]):
        p, lo, hi = wilson_ci(s["wins"], s["games"])
        print(f"{label:28} {s['games']:6d} {len(s['n_decks']):8d} {p:8.3f} {lo:10.3f} {hi:10.3f}"
              f"   usage={s['games']/total_games_pooled*100:.1f}%")

    # ---------- matchup matrix (only games where BOTH sides got a known, non-UNLABELED label) ----------
    matchup = defaultdict(lambda: {"games": 0, "wins_row": 0})
    for e in decisive_main:
        l0 = decks.get(e["deck0_hash"], {}).get("label", "UNLABELED")
        l1 = decks.get(e["deck1_hash"], {}).get("label", "UNLABELED")
        if l0 == "UNLABELED" or l1 == "UNLABELED":
            continue
        w = e["winner"]
        for (row, col, row_side) in [(l0, l1, 0), (l1, l0, 1)]:
            matchup[(row, col)]["games"] += 1
            if w not in ("", None) and int(w) == row_side:
                matchup[(row, col)]["wins_row"] += 1

    print("\n" + "=" * 70)
    print("MATCHUP MATRIX (labeled-vs-labeled games only; UNLABELED excluded)")
    labels_seen = sorted(set(k[0] for k in matchup) | set(k[1] for k in matchup))
    for l0 in labels_seen:
        for l1 in labels_seen:
            if l0 >= l1:
                continue
            m = matchup.get((l0, l1))
            if not m:
                continue
            p, lo, hi = wilson_ci(m["wins_row"], m["games"])
            flag = "  [LOW-N]" if m["games"] < 20 else ""
            print(f"  {l0} vs {l1}: n={m['games']} {l0}_winrate={p:.3f} "
                  f"[{lo:.3f},{hi:.3f}]{flag}")

    # ---------- temporal: EARLY/MIDDLE/RECENT by week ----------
    def period(week):
        w = int(week)
        if w <= 2:
            return "EARLY (weeks 1-3)"
        elif w <= 4:
            return "MIDDLE (weeks 4-5)"
        else:
            return "RECENT (weeks 6-8)"

    period_label_games = defaultdict(lambda: defaultdict(int))
    period_totals = defaultdict(int)
    for e in main_eps:
        p = period(e["week"])
        for hsh_key in ("deck0_hash", "deck1_hash"):
            label = decks.get(e[hsh_key], {}).get("label", "UNLABELED")
            period_label_games[p][label] += 1
            period_totals[p] += 1

    print("\n" + "=" * 70)
    print("TEMPORAL: archetype-label share of games by period")
    for p in ["EARLY (weeks 1-3)", "MIDDLE (weeks 4-5)", "RECENT (weeks 6-8)"]:
        print(f"\n  {p} (n={period_totals[p]} deck-slots):")
        for label, cnt in sorted(period_label_games[p].items(), key=lambda kv: -kv[1]):
            print(f"    {label:28} {cnt:5d}  ({cnt/period_totals[p]*100:.1f}%)")

    # ---------- deck variance within top archetype labels ----------
    print("\n" + "=" * 70)
    print("DECK VARIANCE within most-frequent archetype labels")
    label_to_hashes = defaultdict(list)
    for hsh, d in decks.items():
        label_to_hashes[d["label"]].append(d)
    for label in [l for l, s in sorted(label_stats.items(), key=lambda kv: -kv[1]["games"]) if l != "UNLABELED"][:6]:
        variants = label_to_hashes[label]
        variants_by_games = sorted(variants, key=lambda d: -int(d["n_games_seen"]))
        total_games = sum(int(d["n_games_seen"]) for d in variants)
        top_share = int(variants_by_games[0]["n_games_seen"]) / total_games if total_games else 0
        # card-level presence rate across variants (unweighted by games, i.e. per distinct list)
        card_presence = Counter()
        for d in variants:
            pairs = [tuple(map(int, p.split(":"))) for p in d["composition"].split(";") if p]
            for cid, cnt in pairs:
                card_presence[cid] += 1
        n_variants = len(variants)
        core = [cid for cid, cnt in card_presence.items() if cnt == n_variants]
        tech = [cid for cid, cnt in card_presence.items() if cnt < n_variants]
        print(f"\n  {label}: {n_variants} distinct decklists, {total_games} games, "
              f"top-list share={top_share:.2f}")
        print(f"    core cards (in all {n_variants} lists): {len(core)} unique IDs")
        tech_sorted = sorted(tech, key=lambda cid: -card_presence[cid])[:8]
        print(f"    most-common tech/variable cards: "
              f"{[(name_of(cid), f'{card_presence[cid]}/{n_variants}') for cid in tech_sorted]}")

    # ---------- game length ----------
    print("\n" + "=" * 70)
    print("GAME LENGTH DISTRIBUTION")
    def summarize_steps(rows, name):
        steps = sorted(int(r["n_steps"]) for r in rows)
        if not steps:
            print(f"  {name}: n=0")
            return
        n = len(steps)
        print(f"  {name}: n={n} min={steps[0]} p25={steps[n//4]} median={steps[n//2]} "
              f"p75={steps[3*n//4]} max={steps[-1]}")
    summarize_steps(main_eps, "main stratified sample")
    summarize_steps(anomaly_short, "anomaly_short sub-sample")
    summarize_steps(anomaly_long, "anomaly_long sub-sample")

    # short games: winner side distribution + first-player correlation
    short_cut = 20
    short_games = [e for e in main_eps if int(e["n_steps"]) < short_cut]
    print(f"\n  Main-sample games with n_steps < {short_cut}: {len(short_games)}/{len(main_eps)} "
          f"({len(short_games)/len(main_eps)*100:.1f}%)")
    if short_games:
        fp_wins = sum(1 for e in short_games if e["winner"] not in ("", None)
                      and e["first_player"] not in ("", None)
                      and int(e["winner"]) == int(e["first_player"]))
        decided = [e for e in short_games if e["winner"] not in ("", None) and e["first_player"] not in ("", None)]
        if decided:
            print(f"  Of those with known first_player+winner (n={len(decided)}): "
                  f"first-player won {fp_wins}/{len(decided)} ({fp_wins/len(decided)*100:.1f}%)")


if __name__ == "__main__":
    main()
