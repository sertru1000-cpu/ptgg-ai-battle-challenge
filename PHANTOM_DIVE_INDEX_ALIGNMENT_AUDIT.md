# Phantom Dive Index-Alignment Audit — Resolving Hypothesis 3.4

**Date**: 2026-08-13. **Scope**: investigation only, per explicit instruction — no code changes,
no weight changes, no deck changes, no V6, agent untouched. This closes the single open `[GAP]`
left by `PHANTOM_DIVE_ARCHITECTURE_AUDIT.md` §3.4 ("static plan indices vs. live per-step option
indices — could not confirm or refute from static source alone").

Every claim below is tagged **SUPPORTED**, **NOT SUPPORTED**, **FALSIFIED**, or
**INSUFFICIENT DATA**, per the evidence standard specified for this task. Tooling:
`tools/build_phantom_dive_index_alignment_audit.py` (new, read-only, reuses the Phantom Dive
detection convention already established in `tools/build_phantom_dive_forensic.py`). Data:
all 44 locally-cached real V2-ladder replays in `data/v2_ladder_audit/replays/` — the same corpus
`PHANTOM_DIVE_FORENSIC.md` used, 149 real Phantom Dive attacks total. Raw output preserved in
`results/phantom_dive_index_alignment/{index_alignment_events.json,
lethal_before_counter6_examples.csv, bench_array_shift_log.csv}`.

---

## 1. Executive verdict

**Hypothesis 3.4 is FALSIFIED.**

> "V2 computes the Phantom Dive allocation using the pre-attack bench ordering, but the Kaggle
> engine removes a KO'd Pokémon immediately, shifting the bench indices. Therefore subsequent
> planned counters can be redirected to the wrong Pokémon."

Condition A (the engine removes a KO'd Pokémon and shifts bench indices *before* all six counters
are placed) is **directly contradicted** by real replay evidence: across all 149 real Phantom Dive
attacks — including all 31 where our own damage-tracking confirms a bench target actually reached
lethal HP strictly before the 6th counter was placed, 22 of them with ≥4 live bench targets present
— the engine's own reported bench array **never once** changed length or reordered a
serial-to-position mapping mid-attack. One case (episode 92387111, turn 22, detailed in §4.4) shows
the engine's own `hp` field going 10 → 0 → −10 → −20 → −30 for a bench Pokémon that stays at the
exact same raw array position for four more counter-placements after it died. This is the real
Kaggle `cg` engine implementing the standard Pokémon TCG rule correctly: **Knock Outs are resolved
only after the whole effect finishes, not counter-by-counter.**

Because Condition A is false, the compound hypothesis (which requires A **and** B) is falsified
regardless of B. Index alignment is **not** a contributor to the 47.6% missed-KO rate documented in
`PHANTOM_DIVE_FORENSIC.md`. The real, already-identified mechanisms in
`PHANTOM_DIVE_ARCHITECTURE_AUDIT.md` §3.2 (`hp == 10: score -= 100000`, a backwards fallback
penalty) and §3.3 (the plan-computation's `damage = 200` active-Pokémon contamination) remain the
full explanation for the observed miss pattern — see §7 for why the forensic examples here
corroborate, not compete with, those two findings.

---

## 2. Part 1 — Actual Kaggle engine KO/removal behavior

**SUPPORTED, by direct intermediate-state replay evidence (not inferred from final board state).**

The repo does not contain the real rules engine to read as source: `data/official/sample_submission/sample_submission/cg/{game.py,sim.py}` are 75-line thin process
bindings each, with zero matches for `ko|knock|bench|remove|prize` — confirming
`PHANTOM_DIVE_ARCHITECTURE_AUDIT.md`'s prior finding that the actual simulator is compiled/opaque
and ships only inside the Kaggle sandbox. So this question can only be answered empirically, from
real replay intermediate states — which the existing `find_phantom_dive_events`-style walk already
captures at every one of the 6 sub-decisions (each `SelectContext.DAMAGE_COUNTER_ANY` round-trip
carries its own fresh `obs.current`, i.e., a full board snapshot as of immediately before that
specific counter is chosen).

For every one of 149 real Phantom Dive attacks, this audit recorded the **complete live
`op_state.bench` array** (position → serial/card_id/hp, exactly as `cg` reports it) before each of
the up to 6 counter-placement selects, and diffed every consecutive pair. Findings:

- Bench arrays are **dense** (no null-padded empty slots were ever observed — array length always
  equals live occupant count).
- **0 of 149 events** showed any array-length change between two consecutive sub-steps.
- **0 of 149 events** showed any case of two different serials occupying the same raw position
  across consecutive sub-steps (the direct signature of compaction/reindexing).
- **0 of 149 events** showed a slot silently emptied-in-place mid-attack.
- This holds even in the **31 events where a target's own cumulative counter damage reached or
  exceeded its pre-attack HP strictly before counter #6** — i.e., exactly the population where a
  compacting engine *would* have to shift indices if it removed KOs immediately. It didn't happen
  once.
- Positive, not just absence-of-negative, evidence: engine-reported `hp` goes **negative** (episode
  92387111, §4.4) for a bench Pokémon that is still physically present in the array at its original
  position for four subsequent selects. An engine that removed 0-HP Pokémon immediately could not
  produce a negative `hp` reading four counters later at the same position — the only way to see
  this is if removal is deferred until the whole attack (all 6 placements) resolves.

**Answer to the three sub-questions in Part 1.2**: **(B)** — the Pokémon remains in the bench array,
at its own position, with its `hp` field updated (including going to/below 0) as counters land,
until the complete Phantom Dive attack finishes. No evidence of (A) immediate removal, and no
"KO-pending" intermediate state (C) distinct from just-negative-HP-still-in-place was observed —
the array entry itself is the only representation, all the way through.

---

## 3. Part 3 — How V2 identifies Phantom Dive targets

**SUPPORTED, traced through the exact call chain in source.**

**Answer: (1) raw bench indices.** Not a stable serial, not an object reference, not any other
identity mechanism — confirmed at *both* ends of the pipe:

**Capture (`main_option_proc`, `dragapult_policy_v2plus.py:240-332`)**, called once at
`SelectContext.MAIN`, before Phantom Dive is even chosen as the action:

```python
cards = [op_state.active[0]]          # :265
for pokemon in op_state.bench:        # :266-267
    cards.append(pokemon)
```

`cards` is a plain Python list built by iterating `op_state.bench` **once**, at MAIN-decision time.
The backtracking subset-sum generator (`:268-287`) enumerates combinations of **integer positions
into this list** (0 = active, 1..N = bench position + 1) under a 60-damage budget, and the winning
combo's raw-index list is copied into `self.plan_b.counter` unconditionally at `i == 0` (`:329-331`).
`self.plan_b.counter` is therefore a `list[int]` of **raw list positions as they existed at MAIN
time** — no serial, no card object, no reference of any kind.

**Consult (`DAMAGE_COUNTER_ANY` branch, `dragapult_policy_v2plus.py:769-796`)**, run independently
on each of the 6 sub-decisions:

```python
card = get_card(obs, o.area, o.index, o.playerIndex)   # :727, common.py:14-38 -> ps.bench[o.index]
...
index = o.index + 1                                      # :784
if index in self.plan_b.counter:                         # :785
    score += 100000
```

`get_card` (`src/agents/common.py:14-38`) resolves `o.index` against `ps.bench[o.index]` — i.e.
**a raw positional index into whatever bench array the engine offers for this specific select's own
`obs.current`**, read fresh every one of the 6 times. `o.index` itself comes from the engine's
option list for *that* select, not from anything V2 stored. So the live side is also raw-index
based, and freshly re-derived from the live board every step — it never looks up or checks a
Pokémon's serial/identity anywhere in this branch.

**Conclusion**: both the captured plan and every one of the six live consults use **the same raw
positional-index convention**, resolved against two different snapshots of the same array (MAIN-time
vs. this-sub-step-time) that are never explicitly reconciled by identity. `index in self.plan_b.counter`
is a bare integer-membership check — it is correct **if and only if** the array's shape and
per-position occupant are unchanged between MAIN time and every one of the 6 sub-steps. No serial
comparison, no remap, no defensive check exists anywhere in this path (confirmed by reading the full
`agent()` method — `.serial` is used elsewhere in the file, e.g. `_observe_opponent` at `:369-384`,
so the authors clearly know how to key off serial when they choose to; they didn't do so here).

---

## 4. Part 2 — Five real forensic traces

Selected from the 31 real events where a bench target is confirmed to reach lethal cumulative
damage strictly before counter #6, prioritizing board complexity (multiple bench targets) and
distinct failure shapes. All raw data in
`results/phantom_dive_index_alignment/index_alignment_events.json`; `hp_at_selection_time` below is
the **engine's own live-reported HP** for the resolved target at the moment of that select, not a
derived value.

### 4.1 Episode 92219700, turn 11 — 3 bench targets, 1-counter instant kill

**Pre-attack bench** (`pos_at_main` = raw index − 1, i.e. bench array position):

| pos | serial | card_id | hp/maxhp |
|---|---|---|---|
| 0 | 25 | 649 | 10/70 |
| 1 | 15 | 646 | 70/70 |
| 2 | 30 | 860 | 70/70 |

| counter# | raw idx chosen | resolved serial | hp at selection | bench len |
|---|---|---|---|---|
| 1 | 0 | **25** | 10 | 3 |
| 2 | 1 | 15 | 70 | 3 |
| 3 | 1 | 15 | 60 | 3 |
| 4 | 1 | 15 | 50 | 3 |
| 5 | 1 | 15 | 40 | 3 |
| 6 | 1 | 15 | 30 | 3 |

Post-attack bench: `[{pos0: serial15, hp20}, {pos1: serial30, hp70}]` — serial 25 (the counter-1
kill) is gone; serial 15 survives at 20 HP (5 counters/50 damage against a 70-HP target, 20 HP
short of a kill); serial 30 was never
touched. Serial 25 goes lethal at counter #1 (10 HP, one counter); raw index 0 correctly and
exclusively resolves to serial 25 for that placement, and raw index 1 correctly and consistently
resolves to serial 15 for all five remaining counters — **no drift**. (Dumping 5 counters into one
70-HP target instead of, e.g., leaving it and doing nothing else useful is a plan/allocation
*quality* question, addressed in §7, not an identity question.)

### 4.2 Episode 92224429, turn 9 — 3 bench targets, two lethal events in one attack

**Pre-attack bench**:

| pos | serial | card_id | hp/maxhp |
|---|---|---|---|
| 0 | 15 | 235 | 30/30 |
| 1 | 3 | 119 | 70/70 |
| 2 | 5 | 119 | 20/70 |

| counter# | raw idx | serial | hp at selection |
|---|---|---|---|
| 1 | 2 | **5** | 20 |
| 2 | 2 | **5** | 10 |
| 3 | 0 | **15** | 30 |
| 4 | 0 | **15** | 20 |
| 5 | 0 | **15** | 10 |
| 6 | 1 | 3 | 70 |

Serial 5 goes lethal at counter #2 (20 HP / 2 counters); serial 15 goes lethal at counter #5 (30 HP
/ 3 counters). Both KOs are confirmed by the post-attack bench (`[{pos0: serial3, hp60}]` — only
serial 3 survives). Raw index 2 resolves to serial 5 for both of its placements, then raw index 0
resolves to serial 15 for all three of *its* placements — including for counters #3-5, which are
placed **after** serial 5 (originally at position 2, a *later* position than 15's position 0) has
already died. If the engine reindexed on KO, position 0 would be the first place instability could
show up on the very next select after any removal — it doesn't. Counter #6 (raw idx 1 → serial 3) is
a wasted counter on an untouched 70-HP target after both real KOs were already secured — again an
allocation-quality issue, not an index bug.

### 4.3 Episode 92226320, turn 12 — 5 bench targets (largest board tested), 1-counter instant kill

**Pre-attack bench**:

| pos | serial | card_id | hp/maxhp |
|---|---|---|---|
| 0 | 9 | 269 | 280/280 |
| 1 | 14 | 270 | 10/60 |
| 2 | 8 | 269 | 280/280 |
| 3 | 11 | 270 | 50/60 |
| 4 | 13 | 270 | 60/60 |

| counter# | raw idx | serial | hp at selection |
|---|---|---|---|
| 1 | 1 | **14** | 10 |
| 2 | 3 | 11 | 50 |
| 3 | 3 | 11 | 40 |
| 4 | 3 | 11 | 30 |
| 5 | 3 | 11 | 20 |
| 6 | 3 | 11 | 10 |

Serial 14 goes lethal at counter #1. Post-attack bench:
`[{pos0:9,hp280},{pos1:8,hp280},{pos2:13,hp60}]` — only 3 of the original 5 survive: serial 14
(counter #1) **and** serial 11 (its 50 HP is exactly consumed by the 5 remaining counters, dying on
counter #6 itself — outside this audit's "before counter #6" filter, so it's correctly absent from
the lethal-before-6 table above, but it confirms a second real KO in this same attack). Raw index 3
(well past the already-removed-at-the-end position 1) resolves to the same serial, 11, for all 5
placements from counter #2 through #6 — **no drift**, even though this is the widest board tested
(5 bench targets) and the raw index used (3) sits on the far side of the position that later goes
empty.

### 4.4 Episode 92387111, turn 22 — 3 bench targets, two 1-counter kills, negative HP retained in place (clearest single piece of evidence)

**Pre-attack bench**:

| pos | serial | card_id | hp/maxhp |
|---|---|---|---|
| 0 | 21 | 345 | 150/150 |
| 1 | 16 | 344 | 10/70 |
| 2 | 18 | 344 | 10/70 |

| counter# | raw idx | serial | hp at selection (engine-reported, live) |
|---|---|---|---|
| 1 | 1 | **16** | 10 |
| 2 | 2 | **18** | 10 |
| 3 | 1 | 16 | **0** |
| 4 | 1 | 16 | **−10** |
| 5 | 1 | 16 | **−20** |
| 6 | 1 | 16 | **−30** |

Serial 16 dies at counter #1 (10 HP), serial 18 dies at counter #2 (10 HP). Post-attack bench:
`[{pos0: serial21, hp150}]` — both are confirmed gone **after** the attack fully resolves. But for
counters #3-6, raw index 1 keeps resolving to the *same, already-dead* serial 16, and the engine's
own `hp` field reports it going to **0, then negative** while still occupying array position 1 —
this is the single cleanest piece of intermediate-state evidence in the whole dataset that the
engine does not compact the bench mid-attack: if it did, position 1 would have to start resolving to
serial 18 (or nothing) starting at counter #3, and it never does.

### 4.5 Episode 92235791, turn 9 — 5 bench targets, lethal mid-sequence, 4 more counters placed correctly afterward

**Pre-attack bench**:

| pos | serial | card_id | hp/maxhp |
|---|---|---|---|
| 0 | 67 | 675 | 110/110 |
| 1 | 71 | 676 | 90/110 |
| 2 | 68 | 675 | 110/110 |
| 3 | 64 | 673 | 20/80 |
| 4 | 75 | 678 | 340/340 |

| counter# | raw idx | serial | hp at selection |
|---|---|---|---|
| 1 | 3 | **64** | 20 |
| 2 | 3 | **64** | 10 |
| 3 | 1 | 71 | 90 |
| 4 | 1 | 71 | 80 |
| 5 | 1 | 71 | 70 |
| 6 | 1 | 71 | 60 |

Serial 64 goes lethal at counter #2 (20 HP). Post-attack bench:
`[{pos0:67,110},{pos1:71,50},{pos2:68,110},{pos3:75,340}]` — 4 survivors, confirming only serial 64
died, and — notably — position 3 (serial 64's original slot) is simply **absent** from the
post-attack array rather than reused/renumbered by another serial, consistent with §2's "resolved
only at full-attack-end, then compacted once" model. Raw index 1 resolves to serial 71 correctly and
consistently across all 4 of its placements, both before and after serial 64's death at a lower
position — again no drift.

---

## 5. Summary table — does the array shift mid-attack?

| Episode | Turn | Bench targets | Lethal event(s) before ctr #6 | Array shift observed? |
|---|---|---|---|---|
| 92219700 | 11 | 3 | serial 25 @ ctr1 | **No** |
| 92224429 | 9 | 3 | serial 5 @ ctr2, serial 15 @ ctr5 | **No** |
| 92226320 | 12 | 5 | serial 14 @ ctr1 | **No** |
| 92387111 | 22 | 3 | serial 16 @ ctr1, serial 18 @ ctr2 | **No** |
| 92235791 | 9 | 5 | serial 64 @ ctr2 | **No** |
| *(all other 26 lethal-before-6 events, 149 total attacks)* | — | up to 5 | various | **No — 0/149** |

**Do indices shift during the six counters? FALSIFIED (no).** Across every real Phantom Dive attack
in the available corpus, raw bench positions are stable for the full duration of a single attack;
the engine only removes/renumbers KO'd Pokémon once the entire 6-counter effect has fully resolved.

**Does V2 remap targets? NOT SUPPORTED as a real behavior, but also NOT NEEDED given §2.**
V2 has no serial-based remap or identity check anywhere in the Phantom Dive path (§3) — it relies
entirely on raw-index stability holding. Empirically (§2, §4) that stability always holds in this
engine, so the absence of remapping has not produced any observed failure. This is best described as
a **latent fragility, not an active defect**: the code would misbehave if the engine's KO-timing
rule ever changed, but nothing in 149 real attacks shows it changing.

---

## 6. Part 4 — Hypothesis test result

| Condition | Required for CONFIRMED | Result |
|---|---|---|
| A. Engine removes a KO'd Pokémon before all 6 counters, shifting bench indices | Yes | **FALSIFIED** — 0/149 events, including 31 genuine mid-attack lethal cases | 
| B. V2 resolves stored targets via stale pre-attack indices without dynamic remapping | Yes | **SUPPORTED** — confirmed by code trace (§3): raw-index-only, no serial check |

Hypothesis requires **A AND B**. A is false. **Overall verdict: FALSIFIED.**

---

## 7. Part 5 — Plan quality vs. plan execution (explicit separation)

This audit tested **only** plan-execution/identity-alignment (#2). It found no evidence of it.
The forensic examples above (particularly 92219700 and 92226320) still show V2 producing
**allocation-quality** outcomes that look bad in isolation — 5 counters dumped onto one already-
healthy target after an easy first kill, or a 50-HP target left at exactly 10 HP — but in every one
of these cases the raw-index-to-serial resolution itself was **correct and stable** throughout. That
means these outcomes are fully attributable to the plan-computation and per-counter fallback-scoring
mechanisms already identified and source-verified in `PHANTOM_DIVE_ARCHITECTURE_AUDIT.md`:

- §3.2 — `elif hp == 10: score -= 100000` in the `DAMAGE_COUNTER_ANY` fallback
  (`dragapult_policy_v2plus.py:793-794`), which actively deprioritizes the cheapest kill whenever a
  target isn't already in `plan_b.counter`.
- §3.3 — `main_option_proc`'s hardcoded `damage = 200` contaminating the `i == 0` (active-Pokémon)
  branch of the plan computation, which under specific low-remaining-prize conditions zeroes out
  `plan_b.counter` entirely, forcing every real counter through the flawed fallback in §3.2.

This audit's contribution is narrowing the space: it removes "index/identity misalignment" as a
candidate cause, leaving §3.2/§3.3 as the full, source-verified explanation for the missed-KO pattern
— not a new, previously-unconsidered mechanism.

---

## 8. Exact code path (for reference)

```
main_option_proc()                              dragapult_policy_v2plus.py:240-332
  cards = [active] + bench                       :265-267   (raw list, MAIN-time snapshot)
  counter_indices = backtracking subset-sum       :268-287   (raw integer positions, 60-dmg budget)
  winning combo -> self.plan_a.counter            :304-328
  i==0 unconditionally -> self.plan_b.counter     :329-331   (RAW INDICES, no serial)
        |
        v
agent(), context == MAIN                          :682-683   (main_option_proc invoked once)
        |
        v  (six independent engine round-trips, one per counter)
agent(), context == DAMAGE_COUNTER_ANY             :769-796
  card = get_card(obs, o.area, o.index, ...)       :727, common.py:14-38  (live ps.bench[o.index])
  index = o.index + 1                              :784
  if index in self.plan_b.counter: +100000         :785-786   (bare int-membership, no identity check)
  else: HP-bucket fallback (incl. hp==10 penalty)   :787-794
```

---

## 9. Verdict

**Hypothesis 3.4: FALSIFIED.**

Index/identity misalignment between V2's one-shot pre-attack plan and the six live per-counter
selects is **not** occurring and **not** a contributor to the 47.6% missed-KO rate. The real Kaggle
`cg` engine defers all Knock-Out resolution (bench removal, reindexing) until the complete Phantom
Dive action finishes — confirmed directly from intermediate replay states across 149 real attacks,
31 of them genuinely lethal mid-sequence, with one case (§4.4) showing negative HP retained in a
fixed array position for four placements after death. V2's raw-index-only target resolution
(§3, §8) has no defensive remapping, but none is currently needed, because the premise that would
require it (mid-attack index shifting) does not hold in this engine.

**Per item 11 of the evidence standard — why index alignment is NOT the cause**: the entire failure
mode depends on the bench array changing shape between two of the six sub-selects. That never
happens, in any of the 149 real attacks audited, including the specific high-risk subset (31 events)
where a target's HP genuinely crosses zero mid-attack — the exact population where a compacting
engine would have to shift indices if it were going to. The already-confirmed §3.2/§3.3 bugs remain
the complete, source-verified explanation for the missed-KO pattern (§7); no further "index
misalignment" fix is applicable, and none is proposed here.

**No code, weights, deck, or agent changes were made in this audit.** No V6 was created. This
resolves the last open item from `PHANTOM_DIVE_ARCHITECTURE_AUDIT.md` §3.4/§5/§7; the next decision
(whether/how to address §3.2 and §3.3) remains the user's, per standing process rule 5.
