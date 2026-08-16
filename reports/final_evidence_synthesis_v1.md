# Final Evidence Synthesis v1

**Phase 4.6 — Final Evidence Synthesis & Conservative Counter Policy.** This is a synthesis
phase, not a discovery phase: no new methodology, no new counters, no RL/MCTS/search/agent
work. Every numeric claim below was re-checked directly against the underlying CSV/JSON/parquet
artifacts in `results/meta/`, not copied from prior report prose. Claims are tagged
`[FACT]` / `[RESULT]` (measured result) / `[HYPOTHESIS]` / `[INFERRED]` per this project's
standing process rule, in addition to the LEVEL A-D / confidence framework this phase requires.

## Executive Summary

**What did we learn?** The real ladder meta is dominated by one archetype (Marnie's
Grimmsnarl ex, 8.5%→44.3% share over the 56-day window) and contains a handful of very strong,
statistically credible matchup asymmetries. Exactly one of those asymmetries has survived the
project's full pre-registered detection → out-of-sample confirmation pipeline: **Team Rocket's
Mewtwo ex beats Fezandipiti ex** (76.5% historical, 84.0-84.6% OOS). Two more promising
counters (Ogerpon ex → Grimmsnarl ex; Dragapult ex → Fezandipiti ex) never got enough
post-detection games to clear the confirmation bar before the dataset ends — they are
**unresolved, not disproven**. Two other apparent counters that looked just as strong at
detection time (Kangaskhan ex → Grimmsnarl ex; Grimmsnarl ex → Mewtwo ex) **collapsed on OOS** —
the single clearest methodological lesson of the whole project: a strong historical matchup
number is not evidence of a real predictive counter until it survives OOS testing.

**What can we trust?** The meta representation (LEVEL A). The Grimmsnarl drift (LEVEL A). The
one OOS-confirmed counter, narrowly (LEVEL A within its scope). Recent Win Rate as a deployable
baseline (LEVEL A). The Oracle-vs-deployable gap as proof that real decision edge exists
(LEVEL A). The rating signal's unreliability (LEVEL A finding, of a negative result).

**What should the system do today?** Pick decks by 14-day Recent Win Rate. If the opponent
pool includes Fezandipiti ex at meaningful share, prefer Team Rocket's Mewtwo ex. Do nothing
more sophisticated than that — do not use rating, do not use Conservative/general meta-aware
scoring as the default, do not use the Ogerpon or Dragapult counters yet.

**What should it NOT do?** Build a general opponent-aware agent, a general counter model, an
RL/MCTS search system, or a rating-aware strategy. Four consecutive phases (4.3b, 4.4, 4.5,
4.5b) independently converged on "stay narrow," and this synthesis does not overturn that.

**What remains unresolved?** Whether validated-counter information improves *aggregate* deck
selection (the strict deployable test had zero opportunities to fire — a data-timing artifact,
not a null result). Whether Ogerpon ex → Grimmsnarl ex and Dragapult ex → Fezandipiti ex are
real counters (insufficient OOS runway). Whether general meta-aware selection has a real edge
beyond Recent WR at any meaningful reliability (daily resolution found a small, borderline
effect; weekly resolution found nothing).

## 1. Dataset and Scope

```text
DATASET UNCHANGED SINCE PHASE 4.5b
```

`[FACT]` Canonical dataset: **3,499 successfully parsed episodes** (3,491 decisive after
excluding draws/errors; 6,982 decisive deck-slots), date range **2026-06-16 → 2026-08-10**
(`results/meta/episodes_summary.parquet`). Phase 4.5b (same day, 2026-08-11) independently
re-verified via two methods that no post-2026-08-10 episode data exists on Kaggle
(`kaggle/pokemon-tcg-ai-battle-episodes-index` manifest content unchanged row-for-row; the
`...-2026-08-11` daily dataset returns 403 Forbidden). This phase did not re-pull Kaggle again —
re-checking hours after 4.5b's own check would not plausibly find new data and the phase
instructions direct against re-downloading old episodes. No new episodes were processed. All
numbers in this report trace to the frozen Phase 4.1-4.5b artifact set.

Source-of-truth hierarchy followed as specified: raw parquet → Phase 4.1-4.5b validated CSV/JSON
artifacts → prior report prose (used for interpretation only, every number re-verified against
its underlying CSV before being restated here).

## 2. Meta Representation

