# Competitive V2 Report — Official Data Audit, Search V2, Card/Deck/Meta Discovery

Session 3. Builds on `reports/competitive_v1.md` (session 2) without
repeating completed work. Full supporting detail lives in
`reports/competition_data_audit.md`, `reports/competition_mechanism.md`,
`results/search_v2_audit.md`, `experiments/search_v2_ablation.md`,
`experiments/dragapult_first_variant.md`, `experiments/abomasnow_deck_fix.md`
— this report synthesizes and cross-references them rather than duplicating
their full detail. Tags: **[FACT]** (source/measurement-verified),
**[RESULT]** (a measured experimental outcome), **[HYPOTHESIS]**
(interpretation, not fully isolated), **[QUESTION]** (open).

---

## 1. Competition Data

Full detail: `reports/competition_data_audit.md`. Headlines:

- **[FACT]** The official Data page contains exactly 60 files, unchanged
  since session 1 — nothing new has appeared. No separate restricted card
  list, no bundled decklists beyond the 4 sample-notebook decks, no
  replay/episode files on the Data page itself.
- **[FACT]** Exact card pool, engine-verified: **1267 unique cards** (1056
  Pokemon, 77 Item, 61 Supporter, 27 Tool, 26 Stadium, 12 Special Energy, 8
  Basic Energy; 121 `ex`, 30 `megaEx`, 32 `tera`, 29 `aceSpec`). The 2022-row
  card-data CSVs are a row-per-attack schema over the same 1267 cards, not a
  bigger pool — cross-verified, zero symmetric difference between the CSV's
  card-ID set and the engine's.
- **[FACT]** **`ENGINE CARD POOL` == `COMPETITION-LEGAL CARD POOL`** — read
  directly from `Api.h`'s deck-validation source: only 5 rules are enforced
  (valid ID, ≤1 ACE SPEC, ≤4 copies **per card name** except Basic Energy,
  ≥1 Basic Pokemon, exactly 60 cards). No additional restricted-list check
  exists. **This corrects an unverified, web-research-sourced claim from
  session 1** (`docs/environment.md`) that a separate organizer-restricted
  card list existed.
- **[FACT]** Exactly 4 official rule-based sample decks exist (confirmed
  against both the local notebooks and the live Data-page listing) — no 5th
  archetype anywhere in the official materials.
- **[FACT]** Official daily episode-replay exports exist, are organizer-
  sanctioned explicitly "to help BC/RL/IL", span 2026-06-16 through
  2026-08-10 (56 days, CC0 license, ~4,500-7,800 episodes/day). Only the
  tiny (2KB) index/manifest was pulled this session — the ~40GB+ of raw
  episodes were not downloaded, a scope/time decision, not an access
  barrier.
- **[FACT]** A community dataset (`busyaprime/pokemon-tcg-ai-battle-live-
  meta`, CC BY 4.0, attributed throughout this project) gives a 2026-07-31
  snapshot of the real live-ladder meta — see §6.

---

## 2. Competition Mechanism

Full detail: `reports/competition_mechanism.md`. Headlines:

- **[FACT]** Bayesian skill rating, N(μ,σ²), μ0=600, matchmaking prefers
  similar-rated opponents, **margin of victory does not affect rating
  updates** — only win/draw/loss.
- **[FACT]** Only the latest 2 submissions are used for final judging, but
  *every* submitted agent keeps playing episodes until the competition ends.
- **[FACT]** No ingress/egress during evaluation — no live external calls
  allowed at inference time. No Private Leaderboard — the live rating *is*
  the score.
- **[FACT]** Submissions lock 2026-08-16, but games continue ~2 more weeks
  (to ~08-31) for rating convergence before the leaderboard is truly final.
- **[FACT]** 6,715 teams entered Simulation (vs. 341 in Strategy) — a very
  large, saturated field. Simulation reward is "Knowledge" (no cash); the
  linked Strategy track carries a $240,000 prize pool.
