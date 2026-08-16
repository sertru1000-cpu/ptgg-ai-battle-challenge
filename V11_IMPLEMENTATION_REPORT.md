# V11 Implementation Report — Macro-Action Search (End-of-Turn Lookahead)

**Status**: local build only, **not submitted to Kaggle**, per the governing task's explicit instruction —
waiting for user approval before any ladder submission.

**Files touched**: only new, V11-suffixed files, plus one additive edit to
`tools/build_submission_challenger.py` (new `v11` entry in `VALID_VERSIONS`/`DECK_SOURCE`, same pattern
already used for v9/v10). V6 and its files (`dragapult_policy_v6.py`, `dragapult_agent_v6.py`,
`final_candidate_agent_v6.py`, `main_v6.py`, `decks/dragapult_ex.csv`) were read-only inputs and were never
edited.

---

## 1. Executive Summary

The prior research prototype (`experiments/v6_one_step_lookahead.py`,
`ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md`) found that scoring a candidate action immediately after it is
taken is dominated by an **action-chaining artifact**: V6 routinely plays several MAIN actions in one turn
(play a card → evolve → attach → attack), so a 1-ply comparison between "attack now" and "play a card now"
often just measures two points on the *same* eventual turn, not two different turns. That report mechanically
verified 14/116 disagreements were false positives of exactly this kind.

