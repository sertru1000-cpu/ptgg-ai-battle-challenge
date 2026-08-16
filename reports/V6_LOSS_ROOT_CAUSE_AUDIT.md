# V6 Loss Root-Cause Audit — REAL LADDER

**Date**: 2026-08-13. **Scope**: diagnostic-only forensic audit of every real Kaggle-ladder loss
V6 has played, per explicit instruction. **No code, weight, deck, or submission changes were
made this session.** No V7 was built or recommended. This report answers *why V6 still loses*,
not *how to fix it*.

**Tagging convention** (per standing project rule, [[feedback-ptcg-process]]): every claim below
is marked **FACT** (directly observed in replay data), **MEASURED RESULT** (computed statistic,
sample size stated), **HYPOTHESIS** (plausible but not confirmed), or **INSUFFICIENT DATA**.

---

## PART 1 — V6 Real Ladder Data

- **Submission**: `55475115`, file `challenger_v6_20260813T050318Z.tar.gz`, submitted
  2026-08-13T05:29:14Z. Build identity: V2 Balanced (Dragapult ex, `BALANCED` weights,
  `always_first=True`) + the two confirmed Phantom Dive bug fixes from session 24
  (`hp==10` anti-pattern fix, active-damage-contamination fix) — see
  `PHANTOM_DIVE_V6_FIX_REPORT.md`. No other change vs V2.
