# Phantom Dive Architecture Audit — Code-Level Trace of the V2 Decision Path

**Date**: 2026-08-13. **Scope**: architecture audit only, per your instructions — no weight
changes, no deck changes, no retreat-logic changes, no V5, no fix implemented. Goal: trace the
real execution path of a Phantom Dive decision end-to-end and test (not assume) Gemini's
hypothesis that "V2 suffers from a sequential action-horizon / micro-decision problem... cannot
reliably see the terminal prize gain produced by the complete six-counter allocation," building
on the empirical miss-rate finding in `PHANTOM_DIVE_FORENSIC.md` (47.6% missed-KO rate, 30/63
opportunities, PARTIALLY SUPPORTED verdict).

Every claim is tagged **[FACT]** (verified directly against source in this repo),
**[HYPOTHESIS]** (reasoned from the code but not runtime-instrumented), or **[GAP]** (could not
be resolved from static source alone). Per process rule 6, load-bearing claims below were
checked against the actual source files, not inferred — file:line citations throughout.

---

## 0. What "V2" actually is, end to end (FACT)

Traced the real import chain from the Kaggle entry point down:

```
submission/_staging_v2/main.py
  -> src.agents.final_candidate_agent_v2.agent
       = wrap_agent(wrap_timeout(dragapult_agent_v2.agent))          [safety_wrapper.py, timeout_shield.py]
  -> src.agents.dragapult_agent_v2.agent
       = make_agent(BALANCED, adaptive=False, always_first=True)      [dragapult_agent_v2.py:14]
  -> src.agents.dragapult_policy_v2plus.DragapultPolicy(BALANCED).agent   [dragapult_policy_v2plus.py:401]
```

**[FACT]** `safety_wrapper` and `timeout_shield` are a legality/crash/timeout net around the
*same* single decision — they do not add search, lookahead, or re-evaluate alternatives; they
only validate/fall back if the wrapped call errors or exceeds a budget (confirmed by reading both
files; neither imports `search_step`/`search_begin`).

**[FACT, falsifies a premise of the question set before any deeper tracing]**: `grep -rl
"search_lookahead" src/agents/final_candidate_agent*.py src/agents/dragapult_agent_v*.py` returns
**zero matches**. `src/agents/search_lookahead_v2.py` (the module that actually drives
`search_begin`/`search_step`/tree-style rollouts) is never imported by **any** of V1–V5's real
agent-construction chain. It is only ever invoked by standalone experiment scripts
(`experiments/search_v2_ablation.md`, `results/search_v2_ablation/`). **There is no search tree,
no depth limit, no pruning, no beam, and no discount factor anywhere in the Phantom Dive decision
path that actually ran on the ladder** — for V2 or for any other numbered variant. This directly
answers C, E (partially), H, and K below, and means most of Gemini's search-architecture
questions (C, K, and the depth/pruning half of E/H) describe a mechanism that **does not exist in
the code that produced the 149 audited attacks**. This is the single most important finding of
this audit and should be checked before any further discussion assumes a search tree is involved.

---

## 1. Full execution trace: Phantom Dive selection → 6 placements → resolution

**[FACT]** All of the following is one class, `DragapultPolicy`, called by the engine once per
decision (`dragapult_policy_v2plus.py:401` `agent()`), stateless between calls except for
`self.plan_a` / `self.plan_b` (persisted on the instance).

1. **MAIN decision** (`select.context == SelectContext.MAIN`, `dragapult_policy_v2plus.py:682`):
   `self.main_option_proc(obs, damage=200)` runs **once**, before Phantom Dive is even chosen as
   the action. This function (`:240-332`) is the thing that stands in for a "combinatorial
   solver": for each possible primary target `i` in `[active] + bench`, it evaluates a
   **precomputed set of joint bench-target combinations** (`counter_indices`, built by a
   backtracking subset-sum enumeration over `remain_damage = 60` at `:268-287`) and scores each
   combination by the **total prize value of the whole combo**, not per-counter. The winning
   combo's target-index list is stored in `self.plan_a.counter`, and — critically — **only the
   result from iteration `i == 0` (i.e., "active") is copied into `self.plan_b.counter`**
   (`:329-331`), which is the field actually consulted for Phantom Dive.
