# Deck Selection v1

Tags used throughout: **[FACT]** verified directly from source data, **[RESULT]**
computed this session, **[DESIGN]** a modeling choice made this session,
**[LIMITATION]** an explicit gap, **[QUESTION]** open. Per §22 of the phase
prompt: language is calibrated to strong / moderate / weak / inconclusive
evidence, never "optimal," and no historical correlation is described as
causal.

Built by `tools/build_deck_selection_v1.py`. Reads only
`results/meta/episodes_summary.parquet` (raw, for the walk-forward backtest)
plus `results/meta/archetype_features.csv` / `archetype_matchups.csv`
(Phase 4.2, used only for the descriptive, non-walk-forward counter analysis
in §9). No new episodes downloaded. Rating not used anywhere.

---

## 1. Objective

Answer one question with evidence, not assertion: **can we select a deck more
effectively by explicitly accounting for the observed meta distribution and
matchup structure, versus simple baselines?** This is an evaluation of
decision *rules* applied to historical data — not an agent, not a policy that
plays games, and not a claim about causal deck strength.

---

## 2. Dataset

**[FACT]** Same canonical dataset as Phases 4.1/4.2, unchanged: **3,499
episodes**, 6,982 decisive deck-slots, 2026-06-16 to 2026-08-10 (8 calendar
weeks). **0 additional episodes downloaded this phase.** Weekly deck-slot
counts: week 1=336, 2=336, 3=326, 4=1006, 5=988, 6=1340, 7=1328, 8=1326
(period boundaries EARLY=weeks 1-3, MIDDLE=4-5, RECENT=6-8, identical to
Phase 4.1's definition).

---

## 3. Validation Method

**[DESIGN] Chronological split, two schemes, both walk-forward safe:**

**Primary — rolling weekly windows (7 evaluation periods)**: for test week
`t` in 2..8, `TRAIN` = all decisive deck-slots from weeks `1..t-1`, `TEST` =
week `t` only. Every strategy's meta prior, win-rate estimates, and matchup
table are computed **exclusively from `TRAIN`**; the selected archetype is
then evaluated against `TEST`'s actual realized outcomes. This is the primary
evaluation set because 7 periods give more statistical power than 2, and the
per-week sample sizes (326-1,340 deck-slots) are large enough to support
meaningful `TRAIN` meta estimates from week 3 onward.

**Secondary — coarse period-based windows (2 evaluation periods)**, matching
the phase prompt's literal illustrative example:

- `COARSE_A`: TRAIN = EARLY (weeks 1-3), TEST = MIDDLE (weeks 4-5)
- `COARSE_B`: TRAIN = EARLY+MIDDLE (weeks 1-5), TEST = RECENT (weeks 6-8)

Both schemes are stored in `results/meta/evaluation_windows.csv` and both
appear in every downstream results file with a `scheme` column — nothing is
discarded, the rolling scheme is simply treated as primary for headline
conclusions because n=2 periods cannot support any statistical claim on its
own.

**[DESIGN] Leakage prevention, mechanically enforced**: every strategy
function receives only a `WindowStats` object built from `TRAIN` rows (usage
counts, win/loss counts, archetype-pair matchup counts, and a
"recent-within-train" sub-window equal to `TRAIN`'s own most recent calendar
week — never `TEST`). The evaluation step is a separate function that only
ever reads the already-selected archetype id and looks up its actual outcome
in `TEST`. No shared state, no global caches keyed by full-dataset stats are
used inside the strategy functions. Verified: `train_games` in
`deck_selection_backtest.csv` for `ROLL_W2` = 336 (exactly week 1, not more),
confirming no forward information reached that window's decision.

---

## 4. Strategies

All seven strategies operate at the **archetype** level (`cluster_id`), never
the 619 exact decklists, per the phase prompt's instruction. Every strategy
is restricted to **candidates**: archetypes with `TRAIN` games ≥ 50 (§10). The
same 20/50/100-game confidence tiers from Phase 4.2 are reused for matchup
reliability (INSUFFICIENT/LOW_CONFIDENCE/USABLE/HIGH_CONFIDENCE).

### A. Most Popular
`argmax` of `TRAIN` usage share among candidates.

### B. Highest Historical Win Rate
`argmax` of raw `TRAIN` win rate among candidates (the ≥50-game candidate
floor **is** the minimum-sample guard — a 5-game 100% archetype is never a
candidate at all).

### C. Recent Win Rate
`argmax` of win rate within `TRAIN`'s own most recent calendar week, restricted
to candidates with ≥20 games in that recent sub-window. **[DESIGN] fallback**:
if no candidate clears 20 recent games, falls back to Strategy B's pick for
that window (flagged `fallback_to_B_insufficient_recent_sample` in the
`selection_note` column — this never actually triggered in this run, see §5).

### D. Meta-Aware Expected Win Rate
For each candidate A: `EWR(A) = Σ_B P_train(B) × matchup_estimate(A,B)`,
summed over every opponent archetype B observed in `TRAIN` (weighted by its
`TRAIN` usage share), `argmax` over candidates A. **[DESIGN] matchup
estimate & fallback policy**: if the A-vs-B pair has ≥50 `TRAIN` games
(USABLE+), use the raw empirical win rate. Otherwise (LOW_CONFIDENCE or
INSUFFICIENT — i.e. **not silently assumed 50%**), fall back to
`shrinkage_wr(A) - shrinkage_wr(B) + 0.5`, clipped to `[0.05, 0.95]` — each
archetype's own Beta-Binomial-shrunk overall strength (K=30 pseudo-games
toward 0.5, same as Phase 4.2), combined additively. This is "Policy 2" from
§9. A parallel **`D_policy1_neutral_variant`** row uses "Policy 1" (0.5 flat)
for the same insufficient pairs, run alongside D throughout for direct
comparison (§9, §18).

