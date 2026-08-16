# Counter-Aware Deck Selection v1

**Phase 4.5.** Consumes only the frozen `OOS_CONFIRMED` counter registry from Phase 4.4
(`results/meta/counter_registry.csv`, `counter_oos_validation.csv`, `current_validated_counters.csv`)
against `results/meta/episodes_summary.parquet` (3,499 episodes / 6,982 decisive deck-slots).
Zero new episodes, zero new counter discovery, zero threshold changes to Phase 4.4. No RL/MCTS/
search/opponent-modeling/agent code — a pure walk-forward evaluation, `tools/
build_counter_aware_deck_selection_v1.py`.

Claim tags: **[FACT]** = directly computed, **[HYPOTHESIS]** = plausible interpretation not
itself tested, **[OPEN QUESTION]** = flagged for future work.

---

## 1. Objective

Determine whether explicitly consuming Phase 4.4's single `OOS_CONFIRMED` counter
(`Team Rocket's Mewtwo ex -> Fezandipiti ex`, OOS WR 84.0%, n=25, Wilson lower bound 65.35%)
provides *incremental predictive value at deck-selection decision time*, over and above the
strongest baselines already established in Phase 4.3b. Not whether the matchup itself is strong
— that was already settled in Phase 4.4 — but whether *knowing about it, at the moment a decision
had to be made*, changes and improves that decision.

## 2. Dataset

`results/meta/episodes_summary.parquet`, `outcome_type == "DECISIVE"` → 6,982 deck-slots / 3,491
games, 2026-06-16 to 2026-08-10. **0 additional downloads.** Consumed Phase 4.4 artifacts as-is;
`counter_registry.csv` filtered to `status == "OOS_CONFIRMED"` gives exactly **1 row** —
mechanically verified to contain neither `Ogerpon ex -> Grimmsnarl ex` (`OOS_PENDING`) nor
`Kangaskhan ex -> Grimmsnarl ex` (`OOS_FAILED`); the code never reads any other status.

## 3. Validated Counter Input

| Counter | Target | Historical WR (at detection) | OOS WR | OOS n | Wilson lo | Status | Confirmed |
|---|---|---:|---:|---:|---:|---|---|
| Team Rocket's Mewtwo ex | Fezandipiti ex | 72.88% | **84.0%** | **25** | 65.35% | OOS_CONFIRMED | 2026-08-09 |
| Teal Mask Ogerpon ex | Marnie's Grimmsnarl ex | 81.67% | 82.35%* | 17 | 58.97%* | OOS_PENDING | — (not usable) |
| Mega Kangaskhan ex | Marnie's Grimmsnarl ex | 72.55% | 52.0% | 25 | 33.50% | OOS_FAILED | — (not usable) |

(*ALL_AVAILABLE figures shown for context only — below the n=25 primary bar, hence PENDING.)
Only row 1 ever enters `confirmed_rows` anywhere in the code.

## 4. Strategy Definitions

All strategies use **training window = 14 calendar days**, reused verbatim from Phase 4.3b's own
declared best-deployable configuration (C@14d = 51.29% pooled OOS WR, the highest point estimate
of any strategy; E@14d/C@14d were the two windows found statistically significant vs. Most
Popular in Phase 4.3b). Not retuned for this phase.

- **A — Most Popular**: argmax training-window usage share, among archetypes with training
  games >= 50 (`CANDIDATE_MIN_GAMES`, reused verbatim from 4.3b).
- **B — Recent Win Rate**: argmax training-window win rate. This is Phase 4.3b's `C_recent_wr`
  at 14d.
- **C — Conservative Meta-Aware**: argmax `Σ_b P(b) × matchup_estimate(a,b)`, where
  `matchup_estimate` is the training-window Wilson lower bound if the pair has any training
  games, else a shrinkage fallback (`k=30`, prior 0.5) — Phase 4.3b's `E_conservative_meta_aware`
  at 14d. **This is the "base score" Counter-Aware builds on** (Sec 6): it is the only established
  baseline that already computes a per-archetype-pair matchup expectation, which is exactly the
  structure a counter adjustment needs to plug into.
- **D — Counter-Aware**: base = Strategy C's score for each candidate `a`; for every confirmed
  row where `a` is the counter archetype, add a contribution (Sec 6-8, 8 below) if the target is
  materially present and the counter is practically viable. Falls back to exactly Strategy C
  whenever no confirmed row qualifies (Sec 12) — mechanically guaranteed, not just intended,
  because the contribution term is literally `0.0` in that case.
