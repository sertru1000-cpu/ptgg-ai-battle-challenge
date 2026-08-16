"""Runner for the V6-greedy vs. V6+1-step-lookahead research prototype
(experiments/v6_one_step_lookahead.py). See
ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md for the governing research
question and full write-up of what this script produces.

WHAT THIS SCRIPT DOES AND DOES NOT DO
--------------------------------------
- Drives REAL local self-play games through the actual cg.dll engine
  (cg.game.battle_start/battle_select/battle_finish), the same mechanism
  tools/tournament.py already uses -- NOT kaggle_environments, NOT Kaggle,
  NOT a new ladder submission.
- Every real game's ACTUAL trajectory is always driven by V6's own real
  greedy choice (`policy.agent(obs)`), never by the lookahead prototype's
  choice. The lookahead prototype runs in SHADOW mode: at every in-scope
  decision it also asks "what would V6+lookahead have picked here", records
  the answer, and then the real game proceeds exactly as if the lookahead
  prototype did not exist. This means these games are genuine, unmodified
  V6 self-play (comparable to prior sessions' V6 evaluation), and the
  lookahead prototype can never bias the outcome by feeding an artificial
  trajectory back into itself.
- Why "shadow-mode fresh self-play" rather than replaying the OLD real
  Kaggle ladder JSON in data/v6_ladder_audit/replays/: search_begin's token
  is tied to a LIVE battle_ptr (ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 2B --
  "tied to the live battle's internal state pointer at that instant, not
  something you can manufacture from a deepcopy of a dataclass"). Old
  replay JSON has no live engine process behind it, so engine-backed
  lookahead cannot be retroactively applied to it. Fresh local self-play
  (still real engine, still V6's real unmodified policy, still zero Kaggle
  interaction) is the closest correct interpretation of "historical replay
  data" available under that constraint -- see the report's Part 6 for the
  full discussion.
"""

from __future__ import annotations

import csv
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import psutil

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

import cg.game as g  # noqa: E402

from src.agents import lucario_ex_agent  # noqa: E402
from src.agents.dragapult_policy_v6 import DECK as V6_DECK, DragapultPolicy  # noqa: E402
from src.agents.policy_weights import BALANCED  # noqa: E402

from experiments.v6_one_step_lookahead import evaluate_decision_with_lookahead  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "results" / "v6_lookahead_experiment"
OPPONENT_DECK = lucario_ex_agent.DECK
OPPONENT_FN = lucario_ex_agent.agent
BENCHMARK_NS = (3, 5, 10)
PRIMARY_N = 5


def play_shadow_game(run_id: str, game_index: int, a_slot0: bool, decisions_out: list, proc: psutil.Process, max_steps: int = 800):
    """One real self-play game, V6 (dragapult ex) vs lucario_ex_agent, real
    engine, V6's real choice always drives the actual game. `a_slot0` =
    whether V6 occupies engine slot 0 this game (alternated across games per
    this project's standing first-player-split convention -- see
    feedback_ptcg_process memory / docs/environment.md).
    """
    policy = DragapultPolicy(BALANCED, adaptive=False)
    v6_slot = 0 if a_slot0 else 1
    deck0 = V6_DECK if a_slot0 else OPPONENT_DECK
    deck1 = OPPONENT_DECK if a_slot0 else V6_DECK

    game_id = f"{run_id}_{game_index}"
    obs, start = g.battle_start(deck0, deck1)
    if start.errorPlayer != -1:
        raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")

    steps = 0
    decision_num = 0
    game_decisions = []
    try:
        while obs["current"]["result"] < 0 and steps < max_steps:
            idx = obs["current"]["yourIndex"]
            if idx == v6_slot:
                row = {
                    "game_id": game_id, "game_index": game_index, "v6_slot": v6_slot,
                    "turn": obs["current"]["turn"], "decision_num": decision_num,
                    "rss_mb": proc.memory_info().rss / (1024 * 1024),
                }
                for n in BENCHMARK_NS:
                    t0 = time.perf_counter()
                    result = evaluate_decision_with_lookahead(policy, obs, V6_DECK, OPPONENT_DECK, top_n=n)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    if result is None:
                        row[f"n{n}_in_scope"] = False
                        continue
                    row[f"n{n}_in_scope"] = True
                    row[f"n{n}_total_latency_ms"] = result.total_latency_s * 1000.0
                    row[f"n{n}_root_clone_latency_ms"] = (result.root_clone_latency_s or 0.0) * 1000.0
                    row[f"n{n}_wall_ms"] = elapsed_ms
                    row[f"n{n}_top_n_evaluated"] = result.top_n_evaluated
                    row[f"n{n}_v6_choice"] = result.v6_choice
                    row[f"n{n}_lookahead_choice"] = result.lookahead_choice
                    row[f"n{n}_disagreement"] = result.disagreement
                    row[f"n{n}_fallback_reason"] = result.fallback_reason
                    if n == PRIMARY_N:
                        row["context"] = result.context
                        row["n_options"] = result.n_options
                        row["candidates"] = json.dumps([asdict(c) for c in result.candidates])
                        v6_cand = next((c for c in result.candidates if [c.index] == result.v6_choice), None)
                        la_cand = next((c for c in result.candidates if [c.index] == result.lookahead_choice), None)
                        row["v6_choice_option_type"] = v6_cand.option_type if v6_cand else None
                        row["v6_choice_attack_id"] = v6_cand.attack_id if v6_cand else None
                        row["v6_choice_card_id"] = v6_cand.card_id if v6_cand else None
                        row["v6_choice_rng_class"] = v6_cand.rng_class if v6_cand else None
                        row["lookahead_choice_option_type"] = la_cand.option_type if la_cand else None
                        row["lookahead_choice_attack_id"] = la_cand.attack_id if la_cand else None
                        row["lookahead_choice_card_id"] = la_cand.card_id if la_cand else None
                        row["lookahead_choice_rng_class"] = la_cand.rng_class if la_cand else None
                if row.get(f"n{PRIMARY_N}_in_scope"):
                    game_decisions.append(row)
                    decision_num += 1
                action = policy.agent(obs)
            else:
                action = OPPONENT_FN(obs)
            obs = g.battle_select(action)
            steps += 1

        aborted = obs["current"]["result"] < 0
        result_slot = obs["current"]["result"] if not aborted else None
        outcome = "aborted" if aborted else ("v6_win" if result_slot == v6_slot else ("draw" if result_slot == 2 else "v6_loss"))
    finally:
        try:
            g.battle_finish()
        except Exception:
            pass

    for row in game_decisions:
        row["game_outcome"] = outcome
        row["game_steps"] = steps
    decisions_out.extend(game_decisions)
    return outcome, steps


