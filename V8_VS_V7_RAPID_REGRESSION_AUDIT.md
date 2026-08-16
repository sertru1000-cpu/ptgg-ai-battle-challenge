# V8 vs V7 Rapid Real-Ladder Regression Audit

Forensic diagnosis only. No code, weight, or deck changes. No V9. Every claim below is
tagged **FACT** (directly measured from real Kaggle ladder replays), **HYPOTHESIS**
(plausible but not conclusively proven at this sample size), or **INSUFFICIENT DATA**.

## Executive Summary

- **FACT**: V8's real-ladder rating (569.4, n=23) is lower than V7's (610.3, n=29), but
  the two win-rate Wilson 95% CIs overlap heavily (V7 55.2% [37.5%,71.6%], V8 43.5%
  [25.6%,63.2%]) — the win-rate gap is **not statistically distinguishable** at this
  sample size.
- **FACT**: The new Survival Retreat heuristic is mechanically working exactly as
  designed: it activated on 12/12 (100%) of the turns where its real-replay-reconstructed
  trigger condition held, spread across 9/23 (39.1%) of V8's games. V7, lacking the hook,
  retreated in the equivalent situation only 1/8 eligible turns (12.5%; that single case
  traces to the pre-existing V4/V5 hook, not a new-heuristic control failure).
- **FACT**: V8 did **not** attack less often. Attacks/game (2.90 V7 vs 3.00 V8) and the
  turn-level attack-take-rate when an attack was legally available (54.9% V7 vs 56.7% V8)
  are essentially identical. Retreats/game rose materially (1.34 -> 1.96, +46%), and that
  entire increase is explained by the ~12 new heuristic-caused retreats.
- **FACT**: Phantom Dive KO conversion did **not** regress — it improved from 83.9%
  (26/31, V7) to 96.7% (29/30, V8), small-sample but directionally consistent with all
  three inherited Phantom Dive fixes remaining intact. **NO PHANTOM DIVE REGRESSION
  DETECTED.**
- **FACT (per-instance retreat quality)**: manually inspecting all 12 heuristic-triggered
  retreats, 8 were **GOOD** (correctly dodged a confirmed lethal hit with a real bench
  answer, no follow-up disaster) and 4 were **QUESTIONABLE** (correct in isolation, but
  part of a repeated retreat-and-take-damage-again cycle against one structurally hard
  matchup). **Zero were classified BAD** — no retreat->pass, no retreat into an immediate
  KO anyway, no case where attacking would clearly have been better.
- **HYPOTHESIS**: the games where the heuristic fired skew heavily toward V8's two
  hardest-known matchups (Mega Lucario ex — a weakness already documented in the V6 Loss
  Root-Cause Audit — and a newly-observed Crustle-line opponent). This suggests the
  correlation between "heuristic active" and "loss" (7/9 heuristic-active games were
  losses) is substantially a **matchup-difficulty confound**, not proof the retreat
  decisions themselves caused the losses. Sample is far too small (9 games) to separate
  these cleanly.
