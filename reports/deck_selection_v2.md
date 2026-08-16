# High-Resolution Deck Selection v2

Tags: **[FACT]** verified directly from source data, **[RESULT]** computed
this session, **[DESIGN]** a modeling choice made this session,
**[LIMITATION]** an explicit gap, **[HYPOTHESIS]** plausible but not fully
established. Per the phase prompt: language is calibrated to strong /
moderate / weak / inconclusive evidence, and every parameter choice is fixed
*before* looking at how it affects the headline comparison (§21) — the one
exception, clearly labeled exploratory, is the paired day-block bootstrap
added in §13 after the primary grid was already computed and written to
disk, because the phase prompt's own §14 required a properly-paired
significance test that the primary pipeline's pooled-CI columns don't
provide on their own; the *strategies, windows, and thresholds themselves*
were never altered after seeing results.

Built by `tools/build_deck_selection_v2.py`. Reads only
`results/meta/episodes_summary.parquet`. No new episodes downloaded. Rating
never used. No RL/MCTS/search/opponent-inference/agent code anywhere in this
phase.

---

## 1. Objective

Phase 4.3 found no statistically convincing evidence that any meta-aware
deck-selection strategy beat the simplest baseline, at 7 weekly evaluation
periods. This phase asks specifically **why**: was the weekly evaluation
simply underpowered (too few, too coarse decision points), or is meta-aware
selection's deployable predictive value genuinely small at any resolution?
This is answered by rebuilding the same walk-forward evaluation at **daily**
resolution with **multiple training-window horizons**, using a
leakage-mechanically-verified pipeline and a statistical test appropriate for
correlated daily observations.

---

## 2. Dataset

