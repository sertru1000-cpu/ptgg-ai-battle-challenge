# Prompt 4.7 Evidence: Going-First/Second + Bayesian Opponent Prediction

Research-only deliverable. Scripts: `results/agent/scripts/exp1_going_first_second.py`,
`results/agent/scripts/exp2_opponent_prediction.py`. No agent/gameplay code touched.

## Experiment 1: Going First / Second

**Verified fact.** `results/meta/episodes_summary.parquet` has 6,982 `DECISIVE` rows /
3,491 episodes. `first_player` is populated (non-null) on all 6,982 decisive rows, and
for all 3,491 decisive episodes exactly one side has `first_player=True` (mechanically
checked via `groupby(episode_id)['first_player'].sum() == 1` for 3,491/3,491 episodes).
Pairing is clean; the field is reliable.

**Measured result — pooled effect.** Across all 3,491 decisive games (one first-player
slot, one second-player slot each): `P(win|first)=0.5431` [Wilson 95% CI 0.5265,0.5596],
`P(win|second)=0.4569` [0.4404,0.4735]. Pooled advantage = **+8.62pp** [Wald 95% CI
+6.29pp, +10.96pp] — entirely positive, so the overall first-player edge is
statistically distinguishable from zero.

**Measured result — archetype level** (floor: games≥30 per first/second split, Wilson
CIs on win rate, Wald normal-approximation CI on the two-independent-proportions
advantage since first/second are disjoint game sets, not paired). 9 named archetypes
cleared the floor; 3 have an advantage CI entirely on one side of zero ("credible"):

| Archetype | games_f/s | wr_first | wr_second | advantage [95% CI] |
|---|---|---|---|---|
| Fezandipiti ex | 701/654 | 0.529 | 0.408 | +12.1pp [+6.8, +17.4] |
| Marnie's Grimmsnarl ex | 1147/1078 | 0.539 | 0.439 | +10.0pp [+5.9, +14.1] |
| Team Rocket's Mewtwo ex | 173/176 | 0.578 | 0.449 | +12.9pp [+2.5, +23.3] |

The remaining 6 (Cynthia's Garchomp ex, Dragapult ex, Mega Kangaskhan ex, Mega Lopunny
ex, Mega Lucario ex, Teal Mask Ogerpon ex) have CIs that cross zero — not credible with
current sample sizes.

**Measured result — matchup level.** 22 named-vs-named matchups clear the ≥30/≥30
floor; 12 of those are credible, e.g. Cynthia's Garchomp ex vs Marnie's Grimmsnarl ex
+25.1pp [+6.2, +44.0], Dragapult ex vs Fezandipiti ex +21.9pp [+1.2, +42.5], Marnie's
Grimmsnarl mirror +8.7pp [+2.2, +15.1]. Full table: `results/agent/going_first_second_analysis.csv`
(32 rows: 1 POOLED + 9 ARCHETYPE + 22 MATCHUP).

**Gate (engineering judgment: material = ≥5 percentage points win-rate delta, chosen
because it is large enough to plausibly move a deck-selection ranking and comfortably
exceeds typical CI half-widths here).** All 3 credible archetypes and all 12 credible
matchups clear both the credibility bar and the 5pp materiality bar (10–25pp).

**Verdict: USE_FOR_DECK_SELECTION — scoped to the specific archetypes/matchups above
only.** For Fezandipiti ex, Marnie's Grimmsnarl ex, Team Rocket's Mewtwo ex, and the 12
credible matchups, the first/second differential is real and large enough to fold into
deck-selection EV estimates. For the other 6 archetypes and all matchups that didn't
clear the floor, **IN_GAME_FEATURE_ONLY** (informational, not deck-selection-biasing)
until more data tightens the CIs — this is a hypothesis for those, not a measured result.

## Experiment 2: Bayesian Opponent-Archetype Prediction

**Data-quality caveat (explicit).** Turn-by-turn raw JSON only exists for 1,503/3,499
episodes (43%) — all 56 dates represented but thinner per date than the full dataset.
Of 1,503×2=3,006 possible (episode, side) perspectives, **2,089** had an opponent deck
that hashed to a *named* archetype via `results/meta/deck_to_archetype.csv` (rest were
UNLABELED_CLUSTER opponents, excluded as instructed). Evidence signal used: opponent
Pokemon card ids appearing in that player's own `observation.current.players[opp].active`
/`.bench` (plus each Pokemon's `preEvolution` id list, still part of the same visible
object), cumulative by turn — **no Trainer/Item/Supporter reveals**, scoped explicitly
per the schema-awkwardness fallback. `visualize.*` was never read.

**Verified fact — temporal split.** Sorted by date, last ~20% of dates held out: train =
45 dates (2026-06-16..2026-07-30, 6,824 examples / 1,706 perspectives), test = 11 dates
(2026-07-31..2026-08-10, 1,532 examples / 383 perspectives). Mechanically asserted
`max(train_date) < min(test_date)` = True (2026-07-30 < 2026-07-31).

