"""The BC-gauntlet experiment: does a "strong deck in strong hands" local
benchmark rank our agents in LADDER order?

Test agents (chosen to span known ladder outcomes):
  V6  -> ladder 683.7   (the frozen baseline)
  V18 -> ladder 553     (the generic-gauntlet's famous false positive: 50/60)
  V20 -> ladder ~715    (current champion)
Opponents: the 3 BC pilots (high-rated-imitation) on the same meta decks the
old gauntlet used. Same protocol otherwise (alternating first player).

Success criterion (pre-registered): BC-gauntlet win totals order the agents
V20 > V6 > V18. The old generic gauntlet ordered them V18(50) > V6(46) --
if the new one flips that pair, the benchmark transfers where the old one
failed; Kendall-style agreement over the 3 pairs reported.

Usage:
    python tools/bc_gauntlet.py --games-per-cell 12
"""

from __future__ import annotations

import argparse
import importlib
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
from src.agents.bc_pilot_agent import make_bc_pilot  # noqa: E402

DECKS_DIR = REPO_ROOT / "decks"
OUT_DIR = REPO_ROOT / "results" / "bc_gauntlet"

PILOTS = [
    ("grimmsnarl", DECKS_DIR / "meta_marnie_s_grimmsnarl_ex.csv"),
    ("kangaskhan", DECKS_DIR / "meta_mega_kangaskhan_ex.csv"),
    ("fezandipiti", DECKS_DIR / "meta_fezandipiti_ex.csv"),
]
AGENTS = ["v6", "v18", "v20"]  # ladder: 683.7 / 553 / ~715


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-cell", type=int, default=12)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    games_f = open(OUT_DIR / "raw_games.jsonl", "w", encoding="utf-8")

    results = {}
    t0 = time.time()
    for agent_tag in AGENTS:
        mod = importlib.import_module(f"src.agents.final_candidate_agent_{agent_tag}")
        name, fn, deck = load_agent(f"src.agents.final_candidate_agent_{agent_tag}", name_override=agent_tag)
        total_w = total_l = 0
        for pilot_tag, deck_path in PILOTS:
            pilot_deck = load_deck_csv(deck_path)
            pilot_fn = make_bc_pilot(pilot_tag, pilot_deck)
            w = l = 0
            for i in range(args.games_per_cell):
                r = _play_one_game_keep_search_input(
                    run_id=f"bc_gauntlet_{agent_tag}_{pilot_tag}", game_index=i,
                    agent_a_name=name, agent_a_fn=fn, deck_a=deck,
                    agent_b_name=f"bc_{pilot_tag}", agent_b_fn=pilot_fn, deck_b=pilot_deck,
                    a_slot0=(i % 2 == 0), max_steps=2000,
                )
                if hasattr(mod, "_timeout_shielded_agent"):
                    mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0
                if r.winner_agent == name:
                    w += 1
                elif not r.aborted and r.winner_agent is not None and r.winner_agent != "draw":
                    l += 1
                games_f.write(json.dumps({
                    "agent": agent_tag, "pilot": pilot_tag, "game": i,
                    "winner": r.winner_agent, "aborted": r.aborted, "turns": r.turns,
                }) + "\n")
                games_f.flush()
            print(f"[{agent_tag} vs bc_{pilot_tag}] {w}W-{l}L", flush=True)
            results[f"{agent_tag}_{pilot_tag}"] = {"wins": w, "losses": l}
            total_w += w
            total_l += l
        results[f"{agent_tag}_TOTAL"] = {"wins": total_w, "losses": total_l}
        print(f"=== {agent_tag}: TOTAL {total_w}W-{total_l}L ===", flush=True)

    (OUT_DIR / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Done in {(time.time() - t0) / 60:.0f} min")


if __name__ == "__main__":
    main()
