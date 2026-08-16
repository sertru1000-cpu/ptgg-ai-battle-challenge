# Phantom Dive Forensic Audit — V2 Balanced Real Kaggle Ladder Games

**Date**: 2026-08-13. **Scope**: forensic validation only. Tests, does not assume, Gemini's
specific hypothesis: *"V2 loses significant value because its Phantom Dive damage allocation
fails to convert available bench KO opportunities into prizes."* **Does NOT use the aggregate
68.9% KO-conversion figure as evidence** — that number blends Jet Headbutt with Phantom Dive and
active-KOs with bench-KOs, and mixes situations where no KO was ever possible with situations
where one was missed (`V2_LADDER_AUDIT.md` §4). This report builds the correct denominator: real
Phantom Dive events where the pre-attack board state made a KO reachable. **No agent, weight, or
deck changes. No V5. Phantom Dive is not hardcoded.** Per your instruction, no further weight-
tuning experiment is proposed given the prior retreat-weight finding
(`memory/feedback_ptcg_process.md`, `V2_LADDER_AUDIT.md` §14) — this is a pure data forensics
pass.

Every claim is tagged **[FACT]**, **[HYPOTHESIS]**, or **[GAP]**, per this project's standing
process rule.

---

## 0. Mechanics established this session (verified against real replay data, not assumed)

**[FACT]** Phantom Dive (attackId=154) is declared via a MAIN-menu (SelectContext=0) decision
choosing `{"type":13,"attackId":154}`. Its damage resolves as **up to 6 sequential single-counter
placement decisions**, each a `SelectContext.DAMAGE_COUNTER_ANY` (14) select over the opponent's
*live* bench only. Confirmed directly from `data/v2_ladder_audit/replays/` — new tooling:
`tools/build_phantom_dive_forensic.py` (reuses the same prev-select/this-action pairing already
validated in `src/meta_analysis/ladder_behavior_audit.py`, not a new parsing convention).

**[FACT]** Phantom Dive **never touches the opponent's Active Pokémon** — mechanically confirmed
(no DAMAGE_COUNTER_ANY select ever offers a non-bench target), consistent with the card's own
text ("Put 6 damage counters on your opponent's Benched Pokémon in any way you like") and
`V2_LADDER_AUDIT.md` §9's earlier finding. **Active KOs via Phantom Dive: always 0, by
construction — this attack structurally cannot produce one.**

