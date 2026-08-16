# Counter Re-validation & Extended OOS v1

## 1. Objective

Pre-registered continuation of Phase 4.4 (`tools/build_validated_counter_model_v1.py`,
`reports/validated_counter_model_v1.md`) and Phase 4.5
(`tools/build_counter_aware_deck_selection_v1.py`,
`reports/counter_aware_deck_selection_v1.md`). The goal was to give the one
confirmed counter (Team Rocket's Mewtwo ex -> Fezandipiti ex) and the one
pending counter (Teal Mask Ogerpon ex -> Marnie's Grimmsnarl ex) genuine
post-confirmation runway on episodes released after the previous dataset's
endpoint (2026-08-10), then re-run the frozen Phase 4.4/4.5 pipelines
unchanged. **No methodology, threshold, or definition was changed.**

## 2. Original Experimental Setup

Phase 4.4 built a state-machine counter detector (`UNKNOWN -> CANDIDATE ->
DETECTED -> OOS_PENDING -> OOS_CONFIRMED/OOS_FAILED`) over the 3,499-episode
/ 6,982-decisive-deck-slot dataset (2026-06-16 to 2026-08-10). It found one
`OOS_CONFIRMED` counter (Mewtwo ex -> Fezandipiti ex, detected 2026-07-22,
confirmed 2026-08-09, OOS 84.0% at n=25, Wilson lower 65.35%), one
`OOS_PENDING` counter stuck below the n>=25 confirmation floor purely because
the dataset ran out (Ogerpon ex -> Grimmsnarl ex, 82.35% at n=17), and two
`OOS_FAILED` false positives (Kangaskhan ex -> Grimmsnarl ex; Grimmsnarl ex ->
Mewtwo ex). Phase 4.5 then built a walk-forward Counter-Aware deck-selection
strategy that may only use a counter after its confirmation date (Experiment
A / PRIMARY) and found a near-total data-availability wall: the confirmed
counter had exactly one usable decision day (2026-08-10) before the dataset
ended, producing 0 counter-triggered decisions under strict deployment.

## 3. New Data

**Finding: zero new episodes exist beyond the Phase 4.4/4.5 endpoint.**
Verified two independent ways immediately before any pipeline work:

1. Re-downloaded `kaggle/pokemon-tcg-ai-battle-episodes-index`'s
   `manifest.csv`. The dataset's own last-updated timestamp had advanced to
   2026-08-11T00:07Z (a metadata refresh happened), but its **content is
   row-for-row identical** to the original 56-row index — still 56 days,
   still ends 2026-08-10, still 4,603 episodes on that day.
2. Directly probed `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-11` via
   `KaggleApi.dataset_list_files` -- **403 Forbidden** (not published), the
   same failure signature this project has already documented for
   not-yet-existing daily dumps.
3. Loaded `results/meta/episodes_summary.parquet` directly and asserted
   `max(date) == 2026-08-10` in code (`tools/build_counter_revalidation_v1.py`)
   -- confirmed, not assumed.

Per Sec 3/30's own instruction ("stop downloading once the available source
data is exhausted... do not assume the latest available date, read it from
the actual data"), no download was attempted and none was needed -- there was
nothing to download.

```text
previous_episode_count = 3,499
new_episode_count      = 0
total_episode_count    = 3,499
previous_endpoint      = 2026-08-10
new_endpoint            = 2026-08-10   (identical -- confirmed from actual data, not assumed)
```

This means **every "extended" figure in this report is numerically identical
to its Phase 4.4/4.5 counterpart, by data unavailability, not by a null
effect.** That is a real, reportable finding in its own right (Sec 26/39):
this phase could not add exposure because none exists yet, and the correct
conclusion remains "insufficient post-confirmation evidence," carried forward
unchanged rather than freshly re-derived from nothing.

## 4. Frozen Methodology

`tools/build_validated_counter_model_v1.py` and
`tools/build_counter_aware_deck_selection_v1.py` were read in full and then
**re-run completely unchanged** (no edits) against the unchanged parquet.
Every output CSV was byte-for-byte identical to the pre-existing Phase 4.4/4.5
files (mechanically diffed, 0 differences across all 16 files). This
double-confirms both (a) the pipeline is deterministic given fixed input, and
(b) no methodology drift occurred between phases. All thresholds (Wilson 95%
CI, `MIN_MATCHUP_SAMPLE_PRIMARY=50`, `EFFECT_SIZE_PRIMARY=0.60`,
`PERSISTENCE_MIN_CONSECUTIVE=2`, `OOS_PRIMARY_HORIZON=25`,
`OOS_CONFIRM_WR=0.55`/`OOS_CONFIRM_WILSON_LO=0.50`, `TRAINING_WINDOW_DAYS=14`,
`CANDIDATE_MIN_GAMES=50`, `TARGET_ACTIVATION_THRESHOLD_PRIMARY=0.05`,
`COUNTER_MIN_META_SHARE=0.01`) were left exactly as declared in Phase 4.4/4.5
and are reused verbatim below.

## 5. Mewtwo -> Fezandipiti Extended OOS

Original Phase 4.4 checkpoint (frozen, unchanged, `detection_date` never
moved): **n=25, 84.0% WR, Wilson lower 65.35%, OOS_CONFIRMED
(confirmation_date=2026-08-09)**.

Only 26 post-detection Mewtwo-vs-Fezandipiti games exist in the *entire*
available dataset (through 2026-08-10) -- one more than the n=25 primary
checkpoint used.

| Horizon | Availability | Win rate | Wilson lower | Wilson upper |
|---|---|---|---|---|
| 25 (original checkpoint) | AVAILABLE | 84.00% | 65.35% | 93.60% |
| 50 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED | -- | -- | -- |
| 75 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED | -- | -- | -- |
| 100 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED | -- | -- | -- |
| 150 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED | -- | -- | -- |
| 200 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED | -- | -- | -- |
| ALL_AVAILABLE (n=26) | AVAILABLE | 84.62% | 66.47% | 93.85% |

The one additional post-checkpoint game was a win (22/26 vs the checkpoint's
21/25). Applying the frozen `lifecycle_trend` logic (Wilson-CI overlap across
`OOS_HORIZONS=[25,50,100,150]`) still yields
`INSUFFICIENT_HORIZONS_FOR_TREND` -- only one of those four declared horizons
is reachable, so the pipeline correctly refuses to classify stable/
improving/decaying/failed rather than over-interpreting one extra game.
Directionally the single additional observation is consistent with (not
contradicting) the original estimate: the win rate did not drop, and the
Wilson interval at n=26 fully contains the n=25 interval.

## 6. Ogerpon -> Grimmsnarl Extended OOS

Original Phase 4.4 checkpoint: **n=17, 82.35% WR, OOS_PENDING** (primary
confirmation requires n>=25; the dataset ran out before that could be
reached).

Zero additional post-detection Ogerpon-vs-Grimmsnarl games exist beyond the
original 17 -- the 25/50/75/100/150 horizon table is entirely
`INSUFFICIENT_DATA_SOURCE_EXHAUSTED`.

| Horizon | Availability |
|---|---|
| 25 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED |
| 50 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED |
| 75 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED |
| 100 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED |
| 150 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED |
| ALL_AVAILABLE (n=17, original checkpoint) | AVAILABLE -- 82.35% WR, Wilson lower 58.97% |

Status remains **OOS_PENDING**, unchanged, per the frozen n>=25 rule -- not
rescued or rejected, exactly as Sec 10 requires.

## 7. Negative Controls

**Mega Kangaskhan ex -> Marnie's Grimmsnarl ex** (`OOS_FAILED`, frozen,
unchanged): 159 post-detection games now exist and were all already inside
the original dataset, so the full horizon table is available for diagnostic
purposes:

| Horizon | Win rate | Wilson lower |
|---|---|---|
| 25 (original checkpoint) | 52.00% | 33.50% |
| 50 | 54.00% | 40.40% |
| 75 | -- (n=75 not separately in OOS_HORIZONS) | -- |
| 100 | 48.00% | 38.46% |
| 150 | 49.33% | 41.45% |
| ALL_AVAILABLE (n=159) | 49.06% | 41.40% |

The trajectory collapses toward, and settles at, ~49% -- consistent with
Phase 4.2's full-dataset matchup figure (~48.75%) and confirming the original
false-positive classification remains correct. Status stays `OOS_FAILED`
(never retroactively changed, per Sec 12).

**Marnie's Grimmsnarl ex -> Team Rocket's Mewtwo ex** (`OOS_FAILED`, the
independently discovered second false positive, frozen, unchanged): 73
post-detection games available.

| Horizon | Win rate | Wilson lower |
|---|---|---|
| 25 (original checkpoint) | 44.00% | 26.67% |
| 50 | 50.00% | 36.64% |
| 75/100/150/200 | INSUFFICIENT_DATA_SOURCE_EXHAUSTED | -- |
| ALL_AVAILABLE (n=73) | 49.32% | 38.17% |

Also settles at ~49%, confirming the failure classification remains correct.
Tracked using the identical unmodified methodology as every other counter
(Sec 13 -- not special-cased).

## 8. Counter Lifecycle

`results/meta/counter_lifecycle_extended.csv` (26 rows) lists every horizon
computed above for all four tracked counters, tagged
`data_source=ORIGINAL_DATASET_2026-06-16_to_2026-08-10` throughout (there is
no `NEW_DATA_EXTENSION` category populated this phase -- none exists) and
`detection_epoch=ORIGINAL_DETECTION (frozen, not moved)` on every row. No
historical detection date was moved forward or backward; no methodological
error was found in Phase 4.4 that would justify doing so.

## 9. Extended Counter-Aware Deck Selection

Phase 4.5's exact walk-forward was re-run unchanged. Because the input data
is unchanged, `results/meta/counter_aware_walk_forward_extended.csv` (492
rows) and `counter_aware_decisions_extended.csv` (104 rows) are content-
identical to the originals -- confirmed by direct diff, not merely expected.

## 10. Counter-Triggered Decisions

**Experiment A (PRIMARY, strict deployable) -- unchanged from Phase 4.5:**

- Total decisions: 50 (one per decision day with candidates)
- Opportunities (Sec 21 definition, gate cleared independent of argmax): **1**
  (2026-08-10, target=Fezandipiti ex, target share 14.25%)
- Counter-triggered decisions (counter actually won the argmax): **0**
- Selection changes (Counter-Aware != Conservative Meta-Aware base pick): **0**
- Counter-active OOS performance: **not computable** -- 0 games, 0 wins,
  0 losses. Sample is not merely small, it is empty. This is stated
  explicitly per Sec 20's own instruction, not glossed over.

The single opportunity did fire mechanically (base score 29.17% ->
counter-adjusted final 33.69%, contribution +4.52pp) but lost the argmax to
Mega Lopunny ex (43.99%) by a ~10pp margin -- the counter mechanism worked
correctly, it simply wasn't the deciding factor that day.

**Frozen-Rule diagnostic (Experiment B, non-deployable, kept structurally
separate per Sec 6/16 -- never used as primary evidence):** recomputed
directly from `counter_aware_walk_forward_extended.csv`, unchanged from Phase
4.5: 25 opportunities, 13 counter-active decisions, pooled 47.99% (669/1394)
vs 47.92% primary (+0.07pp, still near-invisible in aggregate); ACTIVE-day
win rate 49.79% (117/235) vs INACTIVE-day 47.63% (552/1159). This still
illustrates the mechanism has real, modest local value when given genuine
runway -- exactly the Phase 4.5 finding, unchanged because the underlying data
is unchanged.

## 11. Aggregate Strategy Comparison

Recomputed (Experiment A / PRIMARY), identical to Phase 4.5:

| Strategy | OOS WR | Games | Decision days | 95% Bootstrap CI |
|---|---:|---:|---:|---|
| A Most Popular | 46.20% | 2,171 | 50 | [44.41%, 47.89%] |
| B Recent WR | 51.29% | 622 | 49 | [47.27%, 55.48%] |
| C Conservative Meta-Aware | 47.92% | 1,703 | 50 | [45.72%, 49.86%] |
| D Counter-Aware | 47.92% | 1,703 | 50 | [45.78%, 49.94%] |
| Counter-Only | 47.95% | 1,683 | 50 | [45.73%, 49.95%] |
| Oracle | 61.38% | 1,028 | 47 | [58.43%, 64.82%] |

Counter-Aware is numerically identical to Conservative Meta-Aware to 4 decimal
places except in the bootstrap CI, because the counter mechanism never won an
argmax under strict deployment (Sec 10).

## 12. Statistical Analysis

Δ Counter-Aware vs Recent WR (pooled point estimate): **-3.37pp**
Paired day-block bootstrap (common decision days only, N=2,000 resamples):
**-3.17pp, 95% CI [-7.18pp, +0.79pp], p=0.117 -- not significant.**
Δ Counter-Aware vs Most Popular: +1.63pp, 95% CI [+0.14pp, +3.51pp], p=0.037
-- significant, but this compares against the weakest baseline, not the
relevant deployable one (Recent WR).
Δ Counter-Aware vs Conservative Meta-Aware: 0.00pp exactly (mechanically
guaranteed, since 0 selections changed).

All figures identical to Phase 4.5's reported numbers -- confirmed by re-run,
not carried over from memory.

## 13. Sensitivity Analysis

Re-run unchanged (`counter_aware_sensitivity.csv`): all 5 variants (target
share threshold 2%/5%/10%, counter share floor 0.5%/1%/2%, raw vs
conservative OOS contribution estimate) still produce exactly 47.92% --
identical to Phase 4.5's own finding that sensitivity was structurally
uninformative here (only one possible opportunity exists to vary at all).
This has not changed and cannot change without new data.

## 14. Leakage Audit

Re-run unchanged: **0/55 temporal-leakage failures**
(`latest_training_timestamp < first_test_timestamp`), **0/52
counter-info-availability failures** (counter info never used before its
confirmation date). Identical to Phase 4.5. `results/meta/
counter_aware_leakage_audit_extended.csv` records this with
`new_episodes_included=0` so the "extended" file is legible as a genuine
re-check, not a stale copy.

## 15. Statistical Power

**Insufficient**, unambiguously. Counter-active decisions available for the
primary aggregate question (does Counter-Aware beat Recent WR): 0. Games
available for that question via the counter-triggered path specifically: 0.
The confirmed counter's own OOS sample only grew from n=25 to n=26 -- nowhere
near the 50/75/100/150/200 horizons that would let stability be assessed with
any rigor. The pending counter's sample did not grow at all (still n=17,
below its own n=25 confirmation floor). No amount of re-analysis of the
existing data can manufacture the missing exposure; only new episodes can,
and none exist yet.

