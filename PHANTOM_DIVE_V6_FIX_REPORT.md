# V6 — Surgical Phantom Dive Bug Fix: Implementation Report

**Date**: 2026-08-13. **Scope**: implement V6 as a strictly controlled experiment — V2 +
ONLY the two confirmed Phantom Dive bugs fixed, nothing else. Per instructions, this is a
causal A/B test of a hypothesis, not a tuning pass; no ELO outcome is assumed.

---

## 1. The two bugs fixed

Both are documented and source-verified in `PHANTOM_DIVE_ARCHITECTURE_AUDIT.md` (§3.2, §3.3)
and re-confirmed as the full explanation (once index-alignment was ruled out) in
`PHANTOM_DIVE_INDEX_ALIGNMENT_AUDIT.md` §7.

**Fix #1 — backwards `hp == 10` fallback penalty** (`dragapult_policy_v2plus.py:793-794`).
The `DAMAGE_COUNTER_ANY` per-counter fallback scored a bench target sitting at exactly one
counter from death (10 HP) with `score -= 100000` — the single cheapest kill available was
being actively deprioritized below unreachable targets. Changed to `score += 40000`, which:
- keeps the change in the same additive-bonus unit scale as the two buckets immediately above
  it (`+30000` for the 210–260 HP near-lethal-mega bucket, `+10000` for the general
  20–120ish HP bucket);
- strictly dominates both, since a guaranteed single-counter kill should always outrank a
  target that merely *might* be finishable;