- **METHODOLOGY FINDING**: the full-replay-trace prize-economy scan reused verbatim from
  the V2/V6 audits (`build_prize_economy_v2_v6.py`) was found this session to have a real
  bug — cross-observer-channel staleness fabricates contradictory prize counts (e.g. "we
  scored all 6 prizes" on a game we actually lost) in a large fraction of games for both
  V7 and V8. Flagged and worked around (self-view-only reads); the original blended
  numbers **must not be trusted**, including implicitly for any past report that used the
  same script. See Section "Prize Economy" for detail.
- **FACT**: V8 faced a different opponent-pool composition than V7 (48% UNLABELED-archetype
  opponents vs 17% for V7) and a modestly higher mean/median opponent rating (617.5/627.3
  vs 610.9/595.2). This is a real, non-trivial confound on any raw win-rate comparison.
- **Overall diagnosis**: the retreat heuristic is mechanically sound and its individual
  decisions are defensible. The evidence does **not** support "Defensive Retreat broke
  V8's attacking behavior" (attacks unchanged, Phantom Dive unchanged/improved). The
  569 rating is **most parsimoniously explained by small-sample variance plus a harder/
  different opponent pool**, not by a behavioral regression from the retreat heuristic —
  though a modest, unproven contribution from the heuristic interacting badly with two
  specific hard matchups cannot be ruled out at n=23.

---

## 1. Submission Identification

Confirmed live via a direct `competition_submissions()` / `competition_list_episodes()`
Kaggle API check at audit time (not from memory/prior reports), read-only.

| | V7 | V8 |
|---|---|---|
| Submission ID | 55478172 | 55482268 |
| File | `challenger_v7_20260813T082207Z.tar.gz` | `challenger_v8_20260813T115034Z.tar.gz` |
| Submitted (UTC) | 2026-08-13T08:24:09Z | 2026-08-13T11:50:59Z |
| Current public score (rating) | 610.3 | 569.4 |
| Real `EPISODE_TYPE_PUBLIC` games | 29 | 23 |
| Wins / Losses | 16 / 13 | 10 / 13 |
| Win rate (Wilson 95% CI) | 55.2% [37.5%, 71.6%] | 43.5% [25.6%, 63.2%] |
| Mean opponent current rating | 610.9 | 617.5 |
| Median opponent current rating | 595.2 | 627.3 |

Both are genuine real-ladder submissions that received real games (well past the ~28-game
floor other agents in this project used for "trust the sample" purposes for V7; V8 is
slightly under that floor at 23 games — treat V8 numbers as preliminary per standing
process rules). V7 is itself **not** a stable/neutral baseline — a prior rapid
crash-diagnosis pass this session found V7 had already dropped sharply from V6's 717.4 to
~594-610, for reasons unrelated to V8 (V7 predates the Survival Retreat heuristic
entirely). This matters: **V7's own rating is already depressed**, so "V8 dropped further
than V7" is a smaller, noisier signal than "V8 dropped from V6," which the prompt did not
ask about but is important context.

## 2. Vital Signs

All figures are per-game means over the full real-game samples (29 V7, 23 V8), computed
via the shared decision-level parser (`src/meta_analysis/ladder_behavior_audit.py`,
identical code path for both).

| Metric | V7 | V8 | Delta |
|---|---|---|---|
| Attacks/game | 2.90 | 3.00 | +0.10 (~+3%) |
| Phantom Dive attacks/game | 2.86 | 3.00 | +0.14 |
| Retreats/game (all sources) | 1.34 | 1.96 | **+0.61 (+46%)** |
| Attach-energy actions/game | 4.97 | 5.39 | +0.43 |
| END/pass actions/game | 0 | 0 | none |
| Game length (turns), mean | 12.1 | 12.8 | +0.7 |
| Turn-level attack-take-rate (attacked when >=1 attack legal that turn) | 54.9% | 56.7% | +1.8pp |
| Turns with attack legally available/game | 5.17 | 5.09 | -0.08 |

**FACT**: Virtually every attack in both versions is Phantom Dive (83/84 total attacks in
V7's sample, 69/69 in V8's) — this deck's only real damage source in these games. Passes
are zero in both — no evidence of retreat-induced "stuck with nothing to do" turns.
**Attacks/game and the turn-level attack-take-rate are statistically indistinguishable
between V7 and V8.** The only vital sign that materially moved is retreats/game, and that
increase is fully accounted for by the new heuristic (Section 3).

## 3. Retreat Heuristic: Did It Actually Activate?

Built a dedicated detector (`tools/build_survival_retreat_activation_audit.py`) that
re-implements `DragapultPolicy._wants_survival_retreat` /
`_bench_pokemon_is_ready` (`src/agents/dragapult_policy_v8.py`) condition-for-condition
against the real per-decision state already extracted from the replays — same 2-Prize-ex
scoping, same visible-energy-only lethal check with attackId 154 (Phantom Dive) excluded
on both sides (reproducing the exact false-positive bug V8's own code deliberately works
around), same count-based (not color-matched) bench-readiness check, same
"don't-flee-a-winning-trade" guard. This is a replay reconstruction, not a re-run of the
live policy — it cannot see the policy's own anti-thrash memory across decisions — but it
gives an accurate independent measurement of when the documented trigger condition held.

Applying the **identical detector** to both V7 and V8's replays (V7 lacks the hook
entirely, so this is a clean behavioral control — "what would have fired had V7 had this
code"), aggregated at **turn level** (a single turn can contain multiple MAIN-menu
decisions before the terminal attack/retreat choice; only the terminal choice of an
eligible turn matters):