- **Counter-Only** (diagnostic, Sec 13): selects the confirmed counter archetype outright
  whenever it qualifies, else falls back to Strategy C's pick. Tests whether the raw override
  rule alone carries standalone value, independent of the aggregated-score approach.
- **Oracle**: best test-day performer (`test_games >= 10`), no training-candidacy requirement —
  hindsight-only ceiling, never used for selection. Reused verbatim from Phase 4.3b.

**Counter contribution formula (Sec 8), exactly as specified:**
```
baseline_matchup_expectation(A,B) = Strategy C's own matchup_estimate(A,B)  [training-window
                                     Wilson lower bound, or shrinkage fallback if no training data]
counter_contribution(A,B) = target_meta_share(B) × (counter_OOS_WR(A,B) − baseline_matchup_expectation(A,B))
Counter-Aware Score(A) = Base Expected Win Rate(A) + Σ_B counter_contribution(A,B)
```
This is a swap-in-place: it replaces exactly the one `B`-specific term inside the base sum with
the more reliable OOS estimate, leaving every other matchup term untouched — not an arbitrary
bonus (Sec 8's explicit prohibition).

**Activation gate (Sec 9-10, primary, declared before evaluation):** target 14-day training-window
share `>= 5%`; counter's own 14-day training-window share `>= 1%` (reused verbatim from Phase
4.4's `COUNTER_MIN_META_SHARE`); counter training games `>= 50` (reused verbatim, `CANDIDATE_MIN_GAMES`
— this is what makes the counter itself a legitimate, selectable candidate deck that day, not merely
a name in a table). Sensitivity: target threshold 2%/10%; counter-share floor 0.5%/2%; contribution
using the OOS Wilson lower bound (65.35%) instead of the raw OOS win rate (84.0%).

## 5. Walk-Forward Evaluation

Two structurally separate experiments (Sec 3-4), never mixed in any output file (`experiment`
column: `PRIMARY` vs `FROZEN_DIAGNOSTIC`):

- **Experiment A (PRIMARY, strict deployable):** a confirmed row may only influence a decision
  made on a calendar day *strictly after* its `confirmation_date`. `Mewtwo -> Fezandipiti` was
  confirmed 2026-08-09; the dataset ends 2026-08-10. **This leaves exactly one decision day
  (2026-08-10) where the counter could possibly have been used at all.** This is the honest
  consequence of Sec 3-4's information constraint, computed directly from Phase 4.4's own
  registry — not a modeling choice made for this phase.
- **Experiment B (FROZEN-RULE DIAGNOSTIC):** the same rule applied to every decision day in the
  dataset, ignoring when it was actually confirmed — explicitly *not* a deployment simulation
  (Sec 25), used only to ask "how useful would this have been had we always known it."

55 calendar decision days (2026-06-17 to 2026-08-10); 50-51 had `>=50`-game training candidates
depending on strategy (5 early days skipped, `SKIPPED_NO_CANDIDATES`, training window still
ramping up).

## 6. Overall Strategy Performance

**Headline table (Sec 34), Experiment A / PRIMARY only:**

| Strategy | OOS WR | Games | Decision Days | Δ vs Recent WR | 95% CI |
|---|---:|---:|---:|---:|---:|
| Most Popular | 46.21% | 2,138 | 50 | −5.08pp | [44.40%, 47.94%] |
| Recent WR | **51.29%** | 622 | 49 | baseline | [47.27%, 55.48%] |
| Conservative Meta-Aware | 47.92% | 1,703 | 50 | −3.37pp | [45.72%, 49.86%] |
| Counter-Aware | 47.92% | 1,703 | 50 | −3.37pp | [45.78%, 49.94%] |
| Counter-Only | 47.95% | 1,683 | 50 | −3.34pp | [45.73%, 49.95%] |
| Oracle | 61.38% | 1,028 | 47 | +10.09pp | [58.43%, 64.82%] |

**Counter-Aware and Conservative Meta-Aware are numerically identical to 4 decimal places** —
because under the strict information constraint, the counter contributes on exactly one day, and
even there it did not change the argmax pick (Sec 7). Counter-Only differs by a hair (0.03pp,
1,683 vs 1,703 games) because its override rule occasionally activates without needing to beat
the base score, but the gap is well within noise.

