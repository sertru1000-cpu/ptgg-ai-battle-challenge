# Engine Clone / Shallow-Lookahead Feasibility Audit

**Scope**: read-only engine feasibility audit. No agent code, engine code, weights,
decklists, or submissions were modified. No lookahead was implemented. This document
only answers: *can the current ctypes-based `cg` engine cheaply and safely clone a
live game state to simulate ~5–10 candidate actions independently before choosing one?*

**Sources traced** (real production path, not filenames-only):
- C++ engine source: `data/official/ptcg_engine/ptcgProgram 22/{Export.cpp,Api.h,ApiData.h,ApiType.h,Search.h,BattleData.h,State.h,Game.h,Core.h,Card.h}`
- Python ctypes boundary: `data/official/sample_submission/sample_submission/cg/{sim.py,game.py,api.py}`
- This repo's own usage of that boundary: `src/environment/engine_loader.py`, `src/agents/search_lookahead.py`, `src/agents/search_lookahead_v2.py`
- Prior project research already on disk: `docs/environment.md`, `docs/search_api.md`, `results/search_v2_audit.md`
- A new, isolated, non-destructive benchmark harness written for this audit (Part 6), run against the real `cg.dll` via the real `deck.csv`, never touching `src/agents/*` or `main*.py`.

---

## Part 1 — Engine state architecture (traced call chain)

```
Python agent (src/agents/*.py, main*.py)
   │  battle_select(action) / battle_start(deck0, deck1)
   ▼
cg/game.py  ──ctypes──▶  cg.dll  (GAME_API exported C functions, Export.cpp)
   │                         │
   │                         ▼
   │                    ApiData* (opaque, C++ heap object; Python only ever
   │                    holds its ctypes.c_void_p address, "battle_ptr")
   │                         │
   │                         ▼
   │                    ApiData : BattleData  { Game game; State state; ... }
   │                    (Api.h/ApiData.h, BattleData.h)
   ▼
Python sees only: a JSON-decoded `Observation` dataclass (rebuilt fresh every
call from a JSON string returned by the DLL) + a `c_void_p` handle it never
dereferences.
```

**What Python actually holds**: a single `ctypes.c_void_p` (`Battle.battle_ptr` in
`cg/game.py:36`, or `agent_ptr` in `cg/api.py:544`) — an **opaque native pointer**,
not a `ctypes.Structure` mirroring the game state and not a serialized buffer kept
resident in Python. Every observation is a **one-shot JSON→dataclass reconstruction**
(`cg/api.py: to_observation_class`), thrown away and rebuilt on the next call. Python
never has a live, mutable view into the C++ memory — it is a request/response boundary
around one authoritative object living entirely in native heap memory.

**Where the authoritative state lives**: entirely inside the C++ process, in one
`ApiData` object per handle. `ApiData` (`ApiData.h:12-25`) contains:
- `Game game` — engine-wide mutable context: RNG (`std::mt19937 rng`), `GameConfig`,
  per-player remaining time, small scratch buffers, `recordLog`/`manualCoin` flags.
- `State state` — the actual board: turn counters, both `PlayerState`s, `allCard`
  (fixed array of 128 `Card`s, see Part 3), selection/effect machinery, logs.
- `Search search` — a **second**, purpose-built object holding a **pool of extra
  `State` clones** (see Part 2). This is the mechanism the rest of this audit is about.

**Multiple native objects representing one game?** Yes, by design, and this is the
key architectural fact for this audit:
1. **The live match** — `ApiData* battle_ptr` (`apiDataType = 1`, created by
   `BattleStart`). This is the one real game; only `Select`/`GetBattleData` touch it.
2. **The agent's private search sandbox** — a *separate* `ApiData* agent_ptr`
   (`apiDataType = 2`, created once via `AgentStart()`). This object owns its own
   `Game`/`State`/`Search`, entirely disjoint from `battle_ptr`. Cloning happens
   **inside this second object only** — the live match's `ApiData` is never touched
   by search calls (Export.cpp:80-84,98,136-160 all gate on `apiDataType`, refusing
   cross-use — e.g. `Select` errors 30 if called on `apiDataType==2`, `SearchBegin`
   errors 30 if called on `apiDataType==1`).

---

## Part 2 — Existing clone/snapshot mechanisms

A grep across the full engine + Python boundary for clone/copy/snapshot/serialize
found **one real mechanism** (not a placeholder, not partially implemented) plus
one serialization path that feeds it:

### A. Direct in-process state cloning — `Search` (`Search.h:45-242`)