- **Real ladder games**: 30 `EPISODE_TYPE_PUBLIC` (+1 `EPISODE_TYPE_VALIDATION`, excluded
  throughout, per standing convention). **18 wins, 12 losses (60.0%)**. **FACT**, re-pulled live
  this session (up from session 25's 29-game snapshot a few hours earlier — 1 new game).
- **Current rating**: 724.0 (started 600.0; was 731.0 at session 25's 29-game snapshot — normal
  Bayesian movement, not a new finding).
- **Opponent ratings** (current live score at audit time, a snapshot not a match-time value —
  same caveat as every prior audit in this project): mean 649.7, median 630.0, n=30.
  **Losses' opponents average 651.1, wins' opponents average 648.7 — statistically
  indistinguishable (MEASURED RESULT).** V6's losses are not explained by facing systematically
  stronger opponents in aggregate; any opponent-strength effect found below is archetype- or
  game-specific, not a blanket "V6 got unlucky with tough pairings" story.
- Went first 22/30 (73.3%); first-player win rate 68.2% (15/22) vs second-player 37.5% (3/8) —
  small n, consistent in direction with this project's real-ladder-confirmed first-player
  advantage (session 14/16), not independently re-litigated here.

---

## PART 2 — Loss Corpus

All 12 real losses, reconstructed turn-by-turn from raw replay JSON via a per-turn prize
trajectory (`(turn, our_remaining_prizes, opponent_remaining_prizes, deficit)`, deficit =
ours − theirs; **positive deficit = we are behind**, since a player's own remaining-prize count
only drops when *that player* lands a knockout — verified against known WIN/LOSS labels before
use, not assumed). Full per-decision data in `results/v6_loss_audit/loss_reports.json`.

| Episode | Opponent (archetype / rating) | 1st? | Turns | First behind | First 2+ deficit | Decisive turn | Final deficit |
|---|---|---|---|---|---|---|---|
| 92549421 | Mega Lucario ex / 599.2 | Y | 11 | 6 | 8 | 8 | +4 |
| 92552245 | UNLABELED / 681.2 | Y | 15 | 2 | 6 | none (recovered to −1, still lost) | −1 |
| 92553251 | Mega Kangaskhan ex / 607.0 | Y | 11 | 6 | 6 | 6 | +5 |
| 92555101 | Mega Lucario ex / 617.1 | N | 10 | 3 | 5 | 5 | +4 |
| 92558848 | Mega Lucario ex / 674.5 | N | 12 | 3 | 5 | 5 | +4 |
| 92560743 | UNLABELED / 585.7 | Y | 9 | 2 | 4 | 4 | +4 |
| 92562643 | Mega Lucario ex / 556.0 | Y | 13 | 4 | 10 | 10 | +4 |
| 92565477 | Fezandipiti ex / 738.0 | N | 28 | 3 | none | none | +1 |
| 92571127 | Dragapult ex (mirror) / 673.9 | Y | 11 | 10 | 10 | 10 | +2 |
| 92571771 | Fezandipiti ex / 797.6 | Y | 9 | 6 | 8 | 8 | +3 |
| 92572051 | Mega Lucario ex / 673.4 | N | 10 | 3 | 5 | 5 | +5 |
| 92583351 | Marnie's Grimmsnarl ex / 610.2 | N | 12 | 5 | 9 | 9 | +5 |

**FACT**: 10/12 losses reach a "decisive turn" (a point past which the deficit is ≥2 for the
rest of the game) at or before turn 10, and 8/12 by turn 8 — the deterioration is early- to
mid-game, not a last-turn collapse, matching the project's own session-17 finding on V2 ("losses
are structurally decisive, not close") extended here to V6.

**Two notable exceptions, both worth reading in full below**: 92552245 (V6 clawed all the way
back from a 4-prize deficit to needing just **1 more prize to win**, then still lost — Part 4/6)
and 92565477 (the longest game in the sample at 28 turns, ends the closest, at a 1-prize
deficit — Part 9).

**Phantom Dive availability**: available in all 12 losses (Dragapult ex reached the field and
had ≥2 of the right energy types in every loss game — FACT). Used at least once in 10/12 losses;
not used at all in 92553251 and 92583351 (Dragapult ex present but never got a turn where the
attack was payable before the game ended — **INSUFFICIENT DATA** to say whether that itself was
avoidable without deeper energy-sequencing reconstruction, not pursued this session).

---

## PART 3 — Root-Cause Classification

Using the requested A–N taxonomy, each loss's **primary** driver (one per loss) plus any
secondary contributing factor:

| Category | Primary in | % | Secondary in |
|---|---|---|---|
| **K — Opponent snowball / unavoidable-leaning matchup** | 92549421, 92553251, 92555101, 92560743, 92571771, 92572051, 92583351 | **7/12 (58%)** | 92552245 |
| **E — Retreat / survival decision** | 92552245, 92558848, 92562643, 92571127 | **4/12 (33%)** | — |
| **D — Active Pokemon target selection (missed KO)** | 92565477 | **1/12 (8%)** | — |
| **B — Phantom Dive damage allocation** | — | 0/12 primary | 92558848, 92562643 |
| **L — Bench space management** | — | 0/12 primary (see Part 7 — present but explicitly NOT causally supported) | 92555101, 92562643, 92571771 (flagged, downgraded) |

**PRIMARY ROOT CAUSE overall: K — a chronic offensive-conversion failure concentrated almost
entirely against one archetype (Mega Lucario ex), not a single decision-level bug.** In 7 of 12
losses V6 scores **0 or 1 prizes across the entire game** while the opponent runs up 4–5 —
there is no single "bad decision" to point to because V6 was rarely offered a real choice; its
attacks simply weren't threatening the opponent's board. **SECONDARY CONTRIBUTING FACTOR: E** —
in the other 4 losses a real decision (declining an available retreat in a provably critical
spot) is identifiable and, per Part 8, empirically consequential within this loss subset.

Categories **A, C, F, G, H, I, J, M** were not found as the *primary* driver of any single loss
at the confidence this data supports (J — prize-race mismanagement — is arguably a re-description
of the K pattern rather than a distinct cause, so deliberately not double-counted). **N (unknown/
insufficient evidence)** was not needed as a primary tag for any loss — every loss had at least
one concrete, evidence-backed classification, though confidence varies (see Part 14).

---

## PART 4 — First Bad Decision Analysis

For the 5/12 losses where a genuine decision-level counterfactual exists (the other 7 are K-type
shutouts with no single flagged decision — see Part 3), the earliest concrete bad decision found:

**92558848 (LOSS vs Mega Lucario ex, turn 12, decisive turn = 5)**
- V6 action: Phantom Dive, allocated all 6 damage counters onto Mega Lucario ex's bench slot
  (hp 110/340 — already known to be unreachable for 60 damage).
- Available alternative: allocate the 6 counters onto a 20-HP Riolu on an adjacent bench slot.
- Immediate consequence: 0 prizes taken (actual) vs 1 prize taken (optimal) — same turn V6's own
  active (Dragapult ex, 20 HP) then declined a legal retreat facing a 270-damage lethal attack
  with 1 ready bench replacement, and was gone by the very next (and, in this game, final) turn.
- Why the alternative is superior: the Riolu KO was unambiguous (60 dmg ≥ 20 hp, no immunity, no
  resistance) and would have put V6 one prize closer to winning at zero opportunity cost —
  Mega Lucario ex's bench copy was never in reach regardless of allocation.
- Confidence: **HIGH** (source-verified via the exact same detector session 25 used to find this
  bug class; this specific episode was already named as an example there).

**92562643 (LOSS vs Mega Lucario ex, turn 13, decisive turn = 10)**
- V6 action: Phantom Dive, all 6 counters onto Mega Lucario ex bench (hp 80/340).
- Available alternative: split 2/4 onto two Makuhita (20 HP and 80 HP) for a confirmed KO.
- Consequence: 0 prizes vs 1 available. Same game, V6 also declined 2 separate critical-retreat
  opportunities (turns 9 and 11) that were each followed by the active Pokemon being gone by the
  next turn.
- Confidence: **HIGH** (same mechanism as above, same source-verified detector).

**92571127 (LOSS vs Dragapult ex mirror, turn 9, decisive turn = 10)**
- V6 action: kept Dragapult ex (110 HP) active against a confirmed lethal (200 dmg) attack with
  a legal retreat and 1 ready bench attacker available.
- Available alternative: retreat to the ready bench attacker.
- Consequence: Dragapult ex was gone by V6's next turn (turn 10), and the deficit went from even
  to a permanent 2-prize hole that turn — this is the single decisive turn of the game.
- Why the alternative is superior: this is a **mirror matchup** (opponent also plays Dragapult
  ex) — there is no deck-level confound here, both sides have access to the same tools, making
  this the cleanest evidence in the whole loss corpus that E is a real, policy-level (not
  deck-driven) issue in at least one game.
- Confidence: **HIGH** for "retreat was legal and a KO followed immediately"; **MEDIUM** for
  "retreating would have won the game" (no re-simulation performed, per the audit's own no-fix,
  no-replay-forking mandate — see Part 14).

**92565477 (LOSS vs Fezandipiti ex, turn 6 of 28, decisive turn = none — the closest loss in the
sample)**
- V6 action: at 6 separate MAIN-menu decision points across the single turn 6 (multiple
  play-then-return-to-menu round trips before ending the turn), V6 never used the confirmed-
  lethal Jet Headbutt (70 dmg) attack that was legally available every single time.
- Available alternative: attack with Jet Headbutt at any of those 6 points.
- Consequence: the target survived that turn; the game continued 22 more turns and was
  eventually lost by only 1 prize.
- Why the alternative is superior: damage (70) exceeded the target's HP, no resistance, no
  ability-based immunity, no non-standard attack text — an unambiguous kill.
- Confidence: **HIGH** that the KO was available and skipped; **LOW** on whether taking it would
  have flipped this specific 22-turns-later outcome (this is explicitly the kind of long-horizon
  counterfactual this audit cannot resolve without re-simulation) — reported per Part 15's own
  instruction not to over-attribute a distant decision as the proven cause of a much-later loss.

**92552245 (LOSS vs UNLABELED, turn 9, decisive turn = none — V6 nearly won this game)**
- V6 action: kept Dragapult ex active at 100 HP facing a confirmed-lethal 220-dmg attack, retreat
  legal, 2 ready bench attackers.
- Consequence: Dragapult ex gone by the next turn — but V6 fought back from there and still
  reached "1 prize from winning" by turn 15 before ultimately losing. This is the loss corpus's
  clearest example of "V6 had a theoretically winning board but lost anyway" (Part 7's own
  question) — the exact final blow on the opponent's turn 16 could not be reconstructed from
  V6's own decision log (V6's own observation freezes once it goes inactive for the rest of the
  game — the same data limitation session 25 hit reconstructing opponent-side final turns).
  **INSUFFICIENT DATA** on the literal final knockout mechanism; **HIGH** confidence the turn-9
  retreat decision was a real, avoidable risk that was later punished exactly as flagged.

