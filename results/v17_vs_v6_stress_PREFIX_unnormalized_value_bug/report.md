# V17 (C++ MCTS) vs V6 (Python Heuristic) -- Local Stress Test Report

**Claim key**: F = verified fact (directly measured this run), H = hypothesis/interpretation.

- [F] Games requested: 200. Games accounted for: 200. Decided: 200. Draws: 0. Aborted (non-crash): 0. Worker crashes: 0.
- [F] Both agents run through the real submission composition (`final_candidate_agent_v17`/`v6`: safety_wrapper -> timeout_shield -> policy), the same one Kaggle would invoke -- not the bare policy functions.
- [H] This is a single 200-game local run against each other, not the Kaggle ladder meta -- see feedback_ptcg_process.md point 3. Do not read this as a ladder-strength claim, only as a same-deck architecture A/B result.

## Overall Win Rate

| Agent | Wins | Win Rate (of decided games) |
|---|---|---|
| V17 (C++ MCTS) | 44 | 22.0% |
| V6 (Python Heuristic) | 156 | 78.0% |

## Coin-Toss / Positional Control

- [F] Intended split: V17 assigned engine slot 0 (goes first) in 100 games; V6 in 100 games.
- [F] Verified against the engine's own reported `first_player_slot` (not assumed, per feedback_ptcg_process.md point 2): of 200 games with a recorded result, engine slot 0 actually went first in 200 of them (0 where a slot other than 0 went first -- would indicate the always-answer-yes assumption broke for one agent).
- [F] V17 therefore actually went first in 100 games (intended: 100).

| | V17 win rate as Player 1 (went first) | V17 win rate as Player 2 (went second) |
|---|---|---|
| V17 | 22/100 (22.0%) | 22/100 (22.0%) |

## Average Game Length (turns, wins only)

| Agent | Avg turns in its own wins |
|---|---|
| V17 | 14.8 |
| V6 | 12.0 |

## Win Conditions (decided games)

| Condition | Count |
|---|---|
| All Prizes Taken | 157 |
| Deck Out | 1 |
| No Active Pokemon | 42 |
| Card Effect | 0 |
| Unknown | 0 |

## Search Engagement (is MCTS actually running?)

Added after discovering the original 1000-game run's test harness stripped `search_begin_input` before every agent call (a tools/tournament.py-local artifact, not present on the real Kaggle path -- see tools/stress_test_v17.py's `_play_one_game_keep_search_input` docstring), which silently made every decision fall through to the plain V6-greedy fallback with 0% search eligibility. Fixed for this run.

- [F] Total V17 decisions: 12234
- [F] Eligible for search (`context==MAIN`, `maxCount==1`, `options>=2`): 6291 (51.4%)
- [F] Eligible AND `search_begin` succeeded (a real MCTS search actually ran): 6291 (100.0% of eligible)
- [F] Decisions where `timeout_shield`'s own future timed out on this exact call (see `timed_v17`'s docstring in the script -- the shared `LAST_CALL_STATS` read would otherwise risk pairing this decision's fast fallback time with a different, still-finishing call's stats): 0 (excluded from eligible/searched counts and from the timing/visits stats below, not counted as ineligible)

- [F] Rollouts/simulations completed per searched decision: mean=98.8, min=28, max=2156, p50=70, p95=237

## V17 Execution Metrics (per-decision wall-clock time, full submission-wrapped call)

- [F] All V17 decisions (including instant non-eligible ones): mean=363.72 ms, min=0.19 ms, max=783.85 ms, p50=701.52 ms, p95=711.12 ms, p99=713.61 ms
- [F] Decisions where a real search ran only: mean=706.12 ms, min=700.82 ms, max=783.85 ms, p50=705.44 ms
- [F] Per-decision Kaggle-equivalent budget: 2.0s (`timeout_shield.PER_DECISION_BUDGET_SECONDS`). Max observed (783.85 ms) is WITHIN budget.

- Raw per-decision timings (never aggregated-away): `results\v17_vs_v6_stress\v17_decision_times.csv`

## Stability Audit

- [F] Worker process crashes (native access violation / process death -- caught at the process boundary, see `results\v17_vs_v6_stress\crashes.jsonl`): **0**
- [F] Games lost/aborted directly due to a crash: 0
- [F] Games aborted for a non-crash reason (Python exception caught by the game loop's own try/except, or `max_steps` exceeded): 0
- [F] V17 `timeout_shield` timeouts (a single decision exceeded its 2.0s budget and was force-defaulted): 0
- [F] V17 `timeout_shield` inner exceptions (the wrapped agent itself raised, caught and defaulted): 0
- [F] V17 `timeout_shield` permanent-degrade-mode activations (would indicate a match-budget exhaustion; per-game budget reset applied after every game, see script docstring): 0
- [F] V17 `safety_wrapper` fallback-used count (final backstop: illegal/invalid selection from the inner agent, replaced with a safe legal default): 0

## Raw Data

- Per-game results (one JSON object per line, dense over game_index 0..199): `results\v17_vs_v6_stress\raw_games.jsonl`
- Per-decision V17 timings: `results\v17_vs_v6_stress\v17_decision_times.csv`
- Crash log: none written (zero crashes)

Per project convention (feedback_ptcg_process.md point 1), this is preliminary/first-run data: raw per-game data is preserved above for any larger follow-up evaluation, and this report should not be treated as final statistical proof beyond what N=200 decided games actually supports.