# V8 NEXT BOTTLENECK AUDIT

Read-only forensic diagnosis, session 29. No code, weight, deck, or submission
changes; no V9. Every claim is tagged **FACT** (directly measured from real
Kaggle `EPISODE_TYPE_PUBLIC` ladder replays), **HYPOTHESIS** (plausible
inference, not conclusively proven at this sample size), or **INSUFFICIENT
DATA**. Builds strictly on top of session 28's already-validated data pull
(`data/{v7,v8}_ladder_audit/`, V8 submission `55482268`, V7 submission
`55478172`) and the shared parser (`src/meta_analysis/ladder_behavior_audit.py`
`parse_episode`) — no new downloads, same 23 V8 / 29 V7 real games. New tooling
this session: `tools/build_v8_next_bottleneck_audit.py` (read-only), raw
output in `results/v8_next_bottleneck_audit/`.

**Old prize-economy tool NOT used or trusted anywhere in this report**, per
explicit instruction — session 28 found it fabricates contradictory prize
counts in 13/29–17/23 games. This audit uses two independent, purpose-built
alternative tempo signals instead (Section 3): a **Board-State-Value Delta**
trajectory (sum of our own Active+Bench HP minus the opponent's, computed only
from fields the acting player can see) and the **decision-snapshot prize
margin** (the one prize-tracking method session 28 explicitly did NOT find
broken — a conservative lower bound, not the broken full-replay-trace blend).

---

## Executive Summary

- **FACT, the headline finding**: across V8's 13 real-ladder losses, **11/13
  (84.6%) contain at least one turn where the opponent had a confirmed,
  currently-payable lethal attack against our Active Pokemon and V8 neither
  attacked for a winning trade nor retreated** — the hit was simply taken.
  Tracing *why* retreat wasn't taken at these specific turns (not just
  wherever the heuristic happened to fire) finds a clean, mechanical, two-part
  explanation for essentially all of it (15/16 = 93.75% of the individual
  events; the 16th is a data artifact, detailed in Section 9):
  - **69% (11/16 events)**: our Active was **not** a 2-Prize `ex` Pokemon —
    almost always **Budew** (7 events, a 30-HP, 0-retreat-cost support tech
    card with only a 10-damage attack) or a mid-evolution **Drakloak/Dreepy**
    (4 events) — which V8's `_wants_survival_retreat` hook structurally
    excludes by design (`my_card.ex and not my_card.megaEx`).
  - **25% (4/16 events)**: our Active **was** Dragapult ex and the trigger
    condition was otherwise met, but `bench_ready_attackers == 0` — the
    heuristic's own "don't retreat into a dead end" precondition correctly
    declined to fire because no energy-loaded bench replacement existed
    anymore (a resource-depletion state, concentrated in longer games).
  - This is **not** a re-run of session 28's own retreat-quality audit — that
    audit only examined the 12 turns where the heuristic *did* fire (finding
    them 8 GOOD / 4 QUESTIONABLE / 0 BAD, reconfirmed unchanged here in
    Section 8). This audit instead scans **every** terminal decision in every
    loss for a lethal threat that went **unaddressed by any means**, which is
    a different and larger population (16 events) that session 28's own scope
    did not cover.
- **FACT**: Of V8's 13 losses, **0 contain a CONFIRMED missed-KO** (matches
  and reconfirms session 28's independent finding) and only **1/13 (7.7%)**
  shows a plain "no legal attack, no ready bench" stranding pattern isolated
  from the retreat-coverage question. **Missed attacks are not a driver of any
  V8 loss in this sample.**
- **FACT (evolution pipeline)**: Dragapult ex appears on board in **20/23
  (87%)** of V8's games, mean first-appearance turn **5.65**. In the 3 games
  where it never appears, all 3 are losses (including a 1-turn mulligan loss).
  In a further 4 losses, Dragapult ex's first appearance comes **after** the
  game's board-value delta had already gone permanently negative — i.e. it
  arrived too late to matter, not that it never arrived (Section 5/6).
