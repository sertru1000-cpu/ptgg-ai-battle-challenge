"""Phase 2 Objective 3: V16 (XGBoost-informed) agent latency smoke test.

Loads the fully safety/timeout-wrapped V16 agent (the same callable
main_v16.py hands to the Kaggle grader) and plays real decisions through the
actual compiled engine (cg.game.battle_start/battle_select, same pattern as
tools/verify_v13_real_game_smoke_test.py -- a synthetic/dummy obs_dict is not
representative here since Observation's `logs`/`current` fields have no
defaults and a hand-rolled stub dict does not match the engine's real shape).

Requirement under test: every V16 decision must return in under 1.0 second
wall-clock, including the XGBoost model load (first call only) and the
per-decision vectorize + predict_proba call.
"""

import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

import cg.game as g  # noqa: E402

from src.agents.abomasnow_agent import DECK as OPP_DECK, agent as opp_agent  # noqa: E402
from src.agents.final_candidate_agent_v16 import DECK as V16_DECK, agent as v16_agent  # noqa: E402

LATENCY_LIMIT_SECONDS = 1.0
MAX_V16_DECISIONS = 60  # "quick local script" -- a handful of real turns, not a full game
MAX_STEPS = 2000


def main() -> int:
    print("=== V16 XGBoost-agent latency smoke test ===")

    obs, start = g.battle_start(V16_DECK, OPP_DECK)
    if start.errorPlayer != -1:
        print(f"FAIL: deck error: player {start.errorPlayer} errorType {start.errorType}")
        return 1

    fns = [v16_agent, opp_agent]
    latencies: list[float] = []
    steps = 0
    v16_decisions = 0

    try:
        while obs["current"]["result"] < 0 and steps < MAX_STEPS and v16_decisions < MAX_V16_DECISIONS:
            idx = obs["current"]["yourIndex"]

            if idx == 0:
                t0 = time.perf_counter()
                action = fns[0](obs)
                elapsed = time.perf_counter() - t0
                latencies.append(elapsed)
                v16_decisions += 1
            else:
                action = fns[1](obs)

            assert isinstance(action, list), f"non-list action: {action}"
            opts = obs["select"]["option"]
            mn, mx = obs["select"]["minCount"], obs["select"]["maxCount"]
            assert mn <= len(action) <= mx, f"action length {len(action)} not in [{mn},{mx}]"
            assert len(set(action)) == len(action), f"duplicate indices: {action}"
            assert all(0 <= i < len(opts) for i in action), f"out-of-range index in {action}"

            obs = g.battle_select(action)
            steps += 1
    finally:
        g.battle_finish()

    print(f"Engine steps played: {steps}, V16 decisions timed: {len(latencies)}")

    if not latencies:
        print("FAIL: no V16 decisions were captured (game ended/errored before player 0 ever acted)")
        return 1

    latencies_sorted = sorted(latencies)
    p95_index = min(len(latencies_sorted) - 1, int(0.95 * len(latencies_sorted)))
    report = {
        "calls": len(latencies),
        "min_s": min(latencies),
        "mean_s": statistics.mean(latencies),
        "median_s": statistics.median(latencies),
        "p95_s": latencies_sorted[p95_index],
        "max_s": max(latencies),
        "first_call_s": latencies[0],  # includes one-time XGBoost model load
    }

    print("=" * 70)
    print("LATENCY REPORT")
    print("=" * 70)
    for k, v in report.items():
        print(f"  {k}: {v:.4f}s" if isinstance(v, float) else f"  {k}: {v}")
    print("=" * 70)

    over_budget = [l for l in latencies if l >= LATENCY_LIMIT_SECONDS]
    if over_budget:
        print(f"FAIL: {len(over_budget)}/{len(latencies)} decisions took >= {LATENCY_LIMIT_SECONDS}s (max={max(over_budget):.4f}s)")
        return 1

    print(f"PASS: all {len(latencies)} V16 decisions returned in < {LATENCY_LIMIT_SECONDS}s (max observed: {report['max_s']:.4f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