def main(n_games: int = 12, max_steps: int = 800):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    proc = psutil.Process()

    rss_start_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"RSS at start: {rss_start_mb:.1f} MB")

    all_decisions: list[dict] = []
    game_outcomes = []
    t_run_start = time.perf_counter()
    for i in range(n_games):
        a_slot0 = i % 2 == 0
        t0 = time.perf_counter()
        outcome, steps = play_shadow_game(run_id, i, a_slot0, all_decisions, proc, max_steps=max_steps)
        elapsed = time.perf_counter() - t0
        game_outcomes.append({"game_index": i, "v6_slot": 0 if a_slot0 else 1, "outcome": outcome, "steps": steps, "elapsed_s": elapsed})
        rss_now = proc.memory_info().rss / (1024 * 1024)
        print(f"  game {i}: v6_slot={0 if a_slot0 else 1} outcome={outcome} steps={steps} elapsed={elapsed:.1f}s rss={rss_now:.1f}MB decisions_so_far={len(all_decisions)}")

    rss_end_mb = proc.memory_info().rss / (1024 * 1024)
    total_elapsed = time.perf_counter() - t_run_start
    print(f"RSS at end: {rss_end_mb:.1f} MB (delta {rss_end_mb - rss_start_mb:+.1f} MB) over {len(all_decisions)} decisions, {total_elapsed:.1f}s total")

    # Raw per-decision CSV -- preserved in full, never discarded after
    # aggregation, per this project's standing process rule.
    decisions_csv = OUT_DIR / f"{run_id}_decisions.csv"
    if all_decisions:
        fieldnames = sorted({k for row in all_decisions for k in row.keys()})
        with open(decisions_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_decisions)
    print(f"Wrote {len(all_decisions)} decision rows to {decisions_csv}")

    games_csv = OUT_DIR / f"{run_id}_games.csv"
    with open(games_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["game_index", "v6_slot", "outcome", "steps", "elapsed_s"])
        writer.writeheader()
        writer.writerows(game_outcomes)
    print(f"Wrote {len(game_outcomes)} game rows to {games_csv}")

    meta = {
        "run_id": run_id, "n_games": n_games, "max_steps": max_steps,
        "opponent": "lucario_ex_agent", "primary_n": PRIMARY_N, "benchmark_ns": list(BENCHMARK_NS),
        "rss_start_mb": rss_start_mb, "rss_end_mb": rss_end_mb, "rss_delta_mb": rss_end_mb - rss_start_mb,
        "total_elapsed_s": total_elapsed, "n_decisions": len(all_decisions),
    }
    meta_path = OUT_DIR / f"{run_id}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote run metadata to {meta_path}")
    return run_id


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=800)
    args = parser.parse_args()
    main(n_games=args.games, max_steps=args.max_steps)
