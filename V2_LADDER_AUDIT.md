# V2 Balanced — Real Kaggle Ladder Behavioral Audit

**Date**: 2026-08-13. **Scope**: data validation, not strategy redesign. Get V2 Balanced's real
Kaggle ladder behavioral profile using the **identical methodology** already applied to Luca,
so the two can honestly be compared on real-vs-real data instead of real-vs-local-simulation.
**No agent/deck/policy/submission changes were made. No V6 is proposed. No weights were
changed.** This is a checkpoint for review.

Every claim is tagged **[FACT]**, **[HYPOTHESIS]**, or **[GAP]**, per this project's standing
process rule. Confidence levels (HIGH/MEDIUM/LOW) are given per metric in §12.

---

## 0. Methodological correction driving this report

The first Luca audit (`LUCA_AUDIT.md`) compared Luca's real ladder games against V2's **150
local simulation games vs V1_baseline only** — not real ladder data for V2. That comparison is
methodologically unsound for a "why is Luca stronger" question. This report fixes that by
pulling V2's own real Kaggle ladder games and re-running Luca's games through the **same code
path** (`src/meta_analysis/ladder_behavior_audit.py`, one shared module, both agents parsed by
it — not two separate implementations), extended with the additional metrics this task
requested (card-level action classification, retreat sub-categories, prize-denial case
analysis) that the first pass didn't compute. Where the first Luca audit already reported a
number using an equivalent definition, the two are consistent (cross-checked in §12); this
report's numbers supersede the first audit's V2-side numbers, not Luca's.

---

## 1. Finding V2's real ladder games

**[FACT]** Two Kaggle submissions exist for V2 Balanced's identical build (same
`fileName=challenger_v2_20260812T053030Z.tar.gz`, same `totalBytes=2028569` — a byte-identical
artifact resubmitted 3 minutes apart on 2026-08-12):

| Submission ID | Submitted (UTC) | Public score | Real ladder games |
|---|---|---|---|
| 55449821 | 05:31:13 | 600.0 (never moved) | **0** (only the self-play validation episode — evidently superseded before matchmaking ever paired it) |
| **55449878** | 05:34:31 | 699.8 | **43** real `EPISODE_TYPE_PUBLIC` games (+1 validation) |

This report analyzes **55449878 only** — not a judgment call between two different versions
(they're the same code), simply "use the one that has data." Verified directly via
`competition_list_episodes()` before committing to it, not assumed.

**[FACT]** Date range of V2's 43 real games: **2026-08-12T05:35Z to 2026-08-12T23:35Z** (~18
hours). 43 unique opponents (no repeats), current ratings pulled for all 43 via
`competition_team_submissions(team_id)` (mean 617.8, median 623.6 — **far lower** than Luca's
opponent pool, see §9). All 43 games are `status=DONE`/complete, 0 errors, 0 timeouts, 0 draws.

---

## 2. Same methodology as Luca — what's identical and what isn't

**[FACT]** Both agents were parsed by the exact same function
(`ladder_behavior_audit.parse_episode`), same categorization tables, same missed-knockout
detector (verbatim from the session-17/session-19 lineage), same prize-value formula (reused
**exactly** from `src/agents/dragapult_policy_v2plus.py::prize_count()` — not reinvented for
this report). Every metric in §3/§4 below uses one definition applied identically to both.

**[GAP, stated once here rather than repeated everywhere]**: two NEW estimators were built for
this report (they didn't exist in the first Luca audit, so there's no earlier definition to
preserve) and are used **identically for both agents**, but are approximations:
- `opp_lethal_now`: opponent's active Pokémon has enough attached energy (by count and type,
  via the engine's own `CardData`/`Attack` tables) to use an attack whose base damage ≥ our
  active's current HP. Ignores weakness (would only make it *more* lethal, so this is
  conservative in one direction) and ignores Rainbow/Team-Rocket special energies providing
  extra type flexibility (so it can under-count in the other direction). Documented in the
  module, not silently assumed accurate.
- `bench_ready_attackers`: how many bench Pokémon already have a payable attack, same
  approximation.