V11 fixes this by evaluating every top candidate **only at the end of the whole turn**: apply the candidate,
then greedily auto-play the rest of the turn (via the engine's real search sandbox) until the turn actually
ends, then evaluate the resulting board with a turn-boundary-safe evaluator. This is a strict fork of V6 (same
decklist, same greedy scorer, same BALANCED weight profile, **no** V8/V9 survival-retreat heuristics, **no**
V10 deck/setup logic) with exactly one addition at the `MAIN` decision routing.

All deliverables are complete: V11 files built, a local self-play smoke test run (no crashes, no leaks, turns
complete normally), and `submission/challenger_v11_20260814T020515Z.tar.gz` packaged and validated. **Nothing
was submitted to Kaggle.**

---

## 2. Fork Verification (Objective 1)

| Check | Result |
|---|---|
| `src/agents/dragapult_policy_v11.py` forked from `dragapult_policy_v6.py` | ✅ every line preserved except the module docstring and the one new macro-lookahead block (§3) |
| `src/agents/dragapult_agent_v11.py`, `final_candidate_agent_v11.py`, `main_v11.py` created | ✅ thin bindings, identical structure to their V6 equivalents, only the imported module names changed |
| V11 decklist == V6 decklist | ✅ verified programmatically: `dragapult_policy_v6.DECK == dragapult_policy_v11.DECK` → `True` (both load `decks/dragapult_ex.csv`, 60 cards) |
| `decks/dragapult_ex.csv` legality | ✅ `tools/deck_validator.py decks/dragapult_ex.csv` → `LEGAL (errorType=0)` |
| V8/V9 survival/defensive-retreat heuristics | Absent — V11 keeps only V6's own pre-existing `defensive_retreat_*` BALANCED-profile behavior (already in V6), no new retreat logic was added on top |
| V10 deck/setup logic | Not used — V11 never imports or references `dragapult_policy_v10.py` or `decks/dragapult_ex_v10.csv` |

---

## 3. Macro-Action Rollout Implementation (Objective 2)

All new logic lives in `src/agents/dragapult_policy_v11.py`, gated to fire only on the in-scope decision type
(`SelectContext.MAIN`, `select.maxCount == 1`, 2+ legal options) — every other decision (deck-declare, damage
counter placement, switch-target selection, hand/trainer sub-selects, etc.) is byte-identical to V6 and never
touches the search sandbox.

```
score every MAIN option with V6's own unmodified greedy scorer (the existing `scores` list)
    |
    v
rank descending, take top MACRO_LOOKAHEAD_TOP_N (5)
    |
    v
ONE search_begin()  (shared root clone, my_deck=opponent_deck_hint=DECK — see §6 limitation #1)
    |
    v
for each of the 5 candidates (stops early if MACRO_LOOKAHEAD_TIMEOUT_S (0.2s) elapsed — §4):
    search_step(root, candidate)                         (candidate's own action)
    while still our turn and game not over:
        disposable copy.deepcopy(policy), forced `_rollout_mode = True`
        -> plain V6 greedy choice at each follow-up decision (NOT recursive macro search)
        search_step(...)                                  (repeat until turn ends)
    -> post_action_state_value(resulting obs)              (turn-boundary-safe evaluator, §3.1)
    final_candidate_score = v6_raw_score + post_action_state_value
    |
    v
search_end()  (always, in a finally block)
    |
    v
execute argmax(final_candidate_score)
```

The chain-stepping loop itself is **not reimplemented** — it reuses `search_lookahead_v2._begin_shared_search`
and `_resolve_full_chain` unchanged (the same already-audited helpers the one-step prototype used). Those
helpers stop exactly when `state.yourIndex != my_index` or the game ends, which — because they keep asking the
same real greedy policy for every intervening decision, not just an immediate follow-up select — already walks
through however many further MAIN decisions (play, evolve, attach, attack) remain in the turn. This is what
makes the mechanism a true end-of-turn rollout rather than a single-decision chain resolution.

**Recursion guard (`_rollout_mode`)**: the disposable deep-copied policy used to drive "the rest of the turn"
must make plain-greedy decisions, not invoke another 5-way macro search of its own (that would branch
combinatorially per candidate and defeat the flat, single-rollout design the task asked for). Each shadow copy
has `_rollout_mode` forced to `True` immediately after `copy.deepcopy()`; `_macro_lookahead_choice` checks this
flag first and returns `None` immediately if set, so the recursion is structurally impossible, not just
avoided by convention.

### 3.1 End-of-turn evaluator

`post_action_state_value(obs, my_index, weights)` is ported unchanged (identical formula and constants) from
`experiments/v6_one_step_lookahead.py`'s own function of the same name:

```
(Σ pokemon_score(p, False, weights) over our Active+Bench)
− (Σ pokemon_score(p, False, weights) over opponent's Active+Bench)
+ (opp.prize_remaining − our.prize_remaining) × 1000 × weights.prize_value_multiplier
(terminal states: ±1,000,000 / 0)
```

`pokemon_score` is V6's own unmodified function — the one scoring routine in V6's surface that is safe to call
on a hypothetical post-action board regardless of whose turn it has become, because it only reads a single
Pokémon's own fields (HP/energy/tools/stage/id) and `weights`, never `select`/`context`/`state.yourIndex`.
Every other V6 scoring routine (`main_option_proc`, the inline `scores[]` loop, `hand_score`, `attach_score`)
assumes it is being asked "given these legal options, which is best" and would silently score the wrong
player's options once control has passed — this is exactly the turn-boundary hazard the governing task warned
about, and it is why this specific evaluator (not a new one) was reused rather than invented.

---

## 4. Safety & Performance (Objective 3)

- **`search_end()` in `finally`**: yes — the entire candidate loop is wrapped in `try/finally`, so a search
  sandbox is always released even on an exception mid-loop or an early `break` from the timeout check.
- **RNG caveat**: accepted, unchanged from the prior prototype's documented position — Crushing Hammer's coin
  flip and the five search-then-shuffle trainers consume the one shared engine RNG stream every branch off a
  single `search_begin` root reads from, so the 5 candidates are not statistically independent. Not fixed for
  V11, per the governing task's explicit instruction.
- **Timeout safeguard**: `MACRO_LOOKAHEAD_TIMEOUT_S = 0.2`. The elapsed-time check runs **before starting each
  candidate's rollout**, not as a preemptive interrupt of an in-flight one (the underlying engine calls are not
  interruptible mid-call) — so it bounds how much *additional* work is attempted once the budget is spent, not
  a hard per-decision ceiling. Measured behavior (§5): median decision latency 32.6ms, well under budget; one
  observed decision reached 222ms (a single in-flight candidate finishing after the budget was already close),
  slightly over the nominal 200ms but still four orders of magnitude under the 600s whole-match Kaggle budget.
  If zero candidates finish before the deadline, `_macro_lookahead_choice` returns `None` and the caller falls
  back to `select_top(select, context, scores)` — V6's own exact, unmodified choice over the same options, so
  the fallback is always a fully legal, already-proven decision, never a degraded one.
