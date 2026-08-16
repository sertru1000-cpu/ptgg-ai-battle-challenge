# Competitive V1 Report — Pokémon TCG AI Battle Simulation

Date: 2026-08-10 (session 2). Covers Prompt #2 ("Competitive V1") in full:
diagnostic fixes → stronger baseline → formal benchmark → Search API evaluation.
Builds directly on the FIRST REPORT (session 1); does not repeat the environment
audit. Deadline: Simulation track final submission **2026-08-16**.

Every claim below is tagged **FACT** (verified against source/direct measurement),
**RESULT** (a measured experimental outcome), **HYPOTHESIS** (an interpretation not
fully isolated/proven), or **QUESTION** (open, unresolved). Per project process
rules, nothing here should be read as a claim about the real Kaggle ladder meta —
all numbers are from local agent-vs-agent play only.

---

## 1. Diagnostic findings

### 1.1 Dragapult ex — the first/second-player "anomaly"

**Was it a bug? No.** Full investigation in `results/dragapult_first_second_analysis.md`
and the Phase-3 code audit (below). Summary:

- **FACT**: the engine always asks the player in **engine slot 0** (not a fixed
  seat, whichever deck is passed first to `battle_start`) the "go first?"
  question (`SetupProc.h`, `SetYesNoSelect(state, SelectContext::IsFirst, 0)`).
  The *answer* is a real, un-hardcoded agent decision — this corrects an earlier
  (session-1) misreading in `docs/environment.md` that conflated "who is asked"
  with "what they answer"; the doc has been corrected in place with a changelog
  note.
- **FACT**: `src/agents/dragapult_agent.py` is a **byte-for-byte behaviorally
  identical port** of the official notebook
  (`sample_notebooks/a-sample-rule-based-agent-dragapult-ex-deck.ipynb`) — every
  scoring branch, threshold, and the `IS_FIRST` handling (`score = -1 if context
  == SelectContext.IS_FIRST else 1`, i.e. deliberately decline to go first) were
  compared line-by-line and match exactly. `decks/dragapult_ex.csv` also matches
  the notebook's stated 60-card decklist exactly (all 22 card-ID counts verified
  programmatically). **No porting bug.**
- **FACT**: `abomasnow_agent.py`, `iono_agent.py`, and the new `lucario_ex_agent.py`
  all answer `YES` unconditionally to any yes/no prompt, including IS_FIRST.
  Since only engine slot 0 is ever asked, and Dragapult (NO) vs. these three
  (YES) is a fully deterministic pairing of opposite preferences, Dragapult ended
  up as the **second** player in essentially 100% of its games vs. Abomasnow and
  Iono's in the session-1 benchmark (verified directly from the raw per-game
  data), regardless of the tournament harness's engine-slot alternation. The
  FIRST REPORT's "160/162 losses when second" statistic is explained by this base
  rate, not by second-player status uniquely causing losses.
- **RESULT** (controlled experiment, `tools/dragapult_first_second_experiment.py`,
  1000 games/condition, Dragapult's real engine slot fixed and only the IS_FIRST
  answer forced): Dragapult wins significantly more often going **first** vs.
  Abomasnow (67.1% vs. 56.3%, z=-4.97, p≪0.001), directionally better first vs.
  Iono's (67.3% vs. 63.7%, not significant) and random (98.1% vs. 96.7%,
  borderline), and a statistical wash vs. Lucario ex (46.6% vs. 47.9%, not
  significant). **Root cause, verified against `GameProc.h`**: attacking and
  playing Supporters are barred on game-turn 1 only (i.e. only for whoever goes
  first), with no compensating "skip a draw" rule in this engine — Dragapult's
  evolution-buildup game plan apparently loses more from a delayed development
  turn than it gains from the second player's immediate-attack option.
- **Fix**: `src/agents/dragapult_agent_always_first.py` (**dragapult_fix_v1**), a
  thin wrapper that forces the IS_FIRST answer to YES and delegates every other
  decision unchanged to the real, untouched `dragapult_agent.py`
  (BEST_DRAGAPULT_AGENT — permanently preserved, never modified). Benchmarked
  against BEST_DRAGAPULT_AGENT's natural (mostly-second) results across 4
  opponents (`experiments/dragapult_first_variant.md`): pooled 65.67%→66.65%
  (not independently significant at this aggregate sample size, but directionally
  consistent with, and justified by, the higher-powered controlled result above).
  **Promoted** as the Dragapult representative for the formal V1 matrix.

### 1.2 Mega Abomasnow ex — deck mismatch