Both are applied identically to Luca and V2, so the *comparison* between them is fair even
though neither absolute number should be over-trusted.

---

## 3. Game-level metrics

| Metric | Luca (n=69) | V2 (n=43) |
|---|---|---|
| Games | 69 | 43 |
| Wins / Losses | 51 / 18 | 27 / 16 |
| Win rate | 73.9% (Wilson CI [62.5%, 82.8%]) | 62.8% (CI [47.9%, 75.6%]) |
| Avg game length (turns) | 10.77 | 12.51 |
| Median game length (turns) | 10 | 12 |
| First-player games | 35 | **31** |
| Second-player games | 34 | **12** |
| Win rate first | 74.3% (CI [57.9%, 85.8%]) | 61.3% (CI [43.8%, 76.3%]) |
| Win rate second | 73.5% (CI [56.9%, 85.4%]) | 66.7% (CI [39.1%, 86.2%]) |
| Comeback rate (won after 2+ deficit) | 35.7% (5/14) | 42.1% (8/19) |
| Games with 2+ prize deficit | 20.3% (14/69) | **44.2%** (19/43) |
| Avg peak deficit faced | 0.70 prizes | 1.51 prizes |
| Final margin, wins (+ = behind) | -1.82 | -1.30 |
| Final margin, losses (+ = behind) | 1.61 | 1.75 |

**[FACT, HIGH confidence]** V2's real-ladder first/second split is heavily lopsided (31 vs 12)
— unlike the local V1-vs-V2 dataset (75/75 by design) or Luca's real split (35/34). This is
itself data (V2's own `IS_FIRST` answer plus real opponents' answers plus matchmaking), not a
sampling artifact to correct for, but it means the "second" cell (n=12) is thin.

**[HYPOTHESIS]** The first Luca audit's local-vs-local comparison suggested a large V2
first/second gap (49.3% vs 65.3%, 16pp, n=75/75). **Real ladder data shows the same direction
but a much smaller, not-statistically-separated gap** (61.3% vs 66.7%, 5.4pp, CIs overlap
heavily, n=31/12). This does not confirm the local-simulation gap was wrong — different
opponent pool, tiny n=12 on the "second" side — but it means the local 16pp figure should not
be quoted as V2's real-ladder first/second weakness. Directionally consistent, magnitude
unconfirmed.

**[FACT, MEDIUM confidence]** V2 hits a 2+ prize deficit in 44.2% of its real games vs Luca's
20.3% — the largest, cleanest game-level gap found. Confounded by different opponent pools
(§9) and deck mechanics (§9), not attributable to policy alone from this alone.

---

## 4. Action-level metrics

| Metric | Luca | V2 |
|---|---|---|
| Attack rate (per turn, when legally available) | 81.2% | 70.3% |
| Retreat rate (per decision) | 1.02% | 1.81% |
| Retreat rate (when retreat legal that decision) | 5.64% | 4.98% |
| Energy attachment (per game) | 4.90 | 5.30 |
| Bench development / PLAY_POKEMON (per game) | 5.64 | 3.70 |
| Evolution (per game) | 2.91 | 4.42 |
| Item usage (per game) | 9.41 | 8.88 |
| Supporter usage (per game) | 3.67 | 5.07 |
| Stadium usage (per game) | 0 (deck runs none, see §9) | 0.77 |
| Ability usage (per game) | 4.00 | 7.30 |
| KO attempts (attacks thrown) | 255 total (3.70/game) | 151 total (3.51/game) |
| **KO success rate per attack** | **87.8%** (CI [83.3%, 91.3%]) | **68.9%** (CI [61.1%, 75.7%]) |
| Missed confirmed KOs | 0 / 69 games | **8 raw flags / 2 distinct turns**, 43 games (see note) |

**[FACT, HIGH confidence]** V2's attacks actually land as a knockout **68.9%** of the time vs
Luca's **87.8%** — CIs do not overlap (61.1–75.7% vs 83.3–91.3%). This is the single most
statistically credible action-level gap found in this report. **[GAP → see §9]**: this is very
likely a deck/mechanics effect, not (or not only) a policy effect — see the Dragapult ex vs
Mega Lucario ex attack-design comparison below.

