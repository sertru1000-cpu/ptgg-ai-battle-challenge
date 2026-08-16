# V14 Implementation Report — Dynamic Game-Phase Policy

**Status:** built and packaged locally. **NOT submitted to Kaggle** — awaiting explicit user approval, per the governing task's instruction.

## 1. Scope and what V14 is not

V14 forks **V6** (`dragapult_policy_v6.py` / `dragapult_agent_v6.py`), not V10 — same decklist (`decks/dragapult_ex.csv`), same greedy scoring engine (attack-combo subset-sum search, hand/attach/switch heuristics), same two Phantom Dive bug fixes V6 shipped. Explicitly out of scope, per the governing task, and NOT present in this fork:

- No lookahead/search — that's V11's job. V14 is a single-ply greedy policy exactly like V6.
- No V8/V9 survival/defensive-retreat heuristics. V6's own (V2-era) defensive-retreat hook is carried over completely unmodified; V14 adds nothing to it and does not tune its thresholds.
- No change to V10's deck or setup logic — V14 never imports from V10.

One deliberate, disclosed deviation from a strict line-for-line copy — the same one V12 already made, for the same reason: V6 carries a V5-only in-battle *opponent-aggression* model (`_observe_opponent` / `_compute_adaptive_weights`, dead code whenever `adaptive=False`, which V6's own `dragapult_agent_v6.py` always sets). That mechanism is orthogonal to this task (game phase, not opponent aggression) and, wired through unchanged, would type-mismatch the moment `self.weights` stopped being the new `PhaseWeights` wrapper. Removed rather than patched around; V14 has no `adaptive` mode. Everything else — the attack-combo planner, every hand/attach/switch scoring branch, both V6 Phantom Dive fixes — is unchanged.

## 2. Files created

| File | Role |
|---|---|
| `src/agents/dragapult_policy_v14.py` | Forked engine: V6's scoring logic + `detect_phase()` + `PhaseWeights` |
| `src/agents/dragapult_agent_v14.py` | Thin binding: `make_agent(BALANCED)` (V14's fixed base profile — identical to V6's) |
| `src/agents/final_candidate_agent_v14.py` | Safety-wrapped submission candidate (`safety_wrapper` → `timeout_shield` → policy), mirrors V6's own composition |
| `main_v14.py` | Kaggle entry point, mirrors `main_v6.py`/`main_v12.py` structure exactly |
| `tools/verify_v14_real_game_smoke_test.py` | Local self-play/cross-play smoke test + phase-detection histogram + V6-equivalence/divergence check |
| `tools/build_submission_challenger.py` | Extended: `v14` added to `VALID_VERSIONS`, `DECK_SOURCE["v14"] = "dragapult_ex.csv"` |

**Deck verified identical to V6** (Objective 1): `dragapult_agent_v14.py` and `dragapult_agent_v6.py` both read `decks/dragapult_ex.csv` via the same `_DECK_PATH` construction (byte-identical to the shared root `deck.csv`, confirmed via `diff`); the smoke test's own first check does a card-for-card `V14_DECK == V6_DECK` comparison (**PASS**); `tools/build_submission_challenger.py --version v14` re-validates deck legality at packaging time (real `battle_start` check, `decks/dragapult_ex.csv: LEGAL`).

## 3. Objective 2 — game-phase detection

`detect_phase(my_prizes, op_prizes, turn)` in `dragapult_policy_v14.py` reads both players' own remaining prize-pile sizes (`len(state.players[i].prize)` — each side's own prize count is always-visible engine data, never hidden opponent info) plus the turn counter, and classifies every decision as one of `EARLY` / `MID` / `LATE`:

```python
def detect_phase(my_prizes: int, op_prizes: int, turn: int) -> str:
    if my_prizes <= 2 or op_prizes <= 2:
        return PHASE_LATE
    if turn <= 3:
        return PHASE_EARLY
    if my_prizes <= 4 or op_prizes <= 4:
        return PHASE_MID
    return PHASE_EARLY
```