2. The MAIN option scores get computed (attack, retreat, trainer, etc.) and `select_top` returns
   the chosen option, e.g. `{"type":13,"attackId":154}` (Phantom Dive).
3. **Six independent engine round-trips follow.** Per `PHANTOM_DIVE_FORENSIC.md` §0 (verified
   against real replay JSON) and confirmed structurally here: each of the 6 damage counters is a
   **separate top-level call into `agent()`**, with `select.context ==
   SelectContext.DAMAGE_COUNTER_ANY`. `main_option_proc` is **not** re-run on these calls (it is
   gated behind `if context == SelectContext.MAIN`, `:682-683`) — `self.plan_b` is whatever was
   computed once, in step 1, against the **pre-attack** board.
4. For each of the 6 calls, every offered bench-target option gets a per-option score
   (`:769-796`):
   ```python
   score = 100000 - 10 * hp + pokemon_score(card, False, weights)
   index = o.index + 1
   if index in self.plan_b.counter:
       score += 100000                      # trust the precomputed plan
   else:
       remain_damage = select.remainDamageCounter * 10
       if 210 <= hp <= 200 + remain_damage:
           score += 30000
       elif 20 <= hp <= 60 + remain_damage:
           score += 10000
       elif hp == 10:
           score -= 100000                  # see §3.2 — this is backwards
   if no_damage_counter(card):
       score = -1
   ```
   `select_top` (`common.py:74-97`) then just sorts and returns the single top-scoring option
   (`select.maxCount == 1` for a single counter).

So the real architecture is: **one upfront, whole-combo plan, consulted six times via a static
index membership check, with a hand-tuned per-option fallback when the plan doesn't apply.** This
is a materially different shape than "six blind micro-decisions with no visibility into the
terminal outcome" — the visibility exists, it's just computed once and (as shown in §3) not
reliably wired through to all six real selects.

---

## 2. Answers to your structured questions

**A. Are the six placements six independent actions?**
**[FACT]** Yes. Six separate `SelectContext.DAMAGE_COUNTER_ANY` engine round-trips, each a fresh
call to `agent()`. Confirmed both from replay structure (forensic report) and from the code path
(§1.3) — there's no batching API used or available for this decision type in `cg.api`.

**B. Does the search/evaluator see the final board state after all six placements?**
**[FACT]** There is no search/evaluator in V2's real path (§0). The closest analogue —
`main_option_proc`'s combo scoring — **does** evaluate the joint/final prize value of an entire
candidate combo, but only once, upfront, before any counters exist, and disconnected from the
live per-step legality state (§3).

**C. Effective search depth; does a max_depth cut off the 6th counter?**
**[FACT]** Not applicable — no search tree exists in V2's path (§0). For completeness: the
*unused* `search_lookahead_v2.py` module, if it were wired in, would **not** truncate a 6-step
same-player chain — its only limit is a defensive `max_chain_steps=20` cap
(`search_lookahead_v2.py:154`, documented as "should never be needed in practice";
`_resolve_full_chain` at `:117-151` keeps stepping through same-player decisions, which per its
own audit (`results/search_v2_audit.md`) includes damage-counter placement). 6 < 20, so even in
that hypothetical wiring, Gemini's "hits the depth limit before the 6th counter" mechanism would
not fire. This falsifies the depth-limit hypothesis on two independent grounds: the module isn't
used, and even if it were, its cap is nowhere near binding for this attack.

**D. Is the prize/KO reward visible only after the final counter, or earlier?**
**[FACT, mixed]** In the upfront plan (`main_option_proc`), reward for a *complete* combo is
visible before the first counter is even placed. In the per-counter fallback path (used whenever
`index not in self.plan_b.counter`), reward is **not** visible — each option is scored from a
static HP-bucket table with no notion of the combo's joint terminal value.

**E. Can the sequence "counter1→A, counter2→A→KO" be discovered, or is it pruned first?**
**[FACT]** Not pruned by search (none exists) or by depth. **[HYPOTHESIS, verified by hand-trace
below, §3.1]**: `main_option_proc`'s combo enumeration *does* discover and correctly rank
multi-counter-to-one-target and multi-target combos in the cases I traced by hand — it is not
structurally blind to this. The failure, where it occurs, is not "never considered," it's
"considered correctly upstream, then lost or misapplied downstream" (§3).