**Measured result — training coverage.** All 11 named archetypes had ≥1 training
example, so none were out-of-vocabulary at test time (`n_oov_excluded=0` everywhere).
But 4 of 11 have thin training counts: Teal Mask Ogerpon ex=11, Iono's=13, Mega Lopunny
ex=14, Mega Abomasnow ex=16 perspectives — their likelihood estimates are
smoothing-dominated and should be treated as low-confidence per rule 1, not as validated
per-archetype numbers. Marnie's Grimmsnarl ex (509) and Fezandipiti ex (420) are
well-powered. Prior: RECENT-period `prior_filtered`, restricted to these 11 archetypes,
floored at 0.001 for Iono's and Mega Abomasnow ex (both have `prior_filtered=0` in the
RECENT window despite appearing in training data), then renormalized to sum to 1 —
explicitly applied and logged. Likelihoods use Laplace (add-one) smoothing, chosen over
Jeffreys (add-0.5) for simplicity given per-cell counts are already modest; no
probability is exactly 0 or 1. Vocabulary = 105 unique opponent Pokemon ids ever
revealed by full-game in training (test-time evidence outside this vocabulary is
ignored — a documented simplification).

**Measured result — headline metrics, test set (n=383 perspectives/cutoff, no OOV
exclusions).** `bayesian` vs `recent_prior` baseline:

| cutoff | bayesian top1 | baseline top1 | bayesian top2 | baseline top2 | bayesian logloss | baseline logloss | bayesian brier | baseline brier | coverage |
|---|---|---|---|---|---|---|---|---|---|
| turn 1 | 0.533 | 0.350 | 0.653 | 0.514 | **2.588 (worse)** | 1.961 | 0.648 (better) | 0.826 | 0.504 |
| turn 2 | 0.770 | 0.350 | 0.822 | 0.514 | 1.237 (better) | 1.961 | 0.345 | 0.826 | 1.000 |
| turn 3 | 0.851 | 0.350 | 0.906 | 0.514 | 0.852 (better) | 1.961 | 0.247 | 0.826 | 1.000 |
| full game | 0.872 | 0.350 | 0.974 | 0.514 | 0.665 (better) | 1.961 | 0.234 | 0.826 | 1.000 |

The degenerate `most_popular` baseline is dominated by `recent_prior` on every metric
(e.g. logloss 13.47, from hard 0/1 assignment penalized heavily when wrong) — confirms
`recent_prior` is the meaningful baseline to beat, not a strawman.

**Important nuance (measured result, not glossed over).** At turn 1, only ~50% of test
perspectives have *any* revealed opponent Pokemon yet (the player hasn't had their own
first decision point if they went second — this is an honest reflection of what's
actually visible, not a bug). Bayesian log loss is *worse* than the flat-prior baseline
at turn 1 specifically, even though top-1 accuracy and Brier score are both better — a
handful of confident-and-wrong predictions (visible in the turn-1 LOW-confidence tier,
67% of cases, mean logloss 3.63) drag the mean log loss up more than they hurt Brier/
accuracy. From turn 2 onward the Bayesian model beats the baseline on *every* metric by
a wide margin.

**Measured result — calibration.** HIGH tier (posterior≥0.80) empirical top-1 accuracy:
95.6% (turn1, n=113), 86.1% (turn2, n=316), 88.8% (turn3, n=365), 90.0% (full, n=369) —
always ≥ the 80% the tier implies, i.e. HIGH is reliable (if anything conservative).
MEDIUM tier (0.60–0.80) roughly matches its band at turn1 (61.5%, n=13) and turn2
(59.4%, n=32, just under); at turn3/full MEDIUM has n=1/n=11 — too small to trust,
flagged as an open question rather than a result. LOW tier is well below 60% at every
cutoff, consistent with "not confident" (no specific promise implied there).
Tier-fraction shift is itself informative: HIGH-tier share grows 29.5%→82.5%→95.3%→96.3%
across turn1→turn2→turn3→full — the model resolves to confident, mostly-correct
predictions fast once any opponent Pokemon has been seen.

**Verdict: EXPERIMENTAL.** From turn 2 onward the Bayesian model clearly, robustly beats
the meta-prior baseline on every metric (top-1, top-2, log loss, Brier) and its HIGH
confidence tier is empirically reliable — this part is a real, usable signal, not noise.
It is not a blanket USE because: (1) turn-1 log loss underperforms the naive baseline —
turn-1 posteriors should not be used for EV-weighted decisions as-is; (2) this is a
single run on a 43%-of-full-dataset sample (1,503/3,499 episodes) with 4 of 11
archetypes trained on <20 examples — per the project's own preliminary-result rule, this
should not be treated as conclusive without a second temporal split or more data;
(3) no cross-validation across multiple cutoff dates was done (one train/test split
only). Recommend: usable as an in-game informational signal starting turn 2, re-validate
with the full 3,499-episode set (or repeated splits) before any production/EV-weighted
use, and exclude turn-1 posteriors from EV calculations until revisited.

## Files written

- `results/agent/going_first_second_analysis.csv` (32 rows)
- `results/agent/opponent_prediction_metrics.csv` (48 rows: 3 models × 4 cutoffs × [OVERALL + 3 tiers])
- `results/agent/opponent_prediction_raw_predictions.csv` (1,532 rows, bayesian model, per test perspective × cutoff)
- `results/agent/scripts/exp1_going_first_second.py`, `results/agent/scripts/exp2_opponent_prediction.py` (analysis code)
