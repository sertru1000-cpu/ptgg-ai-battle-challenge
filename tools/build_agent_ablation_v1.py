"""Phase 4.7 Section 24: mandatory ablation ladder.

A: existing baseline    -- src.agents.dragapult_agent (plain, notebook's
                            unconditional "always second"), safety_wrapper only.
B: + Going First/Second -- src.agents.dragapult_agent_always_first
                            (already-validated 'dragapult_fix_v1' override,
                            see results/dragapult_first_second_analysis.md),
                            safety_wrapper only.
C: + Bayesian opponent prediction -- same policy as B; the opponent-archetype
                            posterior model (results/agent/opponent_prediction_metrics.csv)
                            has no validated action-scoring hook for this
                            specific deck (see reports/final_agent_v1.md
                            Section "Bayesian Opponent Prediction" for the
                            gate decision) so this step is intentionally a
                            behavioral no-op vs B -- included to make that
                            explicit and measured, not assumed.
D: + validated counter  -- same policy as C; the one OOS_CONFIRMED counter
                            (Mewtwo ex -> Fezandipiti ex) does not apply to
                            Dragapult ex, so this step is also an intentional
                            no-op vs C for THIS deck (results/meta/
                            final_validated_counters.csv has no confirmed row
                            with Dragapult ex as the counter_archetype).
E: + all production safety -- adds timeout_shield on top of D's policy,
                            still wrapped in safety_wrapper
                            (== src.agents.final_candidate_agent exactly).

For each variant, plays a fixed opponent panel (existing hand-tuned agents,
not the variant itself) with natural tournament-harness slot alternation,
and instruments (independently of tools/tournament.py, which is left
unmodified): per-decision wall-clock latency (mean/p95/p99/max), plus each
wrapper's own stats dict (invalid_actions via safety_wrapper.stats, timeouts
via timeout_shield.stats where present).
"""

import csv
import statistics
import time
from pathlib import Path

from src.agents.safety_wrapper import wrap_agent
from src.agents.timeout_shield import wrap_timeout
from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from tools.tournament import compute_leaderboard, load_agent, play_one_game  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GAMES_DIR = REPO / "results" / "agent" / "ablation_v1" / "games"
OUT_CSV = REPO / "results" / "agent" / "agent_ablation_results.csv"
GAMES_PER_OPPONENT = 20

OPPONENTS = ["src.agents.abomasnow_agent", "src.agents.iono_agent", "src.agents.lucario_ex_agent"]


def timed(fn, latencies: list):
    def wrapped(obs_dict):
        if obs_dict.get("select") is None:
            return fn(obs_dict)
        start = time.monotonic()
        result = fn(obs_dict)
        latencies.append(time.monotonic() - start)
        return result

    return wrapped