**F. Does the evaluator distinguish "10 dmg to a healthy target" from "10 dmg toward a target one
counter from KO"?**
**[FACT]** Only through the plan. The per-counter fallback bucket score is a function of the
target's **current** `hp` (which does reflect counters already placed on it, since it reads live
`card.hp` each call) but has no explicit "this would now finish it" bonus — a target sitting at
exactly 1 counter from death gets whatever bucket its current HP falls into, same as any other
target in that range, no special-cased lethal-completion bonus outside the plan membership check.

**G. Is there already an existing target/KO heuristic that should have solved this?**
**[FACT] Yes** — `main_option_proc` **is** exactly that heuristic, and it is not new to V2: it
exists verbatim in V1 (`dragapult_agent.py:187-332`, module-level globals instead of instance
state, but byte-for-byte the same algorithm, same `damage = 200` constant at `:346`, same `hp ==
10: score -= 100000` at `:665`). This is not a V2 regression — it is baseline behavior inherited
unchanged by every variant built on `dragapult_policy_v2plus.py` (V2 through V5, per that file's
own docstring claim of exact equivalence to V1, mechanically verified elsewhere by
`tools/verify_v2_engine_equivalence.py`). **[GAP]**: whether V1 itself shows the same ~48%
miss-rate was not measured in this audit or `PHANTOM_DIVE_FORENSIC.md` — only V2 was audited on
real ladder games. If the miss mechanism is in this shared code, V1 measurement would be a cheap,
high-value confirmatory check.

**H. Does action ordering or pruning bias the search toward spreading damage?**
**[FACT]** No search-level ordering/pruning exists. **[FACT]** The per-counter fallback *itself*
has a real bias, independent of any search: `20 <= hp <= 60 + remain_damage` gives **+10000** to
mid/high-HP targets (which mechanically require *more* counters, i.e. more "spreading" toward one
big target), while `hp == 10` — the cheapest possible single-counter kill — gives **−100000**
whenever that target isn't already flagged by the plan. Whenever the plan is incomplete for any
reason, the fallback doesn't fail neutrally, it actively steers toward the worse target. See §3.2.

**I. Any stochastic/random component in target selection?**
**[FACT] No.** `select_top` (`common.py:74-97`) is a deterministic sort. Nothing in
`dragapult_policy_v2plus.py`'s scoring imports or calls `random`. (`search_lookahead_v2.py` does
use `random.sample`/`random.choice`, but only to determinize *hidden* opponent information for
its own unused rollouts — never touches target selection, and isn't in V2's path regardless.)

**J. Could a weight change fix it, or is the needed information unavailable at decision time?**
**[FACT]** The information is available — `main_option_proc` computes it explicitly, upfront,
every time Phantom Dive is on offer. This is **not** an information-availability problem in the
sense Gemini's hypothesis frames it. It is a plumbing problem: a correctly-computed plan is either
(a) discarded to an empty list under a specific game-state shortcut (§3.3), or (b) not reliably
applied to the *live*, per-step option each of the six times it's consulted (§3.4, flagged as
HYPOTHESIS/GAP — could not fully confirm from static source). A pure weight retune (e.g. changing
the `-100000` constant) could mask symptom (b)'s worst case but would not address (a), which is a
branch-skip, not a magnitude problem.

**K. Discount factor / gamma on delayed reward at "step 6"?**
**[FACT] No.** No RL-style temporal discounting exists anywhere in this codebase.
`main_option_proc` computes an undiscounted terminal-value estimate for whole combos upfront; the
per-step fallback's `remain_damage` term changes the width of a static HP bucket per step, it does
not multiply/decay a reward value. Gemini's specific "reward too far in the future gets
discounted" mechanism is not present in this code.

---

## 3. What the code actually does wrong (the real candidates)

### 3.1 The combinatorial plan itself is largely sound where I could check it

**[HYPOTHESIS, supported by hand-trace, not by execution]** I hand-traced `main_option_proc`'s
`counter_indices` backtracking generator (`:268-287`) against two of the forensic report's
concrete examples using the reported HP values:

- Example #2 (92232003 t12): bench = Staryu(10), Staryu(10), Mega Froslass ex(310), Snorunt(70).
  The generator correctly enumerates `{Staryu1}`, `{Staryu1,Staryu2}`, `{Staryu2}` as feasible
  (≤60) combos and excludes Mega Froslass ex / Snorunt outright (>60 alone). The 2-Staryu combo's
  score strictly dominates any single-target combo (same shared baseline, plus one extra positive
  `pokemon_score` term) under the scoring formula at `:301-324`, regardless of which of the two
  `base_prize_count` branches apply.