Priority order, and why:

1. **LATE wins unconditionally** ("either player has 1 or 2 prizes remaining") — lethal urgency matters more than turn count or which bucket the other side is in.
2. **`turn <= 3` forces EARLY** — the task's own explicit "or turn counter <= 3" alternative condition. In practice this branch is rarely load-bearing on its own: no attack is legal before turn 2 (needs an energy attachment first), so both sides sit at 5–6 prizes through turn 3 in every real game observed locally — the prize-count rule below would already return EARLY in that case. Kept as an explicit, separate branch anyway so the read is correct by construction even in a hypothetical early-KO edge case, not just by empirical luck.
3. **MID** fires when either side is down to 3 or 4 prizes.
4. **EARLY is the remaining default** — mechanically only reachable here when both sides are still at 5 or 6 (prize counts are integers in [0, 6]; neither branch 1 nor 3 matched), i.e. exactly "both players have 5 or 6 prizes remaining."

Recomputed fresh on every decision (`self.detected_phase = detect_phase(...)`, top of `agent()`), not cached, since prize counts change turn over turn.

**Verified firing in real games, not just by construction**: 5 full games (self-play ×3, vs `abomasnow_agent`, vs `generic_mewtwo_agent`) produced a combined phase histogram of `{EARLY: 271, MID: 97, LATE: 111}` decisions (numbers vary run-to-run — this engine has no RNG seed control — but all three phases fire in every run observed).

## 4. Objective 3 — dynamic weight modulation by phase

`PhaseWeights` wraps V6's existing `PolicyWeights` (kept fixed at `BALANCED` — V14 does not retune V6's own base profile) with four new fields, each **identity at `PHASE_MID_WEIGHTS`** (0.0 bonus / 1.0 multiplier), so MID reproduces V6's exact formulas — directly implementing the task's own MID instruction, "Use standard V6 default weights":

```python
@dataclass(frozen=True)
class PhaseWeights:
    base: PolicyWeights
    draw_bonus: float = 0.0
    basic_bonus: float = 0.0
    prize_aggression_multiplier: float = 1.0
    switch_risk_relief: float = 1.0

PHASE_MID_WEIGHTS = PhaseWeights(base=BALANCED)
```

Recomputed at the top of every `agent()` call (`self.detected_phase = detect_phase(...); self.weights = phase_weights_for(...)`), i.e. before it is threaded into `pokemon_score()` and every other scoring path in the main option loop, per the governing task's instruction.

### EARLY profile (`PHASE_EARLY_WEIGHTS`)

```python
PHASE_EARLY_WEIGHTS = PhaseWeights(
    base=BALANCED,
    draw_bonus=8000,
    basic_bonus=10000,
    prize_aggression_multiplier=1.0,
    switch_risk_relief=1.0,
)
```

| Field | Value | Where it's applied | Effect |
|---|---|---|---|
| `draw_bonus` | +8000 | `hand_score()`'s Crispin / Brock's Scouting / Lillie's Determination branches (the three card-draw/search Supporters in this decklist), **and** the top-level `OptionType.PLAY` scores for the same three cards (`35000 + draw_bonus`, `14000 + draw_bonus`) | Directly implements "boost scores for card-draw supporters." Applying the bonus at *both* the internal `hand_score()` level (which decides which Supporter wins the once-per-turn "which support card to commit to" race, `self.use_support`) *and* the top-level PLAY score (which decides whether that Supporter beats a competing Item this decision) was necessary for the boost to actually be decisive — an earlier version only touched `hand_score()`, and a real-game equivalence test (§5) found **zero** resulting divergences from V6 across 318 sampled EARLY decisions, because the PLAY-level score for these three cards was hardcoded independent of `hand_score()`'s value. Fixed by adding the bonus at both sites. |
| `basic_bonus` | +10000 | `hand_score()`'s Dreepy and Buddy-Buddy Poffin branches, **and** the top-level `OptionType.PLAY` scores for the same two cards (`51000 + basic_bonus` for playing Dreepy from hand, `46000 + basic_bonus` for Buddy-Buddy Poffin — this engine's functional Nest Ball equivalent) | Directly implements "boost scores for basic Pokemon placement (Buddy-Buddy Poffin / Nest Ball equivalents)." Same both-sites fix as `draw_bonus`, for the same reason. |
| *(no separate field)* | — | — | "Lower the relative penalty for passive development turns (doing setup instead of weak early attacks)" has no dedicated knob: V6's own `ATTACK` option score is already just the raw `attackId` (e.g. 154 for Phantom Dive) — already far below any real setup action's score (thousands to hundreds of thousands) — so attacking never crowds out setup within a turn's decision loop *by construction*, in every phase. `draw_bonus`/`basic_bonus` above widen that existing gap specifically in EARLY, which is the literal ask, without inventing an artificial "attack penalty" that doesn't otherwise exist in V6's scoring structure (same "don't invent a hook the engine doesn't need" discipline `policy_weights.py`'s own docstring documents for two hooks it deliberately left out). |

