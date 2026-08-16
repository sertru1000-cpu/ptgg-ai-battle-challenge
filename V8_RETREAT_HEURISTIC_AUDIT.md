# V8 — 2-Prize Defensive Retreat / Survival Heuristic: Implementation & Validation Report

**Date**: 2026-08-13. **Scope**: V8 = V7 + exactly ONE new strategic addition — a context-aware
heuristic that lets a 2-Prize Active retreat (or decline an available attack) to avoid donating
2 Prizes to a guaranteed, currently-visible lethal hit, even when we could still legally attack
this turn. Per instructions this is a causal test of a stated hypothesis, not a tuning pass, and
**V8 has not been uploaded to Kaggle and V7 has not been modified.**

---

## 1. The hypothesis, and what the Step-1 audit found

**Hypothesis under test**: "When our Active 2-Prize Pokémon is facing a reliable lethal threat
and we have a genuinely playable attacker on the Bench, V2/V6/V7 sometimes incorrectly choose
ATTACK instead of RETREAT, unnecessarily donating 2 Prize cards."

Before writing any new code, the existing production path for ATTACK / RETREAT / switching-Item
scoring was traced end to end in `src/agents/dragapult_policy_v7.py`:

- **The MAIN decision is a single flat scoring pass.** Every legal action this turn (ATTACK,
  RETREAT, PLAY a card, ATTACH energy, EVOLVE, use an ABILITY) is scored once in the same
  `for o in select.option:` loop (`dragapult_policy_v7.py:945-950` in this file's original
  line numbers), and `select_top()` just returns the single highest-scoring option
  (`maxCount=1` for this decision). ATTACK's score is **the raw `attackId` integer**
  (`score = o.attackId`, line 946) — a leftover tie-break, not a value judgement; it exists only
  because the two Pokémon in this deck with >1 attack happen to have higher attack IDs on their
  higher-damage attack (`policy_weights.py`'s own docstring documents this). RETREAT's score is
  a flat `10000 if do_switch else -1` (line 944) — i.e. a single boolean gate, not a graded score.
  Since every real attackId in this 60-card deck is ≤ 1546 (Meowth ex's Tuck Tail), `do_switch =
  True` **always** outscores any legal ATTACK here — this is the existing, already-relied-upon
  mechanism V4/V5's own hook already uses, and V8 reuses it rather than inventing a new constant
  (see §3, Step 3).
- **`do_switch` (the boolean that drives RETREAT's score) is computed once**, at
  `dragapult_policy_v7.py:770-774` (original numbering):
  ```python
  do_switch = not self.can_main_attack and (
      self.bench_attacker or (active_id != Budew and field_counts[Budew] >= 1 and state.turn >= 2)
  )
  if not do_switch:
      do_switch = self._wants_defensive_retreat(my_active, op_active)
  ```
  Three pre-existing reasons can set it True: (a) a charged Bench Dragapult ex is ready and
  Phantom Dive isn't this attack, (b) a "promote Budew" board-development tech, or
  (c) `_wants_defensive_retreat` (V4/V5's own hook, `dragapult_policy_v7.py:394-412`).
- **`_wants_defensive_retreat` is the load-bearing finding.** Its very first real check is:
  ```python
  def _wants_defensive_retreat(self, my_active, op_active) -> bool:
      if not self.weights.defensive_retreat_enabled:
          return False
      if self.can_attack:
          return False  # never give up a legal attack this turn to retreat defensively
      ...
  ```
  `self.can_attack` is `True` whenever **any** ATTACK option is offered this decision — not just
  a *good* attack, not just Phantom Dive, any attack at all. This means the hook that already
  exists to protect a threatened Active **can never fire in exactly the scenario the hypothesis
  describes** (we could attack, but attacking accomplishes nothing worth losing the Pokémon
  over). This is a real, source-verified gap, not a guess — confirmed by direct code trace
  before any new code was written, and independently reconfirmed by the synthetic scenario suite
  (§6) and by real self-play (§7).
- **Retreat legality itself is already engine-validated.** `self.can_switch` is only ever `True`
  when `OptionType.RETREAT` is actually present in `select.option` this decision — the engine
  itself is the source of truth for retreat legality (enough retreat cost payable, not
  asleep/paralyzed, not already retreated this turn, etc.). No retreat-legality logic needed to
  be duplicated.
- **Bench/switch-target scoring is completely separate and untouched.** Once `do_switch=True`
  wins the MAIN decision, a *later* `SWITCH`/`TO_ACTIVE` select decides **which** Bench Pokémon
  actually becomes Active (`dragapult_policy_v7.py:793-814`, original numbering) — Dragapult ex
  preferred (+50000), then Drakloak/Budew/etc., plus `energy_count*1000 + hp*(1+preservation_bias)`.
  V8 does not read, call, or modify this block at all; it only ever decides **whether** to retreat,
  never **to whom**.
- **No "Switch" (or equivalent bypass-retreat-cost) Item card exists anywhere in this 60-card
  deck.** `decks/dragapult_ex.csv` / `dragapult_policy_v8.py`'s own `DECK` constant were checked
  directly — the full Item list is Rare Candy, Unfair Stamp, Buddy Buddy Poffin, Night Stretcher,
  Crushing Hammer, Ultra Ball, Poke Pad, Lucky Helmet. None discards energy for a Retreat-cost-free
  switch. See §8 for how this is handled.

---

## 2. Exact activation conditions (Step 2)

`DragapultPolicy._wants_survival_retreat(my_active, op_active, my_bench)` in
`src/agents/dragapult_policy_v8.py` returns `True` — and only then does `do_switch` get a chance
to become `True` through this new path — **only if every one of the following holds**, checked in
this order, any failure returning `False` immediately:

| # | Condition | Implementation |
|---|---|---|
| D | A retreat is legally on offer *right now* | `self.can_switch` (engine-validated, §1) |
| A | Our Active is 2-Prize: `ex`, **not** `megaEx` | `my_card.ex and not my_card.megaEx` |
| B/C | The opponent's Active has a real attack, with **currently visibly attached** energy (`op_active.energies`, never the opponent's hidden hand), whose card-data damage ≥ our Active's **current** HP | loop over `op_card.attacks` / `_attack_table`, `op_energy_count >= len(atk.energies) and atk.damage >= my_active.hp` |
| — | *(not a lethal-detection loophole, see §9)* Phantom Dive (attackId 154) is excluded from this loop — its `damage=200` card-data field is fictional for the Active | `if aid == 154: continue` |
| — | Not giving up a winning trade: our Active cannot itself KO the opponent's Active this turn with its own attached energy | mirror-image loop over `my_card.attacks`, same Phantom-Dive exclusion |
| D/E | At least one Bench Pokémon is genuinely playable: already has enough attached energy for ≥1 of its own real (`damage>0`) attacks | `_bench_pokemon_is_ready()`, `any(...)` over `my_bench` |
| F | Energy economy is explicitly inspected and logged, but is **not** an independent hard gate beyond E — see §9 for the reasoning | `retreat_cost = my_card.retreatCost; energy_lost = min(retreat_cost, my_energy_count)` |
| STEP 4 | Anti-thrash: not re-firing for the exact same Pokémon, at the exact same HP, facing the exact same opponent Pokémon, we already retreated to save | serial+HP+opponent-serial memory, see §5 |

The hook is called **only** from the actual MAIN decision (`context == SelectContext.MAIN`),
mirroring how `main_option_proc` itself is already scoped — it is a pure, side-effect-free
predicate for every other select context (this matters because `_wants_defensive_retreat` above
is, by contrast, evaluated unconditionally on every call in the pre-existing code; V8's new hook
has state-mutating side effects — the anti-thrash memory and the diagnostic log — so it is
explicitly gated to avoid spurious/duplicate log entries on non-MAIN decisions).

**Step 5 (1-Prize exclusion)**: enforced by condition A. Per the literal spec wording ("2-Prize"),
this also excludes 3-Prize Mega ex Pokémon — verified against a real Mega ex card in the engine's
pool (`Mega Venusaur ex`, id 652) in the validation suite (§6).

---

## 3. Why this is not a blind `+50000` (Step 3)

V8 does not introduce a new score constant at all. It reuses the **existing, already-vetted**
`do_switch = True → RETREAT scores 10000` mechanism that `_wants_defensive_retreat` already
relies on (§1) — the only new thing is the **gating logic** that decides when that boolean
becomes true. This satisfies Step 3's intent (a clearly isolated, conditionally-gated bonus, not
a global reweighting) while reusing a value the codebase already trusts to beat every legal
ATTACK score in this specific 60-card deck.

No switching-Item logic was written (§1: the deck has none), so there is nothing to compare a
manual retreat against for this specific deck; see §8 for how this is handled honestly rather
than with untested dead code.

---

## 4. Step 6 — energy economy, worked through

Step 6 asks the heuristic to "explicitly inspect retreat cost" and gives a worked example where a
costly retreat plus an unready Bench replacement should **not** force a retreat. Real retreat
costs in this deck (`cg.api.all_card_data()`, queried live, not guessed):

| Card | HP | retreatCost |
|---|---|---|
| Dragapult ex | 320 | 1 |
| Fezandipiti ex | 210 | 1 |
| Meowth ex | 170 | 1 |
| Latias ex | 210 | **2** |

**Design decision** (documented in code and here, not silently baked in): condition F computes
and logs `retreat_cost`/`energy_lost`, but is **not** an independent hard gate once condition E
(genuinely ready Bench replacement) already holds. Reasoning: once a real replacement exists,
losing the retreating 2-Prize Pokémon's attached energy is *always* cheaper than losing the
Pokémon itself plus its 2 Prizes to a **confirmed** lethal hit — energy can be reattached in
future turns, a knocked-out ex card and its prizes cannot be recovered. Re-reading Step 6's own
negative worked example (`50 HP, costly retreat, Bench attacker cannot attack, no Switch Item →
should not force it`) confirms this: the example bundles a costly retreat together with an
**unready** Bench replacement, and it is condition E — not the energy cost — that is actually
doing the disqualifying work there. The validation suite includes both the literal positive
version of this example (`full_energy_wipe_retreat_still_fires_with_ready_bench`) and the literal
negative version reconstructed exactly as worded (`full_energy_wipe_plus_unready_bench_blocks`) —
see §6.

---

## 5. Step 4 — the anti-thrash guardrail, precisely

Two structural facts make same-turn ping-ponging (`RETREAT → RETREAT → RETREAT`) impossible by
construction, not just discouraged: (1) the engine only offers `OptionType.RETREAT` once per
turn (`self.can_switch` becomes `False` immediately after retreating), and (2) `do_switch`'s
consumer (`RETREAT` option scoring) only exists inside a single MAIN decision.

The harder case — cross-turn thrash, e.g. retreating Pokémon A→B this turn, then B→(something)
next turn merely because B is *also* threatened — is handled with real state, not a turn-count
cooldown:

- `_survival_retreat_pending`: set the instant the hook fires, cleared the moment a **different**
  Active Pokémon is subsequently observed (i.e. the retreat has actually resolved).
- On resolution, `_last_survival_retreat_serial` / `_hp` / `_op_serial` snapshot **exactly** who we
  retreated into, at what HP, facing which specific opponent Pokémon (by serial, a unique
  per-card-instance identifier — not just species/id).
- The next time the hook considers firing, if the currently-threatened Pokémon's serial, HP, *and*
  the opponent's serial all match that snapshot exactly, it declines — nothing has actually
  changed, so re-litigating would just thrash. Any one of those three differing (the Pokémon took
  damage, a different Pokémon is now threatened, or the opponent switched to a different threat)
  is treated as genuinely new information and is never blocked.

This state resets on `state.turn == 0` (a new game), so it can never leak across battles for a
reused policy instance (e.g. `tools/tournament.py`).

Validated end-to-end through `agent()` (not just the isolated method) in
`tools/verify_v8_survival_retreat.py`'s PART C — see §6.

---

## 6. Validation results (Step 9)

`tools/verify_v8_survival_retreat.py`, three parts, **all checks pass**:

- **PART A — Phantom Dive regression** (Step 7): re-runs V7's own regression fixtures
  (`tools/verify_phantom_dive_v7_fix.py`'s exact scenarios: 10-HP fallback KO, multi-target combo
  plan, both reconstructed forensic rows, the Active short-circuit case, the immune-target case,
  the `plan_a`/`plan_b` false-belief isolation case, and the no-RETREAT-offered MAIN/DAMAGE_COUNTER
  paths) against **both** V7 and V8, asserting byte-identical output. **9/9 checks pass, 0
  differences** — Phantom Dive behavior (all three V6/V7 fixes: the `hp==10` fallback, Active
  bench-damage separation, and the i≥1 bench-target planner fix) is unchanged in V8.
- **PART B — 28 hand-built scenarios** covering every category the phase prompt lists: guaranteed
  lethal + ready/multiple/zero-cost-attack Bench replacements; guaranteed lethal + empty/unready/
  zero-damage-only Bench; no-lethal (insufficient opponent energy, HP just out of range); 1-Prize
  exclusion (Dreepy, Drakloak); 3-Prize Mega ex exclusion (a real card from the engine's pool,
  Mega Venusaur ex); moderate vs. full energy-wipe retreat cost (Step 6's own worked example, both
  the positive and literal negative version); the winning-trade guard (affordable and
  unaffordable); the Phantom-Dive-is-not-real-Active-damage regression found in §9; the
  `can_switch=False` legality gate; the `>=` (not `>`) lethal boundary; the `can_attack=False`
  graceful-overlap case; every 2-Prize ex Active in the real decklist (Dragapult ex, Fezandipiti
  ex, Latias ex, Meowth ex); and a 1-Prize opponent that is nonetheless lethal. **28/28 pass.**
  - **Divergence from V7, measured directly** (each of the 28 fixtures run through both
    `V7Policy` and `V8Policy`, comparing the actual chosen MAIN action): **12 of 28 scenarios
    (43%) produce a different decision** — in every one of those 12, V7 attacks into a confirmed
    lethal hit that V8 retreats from, exactly the hypothesis under test. **16 of 28 (57%)** are
    identical between V7 and V8 — these are precisely the guardrail/exclusion scenarios (no
    Bench replacement, 1-Prize/Mega-ex excluded, no real lethal, winning-trade guard, retreat
    illegal, boundary just-below-lethal, Phantom-Dive-is-not-real-damage) proving the new hook is
    inert outside its intended scope, not merely "usually inert."
- **PART C — anti-thrash guardrail**, exercised end to end through `agent()` across a 4-decision
  simulated sequence (fire → resolve → stale repeat correctly blocked → genuinely new information
  correctly un-blocks it). **8/8 checks pass**, including the two load-bearing ones:
  `partc_stale_repeat_blocked` (RETREAT NOT chosen when nothing has changed) and
  `partc_new_info_unblocks` (RETREAT chosen again once HP genuinely changed).

Full pass/fail transcript reproducible via `python tools/verify_v8_survival_retreat.py`
(exit code 0).

---

## 7. Real-engine smoke test (Step 7, additional validation beyond the synthetic suite)

`tools/verify_v8_real_game_smoke_test.py` runs 5 full games through the actual compiled engine
(not synthetic fixtures): V8 self-play, V8 vs. `abomasnow_agent`, V8 vs. V7 head-to-head, V8 vs.
`lucario_ex_agent` (Mega Lucario ex — the hardest realistic hitter available locally), V8 vs.
`generic_mewtwo_agent`. All 5 completed with **only legal actions** (index bounds, min/maxCount,
no duplicates, mechanically asserted every step) — no exceptions, no illegal-action rejections.

The new hook fired **4 times across these 5 real games** (against Mega Lucario ex and the Mewtwo
ex agent — both real, hard-hitting, non-mirror matchups), each logged with the full diagnostic
record specified in Step 8 (our Active/HP/prizes, opponent Active/energy, retreat cost, Bench
replacement). It did **not** fire in the V8-mirror self-play game or the V7 head-to-head — both
Dragapult ex mirror matches, where Dragapult ex's 320 HP makes a guaranteed one-shot kill rare
with this local agent pool. This is informational, not a target metric (Phantom Dive activation
in V6's own report showed the same game-to-game variance) — but it is the direct evidence this
report leans on for "the heuristic activates correctly in real, unscripted play," on top of the
28 synthetic scenarios.

---

## 8. Switching-Item cards (Step 3's other half)

Per §1, this deck contains **no Item card that bypasses the retreat-cost energy discard** (no
Switch, Rope, Escape Board, or similar). Writing logic to "prefer playing the Switch Item as
equal to or better than a manual retreat" would be dead code with zero test coverage for this
specific decklist — per the instruction to avoid features beyond what the task requires, none was
written. If a future deck variant adds such a card, the natural extension point is
`_wants_survival_retreat`'s condition D/E (currently keyed only on `self.can_switch` +
Bench-readiness) plus a parallel check against `hand_score`'s existing Item-scoring path — flagged
here rather than speculatively implemented.

---

## 9. A real bug this task's own testing discipline caught (transparency)

The first draft of `_wants_survival_retreat` read `op_card.attacks` / `my_card.attacks` and
trusted each attack's card-data `damage` field at face value — exactly the same pattern this
file's own pre-existing `_wants_defensive_retreat` already uses. Real self-play (§7, first run,
before the fix below) immediately produced 4 "activations" in a V8-mirror self-play game, all
against **another Dragapult ex**, all citing `op_active_id: 121` with 2 energy attached. Tracing
it: Phantom Dive (attackId 154) has card-data `damage=200`, but — as this exact file's own V6 FIX
#2 / V7 FIX #3 already established and fixed **elsewhere** in `main_option_proc` — Phantom Dive
**never damages the Active**, only the Bench (up to six 10-damage counters). The lethal-detection
loop was treating a fictional 200-damage hit as real, and the winning-trade-guard loop had the
identical bug in the mirror direction (believing *our own* Phantom Dive could KO the opponent's
Active). **Fixed** by excluding `aid == 154` from both loops, exactly mirroring the established
fact already encoded elsewhere in this file. Re-running the real-game smoke test after the fix:
the mirror self-play game correctly shows 0 activations (no real lethal threat existed), while
the non-mirror games against genuinely hard-hitting opponents (Mega Lucario ex, Mewtwo ex) still
show 4 real activations (§7). Two new regression scenarios covering exactly this
(`phantom_dive_is_not_a_real_lethal_threat_to_active`,
`phantom_dive_is_not_a_real_trade_opportunity`) were added to the validation suite and pass.

This is disclosed here rather than silently fixed because it is directly relevant to trusting the
rest of this report, and because it surfaces a **known, unfixed latent inaccuracy already present
in `_wants_defensive_retreat`** (the pre-existing V4/V5 hook) — that hook has the exact same
"trusts card-data damage at face value" pattern and would misfire identically in a Dragapult-ex
mirror matchup where the opponent has 2+ energy on their Active. It was **not** touched, per the
surgical scope ("preserve existing target-selection/planning logic exactly," "do not refactor
unrelated code") — flagged here as a known limitation for a future, separate fix, not fixed
opportunistically.

---

## 10. Known limitations

1. **Card-data `damage` is trusted at face value for every attack except the one specific,
   source-verified exception in this codebase (Phantom Dive, §9).** A full semantic audit of all
   attack text across the engine's 1267-card pool (to find other "high damage number but
   bench/utility-only" attacks) was out of scope for a surgical, single-heuristic change; this is
   a residual risk shared with the pre-existing `_wants_defensive_retreat` hook, not something V8
   introduces net-new.
2. **The anti-thrash guardrail (§5) is deliberately conservative.** It blocks a repeat trigger
   whenever the threatened Pokémon's serial+HP and the opponent's serial are *all* unchanged, even
   in the (untested-for) case where Bench readiness itself improved between decisions (e.g. a
   previously-unready Bench Pokémon gained enough energy). This trades a small amount of
   theoretical missed value for a guaranteed-safe defense against real thrashing, per the phase
   prompt's own "CRITICAL GUARDRAIL" framing.
3. **No switching-Item logic exists** because this specific 60-card deck has no such card (§8) —
   documented as inert-by-construction, not implemented speculatively.
4. **`_bench_pokemon_is_ready` only checks energy affordability**, not HP/bulk or whether the
   replacement itself would immediately die too — ranking *which* ready candidate to retreat to
   is entirely delegated to the pre-existing, unmodified SWITCH/TO_ACTIVE scoring block (§1),
   exactly as the surgical scope requires.
5. **The real-ladder effect is untested** — per standing process rules, no ELO/win-rate outcome is
   claimed. V8 has not been submitted to Kaggle. Only local synthetic scenarios (§6) and local
   real-engine games against the existing local agent pool (§7) were run.

---

## 11. Files changed / added

**Modified**: none. `dragapult_policy_v7.py` and every other pre-existing file are byte-identical
to the V7 baseline (only the new module's own docstring intro differs from V7's — confirmed via
direct `diff`, the only removed lines across the whole file are the seven lines of V7's own module
docstring header, replaced by V8's).

**Added**:
- `src/agents/dragapult_policy_v8.py` — forked from `dragapult_policy_v7.py`; the new
  `_wants_survival_retreat` / `_bench_pokemon_is_ready` methods, ~15 lines of new bookkeeping
  state in `__init__`/`agent()`, and one new line wiring the hook into the existing `do_switch`
  computation. Everything else byte-identical (verified by `diff`, §11 above).
- `src/agents/dragapult_agent_v8.py` — thin binding, `make_agent(BALANCED, adaptive=False,
  always_first=True)` against V8's own engine (same weight profile as V2/V6/V7 — this is an A/B
  test of the new heuristic, not a retune; `policy_weights.py` was not modified).
- `src/agents/final_candidate_agent_v8.py` — safety_wrapper → timeout_shield → policy, same
  composition as every other version.
- `main_v8.py` — Kaggle entry point, same structure/deck as V1-V7.
- `tools/verify_v8_survival_retreat.py` — the PART A/B/C validation suite (§6).
- `tools/verify_v8_real_game_smoke_test.py` — real-engine smoke games (§7).

**Not done**: `policy_weights.py` unmodified; no MCTS/minimax/beam search/lookahead; no changes to
the deck, the safety wrapper, target-selection/planning logic, or any Phantom Dive fix; V8 not
submitted to Kaggle.
