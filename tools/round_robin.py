"""Phase 7/8: run every unique pairing among a fixed agent roster and produce
one combined matchup matrix (win rate, first/second split, avg game length,
terminal-reason distribution) from the raw per-game data.

Usage:
    python tools/round_robin.py --games 500 --out-dir results/formal_matrix_v1

Roster is fixed below (edit AGENTS to change it) rather than taking it as a
flag -- Phase 7/8 explicitly wants the same 5-agent roster
(Random, Abomasnow ex [corrected deck], Dragapult ex [current best variant],
Iono's, Mega Lucario ex) run consistently, not an ad-hoc set per invocation.
"""

import argparse
import csv
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.tournament import run_tournament

REPO_ROOT = Path(__file__).resolve().parents[1]

AGENTS = {
    "random_agent": {
        "spec": str(REPO_ROOT / "data" / "official" / "sample_submission" / "sample_submission" / "main.py"),
        "deck": str(REPO_ROOT / "data" / "official" / "sample_submission" / "sample_submission" / "deck.csv"),
    },
    "abomasnow_corrected": {
        "spec": "src.agents.abomasnow_agent",
        "deck": str(REPO_ROOT / "decks" / "abomasnow_ex_corrected_v1.csv"),
    },
    "dragapult_agent": {
        "spec": "src.agents.dragapult_agent",
        "deck": None,
    },
    "iono_agent": {
        "spec": "src.agents.iono_agent",
        "deck": None,
    },
    "lucario_ex_agent": {
        "spec": "src.agents.lucario_ex_agent",
        "deck": None,
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=500)
    parser.add_argument("--out-dir", default="results/formal_matrix_v1")
    parser.add_argument("--dragapult-spec", default="src.agents.dragapult_agent",
                         help="override which module implements 'dragapult_agent' in the roster (e.g. src.agents.dragapult_agent_always_first)")
    args = parser.parse_args()

    AGENTS["dragapult_agent"]["spec"] = args.dragapult_spec

    out_dir = Path(args.out_dir)
    names = list(AGENTS.keys())
    for a, b in itertools.combinations(names, 2):
        pair_dir = out_dir / f"{a}__vs__{b}"
        run_tournament(
            AGENTS[a]["spec"], AGENTS[b]["spec"], args.games, str(pair_dir),
            deck_a=AGENTS[a]["deck"], deck_b=AGENTS[b]["deck"],
            name_a=a, name_b=b,
        )

    # Aggregate a combined matrix from all raw per-game files just written.
    rows = []
    for a, b in itertools.combinations(names, 2):
        pair_dir = out_dir / f"{a}__vs__{b}" / "games"
        games, aborted, draws = 0, 0, 0
        a_wins = b_wins = 0
        a_wins_first = a_games_first = a_wins_second = a_games_second = 0
        turns_total = 0
        reasons = Counter()
        for jf in pair_dir.glob("*.jsonl"):
            if jf.name.endswith("_decisions.jsonl"):
                continue
            for line in jf.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                games += 1
                if r["aborted"]:
                    aborted += 1
                    continue
                turns_total += r["turns"]
                reasons[r["win_reason"]] += 1
                a_was_first = (r["agent_a_slot"] == r["first_player_slot"])
                if a_was_first:
                    a_games_first += 1
                else:
                    a_games_second += 1
                if r["winner_agent"] == "draw":
                    draws += 1
                    continue
                if r["winner_agent"] == a:
                    a_wins += 1
                    if a_was_first:
                        a_wins_first += 1
                    else:
                        a_wins_second += 1
                elif r["winner_agent"] == b:
                    b_wins += 1
        decided = games - aborted - draws
        rows.append({
            "agent_a": a, "agent_b": b, "games": games, "aborted": aborted, "draws": draws,
            "a_wins": a_wins, "b_wins": b_wins,
            "a_win_rate_overall": round(a_wins / decided, 4) if decided else None,
            "a_win_rate_when_first": round(a_wins_first / a_games_first, 4) if a_games_first else None,
            "a_win_rate_when_second": round(a_wins_second / a_games_second, 4) if a_games_second else None,
            "a_games_first": a_games_first, "a_games_second": a_games_second,
            "avg_turns": round(turns_total / decided, 2) if decided else None,
            "reason_counts": json.dumps(dict(reasons)),
        })

    matrix_path = out_dir / "matchup_matrix.csv"
    with open(matrix_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Combined matrix written to {matrix_path}")


if __name__ == "__main__":
    main()