### E. Recent Meta-Aware
Identical formula to D, but `P(B)` uses `TRAIN`'s recent-within-train share
instead of full-`TRAIN` share. **[DESIGN] fallback**: if the recent sub-window
has <20 total games, falls back to D's full-history prior for that window
(flagged).

### F. Anti-Meta
**[DESIGN] dominant-set definition**: archetypes whose recent-within-train
share ≥ 15% (same threshold Phase 4.2 used for `CURRENT_DOMINANT`). `EWR`
is computed only against this dominant set, re-normalized to sum to 1 across
its members (not the single top deck) — directly implementing §7's
instruction to consider "the entire relevant opponent distribution," not just
the #1 deck. **[DESIGN] fallback**: if no archetype clears 15% share in a
given window's recent sub-window (common in early, thin windows), falls back
to Strategy D's full-meta pick, flagged `fallback_to_D_no_dominant_archetype`.

### G. Conservative Meta-Aware
Identical formula to D, but every matchup estimate — **including
USABLE/HIGH_CONFIDENCE pairs, not just gap-filled ones** — is replaced by its
95% Wilson **lower bound** (falling back to the same Policy-2 estimate only
when a pair has literally zero `TRAIN` games). This directly executes §8's
requirement not to treat an 82%-at-n=77 pair the same as a 62%-at-n=400 pair:
the Wilson lower bound shrinks the former far more than the latter.

---

## 5. Backtest Results

**[RESULT]** Full per-window, per-strategy detail: `deck_selection_backtest.csv`
(81 rows = 9 windows × [7 strategies + 1 policy-1 variant + 1 oracle]).
Selected archetypes varied meaningfully across windows and strategies — no
strategy degenerated into always picking the same deck. The
`C_recent_wr`-fallback path was never triggered (every rolling window's
recent-within-train sub-window had ≥1 candidate clearing 20 games from week 2
onward); `F`'s no-dominant-archetype fallback triggered in `ROLL_W2` and
`ROLL_W3` (early windows where no single deck yet held 15% recent share).

