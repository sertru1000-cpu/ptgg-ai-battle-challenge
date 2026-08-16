# Validated Counter Model v1

**Phase 4.4.** Built on `results/meta/episodes_summary.parquet` (3,499 episodes / 6,982 decisive
deck-slots, 2026-06-16 to 2026-08-10) and the Phase 4.1-4.3b outputs. Zero new episodes
downloaded. Pipeline: `tools/build_validated_counter_model_v1.py`. Statistical thresholds +
temporal detection + persistence + OOS confirmation + expiration only — no RL, MCTS, search,
opponent inference, embeddings, or trained model of any kind.

Claim tags used throughout: **[FACT]** = directly computed from the data, **[HYPOTHESIS]** =
plausible interpretation not itself statistically tested, **[OPEN QUESTION]** = flagged for
future work.

---

## 1. Objective

Determine which historical archetype-matchup advantages are reliable, actionable counter
relationships versus statistical artifacts, by requiring every candidate to survive: a
pre-registered statistical + effect-size gate, temporal persistence, and genuine walk-forward
out-of-sample (OOS) confirmation — evaluated identically for every candidate, including the
project's two known positive controls and one known negative control. No candidate is
hard-coded as valid; the pipeline only ever sees `A`, `B`, and dates.

## 2. Data

- Canonical source: `results/meta/episodes_summary.parquet`, filtered to `outcome_type ==
  "DECISIVE"` — **6,982 deck-slots / 3,491 games**, matching the project's canonical episode
  count (3,499 episodes minus 6 ERROR_OR_TIMEOUT and 2 of the 10 DRAW-pair episodes'
  non-decisive rows are excluded per side, same convention as every prior phase). **0 additional
  downloads.**
- Archetype identity: `player_deck_cluster_id` / `opponent_deck_cluster_id`, reusing Phase 4.1's
  deterministic clustering — no re-clustering done here.
- **Named-archetype universe: 11** (`Cynthia's Garchomp ex`, `Dragapult ex`, `Fezandipiti ex`,
  `Iono's (Bellibolt/Voltorb)`, `Marnie's Grimmsnarl ex`, `Mega Abomasnow ex`, `Mega Kangaskhan
  ex`, `Mega Lopunny ex`, `Mega Lucario ex`, `Teal Mask Ogerpon ex`, `Team Rocket's Mewtwo ex`).
  `UNLABELED_CLUSTER_*` buckets (heterogeneous leftover-deck groupings from Phase 4.1, not
  archetypes a player could deliberately pilot) are excluded from the counter/target candidate
  universe — a player cannot "pick" an unlabeled cluster, so recommending one as a counter would
  be meaningless. This mirrors the convention already used by `counter_analysis.csv` and
  `current_deck_recommendation.csv` in Phase 4.3.
- Candidate universe: every ordered pair `(A, B)`, `A != B`, among the 11 named archetypes with
  **full-dataset games(A vs B) >= 20** (the most permissive of the three sensitivity floors —
  a pair that never reaches 20 games across the whole dataset cannot pass any sensitivity variant
  either, so nothing is lost by filtering here) → **42 directed pairs** out of 110 possible.

## 3. Counter Definition

`A -> B` (`counter_archetype -> target_archetype`) is evaluated as its own, non-symmetric
object. `A -> B` and `B -> A` are tracked as two independent rows through the entire pipeline —
neither status nor sample data is shared between them. Both directions of every one of the 21
named-archetype-pair matchups with >=20 full-dataset games are in the 42-pair universe.

## 4. Detection Gate