`[RESULT]` The RECENT-period meta prior (`meta_prior.csv`) resolves to **9 archetypes** that
clear the 20-game floor, prior_filtered summing to 1.0 by construction. Current top archetypes
(share definitions below; see note on two distinct "share" conventions):

| Archetype | Early share | Recent share (Phase 4.2, period-based) | Current share (Phase 4.4, dataset-end) | Change (early→recent) |
|---|---|---|---|---|
| Marnie's Grimmsnarl ex | 8.517% | 44.336% | 43.47% | **+35.82pp** |
| Fezandipiti ex | 8.116% | 16.817% | 14.87% | +8.70pp |
| Mega Kangaskhan ex | 2.104% | 8.747% | 9.51% | +6.64pp |
| Mega Lopunny ex | 0.200% | 6.842% | 9.43% | +6.64pp |
| Team Rocket's Mewtwo ex | 0.902% | 5.539% | 2.94% | +4.64pp |
| Teal Mask Ogerpon ex | 0.301% | 4.787% | 7.17% | +4.49pp |
| Dragapult ex | 6.413% | 4.612% | 5.13% | -1.80pp |
| Cynthia's Garchomp ex | 1.703% | 4.186% | 2.75% | +2.48pp |
| Mega Lucario ex | 17.535% | 1.504% | 2.23% | -16.03pp |

`[FACT] Methodology note (reported, not silently reconciled per Section 3 instruction):` "recent
share" (Phase 4.2, `archetype_features.csv`, share of games in the last of three roughly-equal
calendar periods) and "current share" (Phase 4.4, `counter_registry.csv`
`target_current_meta_share`, a dataset-end rolling snapshot used for counter-relevance gating)
are two genuinely different window definitions from two different phases. They agree closely for
some archetypes (Grimmsnarl 44.34% vs 43.47%) and diverge for others (Mewtwo 5.54% vs 2.94%;
Ogerpon 4.79% vs 7.17%) because Mewtwo's and Ogerpon's shares are still moving within the
"recent" period itself. Both are legitimate, both are cited by name in different sections below,
and neither has been altered to make them match.

`[RESULT]` 0 of 83 archetypes show an overall win rate statistically distinguishable from 50%
at HIGH_CONFIDENCE_STRONG tier; only Fezandipiti ex reaches HIGH_CONFIDENCE_WEAK. Strength
differentiation lives in matchup-specific structure, not aggregate win rate.

**Evidence level: A (VALIDATED).** Confidence: **HIGH**. Reproduced independently at full scale
(session 6, Phase 4.2) directly from the raw parquet, consistent across weekly and daily
evaluation resolutions (session 7-8).

## 3. Meta Drift

```text
Marnie's Grimmsnarl ex
8.5% → 44.3%
```

`[FACT]` Reproduced exactly: `early_share=8.517%` → `recent_share=44.3358%`
(`archetype_features.csv`), n=2,225 total games for the archetype. `meta_trend` field:
"strongly rising"; `meta_tags`: `CURRENT_DOMINANT;CURRENT_RISING`.

**Classification per established methodology (not recalculated): Evidence level A (VALIDATED).**
Confidence: **HIGH**. This is the single strongest and most reproduced quantitative finding of
the entire project — confirmed independently in the Phase 4.1 pilot (43.1% recent), Phase 4.1
full-scale run (31.9% overall / 44.3% recent), and Phase 4.2's from-parquet recomputation
(identical to the third decimal).

## 4. Matchup Structure