- **[FACT]** Organizers explicitly confirmed (competition forum, quoted in
  full in `competition_mechanism.md`) 3 specific simulator-vs-real-TCG rule
  deviations, all judged low-impact by them; "the simulator behavior will be
  treated as the correct behavior."

---

## 3. Search V2

Full detail: `results/search_v2_audit.md`, `experiments/search_v2_ablation.md`.

- **[FACT]** Search V1's regression (Competitive V1) was source-verified
  this session, not just inferred: Dragapult's Phantom Dive and Lucario's
  Aura Jab both trigger genuine linked follow-up selects
  (`SelectContext.DamageCounter`, `SelectContext.SelectAttachTo`) confirmed
  directly in `EffectInstant.h`/`CreateCard.h`, both addressed back to the
  attacking player. V1 evaluated the state after only the first select —
  an artificial intermediate state, exactly as the governing prompt
  hypothesized.
- **[RESULT]** Search V2 (`src/agents/search_lookahead_v2.py`) resolves the
  full same-player decision chain (driven by the real heuristic on each
  hypothetical sub-decision, stopping only when control passes to the
  opponent or the game ends) — mechanically verified correct: 0 search
  failures, 0 chain-length-cap hits, sensible 2-9 step chains, across 7000
  ablation games. A real implementation bug (reusing the root search's ID
  instead of chaining off each step's own returned ID) was found and fixed
  during development.
- **[RESULT]** Despite the fix being mechanically correct, Search V2 is
  **significantly WORSE** than the heuristic baseline in 6 of 7 matchups
  tested (z=-4.19 to -8.49, effect sizes -12pp to -27pp, n=500/condition):

| Matchup | Heuristic | Search V2 | z | Verdict |
|---|---|---|---|---|
| dragapult vs iono | 66.2% | 39.4% | -8.49 | significant, much worse |
| dragapult vs lucario | 49.0% | 32.6% | -5.28 | significant, worse |
| dragapult vs abomasnow | 57.4% | 43.4% | -4.43 | significant, worse |
| dragapult vs random | 97.4% | 96.2% | -1.08 | not significant |
| lucario vs iono | 78.4% | 65.8% | -4.44 | significant, worse |
| lucario vs dragapult | 53.0% | 39.8% | -4.19 | significant, worse |
| lucario vs random | 95.6% | 98.0% | +2.16 | significant, better (sanity-check only) |

- **[HYPOTHESIS]**: the (deliberately unchanged from V1) evaluation function
  — prize race + HP differential + bench-count differential — is too crude
  relative to the heuristics' own hand-tuned attack logic (KO-immunity
  checks, prize-count thresholds, multi-turn plan continuity) for exactly
  the decision class Search V2 targets. The chain-completion fix removed
  one real source of error but left a larger evaluation-quality gap in
  place.
- **[RESULT]** Runtime is not the constraint: 0.04-0.16s/game average, no
  threat to the 10-minute/match budget even in decision-rich matchups.
- **[RESULT]** Search changed the heuristic's own choice 55-92% of the time
  it engaged; a first pass at decision-level analysis (Part A9) found no
  simple "search only sabotages losses" pattern (changed-decision density
  was actually slightly *higher* in games Dragapult won than lost, vs.
  Iono) — flagged as a nuance, not further isolated causally this session.
- **[Promotion decision]: Search V2 is NOT promoted.** `BEST_AGENT` remains
  `dragapult_fix_v1` / `lucario_ex_agent`. This is treated as intended — a
  valid, evidence-based negative result, not a failure of the exercise.

---

## 4. Current Best Agent

Unchanged from Competitive V1, re-confirmed (not re-litigated) this session:

- **Best practical agent**: `dragapult_agent_always_first` (`dragapult_fix_v1`)
  — recommended default for submission.
