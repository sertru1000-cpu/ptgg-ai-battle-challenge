# V10 Implementation Report — Strict Survival-Retreat Ablation Study

**Status**: local build only, not submitted to Kaggle, per the governing task's explicit instruction.
**Files touched**: only new, V10-suffixed files. V6/V7/V8/V9 and their shared decks (`decks/dragapult_ex.csv`,
`decks/lucario_ex.csv`) were read-only inputs to this session and were never edited (confirmed by file
mtimes — see §9).

---

## 1. Executive Summary

Real-ladder ratings collapsed across V4 → V6 → V8 → V9 (~736.9 → ~717 → ~551 → ~548). V8 introduced a
hard-coded "Survival Retreat" heuristic that overrides ATTACK with RETREAT whenever a 2-Prize Active faces
a confirmed lethal hit and a ready Bench replacement exists; V9 inherited and expanded it to 1-Prize Actives
while also switching decks to Mega Lucario ex. Because V8/V9 changed **two things at once** (the heuristic
*and* the deck), the regression's cause was confounded and untested.

V10 is a controlled ablation that isolates the heuristic. It is built by forking
`src/agents/dragapult_policy_v7.py` — the V6/V7 engine, which contains all three proven Phantom Dive fixes
and **predates** the Survival Retreat heuristic entirely (V8 is where that heuristic was first written) —
and changing exactly one thing: the deck path, pointed at a new, modernized Dragapult ex decklist
cross-referenced against the real Top-100-ladder canonical Dragapult ex build
(`TOP100_META_AUDIT.md` Part 8/11, `results/meta/archetype_canonical.csv`). No engine/scoring code was
written, removed, or modified beyond what forking from V7 already excludes. All 4 required local validation
tests pass (§8). The V8/V9 Survival Retreat override is structurally absent from V10 (no such methods exist
on `DragapultPolicy`) and behaviorally confirmed unreachable (V10 attacks on the exact fixture where V8
forcibly retreats — §6). All three Phantom Dive fixes remain byte-identical to V7 (§7). The deck change is a
real, verified 60-card modernization (§3/§4).

V10 answers the ablation's single question by construction, not by running games this phase: **if V10's
real-ladder rating recovers toward V4/V6 levels, the Survival Retreat heuristic (not the deck, not any other
engine change) is confirmed as the dominant cause of the V8/V9 collapse.** Submitting V10 to the ladder to
observe that outcome is explicitly out of scope for this phase per the governing task.

---

## 2. V6 → V10 Architecture Comparison

V10 is forked from **V7**, not V6 directly, because Objective 2 requires preserving *all three* proven
Phantom Dive fixes, and only V7 (not V6) contains FIX #3. V7 itself contains zero Survival Retreat code
(that was first written in V8), so basing V10 on V7 satisfies both "predates V8" and "has all the fixes"
simultaneously — there is no conflict between the two requirements.

| Aspect | V6 | V7 | V8 | V9 | **V10** |
|---|---|---|---|---|---|
| Phantom Dive FIX #1 (hp==10) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Phantom Dive FIX #2 (Active damage=0) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Phantom Dive FIX #3 (Bench damage=0, i≥1) | ❌ | ✅ | ✅ | ✅ | ✅ |
| Survival Retreat heuristic | ❌ | ❌ | ✅ (2-Prize) | ✅ (expanded, 1-Prize) | ❌ |
| Deck | `decks/dragapult_ex.csv` | `decks/dragapult_ex.csv` | `decks/dragapult_ex.csv` | `decks/lucario_ex.csv` (Mega Lucario ex) | **`decks/dragapult_ex_v10.csv`** (modernized Dragapult ex) |
| `policy_weights.py` profile | BALANCED | BALANCED | BALANCED | BALANCED | BALANCED (unchanged) |
| Class name | `DragapultPolicy` | `DragapultPolicy` | `DragapultPolicy` | `DragapultPolicy` | `DragapultPolicy` (unchanged) |

New files created for V10 (mirroring the exact V6/V7/V8 entry-point-chain pattern, no shared file modified):

- `src/agents/dragapult_policy_v10.py` — forked from `dragapult_policy_v7.py`; diffs only in the module
  docstring and the `_DECK_PATH` constant (verified byte-for-byte, §9).
- `src/agents/dragapult_agent_v10.py` — thin binding, identical structure to `dragapult_agent_v7.py`.
- `src/agents/final_candidate_agent_v10.py` — identical safety-wrapper composition to
  `final_candidate_agent_v7.py` (`safety_wrapper` → `timeout_shield` → policy).