- **Defense in depth**: `final_candidate_agent_v11.py` still wraps the whole policy in the standard
  `safety_wrapper` (legal-selection guarantee) → `timeout_shield` (2.0s per-decision / 600s match budget,
  independent of and outside V11's own 0.2s internal budget) chain, unchanged from V6/V1. Even if the internal
  macro-lookahead safeguard were somehow bypassed, this outer shield still guarantees the match-level budget.

---

## 5. Local Self-Play Test Results

Two separate local harnesses were run (both real `cg.dll` engine self-play, no Kaggle interaction):

### 5.1 Raw policy chain (`src.agents.dragapult_agent_v11`), 3 games vs. `lucario_ex_agent`

`tools/v11_selfplay_smoke_test.py --games 3`, first-player slot alternated:

| Game | V11 slot | Outcome | Turns | Steps | Elapsed |
|---|---|---|---|---|---|
| 0 | 0 | v11_win | 13 | 157 | 2.3s |
| 1 | 1 | v11_win | 10 | 155 | 1.7s |
| 2 | 0 | v11_loss | 10 | 145 | 1.7s |

- **0 crashes, 0 aborted games** — every game reached a real result (win/loss), none hit the 800-step cap.
- **Memory**: RSS 35.1 MB → 40.6 MB over 3 games (+5.6 MB total, no runaway growth pattern) — consistent with
  the prior prototype's own negligible-growth finding for this same deep-copy-per-candidate design.
- **Latency, 129 in-scope MAIN decisions** (macro-lookahead fired on all 129, 0 fallbacks this run):

  | Metric | Value |
  |---|---|
  | Median | **32.6 ms** |
  | Mean | 41.4 ms |
  | p95 | 96.4 ms |
  | Max | 222.2 ms |
  | Max chain length reached | 28 (cap = 30, cap never hit) |

  The median matches the prior shadow-mode research prototype's own N=5 median (32.6 ms) almost exactly —
  expected, since V11 reuses the same underlying mechanism, now live-driving the game instead of shadowing it.

### 5.2 Full production stack (`main_v11.py`), 2 games vs. `lucario_ex_agent`

`tools/tournament.py --agent-a main_v11.py --agent-b src.agents.lucario_ex_agent --games 2`:

| Game | a_slot0 | Outcome | Turns | Steps |
|---|---|---|---|---|
| 1 | True | main_v11 win | 13 | 197 |
| 2 | False | lucario_ex_agent win | 19 | 195 |

Both games completed cleanly through the entire `main.py → final_candidate_agent_v11 → safety_wrapper →
timeout_shield → policy` chain — confirms the macro-lookahead addition does not break the standard safety
composition every other version ships with.

**Sample-size caveat** (per this project's standing process rule): 5 total games is a functional smoke test,
not a performance claim. No win-rate conclusion is drawn from these results — they exist only to verify "does
it crash, does it leak memory, does it complete turns," which is exactly what this deliverable asked for.

---

## 6. Known Limitations (accepted for V11, not fixed)

1. **Opponent deck is unknown** — `_begin_shared_search`'s `opponent_deck_hint` is set to V11's own `DECK`
   (a mirror-match proxy), since the real opponent's 60-card list is hidden information in a live match. This
   only affects the determinization of unseen opponent cards (hand/deck/prize sampling) used to build the
   search sandbox, not any of V11's own decision logic.
2. **RNG non-independence** across the 5 branches sharing one `search_begin` root (§4) — accepted per the
   governing task.
3. **Timeout is a soft, between-candidate check**, not a hard mid-call interrupt (§4) — the observed 222ms max
   slightly exceeds the nominal 200ms target on a slow individual candidate; still negligible against the
   600s match budget, and backed by the independent outer `timeout_shield`.
4. **No outcome/win-rate evidence** — this task explicitly scoped to "build and package it" plus a functional
   smoke test, not a win-rate evaluation against V6. Whether macro-action search actually improves on V6's
   real ladder performance is an open question for a future, explicitly-scoped evaluation phase.

---

## 7. Submission Packaging

`tools/build_submission_challenger.py` extended with a `v11` entry (`DECK_SOURCE["v11"] =
"dragapult_ex.csv"`, matching V6). Build run and validated:

```
python tools/build_submission_challenger.py --version v11
```

- `main_v11.py` imports cleanly, `agent()` callable, `DECK` has 60 cards.
- `decks/dragapult_ex.csv` passes real `battle_start` legality validation.
- Staged directory (`submission/_staging_v11/`) assembled and runs standalone (no dev-path dependency).
- Archive created: **`submission/challenger_v11_20260814T020515Z.tar.gz`** (2.00 MB, 74 members, top-level
  entries `main.py`, `deck.csv`, `cg`, `src`, `decks` — matches every prior version's expected structure).

**Not uploaded to Kaggle** — this tool only builds the local archive, per its own design (never calls `kaggle
competitions submit`) and per this task's explicit instruction to wait for user approval.

---

## 8. Next Step

Waiting for explicit user go-ahead before any Kaggle submission or larger-scale evaluation. If pursued, the
natural follow-up (per this project's standing checkpoint-and-wait process) would be a real A/B — V11 vs. V6,
first-player alternated, enough games for a non-preliminary sample — to get the win-rate evidence this report
does not attempt to fabricate.
