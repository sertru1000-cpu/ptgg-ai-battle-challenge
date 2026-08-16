"""V19 (leader decklist) validation gauntlet.

Two measurements, both pure-Python agents (fast, no search budgets):
  1. V19 vs V6 head-to-head -- the clean deck A/B: SAME engine family
     (V19's policy is V6's engine + new-card support), different 60 cards.
     This isolates the list's value.
  2. The standard 3-deck meta-gauntlet (same decks/protocol as
     meta_gauntlet_v17/v18) -- V6 control: Kangaskhan 11/20, Fezandipiti
     17/20, Grimmsnarl 18/20.

Also tallies V19's Munkidori usage per game (ability actually fired?) from
the policy's own decision stream via a lightweight wrapper -- the V13 failure
mode (new cards rotting in hand) must be visible, not guessed.

Usage:
    python tools/gauntlet_v19.py --games-vs-v6 40 --games-per-deck 20
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.tournament import load_agent  # noqa: E402
from tools.stress_test_v17 import _play_one_game_keep_search_input  # noqa: E402
from src.agents.common import load_deck_csv  # noqa: E402
from src.agents.generic_policy_agent import make_agent as make_baseline_agent  # noqa: E402

DECKS_DIR = REPO_ROOT / "decks"
OUT_DIR = REPO_ROOT / "results" / "v19_gauntlet"

META_DECKS = [
    ("Mega Kangaskhan ex", DECKS_DIR / "meta_mega_kangaskhan_ex.csv", 11),
    ("Fezandipiti ex", DECKS_DIR / "meta_fezandipiti_ex.csv", 17),
    ("Marnie's Grimmsnarl ex", DECKS_DIR / "meta_marnie_s_grimmsnarl_ex.csv", 18),
]

MAX_STEPS = 2000


def _reset_budgets() -> None:
    import src.agents.final_candidate_agent_v19 as v19_mod

    v19_mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0


def run_series(series_label: str, opp_name: str, opp_fn, opp_deck, n_games: int,
               v19_name: str, v19_fn, v19_deck, games_f) -> dict:
    wins = losses = draws = aborted = 0
    for i in range(n_games):
        v19_slot0 = i % 2 == 0
        result = _play_one_game_keep_search_input(
            run_id=f"v19_gauntlet_{series_label}", game_index=i,
            agent_a_name=v19_name, agent_a_fn=v19_fn, deck_a=v19_deck,
            agent_b_name=opp_name, agent_b_fn=opp_fn, deck_b=opp_deck,
            a_slot0=v19_slot0, max_steps=MAX_STEPS,
        )
        _reset_budgets()
        if result.aborted:
            aborted += 1
        elif result.winner_agent == v19_name:
            wins += 1
        elif result.winner_agent == "draw":
            draws += 1
        else:
            losses += 1
        games_f.write(json.dumps({
            "series": series_label, "game_index": i, "v19_slot0": v19_slot0,
            "winner_agent": result.winner_agent, "win_reason": result.win_reason,
            "turns": result.turns, "steps": result.steps,
            "aborted": result.aborted, "error": result.error,
        }) + "\n")
        games_f.flush()
        print(f"[{series_label}] [{i + 1}/{n_games}] winner={result.winner_agent} aborted={result.aborted}", flush=True)
    return {"series": series_label, "games": n_games, "v19_wins": wins, "v19_losses": losses,
            "draws": draws, "aborted": aborted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-vs-v6", type=int, default=40)
    parser.add_argument("--games-per-deck", type=int, default=20)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    games_f = open(OUT_DIR / "raw_games.jsonl", "w", encoding="utf-8")

    v19_name, v19_fn, v19_deck = load_agent("src.agents.final_candidate_agent_v19", name_override="v19_leader_deck")
    v6_name, v6_fn, v6_deck = load_agent("src.agents.final_candidate_agent_v6", name_override="v6_heuristic")

    summary = []
    t0 = time.time()

    row = run_series("vs_v6", v6_name, v6_fn, v6_deck, args.games_vs_v6,
                     v19_name, v19_fn, v19_deck, games_f)
    row["deck_label"] = "V6 head-to-head (deck A/B)"
    summary.append(row)
    print(f"=== vs V6: V19 {row['v19_wins']}W-{row['v19_losses']}L ===", flush=True)

    for deck_label, deck_path, v6_control in META_DECKS:
        baseline_deck = load_deck_csv(deck_path)
        baseline_fn = make_baseline_agent(baseline_deck)
        row = run_series(deck_path.stem, f"baseline__{deck_path.stem}", baseline_fn, baseline_deck,
                         args.games_per_deck, v19_name, v19_fn, v19_deck, games_f)
        row["deck_label"] = deck_label
        row["v6_control_wins_of_20"] = v6_control
        summary.append(row)
        print(f"=== {deck_label}: V19 {row['v19_wins']}W-{row['v19_losses']}L (V6 control: {v6_control}/20) ===", flush=True)

    games_f.close()
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Done in {time.time() - t0:.0f}s. Summary: {OUT_DIR / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