**[FACT]** V2's 8 raw "confirmed missed knockout" flags collapse to **2 distinct in-game
situations** (episodes 92230119 and 92239608, both turn 8) — the detector emits one flag per
MAIN-menu revisit within a turn, and both situations were revisited 3-5 times before the turn
ended, all for the same standing opportunity (`Jet Headbutt`, Dragapult ex's cheap attack).
Reporting the raw count without this note would overstate the finding; 2 real missed
opportunities across 43 games, vs 0 across Luca's 69, is the honest comparison.

### Retreat sub-categories (never mixed, per instruction)

| # | Category | Luca count | Luca rate | V2 count | V2 rate |
|---|---|---:|---:|---:|---:|
| 1 | All retreats | 48 | 1.02%/decision | 74 | 1.81%/decision |
| 2 | Retreat when legally available | 48 / 851 legal | 5.64% | 74 / 1486 legal | 4.98% |
| 3 | Retreat of a 2+-prize Pokémon | 20 / 2555 such decisions | 0.78% | 21 / 2305 | 0.91% |
| 4 | Retreat of a damaged Pokémon | 30 / 1597 | 1.88% | 20 / 1237 | 1.62% |
| 5 | Retreat when opponent lethal *now* | 16 / 566 | 2.83% | 11 / 498 | 2.21% |
| 5b | …lethal now OR one energy away | 18 | — | 20 | — |
| 6 | Retreat when a bench target exists | 48 / 4293 | 1.12% | 74 / 3768 | 1.96% |

**[FACT, MEDIUM confidence]** Across every single-condition retreat rate, Luca and V2 are
**close and inconsistent in direction** (Luca higher on #4/#5, V2 higher on #1/#2's raw
count/#3/#6) — no single-condition retreat category shows a large, one-directional gap. The
gap only appears once all five conditions are required **simultaneously** — see §5.

---

## 5. Prize-denial hypothesis test (Gemini's claim) — Cases A–E

Defining a decision as satisfying Case A–E **all at once** (2+-prize active, damaged, opponent
lethal *now*, retreat legal, viable bench target exists) = a **critical situation**:

| | Luca | V2 |
|---|---:|---:|
| Marginal: A (2+-prize active) | 2555 decisions | 2305 |
| Marginal: B (damaged) | 1597 | 1237 |
| Marginal: C (opp lethal now) | 566 | 498 |
| Marginal: D (retreat legal) | 851 | 1486 |
| Marginal: E (bench target exists) | 4293 | 3768 |
| **Critical situations (A∧B∧C∧D∧E)** | **136** | **90** |
| Retreated in critical situations | 11 (8.1%, CI [4.6%,13.9%]) | 3 (3.3%, CI [1.1%,9.3%]) |
| Stayed in critical situations | 125 | 87 |
| Of "stayed": confirmed KO'd on next decision | **1** | **0** |
| Of "stayed": survived to next decision | 120 | 87 |
| Of "stayed": game ended at that exact decision | 4 | 0 |

**[FACT, MEDIUM confidence]** Luca retreats in critical situations at roughly **2.4× V2's
rate** (8.1% vs 3.3%) — the CIs overlap (4.6–13.9% vs 1.1–9.3%) so this is not fully
statistically separated at this n, but it's the cleanest directional signal for "Luca retreats
more when danger signals stack up" found in this audit.

**[FACT, HIGH confidence — and the single most important number in this report]**: staying in
a "critical situation" almost **never** actually results in a confirmed knockout on the very
next observed decision, **for either agent**: 1/125 for Luca (0.8%), 0/87 for V2 (0%). This
directly bears on the hypothesis test in §14.

---

## 6. Counterfactual analysis

Per instruction: only assessed for the "stayed → confirmed KO'd" subset, and marked
**COUNTERFACTUAL NOT IDENTIFIABLE FROM AVAILABLE DATA** where it can't be estimated.

**V2**: `n_confirmed_ko_after_staying = 0`. **COUNTERFACTUAL NOT IDENTIFIABLE — there is no
case in this dataset where V2 stayed in a critical situation and was then confirmed knocked
out on its very next decision.** Whatever is costing V2 games (§7 shows V2 does lose 16/43
real games), it is not, on this data, "stayed active in an A∧B∧C∧D∧E critical situation and
got immediately punished for it."

**Luca**: exactly 1 qualifying case (episode logged in
`results/ladder_behavior_audit/luca_stayed_critical_outcomes.csv`). Factors:
retreat cost 2.0 (Mega Lucario ex's actual retreat cost), energy loss if retreated would have
been 2.0 (all attached energy), 1 ready bench attacker existed, opponent's best available
attack was 200 damage. Game result: LOSS. **With n=1, no rate or general conclusion can be
drawn** — this is a single anecdote, reported because it exists, not because it's
representative. **[HYPOTHESIS, not stated as fact]**: in this one case a bench attacker was
ready, so retreating was *structurally possible* without giving up tempo entirely — but one
case cannot support "retreat would have improved EV in general."

**Overall verdict for this section**: **COUNTERFACTUAL NOT IDENTIFIABLE FROM AVAILABLE DATA**
at any general/aggregate level for either agent — n=1 and n=0 are both too small to estimate
whether retreating "actually improves EV or only looks good retrospectively." This null result
is itself an answer to the question this section was designed to test, not a failure to find
one.

---

## 7. Loss analysis (V2's 16 real losses only)

| Pattern | Count / 16 |
|---|---:|
| Losses going first | 12 (75%) |
| Losses going second | 4 (25%) |
| Losses with a 2+ prize deficit at some point | 11 (69%) |
| Losses where retreat was legal in the final 3 own decisions | 3 (19%) |
| Losses where a bench target existed in the final 3 own decisions | 14 (88%) |
| Losses that lost a 2+-prize attacker at some point in the game | 11 (69%) |
| Losses with ≥1 missed-KO flag anywhere in the game | 5 (31%) |
| Avg final prize margin (+ = behind) | 1.75 |
| Avg energy-attach rate per turn | 0.42 |

**[FACT]** 12 of V2's 16 real losses (75%) happened while going first — directionally
consistent with §3's first/second gap, though (as in §3) this is descriptive, not causal:
V2 also played first far more often overall (31/43 games), so a naive base rate alone would
predict most losses come from the first-player games too. A fair comparison needs the *rate*,
already given in §3 (61.3% first WR vs 66.7% second WR) — the loss table adds no new evidence
beyond what §3 already shows, it's the same fact from the other side.

**[FACT]** Only 3/16 losses (19%) had retreat legally available in the final 3 own decisions —
i.e. in most of V2's losses, by the time the game was clearly ending, retreating **was not
even an option any more** (no bench, retreat cost unpayable, etc.), while a bench target
existed in 14/16 (88%) — meaning the bottleneck in most late-game-loss positions was
specifically retreat legality (likely: retreat cost unpaid because energy was already
committed elsewhere, or the active had already retreated that turn), not bench availability.

**[GAP]**: `last3_own_decisions_action_classes` frequently shows `?` (non-MAIN sub-selection
decisions like discard/damage-counter-placement, common in a game's final few decisions after
the decisive exchange already happened) — meaning "final 3 decisions" often captures
end-of-game cleanup, not the actual tactical moment. Raw per-loss detail preserved in
`results/ladder_behavior_audit/v2_loss_analysis.csv` for anyone who wants to inspect further;
not fully resolved here.

---

## 8. Correlation vs. causation — explicitly checking alternatives

The naive story ("V2 loses because it doesn't retreat enough") predicts: V2's losses should be
full of situations where retreat was legal, a good bench target existed, and V2 stayed anyway
and got punished. **§5/§6/§7 argue against this specific story**, on this data:

- Of V2's 90 true "critical situations" (all 5 danger signals present), **0 led to a confirmed
  immediate KO after staying** — the mechanism the hypothesis describes essentially never fires
  in this dataset.
- In V2's actual losses, retreat was legal in the closing decisions only 19% of the time — the
  more common pattern is retreat **not being a live option** late in a losing game, which is
  consistent with alternatives the instructions explicitly asked to check: retreat cost already
  too high / energy already committed, or the game was effectively decided several turns
  earlier (§7's prize-margin data: average losing final margin is 1.75 prizes behind, and
  §3 shows 44% of games hit a 2+ deficit at some point — the deficit is usually build up over
  multiple turns, not a single stay-vs-retreat decision).
- The one confirmed "stayed → KO'd" event found (Luca, §6) had a ready bench attacker, which
  argues *for* the hypothesis in that single instance — but n=1 cannot generalize.

**[HYPOTHESIS, not proven]**: if V2 loses more than Luca (37.2% vs 26.1% real decisive loss
rate), the more data-supported explanation on this pass is a mix of (a) a much tougher/more
volatile opponent pool at V2's own rating band (§9), (b) deck mechanics (Dragapult ex's KO
profile, §9), and (c) tempo lost gradually over many turns (44% of games reach a 2+ deficit)
rather than one identifiable retreat/no-retreat decision point. This directly contradicts
treating "insufficient defensive retreat" as *the* cause.

---

## 9. Deck/mechanics confounding — kept separate from policy, as instructed

| | Luca — Mega Lucario ex | V2 — Dragapult ex |
|---|---|---|
| Retreat cost | **2** energy | **1** energy (cheaper) |
| Prize value if KO'd | **3** (ex + Mega) | **2** (ex) |
| HP | 340 | 320 |
| Evolution line | Stage-1-equivalent Mega Evolution, direct from Riolu (1 step) | **Stage 2** — Dreepy→Drakloak→Dragapult ex (2 steps, slower to power up) |
| Signature/cheap attack | Aura Jab, 130 dmg, cost 1 Fighting energy | Jet Headbutt, 70 dmg, cost 1 colorless energy |
| Big attack | Mega Brave, **270 dmg, hits the active directly**, cost 2 Fighting energy | Phantom Dive, 200 dmg, but its text places damage **on the opponent's Bench**, not the active Pokémon |

**[FACT]** This is a **DECK/MECHANICS** finding, not a POLICY finding: Dragapult ex's own
highest-damage attack does not hit the opposing active Pokémon at all. This alone plausibly
explains a meaningful share of §4's KO-success-rate gap (68.9% vs 87.8%) — V2's deck is
structurally less equipped to land direct-lethal hits with its strongest attack, independent of
how good V2's targeting/timing logic is. **[HYPOTHESIS]**: the exact split between "deck can't"
and "policy chooses suboptimally" cannot be separated further with this data — would need V2's
policy piloting a different deck, or a different policy piloting Dragapult ex, neither of which
exists yet.

**[FACT]** Dragapult ex is cheaper to retreat (1 energy vs 2) and worth fewer prizes if lost (2
vs 3) — if anything, this should make retreating **easier and lower-stakes** for V2 than for
Luca, the opposite direction of "V2 doesn't retreat enough because retreating is too costly for
this deck."

**[FACT]** Dragapult ex is a slower-developing Stage 2 line (2 evolutions) vs Mega Lucario ex's
1-step line — independently explains part of V2's longer average game length (12.51 vs 10.77
turns, §3) without invoking any policy difference.

**[FACT, critical for interpreting every table above]**: V2's 43 real opponents currently
average rating **~618** (median 624); Luca's 69 real opponents currently average **~977**
(median 1003). **V2 and Luca are not competing in the same part of the ladder.** Any raw
win-rate or behavioral-rate gap between them is confounded by opponent strength as much as by
deck or policy — this is the largest single confound in the whole report and is why §14 does
not draw a "why Luca is stronger" conclusion.

---

## 10. V2 summary table

| Metric | V2 | Definition |
|---|---:|---|
| Games | 43 | Real `EPISODE_TYPE_PUBLIC` episodes, submission 55449878, validation episode excluded |
| Win rate | 62.8% | wins / (wins+losses) |
| First-player WR | 61.3% (n=31) | win rate when `firstPlayer == our_index` |
| Second-player WR | 66.7% (n=12) | win rate when opponent asked "go first" |
| Avg game length | 12.51 turns | mean of `n_turns` across all games |
| 2+ prize deficit | 44.2% of games | share of games where `our_remaining − opp_remaining ≥ 2` at any decision |
| Retreat rate | 1.81% of decisions | RETREAT chosen / all own decisions |
| Retreat when available | 4.98% | RETREAT chosen / decisions where RETREAT was a legal option |
| 2-prize retreat | 21 events, 0.91% of such decisions | RETREAT chosen while own active is ex/Mega-ex |
| Damaged-Pokémon retreat | 20 events, 1.62% of such decisions | RETREAT chosen while own active HP < max HP |
| Attack rate | 70.3% of turns with a legal attack | turns where an attack was chosen, of turns where ≥1 was legally available |
| Missed KO (confirmed) | 8 raw flags / 2 distinct turns | non-resisted, ability-free, standard lethal attack available, not taken, unresolved same turn |
| Comeback rate | 42.1% (8/19) | won after facing a 2+ prize deficit, of games that faced one |

---

## 11. Luca vs. V2 — factual comparison only (no "why" conclusion yet)

| Metric | Luca | V2 | Difference | Confidence |
|---|---:|---:|---:|---|
| Win rate | 73.9% | 62.8% | +11.1pp (Luca) | LOW — CIs overlap [62.5,82.8] vs [47.9,75.6]; different opponent pools (§9) |
| 2+ prize deficit | 20.3% | 44.2% | +23.9pp (V2 worse) | MEDIUM — large gap, but opponent-pool/deck confounded |
| Retreat (per decision) | 1.02% | 1.81% | V2 retreats *more* overall | LOW — opposite direction from the naive hypothesis |
| Retreat when available | 5.64% | 4.98% | roughly equal | LOW — small gap, likely noise |
| 2-prize retreat rate | 0.78% | 0.91% | roughly equal | LOW |
| Retreat in critical situations (A∧B∧C∧D∧E) | 8.1% | 3.3% | +4.8pp (Luca) | MEDIUM — CIs overlap, but consistent direction and the most relevant cut for the hypothesis |
| Attack rate (per turn) | 81.2% | 70.3% | +10.9pp (Luca) | MEDIUM |
| KO success per attack | 87.8% | 68.9% | +18.9pp (Luca) | **HIGH — CIs do not overlap**, but plausibly deck-mechanics-driven (§9), not purely policy |
| Comeback rate | 35.7% | 42.1% | roughly equal, V2 slightly higher | LOW — small n both sides |

---

## 12. Data quality & confidence

### DATASET
- Luca: 69 complete real games (+1 validation, excluded), 0 incomplete, submission 55447414,
  2026-08-12T20:18Z–20:35Z (per the original Luca audit's pull) → cross-checked, unchanged.
- V2: 43 complete real games (+1 validation, excluded), 0 incomplete, submission 55449878,
  2026-08-12T05:35Z–23:35Z.
- Unavailable fields: neither agent's own stdout/stderr logs are retrievable for the other
  side's team (403, applies symmetrically); no per-game rating delta exists on either side (only
  each submission's current aggregate score); opponent ratings are current snapshots, not
  ratings at match time.
- Parsing issues: none — 0 replay download failures, 0 unparseable episodes, both agents'
  archetype tags and deck hashes were 100% internally consistent (single fixed decklist each).

### CONFIDENCE, per key metric
| Metric | Confidence | Why |
|---|---|---|
| Win rate (either agent) | MEDIUM | real data, but modest n and CIs are wide |
| First/second split (V2 second-side, n=12) | LOW | too few games |
| KO success rate gap | HIGH | CIs don't overlap, mechanism (Phantom Dive is bench-targeting) independently confirmed from card data |
| Retreat-category marginal rates (§4 table) | MEDIUM | large denominators (500-4000+), but definitions carry the stated approximations |
| Critical-situation retreat rate (§5) | MEDIUM | depends on the `opp_lethal_now` approximation; direction is consistent with the marginal retreat data, magnitude uncertain |
| Counterfactual analysis (§6) | LOW / not estimable | n=1 and n=0 — explicitly reported as not identifiable, not given false confidence |
| Deck-mechanics facts (§9) | HIGH | pulled directly from the engine's own `CardData`/`Attack` tables, not inferred |
| Opponent-pool rating gap (§9) | MEDIUM | current snapshots, not at-match-time ratings (known structural limitation, same as the original Luca audit) |

---

## 13. Note on scope discipline

This report used **only** V2's 43 real Kaggle ladder games and Luca's 69 real Kaggle ladder
games as the primary dataset for every statistic above. Local V1-vs-V2 simulation data (the
first Luca audit's V2-side source) was **not** used for any number in §3–§11 — it is
superseded by this report for anything about V2's own behavior. No synthetic games were run.

---

## 14. Final conclusion

### What we now know about V2
- V2's real ladder record: 27-16 (62.8%) over 43 games, submission 55449878, 2026-08-12.
- V2's KO-success-per-attack (68.9%) is genuinely, statistically lower than Luca's (87.8%) —
  but Dragapult ex's own signature attack not hitting the active Pokémon is an independently
  confirmed, deck-level reason a meaningful part of that gap could exist without any policy
  difference at all.
- V2 hits a 2+ prize deficit far more often than Luca (44.2% vs 20.3%) and its games run longer
  (12.5 vs 10.8 turns) — partly explained by Dragapult ex's slower (Stage 2) evolution line.
- V2's raw retreat rate is **not** lower than Luca's overall (1.81% vs 1.02% — V2 retreats
  *more* by this count) — the only place Luca clearly retreats more is specifically inside the
  narrow "everything-stacked-against-you" critical-situation cut (8.1% vs 3.3%), and even there
  the practical consequence (getting KO'd immediately after staying) was observed **0 times for
  V2 and 1 time for Luca** out of a combined 226 critical situations.
- V2's real first/second gap (61.3% vs 66.7%, n=31/12) is far smaller than the local-simulation
  gap reported in the first Luca audit (49.3% vs 65.3%, n=75/75) — same direction, much weaker
  signal, thin sample on the "second" side.

### What remains unknown
- Whether V2's lower win rate vs Luca reflects policy quality at all, given the two are not
  competing in the same rating band (opponent means ~618 vs ~977) and pilot entirely different
  decks with different mechanical ceilings.
- Whether retreat timing specifically costs V2 games in general (as opposed to the 0 directly
  observed cases in this dataset) — 43 games is not enough to rule out a real but rare effect.
- The true share of the KO-success gap attributable to deck mechanics vs policy — not
  separable without a controlled swap (different policy on Dragapult ex, or V2's policy on a
  different deck), neither of which exists.

### Does the real ladder data support the Gemini hypothesis ("V2 loses to Luca because of
insufficient defensive retreat / prize denial")?

**NOT SUPPORTED** by the specific mechanism the hypothesis describes (stay-in-danger →
get-immediately-KO'd), which was observed **0 times for V2** across 90 true critical
situations in 43 real games. **PARTIALLY SUPPORTED** in a narrower, weaker sense: Luca does
retreat about 2.4× more often than V2 specifically when every danger signal stacks up
simultaneously (8.1% vs 3.3%, CIs overlapping, not fully separated statistically), so the
*behavioral difference* the hypothesis points at is real and directionally confirmed — it is
the **causal claim that this difference is costing V2 games** that the data does not support on
this pass. Given the overlapping CIs, the opponent-pool confound, and the deck-mechanics
confound (§9), the honest overall call is:

**INSUFFICIENT DATA** to confirm or reject the hypothesis as a cause of V2's win-rate gap vs
Luca — but the specific mechanism proposed (immediate punishment for staying active) is the
part that is actually **NOT SUPPORTED**, and that is the actionable part of this conclusion:
if `preservation_bias`/`defensive_retreat_enabled` tuning is considered later, it should not be
justified by "V2 is getting punished for staying active," because this dataset shows that
essentially never happens to either agent.

No V6 is proposed. No weights were changed. This is the data-validation checkpoint requested;
the next decision is the user's.