```cpp
using StateArray = std::array<State, 128>;   // pool, 128 States per block

SearchState alloc(const State& src) {
    ...
    State* state = freeStateList.back();  // reuse a pooled slot
    freeStateList.pop_back();
    *state = src;                         // <-- THE CLONE: C++ struct assignment
    ss.state = state;
    return ss;
}
```

`Search::start()` (called by `SearchBegin`) and `Search::step()` (called by
`SearchStep`) **both** call `alloc(src)` before mutating anything. This means every
`SearchStep` call already performs "clone-then-apply-action" atomically — see Part 4.

`*state = src` is the compiler-generated `State::operator=`. Traced `State`'s members
(`State.h:110-236`): a `Game*` raw pointer, a mix of `std::array`/fixed-size
containers, and 14 `std::vector`/dynamic-container members (`options`, `selected`,
`preTargetList`, `targetList`, `koList`, three trigger stacks, `turnUsedSkill`,
`turnPlay`, `turnHeal`, `turnEvolve`, `functionStack`, `logs`). Default assignment
deep-copies every `std::array`/`std::vector` member (each vector gets its own new
heap buffer) — **except** the raw `Game*`, which is copied by value (i.e. **all
clones point at the same single `Game`**). This is the central fact for Parts 3–5.

`Card` itself (embedded 128× in `State::allCard`, `Card.h:192`) is confirmed
plain-old-data — ints/shorts/bools/unions/fixed arrays only, no pointers, no
`std::vector`/`std::string` — so per-card data is always a true, independent copy.

### B. Serialization/deserialization — exists, but for a different purpose

