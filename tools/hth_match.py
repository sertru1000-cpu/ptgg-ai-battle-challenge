"""Head-to-head match runner for two final_candidate agents (both may be
native-search agents -- each keeps its own DLL/engine; the shared cg.dll is
LoadLibrary'd per package, established safe since the V17-vs-V12 gauntlet).

Strict first-player alternation; per-game timeout-budget reset for BOTH
modules (timeout_shield's match latch, see stress_test_v17's docstring).

Usage:
    python tools/hth_match.py --a v24 --b v23 --games 32
Writes results/hth_<a>_vs_<b>/raw_games.jsonl + summary.json.
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", required=True, help="version tag, e.g. v24")
    parser.add_argument("--b", required=True)
    parser.add_argument("--games", type=int, default=32)
    args = parser.parse_args()

    mod_a = importlib.import_module(f"src.agents.final_candidate_agent_{args.a}")
    mod_b = importlib.import_module(f"src.agents.final_candidate_agent_{args.b}")
    name_a, fn_a, deck_a = load_agent(f"src.agents.final_candidate_agent_{args.a}", name_override=args.a)
    name_b, fn_b, deck_b = load_agent(f"src.agents.final_candidate_agent_{args.b}", name_override=args.b)

    out_dir = REPO_ROOT / "results" / f"hth_{args.a}_vs_{args.b}"
    out_dir.mkdir(parents=True, exist_ok=True)
    games_f = open(out_dir / "raw_games.jsonl", "w", encoding="utf-8")

    wins_a = wins_b = draws = aborted = 0
    t0 = time.time()
    for i in range(args.games):
        a_slot0 = i % 2 == 0
        r = _play_one_game_keep_search_input(
            run_id=f"hth_{args.a}_{args.b}", game_index=i,
            agent_a_name=name_a, agent_a_fn=fn_a, deck_a=deck_a,
            agent_b_name=name_b, agent_b_fn=fn_b, deck_b=deck_b,
            a_slot0=a_slot0, max_steps=2000,
        )
        for m in (mod_a, mod_b):
            m._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0
        if r.aborted:
            aborted += 1
        elif r.winner_agent == name_a:
            wins_a += 1
        elif r.winner_agent == name_b:
            wins_b += 1
        else:
            draws += 1
        games_f.write(json.dumps({
            "game_index": i, "a_slot0": a_slot0, "winner": r.winner_agent,
            "turns": r.turns, "aborted": r.aborted, "error": r.error,
        }) + "\n")
        games_f.flush()
        print(f"[{i + 1}/{args.games}] winner={r.winner_agent} ({args.a} {wins_a}:{wins_b} {args.b})", flush=True)

    summary = {"a": args.a, "b": args.b, "games": args.games, "wins_a": wins_a,
               "wins_b": wins_b, "draws": draws, "aborted": aborted,
               "minutes": round((time.time() - t0) / 60, 1)}
    games_f.close()
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