| | V7 (control) | V8 |
|---|---|---|
| Turns where the trigger condition held | 8 | 12 |
| ...and the agent retreated | 1 (12.5%) | **12 (100%)** |
| ...and the agent attacked instead | 6 (75%) | 0 |
| ...and neither (other MAIN action chosen, resolved differently) | 1 | 0 |
| Distinct games containing >=1 such retreat | 1/29 (3.4%) | **9/23 (39.1%)** |

**FACT**: The hook fires and wins the score comparison **every single time** its
condition is met in real play (12/12) — fully consistent with the design intent ("RETREAT
scores 10000, always beats this deck's attackId-based ATTACK score"). V7's one control
retreat (episode 92595153) is not evidence of the new hook partially existing in V7 — V7
has no such code path; that single retreat is attributable to the pre-existing V4/V5
`_wants_defensive_retreat` hook, a structurally different (and disjoint-condition) piece
of code. **V8 materially changed retreat behavior — this is directly caused by the new
heuristic, mechanically confirmed, not inferred.**

A useful counterfactual sits in V7's 6 "eligible-but-attacked" control cases: 3 were wins,
3 were losses. One of the 3 losses (episode 92610256, turn 10: our Dragapult ex at 20 HP
facing a confirmed 130-damage lethal attack, attacked anyway) is close to a textbook
example of the exact gap the new heuristic was built to close — V7 had no way to avoid
that hit. That specific failure mode is now covered in V8.

## 4. Retreat Quality: GOOD / QUESTIONABLE / BAD

All 12 heuristic-triggered retreats, inspected individually (opponent, prize value, HP,
opponent's confirmed available attack, retreat cost, energy discarded, replacement
readiness, subsequent outcome):

| Episode | Turn | Result | Our Active (HP) | Opp Active (HP) | Opp Lethal Attack | Ready Bench | Verdict |
|---|---|---|---|---|---|---|---|
| 92639822 | 10 | LOSS (margin 1, close) | Dragapult ex (60) | Mega Lucario ex (140) | Aura Jab 130 | 1 | **GOOD** |
| 92642676 | 7 | LOSS (margin 2) | Dragapult ex (120) | Grimmsnarl ex (320) | Shadow Bullet 180 | 2 | **GOOD** |
| 92644563 | 9 | LOSS (margin 2) | Dragapult ex (30) | Mega Lucario ex (340) | Aura Jab 130 | 1 | **GOOD** |
| 92645508 | 8 | LOSS (margin 4) | Dragapult ex (50) | Mega Lucario ex (360) | Aura Jab 130 | 1 | **GOOD** |
| 92654005 | 14 | LOSS (margin 2, 24-turn grind) | Dragapult ex (80) | Crustle (110) | Superb Scissors 120 | 2 | **QUESTIONABLE** |
| 92654005 | 18 | LOSS (same game) | Dragapult ex (80) | Crustle (170) | Superb Scissors 120 | 2 | **QUESTIONABLE** |
| 92654952 | 11 | LOSS (margin 3, 23-turn grind) | Dragapult ex (80) | Crustle (130) | Superb Scissors 120 | 1 | **QUESTIONABLE** |
| 92654952 | 15 | LOSS (same game) | Dragapult ex (80) | Crustle (130) | Superb Scissors 120 | 1 | **QUESTIONABLE** |
| 92655907 | 14 | LOSS (margin 0, very close) | Dragapult ex (60) | Mega Starmie ex (270) | Jetting Blow 120 | 1 | **GOOD** |
| 92657829 | 8 | **WIN** | Dragapult ex (140) | Grimmsnarl ex (100) | Shadow Bullet 180 | 1 | **GOOD** |
| 92659740 | 8 | **WIN** | Dragapult ex (140) | Grimmsnarl ex (320) | Shadow Bullet 180 | 2 | **GOOD** |
| 92659740 | 10 | same game | Dragapult ex (140) | Grimmsnarl ex (250) | Shadow Bullet 180 | 2 | **GOOD** |

**Result: 8 GOOD, 4 QUESTIONABLE, 0 BAD.**

Every single retreat correctly avoided a confirmed lethal hit (the attached-energy-based
threat detection never misfired) and always had a genuinely energy-ready bench
replacement (retreat cost was 1 in all 12 cases — cheap). None of the specific failure
patterns the audit asked about were found:

- **RETREAT -> PASS**: 0 occurrences (END/pass rate is 0 in both versions, Section 2).
- **RETREAT -> inability to attack**: 0 — every replacement had >=1 pre-verified ready
  attack.
- **RETREAT -> immediate KO anyway**: 0 — no case where the retreat target died the very
  next opposing turn in a way that made the retreat pointless (would require checking the
  opponent's *hidden* hand/next draw, which is not identifiable from available data, but no
  such pattern appears in the visible-state trace either).
- **RETREAT -> loss of critical energy**: retreat cost was always exactly 1 energy in
  these 12 cases — not the deck's main damage-enabling resource (Phantom Dive's own cost
  is separate and unaffected).