**[FACT]** Same canonical dataset as every prior phase: 3,499 episodes, 6,982
decisive deck-slots, 56 calendar days (2026-06-16 to 2026-08-10). **0
additional episodes downloaded.** Daily deck-slot counts range 22-206
(mean 125, growing over the window as the ladder matured — matches Phase
4.1's finding that MIDDLE/RECENT periods have far more games/day than EARLY).

---

## 3. Walk-Forward Method

**[DESIGN]** For every decision day `T` (55 of the 56 dates — the first date
has no possible training data under any window) and every training window
`w ∈ {7d, 14d, 30d, full}`: `TRAIN` = all decisive deck-slots with
`date < T` and, for the fixed-length windows, `date >= T - w`. `TEST` = all
decisive deck-slots with `date == T` (one calendar day only). Every strategy
reads exclusively from a `WindowStats` object built from `TRAIN`; evaluation
is a separate step that only looks up the frozen selection's actual outcome
in `TEST`.

**[RESULT] Leakage mechanically verified for every decision**: each row of
`daily_walk_forward.csv` stores `latest_training_timestamp` and
`first_test_timestamp`; the invariant `latest_training_timestamp <
first_test_timestamp` was checked for all 1,100 strategy-decision rows with
both timestamps available — **1,100 / 1,100 pass, 0 failures**. (Oracle rows
carry no training timestamps by construction — they are diagnostic-only and
never feed any decision — so this check does not apply to them, and they are
excluded from the leakage-check denominator.)

---

## 4. Daily Evaluation Design

**[DESIGN]** Candidate floor: an archetype needs **≥50 games within the
active `TRAIN` window** to be selectable by any strategy — the identical
absolute bar used in Phase 4.2/4.3, applied uniformly across all four window
lengths (not relaxed for short windows) so that window comparisons in §5 are
apples-to-apples, not an artifact of a looser bar for shorter windows. If a
`(day, window)` combination has zero qualifying candidates, it is **skipped
and logged**, never fabricated: `results/meta/daily_walk_forward.csv` marks
these rows `status=SKIPPED_NO_CANDIDATES`.

**[RESULT]** Of 1,155 total `(day, window, strategy)` combinations attempted
(220 `day×window` cells × 5 strategy labels, plus 55 oracle rows):
**1,046 OK**, 60 `SKIPPED_NO_CANDIDATES` (concentrated in the earliest days,
where even the single largest early archetype had not yet reached 50 games
within a short window), 44 `SKIPPED_NO_TEST_DATA` (a selection was made but
the archetype happened not to appear at all on that specific test day — most
common for thin/rare archetypes on light-volume early days), 5
`SKIPPED_NO_ORACLE_CANDIDATE` (a day where no single archetype reached the
oracle's own 10-game floor).

---

## 5. Training Window Comparison

**[RESULT]** Full detail: `results/meta/window_comparison.csv` (21 rows =
20 strategy×window combinations + 1 oracle row). Headline numbers:

| Strategy | Window | Days | Games | Pooled OOS WR | 95% bootstrap CI | Median daily WR | Std daily WR |
|---|---|---|---|---|---|---|---|
| A — Most Popular | 7d | 51 | 2,374 | 46.50% | [44.67%, 48.23%] | 44.84% | 8.78pp |
| A — Most Popular | 14d | 50 | 2,138 | 46.21% | [44.40%, 47.94%] | 44.28% | 16.69pp |
| A — Most Popular | 30d | 50 | 2,118 | 46.36% | [44.48%, 48.03%] | 44.36% | 18.65pp |
| A — Most Popular | full | 50 | 2,118 | 46.36% | [44.49%, 48.08%] | 44.36% | 18.65pp |
| B — Highest Historical WR | full | 51 | 736 | 47.15% | [43.45%, 50.80%] | 47.83% | 17.96pp |
| C — Recent WR | 7d | 51 | 863 | 49.94% | [46.51%, 53.52%] | 50.00% | 14.98pp |
| C — Recent WR | 14d | 49 | 622 | **51.29%** | [47.27%, 55.26%] | 50.00% | 17.21pp |
| C — Recent WR | 30d | 51 | 670 | 49.85% | [45.98%, 53.95%] | 50.00% | 16.58pp |
| D — Meta-Aware EWR | 7d | 51 | 954 | 47.17% | [44.11%, 50.28%] | 48.48% | 14.11pp |
| D — Meta-Aware EWR | 14d | 49 | 653 | 49.00% | [45.16%, 52.87%] | 50.00% | 17.13pp |
| D — Meta-Aware EWR | 30d | 51 | 704 | 49.01% | [45.36%, 52.75%] | 50.00% | 16.38pp |
| D — Meta-Aware EWR | full | 51 | 741 | 47.91% | [44.07%, 51.65%] | 47.83% | 18.99pp |
| E — Conservative Meta-Aware | 7d | 51 | 1,903 | 49.03% | [46.87%, 51.05%] | 48.48% | 10.52pp |
| E — Conservative Meta-Aware | 14d | 50 | 1,703 | 47.92% | [45.87%, 50.03%] | 47.32% | 12.55pp |
| E — Conservative Meta-Aware | 30d | 49 | 2,142 | 47.81% | [45.72%, 49.54%] | 47.37% | 10.70pp |
| E — Conservative Meta-Aware | full | 49 | 2,146 | 47.62% | [45.69%, 49.54%] | 46.43% | 11.11pp |
| **ORACLE** | n/a | 50 | 1,086 | **60.87%** | [58.17%, 64.10%] | 60.50% | 11.25pp |

**[RESULT] No window is uniformly "best"** — Strategy C peaks at 14d, D
peaks at 14d/30d roughly equally, E is highest at 7d but nearly flat across
7d/14d/30d/full (47.6%-49.0%, its narrowest spread of any strategy). Strategy
A (the baseline) is essentially window-invariant (46.2%-46.5% regardless of
window) — expected, since which archetype is "most popular" rarely flips on
a week-to-week basis for the dominant deck.

**[RESULT] `E_conservative_meta_aware` has the smallest daily win-rate
variance of any deployable strategy at every window** (std 10.5-12.6pp vs.
14.1-19.0pp for the others) — direct, measurable evidence that the Wilson-
lower-bound conservative estimator does what it is designed to do: reduce
variance from noisy matchup cells, at the cost of a slightly lower point
estimate than C's peak.

**[LIMITATION]** Coverage is not identical across windows (49-51 valid days
each) — a handful of days are valid for one window but not another (e.g. an
archetype clears 50 games in a 30-day window before it does in a 7-day
window). §13's paired comparisons restrict to the intersection of valid days
for exactly this reason.

---

## 6. Strategy Performance

**[RESULT]** By pooled point estimate alone, **Strategy C (Recent Win Rate)
at the 14-day window is the best deployable strategy** (51.29%), followed by
D at 14d/30d (~49%) and E at 7d (49.03%). This *ranking* is consistent with
Phase 4.3's weekly finding (C was also the best point-estimate performer
there, at 50.59%) — the daily re-run did not change *which* strategy looks
best, but see §13 for what changed about how much we can trust that ranking.

**[RESULT]** `D_policy1_neutral_variant` (the 50%-neutral-fallback ablation)
underperforms the primary `D` (policy-2, archetype-strength fallback) at
every window except 7d — consistent with Phase 4.3's finding that Policy 2 is
the better-motivated fallback, now replicated at daily resolution.

---

## 7. Weekly vs Daily Evaluation

**[RESULT] Direct comparison** (Phase 4.3's weekly rolling scheme vs this
phase's daily full-history/matching-strategy rows):

| Strategy | Phase 4.3 (weekly, n=7) | Phase 4.3b (daily, n≈50) | Games (weekly → daily) |
|---|---|---|---|
| A — Most Popular | 46.69% | 46.36% (full) | 1,891 → 2,118 |
| B — Highest Historical WR | 48.14% | 47.15% (full) | 698 → 736 |
| C — Recent WR (best window) | 50.59% | 51.29% (14d) | 595 → 622 |
| D — Meta-Aware EWR (full) | 48.19% | 47.91% (full) | 689 → 741 |
| Oracle | 62.74% | 60.87% | 365 → 1,086 |

**[RESULT] The point estimates are remarkably stable between weekly and
daily evaluation** — every strategy's win rate moved by less than 1.3
percentage points switching from weekly to daily granularity, and Oracle
moved by only 1.9pp. **This means daily evaluation did not uncover a larger
effect that weekly evaluation was somehow missing or diluting.** What changed
is the number of independent-ish decision points available to test that
effect against noise (7 → 47-51), which is exactly the **statistical power**
axis, not the **effect size** axis. See §13 for the direct consequence of
this.

---

## 8. Oracle Gap

**[RESULT]** Oracle pooled OOS win rate: **60.87%** [58.17%, 64.10%], n=1,086
games across 50 days (5 days had no archetype reach the 10-game oracle floor,
logged not fabricated). Best deployable strategy by point estimate (C@14d):
51.29%. **Oracle gap: 9.58 percentage points.**

**[RESULT] Compared to Phase 4.3's weekly gap (62.74% − 50.59% = 12.15pp),
the daily-resolution gap (9.58pp) is modestly smaller but not dramatically
so** — roughly a 21% relative reduction, driven mostly by Oracle's own
point estimate coming down slightly (more, smaller test windows give Oracle
less room to cherry-pick an extreme-but-lucky single day) rather than by
deployable strategies capturing much more of the available edge. **This does
not support the strong version of the temporal-resolution hypothesis** (that
resolution alone was hiding most of the gap) — a real, sizeable gap persists
at daily resolution too.

---

## 9. Ogerpon → Grimmsnarl Detection Test

**[DESIGN]** Detection criterion, reusing Phase 4.2's exact statistical
method per §17's instruction: credible when the training-to-date
Ogerpon-vs-Grimmsnarl sample has **≥50 games AND Wilson 95% lower bound
>0.50**. Never chosen or adjusted after looking at the outcome — this is
literally Phase 4.2's already-published gate, applied walk-forward.

**[RESULT]** Full detail: `results/meta/ogerpon_grimmsnarl_walk_forward.csv`
(55 daily rows). The pairing itself was almost nonexistent before late July —
only 2 games total before 2026-07-31 (1 on 07-06, 1 on 07-13) — then grew
rapidly as both archetypes became meta-relevant simultaneously. **Credible
detection date (walk-forward safe): 2026-08-08** — the training sample
available at the start of that day (all games through 2026-08-07) had
**n=56, win rate 80.4%, Wilson lower bound 0.682**, clearing the bar for the
first time.

**[RESULT] Post-detection out-of-sample performance (2026-08-08 through
2026-08-10, the last 3 days of the dataset): n=21 games, 18 wins, 85.7% win
rate** — **at or above** the 80.4% estimate available at the moment of
detection, not a decayed or reverted number. **[RESULT]** The general
meta-aware Strategy D (full-history window) independently selected Ogerpon
as its top overall pick starting on exactly the same day (2026-08-08) the
counter became credible — the detection criterion and the deployable
strategy's own behavior are consistent, not just a hand-picked coincidence.

**[LIMITATION]** The post-detection OOS window is only 3 days / 21 games —
the entire dataset ends shortly after detection, so this is a real but
short validation, not a long-run track record.

---

## 10. Counter Exploitability

**[RESULT]** Full detail: `results/meta/counter_detection.csv`. For the two
required targets, using the identical walk-forward detection method as §9:

| Target | First detected counter | Detection date | Historical estimate at detection (n) | Future OOS win rate (n) |
|---|---|---|---|---|
| Marnie's Grimmsnarl ex | **Mega Kangaskhan ex** | 2026-07-17 | 74.0% (n=50) | **48.75%** (n=160) |
| Fezandipiti ex | Team Rocket's Mewtwo ex | 2026-07-21 | 72.55% (n=51) | **82.35%** (n=34) |

**[RESULT — important and sobering] The very first credible counter signal
detected for Grimmsnarl (Mega Kangaskhan ex, 74.0% at n=50) completely
failed to hold up out-of-sample** — its subsequent 160-game performance
(48.75%) is statistically indistinguishable from a coin flip, not a
counter at all. This is a textbook illustration of exactly the risk the
phase prompt warned about: an early "credible" (by the n≥50/Wilson-lower
gate) signal can still be a false positive that regresses to the mean once
more data arrives. **Teal Mask Ogerpon ex was NOT the first archetype to
cross the credible-counter bar against Grimmsnarl — it was Kangaskhan, and
Kangaskhan's signal was the one that turned out not to be real.** Ogerpon
only crossed the bar much later (§9, 2026-08-08) and, unlike Kangaskhan's
early false signal, held up.

**[RESULT] By contrast, Fezandipiti's first detected counter (Team Rocket's
Mewtwo ex, detected 2026-07-21) held up and even strengthened out-of-sample**
(72.55% → 82.35%).

**[RESULT] Direct answer to "are counter relationships sufficiently stable
to be actionable" (Q6): not uniformly.** One of the two general
first-detected-counter cases tested here failed OOS; the other held. This is
a 1-of-2 (Grimmsnarl's Kangaskhan) false-positive rate on the *first*
signal detected — a meaningful, not negligible, risk of acting on an early
counter-detection signal without further confirmation. The specific,
independently-tracked Ogerpon relationship (§9) is the more reliable case
in this dataset, but it was **not** the first signal that appeared —
generalizing "trust the first credible counter you see" would have been
actively harmful in the Grimmsnarl case.

---

## 11. Meta Regime Analysis

**[DESIGN]** Daily Jensen-Shannon divergence (base-2) between consecutive
days' archetype-share distributions, classified into **stable /
moderately_changing / rapidly_changing** by terciles of the 55 observed
values (thresholds: ≤0.225 stable, 0.225-0.399 moderate, >0.399 rapid — data-
driven, computed once, not adjusted after seeing regime-performance results).
This gives 18/19/18-per-bucket coverage, far better powered than Phase 4.3's
weekly 3-4-per-bucket regime analysis.

**[RESULT]** Every deployable strategy performs **best in the `stable`
regime and worst in `rapidly_changing`**, replicating Phase 4.3's directional
finding with much more data behind it:

| Strategy (window) | Stable WR | Moderate WR | Rapid WR |
|---|---|---|---|
| A — Most Popular (14d) | 46.70% | 45.80% | 42.86% |
| C — Recent WR (14d) | **57.33%** | 49.78% | 44.65% |
| D — Meta-Aware EWR (14d) | 53.21% | 47.16% | 44.65% |
| E — Conservative (7d) | 50.16% | 48.82% | 43.79% |
| ORACLE | 65.37% | 58.99% | 57.83% |

**[RESULT] Direct answer to Q7: no — meta-aware selection does NOT work
better during rapid meta changes; it works measurably worse**, and the gap
between `stable` and `rapidly_changing` performance is *larger* for the
recency/meta-aware strategies (C: 57.3%→44.7%, a 12.7pp swing) than for the
simple baseline A (46.7%→42.9%, a 3.8pp swing). **[HYPOTHESIS, now better
supported with n≈18 per bucket than Phase 4.3's n≈3-4]**: strategies that
condition on recent history are, mechanically, most vulnerable exactly when
recent history stops being representative of the immediate future — this
was speculative in Phase 4.3 and is now a more credible pattern, though
still not something this analysis formally hypothesis-tests beyond
descriptive comparison across the three regime buckets.

---

## 12. Sensitivity Analysis

**[RESULT]** Full detail: `results/meta/high_resolution_sensitivity.csv`.
For the **current** ("today," using all history through 2026-08-10)
recommendation: **Teal Mask Ogerpon ex is selected under every one of the 12
variants tested** — training window (7d/14d/30d/full), matchup min-sample
threshold (20/50/100), uncertainty handling (raw-with-fallback vs.
conservative Wilson-lower), and meta-prior type (rolling full-history vs.
exponentially recency-weighted with 7-day or 14-day half-life, per §20's
instruction to test a small number of clearly defined decay parameters, not
optimize them). Expected win rate ranges 41.9%-66.5% across variants
(lowest under the maximally conservative Wilson-lower treatment, as expected
— see Phase 4.3 §10 for why this is not itself a probabilistic floor).
**This reproduces and reconfirms Phase 4.3's robustness finding at daily
resolution and with two additional axes of variation (exponential decay,
finer training windows) — the current one-shot recommendation is not
sensitive to any of the specific modeling choices tested.**

---

## 13. Statistical Uncertainty

**[DESIGN]** Per §14's explicit warning, daily decisions are **not**
treated as independent: consecutive days share heavily-overlapping training
data (especially at 14d/30d/full windows), so game-level or naive per-day
significance tests would overstate confidence. **Method used: paired
day-block bootstrap** — for a strategy vs. baseline comparison at a fixed
window, resample *decision days* (the whole day is one exchangeable block,
not individual games) with replacement 5,000 times, computing the pooled
win-rate difference each time; report the actual point difference and the
2.5th/97.5th percentile of the bootstrap distribution as a 95% CI. This
directly implements §14's "paired comparison on the same test days" +
"block bootstrap" guidance together (paired on days, blocked at the day
level). Restricted to the intersection of days valid for both arms.

**[RESULT] This is the single most important new finding of this phase.**
Unlike Phase 4.3's weekly sign-test (p=1.000 for every strategy vs. baseline
— no daylight at all), the daily paired block-bootstrap finds **several
statistically significant advantages over the Most-Popular baseline**:

| Strategy (window) vs. A (same window) | n days | Point diff | 95% CI | Significant? |
|---|---|---|---|---|
| B (full) | 49 | +0.59pp | [−3.38, +4.59] | No |
| C (7d) | 50 | +3.61pp | [−0.36, +7.93] | No |
| **C (14d)** | 47 | **+5.04pp** | **[+0.56, +9.68]** | **Yes** |
| C (30d) | 49 | +3.41pp | [−0.76, +7.89] | No |
| D (7d) | 50 | +0.78pp | [−2.24, +4.07] | No |
| D (14d) | 47 | +2.64pp | [−1.80, +7.05] | No |
| D (30d) | 49 | +2.53pp | [−1.64, +6.79] | No |
| D (full) | 49 | +1.39pp | [−2.71, +5.64] | No |
| **E (7d)** | 50 | **+2.60pp** | **[+0.85, +4.69]** | **Yes** |
| **E (14d)** | 48 | **+1.62pp** | **[+0.14, +3.55]** | **Yes** |
| **E (30d)** | 47 | **+1.35pp** | **[+0.14, +2.79]** | **Yes** |
| E (full) | 47 | +1.16pp | [−0.05, +2.61] | No (borderline) |
| Oracle vs. best deployable (C@14d) | 44 | +10.52pp | [+5.80, +15.60] | Yes |

**[RESULT] Strategy E (Conservative Meta-Aware) shows a statistically
significant advantage over the Most-Popular baseline at three of its four
windows (7d, 14d, 30d), with a consistent direction and overlapping small
effect size (1.2-2.6pp) at all four** — this cross-window replication is
more convincing than any single p-value in isolation, since it is not one
lucky test among many but the same qualitative result recurring as the
window length changes. **Strategy C is significant only at 14d** (not 7d or
30d) — a real point estimate but a less robust one, plausibly closer to a
single favorable draw than a stable effect.

**[LIMITATION — multiple comparisons]** 13 comparisons were run; at a raw
5% significance level roughly 0.65 false positives would be expected by
chance alone even with no real effect anywhere. Finding 4 significant
results is well above that chance rate, and E's 3-window replication in
particular is hard to attribute to chance alone — but this is not a formally
multiplicity-corrected result, and should be read as **moderate**, not
strong, evidence.

**[RESULT] Direct answer to §14's instruction**: the evidence is **not**
uniformly inconclusive anymore (unlike Phase 4.3) — for Strategy E
specifically, there is **moderate, replicated evidence of a small
(1-3pp) real advantage** over the simplest baseline. For Strategy C, D, and
B, the evidence remains **weak-to-inconclusive** (isolated or absent
significant results).

---

## 14. Findings

1. **[RESULT]** Point estimates barely moved between weekly (Phase 4.3) and
   daily (this phase) evaluation — the *effect size* meta-aware selection
   can plausibly deliver is small (roughly 1-5pp) at either resolution.
2. **[RESULT]** What *did* change is statistical power: daily evaluation
   (47-51 decision days vs. 7 weeks) is the difference between "every
   strategy indistinguishable from baseline" (Phase 4.3) and "Strategy E
   shows a small, cross-window-replicated, statistically significant
   advantage" (this phase). **The weekly evaluation was genuinely
   underpowered, not simply "correctly finding nothing."**
3. **[RESULT]** The Oracle gap (≈9.6pp daily vs. ≈12.2pp weekly) shrank only
   modestly — most of the theoretically available predictive edge remains
   uncaptured by every strategy tested here, at any resolution.
4. **[RESULT]** The Ogerpon → Grimmsnarl counter was genuinely detectable
   in a walk-forward-safe way (2026-08-08) and held up out-of-sample
   (80.4% at detection → 85.7% OOS, n=21) — a specific, validated,
   actionable signal.
5. **[RESULT, important caution]** The *first* credible counter signal
   detected for the meta's dominant deck (Mega Kangaskhan ex vs. Marnie's
   Grimmsnarl ex, 74.0% at n=50) was a **false positive that collapsed to
   48.75% out-of-sample over the next 160 games** — credible-counter
   detection is not uniformly reliable on the first signal, even using
   the same statistical gate that correctly validated Ogerpon.
6. **[RESULT]** Meta-aware/recency-based strategies perform measurably worse
   during rapidly-changing meta periods and best during stable ones — the
   opposite of the naive expectation that meta-awareness helps most when
   the meta is moving fastest, now confirmed with much better statistical
   power (n≈18/bucket) than Phase 4.3's inconclusive n≈3-4.
7. **[RESULT]** The current one-shot recommendation (Teal Mask Ogerpon ex)
   is unchanged and robust across every one of 12 sensitivity variants
   tested, including two new axes (exponential recency weighting, finer
   training windows) not tested in Phase 4.3.

---

## 15. Decision: What Information Is Missing?

**[RESULT]** The persistent, only-modestly-shrinking Oracle gap (§8), the
regime-dependence finding (§11), and the mixed counter-exploitability result
(§10) together point toward a specific, evidence-grounded answer, not a
blind guess:

**Not primarily a temporal-resolution problem** — §13 shows resolution *was*
part of the problem (it hid a real small effect), but §8 shows most of the
Oracle gap survives the resolution fix, so resolution alone does not explain
the remaining gap.

**Likely, at least partly, a matchup-sparsity / regime problem**: §10's
Kangaskhan false-positive and §11's stable-vs-rapid performance split both
point at the same underlying issue — matchup and meta estimates built from
`TRAIN` are a snapshot of a *recently-past* meta, and this dataset's meta
is not stationary (Phase 4.1/4.2 already established large archetype-share
swings over the 56-day window). A method that is only as good as "the recent
past predicts the near future" will structurally underperform exactly when
that assumption is weakest — which, per §11, is measurably common in this
data (18 of 55 days classified `rapidly_changing`).

**[HYPOTHESIS, not established here]** The remaining Oracle gap plausibly
requires information this phase's inputs do not contain at all: exact
decklist / tech-card variation within an archetype (Phase 4.2 showed
archetypes like Fezandipiti ex have 87 distinct exact builds), in-game state
(this phase never looks inside a game, only at final W/L outcomes), or
player-specific skill/tendencies (explicitly excluded via the rating
finding, Phase 4.1 §6). This phase's evidence is **consistent with** that
hypothesis (the gap is large and not resolution-driven) but does **not
directly test** any of those three candidate explanations — that would
require different data than what exists in `episodes_summary.parquet`.

---

## 16. Recommendation for Next Phase

See §26 below for the single required recommendation line. In addition:

1. **Do not build a general opponent-archetype-inference system** — the
   evidence for general meta-aware selection is real but small (1-3pp), and
   §10's Kangaskhan false-positive shows naive "trust the first credible
   counter" logic is actively risky, not just weak.
2. **The Ogerpon → Grimmsnarl relationship is validated enough to encode as
   a narrow, specific rule** (§9) — this is the one finding in this whole
   phase (4.1 through 4.3b) with both a clean statistical gate and
   walk-forward-validated out-of-sample confirmation.
3. **If further temporal work is pursued**, the highest-value next step
   given §15 is investigating regime-detection *itself* as a usable signal
   (i.e., can `rapidly_changing` vs. `stable` be detected in real time and
   used to gate whether meta-aware selection is trusted that day?), not
   further scaling daily evaluation — resolution has now been tested and is
   not the dominant remaining bottleneck (§8).

---

## Answers to the Required Questions (§24)

**Q1 — Does daily evaluation outperform weekly evaluation?** Yes, in the
specific sense that matters: it has enough statistical power to detect a
small, real effect (Strategy E's 1-3pp advantage, replicated at 3 of 4
windows) that weekly evaluation could not distinguish from noise (Phase
4.3's sign-test p=1.000 across the board). It does **not** reveal a larger
effect — point estimates are nearly unchanged (§7).

**Q2 — Does a shorter training window improve prediction?** Mixed, and
strategy-dependent. Strategy C peaks at 14d (not 7d or 30d). Strategy E is
significant at 7d/14d/30d but *not* at full-history — some recency helps E,
but there is no single window that is best for every strategy, and E's
effect size is fairly flat across all three short/medium windows (§5, §13).

**Q3 — Does meta-aware selection now outperform the Recent Win Rate
baseline?** No — Recent Win Rate (C) has the *highest* point estimate of any
deployable strategy (51.29% at 14d) and is itself one of only two strategies
reaching significance vs. the Most-Popular baseline. Meta-aware EWR (D) does
not clear significance at any window. Conservative Meta-Aware (E) is the
most *robustly* significant strategy but at a lower point estimate than C.
There is no strategy here that both outperforms Recent Win Rate on point
estimate **and** is itself statistically distinguishable from it.

**Q4 — Does higher temporal resolution reduce the Oracle gap?** Only
modestly (≈12.2pp weekly → ≈9.6pp daily, §8) — most of the achievable
ceiling remains uncaptured. Resolution was a real but partial bottleneck.

**Q5 — Could the Ogerpon → Grimmsnarl counter have been detected before it
became strategically relevant?** Yes — detected 2026-08-08 using only
data through 2026-08-07 (n=56, 80.4%, Wilson lower bound 0.682), and the
general meta-aware strategy independently began selecting Ogerpon as its
top pick starting that exact same day. Out-of-sample performance in the
following 3 days (85.7%, n=21) held at or above the detection-time estimate.

**Q6 — Are counter relationships sufficiently stable to be actionable?**
Not uniformly. Ogerpon → Grimmsnarl (§9) and Mewtwo → Fezandipiti (§10) both
held up out-of-sample after detection. But the *first* credible counter
signal detected for Grimmsnarl (Mega Kangaskhan ex) was a false positive
that collapsed from 74.0% to 48.75% over the next 160 games (§10) — the
same statistical gate that correctly validated two real counters also
produced one false positive. Actionability requires validating each specific
counter, not trusting the detection gate as uniformly reliable.

**Q7 — Does meta-aware selection work better during rapid meta changes?**
No — the opposite. Every deployable strategy performs worst during
`rapidly_changing` periods and best during `stable` ones, and the
recency/meta-aware strategies show a *larger* stable-vs-rapid gap than the
simple baseline (§11).

**Q8 — If meta-aware selection still does not work [well], what information
appears to be missing?** Primarily a **matchup-sparsity / non-stationary-meta
problem**, not (mainly) a temporal-resolution problem (§15) — the Oracle gap
survives the resolution fix, and the regime finding shows the existing
methods are least reliable exactly when the meta is moving fastest. This is
**consistent with, but does not directly establish**, the hypothesis that
exact-decklist detail, in-game state, or player-specific information would
be needed to close the remaining gap — those were not tested here.

---

## 25. Interpretation

This phase's results do not cleanly match any single one of the four
labeled outcomes in the phase prompt — they sit between **Outcome A** and
**Outcome B**, with important qualifications from **Outcome D**:

- Closer to **Outcome B** in overall character: daily evaluation improved
  the *evidence* (found a small, real, replicated effect for Strategy E)
  but the effect is modest, not "material," and the Oracle gap remains
  large — this is not a clean, robust win for general meta-aware selection.
- Matches **Outcome D** specifically and cleanly for the Ogerpon →
  Grimmsnarl relationship: strongly predictive out-of-sample, but §10's
  Kangaskhan counter-example is explicit, direct evidence **against**
  generalizing this to "trust any detected counter" — exactly the caution
  Outcome D calls for.
- Does **not** match Outcome C (no daily-resolution strategy shows *zero*
  advantage — E is a genuine, replicated exception) or the clean version of
  Outcome A (the effect found is real but small, not "material").

---

## 26. Final Recommendation

```text
PROCEED WITH NARROW COUNTER MODEL ONLY
```

**Reasoning, from the actual results above**: General meta-aware deck
selection now has moderate (not strong) statistical evidence of a small
real advantage (Strategy E, 1-3pp, replicated across 3 windows, §13) — not
large enough, and not robust enough (Strategy D itself never reaches
significance; the Kangaskhan false-positive shows the counter-detection
gate is not uniformly trustworthy, §10) to justify a general opponent-aware
agent, which would need to reliably act on many matchup and meta signals at
once, most of which individually resemble Kangaskhan's false counter more
than Ogerpon's validated one. **What the evidence does robustly support** is
encoding the small number of specifically walk-forward-validated
relationships (Ogerpon → Grimmsnarl, §9; Mewtwo → Fezandipiti, §10) as
narrow, explicit counter rules — both detected using a fixed, pre-registered
statistical gate and both confirmed out-of-sample, which is a meaningfully
higher evidence bar than "found a credible counter in the historical data."

---

**Episodes used: 3,499. Additional downloads: 0. Rating used: NO.**
Per the phase prompt's explicit instruction, no RL/MCTS/search/opponent-
inference/gameplay-agent implementation follows from this report without
separate authorization.