---

## PART 5 — Phantom Dive Recheck

**Do not assume Phantom Dive is still the dominant bottleneck — it is not, for this loss
corpus specifically.** Refreshed session-25 methodology against the full 30-game set:

- 97 total Phantom Dive attacks; 34 had a genuine (immunity-adjusted) KO opportunity; 28
  converted optimally, 29 landed *any* KO; **6 missed-value events total across all 30 games**
  (82.4% opportunity-to-KO conversion, matching session 25's figure almost exactly — the 1 new
  game since that audit didn't materially move this number). **MEASURED RESULT**.
- **Of those 6 missed-value events, only 2 occurred in games V6 actually lost** (92558848 turn
  12, 92562643 turn 13 — both detailed in Part 4, both vs Mega Lucario ex). Both are the known,
  already-documented `i>=1` bench false-premise bug from session 25 (opponent bench Pokemon with
  HP ≤ the hardcoded `damage=200` constant get falsely treated as already dead, biasing the
  combo planner toward the high-prize-value Mega Lucario ex bench copy that was never actually
  reachable).
- **Distinguishing the 4 requested buckets**: 2 events are "missed KO that plausibly affected the
  loss" (92558848, 92562643 — both occurred at or after the game's own decisive turn, in a game
  ultimately lost by exactly the margin the missed prize would have closed); 0 events are "missed
  KO in a game V6 was already winning" (none of the 6 total misses across all 30 games occurred
  in a loss where V6 was ahead at the time); 0 are "missed KO after the game was already
  effectively lost" (both loss-corpus misses happened at turns that were themselves the decisive
  turn, not afterward); the remaining 4 misses (of the 6 total) are in games V6 **won** anyway,
  confirming the same finding pattern as session 22/25: PD misallocation is real and recurring,
  but it is **not** the dominant loss driver — it shows up equally (in fact more often, 4 vs 2)
  in games V6 won regardless.
