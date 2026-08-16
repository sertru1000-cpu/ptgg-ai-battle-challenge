"""Anchored round-robin: place unsubmittable agents (V27a/V27b) on the
ladder scale via matches against LADDER-CALIBRATED anchors, then fit the
local->ladder mapping on the anchors themselves (the instrument's own
honesty check -- see reports discussion; V18 is the known outlier control).

Schedule (sequential, overnight):
  v27  vs [v20 v6 v17 v19 v24 v26 v25 v23] x GAMES_MAIN
  v27b vs [v20 v24 v25 v23]                x GAMES_SUB

Writes results/anchored_rr/raw_games.jsonl + summary.json (appending safe --
resumable by pair).
"""

from __future__ import annotations

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

OUT = REPO_ROOT / "results" / "anchored_rr"
GAMES_MAIN = 16
GAMES_SUB = 16
ANCHORS_MAIN = ["v20", "v6", "v17", "v19", "v24", "v26", "v25", "v23"]
ANCHORS_SUB = ["v20", "v24", "v25", "v23"]


def reset_budget(mod) -> None:
    if hasattr(mod, "_timeout_shielded_agent"):
        mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0


def play_pair(a_tag: str, b_tag: str, n: int, done_pairs: set, games_f) -> dict | None:
    key = f"{a_tag}__{b_tag}"
    if key in done_pairs:
        return None
    mod_a = importlib.import_module(f"src.agents.final_candidate_agent_{a_tag}")
    mod_b = importlib.import_module(f"src.agents.final_candidate_agent_{b_tag}")
    name_a, fn_a, deck_a = load_agent(f"src.agents.final_candidate_agent_{a_tag}", name_override=a_tag)
    name_b, fn_b, deck_b = load_agent(f"src.agents.final_candidate_agent_{b_tag}", name_override=b_tag)
    wa = wb = 0
    for i in range(n):
        r = _play_one_game_keep_search_input(
            run_id=f"rr_{key}", game_index=i,
            agent_a_name=name_a, agent_a_fn=fn_a, deck_a=deck_a,
            agent_b_name=name_b, agent_b_fn=fn_b, deck_b=deck_b,
            a_slot0=(i % 2 == 0), max_steps=2000,
        )
        reset_budget(mod_a)
        reset_budget(mod_b)
        if r.winner_agent == name_a:
            wa += 1
        elif r.winner_agent == name_b:
            wb += 1
        games_f.write(json.dumps({"pair": key, "game": i, "winner": r.winner_agent,
                                  "aborted": r.aborted, "turns": r.turns}) + "\n")
        games_f.flush()
    print(f"[{key}] {wa}:{wb}", flush=True)
    return {"pair": key, "wins_a": wa, "wins_b": wb, "games": n}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary_path = OUT / "summary.json"
    results = json.loads(summary_path.read_text()) if summary_path.exists() else []
    done_pairs = {r["pair"] for r in results}
    games_f = open(OUT / "raw_games.jsonl", "a", encoding="utf-8")
    t0 = time.time()
    for anchor in ANCHORS_MAIN:
        r = play_pair("v27", anchor, GAMES_MAIN, done_pairs, games_f)
        if r:
            results.append(r)
            summary_path.write_text(json.dumps(results, indent=2))
    for anchor in ANCHORS_SUB:
        r = play_pair("v27b", anchor, GAMES_SUB, done_pairs, games_f)
        if r:
            results.append(r)
            summary_path.write_text(json.dumps(results, indent=2))
    games_f.close()
    print(f"DONE in {(time.time() - t0) / 3600:.1f} h; pairs={len(results)}")


if __name__ == "__main__":
    main()