## 16. Interpretation

Per the Sec 37 hierarchy:

- Not **strong positive** (Counter-Aware does not beat Recent WR; CI includes
  0; counter-active sample is literally empty this round).
- Not straightforwardly **positive but underpowered** either, because the
  primary experiment recorded zero counter-active games to be underpowered
  *about* -- there is no positive point estimate at all to report for the
  activated mechanism under strict deployment.
- The **mixed-result** pattern from Phase 4.5 still holds when the Frozen-Rule
  diagnostic is considered as context (not as primary evidence): the counter
  itself remains locally valid (84.0-84.62% Mewtwo-vs-Fezandipiti win rate,
  holding, not decaying) but this has not yet translated into a general
  deck-selection advantage, because it essentially has not been *tested*
  under real deployment conditions yet.
- Correct overall label, unchanged from Phase 4.5 and now reaffirmed rather
  than newly derived: **UNRESOLVED DUE TO INSUFFICIENT EXPOSURE.**

## 17. Limitations

1. **The central limitation of this entire phase is data availability, not
   methodology.** Zero new episodes existed to extend anything with. Every
   "extended" number in this report equals its Phase 4.4/4.5 counterpart by
   construction.
2. The Mewtwo counter's OOS sample is still only n=25-26 -- nowhere near
   large enough to distinguish "genuinely 84%" from "genuinely 65-70% with a
   lucky small sample," which is exactly what the Wilson interval
   [65.35%, 93.60%] already says plainly.