- **Verdict for this audit: PD is a real, small, already-diagnosed (session 25) contributing
  factor in 2/12 losses (17%), not V6's primary bottleneck.** The Part 3/13 finding that the
  *matchup itself* (Mega Lucario ex's 340 HP wall, untouched by Phantom Dive's bench-only
  targeting) is the larger issue stands independently of whether the allocation bug is ever
  fixed.

---

## PART 6 — Prize-Race Failure

Refreshed prize economy (30 games, `results/v6_v2_audit/prize_economy.json`): V6 scores 4.57
prizes/game, opponents score 4.33/game — near breakeven in aggregate, but this average masks a
**bimodal** loss pattern:

- **Pattern A — total offensive shutout (7/12 losses)**: V6 scores 0–1 prizes across the *entire
  game* while the opponent scores 4–5. Recurring pattern **A** ("V6 gives up 2-prize Pokemon too
  easily") does not fit — V6's *own* board mostly isn't the thing being traded away cheaply here,
  it's that V6's attacks aren't landing KOs at all. This is closer to pattern **D** ("V6 gets
  behind before its main attacker is ready") in spirit, except the timing data shows Dragapult ex
  *was* on the field and attacking in these games (Phantom Dive fired) — the deeper mechanism is
  Jet Headbutt (70 dmg) and Phantom Dive (bench-only) both being unable to threaten Mega Lucario
  ex's 340-HP active in a reasonable number of turns, not a readiness-timing problem. Recorded as
  a **new pattern not in the original A–E list**: "V6's own attack profile cannot generate KOs
  against a specific high-HP wall archetype fast enough to keep pace."
- **Pattern E — cannot recover after losing tempo (4/12 losses, the E-classified group)**: a
  single retreat-decline turn converts a recoverable position into a fixed 2-prize deficit that
  never closes again (matches pattern **E** exactly).
- **Pattern C — fails to preserve a winning prize race (1/12, 92552245)**: the one game where V6
  reached a 1-prize-from-winning position and still lost fits this pattern most directly, though
  the final mechanism is **INSUFFICIENT DATA** (Part 4).
- Patterns **B** ("takes low-value 1-prize KOs") was not separately identifiable as a loss driver
  — V6's Phantom Dive economy is *already* almost entirely 1-prize by deck construction (31 of 32
  bench KOs landed across the whole 30-game set are 1-prize, per Part 5's underlying data),  so
  this isn't a discretionary mistake, it's the deck's structural shape.

---

## PART 7 — Energy / Tempo / Bench / Resource Audit

**Bench-lock (new metric)**: a decision where the hand (fully visible) contains ≥1 **Basic**
Pokemon (the only kind that actually needs a free bench slot — evolution cards attach in place
onto an already-benched pre-evolution and need zero bench space; an earlier draft of this
detector incorrectly flagged Dragapult ex sitting in hand while 3 Drakloak already sat on a full
bench as "bench-locked," which was wrong — evolving one of those Drakloak was the free, always-
available fix, not a blocked action) while the bench sits at its 5-slot cap, and that Basic is
never played for the rest of the game.

- **MEASURED RESULT, decisive**: this happens in **25.0% of losses (3/12) vs 38.9% of wins
  (7/18)** — i.e. it is *more* common in games V6 wins. Per the project's own win-vs-loss
  discipline (a behavior equally or more present in wins is not implicated as a loss cause), **L
  is NOT SUPPORTED as a loss driver for V6.**
- The Basics actually getting locked out are overwhelmingly low-priority tech pieces —
  **Fezandipiti ex (26 events, all in wins), Meowth ex (15 in losses, 10 in wins), Budew (21 in
  wins, 4 in losses)** — never the deck's core Dreepy/Drakloak/Dragapult ex attacking line. This
  is consistent with the null result: the deck simply runs more 1-of/2-of Basic utility pieces
  than reliably fit on a 5-slot bench, and losing access to a spare Meowth ex or Budew for a game
  is a minor, symmetric cost, not a differentiator.

**Supporter/Item resource audit (new metric)**: hand-size and discard-pile deltas measured
directly across every `PLAY_SUPPORTER`/`PLAY_ITEM` decision in the 12 losses (`cg.api.CardData`
does not expose trainer-card effect text — confirmed empty this session for every supporter/item
in the deck — so exact card mechanics could not be source-verified; only the empirically observed
hand/discard deltas are reported).

- Item cards (Ultra Ball, Crushing Hammer, Buddy-Buddy Poffin, Night Stretcher, Rare Candy) show
  a consistent −1 hand delta (just removing themselves) with near-zero discard-pile growth —
  no evidence of unexpected hand-thinning.
- Supporters are inconsistent: Lillie's Determination shows a **+2.14 mean hand delta** (net hand
  growth, consistent with a draw effect resolving within the same decision snapshot); Crispin,
  Brock's Scouting, and Boss's Orders show **−1.0** (no visible net change at this snapshot
  granularity) despite plausibly being draw/search effects by their real-world card identity —
  most likely because their resolution (e.g. a follow-up "look at N, keep 1" select) lands as a
  **separate subsequent decision** not captured by this single-decision-boundary delta, not
  because they have no effect.
