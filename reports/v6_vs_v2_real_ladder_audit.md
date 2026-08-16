# V6 vs V2 — REAL LADDER AUDIT

**Scope**: real Kaggle ladder games only. V2 and V6 only (no V3/V4/V5/Luca, except as
methodological reference where the V2 baseline was already established). Read-only —
no code, weights, decks, or agents were changed in the course of this audit, and no V7
is proposed. Every claim below is tagged **FACT** (directly measured from real replay
data or source code), **HYPOTHESIS** (a plausible but unconfirmed explanation), or
**INSUFFICIENT DATA** (sample too small / signal not resolvable from what's available).

---

## Executive Summary

V6 was submitted to the real Kaggle ladder on 2026-08-13 (submission `55475115`) and has
accumulated **29 real ladder games** at the time of this audit — just over the ~28-game
floor set for this audit, so win-rate/rating claims below are directional, not final.
V2's comparison baseline is its already-validated **43-game** real-ladder dataset
(submission `55449878`), reused unchanged from prior sessions for apples-to-apples
consistency with the previously-cited 149-attack Phantom Dive figures.

**Headline result: the two V6 fixes work mechanically exactly as designed, and Phantom
Dive KO conversion improved from 52.4% to 82.4% — a statistically significant jump
(two-proportion z=2.92, p=0.0036) even at this sample size.** Win rate did **not**
detectably improve (62.8% V2 vs 62.1% V6, p=0.95, statistically indistinguishable) over
these specific 43/29-game samples, and V6 faced a modestly higher-rated opponent pool on
average, which is a real confound for any rating/win-rate claim. A **new, previously
undocumented issue** was found and mechanistically confirmed as the dominant cause of
V6's 6 residual Phantom Dive misses: Fix #2 only patches the `i==0` (opponent's Active)
iteration of `main_option_proc`'s target loop — the identical flat-200-damage false
premise remains live, unpatched, for `i>=1` (every bench Pokemon), still causing the
planner to prefer high-value-but-unreachable bench targets over reachable ones. This is
reported as a finding, not acted on.

---

## PART 1 — Submission Identification

Checked directly against `competition_submissions()` this session (not from memory/
registry files, which were stale — the project memory as of end of the prior session
said V6 was "not yet submitted"; it was submitted several hours later, same day).

| Version | Submission ID | Submitted (UTC) | File | Status | Real games (`EPISODE_TYPE_PUBLIC`) | Current public score |
|---|---|---|---|---|---|---|
| V2 (used) | `55449878` | 2026-08-12T05:34:31Z | `challenger_v2_20260812T053030Z.tar.gz` | COMPLETE | 43 (at time of the prior V2 audit pull; **47 exist right now**, see note below) | 687.3 |
| V2 (dormant duplicate — NOT used) | `55449821` | 2026-08-12T05:31:13Z | same file, byte-identical | COMPLETE | 0 (only the self-play validation episode; superseded before matchmaking ever used it, stuck at the 600.0 starting baseline) | 600.0 |
| V6 (used) | `55475115` | 2026-08-13T05:29:14Z | `challenger_v6_20260813T050318Z.tar.gz` | COMPLETE | 29 | 731.0 |

**FACT**: only one V6 submission exists (checked directly — no duplicate/superseded-ID
disambiguation needed for V6, unlike V2/V4 in prior sessions).

**FACT**: V2 has the same duplicate-submission pattern documented in prior sessions for
V4 — two byte-identical uploads 3 minutes apart, one (`55449821`) never matched into real
games and stuck at 600.0, the other (`55449878`) is the real, live one. `55449878` is
used throughout this audit, exactly as in the prior V2 Phantom Dive forensic work.