3. The Ogerpon counter remains entirely unable to reach its own pre-declared
   confirmation bar (n>=25) -- it is not close, it simply has no more games to
   draw on.
4. The single Counter-Aware opportunity that did occur was a genuine test of
   the deployed mechanism (not a leakage artifact -- 0/52 confirmed) but n=1
   opportunity is not a sample from which any general claim about
   deck-selection value can be drawn in either direction.
5. This report cannot rule out that new episodes, once available, will
   change any of these numbers substantially -- that is precisely the
   open question this phase set out to close and could not, for reasons
   external to the analysis.

## 18. Recommendation

**Do not re-tune any threshold to manufacture a result from this null
data-availability outcome** (Sec 38 -- no methodology change was made, and
none is being proposed). The correct action is to **wait for new daily
episode dumps to actually be published** (the source has consistently lagged
by ~1 calendar day per prior sessions' findings; the 2026-08-11 dump was not
yet available at the time of this run) and then **re-run this exact unchanged
three-script chain** (`build_validated_counter_model_v1.py` ->
`build_counter_aware_deck_selection_v1.py` ->
`build_counter_revalidation_v1.py`) once meaningful new data exists. Given the
project's Simulation deadline (2026-08-16, then ~2 more weeks of continued
ladder play for rating convergence) and Strategy deadline (2026-09-13), there
should be multiple further opportunities to attempt this re-validation with
real new data before either deadline. **Do not proceed to RL/MCTS/search/
opponent-inference/general-agent work** -- nothing in this phase's findings
changes the four consecutive phases (4.3b, 4.4, 4.5, and now 4.5b) that have
converged on "stay narrow, the evidence for a general opponent-aware agent
does not exist."

