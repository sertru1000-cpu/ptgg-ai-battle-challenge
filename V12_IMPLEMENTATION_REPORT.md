# V12 Implementation Report — Matchup-Aware Policy

**Status:** built and packaged locally. **NOT submitted to Kaggle** — awaiting explicit user approval, per the governing task's instruction.

## 1. Scope and what V12 is not

V12 forks **V6** (`dragapult_policy_v6.py` / `dragapult_agent_v6.py`), not V10 — same decklist (`decks/dragapult_ex.csv`), same greedy scoring engine (attack-combo subset-sum search, hand/attach/switch heuristics), same two Phantom Dive bug fixes V6 shipped. Explicitly out of scope, per the governing task, and NOT present in this fork:

- No lookahead/search — that's V11's job. V12 is a single-ply greedy policy exactly like V6.
- No V8/V9 survival/defensive-retreat heuristics. V6's own (V2-era) defensive-retreat hook is carried over completely unmodified; V12 adds nothing to it and does not tune its thresholds.
- No change to V10's deck or setup logic — V12 never imports from V10.

One deliberate, disclosed deviation from a strict line-for-line copy: V6 carries a V5-only in-battle *opponent-aggression* model (`_observe_opponent` / `_compute_adaptive_weights`, dead code whenever `adaptive=False`, which V6's own `dragapult_agent_v6.py` always sets). That mechanism answers a different question (how aggressively is this specific opponent playing, moment to moment) than V12's task (what archetype is this opponent's deck). Left in place unmodified, it would type-mismatch the moment `self.weights` stopped being the new `MatchupWeights` wrapper every other call site in this file expects. It was removed rather than patched around, and V12 has no `adaptive` mode. Everything else — the attack-combo planner, every hand/attach/switch scoring branch, both V6 Phantom Dive fixes — is unchanged.

## 2. Files created

| File | Role |
|---|---|
| `src/agents/dragapult_policy_v12.py` | Forked engine: V6's scoring logic + archetype detection + `MatchupWeights` |
| `src/agents/dragapult_agent_v12.py` | Thin binding: `make_agent(BALANCED)` (V12's fixed base profile — identical to V6's) |
| `src/agents/final_candidate_agent_v12.py` | Safety-wrapped submission candidate (`safety_wrapper` → `timeout_shield` → policy), mirrors V6's own composition |
| `main_v12.py` | Kaggle entry point, mirrors `main_v6.py`/`main_v11.py` structure exactly |
| `tools/build_submission_challenger.py` | Extended: `v12` added to `VALID_VERSIONS`, `DECK_SOURCE["v12"] = "dragapult_ex.csv"` |

**Deck verified identical to V6**: `dragapult_agent_v12.py` and `dragapult_agent_v6.py` both read `decks/dragapult_ex.csv` via the same `_DECK_PATH` construction; `tools/build_submission_challenger.py --version v12` re-validates this at packaging time (real `battle_start` legality check, `decks/dragapult_ex.csv: LEGAL`).

## 3. Objective 2 — archetype detection

`detect_archetype(op_state)` in `dragapult_policy_v12.py` scans the opponent's currently-visible `active` + `bench` Pokemon IDs (real `Observation.current.players[..]` data — never hidden opponent info) and classifies into one of three profiles, recomputed fresh on every decision (not cached, since the opponent's board develops turn over turn):

- **SNIPER**: any of `{Dreepy=119, Drakloak=120, Dragapult ex=121}` — the mirror matchup, verified as the same three IDs V6's own decklist constants use.
- **AGRO_TANK**: any of the Lucario ex line (`Riolu` in its three legal printings — PRE 333, MEG 677, SCR 974 — plus `Mega Lucario ex`=678) or the Crustle line (`Dwebble`/`Crustle` in both legal printings — DRI 344/345, BLK 532/533). All eight IDs were verified directly against `data/official/EN Card Data.csv` (see rows 635, 652–654, 966–969, 1208–1210, 1679), not guessed.
- **UNKNOWN**: default — fires whenever neither signal is present, which mechanically includes an empty/undeveloped opponent board (empty ID set intersects nothing).

SNIPER takes priority if both signals were somehow present (the two ID pools don't overlap in practice, so this never actually triggers).

**Verified in real games**, not just by construction (see §5): against a real V6 opponent (Dragapult ex mirror), detection is `UNKNOWN` for the empty-board early turns and flips to `SNIPER` once mirror cards land (480/513 decisions across 6 games). Against `lucario_ex_agent`, it flips to `AGRO_TANK` the same way (448/525 decisions across 6 games).

## 4. Objective 3 — dynamic weight shifting

`MatchupWeights` wraps V6's existing `PolicyWeights` (kept fixed at `BALANCED` — V12 does not retune V6's own base profile) with five new fields, each **identity at `MATCHUP_DEFAULT`** (1.0 multiplier / 0.0 bonus), so UNKNOWN is guaranteed to fall back to V6's exact formulas:

```python
@dataclass(frozen=True)
class MatchupWeights:
    base: PolicyWeights
    bench_hp_multiplier: float = 1.0
    evolution_stage_multiplier: float = 1.0
    low_prize_bench_penalty: float = 0.0
    tempo_bonus: float = 0.0
    energy_accel_bonus: float = 0.0
```

Recomputed at the top of every `agent()` call (`self.detected_archetype = detect_archetype(op_state); self.weights = matchup_weights_for(...)`), i.e. *before* it is threaded into `pokemon_score()` and every other scoring path in the main option loop, per the governing task's instruction.

### SNIPER profile (`MATCHUP_SNIPER`)

```python
MATCHUP_SNIPER = MatchupWeights(
    base=BALANCED,
    bench_hp_multiplier=1.4,
    evolution_stage_multiplier=1.6,
    low_prize_bench_penalty=12000,
)
```

| Field | Value | Where it's applied | Effect |
|---|---|---|---|
| `evolution_stage_multiplier` | 1.6× | `pokemon_score()`'s stage1/stage2 bonus (250/130 → 400/208); **`OptionType.EVOLVE` scoring** (30000/70000 → 48000/112000) | Evolving Dreepy→Drakloak→Dragapult ex on the bench is prioritized more strongly, so bulkier forms replace the fragile 1-prize Dreepy sooner — the task's explicit goal ("evolve Dreepy/Drakloak on the bench faster so they don't get wiped by an opponent's Phantom Dive 6-damage-counter spread"). |
| `bench_hp_multiplier` | 1.4× | `pokemon_score()`'s flat `pokemon.hp` addend (opponent-board target valuation, the literal "passed to `pokemon_score()`" hook the task named); **also** the SWITCH/TO_ACTIVE candidate-scoring HP term (`hp * (1 + preservation_bias) * bench_hp_multiplier`) | The second application is the one that actually matches "value of bench HP" in spirit: when forced to promote a new Active, V12 leans harder toward the bulkiest bench Pokemon available — the ones most likely to have survived a counter spread. |
| `low_prize_bench_penalty` | 12000 | `hand_score()`'s `Budew` branch (`30000 → 30000 − 12000 = 18000`) | Budew is this decklist's only low-HP, non-evolving, 1-prize Basic — a cheap, undeveloped target for the mirror's own Phantom Dive. Its score drops from clearly above Drakloak's ready-to-evolve score (20000) to below it, so V12 now prefers developing the evolution line over benching Budew when both are live options — a real but *slight* deprioritization: Budew still scores well above zero and is never banned, since it remains useful support tech (Fezandipiti ex/Latias ex switch-in enabler) elsewhere in the formula. |

### AGRO_TANK profile (`MATCHUP_AGRO_TANK`)

```python
MATCHUP_AGRO_TANK = MatchupWeights(
    base=BALANCED,
    tempo_bonus=2000,
    energy_accel_bonus=600,
)
```

| Field | Value | Where it's applied | Effect |
|---|---|---|---|
| `tempo_bonus` | 2000 | `main_option_proc()`'s partial-damage branch: when a target survives this turn's hit, `base_score` is scaled by `damage/hp` as in V6, then `tempo_bonus * (damage/hp)` is added on top | Directly implements "increase the reward for immediate damage output": the attack-combo planner now values pressing damage *now* more heavily relative to holding back for a cleaner future KO. Scaled by the same ratio as the base score, so a token poke gets a token bonus and a substantial hit gets most of the 2000 — it doesn't inflate trivial chip damage into a priority. |
| `energy_accel_bonus` | 600 | `attach_score()`, added only when `active=True`, only on the main energy-count decision path (not the TOOL branch, not the Fezandipiti ex/Meowth ex/Latias ex support-switch-in branch, which are unrelated to tempo) | Directly implements "increase the reward for... energy acceleration to the Active Pokemon": attaching to the Active is now favored more strongly over attaching to the bench, keeping the attacker fed and swinging every turn against a high-HP target that would otherwise grind the game out. |

Neither profile touches the hard win-securing branches (`score = 50000` when a plan guarantees game-ending prizes, or the `1200`/`300` prize-count adjustments) — those stay absolute at every profile, exactly as V6's own `prize_value_multiplier` already guaranteed for its one existing knob.

## 5. Verification performed

1. **Import/packaging sanity**: `main_v12.py` imports cleanly, defines `agent()`, `DECK` has 60 entries; `tools/build_submission_challenger.py --version v12` passes every stage (deck legality, staged-directory standalone import, archive structure) — **PASS**.
2. **UNKNOWN ≡ V6 exactly, mechanically verified, not just asserted by construction.** Ran V6 vs. `iono_agent` (a deck with no SNIPER/AGRO_TANK signature cards) for 6 full games, and at every one of V6's 600 real in-game decisions, fed the *identical* observation dict to a freshly-instantiated V12 policy and diffed the chosen action list. **0/600 mismatches**, and V12's detector reported `UNKNOWN` on all 600 — confirms `MATCHUP_DEFAULT`'s identity values genuinely reduce to V6's formulas in the live engine, not merely on paper.
3. **Detection fires correctly in real games, not just by construction.** V12 vs. a real V6 opponent (Dragapult ex mirror): archetype sequence is `UNKNOWN` for 33 early-game decisions (empty/undeveloped opponent board) then `SNIPER` for 480/513 remaining decisions across 6 games, once mirror cards hit the field. V12 vs. `lucario_ex_agent`: `UNKNOWN` for 77 decisions then `AGRO_TANK` for 448/525, same pattern.
4. **Self-play smoke test (crash check) across three matchup types**, 4 games each, `tools/tournament.py`, no aborts:
   - V12 vs. V6 (SNIPER trigger): 4/4 games completed cleanly, 2-2 split.
   - V12 vs. `lucario_ex_agent` (AGRO_TANK trigger): 4/4 completed cleanly, 2-2 split.
   - V12 vs. `iono_agent` (UNKNOWN): 4/4 completed cleanly, 2-2 split.

   Per the project's own preliminary-result rules, these 4-game splits are **not** treated as evidence of a win-rate effect — they exist only to confirm the archetype-detection code path doesn't crash or hang when reading a real opponent's board, across all three profiles, including the SNIPER mirror case where both agents are simultaneously trying to read each other's evolving Dragapult ex line. No larger benchmark was run for this task, per the "build and package, do not submit" scope.

## 6. Deliverables

- `src/agents/dragapult_policy_v12.py`, `dragapult_agent_v12.py`, `final_candidate_agent_v12.py`, `main_v12.py`
- `tools/build_submission_challenger.py` (extended for v12)
- `submission/challenger_v12_20260814T032607Z.tar.gz` (2.01 MB), staging dir preserved at `submission/_staging_v12/` for inspection
- This report

**Not done, by explicit instruction**: no Kaggle submission (`kaggle competitions submit` was never called by this task or by `build_submission_challenger.py`, which never calls it under any version); no larger-scale A/B benchmark against V6 to measure an actual win-rate delta (would be the natural next step once approved, ideally run the same way as the project's existing V2-V11 comparisons — paired, first-player-alternated, raw-data-preserved).