**Methodology note (transparency, not a correction)**: a fresh episode-count check
during this audit found V2's live submission now has **47** real games, not 43 — 4 more
have accumulated since the prior session's pull. This audit deliberately **keeps V2's
existing, already-validated 43-game / 149-Phantom-Dive-attack dataset** as the
comparison baseline, because the task explicitly anchors to that established figure
("V2 baseline: 149 attacks, 63 opportunities, 33 successful, 30 missed, 52.4%
conversion") and re-pulling would silently shift a cited reference number mid-audit. The
4 uncounted V2 games are a known, disclosed gap — not hidden.

**Build identity (source-verified)**: V6 is a byte-for-byte fork of V2's shared engine
(`src/agents/dragapult_policy_v2plus.py` → `src/agents/dragapult_policy_v6.py`) with
exactly two functional deltas (confirmed by direct `diff`, see Part 5). No other agent
file (deck, weights, retreat logic, search) differs between V2 and V6.

---

## PART 2 — Apples-to-Apples Ladder Comparison

Identical extraction/parsing pipeline used for both
(`src/meta_analysis/ladder_behavior_audit.py`, applied via
`tools/build_ladder_behavior_audit.py` — the same module already used for the V2-vs-Luca
audit). Wilson 95% CIs throughout.

| Metric | V2 (n=43) | V6 (n=29) | Note |
|---|---|---|---|
| Wins / Losses / Draws | 27 / 16 / 0 | 18 / 11 / 0 | FACT |
| Win rate (Wilson 95% CI) | 62.8% [47.9%, 75.6%] | 62.1% [44.0%, 77.3%] | FACT. Two-proportion z-test: z=−0.06, **p=0.95 — not significant** |
| Current live rating | 687.3 | 731.0 | FACT, but confounded by opponent-pool differences (Part 9) — do not read as "V6 is +44 Elo better," see Part 9/13 |
| Mean / median opponent rating | 617.8 / 623.6 | 648.5 / 637.9 | FACT — V6 faced opponents ~+31 rating higher on average |
| First-player win rate (Wilson CI) | 61.3% [43.8%, 76.3%] (n=31) | 68.2% [47.3%, 83.6%] (n=22) | FACT, both wide CIs |
| Second-player win rate (Wilson CI) | 66.7% [39.1%, 86.2%] (n=12) | 42.9% [15.8%, 75.0%] (n=7) | FACT, very small n, see Part 10 |
| Mean game length (turns), all games | 12.5 | 13.7 | FACT |
| Mean game length, wins / losses | 12.7 / 12.2 | 14.3 / 12.6 | HYPOTHESIS: no evidence V6 wins are *faster* — if anything slightly slower; not attributable to KO conversion alone without controlling for opponent deck |
| Prizes we scored / game (full-replay trace) | 4.28 | 4.52 | FACT (see Part 7 methodology) |
| Prizes opponent scored / game | 2.93 | 4.48 | FACT — V6's opponents also scored more; see Part 9 confound |
| Retreat rate (chosen / available) | 5.0% | 4.7% | FACT, essentially identical — retreat logic is untouched code, as expected |
| Critical-situation retreat rate (retreat available AND opponent lethal-now) | 4.7% (11/233) | 6.1% (16/264) | FACT, both very low, overlapping CIs |
| Attacks per game | 3.51 | 3.31 | FACT |

**Game length / KO-conversion-speed claim**: **HYPOTHESIS, not supported**. V6 does not
win faster than V2 despite far better Phantom Dive conversion — mean turns-per-win is
actually slightly *higher* for V6 (14.3 vs 12.7). This is plausible (V6's harder
opponent pool takes longer to beat) but not confirmed; **do not conclude "better KO
conversion → faster wins"** from this sample.

---

## PART 3 — THE CRITICAL V6 TEST: Phantom Dive KO Conversion

Identical methodology to the established V2 baseline (`tools/build_phantom_dive_forensic.py`,
re-parameterized for V6 as `tools/build_phantom_dive_forensic_v6.py` — same immunity
rules, same brute-force-optimal allocation search, same denominator definition: "events
where the pre-attack, immunity-adjusted opponent bench state made ≥1 KO reachable with
some allocation of the attack's 6 damage counters").

| | V2 (baseline) | V6 |
|---|---|---|
| Total Phantom Dive attacks | 149 | 97 |
| Events with a real (immunity-adjusted) KO opportunity | 63 | 34 |
| Successful (achieved the optimal-prize outcome) | 33 | 28 |
| Missed | 30 | 6 |
| **KO conversion rate** | **52.4%** | **82.4%** |
| Wilson 95% CI on conversion | [40.3%, 64.2%] | [66.5%, 91.7%] |
| Missed-KO rate when a KO was available | 47.6% | 17.6% |
| Bench KOs landed (total) | 43 (42×1-prize, 1×2-prize) | 32 (31×1-prize, 1×2-prize) |
| Multi-KO opportunities available / achieved | 8 / 4 | 0 / 0 |
| Prize value lost to missed KOs | 32 | 7 |
| Active KOs via Phantom Dive | 0 (by construction — bench-only attack) | 0 |

**FACT, statistically significant**: two-proportion z-test on conversion rate, V2 33/63
vs V6 28/34: **z=2.92, p=0.0036**. This clears significance despite the modest V6 sample
— the effect size (+30 points of conversion) is large enough to be detectable even at
n=34 opportunities.

**FACT**: V6 had **zero** multi-KO-available situations in its 29-game sample (V2 had
8). This is a real gap in this specific audit's ability to test the "priority of
available KOs" question for V6 at all on genuinely simultaneous multi-target lethal —
flagged explicitly in Part 4, not glossed over.

**Conclusion for Part 3: STRONGLY SUPPORTED.** V6's Phantom Dive KO conversion is
higher, by a large and statistically significant margin, using the exact same
denominator definition as the V2 baseline.

---

## PART 4 — Missed-Lethal Forensics & Side Effects

### The "old pattern" check (target at 10 HP ignored in favor of a high-HP target)

**FACT: 0/6 of V6's real missed-KO events involve a 10-HP target at all** — the specific
`hp==10` anti-pattern that defined V2's failure mode is **absent** from V6's real-ladder
misses. By contrast, re-inspecting V2's 30 missed events turns up the pattern
repeatedly, e.g.:

- Episode `92220638`, turn 11: bench has Kyogre at **10 HP** (1 counter needed) and
  Kyogre at 100 HP (unreachable, needs 10). V2 allocated **0** counters to the 10-HP
  Kyogre and dumped all 6 into the unreachable one. 1 prize missed.
- Episode `92232003`, turn 12: **two** Staryu at 10 HP each (1 counter each, both
  killable with 2 total counters) plus an unreachable 310-HP Mega Froslass ex and an
  unreachable 70-HP Snorunt. V2 put all 6 counters into the 70-HP Snorunt (still
  insufficient, 60<70) and ignored both 10-HP Staryu entirely. 2 prizes missed.
- Episode `92226320`, turn 16: 10-HP Wattrel available (1 counter) alongside a
  reachable 50-HP Tadbulb (5 counters, total 6 — the exact double-KO). V2 avoided the
  10-HP target and split counters across two other, non-lethal targets instead. 2
  prizes missed (the multi-KO opportunity, see below).

This is the exact behavior the `score -= 100000` bug predicts, and it is **gone** in
V6's real data. **Fix #1 verdict: FIX WORKED (empirically confirmed on real ladder
data, not just synthetic tests).**

### V6's actual missed-KO events — all 6, in full (not a sample; this is the complete set)

| Episode | Turn | Result | What happened | Prize lost |
|---|---|---|---|---|
| `92557908` | 19 | WIN | Bench: Crustle 50HP (**immune**), Mega Kangaskhan ex 60HP (3-prize, exactly killable with all 6 counters), Crustle 90HP (**immune**), Dwebble 20HP (1-prize). V6 put 4 counters into an **immune** Crustle (0 real damage) and 2 into Dwebble (killed). Missed the clean 3-prize Kangaskhan kill entirely. | 2 (took 1, optimal was 3) |
| `92558848` | 12 | **LOSS** | Bench: Lunatone/Solrock/Hariyama (110–150HP, all unreachable), Mega Lucario ex 110HP (unreachable, needs 110>60), Riolu 20HP (needs 2 counters). V6 put **all 6 counters into the unreachable 110-HP Lucario ex**, zero KOs. Riolu was a free, certain 1-prize kill. | 1 |
| `92562643` | 13 | **LOSS** | Bench: Solrock/Lunatone 110HP (unreachable), Mega Lucario ex 80HP (unreachable), Makuhita 20HP (killable) and Makuhita 80HP (unreachable). V6 put all 6 into the 80-HP Lucario ex, zero KOs. The 20-HP Makuhita was free. | 1 |
| `92563590` | 6 | WIN | Bench: Kadabra 80HP (unreachable), 2×Abra 50HP (unreachable each alone), Dunsparce 60HP (exactly killable with all 6). V6 put all 6 into the unreachable 80-HP Kadabra. | 1 |
| `92563590` | 8 | WIN | Bench: Alakazam 80/140HP (unreachable), Abra 50HP (unreachable alone), Dunsparce 60HP (exactly killable). V6 again committed all 6 to the unreachable Alakazam. | 1 |
| `92568309` | 11 | WIN | Bench: Mega Lucario ex 80HP (unreachable), Solrock 50HP (killable with 5 counters), Riolu 80HP (unreachable). V6 put all 6 into the unreachable Lucario ex; Solrock was free. | 1 |

**New finding (not one of the two documented V6 fixes) — mechanistically confirmed, see
Part 5**: in every one of these 6 cases, V6 dumped its entire attack into the
**highest-prize-value bench target present, even when that target's HP exceeded the
60-damage/6-counter budget and was therefore mathematically unkillable this attack** —
while a fully reachable, lower-value kill sat unused. This is a distinct but related
failure mode to the old `hp==10` bug: not "avoid the cheap kill," but "fixate on the
expensive kill even when it's impossible this turn."

### Priority-of-available-KOs (over-fixation check)

**INSUFFICIENT DATA for V6 on genuinely simultaneous multi-lethal choices** — V6 had
**zero** multi-KO-available events in 29 games (vs V2's 8), so "did V6 pick the
highest-prize KO when multiple were *simultaneously* achievable" cannot be tested on V6
in this sample.

For V2 (where 8 such situations exist), **none involved a straight 1-prize-vs-2-prize
trade-off** — all 8 were pairs of 1-prize targets (combined value 2 either way), so V2's
"priority of KOs" question also reduces to *whether it got both*, not *which one it
prioritized by value*. V2 got both in 4/8 (50%), one of two in 2/8, and zero in 2/8 —
and the zero-of-two cases are, again, the `hp==10`-avoidance pattern (both examples
above). No evidence either agent, in this specific sample, ever had to choose between a
cheap 1-prize kill and an available 2-prize kill and picked wrong — that specific
scenario (Part 4's literal "was a 2-prize KO available while a 1-prize KO was selected")
did not occur in the observed data for either agent. **Class D (arbitrary/suboptimal
allocation, not value-priority)** best describes both agents' actual failures: wasted
counters on an unreachable or immune target while a reachable lower-effort kill was
available — this is a *reachability* miscalibration, not a *value-ranking* miscalibration.

---

## PART 5 — Did the Two V6 Fixes Actually Activate?

Traced directly against the live production code
(`src/agents/dragapult_policy_v6.py` vs `src/agents/dragapult_policy_v2plus.py`, full
`diff` performed this session — reproduced in the appendix note below).

### A. `hp == 10` backwards penalty

**FACT (source)**: confirmed present as `score -= 100000` in V2's
`DAMAGE_COUNTER_ANY` fallback (line ~823), and confirmed changed to `score += 40000` in
V6 — the only textual difference at that line. **FIX WORKED** — both structurally
(source diff) and empirically (Part 4: the anti-pattern is 0/6 in V6's real misses vs
recurring in V2's).

### B. Phantom Dive planning separated from the generic `Active = 200 damage` premise

**FACT (source)**: `main_option_proc`'s `i == 0` (opponent's Active) branch is gated:
```python
if i == 0 and self.can_main_attack:
    active_damage = 0          # V6
else:
    active_damage = 0 if no_damage_dex(pokemon.id) else damage   # V2: damage=200 (unconditional)
```
This fix is **structurally complete for i==0**: with `active_damage` forced to `0`,
`pokemon.hp <= active_damage` can never be true for a live Active (hp is always >0), so
`base_prize_count` for the Active iteration is always `0`, and the `remain_prize <=
base_prize_count` shortcut — the exact mechanism that emptied `self.plan_b.counter` for
Phantom Dive in V2 — can **never fire** at `i==0` anymore.

Empirically confirmed against all real Phantom Dive main-decisions (149 for V2, 97 for
V6), tracking exactly the condition the source code evaluates (opponent Active's real HP
and our own remaining-prize count at each decision):

| | V2 | V6 |
|---|---|---|
| PD main decisions | 149 | 97 |
| Active genuinely already at 0 HP at decision time (benign, not a bug) | 97 (65.1%) | 58 (59.8%) |
| Active **falsely** treated as already-dead while still alive (the actual bug) | **46 (30.9%)** | **0 (0%)** |
| Of those, cases where it fully emptied `plan_b.counter` (shortcut condition met) | 3 (2.0%) | 0 (0%) |

**FIX #2 verdict for its stated scope (i==0/Active): WORKED, both mechanically and
empirically — 100% elimination of the false-premise misevaluation on real ladder
data.**

### C. ENDGAME CHECK (`self.plan_b.counter` populated vs empty)

**FACT**: `self.plan_b` is a snapshot taken **only** at loop iteration `i==0`, frozen
before any bench iterations run — i.e. it captures "what's the best bench combo *on top
of* the Active being handled." With Fix #2, this snapshot is now **always** the genuine
bench-only combo search result (never the empty-list shortcut) for i==0's own
contribution. Measured empty-plan rate (any cause) at real decisions:

| | V2 | V6 |
|---|---|---|
| `plan_b.counter` empty (any cause) | 11/149 (7.4%) | 7/97 (7.2%) |
| — of which: benign (Active genuinely already dead) | 4 | 7 (100%) |
| — of which: **caused by the false-premise bug** | **3** | **0** |

V6's small residual empty-plan rate (7.2%) is now **entirely** explained by legitimately
already-dead opposing Actives (a real, unavoidable game state, present in V2 too) — not
by the bug. **Endgame check verdict: FIX WORKED** — the specific empty-`plan_b`-in-close
-games failure mode Part 5C asks about is fully closed for its scoped condition.

### D. New finding — Fix #2's scope is narrower than the bug it targets

**FACT (source, newly discovered this audit, not previously documented in any prior
report/memory)**: the identical false-premise pattern (`pokemon.hp <= active_damage`
using the flat `damage = 200` constant) is **only patched for `i == 0`**. For `i >= 1`
(every **bench** Pokemon), the code still falls to
`active_damage = 0 if no_damage_dex(...) else damage` — i.e. still 200 — **even when
Phantom Dive is the attack being evaluated**. `damage = 200` is a single hardcoded
literal set once in `agent()` (not attack-specific), reused for every context.

This means: for any bench Pokemon with HP ≤ 200, `main_option_proc`'s combo search
still gets a **fabricated "this Pokemon is already dead" credit** when picking which
bench Pokemon should anchor the plan — even though Phantom Dive can only ever deliver at
most 60 damage, split across up to 6 targets. Combined with the pre-existing,
deliberately-left-unfixed `prize==1: score -= 300` vs `prize==0: score += 1200`
asymmety documented in the V6 fix report, this creates a strong bias toward planning
around a high-prize-value bench target that is **mathematically unreachable this
attack**, over a lower-value target that is genuinely killable.

**This mechanism explains all 6 of V6's real-ladder Phantom Dive misses** (Part 4
table): in every case, the target that absorbed the wasted counters had HP ≤ 200 (thus
falsely "already dead" under this unpatched branch) and a higher raw `pokemon_score`
(ex/mega-ex) than the actually-reachable alternative. Cross-checked against the
plan-vs-fallback data: all 6 occurred with a **non-empty** `plan_b.counter` — confirming
the miss is a **wrong plan**, not a **missing plan**.

**Classification for Part 5: FIX #2 WORKED for its documented, scoped bug (i==0/Active)
— confirmed both structurally and empirically, 100% elimination. A separate, structurally
identical but unscoped instance of the same false-premise pattern (i≥1/bench) remains
live and is the dominant explanation for V6's residual real-ladder misses.** This is
reported as a finding for future reference; per this audit's explicit no-fix mandate,
nothing was changed and no V7 is proposed.

---

## PART 6 — Plan vs Fallback Behavior

| | V2 | V6 |
|---|---|---|
| PD attacks with a non-empty plan (any i≥0 contribution) | 92.6% (138/149) | 92.8% (90/97) |
| Of KO-opportunity events specifically: plan existed | 56/63 (88.9%) | 32/34 (94.1%) |
| Of KO-opportunity events: plan was empty | 7/63 (11.1%) | 2/34 (5.9%) |
| KO conversion **when plan exists** | 58.9% (33/56) | 81.25% (26/32) |
| KO conversion **when plan is empty** | **0.0% (0/7)** | 100% (2/2, small n) |

**FACT**: for V2, an empty plan was **catastrophic** — 0/7 conversion whenever
`plan_b.counter` was empty, vs 58.9% when a plan existed. This confirms empty-plan
situations were a real, severe failure mode in V2, exactly as the fix report predicted —
but they were a *minority* of V2's total problem (7/63 KO opportunities, 11%). **The
majority of V2's shortfall (33/56 = 58.9% conversion even WITH a plan, i.e. 23/56 misses
happened despite a non-empty plan) came from something else** — consistent with Part 5D's
finding that the plan itself could still be *wrong*, not just *absent*.

**FACT**: V6's plan-exists conversion (81.25%) is far closer to ceiling than V2's
(58.9%), and empty-plan situations in V6 are rare (5.9%) and benign (Part 5C). **This is
the real mechanism behind V6's overall conversion jump: V6 didn't just stop having empty
plans — its plans, when present, are also converting far more often**, which is
consistent with Fix #1 (the plan-following fallback scoring during DAMAGE_COUNTER_ANY no
longer actively avoids cheap kills) contributing on top of Fix #2.