- `main_v10.py` — local entry point; uses V9's (not V7's) deck.csv-matching safeguard pattern, since V10
  (like V9) does not share the repo-root `deck.csv`'s decklist and must not silently load the wrong deck.
- `decks/dragapult_ex_v10.csv` — the new 60-card decklist (§3).

---

## 3. Exact V10 Dragapult ex 60-Card Decklist

Sourced directly from `results/meta/archetype_canonical.csv`'s Dragapult ex row — the single most-played
exact real-ladder decklist (337 games, 55.19% overall / 57.07% recent-period win rate, per
`TOP100_META_AUDIT.md` Part 3/8/11) — cross-referenced against `decks/dragapult_ex.csv` (the current V8/V9
build) to identify additions/removals. All card IDs verified directly against the live engine
(`cg.api.all_card_data()`), not the audit CSV alone.

| Card | Card ID | Qty | Category |
|---|---:|---:|---|
| Dreepy | 119 | 4 | Basic Pokémon |
| Drakloak | 120 | 4 | Stage 1 Pokémon |
| Dragapult ex | 121 | 3 | Stage 2 Pokémon (ex) |
| Fezandipiti ex | 140 | 1 | Basic Pokémon (ex) |
| Munkidori | 112 | 2 | Basic Pokémon |
| Budew | 235 | 2 | Basic Pokémon |
| Meowth ex | 1071 | 1 | Basic Pokémon (ex) |
| Buddy-Buddy Poffin | 1086 | 4 | Item |
| Night Stretcher | 1097 | 2 | Item |
| Crushing Hammer | 1120 | 4 | Item |
| Ultra Ball | 1121 | 4 | Item |
| Poké Pad | 1152 | 4 | Item |
| Unfair Stamp | 1080 | 1 | Item (ACE SPEC) |
| Boss's Orders | 1182 | 3 | Supporter |
| Crispin | 1198 | 3 | Supporter |
| Judge | 1213 | 1 | Supporter |
| Lillie's Determination | 1227 | 4 | Supporter |
| Dawn | 1231 | 1 | Supporter |
| Jamming Tower | 1246 | 2 | Stadium |
| Basic {R} (Fire) Energy | 2 | 4 | Basic Energy |
| Basic {P} (Psychic) Energy | 5 | 4 | Basic Energy |
| Basic {D} (Darkness) Energy | 7 | 2 | Basic Energy |
| **Total** | | **60** | |

**Legality**: confirmed LEGAL via `tools/deck_validator.py`'s real `battle_start` check — exactly 60 cards,
1 ACE SPEC (Unfair Stamp), no name over the 4-copy cap (Basic Energy exempt), ≥1 Basic Pokémon. See §8 Test 1.

---

## 4. Deck Changes vs. the Previous Dragapult Baseline (`decks/dragapult_ex.csv`)

**Note on a discrepancy found during this session**: `TOP100_META_AUDIT.md` Part 11 states Buddy-Buddy
Poffin is "**0** — Absent from our build entirely" in `decks/dragapult_ex.csv`. Direct inspection of that
file (as it exists on disk today) shows **4 copies already present** (card ID 1086 × 4). This is a real,
unresolved inconsistency between the audit document and the current state of the deck file — reported here
per the governing task's "report but don't fix" instruction for unrelated findings, not corrected. It does
not affect V10: the mandatory Poffin×4 requirement is satisfied either way, since the canonical build V10
adopts also runs exactly 4.