- **RETREAT -> another retreat**: the 4 QUESTIONABLE cases (both Crustle games) do show
  the heuristic firing **twice in the same game** against the same opponent archetype —
  not literally "retreat into another immediate retreat" (there were normal turns of play
  between the two firings), but a real, repeated pattern worth flagging: the deck kept
  bringing a 2-Prize attacker back into range of the same 120-damage attack it could
  neither survive nor (per the established Phantom Dive immunity list, Crustle is
  explicitly self-immune to ex/tera-attacker bench damage) reliably punish. **HYPOTHESIS**:
  this is a genuine matchup-level weakness the retreat heuristic cannot fix by itself
  (it preserves the Pokemon and its prize value each individual time, but does not change
  that the deck has no good answer to Crustle), not a defect in the retreat decision
  itself.

## 5. Critical Test: Did V8 Reduce Attacking?

**FALSIFIED.** Attacks/game (2.90 -> 3.00) and turn-level attack-take-rate (54.9% ->
56.7%) both moved slightly **up**, not down, for V8. Turns with attack available/game are
essentially flat (5.17 -> 5.09). There is no vital-sign evidence that V8 attacks less
often or less efficiently than V7. The retreats added by the new heuristic are additional
actions taken on turns that (per Section 4) were never going to be productive attacking
turns anyway — every one of the 12 was a turn where the opponent had a confirmed lethal
attack ready. **Retreating did not come at the expense of attacking on other turns.**

## 6. Phantom Dive Regression Check

Identical established methodology (immunity rules, allocation-optimality search,
thresholds — byte-for-byte the same code as `build_phantom_dive_forensic_v6.py`,
retargeted) applied to both V7 and V8.

| Metric | V7 | V8 |
|---|---|---|
| Total Phantom Dive attacks | 83 | 69 |
| Events with >=1 KO opportunity (immunity-adjusted) | 31 | 30 |
| KO opportunities converted at optimal prize | 26 | 29 |
| KO opportunities missed | 5 | 1 |
| **Opportunity-to-KO conversion rate** | **83.9%** | **96.7%** |
| Prize value lost to missed KOs | 5 | 1 |