**[RESULT] Every strategy-window pick produced measurable `TEST` data** — 0 of
56 rolling-window strategy picks had 0 `TEST` games (validated,
`deck_selection_backtest.csv` `test_games` column), so no aggregate below
relies on imputed or dropped observations.

---

## 6. Strategy Comparison

**[RESULT] Rolling-weekly scheme (primary, n=7 periods)** —
`strategy_comparison.csv`:

| Strategy | Games | Wins | Pooled OOS win rate | Mean period WR | Median | Worst | Best |
|---|---|---|---|---|---|---|---|
| A — Most Popular | 1,891 | 883 | **46.69%** | 48.02% | 50.00% | 42.52% | 53.85% |
| B — Highest Historical WR | 698 | 336 | 48.14% | 46.87% | 45.96% | 37.84% | 55.77% |
| C — Recent WR | 595 | 301 | **50.59%** | 50.43% | 50.00% | 37.84% | 63.41% |
| D — Meta-Aware EWR (full history) | 689 | 332 | 48.19% | 47.41% | 45.96% | 37.84% | 59.18% |
| D — policy-1 neutral variant | 439 | 215 | 48.97% | 53.18% | 50.00% | 32.26% | 100.00%* |
| E — Recent Meta-Aware | 615 | 287 | 46.67% | 46.69% | 45.96% | 37.84% | 54.17% |
| F — Anti-Meta | 701 | 330 | 47.08% | 47.15% | 48.15% | 37.84% | 54.17% |
| G — Conservative Meta-Aware | 1,510 | 714 | 47.28% | 46.88% | 50.00% | 37.84% | 53.85% |
| **ORACLE (not available at decision time)** | 365 | 229 | **62.74%** | 63.70% | 61.70% | 58.33% | 72.73% |

(*) The policy-1 variant's "best" of 100% is a single-game fluke selection in
`ROLL_W5` (`Mega Lucario ex`, n=1 test game) — a direct illustration of why
Policy 2's archetype-strength fallback (used by the primary D) is preferred
over the neutral-50% fallback, which let one insufficient-data pair dominate
a selection.

**[RESULT] Point estimates alone would suggest Strategy C (Recent Win Rate,
50.6%) is the best-performing deployable strategy**, ahead of every
meta-aware strategy (D/E/F/G all cluster 46.7%-48.2%) and ahead of the
simplest baseline A (46.7%). **This ordering is explicitly not treated as a
finding of superiority — see §7.**

**[RESULT] Coarse scheme (secondary, n=2 periods)**: pooled win rates cluster
even more tightly (47.7%-49.1% across A/B/C/D/E/F, G=50.0%) — directionally
consistent with the rolling result (no strategy clearly separates from the
pack), but n=2 is far too small to support any comparison beyond "consistent
with the rolling-window finding."

**[RESULT] The Oracle (§14) pools 62.7% across the same 7 periods** — proof
that a real, non-trivial predictable edge exists in this meta (the
best-in-hindsight archetype reliably beats 50%, and by a wide margin), even
though none of the decision-time-available strategies below capture more than
a few points of it.

---

## 7. Statistical Significance

**[RESULT] No strategy shows a statistically convincing advantage over
Strategy A (Most Popular) at the rolling-weekly evaluation scale (n=7 paired
periods)**:

| Strategy vs A | Mean paired diff | Sign-test p | Wilcoxon p | Pooled 2-proportion p |
|---|---|---|---|---|
| B | −1.16pp | 1.000 | 0.813 | 0.514 |
| C | **+2.40pp** | 1.000 | 0.688 | 0.097 |
| D | −0.62pp | 1.000 | 0.813 | 0.502 |
| D (policy-1) | +5.15pp | 1.000 | 1.000 | 0.389 |
| E | −1.33pp | 1.000 | 0.625 | 0.990 |
| F | −0.87pp | 1.000 | 0.813 | 0.863 |
| G | −1.14pp | 1.000 | 1.000 | 0.732 |
| **ORACLE** | **+15.68pp** | **0.0156** | **0.0156** | **<0.001** |