- **Best statistically supported**: `dragapult_fix_v1` and `lucario_ex_agent`
  remain **statistically tied** (Competitive V1's formal matrix, z=-0.78
  aggregate, z=-1.77 head-to-head — neither significant). This session's
  Search V2 ablation, run against both as base heuristics, did not surface
  any new evidence favoring one over the other (both suffered similar-
  magnitude regressions under Search V2, both remain strong under
  heuristic-only play).
- **Best agent/deck combination**: unchanged — each heuristic is tightly
  coupled to its own deck's card IDs; agent and deck are not independently
  swappable in the current architecture (see §5).
- **[FACT, explicit anti-overfitting caveat]**: all of the above describes
  relative performance *within our local 4-deck pool*. §6 below shows this
  pool overlaps the real ladder meta by exactly one deck (Dragapult ex) —
  "best agent in our local benchmark" is not interchangeable with "best
  agent for the real leaderboard."

---

## 5. Deck Research

- **[FACT] Part B.1 (validator)**: `tools/deck_validator.py` — a minimal
  wrapper around `battle_start` (the actual authoritative legality check,
  per §1) that reports legal/illegal + reason for any 60-card list. Smoke-
  tested against 2 existing decks, both correctly reported legal. Per
  instruction, this is deliberately the smallest reliable validator, not a
  deck-generation or optimization tool.
- **[RESULT] Part B.2 (small deck probe)**: rather than construct a new
  probe from scratch this session, the qualifying "small number of
  controlled variants" experiment already exists from Competitive V1:
  `experiments/abomasnow_deck_fix.md` (notebook-faithful `decks/
  abomasnow_ex_corrected_v1.csv` vs. the original `decks/abomasnow_ex.csv`,
  same heuristic, n=300/opponent). Result: directionally positive in all 3
  opponents tested (+1.5pp to +3.2pp) but not statistically significant at
  that sample size (all |z|<1.5). **Answer to Part B.2's actual question**
  ("does deck variation produce a meaningful performance effect?"): **plausibly
  yes, but not conclusively demonstrated yet** — the effect size measured
  is small and the sample too limited to be sure it's real rather than
  noise.