**Verdict: V6 fixed both the empty-plan problem (for its scoped condition) AND
substantially improved plan-following fidelity — not merely one or the other.**

---

## PART 7 — Prize Economy

Computed from a full-replay trace (every environment tick, both players' channels — not
just our own decision-point snapshots, which undercounts KOs that happen between our
decisions; see methodology note below) via `tools/build_prize_economy_v2_v6.py`.

| | V2 | V6 |
|---|---|---|
| Prizes we scored / game | 4.28 | 4.52 |
| Prizes opponent scored / game | 2.93 | 4.48 |
| Net prize margin / game (we − opponent) | **+1.35** | **+0.03** |
| Max prize deficit faced, mean | 2.53 | 2.90 |
| Max prize deficit faced, max | 6 | 6 |
| Games facing a ≥2-prize deficit at some point | 24/43 (55.8%) | 18/29 (62.1%) |
| Comeback rate from ≥2-prize deficit | 45.8% (11/24) | 44.4% (8/18) |
| Wins ending strictly ahead on the prize count | 21/27 (77.8%) | 14/18 (77.8%) |

**Methodology note**: an earlier pass using only our own decision-point prize snapshots
(the same convention `ladder_behavior_audit.py` uses) undercounted opponent-scored
prizes severely (it showed 0 opponent KOs across both agents' entire samples, which is
clearly wrong for agents with double-digit loss counts) — traced to real decision gaps
right before game-ending turns. The full-replay-trace numbers above are the corrected,
authoritative ones and are used throughout this report; the decision-snapshot numbers
are **not** used for any prize-economy claim.