def build_variant(letter: str):
    """Returns (name, agent_fn, deck, instrumentation dict)."""
    from src.agents import dragapult_agent, dragapult_agent_always_first

    latencies: list = []
    if letter == "A":
        base = dragapult_agent.agent
        deck = dragapult_agent.DECK
    else:
        base = dragapult_agent_always_first.agent
        deck = dragapult_agent_always_first.DECK

    if letter == "E":
        shielded = wrap_timeout(base, name=f"variant_{letter}")
        safe = wrap_agent(shielded, name=f"variant_{letter}")
        instrumentation = {"safety": safe.stats, "timeout": shielded.stats}
        instrumented = timed(safe, latencies)
    else:
        safe = wrap_agent(base, name=f"variant_{letter}")
        instrumentation = {"safety": safe.stats, "timeout": None}
        instrumented = timed(safe, latencies)

    instrumented.DECK = deck  # type: ignore[attr-defined]
    return instrumented, deck, latencies, instrumentation


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def main() -> None:
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for letter in ["A", "B", "C", "D", "E"]:
        agent_fn, deck, latencies, instrumentation = build_variant(letter)
        variant_name = f"{letter}_variant"
        wins = losses = draws = aborted = 0

        for opp_spec in OPPONENTS:
            opp_name, opp_fn, opp_deck = load_agent(opp_spec)
            run_id = f"ablation_{letter}_{opp_name}"
            for i in range(GAMES_PER_OPPONENT):
                a_slot0 = i % 2 == 0  # natural alternation, consistent with the rest of this project
                result = play_one_game(
                    run_id=run_id,
                    game_index=i,
                    agent_a_name=variant_name,
                    agent_a_fn=agent_fn,
                    deck_a=deck,
                    agent_b_name=opp_name,
                    agent_b_fn=opp_fn,
                    deck_b=opp_deck,
                    a_slot0=a_slot0,
                    max_steps=2000,
                    decision_logger=None,
                )
                jsonl_path = GAMES_DIR / f"{run_id}.jsonl"
                with open(jsonl_path, "a", encoding="utf-8") as f:
                    import json
                    from dataclasses import asdict

                    f.write(json.dumps(asdict(result)) + "\n")

                if result.aborted:
                    aborted += 1
                elif result.winner_agent == "draw":
                    draws += 1
                elif result.winner_agent == variant_name:
                    wins += 1
                else:
                    losses += 1

        games = wins + losses + draws + aborted
        win_rate = wins / (games - aborted - draws) if (games - aborted - draws) > 0 else None
        sorted_lat = sorted(latencies)

        safety_stats = instrumentation["safety"]
        timeout_stats = instrumentation["timeout"]

        rows.append(
            {
                "variant": letter,
                "description": {
                    "A": "existing baseline (plain dragapult_agent, safety_wrapper only)",
                    "B": "+ Going First/Second (dragapult_agent_always_first)",
                    "C": "+ Bayesian opponent prediction (no-op for this deck, see report)",
                    "D": "+ validated counter (no-op for this deck, see report)",
                    "E": "+ all production safety (timeout_shield + safety_wrapper) == final_candidate_agent",
                }[letter],
                "opponents": ";".join(o.rsplit(".", 1)[-1] for o in OPPONENTS),
                "games": games,
                "aborted": aborted,
                "draws": draws,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 4) if win_rate is not None else None,
                "invalid_actions": safety_stats["invalid_returned_by_inner"],
                "safety_fallback_used": safety_stats["fallback_used"],
                "safety_exceptions": safety_stats["exceptions"],
                "timeouts": timeout_stats["timeouts"] if timeout_stats else "N/A (no timeout_shield)",
                "degraded_mode_activations": timeout_stats["degraded_mode_activations"] if timeout_stats else "N/A",
                "crashes": aborted,
                "n_decisions_timed": len(latencies),
                "mean_decision_ms": round(statistics.mean(latencies) * 1000, 3) if latencies else None,
                "p95_decision_ms": round(pct(sorted_lat, 0.95) * 1000, 3) if latencies else None,
                "p99_decision_ms": round(pct(sorted_lat, 0.99) * 1000, 3) if latencies else None,
                "max_decision_ms": round(max(latencies) * 1000, 3) if latencies else None,
            }
        )
        print(
            f"[{letter}] games={games} win_rate={win_rate} invalid_actions={rows[-1]['invalid_actions']} "
            f"timeouts={rows[-1]['timeouts']} mean_ms={rows[-1]['mean_decision_ms']} "
            f"p99_ms={rows[-1]['p99_decision_ms']} max_ms={rows[-1]['max_decision_ms']}"
        )

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {OUT_CSV}")

    lb = compute_leaderboard(GAMES_DIR)
    lb_path = GAMES_DIR.parent / "leaderboard.csv"
    with open(lb_path, "w", newline="", encoding="utf-8") as f:
        if lb:
            writer = csv.DictWriter(f, fieldnames=list(lb[0].keys()))
            writer.writeheader()
            writer.writerows(lb)
    print(f"Wrote {lb_path}")


if __name__ == "__main__":
    main()