**[RESULT] Every deployable strategy's sign-test p-value against A is 1.000**
— at n=7 periods, no strategy beat A in a majority of periods by even a
minimal margin large enough to register (Strategy C came closest at 9.7% on
the less-appropriate pooled proportion test, still short of conventional
significance). **The Oracle is the only row that clears significance on
every test** — expected and appropriate, since it is constructed from
perfect hindsight and is the diagnostic upper bound, not a candidate
strategy.

**[RESULT] Conclusion: no reliable evidence that any of Strategies B-G
outperforms the simplest baseline (A) at this sample size.** Strategy C's
higher point estimate (50.6% vs 46.7%) is the largest gap observed, but with
sign-test p=1.0 and a pooled-proportion p=0.097 (not below the conventional
0.05 bar, and inappropriate as the primary test anyway since it ignores
period-pairing), this is correctly reported as **weak, not moderate or
strong, evidence** — consistent with §22's explicit instruction not to
declare "61%>60%" superiority.

**[LIMITATION]** With only 7 (rolling) or 2 (coarse) evaluation periods, the
statistical power to detect even a real 3-5pp advantage is low — this
analysis cannot rule out a small true advantage for any strategy; it can only
say the available evidence does not establish one.

---

## 8. Meta Regime Analysis

**[DESIGN]** Jensen-Shannon divergence (base-2, bounded [0,1]) between
consecutive weeks' full archetype-share distributions, computed **only from
`TRAIN`-visible week-over-week transitions** (i.e. describes the meta itself,
not a decision — this is a diagnostic, not part of any strategy's selection
logic). Regime label = `HIGH_CHANGE` if a test week's JS divergence from the
prior week is ≥ the median of the 7 observed values, else `LOW_CHANGE`
(median split, chosen because tertiles would leave only ~2 periods per
bucket — even more underpowered).

**[RESULT]**

| Test week | JS divergence vs prior week | Regime |
|---|---|---|
| 2 | 0.460 | HIGH_CHANGE |
| 3 | **0.620** | HIGH_CHANGE |
| 4 | 0.386 | HIGH_CHANGE |
| 5 | 0.387 | HIGH_CHANGE |
| 6 | 0.306 | LOW_CHANGE |
| 7 | 0.289 | LOW_CHANGE |
| 8 | 0.297 | LOW_CHANGE |