| Card | V8/V9 build (`dragapult_ex.csv`) | V10 build | Change |
|---|---:|---:|---|
| Buddy-Buddy Poffin | 4 | 4 | unchanged (already present, contra the audit doc's stale "0" claim above) |
| Munkidori | 0 | **2** | **added** (mandatory inclusion) |
| Dawn | 0 | **1** | **added** (canonical-build staple, Part 8) |
| Judge | 0 | **1** | **added** (canonical-build staple, Part 8) |
| Jamming Tower | 0 | **2** | **added**, replaces Team Rocket's Watchtower (Part 7: functionally different stadium, does not interact with the Crustle immunity tech) |
| Basic {D} (Darkness) Energy | 0 | **2** | **added** (canonical build's 3rd energy type) |
| Poké Pad | 3 | 4 | **+1** (matches canonical) |
| Latias ex | 1 | **0** | **removed** (explicit removal candidate; absent from the canonical build) |
| Rare Candy | 2 | **0** | **removed** (absent from the canonical build; V10's evolution line runs on Dreepy/Drakloak/Buddy-Buddy Poffin consistency instead) |
| Lucky Helmet | 1 | **0** | **removed** (explicit removal candidate; absent from the canonical build) |
| Brock's Scouting | 2 | **0** | **removed** (absent from the canonical build) |
| Team Rocket's Watchtower | 2 | **0** | **removed**, replaced by Jamming Tower above |
| Crispin | 4 | 3 | **-1** (matches canonical) |
| Dreepy / Drakloak / Dragapult ex / Fezandipiti ex / Budew / Meowth ex / Night Stretcher / Crushing Hammer / Ultra Ball / Unfair Stamp / Boss's Orders / Lillie's Determination / Basic Fire / Basic Psychic | unchanged | unchanged | no change |

Net: 9 card-slots removed (Latias ex ×1, Rare Candy ×2, Lucky Helmet ×1, Brock's Scouting ×2, Team Rocket's
Watchtower ×2, Crispin ×1) exactly balanced by 9 card-slots added (Munkidori ×2, Dawn ×1, Judge ×1, Jamming
Tower ×2, Basic Darkness Energy ×2, Poké Pad ×1) — 60 cards preserved.

**Engine-compatibility note on the added Darkness Energy**: queried live against `cg.api.all_attack()` —
none of this deck's Pokémon (Dragapult ex, Fezandipiti ex, Meowth ex, Munkidori) require Darkness-typed
energy specifically; their costs are `[2,5]` (Fire+Psychic, Phantom Dive), `[0]`/`[0,0,0]`/`[5,0]` (Colorless
slots). Darkness Energy pays any Colorless slot exactly like Fire/Psychic already do — verified mechanically
via the Test 4 real-game smoke test (§8), where V10 attacked, evolved, and played Poffin normally. The
engine's `hand_score`/`attach_score` functions (untouched, deck-independent) have no bespoke branch for
Darkness Energy's card ID, identical to how they already have none for Munkidori itself — this is
pre-existing generic fallback behavior for any card without a dedicated branch, not a new heuristic added by
this session, and is reported here rather than "fixed" per the governing task's scope discipline.

---

## 5. Deck Composition Confirmation

- ✅ **Buddy-Buddy Poffin ×4** present (card ID 1086).
- ✅ **Munkidori** present (card ID 112, ×2).
- ✅ **Dragapult ex is the active archetype** (card ID 121, ×3; plus its full Dreepy→Drakloak→Dragapult ex
  evolution line).
- ✅ **Lucario-specific logic is absent**: `src/agents/dragapult_policy_v10.py` never imports
  `lucario_policy_v9.py` or any Lucario-specific module; `Mega_Lucario_ex` (card ID 678) does not appear
  anywhere in `decks/dragapult_ex_v10.csv` (verified programmatically, §8 Test 1). V10's engine is a direct
  fork of V7 (Dragapult's own pre-V8 engine), never V9's Lucario engine — there was never a Lucario code path
  to remove.

---

## 6. Survival Retreat Ablation

**Exact V8/V9 code that does NOT exist in V10** (never copied in, since V10 forks V7 which predates it):

- `DragapultPolicy._wants_survival_retreat()` — the ~130-line method (`dragapult_policy_v8.py` lines
  479–610) that detects a confirmed, currently-visible lethal hit on a 2-Prize (V8) or 1-Prize-eligible (V9)
  Active with a ready Bench replacement, and forces `do_switch = True` even when a legal ATTACK is on offer.
- `DragapultPolicy._bench_pokemon_is_ready()` — the static helper (`dragapult_policy_v8.py` lines 458–477)
  that determines whether a Bench Pokémon can legally fire a damaging attack right now.
- The `__init__` anti-thrash bookkeeping state: `_prev_active_serial`, `_survival_retreat_pending`,
  `_survival_retreat_op_serial`, `_last_survival_retreat_serial`, `_last_survival_retreat_hp`,
  `_last_survival_retreat_op_serial`, `survival_retreat_log` (`dragapult_policy_v8.py` lines 263–276).
- The wiring inside `agent()` that calls the hook and updates that bookkeeping every turn
  (`dragapult_policy_v8.py` lines 978–1012).

**Confirmed unreachable** two independent ways (§8 Test 3):

1. **Structural**: `hasattr(V10Policy, "_wants_survival_retreat")` is `False`; a fresh `V10Policy` instance
   has no `survival_retreat_log` attribute at all. There is no code to disable — it was never present.
2. **Behavioral**: replaying V8's own `verify_v8_survival_retreat.py` "lethal_ready_bench_dragapult" fixture
   (a 2-Prize Dragapult ex at 200/320 HP facing a confirmed 230-damage lethal hit, with a ready Dreepy on the
   Bench, and a legal Jet Headbutt attack also on offer) — **V8 selects RETREAT** (`action=[0]`), **V10
   selects the ATTACK option instead** (`action=[1]`), on the byte-identical input.

**Generic pre-V8 retreat logic preserved, not removed**: `_wants_defensive_retreat()` (V4/V5's own hook) is
present in V10 unchanged, and was directly exercised (§8 Test 3): with no legal attack on offer
(`can_attack=False`) and the opponent's visible attack clearing the HP-fraction threshold, V10's Active
still retreats (`action=[0]`) via this ordinary, pre-existing mechanism. This confirms the ablation removed
*only* the V8/V9 hard-coded override, not retreat behavior in general — RETREAT remains a normal, reachable
option in V10 whenever V6/V7's own logic (the forced-bench-attacker switch, or `_wants_defensive_retreat`)
already called for it.

---

## 7. Phantom Dive Preservation

All three fixes, confirmed present and byte-identical to V7 (§8 Test 2, `tools/verify_phantom_dive_v10_fix.py`):

1. **hp==10 anti-KO-penalty fix (FIX #1)**: confirmed active — a 10 HP lethal Bench target is secured as a
   free KO, not penalized (`score -= 100000`, the pre-V6 regression, does not exist anywhere in V10).
2. **Active/Bench damage-premise separation (FIX #2 + FIX #3)**: confirmed active for both the opponent's
   Active (`i==0`) and every Bench Pokémon (`i>=1`) — Phantom Dive's planner never treats a single target as
   receiving the card data's flat `damage=200`; an unreachable 110 HP Bench target is correctly NOT
   classified as an already-secured kill (V6, which lacks FIX #3, does misclassify it on the identical
   fixture — confirmed as a live contrast in the same test run).
3. **Target-selection behavior**: the combinatorial counter-placement planner (`counter_indices` combo
   search) is untouched; no MCTS/minimax/search/lookahead was added. 8 of V7's own regression fixtures
   (multi-target combos, Active short-circuit, immune-target exclusion, non-Phantom-Dive paths) produce
   **exactly byte-identical output** between V7 and V10 on every one.

No regression found.

---

## 8. Local Test Results

All 4 tests pass. Full transcripts below (abbreviated; scripts are in `tools/`).

**Test 1 — Deck loading** (`tools/verify_v10_deck_load.py`): 11/11 checks PASS. Deck loads through the full
runtime chain, is exactly 60 cards, is engine-legal, contains Buddy-Buddy Poffin ×4, Munkidori, Dragapult ex,
zero Mega Lucario ex, and differs from both V8's and V9's decks (a real change, not a no-op).

**Test 2 — Phantom Dive** (`tools/verify_phantom_dive_v10_fix.py`): 13/13 checks PASS, reusing V7's own
proven forensic suite (`tools/verify_phantom_dive_v7_fix.py`) against V10. Every fixture (hp==10 fix,
Active/Bench separation, combo search, immune-target handling, non-Phantom-Dive paths) is byte-identical
between V7 and V10.

**Test 3 — Survival Retreat removal** (`tools/verify_v10_no_survival_retreat.py`): 8/8 checks PASS.
Structural absence confirmed (no `_wants_survival_retreat`/`_bench_pokemon_is_ready`/`survival_retreat_log`);
behavioral contrast confirmed on V8's own fixture (V8 retreats, V10 attacks); generic pre-V8
`_wants_defensive_retreat` confirmed still functional.

**Test 4 — Basic gameplay** (`tools/verify_v10_real_game_smoke_test.py`): 4/4 real games (self-play, vs.
`abomasnow_agent`, vs. V7 head-to-head, vs. `generic_mewtwo_agent`) complete without a crash, no infinite
loop (all finish well under the 2000-step cap, 169–222 steps observed), every selected action is legal.
Across the 4 games V10 attacked, played Buddy-Buddy Poffin, and evolved (Dreepy→Drakloak or
Drakloak→Dragapult ex) at least once each; Phantom Dive's DAMAGE_COUNTER_ANY selection fired 12–30 times per
game, confirming the attack (and its fixed planner) is exercised for real, not just in synthetic fixtures.

---

## 9. Exact Source Diff Summary

**Files changed relative to V7** (`diff src/agents/dragapult_policy_v7.py src/agents/dragapult_policy_v10.py`):
1 file, 24 lines added / 4 lines removed. All 4 removed lines are the old module-docstring opening (replaced
by an expanded, V10-specific docstring); the only non-docstring line changed is the `_DECK_PATH` constant
(`dragapult_ex.csv` → `dragapult_ex_v10.csv`). **Zero functions changed.**

**Files changed relative to V6** (`diff src/agents/dragapult_policy_v6.py src/agents/dragapult_policy_v10.py`):
1 file, 82 lines added / 33 lines removed. The bulk is docstring text (documenting FIX #3, inherited
unchanged from V7 — expected, since V10 must retain all three fixes per Objective 2). The only function-body
change is inside `main_option_proc` (FIX #3's gate: `if i == 0 and self.can_main_attack:` →
`if self.can_main_attack:`), identical to V7's own change relative to V6, plus the `_DECK_PATH` constant.
**One function changed** (`main_option_proc`), and only in the way V7 already changed it.

**New files created** (mirror V6/V7/V8's own established pattern, no existing file's content altered):
`src/agents/dragapult_policy_v10.py`, `src/agents/dragapult_agent_v10.py`,
`src/agents/final_candidate_agent_v10.py`, `main_v10.py`, `decks/dragapult_ex_v10.csv`, plus 4 validation
scripts in `tools/` (`verify_v10_deck_load.py`, `verify_phantom_dive_v10_fix.py`,
`verify_v10_no_survival_retreat.py`, `verify_v10_real_game_smoke_test.py`).

**Answers to the required audit questions**:

| # | Question | Answer |
|---|---|---|
| 1 | Files changed | 0 existing files changed; 9 new files created (5 runtime + 4 test scripts) |
| 2 | Functions changed | 0 relative to V7; 1 (`main_option_proc`, FIX #3's gate) relative to V6 — inherited from V7, not new |
| 3 | Number of changed lines | vs. V7: 28 (24+/4-); vs. V6: 115 (82+/33-), mostly docstring |
| 4 | Policy weights changed? | **NO** — `policy_weights.py` untouched; V10 uses `BALANCED`, identical to V2/V6/V7/V8/V9 |
| 5 | Generic attack scoring changed? | **NO** |
| 6 | Generic retreat scoring changed? | **NO** — `_wants_defensive_retreat` byte-identical to V6/V7 |
| 7 | Survival Retreat heuristic still reachable? | **NO** — structurally absent (§6) |
| 8 | V6/V7 hp==10 fix present? | **YES** (§7, §8 Test 2) |
| 9 | Phantom Dive Active/Bench separation present? | **YES** (§7, §8 Test 2) |
| 10 | Lucario-specific logic reachable in V10? | **NO** (§5) |
| 11 | Deck changed? | **YES** (§3, §4) |

**Unrelated findings reported, not fixed** (per governing-task scope discipline):

- The Buddy-Buddy Poffin discrepancy between `TOP100_META_AUDIT.md` Part 11 and the actual current state of
  `decks/dragapult_ex.csv` (§4).
- `hand_score()`/`attach_score()` (deck-independent, untouched) have no dedicated scoring branch for
  Munkidori or the newly-added Basic {D} Energy — pre-existing generic fallback behavior, not a new gap
  introduced by this session (§4).

---

## 10. Local Submission Package

Following the same convention already established for V2–V9, V10 was packaged locally via
`tools/build_submission_challenger.py --version v10` (extended with a `v10` entry in that script's
`VALID_VERSIONS`/`DECK_SOURCE`, the only edit made to a pre-existing shared file this session — purely
additive, parameterization-only, no existing version's packaging behavior changed). This produced:

- `submission/_staging_v10/` — the assembled, standalone-runnable submission directory (`main.py`,
  `deck.csv`, `cg/`, `src/`, `decks/`).
- `submission/challenger_v10_20260813T190604Z.tar.gz` (1.99 MB, 71 archive members) — validated by the same
  script: `main_v10.py` imports cleanly and exposes a 60-card `DECK`; `decks/dragapult_ex_v10.csv` passes
  real `battle_start` legality; the staged copy runs fully standalone (no dependency on the dev-only
  `data/official/` path); the archive's top-level layout matches the grader's expected shape
  (`main.py`/`deck.csv`/`cg`/`src`/`decks`, no nested `main.py`).

This is a **fully local, non-uploading packaging step** — the script never calls
`kaggle competitions submit` or any other Kaggle API — and is explicitly consistent with the governing
task's "build/package V10 locally only, do NOT submit to Kaggle" instruction. Uploading remains a separate,
explicit action left to the user.

---

## 11. Final Verdict

**V10 is a clean V6-baseline ablation with a modern Dragapult deck and without the V8/V9 Survival Retreat
heuristic.**