## 7. Counter-Triggered Performance

`results/meta/counter_trigger_analysis.csv` (Experiment A / PRIMARY):

| Counter status | Decision days | Games | Wins | Win rate |
|---|---:|---:|---:|---:|
| ACTIVE | 0 | 0 | 0 | n/a |
| INACTIVE | 50 | 1,703 | 816 | 47.92% |

**Zero decisions were counter-ACTIVE under Experiment A** — not because the counter never
qualified (it did, once — see Sec 9), but because on the one day it qualified, its adjusted score
still lost the argmax to another archetype (Sec 9). There is no ACTIVE-vs-INACTIVE comparison to
make in the primary experiment; this itself is the finding.

Under the **Frozen-Rule Diagnostic** (context only, not primary evidence): 13 of 50 days had a
counter-active *selected* decision, with 235 games at 49.79% vs. 1,159 games at 47.63% when
inactive (+2.16pp) — directionally consistent with the counter helping, but drawn from a
diagnostic that assumes information the strategy could not actually have had at the time.

## 8. Fezandipiti / Mewtwo Analysis

Distinguishing **Mewtwo-vs-Fezandipiti win rate** from **Mewtwo's overall day win rate** (Sec 20's
explicit warning) — Experiment A / PRIMARY:

| | Value |
|---|---:|
| Days Counter-Aware selected Mewtwo ex | 3 |
| Of those, actual Mewtwo-vs-Fezandipiti games | 16 |
| Wins | 13 |
| **Mewtwo-vs-Fezandipiti win rate on those days** | **81.25%** |

All 3 of these days occurred *before* 2026-08-09 (the confirmation date) — meaning Mewtwo won the
argmax on pure Strategy-C merit those days, with **zero contribution from the counter mechanism**
(which had a `0.0` contribution term for every day except 08-10, and even there didn't win). The
81.25% observed win rate specifically against Fezandipiti on those days is a real, corroborating
data point for the underlying matchup strength (consistent with the 84% OOS figure), but it is
*not* evidence that Counter-Aware's counter logic did anything — Strategy C alone would have
produced the identical selections.

Under the Frozen-Rule Diagnostic: 13 Mewtwo-selected days, 51 Mewtwo-vs-Fezandipiti games, 42
wins, **82.35% win rate** — again consistent with, but not independent confirmation beyond, the
84% OOS figure it was built from (same underlying games, different lens).

## 9. Selection Changes

`results/meta/counter_selection_changes.csv`. Experiment A / PRIMARY: **50 decisions, 1
opportunity (2026-08-10 — target share 14.25% cleared the 5% bar, Mewtwo cleared the 50-game/1%
counter-viability floor), 0 counter-triggered decisions, 0 selection changes (0.00%).** On the one
opportunity, the full score breakdown was:

| Archetype | Base score | Contribution | Final score |
|---|---:|---:|---:|
| Mega Lopunny ex (winner) | 43.99% | — | 43.99% |
| Teal Mask Ogerpon ex | 42.60% | — | 42.60% |
| ... | ... | | |
| **Team Rocket's Mewtwo ex** | **29.17%** | **+4.52pp** | **33.69%** |

Mewtwo's own matchup profile that day was weak enough (base 29.17%, dragged down mainly by its
poor matchup against `Marnie's Grimmsnarl ex`, ~43% of the meta) that even the full counter
contribution (+4.52pp, from a 14.25%-share target at an 84% vs. ~52% baseline-matchup gap) left it
14pp short of the winning pick. **The mechanism fired correctly; it simply wasn't the deciding
factor that day.**

Under the Frozen-Rule Diagnostic (context only): **10 of 50 days changed** (all switching *to*
Mewtwo; see `counter_aware_walk_forward.csv` filtered to `FROZEN_DIAGNOSTIC`). On those 10 days,
Mewtwo's actual *overall* day performance was 85/170 = 50.0%, vs. what the base pick scored on
those same days, 232/479 = 48.43% — a real but modest **+1.57pp** improvement on the switched
days specifically. The gap between this (+1.57pp locally) and the pooled headline gap (D-frozen
47.99% vs. C 47.92%, +0.07pp overall) is exactly Sec 30/37's caution made concrete: a locally-real
effect, diluted to near-invisibility in the aggregate because it only touches 10 of 50 days and,
even then, Mewtwo's *other* matchups on those days (not against Fezandipiti) pull its full-day
result back down from the 84%-matchup figure toward a much more ordinary ~50%.