**FACT**: conversion did not regress — it improved (small sample, both versions n<35
opportunities, so treat the magnitude as directional not conclusive). Verified the three
inherited V6/V7 fixes remain structurally intact in V8's source (`dragapult_policy_v8.py`
is explicitly documented and source-confirmed as "V7 + one new hook," and the Step-1
regression fixtures for all three fixes ran 9/9 byte-identical between V7Policy and
V8Policy per the prior session's validation) — no reintroduction of the `hp==10`
anti-pattern, the Active/Bench damage-separation bug, or the old bench-planner bug is
observed in this real-ladder sample either (0 CONFIRMED missed-KO events tied to any of
those three patterns in either version's real games).

**NO PHANTOM DIVE REGRESSION DETECTED.**

## 7. Prize Economy

**Methodology finding (important, read before the numbers):** the full-replay-trace scan
used for the V2/V6 audits (`build_prize_economy_v2_v6.py`, "min-ever-seen prize count
across both observation channels, either channel authoritative") was found this session to
be **unreliable**. Concrete counter-example: V8 episode 92642676 (a confirmed real LOSS,
reward `[-1,1]`) — reading the opponent's prize count via *our own* observation channel
showed it frozen at "3 remaining" for ~50 consecutive replay rows while the opponent's
*own* channel showed it correctly falling 5->2 over the same span. Blending both channels'
"lowest ever seen" fabricated a false "we took all 6 of the opponent's prizes, they took
none of ours" reading on a game we actually lost. This is not an isolated glitch: after
switching to a self-view-only read (each side's prize count taken only from that side's
own channel) and cross-checking every game's derived total against its actual reward,
**13/29 (V7) and 17/23 (V8) games still showed a `we_scored_prizes` vs
`opponent_scored_prizes` value that contradicts the win/loss reward outright** (e.g. a
recorded WIN where `we_scored < opponent_scored`). This means **neither the original nor
the patched full-trace method can be trusted for either version** — the discrepancy is not
V7/V8-specific, so it does not bias the V7-vs-V8 comparison in a known direction, but it
means no "prizes scored/game" number from this family of tooling should be reported as
fact in this or any prior audit that used it. Flagged here per the standing process rule
to report tooling bugs found, not silently patch over them. Root cause not fully
diagnosed within this rapid audit's time budget (best guess: the engine only refreshes a
given player's `observation.current` on that player's own active/decision ticks; the
"current" object read on an *inactive* tick may be end-of-previous-refresh state, not a
live snapshot — this deserves real root-causing before the prize-economy scripts are
trusted again for V2/V6 either).

**What can be trusted**: the decision-snapshot-based prize tracking already embedded in
`parse_episode` (sampled only at our own active decisions, same channel every time, no
cross-observer blending) — this is the same method flagged in session 25 as
*undercounting* opponent KOs between our decisions, so treat it as a conservative lower
bound / directional signal, not an exact count.

| Metric (decision-snapshot, lower-bound) | V7 | V8 |
|---|---|---|
| Max prize deficit faced, mean | 1.79 | 2.65 |
| Max prize deficit faced, median | 1 | 2 |
| Final prize margin, mean (positive = we ended behind) | 0.52 | 0.87 |
| Games reaching a 2+ prize deficit | 14/29 (48.3%) | 19/23 (82.6%) |
| Comeback rate from 2+ deficit | 35.7% (5/14) | 36.8% (7/19) |

**HYPOTHESIS**: V8 fell behind on prizes more often and by more (deficit mean 1.79 ->
2.65) than V7, and ended games further behind on average (0.52 -> 0.87). Given Section 5
shows attacking/Phantom-Dive conversion did **not** get worse, this prize-economy decline
is more consistent with **facing harder matchups more often** (Section 9) than with the
retreat heuristic itself costing prizes. **Did Defensive Retreat preserve prize value, or
just sacrifice tempo?** Neither cleanly — Section 4 shows every individual retreat avoided
losing a 2-Prize Pokemon for a cost of only 1 energy (a real, positive value preservation
per-instance), while Section 5 shows no tempo was sacrificed elsewhere. The *aggregate*
prize-economy decline looks driven by matchup difficulty, not by the retreat mechanism —
but this is **INSUFFICIENT DATA** to fully separate at n=23, especially given the
prize-economy measurement itself is only a lower bound.

## 8. Loss Forensics (all 13 V8 losses)

| Episode | Opponent | Opp. Rating | Turns | Heuristic active? | Max deficit | Final margin |
|---|---|---|---|---|---|---|
| 92639822 | Mega Lucario ex | 708.4 | 12 | Yes (GOOD retreat) | 3 | 1 |
| 92642676 | Marnie's Grimmsnarl ex | 772.0 | 9 | Yes (GOOD retreat) | 2 | 2 |
| 92643618 | Mega Lopunny ex | 663.7 | 14 | No | 5 | 5 |
| 92644563 | Mega Lucario ex | 708.4 | 13 | Yes (GOOD retreat) | 2 | 2 |
| 92645508 | Mega Lucario ex | 620.4 | 10 | Yes (GOOD retreat) | 4 | 4 |
| 92649266 | Fezandipiti ex | 525.9 | 12 | No | 4 | 4 |
| 92650212 | UNLABELED | 761.4 | 12 | No | 4 | 3 |
| 92651053 | UNLABELED | 632.6 | **1** | No | 0 | 0 |
| 92653055 | UNLABELED | 627.3 | 8 | No | 2 | 2 |
| 92654005 | UNLABELED (Crustle) | 646.2 | 24 | Yes x2 (QUESTIONABLE) | 2 | 2 |
| 92654952 | UNLABELED (Crustle) | 570.9 | 23 | Yes x2 (QUESTIONABLE) | 3 | 3 |
| 92655907 | UNLABELED | 610.2 | 16 | Yes (GOOD retreat) | 4 | 0 |
| 92656873 | Mega Abomasnow ex | 520.7 | 13 | No | 5 | 5 |

**FACT**: 7/13 (53.8%) of V8's losses contain a heuristic-triggered retreat; 6/13 do not.
**FACT**: 0/13 losses have a CONFIRMED missed-KO (general or Phantom-Dive-specific) —
this rules out "missed attack" as a driver of any loss in this sample for either version
(V7 also has 0 CONFIRMED missed-KOs in its 13 losses).

Walking each loss for the first clearly consequential decision:

- **92639822, 92642676, 92644563, 92645508, 92655907** (5 losses, all GOOD-graded
  retreats): the retreat was the correct play at the moment it happened (Section 4) and
  the games remained close (margins 1, 2, 2, 4, 0) — consistent with "lost a hard matchup
  despite playing the retreat correctly," not "lost because of the retreat." Four of these
  five are the already-known-weak Mega Lucario ex / Marnie's Grimmsnarl ex matchups.
- **92654005, 92654952** (2 losses, QUESTIONABLE retreats, both vs a Crustle-line
  opponent): the first clearly consequential pattern is not a single bad decision but a
  **repeated cycle** — bring in a fresh 2-Prize attacker, take a ~120-damage hit down to
  80 HP, survival-retreat to save it, repeat. Both games are unusually long (23-24 turns)
  grinds that V8 ultimately lost by a small margin (2-3 prizes). **HYPOTHESIS**: this
  reflects a genuine deck-vs-deck weakness against this specific opponent archetype
  (compounded by Crustle's documented self-immunity to ex/tera-attacker bench damage,
  meaning Phantom Dive itself may be a dead end against it if a Crustle sits on the
  opponent's bench), not a flaw in the retreat decision logic.
- **92643618, 92649266, 92650212, 92653055, 92656873** (5 losses, no heuristic activity):
  unrelated to retreat entirely by definition — the heuristic's trigger condition never
  held in these games. General shutout-style losses (margins 2-5), consistent with
  session 26's previously-documented "K-type" pattern (broad offensive/matchup
  disadvantage with no single flagged decision), now also observed in V8's non-heuristic
  losses.
- **92651053** (1-turn loss): almost certainly an early setup/mulligan-disadvantage loss —
  too short for any MAIN-menu retreat/attack decision to have occurred at all. Unrelated
  to retreat by construction.

**No V8 loss shows a pattern of "declined an available beneficial retreat" (the V7-style
E-type failure session 26 flagged) — that specific old gap appears closed.** The two
QUESTIONABLE-graded losses are the closest thing to a retreat-adjacent negative pattern
found, and even there the individual decisions were locally correct.

## 9. Opponent-Strength Confound

**FACT**: V8 faced a modestly higher mean (617.5 vs 610.9) and notably higher median
(627.3 vs 595.2) opponent rating than V7. More strikingly, the **opponent archetype mix
differs substantially**:

| Archetype | V7 share | V8 share |
|---|---|---|
| UNLABELED | 17.2% (5/29) | 47.8% (11/23) |
| Mega Lucario ex (known weak matchup) | 31.0% (9/29) | 21.7% (5/23) |
| Marnie's Grimmsnarl ex | 10.3% (3/29) | 13.0% (3/23) |
| Dragapult ex mirror | 10.3% (3/29), 0-3 record | 0% (0/23) |
| Fezandipiti ex | 13.8% (4/29) | 8.7% (2/23) |

V8's opponent pool is nearly half UNLABELED-archetype decks (a catch-all bucket the
project's archetype tagger doesn't recognize by name — includes the Crustle-line
opponents from Section 4/8), essentially triple V7's share. This is a real compositional
difference, not just a rating-magnitude one, and the two 24/23-turn Crustle losses
(Section 8) sit inside exactly this bucket. **Do not attribute the full rating gap to the
retreat heuristic** — a meaningfully different opponent pool is a live, evidenced
alternative explanation that these numbers cannot fully separate from the heuristic's own
effect at n=23.