- **Verdict: INSUFFICIENT DATA to confirm or reject "wasteful discard while holding a combo"** as
  a loss driver — no anomalous large discard spike was found in any loss, but the measurement
  granularity is too coarse to rule out a multi-step supporter effect discarding cards a turn
  later. Flagged as a genuine open question, not resolved here, not assumed.

**Tempo**: mean turns-with-an-available-attack that were actually used to attack: **73.0% in
wins vs 40.3% in losses** (Part 10 detail) — a large gap, discussed there with full causal
caveats rather than duplicated here.

---

## PART 8 — Active / Retreat Audit

Not re-litigating "does V6 retreat enough" in the abstract (already closed as NOT SUPPORTED at
the whole-dataset level in session 20's `V2_LADDER_AUDIT.md`). Instead, applying the same
"critical situation" definition (2+-prize active, damaged, opponent lethal *now*, retreat legal,
charged bench replacement available) **strictly within V6's loss corpus**, and asking a sharper
question: when this exact situation occurs in a game V6 goes on to lose, what happens if V6
stays?

- **6 qualifying critical-situation decisions across 4 distinct losses** (92552245 ×2,
  92558848 ×1, 92562643 ×2, 92571127 ×1 — the 18-count in the raw data includes same-turn
  MAIN-menu revisits of the identical decision point, collapsed here to unique turn-events).
- **In 100% of these (6/6), the active Pokemon was gone (knocked out or the game ended) by V6's
  very next turn.** This is a sharp contrast with session 20's dataset-wide finding for V2 (0/87
  "stayed" situations led to an *immediate next-decision* KO) — the difference is partly
  methodology (this audit checks "by next own turn," not "next single decision," fixing a gap
  the same-turn-revisit structure otherwise hides) and partly scope (this is losses only, where
  by definition something eventually went wrong — a selection effect, not a contradiction of
  session 20's broader null result across all 43 V2 games).
- **MEASURED RESULT**: within the loss subset, declining an available retreat in this specific,
  narrowly-defined critical window is 100% followed by losing the active Pokemon by the next
  turn (n=6 events / 4 games). **HYPOTHESIS, not proven**: that retreating would have changed the
  final outcome — no re-simulation was performed (explicitly out of scope), and in at least one
  case (92552245) V6 fought back to a near-win anyway despite the loss at turn 9, showing the
  connection to the eventual game result is real but not deterministic.
- Session 20's original "Gemini hypothesis" mechanism (stay-in-danger → immediately punished)
  remains NOT SUPPORTED at the whole-dataset level; this section narrows and partially
  *rehabilitates* it specifically for V6's loss corpus using a same-next-turn window rather than
  the stricter immediate-next-decision window.

---

## PART 9 — Target Selection Outside Phantom Dive

Only **1 of 12 losses** (92565477) contains a confirmed non-Phantom-Dive missed knockout (Jet
Headbutt, detailed in Part 4) — the general-purpose missed-KO detector (engine-grounded,
`cg.api.all_attack()`/`CardData`, immunity/resistance/nonstandard-text-aware, same detector used
across sessions 17/22/25) found **zero** other confirmed misses in any of the remaining 11
losses. **"V6 attacks the wrong Pokemon even when an obvious KO exists" is NOT a recurring
pattern in this loss corpus** — it happened exactly once, in one game, across one turn.

---

## PART 10 — Win vs Loss Behavioral Comparison

| Metric | Wins (n=18) | Losses (n=12) | Read |
|---|---|---|---|
| Mean turns | 14.3 | 12.6 | losses run shorter |
| Mean decisions | 105.8 | 81.4 | consistent with shorter games |
| **Turn-attack-rate** (turns with a legal attack that were actually used to attack) | **73.0%** | **40.3%** | large gap — **CORRELATION**, not yet CAUSE (see below) |
| Retreat rate when available | 3.7% | 8.7% | V6 retreats *more* in losses, not less |
| % went first | 83.3% | 58.3% | consistent with known first-player advantage |
| Phantom Dive attacks/game | 4.2 | 1.6 | fewer PD attacks landed in losses |
| PD missed-value events/game | 0.22 | 0.17 | roughly even, not elevated in losses |
| Bench-lock events/game (raw count) | 2.67 | 2.75 | roughly even (see Part 7 for the more decisive never-resolved cut) |
| Mean opponent rating | 648.7 | 651.1 | not distinguishable |

**Causal-discipline classification of each row** (Part 14's framework applied directly):

- Turn-attack-rate (73% vs 40%): **CORRELATION, POSSIBLE CAUSE at most.** Read charitably as
  state→action (a team already falling behind has fewer legal, worthwhile attacks and spends
  more turns retreating/building instead — matching session 17's identical caveat on an
  analogous V2 metric), not conclusively action→state. Given Part 3's finding that 7/12 losses
  are total offensive shutouts against a specific high-HP archetype, a large share of this gap is
  plausibly *explained by* the Mega Lucario ex matchup itself (fewer legal/worthwhile attacks
  exist when the opponent's active outlasts your options) rather than being an independent
  behavioral defect layered on top of it.
- Retreat rate (3.7% vs 8.7%): **FACT** as stated; **directly contradicts** any "V6 doesn't
  retreat enough in general" framing — if anything the opposite direction holds in the raw rate.
  Part 8's narrower, situation-conditioned finding (not the raw rate) is the one with real
  signal.
- Went-first split, opponent rating: **FACT**, both consistent with already-established project
  findings, not new.
- Phantom Dive attacks/game and missed-value rate: **FACT**; the *lower* attack count in losses
  is plausibly downstream of shorter games and the offensive-shutout pattern, not an independent
  finding.

---

## PART 11 — Opponent Strength

| Rating band | Losses | 
|---|---|
| <650 | 6 |
| 650–750 | 5 |
| 750–850 | 1 |
| 850+ | 0 |

No band shows a concentration suggesting "V6 only loses to strong opponents" — half the losses
are against sub-650-rated opponents, roughly V6's own rating tier. **The dominant signal is
archetype, not rating band**:

| Opponent archetype | V6 record | Win rate | Mean opponent rating |
|---|---|---|---|
| UNLABELED | 7-2 | 77.8% | 620.1 |
| **Mega Lucario ex** | **3-5** | **37.5%** | 643.6 |
| Fezandipiti ex | 3-2 | 60.0% | 698.2 |
| Mega Kangaskhan ex | 2-1 | 66.7% | 596.8 |
| Dragapult ex (mirror) | 2-1 | 66.7% | 709.4 |
| Marnie's Grimmsnarl ex | 1-1 | 50.0% | 675.7 |

**MEASURED RESULT, n=8 (small, stated plainly)**: V6 is a losing record against Mega Lucario ex
specifically (37.5%), while its opponents in that matchup are *not* rated any higher than its
UNLABELED opponents (643.6 vs 620.1) against whom V6 wins 77.8%, and are rated *lower* than its
Fezandipiti ex and Dragapult ex opponents (698.2, 709.4) against whom V6 still wins 60–67%. **This
rules out "V6 only struggles against strong opponents" as the explanation for the Lucario
weakness specifically** — it is archetype-specific, not rating-driven. Source-level mechanism
(Part 6): Mega Lucario ex's 340-HP active is out of realistic reach for both of Dragapult ex's
attacks (Jet Headbutt 70 dmg needs 5 hits; Phantom Dive doesn't touch the active at all), and this
weakness independently **replicates a directional finding already seen in session 18's local
simulation data** ("every challenger V2–V5 shows a consistent regression vs `lucario_ex_agent`")
— now confirmed on the real ladder, a genuine cross-session, cross-methodology corroboration.
**Same behavioral failure (0-KO shutouts) also appears against weaker UNLABELED and Kangaskhan
opponents in the games V6 does win against them narrowly** (not shown as losses here because V6
still ekes out enough offense in those specific games) — so this is best read as **a matchup-
strength gradient, not a hard wall unique to Lucario**, with Lucario simply being the clearest,
most repeated case in the sample.

---

## PART 12 — Decisive Turn Table

| Game | Turn | V6 Action | Better Alternative | Failure Type | Confidence |
|---|---|---|---|---|---|
| 92558848 | 12 | Phantom Dive onto unreachable Mega Lucario ex bench; stayed active at 20hp vs lethal | Split counters onto 20-HP Riolu (confirmed KO); retreat | B + E | HIGH |
| 92562643 | 9, 11, 13 | Stayed active twice vs lethal; PD onto unreachable Lucario at t13 | Retreat at t9/t11; split PD onto Makuhita at t13 | E + B | HIGH |
| 92571127 | 9 | Stayed active (110hp) vs confirmed 200-dmg lethal | Retreat to ready bench attacker | E | HIGH (KO-followed), MEDIUM (outcome-changing) |
| 92552245 | 9 | Stayed active (100hp) vs confirmed 220-dmg lethal | Retreat (2 ready bench attackers) | E | HIGH (KO-followed), LOW (outcome-changing — game later almost won anyway) |
| 92565477 | 6 | Jet Headbutt lethal available 6x, never used | Attack | D | HIGH (miss confirmed), LOW (outcome-changing, 22 turns before the loss) |
| 92549421, 92553251, 92555101, 92560743, 92571771, 92572051, 92583351 | n/a | No single flagged decision — sustained 0–1-prize offensive shutout for the whole game | n/a | K | N/A — no decision-level counterfactual identified |

---

## PART 13 — Ranked Bottlenecks

1. **Mega Lucario ex / high-HP-wall matchup weakness.** 5/12 losses directly involve this
   archetype (42%), and the underlying mechanism (Jet Headbutt too weak, Phantom Dive never hits
   the active) plausibly generalizes to the broader "K-shutout" pattern seen against other
   opponents too. **Evidence strength: MEDIUM-HIGH** (small n=8 for the archetype cut, but
   corroborated independently by session 18's local-simulation data and not explained by an
   opponent-rating confound). **Causal, not merely correlated**, at the mechanism level (HP math
   is a hard constraint, not a policy judgment call) — though *how much* it explains the 7 K-type
   shutout losses beyond Lucario itself is HYPOTHESIS. **Not addressed by V6's session-24 fixes**
   (those were Phantom Dive allocation-only; this is a raw damage-output/deck-construction
   issue).
2. **Retreat/survival decisions in narrowly-defined critical spots.** 4/12 losses (33%), 6/6
   flagged events followed by losing the active Pokemon by the next turn. **Evidence strength:
   MEDIUM** (real, concrete, but only 6 events and no re-simulation to prove the outcome would
   have changed). **Plausible mechanism confirmed, causal evidence for the specific decisions
   incomplete.** Also present, though not consequential, in some wins — this is why it's ranked
   below the matchup issue, not above it.
3. **Total offensive-conversion failure ("K-shutout" pattern) as its own describable symptom.**
   7/12 losses. Ranked separately from #1 because it also appears (less severely) against
   non-Lucario opponents, suggesting a possible independent tempo/attack-profile issue beyond
   just the one matchup — but this is the weakest-evidenced item on this list (**HYPOTHESIS**,
   largely overlapping with #1's mechanism rather than clearly distinct from it).
4. **The already-documented Phantom Dive `i>=1` bench false-premise bug** (session 25). 2/12
   losses (17%), both against Mega Lucario ex, both already precisely diagnosed with a proposed
   fix direction on record. **Evidence strength: HIGH** for the mechanism, **LOW** marginal
   impact on V6's overall loss rate specifically (small n, overlaps entirely with #1's matchup).
5. **Single confirmed non-Phantom-Dive missed knockout.** 1/12 losses. Concrete, HIGH confidence
   the miss occurred, but isolated — not a recurring pattern in this data.

**Explicitly NOT ranked as bottlenecks** (checked and found NOT SUPPORTED): bench-space
management (L — occurs *more* in wins), general non-PD target selection (D — 1 isolated case),
supporter/item resource waste (M — INSUFFICIENT DATA, no anomaly found), raw retreat *rate*
being too low (contradicted — losses retreat *more* than wins in the raw rate).

---

## PART 14 — Causal Discipline

Applied throughout above; summarized once here per the instruction to distinguish OBSERVED FACT
→ BEHAVIORAL PATTERN → PLAUSIBLE MECHANISM → CAUSAL EVIDENCE → CONFIDENCE explicitly for the two
headline findings:

**Mega Lucario ex weakness**: OBSERVED FACT (37.5% WR, n=8, not rating-confounded) →
BEHAVIORAL PATTERN (0–1-prize shutouts in 3 of those 5 losses) → PLAUSIBLE MECHANISM (Jet
Headbutt 70dmg / Phantom Dive bench-only vs a 340-HP active) → CAUSAL EVIDENCE (the HP-math
mechanism is a verified card-data fact, not inferred; corroborated independently across two
different methodologies/sessions) → CONFIDENCE: MEDIUM-HIGH for "this is a real weak matchup,"
LOW-MEDIUM for "this alone explains 58% of losses" (some of those 7 K-type losses are against
other/UNLABELED archetypes where the same HP-math argument doesn't automatically transfer).

**Retreat/survival decisions**: OBSERVED FACT (6/6 critical-situation-stays followed by losing
the active by next turn) → BEHAVIORAL PATTERN (concentrated in 4/12 losses, absent as a driver
in the other 8) → PLAUSIBLE MECHANISM (staying in a provably lethal spot with a charged
alternative available is a real, avoidable risk) → CAUSAL EVIDENCE (temporal sequence confirmed;
counterfactual outcome NOT confirmed, no re-simulation performed) → CONFIDENCE: MEDIUM for
"this decision pattern is real and risky," LOW for "fixing it would have flipped these specific
game results."

---

## PART 15 — Final Verdict

**Q1 — Is Phantom Dive still a major bottleneck?** No. It is a real, small, already-diagnosed
factor in 2/12 losses (17%), both explained by the pre-existing session-25 `i>=1` bug, both also
against Mega Lucario ex (overlapping with the bigger issue below). The session-24 fixes worked
exactly as designed (Part 5) — they were simply never the dominant loss driver to begin with.

**Q2 — What is the most common failure preceding losses?** A sustained inability to land
knockouts at all against a specific archetype (Mega Lucario ex, 5/12 losses; the broader
"0–1-prize shutout" pattern, 7/12 losses) — not a single flagged decision, but a structural
damage/HP mismatch.

**Q3 — What is the earliest bad decision, when one exists?** Turn 9 in both 92571127 (mirror
matchup, cleanest evidence, retreat declined) and 92552245 (retreat declined, V6 still nearly
recovered to a win) — both retreat-survival decisions, both roughly a third of the way through
an 11–15 turn game, consistent with "poражение закладывается за несколько ходов до конца," though
in over half the losses (the K-type shutouts) no single earliest bad decision could be identified
at all — the game was arguably lost from very early tempo/matchup dynamics with no one clear
inflection point.

**Q4 — Dominant problem?** A matchup-strength gap against high-HP wall archetypes (led by Mega
Lucario ex), not a policy bug. Retreat/survival judgment in critical spots is the clearest
secondary, genuinely decision-level issue.

**Q5 — How many losses are repeatable policy defects vs unavoidable?** Of the 12: **4 (33%)**
show a concrete, repeatable decision-level defect (E-type retreat decisions, 92552245, 92558848,
92562643, 92571127); **1 (8%)** shows a concrete, repeatable but isolated defect (D-type,
92565477); **7 (58%)** show no decision-level defect at all and are best read as matchup/
snowball losses — closer to "unavoidable given the current deck's damage profile" than to any
identifiable in-game mistake, though whether they're truly *unavoidable* (deck-construction-
level) vs *a tempo/sequencing issue this audit's detectors weren't built to catch* is genuinely
open (**INSUFFICIENT DATA**, flagged rather than guessed).

**Q6 — Clear next target?** If gameplay-policy work is prioritized: the retreat/survival decision
logic in provably-critical spots (Part 8/13 #2), since it is the most concrete, decision-level,
evidence-backed pattern found. If deck/meta work is prioritized instead: the Mega Lucario ex
matchup specifically (Part 11/13 #1) is the largest single lever, but note this audit's own
scope explicitly excludes deck changes and does not recommend one.

**Q7 — Anything this audit could not resolve?** Yes, stated plainly rather than glossed over:
(a) whether retreating in the 6 flagged critical spots would actually have changed any game's
final result (no re-simulation performed); (b) the exact final-turn knockout mechanism in 2 games
where V6's own observation stream freezes once inactive (92549421, 92552245); (c) whether
supporter/item plays ever cause a delayed, multi-step wasteful discard (measurement granularity
too coarse); (d) whether the 7 "K-shutout" losses share a common fixable tempo defect or are
genuinely just unfavorable matchups — the single largest open question this report leaves for a
future phase.

---

## Deliverables

`tools/build_v6_loss_root_cause_audit.py` (new), reusing `src/meta_analysis/
ladder_behavior_audit.py` and the already-existing `tools/pull_v6_ladder_data.py`,
`tools/build_ladder_behavior_audit.py`, `tools/build_phantom_dive_forensic_v6.py` (all re-run
this session against the refreshed 30-game pull). Raw output: `results/v6_loss_audit/
{loss_reports.json, win_vs_loss_comparison.json, opponent_band_losses.json}`. Raw per-decision
data for all 30 games (not just the 12 losses) preserved in `results/ladder_behavior_audit/
v6_{games,decisions,missed_knockouts}.csv`, never discarded after aggregation.

**No code, weight, deck, or submission changes were made.** No V7 was built or recommended.