---

## Final Comparison Table (Sec 34)

| Strategy | Original Phase 4.5 WR | Extended WR | Δ | 95% CI | Significant |
|---|---:|---:|---:|---|---|
| Most Popular | 46.20% | 46.20% | 0.00pp | n/a (no new data) | n/a |
| Recent WR | 51.29% | 51.29% | 0.00pp | n/a (no new data) | n/a |
| Conservative Meta-Aware | 47.92% | 47.92% | 0.00pp | n/a (no new data) | n/a |
| Counter-Aware | 47.92% | 47.92% | 0.00pp | n/a (no new data) | n/a |
| Counter-Only | 47.95% | 47.95% | 0.00pp | n/a (no new data) | n/a |
| Oracle | 61.38% | 61.38% | 0.00pp | n/a (no new data) | n/a |

No value in this table is fabricated -- every "Δ" is exactly 0.00pp because
the extended evaluation used the identical dataset (Sec 34's own instruction:
"do not fabricate values where the extended evaluation is not possible" is
honored by reporting the true, uninformative delta rather than inventing
movement that did not happen).

## Final Counter Table (Sec 35)

| Counter | Original Status | New OOS n | Extended OOS WR | Wilson Lower | New Status |
|---|---|---:|---:|---:|---|
| Mewtwo -> Fezandipiti | OOS_CONFIRMED | 0 (n grew 25->26 within existing data, 1 extra game) | 84.62% (ALL_AVAILABLE, n=26) | 66.47% | OOS_CONFIRMED (unchanged) |
| Ogerpon -> Grimmsnarl | OOS_PENDING | 0 | 82.35% (ALL_AVAILABLE, n=17, unchanged) | 58.97% | OOS_PENDING (unchanged) |
| Kangaskhan -> Grimmsnarl | OOS_FAILED | 0 | 49.06% (ALL_AVAILABLE, n=159, unchanged) | 41.40% | OOS_FAILED (unchanged) |
| Grimmsnarl -> Mewtwo | OOS_FAILED | 0 | 49.32% (ALL_AVAILABLE, n=73, unchanged) | 38.17% | OOS_FAILED (unchanged) |