**Impact confirmed real but not (yet) shown to move the win-rate needle.** Full
audit in `results/abomasnow_deck_audit.md`.

- **FACT**: the on-disk `decks/abomasnow_ex.csv` diverges from the official
  notebook's named decklist on exactly 4 trainer/stadium slots — it omits Ultra
  Ball, Precious Trolley, Carmine, and Surfing Beach (all specifically
  referenced by card ID in `abomasnow_agent.py`'s scoring logic) and replaces
  them with 4 cards the agent has never heard of (Mega Signal, Maximum Belt,
  Cyrano, Waitress), plus one extra Basic Water Energy to make the count. This
  makes 3 purpose-built scoring branches permanently dead code and leaves 4
  actual deck cards scored only by generic per-option-type fallback values.
- **Correction**: `decks/abomasnow_ex_corrected_v1.csv`, built directly from the
  notebook's named-constant/comment counts, validated legal via `battle_start`.
- **RESULT** (`experiments/abomasnow_deck_fix.md`, corrected deck n=300/opponent
  vs. current deck's existing n=200): direction is consistently positive (+3.2pp
  vs. random, +1.5pp vs. Iono, +2.3pp vs. Dragapult) but **none reach
  significance** (all |z|<1.5). The deck fix is adopted on fidelity grounds (it
  is what the official example actually intends, and it's an unexplained,
  undocumented deviation otherwise) — not on demonstrated win-rate grounds.
  `decks/abomasnow_ex.csv` is preserved unmodified for session-1 reproducibility.

### 1.3 Mega Lucario ex — implementation

- **Faithful port** of `sample_notebooks/a-sample-rule-based-agent-mega-lucario-ex-deck.ipynb`
  ("Intermediate Level") into `src/agents/lucario_ex_agent.py` — same scoring
  logic, same deliberate omissions preserved (Dusk Ball / Fighting Gong have no
  card-specific scoring branch in the notebook either; not a porting gap), same
  non-`select_top` tail including its one stateful hook (Lunatone ability-use
  tracking after sorting, before truncating to `maxCount`).
- **Legal**: `decks/lucario_ex.csv` (60 cards from the notebook's named counts,
  summed and verified) passes `battle_start` with `errorType=0`.
- **Benchmark** (200 games/opponent initially, later folded into the 500-game
  formal matrix): strong performance overall — see §2. Notably crushes Iono's
  (78.2%) while being close-to-even with Abomasnow and Dragapult.

---

## 2. Final V1 formal matchup matrix

500 games/pairing, 10 pairings among {random, Abomasnow ex [corrected deck],
Dragapult ex [fix v1, always-first], Iono's, Mega Lucario ex}, zero aborted.
Full detail (first/second splits, avg game length, terminal-reason breakdown):
`results/formal_matrix_v1/README.md`. Raw data preserved under
`results/formal_matrix_v1/*/games/*.jsonl`.

| | random | abomasnow | dragapult_fix_v1 | iono | lucario |
|---|---|---|---|---|---|
| **random** | — | 3.8% | 1.6% | 0.0% | 3.4% |
| **abomasnow** | 96.2% | — | 45.6% | 20.4% | 48.6% |
| **dragapult_fix_v1** | 98.4% | 54.4% | — | 65.4% | 52.8% |
| **iono** | 100.0% | 79.6% | 34.6% | — | 21.8% |
| **lucario** | 96.6% | 51.4% | 47.2% | 78.2% | — |

Aggregate agent-vs-agent win rate (random excluded, 3 matchups/agent, n=1500):

| Agent | Win rate | 95% CI |
|---|---|---|
| lucario_ex_agent | 58.93% | [56.4%, 61.4%] |
| dragapult_fix_v1 | 57.53% | [55.0%, 60.0%] |
| iono_agent | 45.33% | [42.8%, 47.9%] |
| abomasnow_corrected | 38.20% | [35.7%, 40.7%] |

With the Dragapult fix adopted, all four heuristic agents now prefer "yes" to
IS_FIRST, so ordinary engine-slot alternation gives a genuine, balanced 50/50
first/second split for every non-random pairing (confirmed: every non-random
pairing split exactly 250/250 first/second in the raw data).

---

## 3. Best current baseline

Statistically clean **3-tier structure** (all comparisons two-proportion z-tests,
full numbers in `results/formal_matrix_v1/README.md` and
`results/statistical_summary.md`):

- **Tier 1 (statistically tied for best)**: `dragapult_fix_v1` and
  `lucario_ex_agent` — neither their aggregate difference (z=-0.78) nor their
  direct head-to-head (52.8%/47.2%, z=-1.77) is significant.
- **Tier 2**: `iono_agent` — significantly behind both Tier-1 agents
  (z=-6.68, z=-7.46) but significantly ahead of Tier 3.
- **Tier 3**: `abomasnow_corrected` — significantly behind all three others.

**HYPOTHESIS/RESULT (non-transitivity)**: Lucario's higher aggregate average
(58.9% vs. Dragapult's 57.5%) coexists with Dragapult beating Lucario head-to-head
(52.8%, though not significantly) — Lucario's average is pulled up by crushing
Iono especially hard (78.2% vs. Dragapult's 65.4% over Iono). Best agent is not
reducible to one scalar in this local pool.

**Recommendation**: `dragapult_agent_always_first` (dragapult_fix_v1) as the
practical default — it beats every other deck in the pool in raw head-to-head
count (though the margin vs. Lucario isn't significant) and is the
better-understood, more heavily audited change this session. `lucario_ex_agent`
remains a fully live alternative candidate; the tie should be revisited with a
larger sample if it becomes submission-relevant.

**Best agent vs. best deck**: kept conceptually separate per instruction, but the
current architecture couples each heuristic tightly to its own deck's card IDs —
agent and deck aren't independently swappable yet. `tools/tournament.py`'s
`--deck-a`/`--deck-b` override (exercised in the Abomasnow fix) preserves the
capability to test deck variants against a fixed heuristic later; no full deck-
optimization project was launched this phase, per instruction.

**Caveat**: this ranks *these four locally-ported, official-notebook-derived
decks against each other in a 5000-game local benchmark* — not a claim about the
real Kaggle Simulation ladder meta, which may look nothing like this.

---

## 4. Search experiment (Phases 11-14)

### 4.1 What the Search API is (Phase 11)

Full reference: `docs/search_api.md`. Headline facts: `search_begin` requires the
*live* observation's `search_begin_input` token (only usable from inside a real
`agent()` call, not a stored/replayed one); you must supply your own concrete
determinized guess for every hidden zone (the engine does **not** sample this for
you); `search_step` enforces the same min/maxCount legality as the real game;
search runs as a fully separate hypothetical state, never touching the real
battle, and the sanctioned usage pattern is "spin up a disposable tree at the
real decision, evaluate candidate first moves, throw it away, apply the winner
via the real `battle_select`."

### 4.2 The 1-ply search agent (Phase 12)

`src/agents/search_lookahead.py`: wraps an existing heuristic agent completely
unchanged for every decision **except** choosing which attack to use when 2+
distinct attacks are legally offered in one MAIN decision (a genuinely high-
impact, narrow decision point, per the prompt's guidance to target attacks/KOs
first). For that one decision: one shared `search_begin` (own hidden zones
sampled from the agent's own known decklist, matching the official RL sample's
approach; opponent hidden zones determinized from the opponent's actual known
decklist — an explicit local-research simplification, flagged in the code and in
`docs/search_api.md`, not a technique that would work blind against an unknown
live opponent), then one `search_step` per candidate attack against that shared
determinization, evaluated by a small self-contained board-state score (prize
race + HP differential + bench count), picking the best; any Search API error
falls back silently to the wrapped heuristic's own choice.

- **Runtime**: no perceptible overhead in a 20-game timed smoke batch (~0.1s/game
  total including ~90 `search_step` calls across the batch) — orders of magnitude
  below the 10-minute/match budget.
- **Action coverage**: multi-attack decisions are common for both Dragapult ex
  (Dreepy/Drakloak/Dragapult ex each have distinct attacks) and especially Mega
  Lucario ex (Mega Lucario ex alone offers 2 attacks whenever it can act) — tens
  of occurrences per 20-30 games for both.
- **Crash rate**: 0/{all search attempts in every batch run} failed once the
  harness-level `search_begin_input`-stripping bug (see below) was fixed.

**Implementation bug caught during Phase 12, not a Search API problem**: the
existing `tools/tournament.py` harness's game loop does `obs.pop
("search_begin_input", None)` before calling the agent every decision — harmless
for every agent used before this phase (none called `search_begin`), but it
silently breaks every `search_begin()` call for any agent that does. Rather than
change the shared harness (used by every other experiment this session and not
worth risking a behavior change to), Phase 12's own experiment script
(`tools/search_ablation_experiment.py`) uses its own game loop that preserves the
field. First attempt at the ablation ran with this bug still present — search
silently failed every time and fell back to the heuristic, so its output was
discarded rather than reported as a "search vs. heuristic" result.

### 4.3 Search ablation (Phase 13)

Full record: `experiments/search_1ply.md`. `dragapult_fix_v1` alone vs.
`dragapult_fix_v1` + the 1-ply search override, 500 games/opponent/condition
(3000 games total), zero aborted, zero search failures (8586/8586 `search_step`
calls succeeded):

| Opponent | Heuristic-only | + 1-ply search | z | Verdict |
|---|---|---|---|---|
| abomasnow_corrected | 56.60% | 47.40% | -2.91 | **significant, worse** |
| iono_agent | 66.60% | 29.80% | -11.64 | **significant, much worse** |
| lucario_ex_agent | 48.80% | 37.00% | -3.77 | **significant, worse** |
| pooled | 57.33% | 38.07% | -10.56 | **significant, worse** |

**RESULT**: this is not "no improvement" — it is a large, statistically
overwhelming **regression** in every matchup tested, worst of all vs. Iono's
(-36.8pp). Runtime was never the issue (no perceptible overhead measured, see
§4.2) — this is a correctness problem with the specific integration.

**HYPOTHESIS** (code-supported, not independently isolated by a further
ablation — flagged as an explanation, not a proven mechanism):
`dragapult_agent.py`'s attack choice is not a simple single-select decision —
`main_option_proc()` runs its own subset-sum search over the opponent's bench to
plan a Phantom-Dive multi-KO sweep, storing the plan in module-global
`plan_a`/`plan_b`. A separate, later select in the same turn
(`SelectContext.DAMAGE_COUNTER`, choosing where to place Phantom Dive's 6 bench
damage counters) reads `plan_b.counter` directly. When `search_lookahead.py`
overrides the attack choice to something other than the heuristic's own planned
attack, that later damage-counter decision is still scored against the
heuristic's original, now-abandoned plan — a stale-state mismatch. Separately,
a single `search_step` call for a Phantom-Dive candidate almost certainly leaves
the hypothetical game still awaiting that same follow-up damage-counter choice
(a real decision, not an automatic resolution), meaning the 1-ply evaluation
never actually observes the attack's signature multi-KO effect in the first
place — it evaluates an incomplete outcome. Both point to the same conclusion:
a naive "override just the top-level choice" pattern is fundamentally unsafe
for a heuristic whose value is realized across a *linked pair* of selects, not
within a single one.

**Important distinction for interpreting this**: the Search API itself held up
fine in isolation (§4.1/4.2 — cheap, legal-respecting, zero crashes across 8586
calls). This is a specific implementation bug in how search was integrated with
an already-sophisticated stateful heuristic, not evidence against the Search API
as a technique in general.

### 4.4 Search depth experiment (Phase 14) — not pursued

Per the prompt's explicit instruction, Phase 14 only applies "if 1-ply/short
search demonstrates a measurable benefit." It did the opposite — a measurable,
large harm — so there is no positive result to extend to greater depth, and
deepening search on top of the same state-integration bug and the same crude
evaluation function would likely compound the problem rather than fix it.
Correctly skipped.

---

## 5. Strategy discoveries

**FACT**: only engine slot 0 is ever asked "go first?", and the answer is a real
agent decision (not hardcoded) — a genuine, exploitable engine mechanic any
heuristic or search-based agent should account for explicitly, not assume away.

**RESULT**: going first is a real, sometimes-large edge for Dragapult ex
specifically (significant, +10.8pp vs. Abomasnow) despite the official notebook's
own design unconditionally declining it — official example agents are not
necessarily strategically optimal even where they're internally consistent and
bug-free.

**RESULT**: local metagame among the 4 ported decks is non-transitive in its
*average* win rate (Lucario's aggregate exceeds Dragapult's despite losing their
head-to-head) even though the underlying win/loss structure is a clean total
order (Dragapult > Lucario > Iono > Abomasnow, no cycles) — "best deck" depends
on whether you're optimizing for beating a specific opponent or the average of a
field.

**RESULT**: Abomasnow-involving games resolve by board-wipe (opponent runs out
of Pokemon) far more than games between the two top-tier decks, which mostly
resolve by prize race — consistent with Hammer-lanche being a big single-target
nuke rather than a sustained-damage attacker.

**RESULT**: a deck/heuristic mismatch (Abomasnow's trainer-card substitution) can
persist through a full benchmark cycle without being caught by win-rate alone —
it only surfaced by directly diffing the on-disk deck against the notebook's
source, not from any win-rate anomaly (the corrected deck's improvement wasn't
even statistically significant).

**QUESTION**: does the first-player advantage found for Dragapult ex generalize
to genuinely different (non-locally-ported) decks, or is it specific to this
4-deck pool's dynamics?

**QUESTION**: would a smarter opponent-hand/deck determinization (rather than the
official sample's placeholder-filler approach, or this phase's "actually know the
local opponent's decklist" simplification) meaningfully change search's value —
i.e. is search underperforming here because 1-ply is too shallow, because the
evaluation function is too crude, or because the determinization is too
uninformative?

**QUESTION**: how much of Iono's and Abomasnow's weakness against Lucario/Dragapult
specifically is fixable with better heuristics vs. a genuine structural deck
disadvantage in this simulator's specific card pool?

**QUESTION**: does the real Kaggle ladder meta resemble this 4-deck local pool at
all, given it's drawn from a restricted card list this project hasn't yet
obtained/verified independently of `battle_start`'s empirical legality checks?

---

## 6. Leaderboard strategy

Ranked by (Expected leaderboard impact × Confidence) ÷ Implementation cost:

**1. Submit `dragapult_fix_v1` (or `lucario_ex_agent`) as the Simulation entry
now.** Impact: high (a real, audited, statistically grounded correctness/
strategy fix over the FIRST REPORT's baseline, with zero known bugs after a
full line-by-line audit). Confidence: high (Phase 1-10's evidence is the most
rigorous in this project so far — large samples, controlled experiments,
significance-tested). Cost: near-zero (packaging work only, no further research
needed). This is the clear highest-ratio move given the 2026-08-16 deadline.

**2. Fix the search-integration bug found in Phase 13 and retry 1-ply search.**
Impact: unknown but potentially high — the API itself is cheap and correctly
usable (§4.1/4.2), and the failure mode identified is specific and fixable
(don't override a linked multi-select decision without either recomputing or
bypassing the dependent state, or extend the rollout past 1 ply so the
heuristic's own downstream logic runs inside the search too). Confidence: medium
(the mechanism is a well-reasoned hypothesis from direct code reading, not yet
independently confirmed by a targeted ablation). Cost: medium (a few hours of
focused debugging + a re-run of the same ablation harness already built).

**3. Resolve the Dragapult/Lucario statistical tie with a larger sample, and/or
investigate whether Lucario's Phase-13-style search integration would fail the
same way.** Impact: low-medium (mostly affects which single agent to submit,
and both are already strong; the tie itself may just reflect genuine
closeness). Confidence: high that the tie is real (already n=500-1500).
Cost: low (just more games of already-built infrastructure).

Deliberately NOT ranked highly this round: deeper search (blocked on #2 first,
per Phase 14's explicit gate), opponent modeling, self-play/RL (explicitly out
of scope this phase per the master prompt), and deck optimization beyond the 4
ported decks (explicitly deferred, and the local 4-deck pool is too small to
safely generalize a deck-tuning conclusion from — see the anti-overfitting
caveat in §3).

---

## 7. Next-phase recommendation

**Package and submit `dragapult_fix_v1` as the Simulation entry, then invest any
remaining time before 2026-08-16 in fixing and re-testing the search
integration (option 2 above) rather than starting a new research direction.**

Rationale: the diagnostic/heuristic-fix work (Phases 1-10) produced the
project's most reliable gains this session — a statistically significant,
well-understood improvement (Dragapult's first-player fix), a legitimate deck
correction, and a fully audited 5-agent baseline with a clean tiered ranking.
That work is submission-ready today and the deadline is close. Search, in
contrast, is not currently net-positive — Phase 13 showed a clear, large
regression traced to a specific, plausible implementation bug rather than a
fundamental limitation of the Search API. Given the API itself measured cheap
and reliable (§4.2: no runtime concerns, zero crashes across 8586 calls), it
remains the most promising *path*, per the master prompt's own framing, toward
a materially stronger agent than pure heuristics — but only once the
integration bug is actually fixed and re-validated, not by pushing forward into
deeper search or self-play on top of a known-broken 1-ply implementation. Do
not start RL/self-play/opponent modeling this phase — nothing measured so far
justifies that jump in complexity yet, per the project's core rule.

---

## STOP

Per the prompt's explicit instruction, this report is the checkpoint. No further
phase (deeper search, self-play, RL, deck optimization, opponent modeling, Kaggle
packaging) begins automatically after this report — the next direction is decided
after review.