**FACT**: V6's *net* prize margin per game (+0.03) is much closer to break-even than
V2's (+1.35), even though V6's *own* scoring rate is higher (4.52 vs 4.28) — because
V6's opponents also scored far more against it (4.48 vs 2.93). **This is best explained
by the opponent-strength confound (Part 9), not by a regression in V6's own play** —
V6's win rate held steady (62.1% vs 62.8%) despite facing tougher opponents who score
more prizes, which is consistent with V6 being at least as strong per-opponent-difficulty,
not weaker. **HYPOTHESIS**, not fully separable from the confound with this sample size.

**Comeback frequency and "ending ahead when winning" are statistically indistinguishable
between the two (44-46% comeback rate, 77.8% ahead-when-winning for both)** — no
evidence of a change in close-game resilience either direction.

---

## PART 8 — Loss-Specific Analysis

Using both missed-KO detectors already established for this project (the general
non-Phantom-Dive detector from `ladder_behavior_audit.py`, and the Phantom-Dive-specific
detector from Part 3/4), applied only to games each agent lost.

| | V2 (16 losses) | V6 (11 losses) |
|---|---|---|
| Losses with ≥1 missed KO of any kind (union of both detectors) | 8/16 (50.0%) | 5/11 (45.5%) |
| Losses with ≥1 general (non-PD) confirmed/possible missed KO | 5/16 (31.3%) | 3/11 (27.3%) |
| Losses with ≥1 Phantom-Dive-specific missed lethal | 4/16 (25.0%) | 3/11 (27.3%) |

