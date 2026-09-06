# Pokémon TCG AI Battle Challenge — agent line V1→V27

Research/competition repo for the Kaggle **Pokémon TCG AI Battle Challenge**
(Simulation track: continuous skill-rating ladder, 6,715 teams; Strategy
track: research report, 341 teams). Built in an intensive 5-day sprint
(2026-08-11 → 2026-08-16) from a notebook baseline to a deep-tree search
agent with a learned evaluation function, an own engine build, and a
500K-game self-play pipeline.

**Strategy-track writeup:** [`reports/strategy_writeup_submission.md`](reports/strategy_writeup_submission.md)
(the submitted 1,806-word report) and
[`reports/strategy_writeup.md`](reports/strategy_writeup.md) (the full
technical version, ~4,400 words, with the complete evidence tables).

## Headline results

All ratings below are converged or settled readings from the live ladder.

| Agent | What it is | Ladder rating* |
|---|---|---|
| V6 | Hand-tuned heuristic (notebook lineage + Phantom Dive bug fixes) | 683.7 |
| V17 | Native C++ MCTS over the engine's search sandbox, V6 eval | 679.9 |
| V18 | + opponent-archetype determinization (V6 eval) | **506** — see below |
| V19 | Leader decklist ("Munkidori package") on the V6 engine | 674.6 |
| **V20** | + learned P(win) eval (XGBoost→static C++ arrays), PUCT, det voting | **691** |
| V23 | V20 with eval retrained on 212K own-engine self-play games | 595 |
| V24 | True multi-level PUCT tree, depth ~13 plies, learned leaf eval | 666 |
| V25 / V26 | Final pair: leader deck + tier-stratified eval | 587.5 / 601.3 |

\* Bayesian skill rating, μ0=600; frozen scores from different days are not
directly comparable (pool drift — documented in the report). Early readings
drift substantially: the final pair read 610/613 on deadline day and settled
two weeks later at 587.5/601.3.

## The central finding (ablation-proven)

Agent strength in this game is bounded by **evaluation quality**, not search
depth, rollout count, hidden-info modeling, or deck choice. Each factor was
isolated with a single-variable experiment:

- 2× simulation budget → no change; leader's exact deck (V19) → no change;
- better determinization with the OLD eval (V18): local gauntlet +6, real
  ladder **collapse to 506** — our reading is that search with a
  miscalibrated eval actively steers into its blind spots (optimizer's
  curse), and local opponents (relatives of the same policy) never punish
  what the diverse real pool punishes. Per-episode logs for that submission
  were not retained, so the rating is measured and the mechanism is our best
  explanation, not a demonstrated one;
- SAME search stack with a LEARNED eval (V20): **506 → 691**;
- depth has no fixed sign: the deep tree gained **+71** on a pool-matched
  eval (V24 vs V23) and lost **−87.1** on an off-distribution one
  (V25 vs V19).

## What we measured about measurement

The repo's most transferable result is quantified evidence on when local
evaluation of a card-game agent can be trusted — it could not be, here:

- a fixed archetype gauntlet correlates with real ladder rating at
  **r = 0.25** over 6 rated agents (ρ = 0.03; r = −0.28 excluding V18);
- a 192-game anchored round-robin against 8 of our own rated agents
  correlates at **r = −0.004** — zero to three decimals;
- the highest local win rate we ever recorded (57/60, V25) belongs to our
  second-worst agent on the ladder;
- an evaluator trained on leaders-only data scores AUC 0.833 on its home
  distribution and **0.736** on a neutral tier-stratified pool — a 10-point
  drop from evaluation ecology alone.

Negative results kept with mechanisms: naive behavioral cloning (46% top-1
imitation of top players) loses 0/6 even to the baseline (compounding
errors); minimax widening amplifies eval error; two generations of local
benchmarks (generic pilots AND imitation pilots) both ranked the
ladder-worst agent first — *a local benchmark measures strength against
your own assumptions about the game*.

## Repo layout

- `src/agents/` — the full agent line. `dragapult_policy_v6.py` (heuristic
  core), `dragapult_agent_v17_cpp/` … `_v27b_cpp/` (native search packages:
  single-TU C++, JIT-compiled at import; `tree_search.hpp` in v24+ is the
  deep PUCT tree; `pwin_trees.hpp` is the learned eval as static C++
  arrays), `bc_pilot_agent.py`, safety wrappers.
- `src/ml/` — 87-feature observation vectorizer, BC feature schema,
  dependency-free exported forests.
- `tools/` — experiment drivers: gauntlets, head-to-head runner, anchored
  round-robin (`anchored_rr.py`), self-play farm (`selfplay_worker.py`),
  dataset builders, trainers with exact-parity C++ export (`train_b1v4.py`,
  `export_b1_cpp.py`), submission packager, figure scripts.
- `reports/`, `results/` — every experiment's write-up and raw per-game
  data (fact/hypothesis-tagged; raw data is never discarded). Key evidence:
  `results/leader_diff/deck_diff.md` (per-team top-100 decklist diffs),
  `results/anchored_rr/` (all 192 games), `results/final_pair_episodes.json`
  (all 57 episodes of the final pair), `results/b1/b1v4_report.md`.
- `docs/` — engine/environment notes derived from source.

## What is deliberately NOT in this repo

The official competition engine (`cg` package, `cg.dll`/`libcg.so`, its C++
sources) and pulled competition data are **competition-use-only** and are
excluded via `.gitignore` (`data/`, `submission/`). To run anything here you
need your own copy of the engine from the competition's Data page placed
under `data/official/`. `src/agents/*_cpp/cpp/cg_engine.hpp` is our own thin
binding that calls the already-shipped engine binary through its public
`extern "C"` export table — nothing of the engine is re-linked, recompiled
or redistributed.

## Reproducing

```
python tools/build_submission_challenger.py --version v24   # package an agent
python tools/meta_gauntlet_v25.py                           # sanity gauntlet
python tools/hth_match.py --a v24 --b v23 --games 32        # head-to-head
python tools/anchored_rr.py                                 # the r = -0.004 result
python tools/train_b1v4.py                                  # retrain the eval
python tools/make_writeup_figures.py                        # writeup figures
```

Python 3.12; `xgboost`, `pandas`, `numpy` for training tooling only — the
shipped agents are dependency-free (learned forests are embedded as static
C++ arrays with bit-exact parity checks, incl. the float32-comparison
NEP-50 gotcha documented in `tools/export_b1_cpp.py`).