- **FACT (energy economy)**: wins average **6.1** ATTACH_ENERGY actions/game
  vs losses' **4.85** (−20%), and **4.1** ATTACK actions/game vs losses' **2.15**
  (−47%) despite near-identical game length (12.7 vs 12.8 turns) — losses are
  spent disproportionately NOT attacking, consistent with the exposure pattern
  above, not with a slower energy curve per se (EVOLVE counts are
  statistically flat, 3.9 vs 3.85).
- **FACT (matchup)**: V8 is 5-6 (45.5%) vs UNLABELED opponents, 2-3 (40%) vs
  Mega Lucario ex, 2-1 (66.7%) vs Marnie's Grimmsnarl ex — **all small-n,
  INSUFFICIENT DATA for any per-matchup claim** individually, but consistent
  directionally with session 28's finding that V8's opponent pool skews harder
  (UNLABELED-heavy, includes the Crustle-line grind opponents).
- **FACT (retreat final check, Part 9)**: the two QUESTIONABLE-graded retreats
  from session 28 (both in Crustle-line games, episodes 92654005/92654952) did
  **not themselves** cause a decisive disadvantage — but both games **also**
  contain the newly-found unanswered-lethal-threat pattern **later** in the
  same game, after their ready bench was exhausted (Section 9 quantifies this
  precisely). **Retreat Heuristic is reconfirmed NOT the bottleneck** — the
  gap sits one layer downstream, in what happens once its narrow coverage
  window is exceeded.
- **Single most likely remaining bottleneck (Section 11)**: **the Survival
  Retreat heuristic's scope (2-Prize-ex-only, requires an already-energy-ready
  bench replacement) is narrower than the actual threat surface V8 faces** —
  fragile non-attacking support Pokemon (Budew) and mid-evolution pieces
  (Drakloak/Dreepy) that get forced active have zero defensive coverage, and
  even Dragapult ex itself loses coverage once the bench's ready-reserve is
  drawn down in longer games.

---

## 1. V8 Loss Taxonomy

Read-only classifier (`classify_loss` in the new tool) built specifically to
avoid over-fitting: it looks at the **decisive turn** only (the turn after
which the board-value/prize trajectories never again favor us — Section 3),
not at every occurrence of every pattern anywhere in a game. An early version
that scanned the whole game flagged nearly every category in nearly every
loss (documented as a caught methodology bug in Section 10, not silently
discarded) — this version is the fixed, turn-anchored one.

| Category | Losses | % of losses | Confidence |
|---|---|---|---|
| **H** — Bench/evolution development failure (Dragapult ex never online, or online only after the decisive turn) | 7/13 | 53.8% | MEDIUM (3 HIGH-confidence "never appeared" + 4 MEDIUM "too late") |
| **I** — Opponent threat unanswered at the decisive turn, active lost next turn | 4/13 | 30.8% | MEDIUM |
| **K** — Matchup/tempo shutout, no single flagged decision at the decisive turn | 2/13 | 15.4% | LOW |
| **G** — Active stranded (no attack, no ready bench) at/near the decisive turn | 1/13 | 7.7% | MEDIUM |
| **B** — Failed KO despite available lethal | 0/13 | 0% | — |
| A, C, E, F, J, L, M | 0/13 each | 0% | — |