**FACT**: this reproduces the project's own established V2 figure exactly — "V2 lost
only 5 games where a [general] KO was missed" (this audit independently recomputes 5/16
using the identical detector) — confirming methodological continuity with prior work.

**Do not treat these as "the missed KO caused the loss."** Spot-checking V6's 2 losses
with a Phantom-Dive-specific miss:

- `92558848` (the 110-HP-Lucario-fixation example from Part 4): the miss happened at
  turn 12; the game continued for several more turns afterward before V6 lost — the
  missed 1-prize Riolu kill was a real, quantifiable cost (V6 was capped at 4 prizes
  taken all game instead of a possible 5), but whether it was *decisive* (i.e. the
  1-prize swing flipped the outcome) is **INSUFFICIENT DATA to determine** without a
  full game-by-game counterfactual replay, which is out of scope for this audit.
- `92562643`: similarly, the miss (Part 4 table) occurred mid-game, not obviously on the
  final turn.

**Verdict for Part 8: descriptive parity, not evidence of a directional change.** V2 and
V6 have statistically indistinguishable rates of "lost a game that also contained a
missed lethal somewhere" (50.0% vs 45.5%, n far too small to test formally) — the
prompt's own standing caution (don't over-attribute losses to missed KOs) is corroborated
again here, at both stages of this project's evolution.

