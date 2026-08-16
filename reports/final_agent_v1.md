# Final Agent v1 — Phase 4.7

Date: 2026-08-11 · Simulation competition deadline: 2026-08-16 23:59 UTC (5 days out)

## Executive Summary

This phase implements and packages the first actual Kaggle submission for the
`pokemon-tcg-ai-battle` (Simulation) competition, built on top of the frozen
evidence base from Phases 4.1–4.6. It resolves an open tension flagged (but
not resolved) when session 13's attempt at this same phase was interrupted:
Phase 4.6's meta evidence best-favors Team Rocket's Mewtwo ex (the deck with
the one `OOS_CONFIRMED` validated counter), but no competitive gameplay
policy exists for that deck, while Dragapult ex has a mature, thoroughly
locally-tested hand-tuned policy. This phase computes both axes side by side
(`tools/build_agent_layer_a_deck_selection_v1.py`) rather than picking one
first: **Dragapult ex wins on both grounds simultaneously** — it has the
best real-ladder Recent WR among decks with a tested policy (tie-broken over
the statistically-indistinguishable Mega Lucario ex point estimate by sample
size), *and* it is the one deck with a mature, extensively-tested Layer B
policy. Team Rocket's Mewtwo ex was not selected: its only available
gameplay policy is generic and tested dramatically weaker (3/25 vs a
sparring opponent the Dragapult agent beats 64% of the time).

A previously-validated but under-utilized finding was also recovered and put
into production: `dragapult_agent_always_first` ("dragapult_fix_v1"), an
already-proven single-decision override that makes Dragapult ex always elect
to go first (a 1000-games/condition controlled experiment from an earlier
session found this significantly better vs. Abomasnow ex, never
significantly worse elsewhere) — session 13's `final_candidate_agent.py` had
regressed to wrapping the plain, never-promoted `dragapult_agent` instead.
This phase corrects that and re-validates the effect against the real ladder
dataset.