Strongest credible matchup relationships (all require `games>=50 AND wilson_lo>50%` per Phase
4.2's frozen credible-counter gate):

| Matchup | Historical win rate | Games | Wilson lower bound | Tier |
|---|---|---|---|---|
| Teal Mask Ogerpon ex → Marnie's Grimmsnarl ex | 81.82% | 77 | ~71.8% | USABLE, credible |
| Team Rocket's Mewtwo ex → Fezandipiti ex | 76.47% | 85 | ~60.4% (detection-time) | USABLE, credible |
| Dragapult ex → Fezandipiti ex | 64.47% | 76 | — | USABLE, credible |
| Marnie's Grimmsnarl ex → Team Rocket's Mewtwo ex | 59.70% | 134 | 51.24% | HIGH_CONFIDENCE, credible (**but OOS_FAILED — see Section 5**) |

`[FACT] Historical vs OOS-confirmed evidence, explicitly distinguished:` all four rows above are
**historical matchup evidence** (Phase 4.2, full-dataset cumulative). Only the Mewtwo→Fezandipiti
row is also **OOS-confirmed** (Phase 4.4/4.5b, held-out post-detection games). The
Grimmsnarl→Mewtwo row looks credible historically and even carries the HIGH_CONFIDENCE tier, but
walk-forward OOS testing (Section 5) shows this specific "credible historical matchup" was itself
a case of early small-sample inflation that did not hold going forward — it is listed here for
completeness and explicitly flagged, not endorsed.

**Evidence level: B (STRONG BUT LIMITED)** as a general class — historical credibility alone,
even at HIGH_CONFIDENCE tier, has been shown (Section 5) not to guarantee OOS survival.
Confidence: **MEDIUM** for the class of finding; individual rows carry their own OOS-based
confidence per Section 5/8.

## 5. Validated Counters

Final counter classification (`results/meta/final_validated_counters.csv`):

| Counter | Target | Status | Evidence |
|---|---|---|---|
| Team Rocket's Mewtwo ex | Fezandipiti ex | **OOS_CONFIRMED** | Historical 76.47% (n=85); detection 72.88% (n=59, 2026-07-22); OOS n=25 = 84.00% (wilson_lo 65.35%); extended n=26 = 84.62% |
| Teal Mask Ogerpon ex | Marnie's Grimmsnarl ex | **OOS_PENDING** | Historical 81.82% (n=77); detection 81.67% (n=60, 2026-08-09); OOS ALL_AVAILABLE n=17 = 82.35% — never reached n≥25 |
| Dragapult ex | Fezandipiti ex | **OOS_PENDING** | Historical 64.47% (n=76); detection 65.57% (n=61, 2026-08-05); OOS ALL_AVAILABLE n=15 = 60.00% — never reached n≥25 |
| Mega Kangaskhan ex | Marnie's Grimmsnarl ex | **OOS_FAILED** | Detection 72.55% (n=51, 2026-07-18); OOS n=25 = 52.00% (wilson_lo 33.50%); ALL_AVAILABLE n=159 = 49.06% |
| Marnie's Grimmsnarl ex | Team Rocket's Mewtwo ex | **OOS_FAILED** | Historical(full) 59.70% (n=134); detection 72.13% (n=61, 2026-07-25, inflated); OOS n=25 = 44.00% (wilson_lo 26.67%); ALL_AVAILABLE n=73 = 49.32% |

No classification here was upgraded or downgraded from Phase 4.4/4.5b's frozen registry.

## 6. Deck Selection

Phase 4.3 (weekly) / Phase 4.3b (daily, 14-day training window — the configuration later reused
verbatim as "the" baseline in Phase 4.5) key numbers, reproduced from `window_comparison.csv`
and `counter_aware_comparison_extended.csv`:

```text
Recent Win Rate (14d):       51.29%   (n=622 games / 49 decision days)
Conservative Meta-Aware:     47.92%   (14d; range 47.62-49.03% across the 4 tested windows)
Oracle (daily, Phase 4.3b):  60.87%   (n=1,086 games / 50 decision days, "full" window)
Most Popular:                46.20%   (n=2,171 games / 50 decision days, Phase 4.5's own table)
```

`[FACT] Discrepancy vs the phase prompt's rough figures, reported not silently corrected:` the
prompt's "~49%" for Conservative Meta-Aware and "~46%" for Most Popular are consistent with, but
not exactly equal to, the precise canonical values above (47.92% and 46.20% respectively) —
7-day-window Conservative Meta-Aware does reach 49.03%, which is likely the source of the
rounded figure. This report uses the exact artifact values throughout.

**Interpretation (unchanged from Phase 4.3/4.3b):**
- **Oracle = hindsight ceiling.** Not deployable; proves real decision edge exists in principle.
- **Recent WR = strongest simple deployable baseline.** Best point estimate of any strategy
  tested at any resolution; the strategy every later phase built on top of.
- **Meta-aware (Conservative) = modest / unstable advantage.** Real at daily resolution (3/4
  windows significant, ~1.3-2.6pp), invisible at weekly resolution (n=7 periods, all p=1.000
  sign-test), and it never beat Recent WR's point estimate at any window.

**Evidence level: A** for Recent WR and Oracle (both directly measured, reproduced across
resolutions). **Evidence level: B** for Conservative Meta-Aware's advantage over Most Popular
(real but small and resolution-dependent).

## 7. Counter-Aware Selection

```text
Counter-Aware:              47.92%
Recent WR:                  51.29%
Δ:                          -3.37pp
95% CI:                     [-7.18pp, +0.79pp]
significant:                NO
counter-triggered decisions: 0
```

`[FACT] A second discrepancy in the underlying artifact, reported not repaired:` the pooled
simple difference (0.4792 − 0.5129 = −0.0337) and the paired day-block bootstrap point estimate
in `counter_aware_comparison_extended.csv` (−0.0317) are not identical, though they share the
same 95% CI and the same non-significant conclusion. Phase 4.5's own report combines the
pooled-difference point estimate with the paired-bootstrap CI (as reproduced above); this
synthesis preserves that exact combination rather than inventing a reconciled number.

**Zero counter-triggered decisions occurred** under strict leakage-honest deployment
(`counter_trigger_analysis.csv`: `ACTIVE` row has `decision_days=0, games=0`) because Mewtwo→
Fezandipiti was confirmed on 2026-08-09, one day before the dataset ends — leaving exactly one
possible decision day, on which the mechanism fired correctly (+4.52pp contribution) but lost
the argmax to Mega Lopunny ex by a 10pp margin.

**Correct conclusion:**
```text
UNRESOLVED DUE TO INSUFFICIENT EXPOSURE
```
not "Counter-Aware strategy disproven." Counter-Aware is numerically identical to Conservative
Meta-Aware in this dataset purely because the counter mechanism never had a chance to differ
from it.

**Evidence level: UNRESOLVED.** Confidence: **UNRESOLVED**.

## 8. Oracle and Decision Ceiling

```text
Oracle ≈ 61%
Best deployable ≈ 51%
```

`[FACT]` Two related-but-distinct Oracle figures exist in the artifacts and both are cited here
rather than merged: Phase 4.3b's general daily-walk-forward Oracle = **60.87%** (n=1,086 /
50 days, `window_comparison.csv`, the figure behind the "Oracle gap only modestly shrank,
~12.2pp weekly → ~9.6pp daily" finding). Phase 4.5's regret-ceiling Oracle, restricted to
candidates with `test_games≥10`, = **61.38%** (n=1,028 / 47 days,
`counter_aware_comparison_extended.csv`). These differ because they use slightly different
candidate/day universes, not because of a computation error; both are internally consistent
with their own phase's other numbers.

Gap vs best deployable (Recent WR, 51.29%): **~9.6-10.1pp**.

**Significance:** A substantial theoretical decision edge exists, but the tested deployable
strategies (best: Conservative Meta-Aware / Recent WR) capture only a fraction of it. The
remaining gap is **not** shown to be recoverable with a more complex model — the Oracle measures
what a perfect-hindsight picker would have achieved, not what any feasible real-time algorithm
could extract from the same information a real agent has at decision time.

**Evidence level: A.** Confidence: **HIGH** (the gap itself is robustly measured); the
implication that it is recoverable is explicitly **not** claimed.

## 9. Rating Limitation

```text
~49-53% labeled-check accuracy
```

`[RESULT]` Both the deck-based and team-based alternating-assignment EM resolution methods
(`src/meta_analysis/rating_resolution.py`) produce a "does the resolved-higher-rated side
actually win more" accuracy of ~49-53% — indistinguishable from chance — holding across every
rating bucket (`rating_analysis.csv`: 5 quintile buckets, win rates 46.9%-51.3%, all overlapping
50% within their 95% CI) and across every major archetype/deck restriction tested.

```text
rating-based conclusions = INFERRED / LOW CONFIDENCE
```

This limitation is **structural**: the source data provides only an unordered per-match score
pair (`min_score`, `sum_score − min_score`), never which side is which, and the raw episode JSON
carries no rating field at all. No amount of additional data at this same schema would fix it.
Rating information is excluded from the final decision policy (Section 13).

**Evidence level: A** (of the negative finding itself — this is a well-established, reproduced
null result, not an open question). Confidence: **HIGH** that rating cannot currently be used.

## 10. Short-Game Findings

```text
Fezandipiti ex:      +18.11pp vs overall WR   (n=135 short games)
Mega Kangaskhan ex:  -25.85pp vs overall WR   (n=109 short games)
```

`[RESULT]` Reproduced exactly from `archetype_features.csv` (`short_game_delta_pp` column).
Both are large, credible, reproduced effects — classified as a **secondary behavioral/meta
finding**, not a primary deck-selection rule. It is not incorporated into the conservative
policy in Section 13, which is scoped to archetype-vs-archetype selection, not game-length-
conditioned play.

**Evidence level: B (STRONG BUT LIMITED)**. Confidence: **MEDIUM-HIGH** — large and credible,
but a narrower/more specific finding than the core meta and counter conclusions.

## 11. What Is Proven

(Full list with tags in `results/meta/final_claims.csv`, rows P1-P10.)

1. Marnie's Grimmsnarl ex became dominant in the recent meta (8.5%→44.3% share). `[verified fact]`
2. Some matchup asymmetries are very strong and statistically credible (Mewtwo→Fezandipiti 76.5%
   n=85; Ogerpon→Grimmsnarl 81.8% n=77). `[measured result]`
3. Mewtwo ex → Fezandipiti ex passed the defined OOS counter-validation gate. `[measured result]`
4. Kangaskhan ex → Grimmsnarl ex failed OOS despite a detection-time signal as strong as the
   real counter. `[measured result]`
5. Historical counter detection alone is insufficient to prove a real counter — OOS confirmation
   is what discriminates. `[verified fact]`
6. Simple Recent Win Rate (14d) is difficult to beat reliably; no strategy showed statistically
   convincing superiority at weekly resolution. `[measured result]`
7. Oracle performance demonstrates substantial theoretical headroom (~10pp) over every
   deployable strategy. `[measured result]`
8. Rating resolution is structurally unreliable (~49-53% accuracy). `[measured result]`
9. Fezandipiti ex and Mega Kangaskhan ex show large, credible short-game win-rate deltas.
   `[measured result]`
10. Conservative Meta-Aware shows a small but statistically significant advantage over Most
    Popular at daily (not weekly) resolution, in 3 of 4 training windows. `[measured result]`

## 12. What Is Not Proven

(Full list in `results/meta/final_claims.csv`, rows N1-N7.)

- A general opponent-aware agent. `[hypothesis, unsupported]`
- A general counter model beyond the single OOS_CONFIRMED pair. `[hypothesis, unsupported]`
- RL/MCTS advantage — the Oracle gap shows headroom exists, not that this class of method would
  recover it. `[hypothesis, unsupported]`
- A reliable rating-aware strategy — the rating signal itself is structurally unreliable.
  `[measured result, negative]`
- Universal meta-aware deck-selection superiority — real but small, resolution-dependent, never
  beat Recent WR's point estimate. `[measured result, does not support the claim]`
- Aggregate Counter-Aware superiority — the strict deployable test had zero opportunities to
  fire; genuinely unresolved, not disproven. `[measured result, UNRESOLVED]`
- Teal Mask Ogerpon ex → Marnie's Grimmsnarl ex as a production counter — OOS_PENDING;
  insufficient post-detection exposure, not a weak signal. `[measured result, insufficient]`

## 13. Conservative Final Policy

Full policy table in `results/meta/final_deck_selection_policy.csv`. Conceptual flow (unchanged
from the phase prompt's own hierarchy — no weights, no scoring model, no unvalidated
assumptions added):

```text
1. Identify current meta            -> meta_prior.csv (9-archetype RECENT-period prior)
        ↓
2. Start from Recent Win Rate (14d) -> established baseline, HIGH confidence
        ↓
3. Check for an OOS_CONFIRMED counter relevant to today's likely opponent
        ↓
4. If relevant AND sufficiently represented (target share ≥5%, counter share ≥1%,
   Phase 4.4's own unchanged gate), apply the counter adjustment
   -> currently exactly one pair: Team Rocket's Mewtwo ex vs Fezandipiti ex
        ↓
5. Otherwise use the baseline (Recent WR alone — not Conservative Meta-Aware by default,
   since its aggregate advantage is small/resolution-dependent, not a clear win)
        ↓
6. Never use OOS_PENDING (Ogerpon→Grimmsnarl, Dragapult→Fezandipiti) or
   OOS_FAILED (Kangaskhan→Grimmsnarl, Grimmsnarl→Mewtwo) counters
        ↓
7. Never use rating/opponent-identity information (structurally unreliable)
```

## 14. Confidence Matrix

```text
Current meta identification:        HIGH
Meta drift (Grimmsnarl):            HIGH
Recent WR baseline:                 HIGH
Mewtwo → Fezandipiti:               HIGH confidence as a narrow matchup counter
Ogerpon → Grimmsnarl:               MEDIUM / LOW  — MEDIUM on the historical signal, LOW on
                                     production-readiness (OOS_PENDING)
Dragapult → Fezandipiti:            LOW — same OOS_PENDING situation, less runway than Ogerpon
Kangaskhan → Grimmsnarl:            HIGH confidence that this is a false positive (rejected)
Grimmsnarl → Mewtwo:                HIGH confidence that this is a false positive (rejected)
Rating-aware selection:             LOW — do not use, structurally unreliable
General Counter-Aware selection:    UNRESOLVED — insufficient exposure, not disproven
General meta-aware selection:       LOW/UNRESOLVED — small, resolution-dependent, never beat
                                     Recent WR's point estimate
General opponent-aware agent:       LOW — insufficient evidence to justify building it
Short-game effects:                 MEDIUM-HIGH — credible secondary finding
```

Final decision matrix:

| Decision | Evidence | Confidence | Action |
|---|---|---|---|
| Current meta identification | strong (9-archetype RECENT prior, sums to 1.0) | HIGH | use |
| Recent WR baseline | reproduced across weekly/daily resolution | HIGH | use |
| Mewtwo → Fezandipiti | OOS-confirmed (n=25/26, 84.0-84.6%) | HIGH | use narrowly |
| Ogerpon → Grimmsnarl | OOS-pending (n=17, stuck) | MEDIUM/LOW | monitor only |
| Dragapult → Fezandipiti | OOS-pending (n=15, stuck) | LOW | monitor only |
| Kangaskhan → Grimmsnarl | OOS-failed | HIGH (rejection) | reject |
| Grimmsnarl → Mewtwo | OOS-failed | HIGH (rejection) | reject |
| Rating-aware selection | structurally unreliable | LOW | do not use |
| Conservative Meta-Aware (general) | small, daily-only, resolution-dependent | MEDIUM | do not use as default; below Recent WR's point estimate |
| General Counter-Aware selection | insufficient exposure (0 opportunities) | UNRESOLVED | do not rely on |
| General opponent-aware agent | insufficient evidence | LOW | do not build yet |

## 15. Research Limitations

Full table in `results/meta/final_limitations.csv`.

- **Dataset limitation.** Current endpoint: `2026-08-10`. No newer data exists as of
  2026-08-11 (re-verified this phase).
- **OOS limitation.** Ogerpon→Grimmsnarl (n=17) and Dragapult→Fezandipiti (n=15) both detected
  too close to the dataset endpoint to reach the primary n≥25 OOS bar.
- **Rating limitation.** Player/opponent rating cannot be reliably resolved from this data
  source (~49-53% accuracy) — structural, not sample-size.
- **Long-tail limitation.** Only 42 of thousands of possible directed archetype pairs reach
  games≥20; only 5 ever reached the counter-detection CANDIDATE stage.
- **Temporal limitation.** Meta share and matchup strength both shift materially over the
  56-day window; recency-conditioned strategies are structurally weakest during high-change
  periods.
- **Selection limitation.** Deck-selection-level effects (~1.3-2.6pp) are much smaller and
  harder to demonstrate at conventional significance than raw matchup-level effects (which
  exceed 30pp for the strongest counters).

## 16. Future Update Protocol

```text
New daily data
        ↓
Re-run Phase 4.4 counter validation (build_validated_counter_model_v1.py, unchanged)
        ↓
Re-run Phase 4.5 counter-aware selection (build_counter_aware_deck_selection_v1.py, unchanged)
        ↓
Compare against this frozen final policy
        ↓
Version the model if evidence changes (do not silently merge new data into v1's results)
```

This final policy is not made dependent on future data arriving. If it never arrives before the
2026-08-16 Simulation deadline / 2026-09-13 Strategy deadline, the policy in Section 13 stands as
final for this project as-is.

## 17. Final Verdict

```text
Is the meta representation reliable?
YES

Is there a real exploitable matchup structure?
YES — narrowly, at the single-matchup level; not proven as a general opponent model

Is there at least one validated counter?
YES — Team Rocket's Mewtwo ex vs Fezandipiti ex (OOS_CONFIRMED)

Does validated counter information demonstrably improve aggregate deck selection?
UNRESOLVED

Is general meta-aware selection reliably superior to Recent WR?
NO

Is a general opponent-aware agent justified?
NO

Is a narrow validated-counter policy justified?
YES — narrowly
```