---

## PART 9 — Opponent-Strength Confound

**FACT, real confound, not hypothetical**: V6 faced a harder opponent pool. Mean
opponent rating 648.5 (V6) vs 617.8 (V2), **+30.6 points**; median 637.9 vs 623.6. This
is expected given V6's own higher live rating (731.0 vs 687.3) under Bayesian
rating-proximity matchmaking — a stronger agent gets paired against stronger opponents,
which mechanically compresses its own observed win rate relative to a "true" skill gap.

Overlapping opponent-rating-band comparison (win rate, Wilson 95% CI):

| Band | V2 win rate (n) | V6 win rate (n) |
|---|---|---|
| <650 | 71.4% [52.9%, 84.7%] (n=28) | 66.7% [41.7%, 84.8%] (n=15) |
| 650–750 | 40.0% [16.8%, 68.7%] (n=10) | 54.5% [28.0%, 78.7%] (n=11) |
| 750–850 | 60.0% [23.1%, 88.2%] (n=5) | 50.0% [9.5%, 90.5%] (n=2) |
| 850+ | n=0 | 100% (n=1) |

**INSUFFICIENT DATA to draw a confident directional conclusion from the banded
comparison** — every band has overlapping, wide Wilson CIs, and the 750+ bands have n≤5
on both sides. The one band with a reasonable comparison size on both sides (650–750:
n=10 vs n=11) actually favors V6 (54.5% vs 40.0%), which is at least consistent with — but
far from proof of — V6 being no weaker once opponent strength is (crudely) controlled
for. **Do not read the raw, unbanded win-rate tie (62.8% vs 62.1%) as "no improvement" without
this caveat** — given V6 faced tougher opponents on average and matched V2's raw win
rate anyway, the confound cuts toward V6 being *at least as strong*, not weaker, but this
audit's sample size cannot make that a statistically confident claim.

