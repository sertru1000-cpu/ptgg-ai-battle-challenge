"""Prompt #5, Part 6: reproducible local comparison of V1 (BASELINE) against
V2 (BALANCED), V3 (AGGRESSIVE), V4 (DEFENSIVE), V5 (ADAPTIVE), all under
identical conditions -- same three sparring opponents, same deck for every
version (Dragapult ex, decks/dragapult_ex.csv), same tools/tournament.py
harness, same slot-alternation convention.

Every version uses the SAME full submission-safety composition
(safety_wrapper -> timeout_shield -> policy) it would actually ship with, so
these numbers reflect what would really run on Kaggle, not a stripped-down
research variant.

Reuses tools/tournament.py's run_tournament() (raw per-game JSONL never
deleted/overwritten, split by first/second-player slot per the project's
standing process rule) and adds: (a) a decision-log pass for the four
V1-vs-Vn head-to-heads (switching-frequency stats, Part 6's explicit
requirement), (b) a single aggregated comparison CSV across every matchup.

Usage:
    python tools/build_v2_v5_experiments.py --games-vs-opponent 60 --games-head-to-head 100
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.tournament import compute_leaderboard, run_tournament, write_leaderboard_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "results" / "agent" / "v2_v5_experiments"
GAMES_DIR = OUT_DIR / "games"

VERSIONS = {
    "V1_baseline": "src.agents.final_candidate_agent",
    "V2_balanced": "src.agents.final_candidate_agent_v2",
    "V3_aggressive": "src.agents.final_candidate_agent_v3",
    "V4_defensive": "src.agents.final_candidate_agent_v4",
    "V5_adaptive": "src.agents.final_candidate_agent_v5",
}

SPARRING_OPPONENTS = {
    "abomasnow_agent": "src.agents.abomasnow_agent",
    "iono_agent": "src.agents.iono_agent",
    "lucario_ex_agent": "src.agents.lucario_ex_agent",
}


def run_battery(games_vs_opponent: int, games_head_to_head: int, max_steps: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Part A: every version vs every sparring opponent, same N, no decision
    # logging (keeps this pass fast; switching-frequency detail is captured
    # in Part B's head-to-head decision logs instead).
    for v_name, v_spec in VERSIONS.items():
        for opp_name, opp_spec in SPARRING_OPPONENTS.items():
            print(f"=== {v_name} vs {opp_name} ({games_vs_opponent} games) ===")
            run_tournament(
                agent_a_spec=v_spec,
                agent_b_spec=opp_spec,
                n_games=games_vs_opponent,
                out_dir=str(OUT_DIR),
                name_a=v_name,
                name_b=opp_name,
                max_steps=max_steps,
                log_decisions=False,
            )

    # Part B: V1 vs each challenger head-to-head, WITH decision logging (Part
    # 6's switching-frequency + decision-statistics requirement).
    for v_name, v_spec in VERSIONS.items():
        if v_name == "V1_baseline":
            continue
        print(f"=== V1_baseline vs {v_name} ({games_head_to_head} games, decisions logged) ===")
        run_tournament(
            agent_a_spec=VERSIONS["V1_baseline"],
            agent_b_spec=v_spec,
            n_games=games_head_to_head,
            out_dir=str(OUT_DIR),
            name_a="V1_baseline",
            name_b=v_name,
            max_steps=max_steps,
            log_decisions=True,
        )

    rows = compute_leaderboard(GAMES_DIR)
    write_leaderboard_csv(rows, OUT_DIR / "leaderboard.csv")
    print(f"\nAggregate leaderboard: {OUT_DIR / 'leaderboard.csv'}")


def summarize_switching(games_dir: Path) -> list[dict]:
    """Post-process every *_decisions.jsonl to compute RETREAT-selection
    frequency and average battle length per named agent, split by whether it
    was V1_baseline or the challenger. Only decision-logged runs (Part B)
    contribute -- Part A's runs have no *_decisions.jsonl and are skipped.
    """
    per_agent_name: dict[str, dict] = defaultdict(lambda: {"decisions": 0, "retreats": 0, "games": set(), "turns_by_game": {}})

    for jsonl_path in sorted(games_dir.glob("*_decisions.jsonl")):
        run_id = jsonl_path.name.replace("_decisions.jsonl", "")
        game_result_path = games_dir / f"{run_id}.jsonl"
        if not game_result_path.exists():
            continue
        game_meta = {}
        for line in game_result_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            game_meta[r["game_index"]] = r

        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            game_id = rec["game_id"]
            game_index = int(game_id.rsplit("_", 1)[-1])
            meta = game_meta.get(game_index)
            if meta is None:
                continue
            player_index = rec["player_index"]
            agent_name = meta["agent_a_name"] if player_index == meta["agent_a_slot"] else meta["agent_b_name"]
            stats = per_agent_name[agent_name]
            stats["decisions"] += 1
            for chosen in rec["chosen"]:
                if chosen["type"] == "RETREAT":
                    stats["retreats"] += 1
            stats["games"].add((run_id, game_index))
            stats["turns_by_game"][(run_id, game_index)] = max(stats["turns_by_game"].get((run_id, game_index), 0), rec["turn"])

    out = []
    for name, s in per_agent_name.items():
        n_games = len(s["games"])
        avg_turns = sum(s["turns_by_game"].values()) / n_games if n_games else 0.0
        out.append(
            {
                "agent": name,
                "games": n_games,
                "decisions": s["decisions"],
                "retreats_chosen": s["retreats"],
                "retreat_rate": round(s["retreats"] / s["decisions"], 4) if s["decisions"] else None,
                "avg_battle_length_turns": round(avg_turns, 2),
            }
        )
    return sorted(out, key=lambda r: r["agent"])


def write_switching_csv(rows: list[dict], path: Path) -> None:
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["agent", "games", "decisions", "retreats_chosen", "retreat_rate", "avg_battle_length_turns"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-vs-opponent", type=int, default=60)
    parser.add_argument("--games-head-to-head", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--skip-run", action="store_true", help="only recompute summaries from already-played games")
    args = parser.parse_args()

    if not args.skip_run:
        run_battery(args.games_vs_opponent, args.games_head_to_head, args.max_steps)

    switching_rows = summarize_switching(GAMES_DIR)
    write_switching_csv(switching_rows, OUT_DIR / "switching_stats.csv")
    print(f"Switching/decision stats: {OUT_DIR / 'switching_stats.csv'}")
    for row in switching_rows:
        print(" ", row)


if __name__ == "__main__":
    main()