**[FACT — declared before running detection, per Sec 35's no-fishing rule.]**

**Confidence level:** 95% Wilson score interval (z=1.96), reused verbatim from Phase 4.2/4.3b.

**Rolling "current" meta-share window:** 14 calendar days, ending strictly *before* the
evaluation date T (`[T-14, T)`), reusing Phase 4.3b's already-established 14-day window. Shares
are computed as archetype deck-slots / total deck-slots in the window (same per-side convention
as `meta_prior.csv`).

**Target relevance tiers** (fixed, not re-derived per date):
- `HIGH`: rolling-14d share >= 15% (reuses Phase 4.2's `DOMINANT_RECENT_SHARE` constant exactly)
- `MEDIUM`: 5% <= share < 15%
- `LOW`: share < 5%

**Counter availability floor:** rolling-14d counter share >= 1% (`COUNTER_MIN_META_SHARE`) — a
low, deliberately permissive floor beneath the LOW/MEDIUM boundary, meant only to exclude
counters appearing in a practically negligible number of games, not to gatekeep on popularity.

**Primary matchup thresholds:** minimum sample **n >= 50**; win rate **>= 60%** (primary effect
size); Wilson lower bound **> 50%**. Sensitivity variants (computed separately, never substituted
for the primary result): sample n >= 20 / n >= 100; effect size 55% / 65% / 70%.

**Full detection gate** (all 5 conditions, evaluated using only data strictly before T):

| # | Condition |
|---|---|
| 1 | `games(A vs B)` before T `>= 50` |
| 2 | `win_rate(A vs B)` before T `>= 0.60` |
| 3 | `Wilson_lower(A vs B)` before T `> 0.50` |
| 4 | `target_meta_share_14d(T)` tier in `{MEDIUM, HIGH}` (>= 5%) |
| 5 | `counter_meta_share_14d(T)` `>= 1%` |

`CANDIDATE` status requires only conditions 1-3 (Sec 5-7's statistical + effect-size gate, no
relevance filter yet). Full gate (1-5) is what `DETECTED` requires.

## 5. OOS Confirmation Method

**Persistence (Sec 13):** the full 5-condition gate must hold on **2 consecutive daily
evaluation points** before a candidate freezes into `DETECTED`. The streak resets to 0 (not the
`candidate_date`) whenever the full gate fails on an intervening day.

**Freeze (Sec 14):** at the second consecutive passing date, `historical_games`,
`historical_win_rate`, `historical_wilson_lower`, `target_meta_share`, `counter_meta_share` are
recorded exactly as of that date and never recomputed retroactively.

**OOS window:** games with `player=A, opponent=B, date >= detection_date`, in chronological
order. Horizons evaluated: next 25 / 50 / 100 / 150 games, only where that many OOS games
actually exist (Sec 15) — plus an "ALL_AVAILABLE" horizon reported for transparency even below
25 games (not used in the confirmation decision).

**Primary OOS confirmation criterion — declared before viewing final results:**
`OOS_PRIMARY_HORIZON = 25` games (the smallest Sec 15 horizon). This was chosen *because* this
56-day dataset gives matchup pairs little runway: reaching the n>=50 historical bar in the first
place consumes much of the calendar, so few pairs can plausibly accumulate 50+ *further* OOS
games before the dataset ends on 2026-08-10. Using n=25 as primary was a deliberate adaptation to
this dataset's actual data budget, made before any pair's OOS numbers were computed — not
selected after seeing which threshold looked best.

- **`OOS_CONFIRMED`** if `oos_games(25) >= 25` and `oos_win_rate >= 55%` and `oos_wilson_lo >
  50%` (Sec 16's "stronger" suggested rule).
- **`OOS_FAILED`** if `oos_games(25) >= 25` and (`oos_win_rate < 50%` **or** it simply doesn't
  clear the confirmation bar above). Two sub-reasons are recorded for transparency:
  `COLLAPSED_BELOW_50PCT` (win rate fell under breakeven) vs. `DID_NOT_CLEAR_PRIMARY_BAR`
  (positive but not statistically/materially convincing at n=25 — at this sample size a Wilson
  lower bound above 50% needs roughly a 68%+ point estimate, so this bucket is not a fine
  distinction in practice).
- **`OOS_PENDING`** if fewer than 25 future games exist yet — explicitly *not* interpreted as
  failure (Sec 28).

Failure-threshold sensitivity (45% / 48%, vs. the primary 50%) is reported in
`counter_sensitivity_analysis.csv`, clearly separated from the primary result.

## 6. Counter Lifecycle

Every candidate pair carries the full field set from Sec 20
(`results/meta/counter_registry.csv`): `counter_id`, `counter_archetype`, `target_archetype`,
`candidate_date`, `detection_date`, `historical_games/win_rate/wilson_lower`,
`target_meta_share_at_detection`, `counter_meta_share_at_detection`, `oos_status` and detail,
`oos_primary_horizon_*`, `confirmation_date`/`failure_date`, `target_current_meta_share` /
`target_current_relevance_tier`, `counter_current_meta_share`, final `status`, `expired_reason`.

For any counter reaching `OOS_CONFIRMED`, `results/meta/counter_lifecycle.csv` additionally
tracks win rate + Wilson CI at each available cumulative OOS horizon (25/50/100/150) and
classifies the trend `STABLE` / `DECAYING` / `FAILED` by comparing the latest available horizon's
CI against the first horizon's CI (non-overlap in the negative direction = `DECAYING`; latest
upper bound below 50% = `FAILED`; otherwise `STABLE`) — using CI overlap rather than raw
point-estimate drift, per Sec 21's explicit instruction not to over-react to normal fluctuation.

`EXPIRED_LOW_TARGET_SHARE` (Sec 22) overrides `DETECTED` / `OOS_PENDING` / `OOS_CONFIRMED` status
whenever the target's **current** (end-of-dataset) rolling-14d share has fallen below the MEDIUM
threshold (5%) — tracked separately from `OOS_FAILED`, since a counter can still statistically
work against a target that has simply left the meta.

## 7. Positive Controls

Both given positive controls entered the 42-pair candidate universe automatically (no
special-casing in code — they are two of the 21 named-archetype pairs with >=20 full-dataset
games) and both reached `DETECTED`:

- **`Teal Mask Ogerpon ex -> Marnie's Grimmsnarl ex`**: candidate 2026-08-04→ detected 2026-08-09
  at n=60, 81.67% (wilson_lo 70.08%) — closely reproduces the prompt's cited 81.8%/n=77
  full-dataset figure. Only 17 OOS games remained by 2026-08-10 (`ALL_AVAILABLE`: 82.35% win
  rate) — below the n=25 primary bar, so status is `OOS_PENDING`, not yet `OOS_CONFIRMED`, purely
  because the dataset ends 1 day after detection. This is an honest data-budget limit, not a
  detection failure (see Sec 15-16).
- **`Team Rocket's Mewtwo ex -> Fezandipiti ex`**: candidate 2026-07-21 → detected 2026-07-22 at
  n=59, 72.88% (wilson_lo 60.40%), closely reproducing the prompt's cited 76.5%/n=85 full-dataset
  figure. OOS at n=25: **84.0% win rate, Wilson lower bound 65.35%** → **`OOS_CONFIRMED`**, the
  model's single fully validated counter.

## 8. Negative Controls

**`Mega Kangaskhan ex -> Marnie's Grimmsnarl ex`** went through the identical, unmodified
pipeline: candidate 2026-07-17 → detected 2026-07-18 at n=51, 72.55% (wilson_lo 59.05%) —
reproduces the prompt's cited 74.0% historical figure closely. OOS at n=25: **52.0% win rate,
Wilson lower bound 33.50%** → **`OOS_FAILED`** (`DID_NOT_CLEAR_PRIMARY_BAR`). Extending to n=100
OOS games (available in `counter_oos_validation.csv`) shows 48.0%, and `ALL_AVAILABLE` (n=160,
matching the prompt's cited 48.75%) shows 49.06% — the same collapse the prompt describes. **The
gate detects it exactly as strongly as the real positive controls at detection time, and OOS
confirmation is what correctly separates it from them** — precisely the discriminating behavior
this phase set out to test.

## 9. Detected Counters

Of the 42 candidate-universe pairs, **5 reached `CANDIDATE`, and all 5 of those reached
`DETECTED`** (100% candidate→detected conversion in this dataset — expected, since cumulative
full-history statistics rarely reverse sharply day-to-day once an n=50 base has been reached):

| Counter -> Target | Detected | Hist. n | Hist. WR | Wilson lo | OOS status |
|---|---|---|---|---|---|
| Dragapult ex -> Fezandipiti ex | 2026-08-05 | 61 | 65.57% | 53.05% | OOS_PENDING (n=15) |
| Team Rocket's Mewtwo ex -> Fezandipiti ex | 2026-07-22 | 59 | 72.88% | 60.40% | **OOS_CONFIRMED** |
| Mega Kangaskhan ex -> Marnie's Grimmsnarl ex | 2026-07-18 | 51 | 72.55% | 59.05% | OOS_FAILED |
| Teal Mask Ogerpon ex -> Marnie's Grimmsnarl ex | 2026-08-09 | 60 | 81.67% | 70.08% | OOS_PENDING (n=17) |
| Marnie's Grimmsnarl ex -> Team Rocket's Mewtwo ex | 2026-07-25 | 61 | 72.13% | 59.83% | OOS_FAILED |

The 5th pair, **`Marnie's Grimmsnarl ex -> Team Rocket's Mewtwo ex`**, is a genuinely new finding
(not named anywhere in the phase prompt): it was detected early at an inflated 72.13% win rate,
then **collapsed to 44.0% OOS** (n=25, `COLLAPSED_BELOW_50PCT`) — its full-dataset final win rate
(59.7%, from `archetype_matchups.csv`) is *below* the 60% primary effect threshold, showing the
early-detection win rate was itself a small-sample overestimate that regressed toward a coin
flip. This is a second, independently-discovered false positive beyond the prompt's own Kangaskhan
example, and further evidence the OOS gate is doing real discriminating work, not just passing
everything through.

## 10. OOS Results

Full per-horizon detail in `results/meta/counter_oos_validation.csv`. Summary at the primary
25-game horizon:

| Counter -> Target | OOS n | OOS WR | OOS Wilson lo | Verdict |
|---|---|---|---|---|
| Mewtwo ex -> Fezandipiti ex | 25 | 84.0% | 65.35% | CONFIRMED |
| Kangaskhan ex -> Grimmsnarl ex | 25 | 52.0% | 33.50% | FAILED |
| Grimmsnarl ex -> Mewtwo ex | 25 | 44.0% | 26.67% | FAILED |
| Ogerpon ex -> Grimmsnarl ex | 17 (< 25) | 82.35%* | 58.97%* | PENDING |
| Dragapult ex -> Fezandipiti ex | 15 (< 25) | 60.0%* | 35.75%* | PENDING |

(*ALL_AVAILABLE figures, reported for transparency only — not the basis of the PENDING
classification, which is driven purely by insufficient sample.)

## 11. False Positives

From `results/meta/counter_false_positive_analysis.csv`:

- Total candidates: 5. Total detected: 5. OOS confirmed: 1. OOS failed: 2. OOS pending: 2.
  Expired (low target share): 0.
- Of the **3 counters with a definitive OOS verdict** (pending excluded, per Sec 28):
  **confirmation rate 33.3% (1/3), false-positive rate 66.7% (2/3).**
- **[HYPOTHESIS]** This false-positive rate looks high, but n=3 evaluated counters is far too
  small to treat as a stable estimate of the gate's true precision — it should be read as "of the
  handful of counters this dataset's short remaining window let us actually confirm or refute,
  2 of 3 failed," not as a general statement about the detection gate's reliability.

## 12. Counter Expiration

**0 counters** reached `EXPIRED_LOW_TARGET_SHARE` in this run. `Marnie's Grimmsnarl ex` (the
Ogerpon target) is still `HIGH` current relevance (43.47%); `Fezandipiti ex` (the Mewtwo target)
is `MEDIUM` (14.87%, just under the 15% HIGH cutoff — a genuine recency effect, not a rounding
artifact: its share over the whole RECENT period was 16.8%, but the last 14 days specifically run
slightly lower). No lifecycle decay could be computed for the one `OOS_CONFIRMED` counter
(Mewtwo -> Fezandipiti) beyond the 25-game horizon — only 26 total OOS games exist by dataset end
(22 wins, 84.6%), just short of the 50-game second lifecycle horizon — so `counter_lifecycle.csv`
correctly reports `INSUFFICIENT_HORIZONS_FOR_TREND` rather than guessing.

## 13. Current Validated Counter Registry

`results/meta/current_validated_counters.csv` — counters with status `OOS_CONFIRMED` **right
now**:

| Counter | Target | Hist. WR | OOS WR | Confidence | Target share | Counter share | Last confirmed |
|---|---|---|---|---|---|---|---|
| Team Rocket's Mewtwo ex | Fezandipiti ex | 72.88% | 84.0% | USABLE (n=25) | 14.87% | 2.94% | 2026-08-09 |

**Exactly one row.** `Marnie's Grimmsnarl ex` — the meta's dominant deck at 43.47% current share
— currently has **zero** `OOS_CONFIRMED` counters under this stricter model, even though
`Ogerpon -> Grimmsnarl` is a real, detected, historically strong relationship: it simply hasn't
had enough post-detection games yet to clear the OOS bar. This is the single most important
practical finding of this phase (see Sec 17, Q9).

## 14. Current Meta Coverage

From `results/meta/counter_coverage.csv` (9 archetypes with current 14-day share > 0):

| Target | Current share | Tier | Validated counters |
|---|---|---|---|
| Marnie's Grimmsnarl ex | 43.47% | HIGH | 0 |
| Fezandipiti ex | 14.87% | MEDIUM | **1** |
| Mega Kangaskhan ex | 9.51% | MEDIUM | 0 |
| Mega Lopunny ex | 9.43% | MEDIUM | 0 |
| Teal Mask Ogerpon ex | 7.17% | MEDIUM | 0 |
| Dragapult ex | 5.13% | MEDIUM | 0 |
| Team Rocket's Mewtwo ex | 2.94% | LOW | 0 |
| Cynthia's Garchomp ex | 2.75% | LOW | 0 |
| Mega Lucario ex | 2.23% | LOW | 0 |

**Coverage with >=1 validated counter: 11.1% (1/9). Coverage with >=2: 0.0%.**

## 15. Statistical Uncertainty

Every win-rate estimate in this phase (historical-at-detection, current, and OOS) is reported
with its Wilson 95% score-interval lower bound alongside the raw point estimate and sample size —
never a bare percentage. Because the historical and OOS samples for a given counter never
overlap in time (OOS games are, by construction, all strictly after `detection_date`), a naive
two-proportion significance test comparing them would be valid in principle, but was not needed
here: the primary decision rule already conditions on the OOS Wilson interval directly rather
than a historical-vs-OOS comparison, which is more conservative and avoids any temptation to
read too much into a shift between two estimates of different, non-comparable samples. Lifecycle
trend classification (Sec 6 / Sec 21) uses CI-overlap comparison for the same reason.

## 16. Limitations

- **[FACT]** The dataset's 56-day span is the binding constraint on this whole phase: matchup
  pairs need n>=50 full-history games before they can even become candidates, which by
  construction happens well into the season for any given pair, leaving only a short remaining
  window for OOS confirmation. 2 of the 5 detected counters (including one positive control,
  Ogerpon -> Grimmsnarl) are stuck at `OOS_PENDING` for exactly this reason, not because the
  signal looks weak.
- **[FACT]** Only 3 counters ever reached a definitive OOS verdict. Any confirmation-rate /
  false-positive-rate figure computed from n=3 is illustrative, not a reliable estimate of the
  gate's long-run precision.
- **[HYPOTHESIS]** The `n=25`-primary-horizon choice, while declared before viewing results,
  trades statistical power for coverage (more counters reach a verdict, but each verdict is
  noisier than at n=50+). A future phase with a longer post-detection dataset window should
  re-run this exact pipeline with the stricter n=50/100 horizons as primary.
- **[FACT]** The rating-resolution problem flagged in Phase 4.1/4.2 (per-side skill rating cannot
  be reliably resolved from this data source) still applies — none of this phase's win rates are
  rating-adjusted, consistent with every prior phase.
- **[FACT]** Only 11 named archetypes / 42 directed candidate pairs were evaluated; the
  `UNLABELED_CLUSTER_*` buckets (13.8% of games, per Phase 4.1) are excluded by design (see
  Sec 2) and could in principle hide additional real counters, but recommending a non-nameable
  cluster as a "counter deck" would not be actionable.

## 17. Implications for Deck Selection

The registry currently supports exactly **one** narrow, high-confidence recommendation: pilot
`Team Rocket's Mewtwo ex` specifically against `Fezandipiti ex`. It does **not** support a
general counter-based deck-selection policy, and critically **does not yet license "play Ogerpon
against Grimmsnarl" as a fully OOS-validated claim** under this phase's own stricter bar — that
relationship remains real and well-supported (Phase 4.3b already found it walk-forward-validated
under a looser 1-day-persistence rule with no relevance gate), but under Phase 4.4's tighter,
explicitly pre-registered criteria it is honestly `OOS_PENDING`, not `OOS_CONFIRMED`, purely
because the dataset ends too soon after its (correctly late) detection date. Any deck-selection
logic consuming this registry should treat `current_validated_counters.csv` as the sole source
of actionable rows, and should re-evaluate as soon as more post-2026-08-10 data exists.

## 18. Recommendation for Next Phase

See Sec "Final Recommendation" below.

---

## Critical Validation Questions (Sec 33)

**Q1 — Does the detection gate reproduce Ogerpon -> Grimmsnarl and Mewtwo -> Fezandipiti without
hard-coding them?** Yes. Both entered the 42-pair candidate universe purely from the
>=20-full-dataset-games filter (no archetype names are special-cased anywhere in
`tools/build_validated_counter_model_v1.py`), and both independently reached `DETECTED` with
historical win rates (81.67%/72.88%) and sample sizes (60/59) closely matching the prompt's
cited figures (81.8%/76.5%, n=77/85).

**Q2 — Does the same gate correctly identify or reject Kangaskhan -> Grimmsnarl as unstable?**
Yes. It is detected identically to the real positive controls (72.55%, n=51, wilson_lo 59.05% —
comparable strength to Mewtwo's 72.88%/n=59) but fails OOS decisively (52.0% at n=25, wilson_lo
33.50%; 49.06% at all 160 available future games, matching the prompt's cited 48.75%). The
detection gate alone cannot tell it apart from a real counter — **only OOS confirmation can**,
which is exactly the discriminating mechanism this phase was built to test.

**Q3 — What percentage of detected counters survive OOS validation?** 1 of 5 detected (20%); 1
of 3 with a definitive verdict (33.3%) — see Sec 11's caveat about the small evaluated-n.

**Q4 — What is the false-positive rate?** 66.7% of evaluated (definitively-verdicted) counters
(2/3) — again, n=3 is too small for this to be a stable estimate; it should be read as "2 known
false positives out of 3 counters this dataset could fully adjudicate," not a general precision
figure.

**Q5 — How many current-meta targets have at least one validated counter?** 1 of 9 (11.1%) —
`Fezandipiti ex`, via `Team Rocket's Mewtwo ex`.

**Q6 — How many have multiple validated counters?** 0 of 9 (0.0%).

**Q7 — How long do validated counters remain useful?** Cannot be answered with confidence yet —
the one `OOS_CONFIRMED` counter (Mewtwo -> Fezandipiti) has only 26 total OOS games by dataset
end, clearing just the first Sec 21 lifecycle block (25 games) but not the second (50), so
`counter_lifecycle.csv` reports `INSUFFICIENT_HORIZONS_FOR_TREND` rather than a stable/decaying/
failed call. **[OPEN QUESTION]** for the next data pull.

**Q8 — How often do counters fail despite passing the historical detection gate?** 2 of 5
detected counters (40%) failed OOS outright; a further 2 (40%) are still pending. Only 1 of 5
(20%) is confirmed. Passing the historical detection gate is evidently a necessary but far from
sufficient condition for a counter to be real.

**Q9 — Is the model conservative enough to prefer no recommendation over a weak signal?** Yes,
markedly so: the current registry recommends a counter for only 1 of 9 live archetypes, and
explicitly withholds a recommendation for the meta's #1 deck (`Marnie's Grimmsnarl ex`, 43.47%
share) despite a strong, independently-reproduced historical signal (Ogerpon), because that
signal hasn't cleared OOS confirmation yet. This is precision-over-recall (Sec 29) working as
designed, not a bug.

**Q10 — Is the resulting counter registry sufficiently reliable to be consumed by a future
deck-selection system?** Partially. The single `OOS_CONFIRMED` row (Mewtwo -> Fezandipiti) is
reliable enough to act on narrowly. The registry as a whole is not yet broad enough (11.1%
coverage) to drive a general counter-aware selection policy, and 2 of the 5 detected counters
remain genuinely undetermined (`OOS_PENDING`) purely due to the dataset's short remaining window
— they should be re-evaluated the moment more post-2026-08-10 data is available, rather than
either promoted or discarded now.

---

## Final Recommendation

**COUNTER MODEL PARTIALLY VALIDATED.**

Reasoning: the pipeline demonstrably does what it was built to do — it reproduces both known
positive controls without hard-coding, and it reproduces (and OOS-rejects) the known negative
control using the exact same mechanism, plus independently discovers a second false positive
(Grimmsnarl -> Mewtwo) the prompt never named. That is real, working discrimination. But the
dataset's short remaining post-detection window means only 3 of 5 detected counters could reach
a definitive OOS verdict at all, and only 1 survived — too thin a base to call the model fully
validated, and too clearly functional (on the controls it was specifically built to check) to
call it unreliable.

**Recommended next step: PROCEED TO COUNTER-AWARE DECK SELECTION — scoped narrowly to the single
`OOS_CONFIRMED` row** (`Team Rocket's Mewtwo ex` as an explicit counter-pick when the opponent is
known/likely to be `Fezandipiti ex`), **not** a general counter-based policy. In parallel,
re-run this exact pipeline (unchanged thresholds) once more post-2026-08-10 episode data becomes
available, specifically to resolve the two `OOS_PENDING` counters (Ogerpon -> Grimmsnarl,
Dragapult -> Fezandipiti) one way or the other — both are one or two more days of games away from
a definitive answer, not a new experiment. Do **not** move to a general opponent-aware agent,
game-state modeling, or any RL/MCTS/search work — nothing in this phase's evidence changes the
Phase 4.3b conclusion that a general opponent model is unsupported; if anything, this phase's
11.1% coverage figure sharpens the case for staying narrow.