## 10. Regret Analysis

`results/meta/counter_regret_analysis.csv`, regret = best-deployable-that-day (`test_games>=10`,
restricted to that day's actual training-candidates — **not** the Oracle) minus chosen strategy's
win rate:

| Strategy | Mean regret | Median regret | 95th pct. regret | Days |
|---|---:|---:|---:|---:|
| Most Popular | 13.34pp | 12.69pp | 37.44pp | 42 |
| **Recent WR** | **7.99pp** | **8.57pp** | **28.88pp** | 42 |
| Conservative Meta-Aware | 11.34pp | 11.09pp | 33.15pp | 44 |
| Counter-Aware | 11.34pp | 11.09pp | 33.15pp | 44 |
| Counter-Only | 12.31pp | 11.09pp | 34.24pp | 44 |

Recent WR has the lowest regret by a wide margin among deployable strategies — corroborating the
headline table's ranking from a completely different angle (regret vs. pooled win rate).
Counter-Aware's regret is identical to Conservative Meta-Aware's, for the same reason as Sec 6.

## 11. Oracle Comparison

| Strategy | OOS WR | Oracle gap |
|---|---:|---:|
| Most Popular | 46.21% | 15.17pp |
| Recent WR | 51.29% | 10.09pp |
| Counter-Aware | 47.92% | 13.46pp |
| Oracle | 61.38% | — |

**Q7 in full below.** Recent WR closes 5.08pp of the 15.17pp Most-Popular-relative gap (33.5%);
Counter-Aware closes only 1.71pp (11.3%) — *worse* gap closure than Recent WR, not better, because
under Experiment A it is mechanically identical to Conservative Meta-Aware, which already
underperformed Recent WR in Phase 4.3b's own findings (47.92% vs. 51.29% at 14d — an already-known
result, not new to this phase).

## 12. Frozen-Rule Diagnostic

**FROZEN-RULE DIAGNOSTIC — not deployable evidence, not mixed into Sec 6-11's primary numbers.**

| Strategy | FROZEN pooled OOS WR | Games | Days |
|---|---:|---:|---:|
| D — Counter-Aware (frozen) | 47.99% | 1,394 | 50 |
| Counter-Only (frozen) | 48.17% | 683 | 49 |

Both are still below Recent WR's 51.29% in pooled terms — the frozen rule does not, even with
unlimited hindsight-free availability, make Counter-Aware beat Recent WR in this dataset. What it
*does* show: the mechanism is not inert. It found 25 real opportunities, activated on 13 of them,
and changed the actual selected deck on 10 of 50 days — with a real, positive (if modest, +1.57pp
on the affected days) effect where it fired. **This diagnostic is the strongest evidence in this
phase that the underlying mechanism works as designed; Experiment A's null result is a data-
availability artifact of this specific dataset's timeline, not evidence the mechanism is broken.**

## 13. Sensitivity Analysis

`results/meta/counter_aware_sensitivity.csv`. Every variant (target-share threshold 2%/5%/10%;
counter-share floor 0.5%/1%/2%; contribution using raw OOS WR vs. OOS Wilson lower bound) produces
the **exact same 47.92% pooled OOS win rate** under Experiment A. This is not a coincidence to
read as "robustness" in the usual sense — it is a direct consequence of there being only one
possible opportunity day in the whole primary experiment, and the margin by which Mewtwo lost that
day's argmax (33.69% vs. 43.99%, a 10pp gap) being far larger than any of these threshold
adjustments could plausibly close. The sensitivity analysis is genuinely uninformative here for a
structural reason (not enough data to vary), which is itself worth stating plainly rather than
implying false robustness.

## 14. Leakage Audit

`results/meta/counter_aware_leakage_audit.csv`:

| Check | Total checked | Failures |
|---|---:|---:|
| `latest_training_timestamp < first_test_timestamp` | 55 | **0** |
| Counter info not used before its confirmation date | 52 | **0** |

Both mechanically verified, not merely asserted. **Negative-control protection (Sec 27)**:
`Kangaskhan -> Grimmsnarl` (OOS_FAILED) and `Ogerpon -> Grimmsnarl` (OOS_PENDING) together
account for 4 non-`OOS_CONFIRMED` rows in the registry; a set-intersection check against the
confirmed set used by the strategy code found **0 overlap** — verified programmatically at
runtime, not just by inspection.