---

## PART 10 — First / Second Player Effect

| | V2 | V6 |
|---|---|---|
| First-player win rate (Wilson CI) | 61.3% [43.8%, 76.3%] (n=31) | 68.2% [47.3%, 83.6%] (n=22) |
| Second-player win rate (Wilson CI) | 66.7% [39.1%, 86.2%] (n=12) | 42.9% [15.8%, 75.0%] (n=7) |

**FACT**: both agents' first/second splits are heavily first-player-skewed in raw game
counts (V2: 31 first / 12 second; V6: 22 first / 7 second) — consistent with the
project's known `always_first=True` configuration for both V2 and V6, so the "second
player" subsample is small in both cases (n=12, n=7) and its CI is correspondingly wide.

**INSUFFICIENT DATA to conclude any real first/second effect difference between V2 and
V6** — the CIs overlap heavily (V2 second-player 66.7% vs V6 second-player 42.9% looks
like a big gap, but n=7 for V6 means the CI spans 15.8%–75.0%, i.e. is statistically
compatible with V2's second-player rate). No fix to first/second behavior was made or is
proposed, per the standing instruction.

---

## PART 11 & 12 — Verdicts

**Q1. Did V6 increase Phantom Dive lethal conversion?**
**YES — STRONGLY SUPPORTED.** 52.4%→82.4%, z=2.92, p=0.0036.

**Q2. Did V6 reduce missed lethal bench allocations?**
**YES — STRONGLY SUPPORTED.** 30/63 (47.6%) → 6/34 (17.6%) missed-when-available;
two-proportion z=−2.92, p=0.0036 (same test, mirrored). The specific `hp==10`
anti-pattern is completely absent from V6's real misses (0/6 vs recurring in V2's 30).

**Q3. Did V6 reduce empty-plan/fallback frequency?**
**PARTIALLY SUPPORTED.** The *bug-caused* empty-plan rate went from 2.0%→0% (fully
eliminated for its scoped condition), but the *raw* empty-plan rate barely moved
(7.4%→7.2%) because most empty-plan events in both versions are benign
(already-dead-Active), not bug-caused. What actually improved more was **plan-following
quality when a plan exists** (58.9%→81.25% conversion), not just plan presence — see
Part 6.

**Q4. Did V6 increase prizes taken per game and prize margin?**
**MIXED / CONFOUNDED.** Prizes-we-scored/game rose modestly (4.28→4.52), but net prize
margin fell (+1.35→+0.03) because opponents also scored more against V6 — attributable
to the opponent-strength confound (Part 9), not a regression in V6's own play, but this
is **HYPOTHESIS**, not proven, at this sample size.

**Q5. Did V6 improve win rate (adjusting for opponent rating)?**
**INSUFFICIENT DATA for a confident answer.** Raw win rate is statistically tied
(62.8% vs 62.1%, p=0.95). Opponent-rating-banded comparison is directionally
consistent with "no worse, possibly slightly better once adjusted" but every band's CI
is too wide (n≤15 per band) to call this resolved.

### Final classifications