### LATE profile (`PHASE_LATE_WEIGHTS`)

```python
PHASE_LATE_WEIGHTS = PhaseWeights(
    base=BALANCED,
    draw_bonus=0.0,
    basic_bonus=0.0,
    prize_aggression_multiplier=1.5,
    switch_risk_relief=3.0,
)
```

| Field | Value | Where it's applied | Effect |
|---|---|---|---|
| `prize_aggression_multiplier` | 1.5× | `pokemon_score()`'s prize-count term (`prize_count(...) * 1000 * base.prize_value_multiplier * prize_aggression_multiplier`), which feeds both `main_option_proc()`'s attack-combo/counter-placement planner and the `DAMAGE_COUNTER`/`DAMAGE_COUNTER_ANY` targeting score; **and** a new, plan-gated bonus on the `OptionType.ATTACK` score itself (`score += (prize_aggression_multiplier - 1.0) * 20000` when `self.plan_a.attack > 0`, i.e. when the combo planner has already identified a productive Phantom Dive target) | Directly implements "aggressively boost attack scores and damage multipliers." The `pokemon_score()` scaling alone was found, by the same real-game equivalence methodology as EARLY (§5), to rarely change the argmax on its own — the combo search is frequently already saturated at V6's hard `50000` guaranteed-lethal score, or the opponent's board doesn't offer enough close-valued alternative targets for a 1.5× scale to reorder. The ATTACK-score addition was added on top so the phase can also express "stop doing marginal setup, just take the shot" once a productive plan exists — this is the mechanism that produced the confirmed divergences in §5. |
| `switch_risk_relief` | 3.0× | `SWITCH`/`TO_ACTIVE`/`SETUP_ACTIVE_POKEMON` candidate scoring: `score -= 1000 / (base.switch_risk_tolerance * switch_risk_relief)` for Fezandipiti ex, `score -= 2000 / (...)` for Meowth ex | Directly implements "remove penalties for retreating or sacrificing a secondary Pokemon if it clears the path for a game-winning prize" — shrinks V6's existing fixed penalty for switching in a risky support Pokemon (the same knob V3/AGGRESSIVE already uses at a smaller 1.3× via `switch_risk_tolerance` itself). **Honesty note**: in this specific decklist, Fezandipiti ex / Meowth ex's baseline switch-candidate score sits so far below the main attacking line's (Dreepy 10000+ / Drakloak 20000+ / Dragapult ex 50000+ / Budew 30000-100000, before the penalty is even applied) that no amount of penalty relief was observed to flip which Pokemon gets promoted in local testing — a known property of the underlying `switch_risk_tolerance` mechanism, not a defect introduced here (V3/V4/V5 tune the same knob across a comparably wide range). The hook is correctly wired to the semantically right call site per the task's instruction; it just wasn't the lever that produced §5's confirmed LATE divergence — `prize_aggression_multiplier`'s ATTACK-score addition was. |