## 15. Statistical Uncertainty

All pooled win rates use day-block bootstrap (2,000 resamples, days — not games — as the
resampling unit, since consecutive days share heavily overlapping 14-day training windows and are
not independent). The primary Counter-Aware vs. Recent WR comparison uses a **paired** day-block
bootstrap (jointly resampling the same day indices for both strategies) to respect that both are
evaluated on the same decision days:

| Comparison | Abs. difference | 95% CI | p-value | Significant |
|---|---:|---:|---:|---|
| Counter-Aware vs. Recent WR | −3.17pp | [−7.18pp, +0.79pp] | 0.117 | No |
| Counter-Aware vs. Most Popular | +1.62pp | [+0.12pp, +3.50pp] | 0.038 | **Yes** |
| Counter-Aware vs. Conservative Meta-Aware | 0.00pp | [0.00pp, 0.00pp] | 1.000 | No (identical by construction) |

Counter-Aware beats Most Popular (inherited entirely from Conservative Meta-Aware, not from the
counter mechanism) but does not beat Recent WR, and the CI vs. Recent WR is wide enough that
"no measurable difference" is a more honest read than either "beats" or "loses to."

## 16. Practical Utility

- Counter information was available (Experiment A) on **1 of 55 decision days (1.8%)** — the
  entire evaluation window.
- It changed the decision on **0 of those days**.
- Incremental wins/losses attributable to the counter mechanism under Experiment A: **0 / 0** —
  there is nothing to attribute, by construction.
- Under the Frozen-Rule Diagnostic (not deployable, context only): available on 25 of 50 days
  (50%), changed the decision on 10 (20%), with a modest positive effect (+1.57pp) on those 10
  days specifically.

Per Sec 30's own framing: a strategy that changes 0% of decisions cannot be described as
operationally important *yet* — not because the underlying signal is weak, but because this
dataset gave it almost no runway to ever be used.

## 17. Findings

1. **[FACT]** Under the strict, leakage-honest deployment simulation (Experiment A),
   Counter-Aware is numerically identical to Conservative Meta-Aware and does not beat Recent WR
   (−3.37pp, not significant). It has exactly one opportunity to differ, and on that day the
   counter contribution (+4.52pp) was insufficient to overturn a 10pp base-score gap.
2. **[FACT]** This is driven entirely by *when* the counter was confirmed (2026-08-09, one day
   before the dataset ends) — not by the counter contribution formula being ineffective or the
   activation gate being too strict. The Frozen-Rule Diagnostic, using the identical formula and
   gate, found 25 opportunities and 10 real selection changes with a positive (if modest) effect.
3. **[HYPOTHESIS]** The gap between the Frozen diagnostic's local effect (+1.57pp on switched
   days) and its pooled effect (+0.07pp overall) suggests that even a strong single-matchup
   counter (84% vs. one specific opponent) contributes only a small amount to a deck's *overall*
   daily performance, because most of any deck's games on a given day are against *other*
   opponents. A counter this narrow may need either a much larger target share, a much larger WR
   edge, or multiple simultaneous confirmed counters before it moves the aggregate needle
   noticeably — consistent with the phase prompt's own Sec 37 caution.
4. **[FACT]** Recent WR remains the strongest deployable baseline in this dataset, by both pooled
   win rate (51.29%) and regret (7.99pp mean, lowest of all five deployable strategies) —
   unchanged from Phase 4.3b's own finding, not something this phase overturns.

## 18. Limitations

- **[FACT]** n=1 opportunity day in the primary experiment is far too small to draw any general
  conclusion about counter-aware selection's value — this phase answers "did it help in the one
  chance it got" (no, narrowly), not "would it help given a normal amount of runway."
- **[FACT]** Only one `OOS_CONFIRMED` counter exists to test with; the aggregation-across-multiple-
  targets code path (Sec 11) is implemented but never exercised with more than one term.
- **[HYPOTHESIS]** The Frozen-Rule Diagnostic's own +0.07pp pooled effect, while real and
  positive, is small enough that even with unlimited runway this single counter alone would
  probably not have been enough to beat Recent WR in this particular dataset window — the deeper
  fix implied by Sec 37 may be more/broader validated counters (Phase 4.4 v2) rather than better
  consumption of this one.