**[FACT, important correction to a naive analysis]**: several real cards grant **hard immunity**
to Phantom Dive specifically because Dragapult ex is both an `{ex}` Pokémon **and** a Tera
Pokémon (`cg.api.CardData` confirms `ex=True, tera=True, basic=False, skills=[]` for cardId 121)
— found by directly scanning all card abilities for "prevent...damage" text, not guessed:
Crustle "Mysterious Rock Inn" and Sylveon "Safeguard" (block ex-attacker damage to themselves),
Milotic ex "Sparkling Scales" (blocks Tera-attacker damage), Poltchageist / Misty's Magikarp
(block all attack damage while benched), Rabsca "Spherical Shield" (**team-wide** — shields the
opponent's *entire* bench, not just itself, if Rabsca is anywhere on their board), Battle Cage
stadium (blocks attack-*effect* damage-counter placement to bench on both sides — Phantom Dive's
damage is effect-based per its own text, not standard attack damage), Neutralization Zone
stadium (blocks ex-attacker damage to non-rule-box Pokémon). **Empirically confirmed the engine
actually enforces this, not just card text**: episode 92217792 turn 12 shows a Crustle bench
target's HP staying completely flat (150/150) across all 6 of V2's counter placements. A naive
"any bench HP ≤ 60" check would have wrongly counted this as a missed KO. Both the naive and
immunity-adjusted counts are reported below — the immunity filter removed exactly 5 of the 68
naively-detected opportunities (68 → 63).

**[GAP]**: the immunity model covers every ability/stadium found by a full-database keyword scan
that could plausibly apply given Dragapult ex's exact properties (ex/tera/non-Basic/no-ability)
— it is not a hand-picked subset, but a keyword scan could in principle miss a differently-worded
effect. Carracosta's "Mighty Shell" (blocks damage from opponents with Special Energy attached)
was checked and never applied in this dataset (would need per-instance special-energy tracking
on our own Dragapult ex; deferred as it never actually appeared as a live case in these 43
games).

Manually cross-verified two full examples end-to-end against raw replay JSON (episode 92219700
turn 13, a missed KO; episode 92217792 turn 12, an immune target) before trusting the automated
pipeline at scale — both matched the script's reconstruction exactly.

---

## 1. Headline counts

| Metric | Count |
|---|---:|
| Total Phantom Dive attacks (43 real games) | **149** |
| ...with zero opponent bench Pokémon at all | 5 |
| ...with ≥1 bench Pokémon present | 144 |
| Naive KO-opportunity count (any bench HP≤60, ignoring immunity) | 68 |
| Immune-target instances found (across all events) | 57 |
| **Phantom Dive with NO KO opportunity (immunity-adjusted)** | **81** |
| **Phantom Dive with ≥1 KO opportunity (immunity-adjusted)** | **63** |
| KO opportunities converted (achieved the full optimal prize value) | **33** |
| KO opportunities with *some* KO landed (incl. suboptimal) | 35 |
| **KO opportunities where value was left on the table (missed)** | **30** |
| Prize value lost to missed KOs, total | **32 prizes** (~0.74/game across all 43 games) |

**Opportunity-to-KO conversion rate: 33/63 = 52.4%**
**Missed-KO rate when a KO allocation existed: 30/63 = 47.6%**

These are the correct denominators the instruction asked for — not the aggregate 68.9%, which
mixes Jet Headbutt, active-targeting, and no-opportunity situations in with this.

---

## 2. Breakdown by KO type

| Category | Count |
|---|---:|
| Active KOs via Phantom Dive | **0** (structurally impossible — bench-only attack) |
| Bench KOs actually landed | 43 |
| — of which 1-prize KOs | 42 |
| — of which 2-prize KOs | 1 |
| Multi-KO opportunities available (best allocation kills ≥2 targets) | 8 |
| — fully converted (both/all killed) | 4 |
| — partially converted (1 of 2 killed) | 2 |
| — completely missed (0 of 2 killed) | 2 |

**[FACT]** Only 1 of V2's 43 landed bench KOs was worth 2 prizes — the deck's Phantom Dive value
is overwhelmingly 1-prize-Basic-Pokémon sniping, not high-value ex targets (ex/Mega-ex bench
Pokémon tend to run too much HP for 6 counters/60 damage to threaten in one hit anyway, e.g.
Fezandipiti ex 210 HP, Latias ex 210 HP, Mega Froslass ex 310 HP all appear in the dataset as
untouchable by a single Phantom Dive regardless of allocation).

**[FACT]** Of the 30 missed-value events, 28 were complete whiffs (0 prize despite an available
KO) and 2 were partial (some KO landed, but a second available KO on the same turn was missed —
episodes 92233918 turn 14 and 92239608 turn 12, both in §3).

---

## 3. Representative missed-KO examples (9 of 30, spanning single/multi-KO and partial/total misses)

| # | Episode | Turn | Result | Opponent bench (pre-attack) | V2's actual allocation | Optimal allocation | Prize diff |
|---|---|---|---|---|---|---|---:|
| 1 | 92226320 | 16 | WIN | Bellibolt ex 280/280(p2); Kilowattrel 120/120(p1); **Wattrel 10/60(p1)**; **Tadbulb 50/60(p1)** | 0,2,0,4 → 0 KOs | 0,0,1,5 → Wattrel+Tadbulb KO'd | **2** |
| 2 | 92232003 | 12 | WIN | **Staryu 10/70(p1)**; **Staryu 10/70(p1)**; Mega Froslass ex 310/310(p3); Snorunt 70/70(p1) | 0,0,0,6 (all 6 dumped on unkillable Snorunt) → 0 KOs | 1,1,0,4 → both Staryu KO'd | **2** |
| 3 | 92219700 | 13 | WIN | **Marnie's Impidimp 20/70(p1)**; Snorunt 70/70(p1) | 1,5 → 0 KOs (Impidimp needed 2, got 1) | 2,4 → Impidimp KO'd | 1 |
| 4 | 92220638 | 9 | WIN | **Kyogre 20/150(p1)**; Kyogre 150/150(p1) | 1,5 → 0 KOs | 2,4 → 1st Kyogre KO'd | 1 |
| 5 | 92223466 | 11 | **LOSS** | **Makuhita 20/80(p1)**; Lunatone 110/110(p1); Makuhita 80/80(p1); Solrock 110/110(p1); Riolu 80/80(p1) | 1,0,5,0,0 → 0 KOs (weak Makuhita got 1, needed 2; 5 dumped on an already-full-HP Makuhita that needed 8) | 2,0,0,0,4 → weak Makuhita KO'd | 1 |
| 6 | 92224429 | 11 | WIN | Fezandipiti ex 210/210(p2); **Dreepy 60/70(p1)**; Latias ex 210/210(p2) | 1,4,1 → 0 KOs (Dreepy needed 6, got only 4) | 0,6,0 → Dreepy KO'd | 1 |
| 7 | 92233918 | 14 | WIN | Snorlax 150/150(p1); Snorlax 150/150(p1); **Dunsparce 10/60(p1)**; **Dunsparce 10/60(p1)**; Phantump 70/70(p1) | 0,0,1,0,5 → 1 KO (only 1st Dunsparce) | 0,0,1,1,4 → both Dunsparce KO'd | 1 (partial — 1 KO landed, 2nd missed) |
| 8 | 92239608 | 12 | WIN | Lunatone 50/110(p1); **Drilbur 10/70(p1)**; Charcadet 80/80(p1) | 5,0,1 → 1 KO (Lunatone only) | 5,1,0 → Lunatone AND Drilbur both KO'd | 1 (partial — Drilbur needed only 1 more counter, taken from the already-dead-certain Charcadet slot instead) |
| 9 | 92309614 | 7 | WIN | **Dunsparce 10/70(p1)**; Mega Lopunny ex 330/330(p3); Dunsparce 70/70(p1) | 0,0,6 (all 6 on the FULL-HP Dunsparce) → 0 KOs | 1,0,5 → weak Dunsparce KO'd | 1 |

**[FACT, pattern, not cherry-picked]**: the failure mode is consistent and mechanistic across
essentially every example above — V2 repeatedly over-allocates counters toward a target that
cannot possibly die this turn (a 70-150+ HP Pokémon needing 7+ counters when only 6 exist) while
under-allocating by exactly 1-2 counters to an adjacent target that WAS one hit from dying. This
is not random noise: the same specific low-HP archetypes recur as missed targets multiple times
within this 43-game sample (Dunsparce missed 5 separate times across 4 different games; Abra
missed 7 separate times across 4 different games, both outside the curated table above but
visible in the full `results/phantom_dive_forensic/missed_ko_examples.csv`), consistent with a
systematic allocation-priority issue rather than isolated misclicks.

---

## 4. Where the misses actually landed (game outcome context)

**[FACT]** 25 of the 30 missed-value events occurred in games V2 ultimately **won anyway**; only
**5 occurred in games V2 lost**, spread across **4 distinct losses** (out of V2's 16 total real
losses — 25%). **[FACT]** 29 of V2's 41 real games that featured a Phantom Dive attack had ≥1 KO
opportunity at some point; 18 distinct games had ≥1 actual miss.

**[HYPOTHESIS, explicitly not proven by this data]**: a missed 1-prize KO does not automatically
mean a lost game — prize races are decided across many turns, and this dataset provides no
counterfactual replay of "what if V2 had taken that KO instead." **No claim is made here that
converting these 30 missed KOs would have flipped any specific loss to a win** — that would
require re-simulating the rest of each game, which is out of scope for a forensic pass. What
*is* established as fact is that the allocation inefficiency itself is real, frequent, and
mechanistically clear — not that it is *the* determinant of V2's win/loss record.

---

## 5. Equivalent vs. superior allocations

**[FACT]** In every one of the 33 successfully-converted KO opportunities, the optimal allocation
found by exhaustive search was **unique or near-unique** in terms of which target(s) to kill —
there was essentially always exactly one way to spend counters that maximizes prize value (kill
the reachable target(s), dump the remainder wherever, since excess counters on an unkillable
target are fungible and don't matter). **[FACT]**: none of the 63 KO-opportunity events had
*multiple, meaningfully different* KO-achieving allocations tied at the same maximum prize value
except for immaterial reshuffling of "wasted" counters among already-unkillable targets — i.e.,
when a KO was available, there was essentially always one clearly-correct allocation, not a
genuine judgment call between equally-good options. This means the 47.6% miss rate is not
attributable to "V2 picked one of several defensible allocations" — the optimal choice was
almost always unambiguous.

---

## 6. Verdict

**Hypothesis under test**: *"V2 loses significant value because its Phantom Dive damage
allocation fails to convert available bench KO opportunities into prizes."*

**PARTIALLY SUPPORTED.**

The specific mechanism — **inefficient split-damage allocation causing missed bench KOs** — is
**SUPPORTED** with strong, concrete, mechanistically-verified evidence, not a hypothetical:
- 47.6% of genuine KO opportunities (30/63) were missed, essentially a coin flip.
- 32 total prize value left on the table across 43 games (~0.74 prizes/game from this one
  attack alone).
- The failure pattern is systematic and recurring (same low-HP archetypes — Dunsparce, Abra,
  Staryu — missed repeatedly across different games), not isolated noise.
- The optimal allocation was almost always unambiguous when a KO existed (§5) — these are not
  close judgment calls V2 happened to lose, they are cases where a clearly-better allocation
  existed and wasn't taken.

The broader causal claim — that this **"loses significant value"** in the sense of costing V2
**games** — is **NOT SUPPORTED** by this data as stated, and should not be asserted without the
missing counterfactual: only 5 of the 30 missed events (4 distinct games, 25% of V2's 16 real
losses) occurred in games V2 actually lost; the large majority (25/30) happened in games V2 won
regardless. No re-simulation was done to test whether converting any specific missed KO would
have changed a game's outcome.

**Recommended framing if this is used going forward**: "V2's Phantom Dive allocation logic has a
real, frequent, mechanistically-confirmed inefficiency (~48% miss rate on available bench KOs)"
is a fact this report supports. "This inefficiency is costing V2 games on the real ladder" is
not yet demonstrated and would need a separate counterfactual/re-simulation study to establish.

Per your instructions: **no code changes made, no V5 created, no weights changed, Phantom Dive
was not hardcoded.** This is the forensic validation checkpoint only; the next decision (if any)
is yours.

---

## 7. Deliverables

`tools/build_phantom_dive_forensic.py` (new, reuses the established replay-parsing convention),
`results/phantom_dive_forensic/{events.csv, missed_ko_examples.csv, phantom_dive_summary.json}`
— all 149 raw events and all 30 missed-value events preserved in full detail, not just the
aggregates in this report, per this project's standing raw-data-preservation rule.