- Example #7 (92233918 t14): bench = Snorlax(150) x2, Dunsparce(10) x2, Phantump(70). The
  generator correctly finds `{Dunsparce1, Dunsparce2}` as a feasible, dominant combo.

In both hand-traced cases, **the combinatorial math that Gemini's hypothesis says can't exist,
does exist and computes the correct answer**. This weighs against "the evaluator structurally
cannot see the joint outcome" and toward "the correct joint answer is computed, then lost."

### 3.2 A confirmed, concrete scoring bug: the fallback punishes the cheapest kill

**[FACT]** `dragapult_policy_v2plus.py:793-794` (and verbatim in V1, `dragapult_agent.py:665`):
```python
elif hp == 10:
    score -= 100000
```
This fires for any bench target sitting at exactly one counter from death (10 HP remaining) that
the plan didn't flag. A target needing 1 counter is the *cheapest possible KO available* — this
branch actively deprioritizes it below almost everything else on the board, including targets
that are mathematically **unkillable this turn** (e.g. a 70-HP target scores `+10000` under the
`20 <= hp <= 60+remain_damage` branch on early counters, when `remain_damage` is still large
enough to make 70 fall in-range even though 70 > 60 total budget). This is not a hypothesis about
intent — it's what the arithmetic does whenever the plan doesn't cover that target, and it maps
directly onto the forensic report's repeated observed pattern ("dump 6 counters on an unkillable
70+ HP target while a 10-HP target sits untouched").

### 3.3 A confirmed logic bug in the plan computation: Phantom Dive inherits a foreign attack's premise