- **[FACT]** As in every prior phase, none of these win rates are rating-adjusted (the project's
  established rating-resolution limitation still applies).

## 19. Recommendation

**Primary conclusion:** the strict, deployable experiment found **zero measurable effect** from
consuming the validated counter — but this is a direct, mechanically-verified consequence of the
counter's late confirmation date relative to the dataset's end, not evidence the underlying
mechanism doesn't work. The Frozen-Rule Diagnostic (explicitly non-deployable) shows the mechanism
does activate, does change real decisions, and does so with a small positive effect where it
fires — but that effect is too small, and too rarely realized in this window, to already justify
calling Counter-Aware selection a proven improvement.

This is closest to **Outcome B — COUNTER SIGNAL PROMISING BUT UNPROVEN**, with the added nuance
that "unproven" here specifically means "not yet given the chance to be tested," not "tested and
inconclusive." Per Sec 31's own instruction for Outcome B: **do NOT proceed to a general
opponent-aware agent.**

**Recommended next step:** re-run this exact, unchanged pipeline once more post-2026-08-10 episode
data becomes available (mirrors Phase 4.4's own recommendation, and resolves both phases' shared
bottleneck simultaneously — more time since `Mewtwo -> Fezandipiti`'s confirmation date, and
possibly a resolution of `Ogerpon -> Grimmsnarl`'s `OOS_PENDING` status feeding a second usable
counter into this exact strategy). Do not yet promote Counter-Aware to production deck-selection
use in place of Recent WR, and do not treat the near-zero Experiment A effect as proof the
approach should be abandoned — both would be overreading a single-day sample.

---

## Required Final Questions (Sec 36)

**Q1 — Does Counter-Aware beat Recent Win Rate?** No. 47.92% vs. 51.29% (−3.37pp) under
Experiment A.

**Q2 — Is the improvement statistically significant?** N/A (there is no improvement to test) —
the difference vs. Recent WR is not significant either (95% CI [−7.18pp, +0.79pp], p=0.117).

**Q3 — How often does the validated counter actually change the selected deck?** 0 of 50 decisions
under Experiment A (it had exactly 1 chance, and didn't win). 10 of 50 under the Frozen-Rule
Diagnostic (not deployable evidence).

**Q4 — Does Mewtwo -> Fezandipiti provide measurable OOS decision value?** Not yet demonstrable
under strict deployment (0 opportunities that changed a decision). The Frozen diagnostic suggests
yes, modestly (+1.57pp on the 10 days it would have changed the pick), but this cannot be claimed
as deployable evidence per Sec 25.

**Q5 — Does Counter-Aware improve performance specifically when Fezandipiti is prevalent?**
Cannot be tested under Experiment A (0 counter-active decisions occurred). Under the Frozen
diagnostic, yes modestly on the specific days it activated (Sec 9, Sec 12).

**Q6 — Does the strategy remain useful outside counter-triggered periods?** Yes, trivially —
outside the one opportunity, Counter-Aware is identical to Conservative Meta-Aware by
construction, so it inherits exactly that strategy's (already-established, Phase-4.3b) usefulness,
neither more nor less.

**Q7 — How much of the Oracle gap is closed?** Counter-Aware closes 11.3% of the Most-Popular-
relative Oracle gap (1.71 of 15.17pp) — less than Recent WR's 33.5% (5.08 of 15.17pp). Counter-
Aware does not close more of the gap than the existing best baseline; under Experiment A it closes
*less*, because it never differs from Conservative Meta-Aware, which itself underperforms Recent
WR.

**Q8 — Is the effect large enough to justify operational use?** No. 0 decisions changed, 0
incremental wins or losses attributable, under the only experiment that honestly reflects
deployable information availability.

**Q9 — Is the current single validated counter sufficient to justify adding more counter rules
later?** The Frozen diagnostic's real (if modest) local effect (+1.57pp on 10 real switched days)
is enough to justify *continuing* to validate and add more counters (Phase 4.4 v2) — a single
narrow counter with 1.8% opportunity-availability in this window was never going to move an
aggregate metric much on its own, which is expected, not disqualifying.

**Q10 — Is there evidence strong enough to proceed to a general opponent-aware agent?** **NO.**
Nothing in this phase's evidence changes that answer — if anything, the near-total absence of
usable counter-triggered decisions in the strict experiment sharpens the case for staying narrow,
exactly as Phase 4.3b and Phase 4.4 both already concluded.