## Required Questions (Sec 36)

**Q1. Did Mewtwo -> Fezandipiti remain strong after substantially more OOS
games?** No "substantially more" games existed to test this against -- only
one additional game (n=25->26). What little extension exists is consistent
with (not contradicting) the original estimate: the win rate stayed at or
above 84% and the Wilson interval widened only trivially.

**Q2. Did Mewtwo -> Fezandipiti remain above its original 84% estimate within
reasonable statistical uncertainty?** Yes, trivially -- 84.62% at n=26 is
above 84.0% at n=25 (one more win). This is not meaningful evidence of
stability given the sample size, just a non-contradiction.

**Q3. Did Ogerpon -> Grimmsnarl reach sufficient OOS evidence for
confirmation?** No. It remains at n=17, unchanged, still below the n>=25
primary confirmation floor.

**Q4. Did Ogerpon -> Grimmsnarl survive OOS validation?** Neither confirmed
nor rejected -- still `OOS_PENDING`, exactly where Phase 4.4 left it. "Did it
survive" cannot yet be answered either way.

**Q5. Did the Kangaskhan false positive remain failed?** Yes. Extended
diagnostic (n=159, full horizon trajectory 52%->54%->48%->49.33%->49.06%)
confirms the original `OOS_FAILED` classification was correct.

**Q6. Did the additional false positive (Grimmsnarl -> Mewtwo) remain
failed?** Yes. Extended diagnostic (n=73, 44%->50%->49.32%) confirms
`OOS_FAILED` remains correct.

**Q7. How many genuine counter-triggered deck-selection decisions
occurred?** Zero, under strict deployment (Experiment A / PRIMARY),
identical to Phase 4.5 -- unchanged because no new decision days exist.

**Q8. Did Counter-Aware actually change the selected deck?** No. Zero
selection changes, identical to Phase 4.5.

**Q9. When Counter-Aware changed the selection, did that improve OOS
results?** Not applicable -- it never changed the selection this phase or
the prior one.

