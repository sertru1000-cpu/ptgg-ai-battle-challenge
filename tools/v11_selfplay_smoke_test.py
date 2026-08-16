"""V11 local self-play smoke test (Deliverable: "run a short local self-play
test to ensure it doesn't crash, doesn't leak memory, and actually completes
turns").

Drives REAL local self-play games through the actual cg.dll engine
(cg.game.battle_start/battle_select/battle_finish), same mechanism as
tools/tournament.py and tools/v6_lookahead_experiment_runner.py. V11's real,
unwrapped policy chain (src.agents.dragapult_agent_v11, i.e.
make_agent(BALANCED, always_first=True) -- always_first wraps but still
exposes `.policy`) drives every real decision so this also collects the
macro-action-search latency/fallback diagnostics
(`policy.macro_decision_latencies_ms`, `.macro_used_count`,
`.macro_fallback_count`, `.macro_stats`) needed for V11_IMPLEMENTATION_REPORT.md.
Not Kaggle, not a submission -- purely local.

Usage:
    python tools/v11_selfplay_smoke_test.py --games 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import psutil

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

import cg.game as g  # noqa: E402

from src.agents import lucario_ex_agent  # noqa: E402
from src.agents.dragapult_agent_v11 import DECK as V11_DECK, agent as v11_agent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "results" / "v11_selfplay_smoke_test"
OPPONENT_DECK = lucario_ex_agent.DECK
OPPONENT_FN = lucario_ex_agent.agent


def play_one_game(game_index: int, v11_slot0: bool, proc: psutil.Process, max_steps: int = 800):
    v11_slot = 0 if v11_slot0 else 1
    deck0 = V11_DECK if v11_slot0 else OPPONENT_DECK
    deck1 = OPPONENT_DECK if v11_slot0 else V11_DECK

    obs, start = g.battle_start(deck0, deck1)
    if start.errorPlayer != -1:
        raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")

    steps = 0
    t0 = time.perf_counter()
    try:
        while obs["current"]["result"] < 0 and steps < max_steps:
            idx = obs["current"]["yourIndex"]
            action = v11_agent(obs) if idx == v11_slot else OPPONENT_FN(obs)
            obs = g.battle_select(action)
            steps += 1
        aborted = obs["current"]["result"] < 0
        result_slot = obs["current"]["result"] if not aborted else None
        outcome = "aborted" if aborted else ("v11_win" if result_slot == v11_slot else ("draw" if result_slot == 2 else "v11_loss"))
        turns = obs["current"]["turn"]
    finally:
        try:
            g.battle_finish()
        except Exception:
            pass
    elapsed = time.perf_counter() - t0
    rss_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"  game {game_index}: v11_slot={v11_slot} outcome={outcome} steps={steps} turns={turns} elapsed={elapsed:.1f}s rss={rss_mb:.1f}MB")
    return outcome, steps, turns, elapsed, rss_mb


def main(n_games: int = 3, max_steps: int = 800):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = psutil.Process()
    policy = v11_agent.policy  # exposed by make_agent(); persists across games in this process

    rss_start_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"RSS at start: {rss_start_mb:.1f} MB")

    games = []
    crashed = False
    for i in range(n_games):
        v11_slot0 = i % 2 == 0  # alternate first-player slot, per project convention
        try:
            outcome, steps, turns, elapsed, rss_mb = play_one_game(i, v11_slot0, proc, max_steps=max_steps)
            games.append({"game_index": i, "v11_slot0": v11_slot0, "outcome": outcome, "steps": steps, "turns": turns, "elapsed_s": elapsed, "rss_mb": rss_mb})
        except Exception as e:  # noqa: BLE001 -- a crash IS the thing this smoke test checks for
            crashed = True
            print(f"  game {i}: CRASHED: {type(e).__name__}: {e}")
            games.append({"game_index": i, "v11_slot0": v11_slot0, "outcome": "CRASH", "error": f"{type(e).__name__}: {e}"})

    rss_end_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"RSS at end: {rss_end_mb:.1f} MB (delta {rss_end_mb - rss_start_mb:+.1f} MB)")

    latencies = policy.macro_decision_latencies_ms
    summary = {
        "n_games": n_games,
        "crashed": crashed,
        "games": games,
        "rss_start_mb": rss_start_mb,
        "rss_end_mb": rss_end_mb,
        "rss_delta_mb": rss_end_mb - rss_start_mb,
        "macro_decisions_total": len(latencies),
        "macro_used_count": policy.macro_used_count,
        "macro_fallback_count": policy.macro_fallback_count,
        "macro_latency_ms_median": statistics.median(latencies) if latencies else None,
        "macro_latency_ms_p95": (statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies) if latencies else None),
        "macro_latency_ms_max": max(latencies) if latencies else None,
        "macro_latency_ms_mean": statistics.mean(latencies) if latencies else None,
        "macro_chain_lengths_max": max(policy.macro_stats.chain_lengths) if policy.macro_stats.chain_lengths else None,
        "macro_chain_cap_hit": policy.macro_stats.chain_cap_hit,
    }
    print(json.dumps(summary, indent=2))

    out_path = OUT_DIR / f"{int(time.time())}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=800)
    args = parser.parse_args()
    main(n_games=args.games, max_steps=args.max_steps)