- **[HYPOTHESIS]**: a new, dedicated small-variant probe on the current
  Tier-1 decks (Dragapult, Lucario) was considered but not run this
  session. Both were already found notebook-faithful (Competitive V1 Phase
  3; this session's Search V2 audit Part A2) — deliberately modifying an
  already-faithful decklist would need its own hypothesis-driven rationale
  that this session's evidence doesn't yet supply. §6's meta-comparison
  finding (only Dragapult ex overlaps the real ladder's known archetypes)
  is a substantially higher-value lead for future deck research than
  further tweaking an already-correct decklist — see §8.
- **[HYPOTHESIS]**: whether deck optimization deserves more resources — the
  honest answer given current evidence is "plausibly, but not yet proven
  more valuable than other open directions" — see the leaderboard-strategy
  ranking (§8), which ranks meta-aware deck selection above blind local
  deck tweaking specifically because of the meta-overlap finding in §6.

---

## 6. Meta Research

**[FACT]** Meta/replay data **does exist** and **is usable** — see §1 and
`reports/competition_data_audit.md` §5 for the full available/accessible/
usable/competitively-useful breakdown. Analyzed the community meta
snapshot (`busyaprime/pokemon-tcg-ai-battle-live-meta`, CC BY 4.0, snapshot
date 2026-07-31, copied to `strategy/meta_analysis/live_meta_snapshot_2026-
07-31/`) in full:

**[RESULT]** 8 named archetypes were active on the real live ladder as of
2026-07-31: Marnie's Grimmsnarl ex (63.8% of tracked games — dominant by
usage share), Mega Kangaskhan ex, Fezandipiti ex, Cynthia's Garchomp ex,
Dragapult ex, Teal Mask Ogerpon ex, Mega Lopunny ex, Team Rocket's Mewtwo ex.

**[RESULT]** **Only 1 of these 8 (Dragapult ex) overlaps with our local
4-deck pool.** Abomasnow ex, Iono's, and Mega Lucario ex — 3 of our 4
locally-benchmarked decks — do not appear at all in the tracked live-ladder
archetype list. This is the single most important finding of this session
for calibrating confidence in the local benchmark's relevance.

**[RESULT]** On the live ladder, "Dragapult ex" (as an archetype label —
not necessarily our exact decklist/heuristic) shows a **59.2% win rate**
(95% CI [52.3%, 65.8%], n=201 games) and only 2.6% usage share — i.e. a
rare but strong archetype in the real meta, consistent in direction with
this project's own local finding that Dragapult (with the first-player fix)
is a Tier-1 performer. This is corroborating, not proof — the live number
reflects real opponents' Dragapult implementations, decks, and skill,
not necessarily this project's own port.

**[RESULT]** The live matchup grid shows real non-transitivity too (e.g.
Marnie's Grimmsnarl ex is favored 53% vs. Mega Kangaskhan ex, but Mega
Kangaskhan ex is favored 78.8% vs. Mega Lopunny ex, and Mega Lopunny ex is
favored 58.7% vs. Marnie's Grimmsnarl ex — a real rock-paper-scissors
triangle in the actual live meta, structurally the same kind of
non-transitive dynamic already found locally in Competitive V1 §5).

**[Part C — opponent-archetype-inference feasibility]**: **[FACT]** (from
the already-verified API structure, not new code this session):
`PlayerState.hand` is hidden for the opponent, but `PlayerState.active` and
`.bench` are real, fully-typed Pokemon objects for **both** players once
revealed (only face-down during the brief simultaneous-setup window) — i.e.
**opponent Pokemon species become visible almost immediately (from turn 1
onward)**, well before hand/deck contents ever would be. **[FACT]**: the EN
Card Data.csv's "Category" field shows many competition Pokemon are
explicitly named/branded per-Trainer (e.g. "Trainer's Pokemon(Iono)",
"Trainer's Pokemon(Marnie)" — matching the live meta's own "Marnie's
Grimmsnarl ex" naming) — meaning a single early-revealed Pokemon ID can be a
strong, sometimes unique, archetype signal. **[HYPOTHESIS]**: this makes
opponent-archetype classification from observable state plausible in
principle — the signal likely exists and would be cheap to read (no hidden-
info access needed). **Not implemented this session** (no classifier was
built), correctly per instruction ("do not implement a sophisticated
opponent model unless the data demonstrates it is feasible" — this session
establishes *plausibility* of the signal, which is the prerequisite step,
not a working model). **[QUESTION]**: whether this signal, even if real, is
available early enough in a match to change anything actionable (deck is
already fixed at submission time; only in-game tactical adaptation could
use it) — not resolved.

---

## 7. Strategy Findings

**FACT/RESULT** (7 required, all listed above in context — consolidated
here):
1. Engine card pool == competition-legal card pool == card-data-CSV pool,
   exactly 1267 cards; no separate restricted list exists (§1).
2. Deck copy-limit is keyed by card **name**, not card ID (§1) — a
   previously-unverified rule now confirmed from source.
3. Margin of victory does not affect skill-rating updates — only win/draw/
   loss (§2).
4. Search V2's chain-completion fix is mechanically correct (0 failures, 0
   cap-hits across 7000 games) but did not recover competitive performance
   — still significantly worse than the heuristic in 6/7 matchups (§3).
5. Only 1 of 8 real live-ladder archetypes (Dragapult ex) overlaps our local
   4-deck pool (§6) — the single highest-value finding this session.
6. The real live meta is itself non-transitive (rock-paper-scissors
   triangle found in the actual matchup grid), structurally mirroring what
   was already found locally in Competitive V1 (§6).
7. Opponent Pokemon species (not hand/deck) are visible from turn 1 onward
   for both players — a real, currently-unused information channel (§6).

**HYPOTHESES** (5 required):
1. Search V2's remaining performance gap is primarily an evaluation-
   function-quality problem, not a further state-completeness problem
   (§3).
2. Deck-level matchup diversity could matter as much as action-selection
   quality, given margin-insensitive scoring and a large, presumably deck-
   diverse 6,715-team population (`competition_mechanism.md` Q5).
3. Opponent-archetype inference from early-revealed Pokemon species is
   plausible and cheap, though not yet demonstrated actionable (§6).
4. A second submission's practical value is closest to risk-hedging/A-B
   testing between the statistically-tied Dragapult/Lucario candidates
   under real ladder conditions, not a coordinated dual-agent strategy
   (`competition_mechanism.md` Q4).
5. Our local Abomasnow/Iono's/Lucario decks, being entirely absent from the
   tracked live meta, may face a substantially different (and currently
   unmeasured) opponent distribution on the real ladder than our local
   4-deck round robin suggests.

**QUESTIONS** (5 required):
1. Do any two distinct card IDs share the same name (relevant to the
   copy-limit rule) (§1)?
2. What is the raw daily episode dump's schema, and would parsing it reveal
   real opponent decklists for the 8 known live archetypes (§6)?
3. Is the 2026-07-31 meta snapshot still representative 11+ days later (§6)?
4. Can Search V2's evaluation function be replaced with something that
   captures KO-immunity/prize-threshold reasoning, and would that recover
   the lost performance (§3)?
5. Is the opponent-species signal (§6) available early enough, and reliable
   enough, to justify building an actual archetype classifier?

---

## 8. Leaderboard Strategy

Ranked by (Expected leaderboard impact × Confidence) ÷ Cost:

**1. Submit `dragapult_fix_v1` (and/or `lucario_ex_agent` as the 2nd Final
Submission) now.** Impact: high — real ladder validation is now possible
and the mechanism audit (§2) shows margin-insensitive, large-sample rating
converges over ~2 months of the live population, which is exactly the kind
of evaluation our small local samples cannot substitute for. Confidence:
high (both candidates are the most rigorously audited work in this
project). Cost: near-zero (packaging only). Using **both** available Final
Submission slots on the statistically-tied Dragapult/Lucario pair
(§7 hypothesis 4) turns the live ladder itself into the tiebreaker,
which no further local benchmarking can provide as cheaply.

**2. Pull and inspect a real slice of the official daily episode data to
verify the 8-archetype meta snapshot and, if feasible, extract real
decklists for the 3 non-Dragapult archetypes closest to our own decks'
role (attacker/support balance).** Impact: potentially high — directly
addresses this session's biggest finding (§6: our local pool barely
overlaps the real meta) and could inform which of our decks (if any) is
worth a serious rebuild vs. which locally-strong decks are simply
irrelevant to the real ladder. Confidence: medium (data is confirmed
available/accessible/usable; whether the raw schema yields clean decklists
without more parsing work is unverified). Cost: medium (real download +
parsing effort, deferred this session for time).

**3. Fix Search V2's evaluation function (not its architecture) and re-run
the ablation.** Impact: medium — the chain-completion mechanism is now
correct infrastructure; if a better evaluation function (even a small,
targeted one covering KO-immunity and prize-count thresholds) closes the
gap, this could recover a meaningfully stronger agent, per the actual
official recommendation to use Search for exactly this kind of question.
Confidence: medium (evaluation-quality hypothesis is plausible but
untested). Cost: medium (needs careful evaluation-function design + a full
re-ablation to confirm, similar scale to this session's work).

Deliberately not ranked highly: deeper search (blocked on #3 succeeding
first), large-scale deck optimization or opponent modeling (§6/7 establish
plausibility, not yet a working signal worth committing resources to), and
self-play/RL (still explicitly out of scope, and nothing measured this
session changes that call).

---

## STOP

Per the governing prompt, this report is the checkpoint. No further phase
(Search V3, large-scale deck optimization, deep MCTS, opponent modeling,
self-play, RL, neural networks) begins automatically — the next direction
is chosen from this evidence, not assumed.