- does not touch `SelectContext.DAMAGE_COUNTER` (a different, single-target context used by
  other effects) — only the `DAMAGE_COUNTER_ANY` branch (Phantom Dive's six-counter mechanic)
  was touched.

**Fix #2 — Phantom Dive plan contaminated by a fictional Active-damage premise**
(`dragapult_policy_v2plus.py:294`, inside `main_option_proc`). The function is called with a
hardcoded `damage=200` — Phantom Dive's own card-data `damage` field, confirmed live against
`cg.api.all_attack()` in this session (`Attack(attackId=154, damage=200, text="Put 6 damage
counters on your opponent's Benched Pokémon in any way you like.")`). The card text is
bench-only; Phantom Dive never touches the Active. The `i == 0` (opponent's Active) iteration
of the loop nonetheless treated the Active as if it took 200 real damage, which could (a)
fabricate a KO'd-Active prize count, and (b) short-circuit the entire bench-counter combo
search (`max_score = 50000`, skipping the real `else` branch) whenever `remain_prize <=
base_prize_count` — leaving `self.plan_b.counter` (the only thing the six live per-counter
selects consult) empty for the whole attack.

Fix: gate the assumption behind `if i == 0 and self.can_main_attack: active_damage = 0`.
`can_main_attack` is set `True` only when Phantom Dive (attackId 154) is among the offered
attack options this decision, so the fix cannot fire for any other attack, and cannot fire on
the `bench_attacker`-only path that also calls `main_option_proc` without Phantom Dive being
offered.

---

## 2. Why these are the smallest safe changes

- **Fix #1** is a single-line constant swap, same branch, same unit scale.
- **Fix #2** adds one conditional gated on state (`self.can_main_attack`) that already exists
  and is already computed earlier in the same function for exactly this purpose (detecting
  Phantom Dive). No new state, no new pass over the board, no change to the combo-generation
  algorithm (the 60-damage backtracking subset-sum enumeration at `:268-287` is untouched).
- Both fixes are scoped so they can only change behavior when Phantom Dive is actually the
  attack in play (`self.can_main_attack`) or its own six-counter placement context
  (`DAMAGE_COUNTER_ANY`) — never any other attack, context, or decision type. TEST 5 (below)
  verifies this empirically, not just by code inspection.
- `main_option_proc` was not rewritten, no macro-action system was added, no MCTS/search/beam
  search was touched, and the action space/protocol is unchanged.

**Not changed, deliberately**: the `prize == 1: score -= 300` / `prize == 0: score += 1200`
combo-scoring asymmetry discovered while designing the regression tests below (it makes
`main_option_proc`'s combo search sometimes prefer "take no bench action" over "take a single
free 1-prize kill" when `remain_prize > 4` — TEST 1 and TEST 3's row A specifically exercise
this path to isolate Fix #1). This is a separate, pre-existing, out-of-scope characteristic of
the combo-value formula shared verbatim with V1 — documented here per instructions ("if you
discover another possible bug, document it separately and leave it untouched"), not fixed.

---

## 3. Files changed / added

**Modified**: none. `dragapult_policy_v2plus.py` (V2's shared engine, still used unmodified by
V2/V3/V4/V5), `policy_weights.py`, `decks/dragapult_ex.csv`, and every other pre-existing file
are byte-identical to the V2 baseline — verified directly against
`submission/_staging_v2/src/agents/dragapult_policy_v2plus.py`, the frozen V2 snapshot (`diff`
returns nothing).

**Added** (V6 gets its own forked engine file rather than reusing the shared one, precisely so
V2/V3/V4/V5 remain provably untouched):
- `src/agents/dragapult_policy_v6.py` — forked from `dragapult_policy_v2plus.py`; the two
  functional changes above, plus an updated module docstring. Everything else byte-identical.
- `src/agents/dragapult_agent_v6.py` — thin binding, `make_agent(BALANCED, adaptive=False,
  always_first=True)` against V6's own policy module (identical weight profile to V2 — this is
  an A/B test of the engine fix, not a retune).
- `src/agents/final_candidate_agent_v6.py` — safety_wrapper → timeout_shield → policy, same
  composition as every other version's final-candidate module.
- `main_v6.py` — Kaggle entry point, same structure as `main_v2.py`, same deck.
- `tools/verify_phantom_dive_v6_fixes.py` — the regression suite (§4).
- `tools/verify_v6_real_game_smoke_test.py` — real-engine smoke games (§5).
- `tools/build_submission_challenger.py` — `VALID_VERSIONS` extended to include `"v6"` (one-line
  addition; the packaging logic itself is fully version-parameterized already and required no
  other change).

---

## 4. Regression tests (`tools/verify_phantom_dive_v6_fixes.py`)

Method: construct minimal, schema-valid `cg.api` Observation dicts by hand and call
`DragapultPolicy.agent()` directly — the exact entry point the real engine calls. One
`MAIN`-context call (offering Phantom Dive) seeds `plan_a`/`plan_b`, then up to six
`DAMAGE_COUNTER_ANY`-context calls simulate the six real placement round-trips, with bench
array positions held fixed and HP tracked live including going to/below zero without the slot
disappearing — this exactly matches the real engine's own documented mid-attack behavior
(`PHANTOM_DIVE_INDEX_ALIGNMENT_AUDIT.md` §2/§4), not an assumption made for convenience. Real
card IDs from this competition's shared card pool were used and cross-checked live against
`cg.api.all_card_data()` (121 = Dragapult ex, 269 = Iono's Bellibolt ex [2-prize, ex], 270 =
Iono's Wattrel [1-prize, non-ex]).

All 5 required tests pass; full output below.

```
TEST 1 -- 10 HP lethal target vs. an unreachable healthy target (fallback path)
    V2: chosen_slots=[1,1,1,1,1,1] final_hp=[10, 90]  dead_slots=[]        <- misses the free kill
    V6: chosen_slots=[0,1,1,1,1,1] final_hp=[0, 100]  dead_slots=[0]       <- takes it
  [PASS] V2 (unfixed) reproduces the bug
  [PASS] V6 (fixed) secures the free 10-HP KO that V2 misses

TEST 2 -- multiple lethal targets + an unreachable distractor (plan/combo path)
    V2: plan_b=[]     chosen_slots=[2,2,2,2,2,2] dead_slots=[]             <- 0/2 KOs, all 6 dumped on distractor
    V6: plan_b=[1, 2] chosen_slots=[0,1,2,2,2,2] dead_slots=[0, 1]         <- 2/2 KOs
  [PASS] V2 (unfixed) reproduces the bug: short-circuit empties plan_b
  [PASS] V6 (fixed) secures both simultaneous lethal KOs

TEST 3 -- reconstructed real missed-KO forensic cases
  Row: episode 92219700 turn 13 (documented optimal: 1 KO, the 20 HP target)
    V2: chosen_slots=[0,1,1,1,1,1] dead_slots=[]      <- matches real ladder data {0:1,1:5}, 0 KOs
    V6: chosen_slots=[0,0,1,1,1,1] dead_slots=[0]     <- secures the documented optimal KO
  Row: episode 92232003 turn 12 (documented optimal: 2 KOs, both 10 HP targets)
    V2: chosen_slots=[3,3,3,3,3,3] dead_slots=[]      <- matches real ladder data, 0 KOs, all 6 on unreachable target
    V6: chosen_slots=[0,1,3,3,3,3] dead_slots=[0, 1]  <- secures both documented KOs
  [PASS] all 4 checks (V2 reproduces / V6 fixes, both rows)

TEST 4 -- Active short-circuit: plan_b must not be abandoned
    V2: plan_b=[]  chosen_slots=[0,0,0,0,0,0] dead_slots=[0]  <- KO still lands here via luck, but plan_b is empty
    V6: plan_b=[1] chosen_slots=[0,0,0,0,0,0] dead_slots=[0]  <- plan_b correctly populated
  [PASS] V2 (unfixed) confirms plan_b.counter is abandoned (empty)
  [PASS] V6 (fixed) still builds the bench allocation plan
  [PASS] V6 (fixed) secures the KO despite the fictional Active-damage premise

TEST 5 -- non-Phantom-Dive regression (identical V2/V6 behavior)
  5a. MAIN decision, Phantom Dive NOT offered (bench_attacker path only):
      V2 plan_b=[] action=[0]  ==  V6 plan_b=[] action=[0]   [PASS] identical
  5b. DAMAGE_COUNTER (not _ANY) context, a different attack's placement:
      V2 action=[0]  ==  V6 action=[0]                        [PASS] identical

PASS: all Phantom Dive V6 regression checks passed.
```

**Reconstruction methodology for TEST 3** (transparency note): the real Kaggle simulation
engine is compiled/opaque and ships only inside the Kaggle sandbox (confirmed by
`PHANTOM_DIVE_INDEX_ALIGNMENT_AUDIT.md` §2 — this repo cannot arbitrarily inject a historical
board state into it). `missed_ko_examples.csv` records bench HP/prize composition but not the
opponent's Active HP for each row, so these two rows reconstruct the documented bench
composition exactly and choose an Active HP / `remain_prize` pair that reproduces V2's actual
recorded zero-KO outcome for that row before checking V6's behavior on the identical fixture —
this is a reconstruction of the documented failure signature from the audited data, not a
byte-for-byte replay of the original replay JSON.

---

## 5. Additional local validation

- `tools/deck_validator.py deck.csv` → `LEGAL` (unchanged, same deck as V1-V5).
- `main_v6.py` imports cleanly, `agent()` defined, `DECK` has 60 cards, first `select=None`
  call returns the deck (mirrors `build_submission_challenger.py`'s own import check).
- `tools/verify_v6_real_game_smoke_test.py` — three full real games through the actual compiled
  engine (not synthetic fixtures): V6 self-play, V6 vs. `abomasnow_agent`, V6 vs. V2 head-to-head.
  All produced only legal actions (index bounds, min/maxCount, no duplicates) for their full
  duration. Phantom Dive's `DAMAGE_COUNTER_ANY` context was genuinely exercised by V6 in every
  game (24, 6, and 12 real counter-placement selects respectively), confirming the fix engages
  in real play, not only in the synthetic regression fixtures.

---

## 6. Diff audit

```diff
--- src/agents/dragapult_policy_v2plus.py
+++ src/agents/dragapult_policy_v6.py
@@ main_option_proc, i==0 iteration @@
-            active_damage = 0 if no_damage_dex(pokemon.id) else damage
+            if i == 0 and self.can_main_attack:
+                active_damage = 0
+            else:
+                active_damage = 0 if no_damage_dex(pokemon.id) else damage

@@ DAMAGE_COUNTER_ANY fallback @@
                                     elif hp == 10:
-                                        score -= 100000
+                                        score += 40000
```
(plus the module docstring, updated to document the fork and the two fixes — no functional
effect.) Every other line of the ~900-line file is unchanged; `diff` against
`dragapult_policy_v2plus.py` shows exactly this delta and nothing else.

**Confirmed no weight, deck, or unrelated policy changes**: `policy_weights.py`,
`decks/dragapult_ex.csv`, and `dragapult_policy_v2plus.py` itself are byte-identical to the
frozen V2 baseline (`submission/_staging_v2/`). V6 uses the exact same `BALANCED` weight
profile, `adaptive=False`, `always_first=True` as V2 (`dragapult_agent_v6.py` mirrors
`dragapult_agent_v2.py` line-for-line except the import source). No retreat logic, targeting
logic outside the two confirmed bugs, first/second-player logic, opponent modelling,
search/lookahead, MCTS, beam search, engine, cg bindings, action protocol, or Pokémon
identity/index handling was touched. No serial-based remapping was added, per instructions —
the index-alignment audit already established raw-index resolution is correct and stable in
the real engine.

---

## 7. Submission package

`submission/challenger_v6_20260813T050318Z.tar.gz` (1.95 MB), built via
`python tools/build_submission_challenger.py --version v6` — the identical packaging procedure
used for V2-V5 (`VALID_VERSIONS` extended by one line; no other change to that tool was
needed). Staging dir preserved at `submission/_staging_v6/` for inspection. **Not submitted to
Kaggle** — that remains a separate, explicit action per standing instructions.

---

## 8. Remaining uncertainty

- **The real-ladder effect is untested.** Per the experimental-discipline instructions, no ELO
  outcome is assumed. V6 is ready to run the same 43-real-ladder-game protocol V2 was measured
  with; only that live measurement can confirm whether these two fixes move V2's 52.4% Phantom
  Dive KO conversion / 62.8% win rate / 699.8 rating.
- **The `prize==1` vs `prize==0` combo-scoring asymmetry** (§2, "not changed, deliberately") is
  a separate, pre-existing characteristic of `main_option_proc`'s combo-value formula (shared
  verbatim with V1) that can make the planner prefer taking no bench action over a single
  1-prize kill when `remain_prize > 4`. It doesn't block either fix (both fixes' target
  mechanisms were verified to work correctly around it, and Fix #1 alone recovers the fallback
  path whenever this quirk keeps `plan_b.counter` empty for an unrelated reason), but it is a
  candidate for a future, separate investigation — not touched here.
- TEST 3's two rows are reconstructions (methodology in §4), not literal replays of the
  original replay JSON, since the real engine only accepts fresh `battle_start` calls, not
  arbitrary historical state injection, from outside the Kaggle sandbox.