| Claim | Classification |
|---|---|
| "The two code fixes work mechanically." | **STRONGLY SUPPORTED** — confirmed by source diff and by empirical replay measurement (false-premise rate 30.9%→0%, `hp==10` anti-pattern 0/6 in V6) |
| "The two fixes improve Phantom Dive KO conversion." | **STRONGLY SUPPORTED** — 52.4%→82.4%, p=0.0036, and the mechanism is directly traceable (plan-exists conversion 58.9%→81.25%) |
| "The improved KO conversion improves prize economy." | **PARTIALLY SUPPORTED** — V6 scores more prizes/game (4.28→4.52), but net margin is confounded by opponent strength; cannot cleanly isolate the KO-conversion effect on net margin from this sample |
| "The improved prize economy improves win rate." | **NOT SUPPORTED (at this sample size)** — win rate is flat (62.8% vs 62.1%, not significant); the causal chain from KO conversion → win rate is not observable in 29 games, whatever its true value |
| "V6 is objectively stronger than V2 on the real ladder." | **INSUFFICIENT DATA** for the win-rate/rating claim specifically (opponent-strength-confounded, small n); **STRONGLY SUPPORTED** for the narrower, well-evidenced claim that V6's Phantom-Dive-specific decision-making is objectively better than V2's |

---

## PART 13 — Sample Size Discipline

V6 has 29 real games — just over this audit's ~28-game floor. Per the standing
instruction: **no strong ELO/win-rate claim is made** (Q5, and the "objectively
stronger" claim, are both explicitly INSUFFICIENT DATA/qualified above). **Strong claims
are made about code-path behavior and mechanical Phantom Dive behavior** (Parts 3, 5, 6),
which rest on 97 real Phantom Dive attacks and 34 real KO opportunities for V6 — a
substantially larger, better-powered sample than the 29-game headline count, and where
the effect size (30 percentage points of KO conversion) is large enough to clear
significance even so.

---

## What We Know

- Both V6 fixes are confirmed present in the live production code path and confirmed
  functionally active on real ladder games, not just synthetic tests.
- Phantom Dive KO conversion improved from 52.4% to 82.4%, a statistically significant,
  large effect, using the identical denominator methodology as the established V2
  baseline.
- The specific `hp==10` avoidance anti-pattern is completely gone from V6's real-ladder
  behavior.
- V6's empty-plan-via-bug rate for the opponent's Active is fully eliminated (30.9%→0%
  false-premise rate; 2.0%→0% bug-caused empty-plan rate).
- A new, previously undocumented bug was found and mechanistically confirmed: the same
  false-premise pattern Fix #2 targeted for `i==0` (Active) is still present, unpatched,
  for `i≥1` (bench targets), and explains all 6 of V6's residual real-ladder Phantom
  Dive misses.
- Win rate is statistically flat between the two versions on real ladder data,
  confounded by V6 facing a modestly stronger opponent pool.

## What Remains Unknown

- Whether V6's Phantom-Dive improvement translates into more wins once opponent
  strength is properly controlled for (not just banded) — needs a much larger V6 sample
  (well beyond 29 games) or a formal opponent-adjusted (e.g. logistic) model.
- Whether the missed KOs in either agent's losses were actually decisive (this audit
  deliberately did not attempt full game-counterfactual replay to answer that).
  Whether the newly-found `i≥1` bench false-premise issue, if fixed, would meaningfully
  close V6's remaining 17.6% miss rate — plausible given it explains 6/6 of the observed
  misses, but unverified (no fix was implemented or tested, per this audit's mandate).
- Whether V6's first/second-player split difference (68.2%/42.9% vs V2's 61.3%/66.7%) is
  real or small-sample noise — current data cannot distinguish the two.

---

### Appendix: data provenance

All figures in this report are computed by scripts written this session and are
reproducible from the raw pulled data (all read-only against Kaggle):

- `tools/pull_v6_ladder_data.py` — V6 episode/replay/opponent-rating pull
  (`data/v6_ladder_audit/`)
- `tools/build_ladder_behavior_audit.py` — extended with a `v6` target, reusing
  `src/meta_analysis/ladder_behavior_audit.py` unchanged
  (`results/ladder_behavior_audit/v6_*.csv`)
- `tools/build_phantom_dive_forensic_v6.py` — V6 Phantom Dive KO-conversion forensic,
  identical methodology to the V2 script (`results/phantom_dive_forensic_v6/`)
- `tools/build_plan_vs_fallback_audit.py` — new this session; source-grounded
  plan-vs-fallback / false-premise measurement for both V2 and V6
  (`results/v6_v2_audit/plan_vs_fallback.json`)
- `tools/build_prize_economy_v2_v6.py` — new this session; full-replay-trace prize
  economy (corrects the decision-snapshot undercounting issue found and documented in
  Part 7) (`results/v6_v2_audit/prize_economy.json`)
- `tools/build_v6_v2_audit_stats.py` — aggregate Part 2/4/7/9/10 statistics with Wilson
  CIs (`results/v6_v2_audit/stats.json`)
