# Pokémon TCG AI Battle Challenge — agent line V1→V24

Research/competition repo for the Kaggle **Pokémon TCG AI Battle Challenge**
(Simulation track: continuous skill-rating ladder, 6,715 teams; Strategy
track: research report). Built in an intensive 5-day sprint (2026-08-11 →
2026-08-16) from a notebook baseline to a deep-tree search agent with a
learned evaluation function, an own engine build, and a 500K-game self-play
pipeline.

## Headline results

| Agent | What it is | Ladder rating* |
|---|---|---|
| V6 | Hand-tuned heuristic (notebook lineage + Phantom Dive bug fixes) | 683.7 |
| V17 | Native C++ MCTS over the engine's search sandbox, V6 eval | 679.9 |
| V18 | + opponent-archetype determinization (V6 eval) | **506** — see below |
| V19 | Leader decklist ("Munkidori package") on the V6 engine | 674.6 |
| **V20** | + learned P(win) eval (XGBoost→static C++ arrays), PUCT, det voting | **~705** |
| V23 | V20 with eval retrained on 212K own-engine self-play games | (deadline day) |
| V24 | True multi-level PUCT tree, depth ~13 plies, learned leaf eval | (deadline day) |

\* Bayesian skill rating, μ0=600; frozen scores from different days are not
directly comparable (pool drift — documented in the report).

## The central finding (ablation-proven)

Agent strength in this game is bounded by **evaluation quality**, not search
depth, rollout count, hidden-info modeling, or deck choice. Each factor was
isolated with a single-variable experiment:

- 2× simulation budget → no change; leader's exact deck (V19) → no change;
- better determinization with the OLD eval (V18): local gauntlet +6, real
  ladder **collapse to 506** — search with a miscalibrated eval actively
  steers into its blind spots (optimizer's curse), and local opponents
  (relatives of the same policy) never punish what the diverse real pool
  punishes;
- SAME search stack with a LEARNED eval (V20): **506 → 705**.

Negative results kept with mechanisms: naive behavioral cloning (46% top-1
imitation of top players) loses 0/6 even to the baseline (compounding
errors); minimax widening amplifies eval error; two generations of local
benchmarks (generic pilots AND imitation pilots) both ranked the
ladder-worst agent first — *a local benchmark measures strength against
your own assumptions about the game*.

## Repo layout

- `src/agents/` — the full agent line. `dragapult_policy_v6.py` (heuristic
  core), `dragapult_agent_v17_cpp/` … `_v24_cpp/` (native search packages:
  single-TU C++, JIT-compiled at import; `tree_search.hpp` in v24 is the
  deep PUCT tree), `bc_pilot_agent.py`, safety wrappers.
- `src/ml/` — 87-feature observation vectorizer, BC feature schema,
  dependency-free exported forests.
- `tools/` — experiment drivers: gauntlets, head-to-head runner, self-play
  farm (`selfplay_worker.py`), dataset builders, trainers with exact-parity
  C++ export (`train_b1v2.py`, `export_b1_cpp.py`), submission packager.
- `reports/`, `results/` — every experiment's write-up and raw per-game
  data (fact/hypothesis-tagged; raw data is never discarded).
- `docs/` — engine/environment notes derived from source.

## What is deliberately NOT in this repo

The official competition engine (`cg` package, `cg.dll`/`libcg.so`, its C++
sources) and pulled competition data are **competition-use-only** and are
excluded via `.gitignore` (`data/`, `submission/`). To run anything here you
need your own copy of the engine from the competition's Data page placed
under `data/official/`.

## Reproducing

```
python tools/build_submission_challenger.py --version v24   # package an agent
python tools/meta_gauntlet_v24.py                            # sanity gauntlet
python tools/hth_match.py --a v24 --b v23 --games 32         # head-to-head
python tools/selfplay_worker.py --worker-id 0 --own-cg-dir <own engine copy>
python tools/train_b1v2.py                                   # retrain the eval
```

Python 3.12; `xgboost`, `pandas`, `numpy` for training tooling only — the
shipped agents are dependency-free (learned forests are embedded as static
C++ arrays with bit-exact parity checks, incl. the float32-comparison
NEP-50 gotcha documented in `tools/export_b1_cpp.py`).