**Q10. Does Counter-Aware now outperform Recent WR?** No. -3.37pp point
estimate, 95% CI [-7.18pp, +0.79pp] includes 0, p=0.117 -- unchanged from
Phase 4.5, not significant.

**Q11. Is the improvement statistically significant and robust?** There is
no improvement to test for significance (point estimate is negative). Not
significant, and the sensitivity analysis (Sec 13) shows the null result is
robust to all 5 predefined variants -- but "robust null," not "robust
improvement."

**Q12. How much of the Oracle gap does Counter-Aware now close?** None,
beyond what Phase 4.5 already found. Oracle-Counter-Aware gap: 13.46pp
(61.38%-47.92%), Oracle-Recent-WR gap: 10.09pp (61.38%-51.29%) -- both
unchanged. Counter-Aware closes 0pp of gap relative to Phase 4.5's own
figures because it produced 0 additional selection changes.

**Q13. Is the result sufficiently powered to make an operational
recommendation?** No. See Sec 15 -- statistical power is explicitly
insufficient, and this report says so rather than forcing a YES/NO
conclusion (Sec 26).

**Q14. Is there evidence to justify a general opponent-aware agent?** No.
Default answer stands, per Sec 36's own instruction that it should only be
overridden if the new data clearly demonstrates otherwise -- and there is no
new data.

---

## Structured Final Answer

```text
Previous endpoint: 2026-08-10
New endpoint: 2026-08-10

Previous episodes: 3,499
New episodes: 0
Total episodes: 3,499
Additional downloads: 0 (source data exhausted -- verified via index-manifest re-pull and a direct 403 on the 2026-08-11 daily dataset)

Mewtwo -> Fezandipiti:
Original OOS: 84.00% (n=25)
Extended OOS: 84.62% (ALL_AVAILABLE, n=26 -- only 1 additional game exists)
Extended n: 26
Wilson lower: 66.47%
Status: OOS_CONFIRMED (unchanged)

Ogerpon -> Grimmsnarl:
Original OOS: 82.35% (n=17)
Extended OOS: 82.35% (unchanged, n=17, no new games exist)
Extended n: 17
Wilson lower: 58.97%
Status: OOS_PENDING (unchanged -- still below n>=25 confirmation floor)

Kangaskhan -> Grimmsnarl:
Extended OOS: 49.06% (ALL_AVAILABLE, n=159, unchanged)
Status: OOS_FAILED (unchanged, reconfirmed)

Grimmsnarl -> Mewtwo:
Extended OOS: 49.32% (ALL_AVAILABLE, n=73, unchanged)
Status: OOS_FAILED (unchanged, reconfirmed)

Most Popular: 46.20%
Recent WR: 51.29%
Conservative Meta-Aware: 47.92%
Counter-Aware: 47.92%
Counter-Only: 47.95%
Oracle: 61.38%

Counter-Aware Δ vs Recent WR: -3.37pp
95% CI: [-7.18pp, +0.79pp]
Statistically significant: NO

Counter-triggered decisions: 0
Selection changes: 0
Selection-change rate: 0.00% (0 of 1 opportunity)

Counter-active OOS performance: NOT COMPUTABLE (0 games -- sample is empty, not merely small)

Oracle gap: 13.46pp (Oracle 61.38% vs Counter-Aware 47.92%)
Oracle gap reduction: 0.00pp (no new counter-triggered decisions occurred)

Leakage failures: 0 / 107 total checks (0/55 temporal, 0/52 counter-info-availability)

Statistical power: INSUFFICIENT

Primary conclusion: UNRESOLVED DUE TO INSUFFICIENT EXPOSURE -- this phase could not add post-confirmation exposure because no new episode data exists yet beyond 2026-08-10 (verified directly against the source, not assumed). The prior conclusion (data-timing artifact, not a weak signal) is reaffirmed, not newly derived.

Counter-Aware deck selection:
PROMISING BUT UNDERPOWERED

General opponent-aware agent justified:
NO

Recommended next phase: Re-attempt this exact unchanged re-validation chain (build_validated_counter_model_v1.py -> build_counter_aware_deck_selection_v1.py -> build_counter_revalidation_v1.py) once Kaggle publishes daily episode dumps beyond 2026-08-10 -- retry in a few days given the project's remaining timeline before the 2026-08-16 Simulation deadline.

Reason: The bottleneck this phase found is external data availability, not a flaw in the counter, the strategy, or the statistical methodology -- all three passed every mechanical check (reproducibility, leakage, sensitivity) unchanged.
```