The meta was measurably more volatile in the first half of the dataset
(weeks 2-5, all above the median) and stabilized in the second half (weeks
6-8) — directionally consistent with Phase 4.1/4.2's finding that most of the
dramatic archetype-share swings (Mega Lucario ex's collapse, Marnie's
Grimmsnarl ex's rise) happened earlier in the window, with RECENT-period
shares comparatively steadier week-to-week.

**[RESULT] Mean per-period advantage over Strategy A, split by regime**
(n=4 HIGH_CHANGE periods, n=3 LOW_CHANGE periods — very small groups,
descriptive only):

| Strategy | HIGH_CHANGE mean advantage | LOW_CHANGE mean advantage |
|---|---|---|
| B | −5.01pp | +3.99pp |
| C | −0.06pp | +5.69pp |
| D | −5.01pp | +5.24pp |
| E | −5.01pp | +3.57pp |
| F | −5.01pp | +4.65pp |
| G | −3.04pp | +1.38pp |
| ORACLE | +16.00pp | +15.25pp |

**[RESULT] Every meta-aware and baseline strategy (B-G) shows a negative or
near-zero advantage during HIGH_CHANGE weeks and a positive advantage during
LOW_CHANGE weeks** — the opposite of the naive expectation that meta-aware
selection should help most when the meta is moving fastest. A plausible
**[HYPOTHESIS]**, consistent with what these strategies actually compute:
they all condition on the *recent past* (recent win rate, recent-within-train
prior), and when the meta is genuinely regime-shifting week to week, the most
recent past is a systematically worse predictor of the immediate future than
it is during a stable stretch — this is a believable mechanism, not a
statistical certainty at n=3-4 per bucket. **[LIMITATION]** This finding must
be read as directional only; it is not statistically tested here (too few
periods per bucket for any test to be meaningful) and should not be treated
as established without a larger sample.

---

## 9. Counter Analysis

**[DESIGN]** Descriptive, full-history analysis (not walk-forward — this
answers "what do we currently know," reusing Phase 4.2's validated
`archetype_matchups.csv` credibility gate: games≥50 AND Wilson lower bound
>0.5), for the 9 archetypes with adequate RECENT-period sample. Full table:
`results/meta/counter_analysis.csv`.

**[RESULT]**

| Target (popular deck) | Recent share | Credible counter | Counter games | Counter win rate | Counter's own recent share | Verdict |
|---|---|---|---|---|---|---|
| Marnie's Grimmsnarl ex | 44.3% | Teal Mask Ogerpon ex | 77 | 81.8% | 4.8% | **STRONG_AND_RELEVANT** |
| Fezandipiti ex | 16.8% | Team Rocket's Mewtwo ex | 85 | 76.5% | 5.5% | **STRONG_AND_RELEVANT** |
| Fezandipiti ex | 16.8% | Dragapult ex | 76 | 64.5% | 4.6% | **STRONG_AND_RELEVANT** |
| Team Rocket's Mewtwo ex | 5.5% | Marnie's Grimmsnarl ex | 134 | 59.7% | 44.3% | **STRONG_AND_RELEVANT** |
| Mega Kangaskhan ex | 8.7% | — | — | — | — | NO_CREDIBLE_COUNTER_FOUND |
| Mega Lopunny ex | 6.8% | — | — | — | — | NO_CREDIBLE_COUNTER_FOUND |
| Teal Mask Ogerpon ex | 4.8% | — | — | — | — | NO_CREDIBLE_COUNTER_FOUND |
| Dragapult ex | 4.6% | — | — | — | — | NO_CREDIBLE_COUNTER_FOUND |
| Cynthia's Garchomp ex | 4.2% | — | — | — | — | NO_CREDIBLE_COUNTER_FOUND |

**[RESULT] All 4 credible counters found are `STRONG_AND_RELEVANT`, not
`STRONG_BUT_RARE`** — every counter archetype itself clears the 20-game
recent-sample floor (in fact all 4 clear it comfortably, 4.6%-44.3% recent
share), so there is no case in this dataset of "a lopsided matchup that's
statistically real but the counter deck is too obscure to actually queue
into." This is a genuinely favorable finding for deck-selection
practicality: the identified counters are decks a player could realistically
choose to play, not curiosities.

**[RESULT] The single most actionable finding**: **Teal Mask Ogerpon ex
credibly counters Marnie's Grimmsnarl ex (81.8%, n=77)**, and Grimmsnarl is
by far the most popular deck (44.3% recent share) — this one relationship
alone is responsible for the bulk of Ogerpon's high expected win rate against
the current meta (§11).

**[RESULT] 5 of the 9 major archetypes have no credible counter at all** in
this dataset (Kangaskhan, Lopunny, Ogerpon itself, Dragapult, Garchomp) — this
is a data-coverage limitation (matchup pairs involving these as the
*countered* side mostly sit at LOW_CONFIDENCE/INSUFFICIENT sample, not
evidence that they have no real counter).

---

## 10. Sensitivity Analysis

**[RESULT]** Full detail: `strategy_sensitivity.csv`. All variants computed
on the full dataset (today's decision, §11) since that is what §18 asks to
stress-test.

**[RESULT] Matchup minimum-sample threshold (20 / 50 / 100 games)**: the
selected archetype is **Teal Mask Ogerpon ex in all three cases** — only the
expected-win-rate point estimate moves (57.2% / 63.4% / 55.2%), not the
recommendation itself.

**[RESULT] Prior recency (full history / recent 50% / recent 25% /
RECENT-period)**: **Teal Mask Ogerpon ex is selected under every variant**,
with expected win rate ranging 63.0%-66.7% depending on which slice defines
"the opponent I expect to face."

**[RESULT] Uncertainty handling (raw+fallback vs conservative Wilson-lower)**:
still **Teal Mask Ogerpon ex** in both cases, though the conservative
estimate drops sharply (63.4% → 41.9%) — expected, since a Wilson lower bound
is a deliberately pessimistic one-sided bound applied to *every* matchup
(including thin ones), not a best estimate; averaging pessimistic bounds does
not itself carry a clean confidence-interval interpretation as a whole. The
qualitative conclusion — Ogerpon remains the top pick — survives; the
absolute number should not be read as "Ogerpon's true expected win rate has a
95% floor of 42%."

**[RESULT] The recommendation is robust across all 9 sensitivity variants
tested** (`changed_from_default = False` in every row of
`strategy_sensitivity.csv`). This robustness traces directly to §9's finding:
Ogerpon's edge is anchored in one large, credible matchup advantage against
the single most popular deck (44% of the meta), which dominates the weighted
sum regardless of how the many small, uncertain matchups are treated.

---

## 11. Current Recommendation

**[DESIGN]** Uses **all 3,499 episodes** as the information set (there is no
future data to hold out for "today's" decision). Matchup estimates use the
full dataset (most reliable pairwise data available); the opponent
distribution uses Phase 4.1/4.2's canonical RECENT period (weeks 6-8,
~4,000 deck-slots) rather than a noisier single-week slice, for consistency
with the already-validated current-meta read. Candidates: archetypes with
≥50 total games AND ≥20 RECENT-period games (9 archetypes, matching Phase
4.2's `meta_prior.csv` filtered set exactly).

**[RESULT] `results/meta/current_deck_recommendation.csv`, full ranking:**

| Rank | Archetype | Recent share | Recent WR | Expected WR vs current meta | Conservative EWR | Counters it has | Counters against it |
|---|---|---|---|---|---|---|---|
| 1 | **Teal Mask Ogerpon ex** | 4.8% | 56.7%* | **66.4%** | 44.6% | 1 | 0 |
| 2 | Dragapult ex | 4.6% | 57.1% | 58.0% | 43.4% | 1 | 0 |
| 3 | Mega Lopunny ex | 6.8% | 56.8% | 55.4% | 42.0% | 0 | 0 |
| 4 | Cynthia's Garchomp ex | 4.2% | 49.1% | 52.1% | 38.0% | 0 | 0 |
| 5 | Mega Lucario ex | 1.5% | 61.7%(n=60) | 51.3% | 33.8% | 0 | 0 |
| 6 | Mega Kangaskhan ex | 8.7% | 50.1% | 50.7% | 40.3% | 0 | 0 |
| 7 | Team Rocket's Mewtwo ex | 5.5% | 48.9% | 49.6% | 34.9% | 1 | 1 |
| 8 | Marnie's Grimmsnarl ex | 44.3% | 48.5% | 48.0% | 41.8% | 1 | 1 |
| 9 | Fezandipiti ex | 16.8% | 47.4% | 45.3% | 39.5% | 0 | 2 |

(*) Ogerpon's own recent win rate (56.7%) is close to but not identical to
its raw overall win rate reported in Phase 4.2 (55.8%) — both are legitimate,
slightly different slices (RECENT-period-only vs all-time).

**[RESULT] Recommended archetype: Teal Mask Ogerpon ex.** This is **not**
simply the highest-recent-win-rate deck (that distinction number-for-number
is close between several top-5 decks, e.g. Mega Lucario ex's 61.7% at n=60)
— the reason to prefer Ogerpon specifically is the combination of:

1. **Highest expected win rate against the actual current opponent
   distribution (66.4%)**, driven by a statistically credible (not lucky)
   81.8% win rate at n=77 against Marnie's Grimmsnarl ex, the single deck a
   player is most likely to face (44.3% of the field);
2. **Zero credible counters found against it** (§9) — unlike Marnie's
   Grimmsnarl ex (1 credible counter: Ogerpon itself) and Fezandipiti ex
   (2 credible counters), choosing Ogerpon does not walk into a known,
   statistically established bad matchup;
3. **Robust to every sensitivity variant tested** (§10) — the pick does not
   depend on a fragile choice of threshold, recency window, or
   uncertainty-handling method.

**[LIMITATION]** Ogerpon's own overall sample (199 total games) is smaller
than Marnie's Grimmsnarl ex's (2,225) or Fezandipiti ex's (1,355), and most of
its individual matchup cells outside the Grimmsnarl pairing are
LOW_CONFIDENCE or INSUFFICIENT (§9's counter table). The recommendation rests
heavily on one strong, credible matchup plus conservative-but-uncertain
fallback estimates for the rest of the field — a real, defensible recommendation,
but not a claim that Ogerpon is comprehensively "solved" against the whole
meta the way its single best matchup is.

---

## 12. Limitations

1. **Small number of evaluation periods** (7 rolling, 2 coarse) is the
   dominant limitation of this whole phase — it is the reason §7 could not
   find statistically convincing evidence for any strategy, even where a real
   gap plausibly exists (the Oracle shows the achievable ceiling is far above
   any deployable strategy's result).
2. **Fallback policies (Policy 2, dominant-set, recent-window) are reasonable
   documented choices, not the only defensible ones** — §18's threshold sweep
   shows the *current recommendation* is robust to the specific choices made,
   but the *backtest comparison numbers* in §6-7 were only computed under one
   configuration each; a full grid backtest (every strategy × every
   threshold × every window) was out of scope for this phase.
3. **The regime-change finding (§8) is descriptive and directional only** —
   3-4 periods per regime bucket cannot support a hypothesis test.
4. **Counter analysis (§9) is retrospective/full-history**, not walk-forward
   — it describes "what we know today," not what a decision-time strategy
   could have known at any earlier point.
5. **Rating excluded throughout** (inherited from Phase 4.1's structural
   finding).
6. **Historical correlation, not causal advantage**: every strategy here is
   evaluated on "if a player queued with archetype X, what was their observed
   win rate" — this reflects the realized population of players who actually
   chose that archetype during that window (their skill, their exact
   decklist, their play), not a controlled causal estimate of "archetype X's
   win rate holding all else equal." This is a data-source-level limitation
   this phase cannot resolve, only flag.

---

## 13. Conclusion

**[RESULT]** The Oracle result (62.7% pooled, p<0.001 vs Strategy A) proves a
real, sizeable predictive edge exists in this meta in principle — archetype
choice genuinely matters, and some archetypes reliably outperform others in
specific future windows. **However, none of the seven decision-time-available
strategies tested (A-G) captured a statistically convincing share of that
edge** at the current evaluation scale (7 rolling periods). Strategy C
(Recent Win Rate) had the best point estimate (50.6% vs baseline A's 46.7%)
but this did not clear even a weak significance bar (sign-test p=1.0, pooled
p=0.097). The meta-aware strategies (D/E/F/G) performed statistically
indistinguishably from the simplest baseline (A) in the backtest, despite
being individually well-motivated and, in the case of the **current, one-shot
recommendation (§11)**, producing a specific, well-justified, and robust pick
(Teal Mask Ogerpon ex).

**[RESULT] This is a genuinely mixed result, not a clean win for meta-aware
selection** — and per §22, that is reported as exactly that, not dressed up
as a positive finding.

---

## 14. Recommendation for Next Phase

**[RESULT]** The honest state of evidence does **not** justify moving to an
opponent-aware gameplay agent yet (Q8, below) — the backtest could not
establish that any of the meta-aware selection rules reliably beat picking
the most popular deck, which is the simplest possible baseline an agent would
need to beat to justify the added complexity of opponent modeling.

**Suggested next steps, in priority order**:

1. **Scale the evaluation, not (necessarily) the deck-selection sophistication**:
   the single biggest lever to turn "weak/inconclusive" into a real answer is
   more evaluation periods (e.g. daily rather than weekly rolling windows,
   which Phase 4.1's data supports since dates are daily-resolution) — this
   is a re-analysis of already-available data, not a new download.
2. **If pursuing opponent-aware agent work regardless of this result**, scope
   it narrowly around the one specific, statistically credible, robust
   finding this phase produced: Teal Mask Ogerpon ex's matchup advantage over
   Marnie's Grimmsnarl ex — a targeted counter-pick heuristic, not a general
   opponent-inference system, would be the minimal justified next step.
3. **Do not build a general opponent-archetype-inference model yet** — this
   phase's own oracle-vs-strategy gap suggests the current information (meta
   prior + matchup table) is not the bottleneck; evaluation power is.

---

## Answers to the Required Questions (§23)

**Q1 — Does meta-aware deck selection outperform the most-popular-deck
baseline?** No reliable evidence that it does. Point estimates for D/E/F/G
(46.7%-48.2%) are statistically indistinguishable from A (46.7%); none clear
even a weak significance threshold.

**Q2 — Does recent-meta weighting outperform full-history weighting?** No.
Strategy E (recent prior) scored *lower* than Strategy D (full-history prior)
in the backtest (46.7% vs 48.2%), though the gap is not significant either
way — inconclusive, with a slight point-estimate edge to full history, not
recency.

**Q3 — Does uncertainty-aware matchup estimation improve robustness?** Yes,
in the one place this phase could directly test it: the *current
recommendation* (§10-11) is stable across matchup-threshold, prior-recency,
and raw-vs-conservative variants specifically because the conservative
(Strategy G) and raw (Strategy D) methods agree on the top pick. In the
backtest, G did not outperform D (47.3% vs 48.2%, not significant) — so
"improves robustness of the specific recommendation" is supported; "improves
backtested win rate" is not.

**Q4 — Does anti-meta selection provide measurable benefit?** No. Strategy F
(47.1%) was statistically indistinguishable from A (46.7%) and from every
other strategy tested.

**Q5 — How large is the advantage, if any?** At most a few percentage points
(Strategy C's +2.4pp mean paired difference over A is the largest observed
among deployable strategies), against a backdrop where the achievable ceiling
(Oracle) is +16pp — i.e. even the best-looking deployable strategy captures
roughly a sixth of the theoretically available edge, if any of its point
estimate reflects a real effect at all.

**Q6 — Is the advantage statistically convincing?** No. Every deployable
strategy's sign-test p-value against baseline A is 1.000; only the Oracle
(not a deployable strategy) clears significance.

**Q7 — Which strategy would we actually deploy using today's available
information?** For a one-shot "what deck should we play right now" decision
(§11), **Teal Mask Ogerpon ex**, selected via the Strategy-D/E-style
meta-aware expected-win-rate method (robust across all sensitivity variants
tested, §10) — this is a defensible pick for a single decision, distinct from
claiming the *method* (D/E in general) is a proven better process than
Strategy A over repeated decisions, which §6-7 do not support.

**Q8 — Is the advantage strong enough to justify moving to an opponent-aware
agent?** No, not on this evidence. See §14 for the recommended narrower next
step instead.

---

**Episodes used: 3,499. Additional downloads: 0. Rating used: NO.**
Per the phase prompt's explicit instruction, no agent/RL/MCTS/search/gameplay
policy implementation follows from this report without separate authorization.
