"""V17 meta-deck gauntlet: the tuned V17 (native C++ MCTS) against (a) the
generic baseline piloting the 3 most DISCRIMINATIVE real-meta decklists, and
(b) V12 (the only V6-derivative that held up on the real ladder, 669.6).

Discriminative = decks where the existing V6 control (results/
meta_gauntlet_v6_v13/summary.json, same 20-games-per-deck protocol, same
generic pilot) did NOT max out: Mega Kangaskhan ex (V6: 11/20), Fezandipiti
ex (V6: 17/20), Marnie's Grimmsnarl ex (V6: 18/20). Decks where V6 already
scores 19-20/20 have no headroom to show a V17 improvement and only cost
night-time budget. The metric that matters is the V17-vs-X minus V6-vs-X
DELTA, not the absolute rate -- the generic pilot is weak, absolute numbers
are inflated.

Uses stress_test_v17._play_one_game_keep_search_input, NOT
tools.tournament.play_one_game -- the latter strips `search_begin_input`
from every observation, which silently disables V17's native search
entirely (the root cause that invalidated this project's first 1000-game
V17 run; see that function's docstring).

Usage:
    python tools/meta_gauntlet_v17.py --games-per-deck 20 --games-vs-v12 30
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
OUT_DIR = REPO_ROOT / "results" / "v17_meta_gauntlet"

# (label, deck csv, V6 control wins out of 20 -- from results/meta_gauntlet_v6_v13/summary.json)
META_DECKS = [
    ("Mega Kangaskhan ex", DECKS_DIR / "meta_mega_kangaskhan_ex.csv", 11),
    ("Fezandipiti ex", DECKS_DIR / "meta_fezandipiti_ex.csv", 17),
    ("Marnie's Grimmsnarl ex", DECKS_DIR / "meta_marnie_s_grimmsnarl_ex.csv", 18),
]

MAX_STEPS = 2000


def _reset_match_budgets() -> None:
    # Same per-game budget reset the stress test does (timeout_shield's
    # match-budget latch has no per-game reset of its own).
    import src.agents.final_candidate_agent_v17 as v17_mod

    v17_mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0


def run_series(series_label: str, opp_name: str, opp_fn, opp_deck, n_games: int,
               v17_name: str, v17_fn, v17_deck, games_f) -> dict:
    wins = losses = draws = aborted = 0
    for i in range(n_games):
        v17_slot0 = i % 2 == 0  # strict alternation
        result = _play_one_game_keep_search_input(
            run_id=f"v17_meta_gauntlet_{series_label}",
            game_index=i,
            agent_a_name=v17_name,
            agent_a_fn=v17_fn,
            deck_a=v17_deck,
            agent_b_name=opp_name,
            agent_b_fn=opp_fn,
            deck_b=opp_deck,
            a_slot0=v17_slot0,
            max_steps=MAX_STEPS,
        )
        _reset_match_budgets()
        if result.aborted:
            aborted += 1
        elif result.winner_agent == v17_name:
            wins += 1
        elif result.winner_agent == "draw":
            draws += 1
        else:
            losses += 1
        games_f.write(json.dumps({
            "series": series_label,
            "game_index": i,
            "v17_slot0": v17_slot0,
            "winner_agent": result.winner_agent,
            "win_reason": result.win_reason,
            "turns": result.turns,
            "steps": result.steps,
            "aborted": result.aborted,
            "error": result.error,
        }) + "\n")
        games_f.flush()
        print(f"[{series_label}] [{i + 1}/{n_games}] v17_slot0={v17_slot0} winner={result.winner_agent} aborted={result.aborted}", flush=True)
    return {"series": series_label, "games": n_games, "v17_wins": wins, "v17_losses": losses,
            "draws": draws, "aborted": aborted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-deck", type=int, default=20)
    parser.add_argument("--games-vs-v12", type=int, default=30)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    games_f = open(OUT_DIR / "raw_games.jsonl", "w", encoding="utf-8")

    v17_name, v17_fn, v17_deck = load_agent("src.agents.final_candidate_agent_v17", name_override="v17_cpp_mcts")

    summary = []
    t0 = time.time()

    for deck_label, deck_path, v6_control_wins in META_DECKS:
        baseline_deck = load_deck_csv(deck_path)
        baseline_fn = make_baseline_agent(baseline_deck)
        row = run_series(deck_path.stem, f"baseline__{deck_path.stem}", baseline_fn, baseline_deck,
                         args.games_per_deck, v17_name, v17_fn, v17_deck, games_f)
        row["deck_label"] = deck_label
        row["v6_control_wins_of_20"] = v6_control_wins
        summary.append(row)
        print(f"=== {deck_label}: V17 {row['v17_wins']}W-{row['v17_losses']}L "
              f"(V6 control: {v6_control_wins}/20) ===", flush=True)

    if args.games_vs_v12 > 0:
        v12_name, v12_fn, v12_deck = load_agent("src.agents.final_candidate_agent_v12", name_override="v12_matchup_aware")
        row = run_series("vs_v12", v12_name, v12_fn, v12_deck, args.games_vs_v12,
                         v17_name, v17_fn, v17_deck, games_f)
        row["deck_label"] = "V12 head-to-head"
        summary.append(row)
        print(f"=== V12 head-to-head: V17 {row['v17_wins']}W-{row['v17_losses']}L ===", flush=True)

    games_f.close()
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Done in {time.time() - t0:.0f}s. Summary: {OUT_DIR / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
