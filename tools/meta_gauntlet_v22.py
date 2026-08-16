"""v22 meta-deck gauntlet -- the Block-A1 measurement run (V17_ROADMAP.md:
A1 must be measured via the meta-gauntlet, NOT vs V6, because vs the V6
mirror the old determinization was already correct).

Same protocol as tools/meta_gauntlet_v17.py (same 3 discriminative real-meta
decks, same generic pilot, same 20-games-per-deck default, strict slot
alternation, keep-search-input harness): the metric is the per-deck DELTA vs
the V17 baseline (results/v17_meta_gauntlet/summary.json: Mega Kangaskhan
9/20, Fezandipiti 17/20, Marnie's Grimmsnarl 18/20) and the V6 control
(11/17/18).

Extra vs the V17 tool: per-game archetype-classification tallies from
native_bridge.CLASSIFICATION_COUNTS are recorded into raw_games.jsonl --
verifies the classifier actually fires against each gauntlet deck (it should
label Kangaskhan/Fezandipiti/Grimmsnarl within the first few decisions once
their board develops, and report MIRROR_FALLBACK only early-game).

Usage:
    python tools/meta_gauntlet_v22.py --games-per-deck 20 --games-vs-v12 30
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
from src.agents.dragapult_agent_v22_cpp import native_bridge  # noqa: E402

DECKS_DIR = REPO_ROOT / "decks"
OUT_DIR = REPO_ROOT / "results" / "v22_meta_gauntlet"

# (label, deck csv, V6 control wins/20, V17 wins/20 -- from
# results/meta_gauntlet_v6_v13/summary.json and results/v17_meta_gauntlet/)
META_DECKS = [
    ("Mega Kangaskhan ex", DECKS_DIR / "meta_mega_kangaskhan_ex.csv", 11, 9),
    ("Fezandipiti ex", DECKS_DIR / "meta_fezandipiti_ex.csv", 17, 17),
    ("Marnie's Grimmsnarl ex", DECKS_DIR / "meta_marnie_s_grimmsnarl_ex.csv", 18, 18),
]

MAX_STEPS = 2000


def _reset_match_budgets() -> None:
    import src.agents.final_candidate_agent_v22 as v22_mod

    v22_mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0


def run_series(series_label: str, opp_name: str, opp_fn, opp_deck, n_games: int,
               v22_name: str, v22_fn, v22_deck, games_f) -> dict:
    wins = losses = draws = aborted = 0
    for i in range(n_games):
        v22_slot0 = i % 2 == 0  # strict alternation
        native_bridge.CLASSIFICATION_COUNTS.clear()
        result = _play_one_game_keep_search_input(
            run_id=f"v22_meta_gauntlet_{series_label}",
            game_index=i,
            agent_a_name=v22_name,
            agent_a_fn=v22_fn,
            deck_a=v22_deck,
            agent_b_name=opp_name,
            agent_b_fn=opp_fn,
            deck_b=opp_deck,
            a_slot0=v22_slot0,
            max_steps=MAX_STEPS,
        )
        classif = dict(native_bridge.CLASSIFICATION_COUNTS)
        _reset_match_budgets()
        if result.aborted:
            aborted += 1
        elif result.winner_agent == v22_name:
            wins += 1
        elif result.winner_agent == "draw":
            draws += 1
        else:
            losses += 1
        games_f.write(json.dumps({
            "series": series_label,
            "game_index": i,
            "v22_slot0": v22_slot0,
            "winner_agent": result.winner_agent,
            "win_reason": result.win_reason,
            "turns": result.turns,
            "steps": result.steps,
            "aborted": result.aborted,
            "error": result.error,
            "classification_counts": classif,
        }) + "\n")
        games_f.flush()
        print(f"[{series_label}] [{i + 1}/{n_games}] v22_slot0={v22_slot0} "
              f"winner={result.winner_agent} aborted={result.aborted} classif={classif}", flush=True)
    return {"series": series_label, "games": n_games, "v22_wins": wins, "v22_losses": losses,
            "draws": draws, "aborted": aborted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-deck", type=int, default=20)
    parser.add_argument("--games-vs-v12", type=int, default=30)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    games_f = open(OUT_DIR / "raw_games.jsonl", "w", encoding="utf-8")

    v22_name, v22_fn, v22_deck = load_agent("src.agents.final_candidate_agent_v22", name_override="v22_arch_det")

    summary = []
    t0 = time.time()

    for deck_label, deck_path, v6_control_wins, v17_wins in META_DECKS:
        baseline_deck = load_deck_csv(deck_path)
        baseline_fn = make_baseline_agent(baseline_deck)
        row = run_series(deck_path.stem, f"baseline__{deck_path.stem}", baseline_fn, baseline_deck,
                         args.games_per_deck, v22_name, v22_fn, v22_deck, games_f)
        row["deck_label"] = deck_label
        row["v6_control_wins_of_20"] = v6_control_wins
        row["v17_wins_of_20"] = v17_wins
        summary.append(row)
        print(f"=== {deck_label}: v22 {row['v22_wins']}W-{row['v22_losses']}L "
              f"(V17: {v17_wins}/20, V6 control: {v6_control_wins}/20) ===", flush=True)

    if args.games_vs_v12 > 0:
        v12_name, v12_fn, v12_deck = load_agent("src.agents.final_candidate_agent_v12", name_override="v12_matchup_aware")
        row = run_series("vs_v12", v12_name, v12_fn, v12_deck, args.games_vs_v12,
                         v22_name, v22_fn, v22_deck, games_f)
        row["deck_label"] = "V12 head-to-head"
        summary.append(row)
        print(f"=== V12 head-to-head: v22 {row['v22_wins']}W-{row['v22_losses']}L ===", flush=True)

    games_f.close()
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Done in {time.time() - t0:.0f}s. Summary: {OUT_DIR / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