**[FACT]** `main_option_proc` is called with a hardcoded `damage = 200`
(`dragapult_policy_v2plus.py:468`, unconditional, not attack-specific), and at `i == 0` (the
active Pokémon) it does:
```python
active_damage = 0 if no_damage_dex(pokemon.id) else damage      # 200, flat
if pokemon.hp <= active_damage:
    base_prize_count += prize_count(pokemon, True)               # treats active as KO'd
...
if remain_prize <= base_prize_count:
    max_score = 50000                                             # SKIPS combo search entirely
```
`PHANTOM_DIVE_FORENSIC.md` §0 already established as fact that **Phantom Dive never deals active
damage — structurally, by card text and by engine-enforced mechanics**. Yet the plan computation
that feeds `self.plan_b` (the only thing Phantom Dive's real per-counter selects consult) treats
the active Pokémon as if it takes a flat, fictional 200 damage from this same attack. Two
consequences, both real code paths, not speculative:
- **Whenever `remain_prize <= base_prize_count`** (i.e., I need very few more prizes to win, and
  the opponent's real active HP happens to be ≤ 200 — true for most non-tank actives) — the
  `else` branch containing the actual combo search (`:303-324`) is **skipped entirely**, and
  `ci` stays at its initialized value, `[]`. Since `i == 0` runs first and unconditionally copies
  into `plan_b` (`:330-331`), **`self.plan_b.counter` becomes an empty list** — meaning *no*
  bench target gets the `+100000` plan bonus for the entire attack, and every real counter falls
  through to the fallback in §3.2 (which then actively steers toward the wrong target). This is a
  narrow condition (near-endgame, low remaining-prize state) but it is a clean, reproducible
  all-or-nothing failure mode when it hits.
- **Whenever that shortcut doesn't fire**, the bogus "active took 200 damage, +1 prize" gets
  added into every combo's `prize`/`score` tally uniformly at `i == 0`. I checked algebraically
  whether this reverses the *ranking* between combos (it doesn't, in the cases checked — it's an
  additive constant shared by every candidate at that `i`) — but it does shift which of the
  `prize >= 2` / `elif prize == 1` / `else` branches (`:314-321`) each combo lands in, which
  changes the applied bonus/penalty in ways I did not fully resolve for every game state. This is
  flagged as a real defect (Phantom Dive's plan should never reason about active-Pokémon damage
  at all) independent of whether it's the dominant cause of the 47.6% miss rate.

### 3.4 The unresolved candidate: static plan indices vs. live per-step option indices

**[HYPOTHESIS — could not confirm or refute from static source; flagged as the top follow-up]**
`self.plan_b.counter` is computed **once**, as a list of indices into `cards = [active] +
op_state.bench` **as it existed before the first counter was placed** (§1, step 1). Each of the
six real `DAMAGE_COUNTER_ANY` selects then does `index = o.index + 1` against **whatever bench
list the engine offers at that specific step** and checks membership in that same static list
(`:784-786`). This is only correct if the live per-step bench ordering/membership is *identical*
across all six steps to what it was at the MAIN decision.

I could not verify this from source: the actual game simulation (`cg`) is a compiled/opaque
engine — `cg/game.py` and `cg/sim.py` in this repo are ~75-line bindings, not the real simulation
logic (per `engine_loader.py`'s own docstring, the real engine ships inside the Kaggle
submission/sandbox, not this repo). Standard Pokémon TCG rules check for Knock Outs only after an
effect fully resolves (i.e., all 6 counters land before anything is removed from the bench), which
would argue indices *should* stay stable across the 6 steps of a single Phantom Dive — but I have
no way to confirm this specific engine implementation actually follows that rule rather than
reindexing live.

**Suggestive but not conclusive evidence this matters**: `tools/build_phantom_dive_forensic.py`
(built in the prior session, already in this repo) does **not** trust a single pre-attack bench
snapshot for the full 6-step walk — it explicitly re-fetches `live_bench_now =
bench_snapshot(...)` fresh at every one of the 6 sub-steps and resolves each placement to a
Pokémon **serial** (a stable per-Pokémon identity), not a raw index (`:198-202`), specifically to
avoid trusting index stability across the sequence. That's the right way to parse replay data
defensively either way, so it isn't proof the underlying bug exists — but it's exactly the kind of
implementation choice you'd make if raw index reuse across the 6 steps had already bitten a
prior analysis. This is the single most valuable, cheaply-buildable next check: instrument
`plan_b.counter`'s captured indices against the actual `o.index+1` sequence seen in each of the 30
documented missed-KO replays (the raw data already exists in
`results/phantom_dive_forensic/events.csv` and the underlying replay JSON) and see whether they
diverge, and if so, at which step.

---

## 4. Testing Gemini's hypothesis directly

**Hypothesis as stated**: *"V2 suffers from a sequential action-horizon / micro-decision problem.
The agent evaluates the six 10-damage placements as separate micro-actions and therefore cannot
reliably see the terminal prize gain produced by the complete six-counter allocation."*

**Falsified as literally stated.** V2 has no search horizon to be limited (§0) — there is no tree,
no depth cap, no beam, no discount. More specifically, the agent is **not** blind to the terminal
/ joint outcome: `main_option_proc` computes exactly that — the total prize value of a complete
candidate allocation — once, before the first counter is placed (§1, §3.1). The six placements
are indeed six independent engine round-trips (Gemini is right about that mechanical fact,
matching the forensic report), but "independent round-trips" and "no visibility into the joint
outcome" are not the same claim, and only the second one is what actually fails here.

**What survives, reframed**: the six placements *are* decided by six independent scoring calls,
and the thing that's supposed to give them shared, joint awareness (`self.plan_b`) is a
**one-shot, potentially-stale, potentially-wrongly-computed artifact**, consulted through a bare
index-membership check with an actively harmful fallback when it doesn't apply. That's a real,
code-verified defect — just not a search-horizon defect. It's closer to "a correct one-shot plan
exists but the wiring from plan → six independent executions is fragile," plus at least one
outright logic bug (§3.3) and one clearly-backwards heuristic constant (§3.2).

---

## 5. Root cause classification

**Combination of the above** — specifically:

- **State-evaluation limitation**: NOT applicable in the search sense (no search exists), but the
  per-counter *fallback* evaluator (§3.2) genuinely cannot distinguish "cheap available kill" from
  "unreachable target" once it's operating without the plan — this is a real state-evaluation
  defect, just inside a heuristic scoring function rather than a search evaluator.
- **Target-selection heuristic bug**: confirmed, concretely — `hp == 10: score -= 100000`
  (§3.2) and the active-damage contamination in `main_option_proc` (§3.3) are both real, source-
  verified bugs in the existing target-selection heuristic Gemini's question G asked about
  ("is there already a heuristic that should have solved this" — yes, and it has identifiable
  defects).
- **Action-space / action-pruning / search-horizon limitations**: **ruled out** — no search
  exists in the deployed path for any variant V1–V5 (§0), so these categories do not apply to what
  actually ran on the ladder.
- **Insufficient evidence** on one specific point only: whether static-plan-index vs.
  live-per-step-index misalignment (§3.4) is real and how much of the 47.6% miss rate it accounts
  for, versus §3.2/§3.3 alone. This is the one piece of the mechanism I could not close out from
  source reading and flag as the clear next step before deciding on a fix.

---

## 6. Smallest architectural intervention (recommended, NOT implemented)

You asked me to explicitly weigh two options. Given the findings above, neither one is actually
what this bug calls for — both would be solving the wrong layer:

- **"Output a single combinatorial `Action([targets])` instead of 6 micro-actions"** — this
  assumes the six-actions-per-attack shape is the problem. It isn't (§4): a joint-aware plan
  already exists and is computed before the first micro-action. Collapsing the action space would
  remove information the engine's own API doesn't offer a way to submit anyway (per
  `PHANTOM_DIVE_FORENSIC.md`, the engine itself exposes Phantom Dive as 6 sequential
  `DAMAGE_COUNTER_ANY` selects — this isn't something our agent code controls, it's the `cg` API's
  contract).
- **"Run a fast forward-pass without depth limits specifically for damage resolution"** — this
  assumes a depth-limited search is truncating visibility. There is no search in the path at all
  (§0), so there's no depth limit to lift. Wiring `search_lookahead_v2`-style chain-following into
  V2's live path would be a much bigger, riskier change than the bug warrants, and per §3.1 it
  wouldn't even be attacking the actual defect (the plan is already joint-aware; the problem is
  downstream of it).

**What the evidence actually points to, smallest-first**:

1. **(Near-certain fix, minimal surface)** Remove or invert the `elif hp == 10: score -= 100000`
   branch in the `DAMAGE_COUNTER_ANY` fallback (`dragapult_policy_v2plus.py:793-794`). This is a
   single-line, clearly-backwards constant with no dependency on anything else — a cheap-kill
   target should never score below an unreachable one. This alone would stop the "actively steer
   away from the free kill" half of the observed pattern regardless of what caused the plan to
   miss that target in the first place.
2. **(Small, structural)** Stop `main_option_proc`'s `i == 0` iteration from reasoning about
   fictional active-Pokémon damage when the attack in question is Phantom Dive specifically (it
   never touches the active — this is already an established fact, not new information). Either
   gate the `active_damage`/`base_prize_count` contamination behind a real "does this attack hit
   the active" check, or compute `plan_b` from a dedicated bench-only pass instead of reusing the
   `i == 0` branch of the generic multi-target loop. This directly removes the empty-`plan_b`
   shortcut in §3.3.
3. **(Requires the follow-up measurement in §3.4 first)** If instrumenting real replays confirms
   index misalignment across the 6 steps, the fix is to make `plan_b` identity-based (Pokémon
   serial, matching what `build_phantom_dive_forensic.py` already does defensively) rather than
   raw-index-based, and/or re-derive the *current* live-index → planned-target mapping fresh at
   each of the 6 steps instead of trusting a single static list captured before the attack.

None of these three requires touching weights, the deck, retreat logic, or search architecture —
consistent with your standing instruction not to change those. I have not implemented any of
them; this is the architecture-audit checkpoint, and per this project's standing process rule, the
next decision is yours.

---

## 7. Explicit gaps / not done in this audit

- Did not execute the engine or replay real games to runtime-instrument the exact per-step index
  sequence against `plan_b.counter` (§3.4) — recommended as the highest-value next step before
  choosing between fix (2) and fix (3) above.
- Did not measure whether V1 (which shares this exact heuristic verbatim, §2.G) shows the same
  ~48% Phantom Dive miss rate — would help separate "defect in shared inherited code" from
  "defect specific to V2's BALANCED weight profile" (evidence here points to the former, since
  none of the identified bugs are gated by any `PolicyWeights` field).
- Did not fully resolve the branch-shift consequence of the `i == 0` prize contamination (§3.3,
  second bullet) for every possible game state — established it's a real defect, not fully traced
  its magnitude.