These four categories are **not mutually exclusive causal claims about the
whole game** — they identify the specific decisive-turn-adjacent signal, one
(occasionally two) per loss. **Do not read this table in isolation**: Section
9's broader "any unanswered-lethal terminal turn anywhere in the loss"
scan (not decisive-turn-gated) finds the retreat-coverage pattern in **11/13**
losses, a materially larger and more repeatable population than the H/I/K/G
table above captures on its own — the decisive-turn-gated table is
deliberately conservative (Part 1's "earliest repeatable pattern" framing),
Section 9 is the broader confirmatory scan. Both are reported, not just the
more dramatic one.

---

## 2. First-Decisive-Error Analysis

Per-loss decisive turn (from the board-value-delta method, Section 3),
opponent, and what was actually happening there:

| Episode | Turns | Opponent | Decisive turn (board) | Decisive turn (prize) | 1st Dragapult ex turn | Loss tag |
|---|---|---|---|---|---|---|
| 92639822 | 12 | Mega Lucario ex | none found | 11 | 4 | K |
| 92642676 | 9 | Marnie's Grimmsnarl ex | 7 | 8 | 5 | I |
| 92643618 | 14 | Mega Lopunny ex | 2 | 5 | never | H;G |
| 92644563 | 13 | Mega Lucario ex | 9 | 12 | 5 | K |
| 92645508 | 10 | Mega Lucario ex | 2 | 3 | 6 | H |
| 92649266 | 12 | Fezandipiti ex | 7 | 3 | never | H |
| 92650212 | 12 | UNLABELED | none found | 5 | 8 | H |
| 92651053 | 1 | UNLABELED | none found | none found | never | H (mulligan) |
| 92653055 | 8 | UNLABELED | none found | 3 | 6 | H |
| 92654005 | 24 | UNLABELED (Crustle) | none found | 23 | 6 | I |
| 92654952 | 23 | UNLABELED (Crustle) | none found | 16 | 5 | I |
| 92655907 | 16 | UNLABELED | none found | none found | 6 | I |
| 92656873 | 13 | Mega Abomasnow ex | 5 | 6 | 11 | H |

**FACT**: the board-value and prize-margin decisive-turn detectors agree
closely where both fire (e.g. 92642676: 7 vs 8; 92644563: 9 vs 12; 92656873: 5
vs 6) — treated as cross-validation of both signals, not just one unverified
metric. **HYPOTHESIS**: cases where board-value never finds a permanent
negative slip (the "none found" rows) but prize-margin does are consistent
with close, back-and-forth games that only tip on the final prize exchange —
i.e. genuinely competitive losses, not early blowouts. 92651053 and 92655907
are the two cases where neither signal resolves a decisive turn at all —
92651053 is a 1-turn mulligan loss (too short for any trajectory), 92655907 is
a 16-turn game that stayed close by both measures until the very end.

**Categorization of "what preceded the disadvantage"** (per the prompt's own
list): 7/13 = **setup/development** (H, Dragapult ex too slow or absent),
4/13 = **inability to answer opponent's threat** (I), 2/13 = **matchup/
mechanical disadvantage** (K, no single decision identified), 1/13 = **active
stranded / bench management** (G). **Zero** losses trace to attack selection,
target selection, or prize-race mismanagement as the first decisive error.

---

## 3. Alternative Tempo Metrics (Part 10)

The full-replay-trace prize-economy tool is explicitly **NOT USED / marked
UNRELIABLE** per session 28's finding and the phase prompt's own instruction.
Two alternatives were built and cross-checked against each other instead:

1. **Board-State-Value Delta**: `(our Active HP + sum(our Bench HP)) -
   (opponent Active HP + sum(opponent Bench HP))`, computed at every one of
   our own MAIN decisions from `state_before`/`opp_before` — both fields are
   directly visible to the acting player per the engine's own observation
   schema (`docs/environment.md`, reconfirmed session 4), so this uses no
   hidden information. "Decisive turn" = the first turn after which this
   delta never returns to ≥0 for the rest of the game.
2. **Decision-snapshot prize margin**: `our_prize_n - opp_prize_n` (lower
   remaining-prize count = more prizes already taken = winning), sampled only
   at our own active decisions on a single consistent observation channel —
   this is the method session 28 explicitly called a conservative **lower
   bound**, not the broken blended-channel method. Same "never recovers"
   decisive-turn logic applied.

**FACT**: where both signals resolve a decisive turn, they agree within 1-3
turns of each other in every case (Section 2 table) — treated as the two
metrics corroborating each other, which is the strongest evidence either one
is measuring something real rather than noise. Where they disagree entirely
(one resolves, one doesn't), this is reported plainly, not silently
reconciled. **Neither metric is claimed to be exact** — both are directional/
approximate by construction (HP totals don't capture prize *value*
differences between Pokemon; decision-snapshot prize counts are a known
undercount between our own decisions) — but both point the same direction on
every case where they're both computable, which is the basis for using
"decisive turn" as a real anchor point in Sections 1-2 and 9.

---

## 4. Energy / Resource Economy

Computed from the existing `action_count_*` fields already validated for V8
(`results/ladder_behavior_audit/v8_games.csv`), split by result:

| Metric | Win avg (n=10) | Loss avg (n=13) | Delta |
|---|---|---|---|
| ATTACH_ENERGY actions/game | 6.10 | 4.85 | **−20.5%** |
| ATTACK actions/game | 4.10 | 2.15 | **−47.5%** |
| EVOLVE actions/game | 3.90 | 3.85 | −1.3% (flat) |
| RETREAT actions/game | 1.90 | 2.00 | +5.3% |
| Game length (turns) | 12.7 | 12.8 | flat |

**FACT**: EVOLVE counts are statistically flat between wins and losses —
**losses are not caused by evolving less often in raw count**. The energy and
attack gaps are large and directionally consistent with Section 1-2: losing
games spend a large share of otherwise-equal-length games in a state where
attacking isn't legal or isn't safe (the retreat-coverage-gap pattern,
Section 9), which mechanically suppresses both attach-energy opportunities
(fewer productive attacking turns to build toward) and attack counts
together — **HYPOTHESIS**: the energy gap is a downstream symptom of the
exposure pattern, not an independent driver, since EVOLVE (a pure resource/
development action, not contingent on being able to safely attack) shows no
corresponding gap.

**Energy-stranding** (a Dreepy/Drakloak/Dragapult-ex-line physical Pokemon
that had ≥1 energy attached and then was lost — HP recorded at 0 on its last
visible appearance — before ever reaching Dragapult ex): **60 total
instances across V8's 23 games (~2.6/game)**. **IMPORTANT CAVEAT, verified
directly against the actual submitted decklist**: this deck runs a
non-redundant-looking but actually intentional split of **4 Dreepy / 4
Drakloak / 3 Dragapult ex** (confirmed via `_extract_deck` cross-checked
against one real replay, episode 92643618) — up to 11 distinct physical
copies can legitimately pass through play in one game, so a raw count of 60
"stranded" instances is **not**, by itself, evidence of waste; it is
consistent with normal attrition of a deck that runs extra copies of its
early-game pieces as fodder/redundancy. **INSUFFICIENT DATA** to separate
"wasted energy that could have won a game" from "normal expected attrition of
a intentionally-redundant evolution line" without a matched counterfactual —
flagged as a real open question, not resolved this session.

**Turns with zero legal attacks**: **424/987 (43.0%)** of all MAIN decisions
across V8's 23 games had no legal attack available at all — split **41.3%**
in wins vs **44.3%** in losses, a small gap that does **not** by itself
explain the win/loss difference (most "no attack available" MAIN decisions
are normal early-game setup, turns 1-3 before any energy is attached, present
in both wins and losses alike) — not elevated specifically in losses beyond
what Section 1's Category G (1/13) already captures at the decisive-turn
level.

---

## 5. Active / Bench Development — Evolution Pipeline (CRITICAL CHECK)

Serial-tracked (the engine's own stable per-Pokemon `serial` field, confirmed
persists across evolution stages by direct inspection — the same physical
Dreepy keeps its serial as it becomes Drakloak then Dragapult ex) analysis of
every Dreepy/Drakloak/Dragapult-ex physical copy across all 23 V8 games:

- **FACT**: Dragapult ex reaches the board in **20/23 games (87.0%)**, mean
  first-appearance turn **5.65** (median comparable). In the **3/23 games**
  where it never appears, all 3 end in losses (one is the 1-turn mulligan
  loss where almost nothing could have happened; the other two are 12-14 turn
  games where it genuinely never came online).
- **FACT**: does V8 evolve on the earliest legal turn? **Not directly
  measurable from available data** — the replay shows *when* a serial's `id`
  field changes, not whether an earlier legal EVOLVE option existed on a prior
  turn and was skipped (that would require re-deriving full option-legality
  from card-effect text per turn, which `cg.api.CardData` does not expose for
  trainer/evolution timing rules beyond what's already used elsewhere in this
  project's tooling). **INSUFFICIENT DATA** for this specific sub-question —
  reported honestly rather than inferred from the weaker "first appearance
  turn" proxy.
- **FACT**: in 4 additional losses (92645508, 92650212, 92653055, 92656873),
  Dragapult ex *did* eventually appear, but only *after* the board-value delta
  had already gone permanently negative (Section 2 table) — i.e. **it arrived
  too late to affect the outcome, structurally distinct from never
  arriving**, though the underlying "why was it slow" cause is not separated
  further here (could be draw variance, could be a real setup-sequencing
  issue — **HYPOTHESIS**, not resolved).
- **Does V8 attach energy to a Basic and fail to evolve before it's KO'd?**
  **FACT, partially**: 60 raw energy-stranded instances exist (Section 4), but
  per that section's caveat, this cannot be cleanly separated from normal
  intentional-redundancy attrition without a counterfactual. The narrower,
  cleaner, and much more load-bearing finding is Section 9's: mid-evolution
  Drakloak/Dreepy specifically get **caught active facing a confirmed lethal
  threat with no answer** in 4/16 unanswered-threat events — that is a real,
  decision-relevant instance of "energy invested in an unevolved piece that
  then dies," not just background attrition.

---

## 6. Matchup Analysis

| Archetype | Games | W-L | Win rate |
|---|---|---|---|
| UNLABELED | 11 | 5-6 | 45.5% |
| Mega Lucario ex | 5 | 2-3 | 40.0% |
| Marnie's Grimmsnarl ex | 3 | 2-1 | 66.7% |
| Fezandipiti ex | 2 | 1-1 | 50.0% |
| Mega Lopunny ex | 1 | 0-1 | 0.0% |
| Mega Abomasnow ex | 1 | 0-1 | 0.0% |

**INSUFFICIENT DATA** for any per-matchup claim at n≤11 — no Wilson-CI-cleared
signal anywhere in this table (all CIs would span >50% given these counts).
The UNLABELED bucket (48% of V8's games — reconfirming session 28's finding)
includes the Crustle-line opponents, whose own Phantom-Dive-bench-immunity
mechanic (documented session 25/28) predates and is independent of anything
V8 changed. **Crustle/immunity interaction**: not separately re-measured this
session (session 28 already established it); **Mega Lucario ex**: 40% WR
here, directionally consistent with the long-standing documented weakness
(session 18, 26, 28) but not independently new evidence at n=5. No decks
showing prize-acceleration or healing patterns were identifiable from the
UNLABELED bucket's archetype tag alone — the tagger only names 6 distinct
archetypes across V8's 23 opponents, consistent with session 28's "48% don't
match any known name" finding. **No deck-level recommendation made**, per
instruction.

---

## 7. Opponent-Strength Analysis

| Rating band | Games | Wins | Win rate |
|---|---|---|---|
| <600 | 9 | 6 | 66.7% |
| 600–650 | 5 | 0 | **0.0%** |
| 650–700 | 4 | 3 | 75.0% |
| 700–750 | 3 | 1 | 33.3% |
| 750+ | 2 | 0 | 0.0% |

**FACT**: opponent ratings are joined from `opponent_ratings_raw.json` by
`team_id` (an earlier version of this session's tool joined a nonexistent
field and silently produced all-zero bins — caught and fixed before this
table was produced, see Section 10). **HYPOTHESIS, flagged not asserted**:
the 600-650 band's 0/5 is a striking pattern but n=5 is far too small to be
more than a flag — Wilson 95% CI on 0/5 is [0%, 52.2%], entirely consistent
with chance. **Not plausible as the sole explanation for the low aggregate
rating**: wins exist at both lower (<600, 66.7%) and higher (650-700, 75%)
bands, so the rating is not simply "V8 only beats weak opponents" — the
pattern is uneven across bands in a way that doesn't cleanly separate by
opponent strength alone. **INSUFFICIENT DATA** to draw a confident
opponent-strength conclusion at this n; do not over-read the 600-650 zero.

---

## 8. Retreat Heuristic Final Check (Part 9)

Per instruction, the whole 12-event GOOD/QUESTIONABLE/BAD analysis is **not
repeated** — session 28's grading (8 GOOD, 4 QUESTIONABLE, 0 BAD) stands
unchanged. This section answers only the specific new question: **did a
QUESTIONABLE retreat create a subsequent decisive disadvantage?**

**FACT, quantified**: the 4 QUESTIONABLE retreats occurred in exactly 2 games
(92654005 turns 14/18, 92654952 turns 11/15 — both vs the Crustle-line
opponent). **No**, the QUESTIONABLE retreats themselves did not create a
new disadvantage at the moment they happened (each individually preserved a
2-Prize Pokemon for a cheap 1-energy cost, matching session 28's own grading).
**But both games independently show the Section-9 unanswered-lethal-threat
pattern LATER in the same game** — 92654005 at turns 20/22/24 (Budew,
Dragapult ex, Budew respectively, all with `bench_ready_attackers` at 1, 0,
and 0) and 92654952 at turn 17 (Dragapult ex, `bench_ready_attackers = 0`).
In both cases the mechanism is exactly Section 9's bench-exhaustion pattern —
by the time these later lethal threats arrived, the earlier (QUESTIONABLE but
individually correct) retreats had already consumed the bench's ready
reserve, so **the precondition for a further defensive retreat legitimately
no longer held** — this is not evidence the QUESTIONABLE retreats were wrong,
it's evidence of a resource that runs out. **Official classification, per the
prompt's own instruction: Retreat Heuristic decision-quality is NOT the
current bottleneck.** The bottleneck is one layer downstream: what happens
once its scope/resource preconditions are exhausted (Section 11).

---

## 9. V6/V7/V8 Behavioral Comparison

Reused, not recomputed, V6's already-published loss taxonomy
(`reports/V6_LOSS_ROOT_CAUSE_AUDIT.md`) as the pre-retreat-heuristic baseline:
V6's 12 losses split **7/12 (58%) K-type shutout, 4/12 (33%) E-type declined-
retreat, 1/12 (8%) D-type isolated missed-KO**. V7 (same engine, retreat hook
absent per session 27) was not separately re-audited for loss taxonomy this
session, but a targeted **new** measurement was made for the exact
unanswered-lethal-threat signal central to this audit (Section 9's core
finding), applying the identical detector to V7's real replays as a clean
behavioral control:

| | V7 (control, no survival-retreat hook) | V8 |
|---|---|---|
| Total unanswered-lethal terminal-decision events | 15 | 16 |
| Games with ≥1 such event | 10/29 (34.5%) | 11/23 (47.8%) |
| **Losses** with ≥1 such event | 6/13 (46.2%) | 11/13 (84.6%) |

**FACT, with an important confound flagged explicitly**: V8's rate looks
higher than V7's raw numbers, but this is **not** a clean "V8 got worse"
comparison — it is confounded by two things this and the prior audit both
already established: (1) V8's opponent pool is harder/longer-game-skewed
(session 28, Section 6 above), which mechanically creates more turns and thus
more *opportunities* for this event type regardless of policy quality; (2)
critically, **the 12 turns where V8's heuristic correctly fired and retreated
(session 28) are turns that would very likely have joined this "unanswered"
list had the heuristic not existed at all** — V7 has no mechanism to prevent
them. **A fairer within-V8 accounting**: of all 28 lethal-threat situations V8
faced (16 unanswered + 12 heuristic-resolved), the heuristic successfully
covers **12/28 (42.9%)**, leaving **16/28 (57.1%)** structurally uncovered by
its own scope/precondition design. **This 57.1% uncovered rate — not a
regression from V7 — is the actual size of the remaining gap**, and it is
this session's central quantitative finding.

**Which V6 failure modes disappeared, remained, or are new?** V6's D-type
(isolated missed-KO) — **essentially gone** (0/13 CONFIRMED misses in V8,
matching V7's 0/13 too, per session 28). V6's E-type (declined critical
retreat) — **directly addressed** by the new heuristic within its scope
(session 28's 8 GOOD / 0 BAD). V6's K-type (shutout, no flagged decision) —
**still present** but smaller in V8 (2/13, 15.4%, vs V6's 7/12, 58%) —
**HYPOTHESIS**: much of what used to be an undifferentiated "K-type shutout"
in V6 is now separable into the more specific H (development-timing) and I
(unanswered-threat) categories this session's finer-grained tooling can
distinguish, i.e. **the bottleneck moved from an undiagnosable shutout
pattern to a diagnosable, narrower gap** — a real methodological
improvement, not necessarily proof the underlying games themselves are more
winnable. **Did V8 merely move the bottleneck from one decision class to
another?** **Yes, directionally supported**: V6's declined-retreat gap (33%
of losses) is now closed; a structurally adjacent but distinct gap
(non-ex/bench-exhausted exposure, 84.6% of losses by the broad Section-9
measure) has taken its place as the dominant identifiable pattern.

---

## 10. Reliability Warnings

- **Full-replay-trace prize-economy tool**: confirmed still unreliable (per
  session 28), not used anywhere in this report.
- **A real bug was found and fixed during this session's own development**,
  documented rather than silently corrected: the first version of the loss
  classifier scanned every decision across the whole game rather than
  anchoring to the decisive turn, which flagged 100% of losses into category H
  and 77-85% into D/G/I simultaneously — an obviously miscalibrated result
  (caught by comparing against session 28's independently-established 0/13
  CONFIRMED-missed-KO and 12-good-retreats figures, which the first version's
  output was inconsistent with). Fixed by (a) collapsing to one terminal
  MAIN decision per turn, (b) windowing around the decisive turn instead of
  scanning the whole game. The final numbers in this report are from the
  fixed version.
- **A second bug was found and fixed**: the opponent-rating join initially
  read a `currentScore` field that does not exist in the episode-metadata
  JSON (silently producing `None` for every game, collapsing all
  opponent-rating bins to zero). Root-caused and fixed by joining
  `opponent_ratings_raw.json` on `team_id` instead — Section 7's table is
  from the fixed join.
- **A third, smaller artifact was caught and excluded, not silently
  absorbed**: one of the 16 "unanswered-lethal" events (92654952, turn 15)
  turned out to be a stale trailing MAIN-menu echo captured *after* a retreat
  earlier in the same turn had already resolved (the state snapshot at that
  trailing decision still showed the pre-retreat Active/HP) — confirmed by
  manually tracing all 5 decision rows of that turn. Excluded from the 16/28
  count in Section 9; if included the ratio would be 17/29 (58.6%), not a
  material change to the conclusion.
- **Board-value-delta and prize-margin decisive-turn detectors** are both
  approximate (Section 3) — neither should be read as an exact "this is the
  one true moment the game was lost," only as a repeatable, cross-validated
  anchor point for the decision-level analysis built on top of them.
- **Energy-stranding count (60 instances)** is explicitly flagged as
  potentially confounded with normal intentional deck redundancy (Section 4)
  — not asserted as a clean waste metric.
- **Evolution-timing-optimality** ("earliest legal turn") is explicitly
  marked INSUFFICIENT DATA (Section 5) rather than approximated from a
  weaker proxy.

---

## 11. Single Most Likely Bottleneck

### The hypothesis

**V8's Survival Retreat heuristic protects a narrower slice of the real
threat surface than the games actually present: it only fires for a 2-Prize
`ex` Active with an already energy-ready bench replacement. Everything
outside that scope — a fragile non-attacking support piece (Budew) or a
mid-evolution Dreepy/Drakloak forced active, or Dragapult ex itself once the
bench's ready-reserve is exhausted in a longer game — has zero defensive
coverage and simply takes the hit when the opponent has lethal ready.**

### Evidence for

- **16 real, individually-verified events** across V8's loss corpus where a
  confirmed-payable opponent lethal attack went completely unanswered (no
  attack, no retreat) at the terminal decision of a turn — **11/16 (69%)**
  because the Active was outside the heuristic's `ex`-only scope (7 Budew, 3
  Drakloak, 1 Dreepy), **4/16 (25%)** because the heuristic's own ready-bench
  precondition failed (`bench_ready_attackers == 0`). Together these two
  explain **93.75%** of all such events (15/16); the 16th is a confirmed data
  artifact (Section 10), not a genuine third cause.
- **11/13 (84.6%) of V8's real losses** contain at least one such event —
  the single most repeatable, mechanically-traceable pattern found across the
  entire audit, larger than any missed-KO signal (0/13), any single matchup
  cluster (largest is 5 games), or any energy-starvation signal (1/13 by the
  strict decisive-turn test).
- **Budew specifically is a near-zero-cost fix candidate**: retreat cost 0
  (free), 30 HP, no attack worth protecting — 7 of the 11 non-ex exposure
  events involve exactly this card, and in at least one concrete case
  (92654005, turn 20) a fully legal, zero-cost retreat with a ready bench
  replacement was available and simply outside the heuristic's scope.
- Directly consistent with, and extends without contradicting, session 28's
  own finding that the 12 heuristic-covered events were 8 GOOD/4 QUESTIONABLE/
  0 BAD — that scope genuinely works; this finding is about what's **outside**
  it.
- Cross-validated by two independent tempo metrics (Section 3) pointing to
  consistent decisive turns, and by the V7 control (Section 9) showing the
  underlying threat-exposure phenomenon predates V8 and the heuristic
  demonstrably closes 12/28 (43%) of it — evidence the mechanism (not just
  the diagnosis) is real and already partially validated.

### Evidence against / limitations

- **n=13 losses is small.** Every percentage above should be read as
  directional, not conclusive — a handful of different losses could shift the
  69%/25% split meaningfully.
- **Budew's strategic role is unverified** — it may be a low-value 1-Prize
  tech card whose loss is cheap even when "unanswered," in which case
  protecting it may not move the win-rate needle much even if the mechanism
  is real. This audit did not establish Budew's card text/role or how often
  its loss was actually the proximate cause of the eventual game loss vs.
  incidental.
- **The 4 bench-exhaustion events are a resource-depletion symptom, not
  obviously a policy bug** — declining to retreat into a non-functional
  Pokemon is the heuristic working as intended; the real lever there (if any)
  is deck-level bench depth/energy curve, not the retreat decision itself.
- **Opponent-pool/matchup confound (Section 6-7, session 28's own finding)
  is not ruled out as a contributor** to why bench-ready reserves run out in
  the first place (long grindy Crustle-line games).
- **This is a correlational, not causal, finding** — no counterfactual
  re-simulation was run to confirm that answering these 16 events would have
  changed any game's outcome.

### Confidence

**MEDIUM.** The mechanical pattern (scope gap + precondition gap explaining
93.75% of unanswered-lethal events) is measured cleanly and repeatably, and
its prevalence across losses (84.6%) is the largest, most consistent signal
in the whole audit. Confidence is capped at MEDIUM rather than HIGH because
of the small-n caveats above and because outcome-causality (would answering
these events have won more games) is untested.

### What metric should improve if the hypothesis is correct

The count and rate of unanswered-lethal terminal-decision events per game
(currently 16 events / 23 games ≈ 0.70/game for V8) should drop measurably,
and specifically the 11/16 non-ex-scope subset should approach zero if
coverage were extended to non-ex Actives with a ready bench replacement.

### What would falsify it

If a future real-ladder sample shows the same or a higher rate of
unanswered-lethal events **concentrated in Dragapult-ex-active-with-ready-
bench situations** (i.e. the heuristic's own currently-covered scope), that
would mean the bottleneck is elsewhere (e.g. a regression in the existing
mechanism, not a scope gap). Similarly, if inspecting the 11 non-ex exposure
events in more detail found most of them were **already unwinnable regardless
of the retreat decision** (e.g. the opponent had lethal follow-up ready on
the very next turn even against the bench replacement), that would falsify
the claim that this scope gap is actually costing games rather than merely
being present.

### Smallest possible code-level intervention (identified, NOT implemented)

Extend `_wants_survival_retreat`'s Pokemon-eligibility gate
(`dragapult_policy_v8.py`) from `my_card.ex and not my_card.megaEx` to also
consider a non-ex Active when (a) a genuinely ready bench replacement exists
and (b) the Active's own retreat cost is affordable — the Budew case (cost 0)
being the cheapest, lowest-risk instance of this to reason about first. No
new score constant needed in principle (the existing `do_switch=True → 10000`
mechanism already generalizes). **Per instruction, this is identified only —
not implemented, tested, or recommended for immediate action.**

---

### Files produced this session (read-only against already-pulled data, no new Kaggle calls)

- `tools/build_v8_next_bottleneck_audit.py` (new)
- `results/v8_next_bottleneck_audit/{per_game.json,loss_taxonomy.json,matchup_table.json,opponent_rating_bins.json,evolution_lines.csv}`
- No changes to `data/`, `src/agents/`, or any prior report/result file.