`State::serialize`/`deserialize` (`State.h:243-279`) plus `ApiGetBattleData`/
`SetBattleData` (`Api.h:99-120`) round-trip a `State` through a base64 buffer. This
is **not** used for cloning — it's used once per real decision to hand the *live*
match's state across the ctypes boundary into the agent's *own* process memory
(`SearchBegin`'s `serialized` argument, `cg/api.py:574`), after which the native
`Search::start()` (mechanism A) does the actual cloning. So: real serialization
exists, but it's the transport for *entering* the search sandbox, not the cloning
primitive itself.

### C. Creating a new hypothetical game from an existing state — yes, this is exactly
what `SearchBegin` does (`Api.h:158-160` → `Search::start`, `Search.h:89-164`):
takes the live match's (sanitized — see Part 5) state, clones it, and fills the
erased hidden zones with agent-supplied predicted card IDs.

### D–F. No raw native-memory-copy API, no "replay from turn 0" reconstruction path,
and no other mechanism exists. Mechanism A is the only one, and it is sufficient.

**Does it produce a TRUE independent state?** For all board/card/selection data:
**yes**, verified by source (deep vector + array copy). For the shared `Game`
(RNG, config, clock): **no** — see Part 5, this is the one real caveat.

---

## Part 3 — ctypes safety & `deepcopy()` / memory-leak analysis

**`copy.deepcopy()` on anything Python holds is not meaningful and would not work as
hoped.** Python never holds a `ctypes.Structure` mirroring the state — it holds a bare
`c_void_p` (an integer address) and, separately, plain-old Python dataclasses
(`Observation`) that are just JSON snapshots. Concretely:

- `deepcopy(Battle.battle_ptr)` — `c_void_p` deepcopies as **the same pointer value**
  (ctypes simple types deepcopy by value-copy of the address, not by copying pointee
  memory) → **(B) from the prompt's framing**: two Python objects, one native game.
  Mutating through either "clone" mutates the one real object twice.
- `deepcopy(observation_dataclass)` — this *would* produce an independent Python
  object, but it's a dead end: it's a read-only snapshot with no way to feed it back
  into the engine to keep simulating (the engine has no "load an arbitrary
  `Observation` and resume" entry point — only `SearchBegin`, which requires a live
  `search_begin_input` token minted by the engine itself, `cg/api.py:546-548`, tied to
  the live battle's internal state pointer at that instant — not something you can
  manufacture from a deepcopy of a dataclass).
- **Conclusion**: `deepcopy()` is not a valid clone mechanism at any layer of this
  boundary, confirming the prompt's instruction not to assume it is. The only valid
  clone mechanism is native, inside `Search` (Part 2A), invoked via `SearchBegin`/
  `SearchStep`.

### Memory leak check — traced, then empirically measured

Traced: `Search` pools `State` objects in blocks of 128 (`StateArray`). `clearSingle`
(`search_release`) and `clear()` (`search_end`) return slots to `freeStateList` for
**reuse**, not `free()`/`delete` back to the OS — memory grows to a high-water mark and
stays resident (normal for a pool allocator) but is **not leaked** in the sense of
becoming unreachable, as long as `search_end`/`search_release` are called. There is
**no exported "destroy the agent sandbox" function** (`AgentStart` has no counterpart
in `Export.cpp`), but the repo's own usage (and the official sample notebook) create
`agent_ptr` exactly once per process and keep it for the process lifetime — correct
usage, not a leak.

Rather than trust this trace alone, I wrote an isolated, read-only benchmark
(scratchpad-only, not committed to the repo, never touches `src/agents/*`) that plays
a real self-play game through the actual `cg.dll` with `deck.csv`, and at 60 real
decisions either (a) calls `search_end()` every decision (correct usage) or (b) never
releases anything (worst case):

| Hygiene | Decisions | RSS start | RSS end | Δ |
|---|---|---|---|---|
| `search_end()` every decision (correct) | 60 (≤10 branches each, ≤600 clones) | 30.8 MB | 32.1 MB | **+1.2 MB** |
| Never released (worst case) | 60 (≤600 clones, never freed) | 31.7 MB | 38.1 MB | **+6.4 MB** |

**Result**: even the deliberately-bad-hygiene worst case grows by roughly 0.1 MB per
decision at 10 clones/decision. A full match (docs/environment.md: 10-minute wall
clock, realistically well under 100 real decisions) would add single-digit MB even if
`search_end()` were never called once. **This is not an OOM risk** given
`docs/environment.md`'s recorded ~6.8 GB free at audit time. With correct hygiene
(call `search_end()` once per real decision, exactly as the official sample notebook
and this repo's `search_lookahead*.py` already do) the growth is negligible.

---

## Part 4 — Mid-turn (arbitrary decision-point) cloning: **YES, and better than the naive model**

The engine supports cloning at the exact instant an agent must choose an action —
not just before/after turn — because `SearchBegin` is invoked *from inside* a live
`agent(obs)` call, using that exact call's `search_begin_input` token
(`docs/search_api.md` FACT, confirmed against `cg/api.py:517-595`). There is no
"before turn" restriction anywhere in the native code.

More importantly, tracing `Search::step()` (`Search.h:166-194`) reveals the *actual*
mechanism is more efficient than the prompt's diagram assumes:

```
clone                                    clone (root, ONE time per decision)
  ↓                                         ↓
candidate action        actually is:    search_step(root_id, A) ─┐
  ↓                                     search_step(root_id, B) ─┼─ each call clones
engine resolves action                  search_step(root_id, C) ─┤  FROM THE PRISTINE
  ↓                                     search_step(root_id, D) ─┤  ROOT internally
inspect resulting state                 search_step(root_id, E) ─┘  (Search.h:178,
                                                                      `alloc(*src.state)`)
```

`search_step(id, action)` **is itself** "clone-from-`id`'s-state, then apply
`action`" — the clone and the action-apply are fused into one call
(`Search::step` → `alloc(*src.state)` then `state.step()`). Calling it repeatedly with
the same `root_id` produces **N independently-cloned branches**, each starting from
the same untouched root — this is exactly the "5–10 candidate actions independently"
pattern requested, and it's cheaper than doing an explicit clone per candidate because
the expensive part (deserializing the live match's state + filling predicted hidden
zones, `Api.h:99-164`) is paid **once per decision**, not once per candidate. This is
already how this repo's `src/agents/search_lookahead.py`/`_v2.py` use it
(`_begin_shared_search`, called once, then `search_step` per candidate).

---

## Part 5 — RNG / hidden-state safety

### RNG sharing — real, confirmed by source, not resolved automatically

`State::game` is a raw `Game*`. `ApiAgentStart()` (`Api.h:84-93`) sets
`data->state.game = &data->game` — **one `Game` per agent sandbox**. Because struct
assignment copies pointers by value, **every clone produced by `Search::alloc` shares
that same single `Game`**, including its `std::mt19937 rng`. Grep confirms `game->rng`
is consumed in at least 6 files (coin flips, shuffles, effect/select resolution:
`CardMove.h`, `EffectInstant.h`, `EffectProc.h`, `SelectProc.h`, `Search.h`, `Api.h`)
— this is pervasive, not a rare edge case.

**Consequence**: if candidate A's simulated action consumes RNG draws (a coin-flip
attack, a shuffle) before candidate B is stepped, candidate B's random draws come from
wherever A left the shared stream — **branches are not statistically independent or
reproducible**, and execution order matters. This is a real simulation-contamination
risk for any card whose outcome depends on chance (this repo's own roster includes
several — Iono's deck alone has multiple coin-flip attacks per `results/search_v2_audit.md`
§6 table). There is **no exposed API** to snapshot/restore just the RNG (no seed
parameter on `search_begin`, confirmed in `docs/search_api.md` §5/§1) — the only way to
get a fresh independent RNG stream per branch would be a new `agent_ptr` per branch
(possible but defeats the pooling design and multiplies the "no AgentFinish" resident
cost from Part 3 by the branch count).

**Practical scope of the risk**: deterministic-outcome actions (most attacks/plays
with no coin flip) are entirely unaffected — the shared RNG is simply never touched.
It matters specifically for chance-dependent cards, and specifically for *comparing*
branches that both consume RNG (their comparison becomes noisy, not their individual
legality/correctness).

### Hidden-information / cheating prevention — confirmed safe by source trace

Before a live state ever crosses the ctypes boundary, `ApiGetBattleData`
(`Api.h:99-113`) calls `state.erasePlayerData(state.selectPlayer)`
(`State.h:288-315`), which:
- erases **my own** prize and deck *contents* (order/identity — matching physical TCG
  rules: you don't know your own shuffled deck/prize order either),
- erases the **opponent's** prize, hand, and deck *entirely*, and erases any
  face-down active Pokémon's identity.

Only after this erasure does the sanitized state get serialized and handed to
`SearchBegin`, whose `set()` lambda (`Search.h:104-160`) fills those now-empty slots
using **the agent's own supplied guesses** (`your_deck`/`your_prize`/`opponent_deck`/
`opponent_prize`/`opponent_hand`/`opponent_active` — plain `list[int]` parameters the
agent must construct, `cg/api.py:517-595`). The native layer enforces only that guess
*counts* match reality — it does not (and structurally cannot, since it never
received the real hidden data) leak or validate plausibility of the guesses.

**Result**: the engine cannot leak real hidden opponent information into a simulation
even by an agent bug — the true data is erased at the source, server-side (well,
engine-side) of the boundary, before Python ever sees it. Any "cheating" would have to
be the agent's own hidden-info *predictor* being unrealistically good, not an engine
leak. This matches `docs/search_api.md`'s independently-derived FACT (§1) and this
repo's `search_v2_audit.md`/`search_lookahead*.py` treat determinization exactly this
way.

### Can simulations be run independently?

**Mostly yes, with one caveat.** Board state, card identity, selection state, logs:
fully independent per clone (Part 2A). RNG: **not independent** — shared mutable
stream across all clones from one sandbox, order-dependent. Flag this explicitly as
the one non-independence in an otherwise clean architecture.

---

## Part 6 — Performance benchmark (measured, not modeled)

Isolated harness (scratchpad-only; not part of the repo; never imports or calls
`src/agents/*`), driving a real self-play game through the actual `cg.dll` with the
real `deck.csv`. At 40 real decisions offering ≥2 legal options, benchmarked the
actual usage pattern from Part 4 (one shared root, then `search_step` per candidate,
up to 10 candidates/decision, 165 total step samples):

| Phase | median | p95 | max |
|---|---|---|---|
| **Root clone** (`search_begin`: deserialize + native clone + fill predicted hidden zones) | 0.30 ms | 0.45–0.55 ms | 0.87–1.34 ms (2 runs) |
| **Branch + action + observe** (`search_step`, total) | 0.06 ms | 0.10 ms | 0.19–0.69 ms |
| — native portion only (raw `ctypes` call into the DLL) | 0.02 ms | 0.03–0.04 ms | 0.05–0.07 ms |
| — Python portion (JSON decode + dataclass rebuild) | 0.04 ms | 0.07 ms | 0.17–0.66 ms |

Notably, the Python-side JSON/dataclass reconstruction (~65% of `search_step`'s cost)
dominates over the actual native engine work (~35%) — the engine itself is not the
bottleneck; the JSON marshalling convention is.

**Estimated cost, using the real "1 clone + K branches" pattern (Part 4), median:**

| Simulations | Formula | Estimated cost |
|---|---|---|
| 5 | 0.30 ms + 5 × 0.06 ms | **~0.61 ms** |
| 10 | 0.30 ms + 10 × 0.06 ms | **~0.93 ms** |

This is roughly three orders of magnitude below anything that could threaten a
per-decision or per-match time budget (Part 7).

---

## Part 7 — Actual Kaggle time budget

From `docs/environment.md` (recorded from the competition rules page, not guessed):

> **Match time limit: 10 minutes per match total**, and a player that exhausts it
> **loses on timeout**. This is a hard wall-clock budget for an *entire game* (all our
> turns combined), not per move.

- **Per-decision limit**: **not documented anywhere in the repo or competition
  materials found** — only the whole-match 10-minute budget exists. Stating this
  explicitly per the audit's instruction not to guess: no per-move cap has been
  established; the constraint is cumulative across the whole game.
- **Do ctypes/native calls count toward the same limit?** Yes — it's wall-clock for
  the whole match, and all `search_*` calls are ordinary synchronous ctypes calls on
  the same process/thread as everything else the agent does, so they consume the same
  budget as move selection itself.
- **Timeout fallback?** Not found in the repo — `docs/environment.md` states timeout
  = loss, with no mention of an engine-side or platform-side fallback/pass. This
  repo's own search wrappers (`search_lookahead.py`/`_v2.py`) implement their **own**
  safety net (try/except around every search call, falling back to the un-searched
  heuristic decision on any error) — a defensive pattern worth keeping for any future
  lookahead, but it is agent-side discipline, not an engine guarantee.

`simulation_budget_ratio = (clone + action + observation) / decision_time_budget`:
with no per-decision budget documented, this ratio can only be computed against the
whole-match budget: **~0.9 ms / 600,000 ms ≈ 0.0000015** for a 10-candidate decision —
even if every single decision in a long game did a full 10-candidate simulation, a
100-decision game would spend **~90 ms total** out of a 600,000 ms budget.

---

## Part 8 — 5–10 simulation feasibility verdict

### **GREEN** — 5–10 forward simulations per decision are comfortably feasible.

Rationale:
- A real, correct, already-used-in-this-repo clone mechanism exists (Part 2A), is
  invoked at exactly the right point (arbitrary decision-time, Part 4), produces true
  independent copies of all board/card/selection data (Part 3), and safely masks
  hidden information by construction (Part 5).
- Measured cost for 10 simulations (~0.9 ms median) is roughly 5–6 orders of
  magnitude below the only documented time constraint (10 min/match, Part 7).
- Memory growth even under worst-case (never-released) hygiene is single-digit MB
  over 60 decisions × 10 clones (Part 3) — no realistic OOM path within one match.

**The one real caveat, not a blocker but must be designed around**: the shared-`Game`
RNG (Part 5) makes branches non-independent specifically for chance-dependent actions.
This doesn't change the GREEN verdict on cost/feasibility, but it means "5–10
independent simulations" is true for state/board data and **not strictly true** for
randomness — any evaluation function comparing branches should either (a) tolerate
that chance-dependent candidates get one non-reproducible sample rather than a clean
comparison, or (b) avoid weighting single random outcomes heavily in the evaluation
(e.g., use the coin-flip attack's *expected* value from card data rather than trusting
one simulated draw).

**Lighter alternatives** (available if ever needed, not needed for a GREEN case):
- Clone only top-K candidates after a cheap tactical pre-filter (already how V1/V2
  scope MAIN/ATTACK-only decisions, `search_v2_audit.md` §A5).
- One-step simulation is already what's cheap here; even the "full same-player decision
  chain" resolution this repo's V2 already implements (`search_lookahead_v2.py`,
  chains of 2–9 steps per `search_v2_audit.md` benchmark) stays far under budget.
- A per-branch fresh `agent_ptr` would fully decouple RNG streams at the cost of the
  "no AgentFinish" resident-memory caveat (Part 3) scaling with branch count instead
  of staying flat — only worth it if RNG independence turns out to matter empirically
  for the cards in play.

---

## Part 9 — Smallest viable future simulation architecture (NOT implemented)

```
Current live decision (agent(obs) called by the real match)
    │
    ▼
generate legal actions            (obs.select.option — already provided by engine)
    │
    ▼
cheap tactical filter             (existing heuristic scoring code, e.g. this repo's
    │                              per-deck agents' own attack/option scoring —
    │                              reused as-is, not reimplemented)
    │
    ▼
select top K (5–10)
    │
    ▼
ONE search_begin()                (root clone; ~0.3ms measured; pays the
    │                              deserialize + hidden-zone-fill cost once)
    │
    ▼
for each of the K candidates:
    search_step(root_id, candidate)      (~0.06ms measured; independent clone
    │                                      + action-apply + observe, per candidate)
    ▼
evaluate resulting Observation     (existing/simple evaluation function — see
    │                              search_lookahead.py's `_evaluate` for a minimal
    │                              example already in the repo)
    ▼
search_end()                       (release the root + all K branches back to
    │                              the pool — correct hygiene per Part 3)
    ▼
choose best-scoring candidate
    │
    ▼
battle_select(that candidate)      (applied to the REAL match — completely
                                    separate call from everything above)
```

This is deliberately the same shape this repo already built and benchmarked in
`src/agents/search_lookahead_v2.py` (chain-completion for multi-select attacks) —
scoped narrowly to specific decision types (per `search_v2_audit.md` §A5), not "search
every action." MCTS is not warranted: at sub-millisecond cost for 10 branches, there is
no computational pressure pushing toward tree search or visit-count selection; a flat
1-ply (or short-chain) evaluate-and-pick is sufficient for the budget available.
**Note**: this repo already tried exactly this shape competitively and found it
regressed win rate against the existing heuristic in 6/7 matchups
(`search_v2_audit.md` §"Part A6-A10" — attributed to the evaluation function being
cruder than the heuristics' own hand-tuned logic, not to any engine limitation). This
audit is purely about *engine* feasibility, which is GREEN; whether a *future* attempt
should revisit lookahead at all is a separate, already-negatively-tested modeling
question, not an engine one.

---

## Part 10 — Summary

| Question | Answer |
|---|---|
| Engine architecture | Python holds only an opaque `c_void_p` per native `ApiData`; the live match and the agent's private search sandbox are two separate native objects (`apiDataType` 1 vs 2); state never lives in Python except as disposable JSON→dataclass snapshots. |
| State representation | `State` struct: raw `Game*` (shared) + fixed arrays/unions (Card data, true POD) + 14 `std::vector` members (deep-copied on assignment). |
| ctypes boundary | JSON strings + a `c_void_p` handle; no `ctypes.Structure` mirrors the state; no direct memory access from Python. |
| Existing clone mechanism | Yes — native `Search::alloc` (`*state = src`), invoked by `search_begin`/`search_step`; pooled, reused, real. |
| Is `deepcopy()` safe/valid? | No — deepcopying the Python handle just duplicates the pointer value (same native object); deepcopying an `Observation` snapshot produces an inert, non-resumable copy. The only valid clone path is native, via `search_begin`/`search_step`. |
| Memory leak risk | Empirically measured: negligible (+1.2 MB/60 decisions with correct hygiene; +6.4 MB/60 decisions even with hygiene never observed). No OOM path within a match. |
| Mid-turn (arbitrary decision-point) cloning | Yes — and `search_step` fuses clone+action into one call, so K branches only cost 1 root clone + K step calls, not K full clones. |
| RNG / hidden-state safety | Hidden info: safely masked at the source (`erasePlayerData` before serialization) — no cheating path. RNG: **shared mutable stream** across all clones from one sandbox — branches are not independent for chance-dependent actions; no seed/snapshot API exists to fix this. |
| Benchmark (measured) | Root clone: 0.30ms median / 0.45–1.3ms p95–max. Branch+step: 0.06ms median / 0.1–0.7ms p95–max. |
| 5-simulation cost | ~0.61 ms (median) |
| 10-simulation cost | ~0.93 ms (median) |
| Kaggle time budget | 10 minutes/match total (no documented per-decision limit); ctypes calls count toward it; no documented engine-side timeout fallback (this repo's own agent code adds its own try/except fallback). |
| **Verdict** | **GREEN** — 5–10 forward simulations per decision are comfortably feasible, cost- and memory-wise, several orders of magnitude under budget. |
| Risks / limitations | (1) Shared-RNG non-independence for chance-dependent actions (real, source-confirmed, no engine-level fix available). (2) No `AgentFinish`/destroy for the search sandbox (fine for one persistent `agent_ptr`/process, as already practiced). (3) Simulation quality is bounded by the agent's own hidden-info determinization, not an engine limitation. (4) This repo already tried this exact shallow-lookahead shape and found it competitively regressive with a crude evaluation function — an engine-feasibility GREEN does not imply a strategy win. |
| Smallest viable architecture | Filter → 1 shared `search_begin` → K×`search_step` → evaluate → `search_end` → `battle_select`. No MCTS needed at this cost profile. Already prototyped in `src/agents/search_lookahead_v2.py`. |