Neither profile touches the hard win-securing branches (`score = 50000` when a plan guarantees game-ending prizes) — those stay absolute at every phase, exactly as V6's own `prize_value_multiplier` already guaranteed for its one existing knob.

## 5. Verification performed

1. **Import/packaging sanity**: `main_v14.py` imports cleanly, defines `agent()`, `DECK` has 60 entries; `tools/build_submission_challenger.py --version v14` passes every stage (deck legality, staged-directory standalone import, archive structure) — **PASS**.
2. **Deck identity** (Objective 1): `V14_DECK == V6_DECK`, card-for-card, 60/60 — **PASS**.
3. **No crash, only legal actions, real activity**: 5 full real games (self-play ×3, vs `abomasnow_agent`, vs `generic_mewtwo_agent`) via `tools/verify_v14_real_game_smoke_test.py`. All passed: no crash across any game; attacked in every run; evolved in every run; played Buddy-Buddy Poffin in most runs (deck-draw dependent, as expected).
4. **All three phases fire in real play**: combined histogram across the 5 games, `{EARLY: 271, MID: 97, LATE: 111}` (one representative run — exact counts vary run-to-run since this engine has no RNG seed control, but all three phases fire in every run observed) — **PASS**.
5. **MID ≡ V6 exactly, mechanically verified, not just asserted by construction.** Same methodology V12's own report used: ran 6 real games (a fresh V6 instance actually driving player 0's moves, vs `abomasnow_agent` ×2 / `generic_mewtwo_agent` ×2 / a second fresh V6 instance ×2), and at *every one* of V6's own decisions, fed the identical observation dict to a separately-instantiated, live V14 "shadow" policy (never used to drive the game, but fed the exact same observation stream turn-for-turn so its internal log/prize bookkeeping stays in lockstep) and diffed the chosen action lists, bucketed by the shadow's own `detected_phase`. Aggregated over the 6 games: **0/120 mismatches when the shadow's own `detected_phase == MID`** — confirms `PHASE_MID_WEIGHTS`'s identity values genuinely reduce to V6's exact formulas in the live engine.
6. **EARLY and LATE both provably diverge from V6 in real play** (confirms the phase hooks are live code, not dead weight, using the same shadow methodology): **8/263 EARLY decisions diverged**, **6/70 LATE decisions diverged** (representative run; both counts are non-zero, i.e. real behavioral changes were observed, not just theoretical). Getting a non-trivial LATE sample required running the equivalence check across 6 game pairings rather than 1 — LATE-phase decisions are naturally rare (only the last few turns of each game), and an earlier single-game check happened to sample only 1 LATE decision with 0 divergence, which on its own would have been inconclusive rather than a real finding.
7. Full raw per-check output preserved in `tools/verify_v14_real_game_smoke_test.py`'s own run (re-runnable; not a one-off log) — tagged here as a **measured result** from local self-play sampling against this project's own local opponent pool, not a claim about the real Kaggle ladder meta.

## 6. Deliverables

- `src/agents/dragapult_policy_v14.py`, `dragapult_agent_v14.py`, `final_candidate_agent_v14.py`, `main_v14.py`
- `tools/verify_v14_real_game_smoke_test.py`
- `tools/build_submission_challenger.py` (extended for v14)
- `submission/challenger_v14.tar.gz` and `submission/challenger_v14_20260814T042209Z.tar.gz` (2.03 MB, byte-identical), staging dir preserved at `submission/_staging_v14/` for inspection
- This report

**Not done, by explicit instruction**: no Kaggle submission (`kaggle competitions submit` was never called by this task or by `build_submission_challenger.py`, which never calls it under any version); no larger-scale A/B benchmark against V6 to measure an actual win-rate delta (would be the natural next step once approved — this report's §5 divergence counts establish that V14 *behaves differently* from V6 in a phase-scoped, semantically-appropriate way, not that it wins more, which is a separate, larger question this task explicitly did not ask to answer yet).