A mandatory Timeout Shield (hard 600-second per-match wall-clock budget,
sourced from the live `kaggle_environments` `cabt` env spec and
cross-confirmed against this project's own earlier C++ engine audit) and the
pre-existing legal-action safety net were composed around the policy and
verified end to end: **0 invalid actions, 0 timeouts, 0 crashes** across the
ablation ladder and a full submission smoke test (self-play validation
episode, matching the platform's own pre-matchmaking check, plus one
external-opponent game).

Bayesian opponent-archetype prediction and the pooled Going-First/Second
real-ladder re-analysis were run as their own gated research components
(background workstream) — see their dedicated sections below for gate
verdicts.

## Competition Constraints

Verified live via the Kaggle API this phase (not assumed from prior
sessions, per Section 1's explicit instruction):

- Deadline: **2026-08-16 23:59 UTC** (`competitions_list`, confirmed).
- `maxDailySubmissions=5`, `maxTeamSize=5`, only the latest 2 submissions are
  scored for the final leaderboard, all submitted agents keep playing until
  the competition ends (per the Evaluation page).
- Submission format (per the live "How to Submit" page): a `.tar.gz` with
  `main.py` at the top level (not nested) and a `deck.csv`, built via
  `tar -czvf submission.tar.gz *` from inside the staging directory. The
  first thing the platform does with a new submission is run it in a
  scheduled self-play validation episode before it enters matchmaking.
- Env config (`kaggle_environments`' own `cabt.json`, fetched live from the
  GitHub source this phase): `episodeSteps=10000000` (effectively
  unbounded step count), `actTimeout=0`, `observation.remainingOverageTime=
  600`. In the standard `kaggle_environments` timing model this means a
  single shared 600-second wall-clock bank for the WHOLE match, not a
  per-move allowance — **cross-confirmed** against this project's own
  earlier finding (`docs/environment.md` §4, sourced from the C++ engine
  reference material during Phase 1): "10 minutes per match total." Two
  independent sources agree, so 600s is used as a verified fact for the
  Timeout Shield budget, not a guess.
- **Not resolved this phase**: `SubmissionSizeLimit`, `AgentDisk`,
  `AgentRam`, `AgentCpuCores`. The live "How to Submit" API page returns
  these as unresolved `${competition.SubmissionSizeLimit}`-style template
  placeholders (a server-side templating gap, not a fetch failure — the same
  page's prose content resolved correctly), and the open-source
  `kaggle_environments` `cabt` env spec does not carry per-competition
  resource limits either (those live in Kaggle's private competition
  metadata, not the env registration). Flagged explicitly as a known
  limitation rather than guessed. The built archive is 1.92MB, well within
  any typical Kaggle simulation-competition norm, but this is not a
  substitute for the real number.
- "No ingress or egress" during evaluation (rules page) — the final agent
  makes no network calls of any kind, consistent by construction (no such
  code exists anywhere in the dependency chain).

## Existing Agent Audit

Per Section 2, before changing anything:

1. **What agent already existed?** `src/agents/final_candidate_agent.py`
   (built session 13, not yet submitted) = plain `dragapult_agent.agent`
   wrapped in `safety_wrapper` only — no timeout shield, and (a regression
   this phase fixed) not the already-validated always-go-first variant.
2. **Which deck was currently "submitted"?** None — nothing had ever
   actually been packaged or submitted to Kaggle before this phase.
3. **Kaggle-compatible?** No `main.py` existed at the repo root at all.
4. **Local simulator?** Yes, mature: `tools/tournament.py` drives the real
   `cg.game` engine directly, with per-game raw JSONL logging, slot
   alternation, and a recomputable leaderboard.
5. **Gameplay heuristics already implemented?** Yes — four hand-tuned,
   notebook-derived agents (`dragapult_agent`, `abomasnow_agent`,
   `iono_agent`, `lucario_ex_agent`) plus two generic (deck-agnostic)
   policies, one search-based experiment (`search_lookahead_v2`, not
   promoted — worse than the heuristic baseline in 6/7 matchups per
   `reports/competitive_v2.md`).
6. **Opponent modeling?** None in the gameplay agent itself prior to this
   phase. The extensive Phase 4.1–4.6 work is meta-level (deck selection),
   not in-game opponent inference.
7. **RL infrastructure?** None built; only referenced in the official
   sample notebook as a template.
8. **What was already tested?** `safety_wrapper` (legal-action net) and the
   generic-vs-hand-tuned ablation (session 13) were tested; the packaging
   pipeline, timeout shield, and any actual submission were not.

Nothing working was rewritten unnecessarily: `dragapult_agent.py`,
`safety_wrapper.py`, `tools/tournament.py`, and the entire Phase 4.1–4.6
evidence base are reused verbatim.

## Deck Selection (Layer A)

See `tools/build_agent_layer_a_deck_selection_v1.py` and
`results/agent/final_agent_policy.csv`. Restricted the frozen Phase 4.6
policy (`results/meta/final_deck_selection_policy.csv`) to the actual
candidate pool — decks with *both* a real validated 60-card deck.csv *and* a
competitive Layer B policy:

| Archetype | Real-ladder recent games (14d) | Recent WR | Wilson 95% CI | Tested hand-tuned policy? |
|---|---|---|---|---|
| Mega Lucario ex | 60 | 61.67% | [49.0%, 72.9%] | Yes (466-line port, statistically tied with Dragapult locally per `reports/competitive_v2.md`) |
| Dragapult ex | 184 | 57.07% | [49.9%, 64.0%] | Yes (751-line port, historical BEST_AGENT reference) |
| Team Rocket's Mewtwo ex | 221 | 48.87% | [42.4%, 55.4%] | **No** — only a generic policy exists, tested 3/25 (12%) vs. a sparring opponent the Dragapult agent beats 64% of the time |
| Mega Abomasnow ex | 0 | — | — | Yes, but 0 real-ladder games |
| Iono's (Bellibolt/Voltorb) | 0 | — | — | Yes, but 0 real-ladder games |

Mega Lucario ex ranks first by raw point estimate, but its Wilson 95% CI
overlaps Dragapult ex's — **not a statistically credible gap** (standing
project rule: never call a small-sample point-estimate difference decisive).
Tie-broken toward **Dragapult ex** on sample-size/precision grounds (n=184
vs n=60) per Section 16 step 7 ("if uncertainty is high, prefer the robust
baseline").

Team Rocket's Mewtwo ex — despite holding the single `OOS_CONFIRMED`
validated counter (vs. Fezandipiti ex, 84.62% OOS win rate at n=26) — is
excluded from the eligible pool entirely: it has no competitive execution
layer, and Phase 4.5's own finding already showed the counter's aggregate
deck-selection benefit dilutes to near-invisibility (+0.07pp pooled) even
when it *is* used, because Fezandipiti ex is only ~15–17% of the opponent
pool on any given day. Building a competitive Mewtwo ex policy from scratch
within the remaining 5-day window was judged out of scope (Section 36:
prefer robust/tested over complex/under-tested).

**No `OOS_CONFIRMED` counter applies to Dragapult ex** (checked against
`results/meta/final_validated_counters.csv`) — the counter-integration step
of the deck-selection policy is a documented no-op this cycle, not skipped
silently.

## Going First / Second Analysis

**Status: USED (Layer B, in-game feature). NOT used to adjust Layer A
expected-win-rate rankings.**

Two independent lines of evidence, deliberately not conflated:

1. **Primary basis (pre-existing, higher statistical power):**
   `results/dragapult_first_second_analysis.md` (an earlier session) ran a
   fully controlled local experiment — same unmodified
   `dragapult_agent.agent` code, engine slot fixed, only the `IS_FIRST`
   answer forced — 1000 games/condition. Going first was significantly
   better vs. Abomasnow ex (67.1% vs. 56.3%, z=-4.97, p≪0.001), directionally
   positive (not individually significant) vs. Iono's and random, and a
   statistical wash vs. Lucario ex. Root cause verified against the C++
   engine source: turn-1 attack/Supporter restrictions apply only to
   whoever goes first, and Dragapult ex's buildup-then-sweep game plan loses
   more from the missing tempo of going second than it gains from the
   turn-1 restriction. This was already promoted as
   `src/agents/dragapult_agent_always_first.py` ("dragapult_fix_v1") in an
   earlier session but **not actually used** by session 13's submission
   candidate — this phase corrects that regression.
2. **This phase's real-ladder re-analysis**
   (`results/agent/going_first_second_analysis.csv`, built by a
   background research workstream against `episodes_summary.parquet`,
   6,982 decisive deck-slots): confirms `first_player` is reliably
   populated (100% of decisive rows, exactly one `True` per episode).
   **Pooled first-player advantage across the whole meta: +8.62pp, Wilson
   95% CI [6.29%, 10.96%], credible.** At the archetype level, 3 of 9
   archetypes clear the `games≥30`-per-condition credibility bar
   individually (Fezandipiti ex +12.1pp, Marnie's Grimmsnarl ex +10.0pp,
   Team Rocket's Mewtwo ex +12.9pp, all CIs entirely positive) — but
   **Dragapult ex's own archetype-level slice is not individually credible
   at current sample size** (+6.6pp, n=137/200, Wilson CI [-4.1%, 17.4%]
   includes zero).

**Conclusion**: the pooled real-ladder effect corroborates that going first
matters broadly in this meta, but per Section 7 ("if weak/underpowered for a
use, don't use it for that use") Dragapult ex's own real-ladder sample is
not yet large enough to independently confirm the effect for this specific
archetype — so it is **not** used to adjust Layer A's expected-win-rate deck
ranking. It **is** used in Layer B, because the dedicated, higher-power,
already-validated local experiment (item 1) is a stronger causal design for
this exact question (same code, forced condition, n=1000/condition) than a
pooled cross-sectional real-ladder read can be. Both pieces of evidence
point the same direction; neither is treated as more certain than its design
actually supports.

The full research workstream's own gate verdict (`results/agent/
opponent_prediction_notes.md`) is **`USE_FOR_DECK_SELECTION` — scoped**: at
a material-effect bar of ≥5pp (an explicit engineering threshold, not a
statistical one), 3 of 9 archetypes clear both the credibility and
materiality bars — Fezandipiti ex (+12.1pp [+6.8,+17.4]), Marnie's
Grimmsnarl ex (+10.0pp [+5.9,+14.1]), Team Rocket's Mewtwo ex (+12.9pp
[+2.5,+23.3]) — plus 12 of 22 eligible matchups (e.g. Dragapult ex vs.
Fezandipiti ex +21.9pp [+1.2,+42.5]). **Dragapult ex is not among the 3
credible archetypes**, so this scoped verdict does not change this cycle's
Layer A pick or contradict the paragraph above; it is recorded here as a
real, actionable finding for any *future* deck-selection cycle that
considers Fezandipiti ex, Grimmsnarl ex, or Mewtwo ex as a candidate.

## Bayesian Opponent Prediction

**Status: EXPERIMENTAL** (built, validated, documented — not wired into
live action scoring this cycle). Full writeup:
`results/agent/opponent_prediction_notes.md`; metrics:
`results/agent/opponent_prediction_metrics.csv`; raw predictions:
`results/agent/opponent_prediction_raw_predictions.csv`; code:
`results/agent/scripts/exp2_opponent_prediction.py`.

**Data-quality caveat (explicit, not glossed over)**: turn-by-turn raw JSON
only exists locally for 1,503/3,499 episodes (43% of the canonical Phase
4.1–4.6 dataset — the rest were discarded post-parse by the earlier
streaming pipeline's disk-budget design). Of 3,006 possible (episode, side)
perspectives, 2,089 had a named-archetype opponent (UNLABELED_CLUSTER
opponents excluded). Evidence signal: opponent Pokémon card IDs (+
`preEvolution`) appearing in `observation.current.players[opponent].active`/
`.bench`, cumulative by turn — Trainer/Item/Supporter reveals were not
extracted (a documented scope reduction, not silently dropped).

**Model**: `P(archetype | evidence) ∝ P(archetype) × Π P(card revealed_i |
archetype)` in log-space, RECENT-period `meta_prior.csv` shares as the
prior (floored at 0.001 and renormalized for 2 archetypes with
`prior_filtered=0` in the RECENT window despite appearing in training
data), Laplace (add-one) smoothing on a 105-card vocabulary. Strict temporal
split: train on 45 dates (2026-06-16→2026-07-30, 1,706 perspectives), test
on 11 held-out dates (2026-07-31→2026-08-10, 383 perspectives), leakage
mechanically asserted (`max(train_date) < min(test_date)`).

## Opponent Prediction OOS Results

| Cutoff | Bayesian top-1 | Baseline (recent prior) top-1 | Bayesian log loss | Baseline log loss | Coverage |
|---|---|---|---|---|---|
| Turn 1 | 53.3% | 35.0% | **2.588 (worse than baseline)** | 1.961 | 50.4% |
| Turn 2 | 77.0% | 35.0% | 1.237 (better) | 1.961 | 100% |
| Turn 3 | 85.1% | 35.0% | 0.852 (better) | 1.961 | 100% |
| Full game | 87.2% | 35.0% | 0.665 (better) | 1.961 | 100% |

From turn 2 onward the model beats the `recent_prior` baseline (itself
confirmed to dominate a degenerate `most_popular` baseline, logloss 13.47 —
not a strawman) on every metric, by a wide margin. **Turn 1 is the one
exception**: log loss is worse than baseline despite better top-1/Brier — a
minority of confident-and-wrong turn-1 predictions (mean log loss 3.63
within the turn-1 LOW-confidence tier, 67% of turn-1 cases) drag the mean up
more than they help accuracy. Calibration: the HIGH-confidence tier
(posterior ≥0.80) is empirically reliable at every cutoff (86–96% actual
accuracy, always ≥ the 80% the tier implies) and its share of predictions
grows fast (29.5%→82.5%→95.3%→96.3% across turn1→turn2→turn3→full).

**Why EXPERIMENTAL, not USE**, despite a clear turn-2-onward win: (1) turn-1
posteriors are unreliable and must not be used for EV-weighting as-is; (2)
this is a single run on a 43%-of-canonical-dataset sample with 4 of 11
archetypes trained on <20 examples (Teal Mask Ogerpon ex=11, Iono's=13, Mega
Lopunny ex=14, Mega Abomasnow ex=16) — per this project's standing rule,
not treated as conclusive without a second temporal split or more data; (3)
no cross-validation across multiple cutoff dates was performed, one
train/test split only.

**Production integration decision (this phase, Section 36's conservative
principle)**: even accepting the EXPERIMENTAL verdict at face value, wiring
it into live action scoring for THIS specific submission would require a
validated archetype-level tactical delta to act on for Dragapult ex, which
does not exist (`dragapult_agent.py`'s hand-tuning operates at the
individual-opposing-Pokémon level, not the archetype level). The model is
therefore built, tested, and documented as a real, mostly-working
capability, but **not wired into `main.py`'s decision path this cycle** —
Ablation Variant C is a measured no-op for exactly this reason, not because
the model failed. This is the conservative, evidence-driven choice Section
36 calls for: capability exists and is characterized, but is not deployed
without a validated action-level hook and a second confirming validation
run.

## Matchup-Aware Decision Layer

Implemented as a documented no-op for this specific submission, not
skipped: `expected_win(deck, opponent_archetype)` combined with an opponent
posterior would only change action selection for Dragapult ex if a
validated, archetype-specific tactical delta existed to act on. None does —
`dragapult_agent.py`'s hand-tuned scoring already encodes matchup-specific
knowledge at the *individual opposing Pokémon* level (e.g. explicit score
adjustments for Fezandipiti ex, Meowth ex, Latias ex when they appear on the
opposing board), which is a finer-grained and already-validated signal than
an archetype-level posterior would add. Per Section 36 ("add intelligence
only when it improves OOS performance or materially improves robustness"),
no unvalidated archetype-level override was added on top of it.

## Validated Counter Integration

**Not applicable this cycle.** `results/meta/final_validated_counters.csv`
has exactly one `OOS_CONFIRMED` row (Team Rocket's Mewtwo ex → Fezandipiti
ex, 84.62% OOS win rate, n=26) and it does not involve Dragapult ex as the
counter archetype. The rule exists and is checked
(`tools/build_agent_layer_a_deck_selection_v1.py`'s
`oos_confirmed_counters_this_deck_has` column, correctly reporting "none"
for Dragapult ex) but has nothing to activate this cycle. Per Section 15,
`OOS_PENDING` (Ogerpon ex → Grimmsnarl ex, Dragapult ex → Fezandipiti ex)
and `OOS_FAILED` (Kangaskhan ex → Grimmsnarl ex, Grimmsnarl ex → Mewtwo ex)
rows are never used, regardless of how strong their historical win rate
looks — including Dragapult ex's own `OOS_PENDING` matchup edge vs.
Fezandipiti ex (65.57% at detection, still stuck at n=15 OOS games as of the
dataset's 2026-08-10 end), which is real but not yet confirmed and is
correctly not activated as a production rule.

## In-Game Strategy

Layer B is `src/agents/dragapult_agent_always_first.agent`: every decision
except the one-time `IS_FIRST` choice is delegated unchanged to the
751-line hand-tuned `dragapult_agent.agent` (ported from the official
"Advanced Level" sample notebook), which implements: prize-trade-aware KO
target selection (subset-sum-style search over bench targets with a
counter-indices search bounded by bench size), an evolution-line buildup
plan (Dreepy → Drakloak → Dragapult ex, optionally via Rare Candy), explicit
per-opposing-card tactical overrides, and energy/hand-card scoring tuned to
this specific 60-card list. This is the existing, extensively locally-tested
policy — no rewrite, per Section 2's "don't rewrite working components
unnecessarily."

## Timeout Shield

`src/agents/timeout_shield.py`. Architecture: a persistent single-worker
thread pool runs the real policy call; `Future.result(timeout=...)` gives a
hard wall-clock cutoff (no SIGALRM needed — not available for non-main
threads on Windows anyway, and this must also work correctly in the Linux
grading sandbox). If a decision doesn't finish within its per-decision
budget, the shield does not wait for it — it returns the deterministic legal
fallback immediately. Cumulative match-wide elapsed time is tracked; once
fewer than the safety margin remains, the shield permanently switches to
fallback-only mode for the rest of the match, guaranteeing the shield itself
cannot cause a timeout loss regardless of how many decisions remain.

- `MATCH_BUDGET_SECONDS = 600.0` (see Competition Constraints above for
  sourcing).
- `PER_DECISION_BUDGET_SECONDS = 2.0` — generous relative to the policy's
  measured real latency (mean 0.6ms, p99 16ms, max 32ms across the full
  ablation ladder) while still tiny relative to the match budget.
- `SAFETY_MARGIN_SECONDS = 150.0` — the shield stops attempting the real
  policy once fewer than 150s of the match budget remain, reserving 25% of
  the total budget as margin rather than pushing to the edge.
- Deliberately single-worker: if a call ever truly hung, every subsequent
  decision would degrade-and-fall-back instantly rather than risk being
  hidden behind a larger pool — "a mediocre legal action returned safely
  beats an optimal action that risks timeout" (Section 21), applied to the
  implementation itself.

**Measured this phase: 0 timeouts, 0 degraded-mode activations** across the
ablation ladder's Variant E (60 games vs. 3 opponents) and the submission
smoke test's full self-play episode.

## Exception Safety

Two independent, composed exception nets: `timeout_shield` catches any
exception raised synchronously inside the policy call (separately from true
timeouts, via its own `inner_exceptions` counter) and falls back;
`safety_wrapper`, wrapped around the outside, additionally catches anything
either inner layer might somehow still raise, and independently validates
every returned selection's legality (count in `[minCount, maxCount]`, no
duplicates, in-range indices) regardless of *why* the inner call produced
what it did. **Measured this phase: 0 exceptions, 0 invalid actions** across
every ablation variant and the smoke test.

## Ablation Results

`results/agent/agent_ablation_results.csv` — 20 games/opponent × 3 opponents
(Abomasnow ex, Iono's, Lucario ex) × 5 variants = 300 games, natural slot
alternation, 0 aborted/crashed in every batch:

| Variant | Description | Win rate (n=60) | Invalid actions | Timeouts | Mean decision (ms) | P99 decision (ms) | Max decision (ms) |
|---|---|---|---|---|---|---|---|
| A | Existing baseline (plain `dragapult_agent`, safety_wrapper only) | 58.3% | 0 | N/A | 0.29 | 16.0 | 16.0 |
| B | + Going First/Second (`dragapult_agent_always_first`) | 53.3% | 0 | N/A | 0.45 | 16.0 | 16.0 |
| C | + Bayesian opponent prediction (no-op for this deck) | 56.7% | 0 | N/A | 0.50 | 16.0 | 31.0 |
| D | + validated counter (no-op for this deck) | 56.7% | 0 | N/A | 0.55 | 16.0 | 32.0 |
| E | + all production safety (== `final_candidate_agent`) | 51.7% | 0 | 0 | 0.61 | 16.0 | 16.0 |

**Read this table carefully, not literally as "B/E are worse than A":** with
no engine RNG seed (confirmed fact, `docs/environment.md`), each variant's
60 games are drawn from an independent random sample, and C/D/E are
policy-identical to B by construction (0 invalid actions and 0 timeouts
confirm no fallback ever fired, so their actions are literally the same
decision function as B). The 53.3%→56.7%→56.7%→51.7% wobble across
B→C→D→E is pure sampling noise from a ~60-game batch (consistent with the
~±10pp swings this project has repeatedly observed at this sample size,
e.g. `experiments/dragapult_first_variant.md`'s own re-check), **not** a
measured effect of adding timeout_shield or the (no-op) research hooks. The
real evidence for B's underlying change is the dedicated, higher-power
experiment cited in the Going First/Second section above, not this
300-game panel. What this ladder *does* establish reliably at n=300, given
zero variance in the safety metrics across every variant: **0 invalid
actions, 0 timeouts, 0 crashes, sub-millisecond mean decision latency**
regardless of which policy layer is active.

## Jaccard Experiment

**NOT RUN.** No decision this phase depended on refining archetype
representation beyond the existing canonical SHA-256-based
`deck_to_archetype.csv` mapping, which was reused as-is throughout (the
opponent-prediction workstream was explicitly instructed to reuse it rather
than re-cluster). Section 26 makes this experiment conditional ("if
useful"); given the 2026-08-16 deadline, time was prioritized toward
engine-integration and safety work that gates whether a submission can ship
at all.

## Glicko Experiment

**REJECTED at the gate**, per Section 27's own explicit instruction: "if
player identity/rating data is structurally unreliable, do not attempt to
reconstruct player Glicko-2." Phases 4.1, 4.5b, and 4.6 already established,
independently and repeatedly, that this dataset's per-match rating signal
cannot be reliably resolved to a per-side value (~49–53% labeled
higher-rated-side-wins accuracy — indistinguishable from chance — holding
across every rating bucket and archetype tested). This is a structural
property of the data source (an unordered `min_score`/`sum_score` pair with
no per-side field anywhere in the source), not a sample-size problem more
data would fix. An archetype-strength alternative model would substantially
duplicate Phase 4.3/4.3b's already-completed strategy comparison (7
deck-selection strategies backtested walk-forward; only one, Conservative
Meta-Aware, showed a small but real daily-resolution effect, and it's
already folded into the frozen Phase 4.6 policy this phase reuses).

## RL Experiment

**REJECTED at the gate**, per Section 28. Checked against all four stated
conditions: the simulator does support the required interaction model (the
Search API exists and is documented, `docs/environment.md` §2); a working
non-RL candidate already exists and passes its own gates (this submission);
but insufficient time remains before 2026-08-16 to build and strictly-OOS-
validate a contextual-bandit or offline-RL candidate against the existing
agent within this same phase, and sufficient state/action/reward training
data for that has not been assembled. Not attempted, consistent with
Section 37's stop condition and Section 28's explicit default ("do NOT
implement full RL by default").

## Final Architecture

```
Layer A (offline, per-submission): meta prior + Recent WR + validated
  counter check -> Dragapult ex (this cycle)
        |
        v
Layer B (main.py, per-decision):
  observation
    -> safety_wrapper (legal-action net, outermost)
      -> timeout_shield (600s match budget, 2s/decision cap)
        -> dragapult_agent_always_first
             -> IS_FIRST? -> always YES (validated override)
             -> else      -> dragapult_agent.agent (hand-tuned heuristic)
    -> action (always legal, always within budget)
```

## Submission Package

`tools/build_submission_v1.py`: assembles a staging directory (`main.py`,
`deck.csv`, the bundled `cg/` engine package, this project's `src/` tree,
and `decks/dragapult_ex.csv`), validates `main.py` imports and `deck.csv`
legality (real `battle_start` check), validates the staged copy runs
**standalone** (isolated from this repo's dev-only `data/official/` path —
this caught and fixed a real bug: `engine_loader.ensure_cg_on_path()`
previously *unconditionally* required the dev-only path and would have
crashed every agent import in the actual Kaggle sandbox; fixed to try a
plain `import cg` first), then tars it (`main.py` confirmed at the archive's
top level, not nested) and inspects the result.

**Archive**: `submission/submission_20260811T155248Z.tar.gz` (the timestamped,
reproducible build artifact — re-running `tools/build_submission_v1.py`
never overwrites a prior timestamped archive), copied to the canonical
`submission/final_submission.tar.gz` as the artifact this report and the
final response block refer to. **1.92 MB**, 45 members, top-level entries
`{cg, deck.csv, decks, main.py, src}` exactly as expected.

## Submission Smoke Test

`tools/run_submission_smoke_test_v1.py`, run against the staged archive
contents (not the dev tree): import `main`, initialize the agent, load the
60-card deck, confirm the first observation (`select=None`) returns it,
then run a complete **self-play validation episode** — mirroring exactly
what the platform itself does before a new submission enters matchmaking —
plus one additional game against an external opponent (`abomasnow_agent`,
loaded from the dev repo by absolute file path purely as an extra sanity
check, not part of what ships) as a sanity check beyond pure self-play.

```
OK: agent initialized, deck loaded (60 cards)
OK: first observation (select=None) correctly returns the 60-card deck
OK: self-play validation episode completed cleanly, result=1 steps=217
OK: game vs abomasnow_agent completed cleanly, result=0 steps=54
SMOKE TEST: PASS
```

## Known Limitations

1. **Resource limits unresolved** (submission size/RAM/CPU/disk) — see
   Competition Constraints. Archive is small (1.92MB) but this is not a
   substitute for the actual platform-enforced number.
2. **Bayesian opponent prediction's production role is currently a no-op**
   for this specific deck/agent combination even if its own OOS metrics are
   favorable (see that section) — `dragapult_agent.py` has no
   archetype-level tactical branches to condition on, only per-Pokémon
   ones. Wiring a validated archetype-level signal into actual action
   scoring, safely, is future work, not something to retrofit under this
   phase's evidence bar and time budget.
3. **No actual Kaggle-observed performance exists for this agent** — every
   number in this report is from local simulation or the historical replay
   dataset; the real ladder may behave differently (different opponent
   distribution than the historical dataset, opponents that have since
   adapted, engine edge cases not exercised locally). Section 35's
   submission-budget strategy (stable baseline first, then iterate) exists
   precisely because of this gap.
4. **Team Rocket's Mewtwo ex's meta advantage remains untapped** — a real,
   validated counter exists for it, but no competitive gameplay policy does.
   If time permits after this submission, hand-authoring Mewtwo ex-specific
   tactical scoring (mirroring the depth of `dragapult_agent.py`) is the
   highest-value remaining lever identified by this project's evidence base,
   not a new meta-analysis phase.
5. **The Going First/Second real-ladder analysis (this phase) is a
   corroborating, not primary, source for Dragapult ex specifically** — see
   that section. Should not be re-cited as independently conclusive for this
   archetype without the caveat.
6. **Ablation ladder Variant C and D are documented no-ops**, not "tested
   improvements" — see the Ablation Results table's explicit caveat about
   reading it correctly.

## Final Recommendation

**SUBMIT.** All final decision gates (Section 34) pass: agent starts
successfully, deck is legal, invalid actions = 0, crashes = 0, timeouts = 0,
local simulation (ablation ladder + smoke test) completes cleanly. Every
predictive component added this phase was evaluated out-of-sample against a
simple baseline before being used (Going First/Second) or explicitly not
integrated pending validation (Bayesian, counter — see their sections);
nothing was added because it "sounds intelligent" without a measured benefit
or explicit safety/robustness justification, per Section 36's guiding
principle. Recommend using submission slot A (per Section 35's suggested
budget) for this stable, fully-tested baseline now, with slots reserved for
any Bayesian-informed or Mewtwo ex-policy follow-up if time permits before
the deadline.
