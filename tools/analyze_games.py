"""Cheap, three-axis loss categorization over raw tournament results.

Pure stdlib (json/csv only) -- no dependency on the cg engine, so it can run
standalone against any results/games/*.jsonl produced by tools/tournament.py.

Scope (deliberately limited, per the project's current phase): this
categorizes losses along three cheap, directly-recorded axes only --
- RESULT log reason code (1=0 prizes, 2=decked out at turn start,
  3=no Pokemon in Active Spot, 4=card effect)
- game length bucket (in turns)
- whether the losing agent was first or second player that game
It does NOT attempt tactical/decision-level fault analysis (e.g. "which
specific action lost the game") -- that needs opponent-model/search
machinery that is out of scope for this phase. Treat this as a first pass,
not a root-cause tool.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

REASON_NAMES = {
    1: "zero_prizes_remaining",
    2: "decked_out_at_turn_start",
    3: "no_pokemon_in_active_spot",
    4: "card_effect",
}


def load_results(results_dir: Path) -> list[dict]:
    games_dir = results_dir / "games"
    records = []
    for jsonl_path in sorted(games_dir.glob("*.jsonl")):
        if jsonl_path.name.endswith("_decisions.jsonl"):
            continue
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def length_bucket(turns: int) -> str:
    if turns <= 5:
        return "short (<=5 turns)"
    if turns <= 15:
        return "medium (6-15 turns)"
    return "long (>15 turns)"


def categorize_losses(results: list[dict], agent_name: str) -> dict:
    games_played = 0
    losses = []
    wins = 0
    draws = 0
    aborted_games = 0

    for r in results:
        if agent_name not in (r["agent_a_name"], r["agent_b_name"]):
            continue
        games_played += 1
        if r["aborted"]:
            aborted_games += 1
            continue
        if r["winner_agent"] == agent_name:
            wins += 1
            continue
        if r["winner_agent"] == "draw":
            draws += 1
            continue
        # a loss for agent_name
        my_slot = r["agent_a_slot"] if r["agent_a_name"] == agent_name else (1 - r["agent_a_slot"])
        was_first_player = r.get("first_player_slot") == my_slot
        losses.append(
            {
                "opponent": r["agent_b_name"] if r["agent_a_name"] == agent_name else r["agent_a_name"],
                "reason": r.get("win_reason"),
                "turns": r["turns"],
                "was_first_player": was_first_player,
            }
        )

    by_reason = Counter(REASON_NAMES.get(loss["reason"], f"unknown({loss['reason']})") for loss in losses)
    by_length = Counter(length_bucket(loss["turns"]) for loss in losses)
    by_first_player = Counter("first_player" if loss["was_first_player"] else "second_player" for loss in losses)
    by_opponent = Counter(loss["opponent"] for loss in losses)

    return {
        "agent": agent_name,
        "games_played": games_played,
        "wins": wins,
        "losses": len(losses),
        "draws": draws,
        "aborted": aborted_games,
        "loss_rate": round(len(losses) / (games_played - aborted_games), 4) if (games_played - aborted_games) else None,
        "losses_by_reason": dict(by_reason),
        "losses_by_length_bucket": dict(by_length),
        "losses_by_first_or_second_player": dict(by_first_player),
        "losses_by_opponent": dict(by_opponent),
    }


def print_summary(summary: dict) -> None:
    print(f"=== Loss analysis: {summary['agent']} ===")
    print(f"games_played={summary['games_played']} wins={summary['wins']} losses={summary['losses']} "
          f"draws={summary['draws']} aborted={summary['aborted']} loss_rate={summary['loss_rate']}")
    print("by reason (RESULT log):")
    for k, v in sorted(summary["losses_by_reason"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("by game length:")
    for k, v in sorted(summary["losses_by_length_bucket"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("by first/second player:")
    for k, v in sorted(summary["losses_by_first_or_second_player"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("by opponent:")
    for k, v in sorted(summary["losses_by_opponent"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--agent", required=True, help="which agent's losses to analyze")
    args = parser.parse_args()

    results = load_results(Path(args.results_dir))
    summary = categorize_losses(results, args.agent)
    print_summary(summary)


if __name__ == "__main__":
    main()