## 10. Statistical Discipline

- Win rate: V7 55.2% [37.5%,71.6%] vs V8 43.5% [25.6%,63.2%] (Wilson 95% CI) — **CIs
  overlap substantially; the win-rate difference is not statistically established.**
- Phantom Dive conversion: V7 26/31 (83.9%) vs V8 29/30 (96.7%) — both very small
  opportunity counts; treat the direction (no regression) as more reliable than the exact
  magnitude.
- Heuristic activation-to-retreat rate: V8 12/12 (100%) vs V7 control 1/8 (12.5%) — this
  one is a large, clean effect size on a moderate n (20 combined eligible turns) and is the
  most statistically solid finding in this audit.
- Retreat quality: 8 GOOD / 4 QUESTIONABLE / 0 BAD out of 12 — full population (not a
  sample), so no CI needed, but n=12 is still small in absolute terms; a few more games
  could shift this picture.
- Prize economy: **INSUFFICIENT DATA** — the primary established measurement tool was
  found broken this session (Section 7); the fallback (decision-snapshot) method is a
  documented undercount, not an exact figure.

## 11. Final Diagnosis

| # | Question | Answer | Classification |
|---|---|---|---|
| Q1 | Did V8 materially change retreat behavior? | Yes — retreats/game +46%, 100% of heuristic-eligible turns resulted in a retreat vs V7's 12.5% control rate | **SUPPORTED** |
| Q2 | Did V8 reduce attacks/game? | No — attacks/game and turn-level attack-take-rate both slightly increased | **FALSIFIED** |
| Q3 | Did V8 increase unnecessary retreats? | No individual retreat was unnecessary (all 12 dodged a confirmed lethal hit); the 4 QUESTIONABLE cases reflect a hard-matchup cycle, not unnecessary/incorrect individual decisions | **NOT SUPPORTED** |
| Q4 | Did V8 create retreat -> pass / retreat loops? | Zero passes in either version; the 2 games with a double-retreat are not literal back-to-back loops (normal play occurred between firings), but do show a repeated symptomatic pattern vs one opponent archetype | **NOT SUPPORTED** (loops); **PARTIALLY SUPPORTED** (repeated-firing pattern exists, is not itself a bug) |
| Q5 | Did V8 sacrifice attack tempo for survival? | No — attack frequency and take-rate are unchanged; every heuristic-triggered retreat occurred on a turn where attacking would not have been the better play (opponent had lethal ready) | **FALSIFIED** |
| Q6 | Did V8 preserve more Prize value? | Each individual retreat preserved a 2-Prize Pokemon for 1 energy (locally yes); in aggregate V8's prize-deficit/margin numbers are worse than V7's, but the primary measurement tool for this is broken (Section 7) and the fallback is a lower bound | **INSUFFICIENT DATA** (aggregate); **SUPPORTED** (per-instance) |
| Q7 | Did V8 change Phantom Dive KO conversion? | Yes, improved (83.9% -> 96.7%), small sample | **SUPPORTED** (direction); magnitude not conclusive |
| Q8 | Did V8 reintroduce any V7 Phantom Dive bug? | No CONFIRMED missed-KOs tied to any of the three known bug patterns in either version's real games; source-level fixes verified intact | **FALSIFIED** |
| Q9 | Is there evidence Defensive Retreat caused the poor V8 rating? | 53.8% of V8's losses contain a heuristic-triggered retreat, and every individual retreat was graded GOOD or QUESTIONABLE (never BAD) — the correlation is real but the same games are dominated by known-hard matchups (Lucario, Crustle-line) where V7-style attacking also loses (V7's own control-case loss to Crustle-line, episode 92596095). No mechanism was found by which the retreat itself (vs. the underlying matchup) caused a loss | **NOT SUPPORTED** as a causal claim; **PARTIALLY SUPPORTED** as a correlation worth continued monitoring |
| Q10 | Is 569 explainable by observed behavior, or still primarily small-sample/opponent-pool? | Vital signs, attack frequency, and Phantom Dive conversion all argue AGAINST a behavioral regression; opponent pool composition (Q9's matchup skew, Section 9's UNLABELED/rating differences) and small n (23 games, below this project's usual ~28-30 floor) are live, evidenced alternative explanations that are not ruled out | **INSUFFICIENT DATA** — leans toward small-sample/opponent-pool over behavioral regression, but not conclusively |

**Bottom line**: the Survival Retreat heuristic works exactly as designed and its
individual decisions are sound (0 BAD out of 12 real activations). No evidence was found
that it reduced attacking, hurt Phantom Dive execution, or caused a loss it wouldn't have
happened anyway given the matchup. The clearest concrete lead for a future (not
this-session) investigation is the Crustle-line matchup, where the deck's core attacker
(Phantom Dive) may be structurally weak (per Crustle's documented ex/tera-attacker bench
immunity) independent of anything V8 changed — that predates and is orthogonal to the
retreat heuristic. The 569 rating sits within a win-rate confidence interval that overlaps
V7's, on a smaller sample facing a measurably different opponent pool; **this audit does
not find behavioral evidence sufficient to call V8 a regression from V7.**

---

### Files produced this session (read-only against Kaggle throughout)

- `tools/pull_v7_v8_regression_data.py` — full replay + opponent-rating pull for both submissions
- `tools/build_phantom_dive_forensic_v7_v8.py` -> `results/phantom_dive_forensic_{v7,v8}/`
- `tools/build_prize_economy_v7_v8.py` -> `results/v7_v8_regression_audit/prize_economy.json` (see Section 7 caveat)
- `tools/build_survival_retreat_activation_audit.py` -> `results/v7_v8_regression_audit/{survival_retreat_activation.json,survival_retreat_events.csv}`
- `tools/build_ladder_behavior_audit.py` extended with `v7`/`v8` targets -> `results/ladder_behavior_audit/{v7,v8}_{games,decisions,missed_knockouts}.csv`
- Raw data: `data/{v7,v8}_ladder_audit/`
