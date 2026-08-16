# V17 -- C++ MCTS Edition

Native Monte Carlo Tree Search implemented in C++ against the competition
engine's native `SearchBegin`/`SearchStep`/`SearchEnd` C ABI, using V6's own
scoring math (ported line-for-line) as both the rollout default policy and
the leaf/backup evaluation function. See `main_v17.py` (repo root) for the
Kaggle entry point.

**Status: compiled and execution-tested on Windows (MSVC); the Linux/g++
path (Kaggle's actual target) is still unverified.** This dev machine
initially had no C++ compiler at all; the user then installed Visual Studio
Build Tools mid-session, which made real compilation and testing possible.
Using it surfaced and fixed four real bugs that pure code review had missed
-- see "What compiling and testing actually found" below. After those fixes,
~10 full games played live against the real `cg.dll` (via `cg.game`,
`src/agents/dragapult_policy_v6.py` as the pure-Python cross-check) came back
clean: zero crashes, zero native errors, zero scoring divergence from the
Python reference beyond one deliberate, expected difference (see below).
MCTS is confirmed actually engaging: in a majority of eligible decisions
across these runs it picked something other than V6's own plain-greedy
choice. **What is still NOT verified**: this machine has MSVC, not g++/Linux
-- the code has never been compiled with g++, and Kaggle's actual grading
container (the real deployment target) has not been confirmed to have a C++
compiler at all. `native_bridge.py`'s compiler selection tries MSVC first on
Windows and g++ everywhere else (see "Compiled on the machine that runs it"
below), but only the MSVC branch has actually been exercised.

### What compiling and testing actually found

Four real, non-cosmetic bugs, found only once a compiler and a live-engine
test harness were available -- listed because the fact that hand review
missed all four is itself informative about how much to trust hand review
alone on the rest of this codebase:

1. **Double `GameInitialize()` call crashed the DLL** ("buffer full,
   capacity:7"). `Engine`'s constructor called it unconditionally, not
   realizing `native_bridge.py`'s own `import cg` (which always runs first)
   already triggers Python's `cg` package to call it once on the same loaded
   module image. Fixed by never calling it from C++ at all (documented in
   `cg_engine.hpp`).
2. **Null-pointer read inside the native `SearchBegin` call** when
   `myPrizeGuess` was shorter than the real prize count -- `std::vector::
   data()` on a too-short/empty vector can be `nullptr`, and the engine's own
   `CopyIdPtr` dereferences it unconditionally for a nonzero count. Fixed by
   defensively padding `my_prize` to the required length in `mcts.hpp`,
   mirroring the padding `expand_deck()` already did for `my_deck`.
3. **`AreaType.DECK`/`PRIZE`/`LOOKING` were unhandled** in `get_card_ref()` --
   only HAND/DISCARD were resolved, so any option referencing a card visible
   via a deck-search effect, a revealed prize, or a "looking" zone silently
   scored 0, collapsing `select_top`'s stable sort to "always pick index 0."
   Fixed by adding `selectDeck`/`myPrizeCards`/`looking` to the ABI struct,
   `Observation`, and `get_card_ref` (with an `id==0` sentinel for a face-down
   prize/looking slot, positions never compacted).
4. **`Observation::deckCounts` was declared, flattened by Python, sent over
   the wire, and then silently never read into the C++ struct** -- `from_ctypes()`
   was simply missing the loop that copies `deckIds`/`deckCounts` out of the
   ctypes struct. Every root-decision `hand_score()` call that depends on
   deck composition (Buddy Buddy Poffin, Crispin, Ultra Ball, Poke Pad) saw
   an always-empty deck as a result. This was the dominant remaining cause
   of the scoring mismatches bug #3's fix didn't fully resolve.

None of these were found by static reading -- all four were isolated by
adding temporary `fprintf`/`fflush` tracing, bisecting against the exact
line where output stopped, then removed once fixed (not by guessing).

The one **expected, non-bug** divergence from the pure-Python reference:
answering the one-time "go first?" question. V6's raw (un-wrapped) per-option
scorer actually prefers NO by default (`score = -1 if context == IS_FIRST
else 1`, and NO falls through to the default `score = 0` which beats it) --
it's the `with_always_first` wrapper that overrides this to always answer
YES. `agent.py` replicates that same interception in Python *before* ever
calling into C++ (see `agent.py`), so the native scorer's own raw IS_FIRST
behavior is never actually used in the real decision path; the test harness
calls the native path directly for comparison purposes and correctly shows
this one intentional difference every game.

## Why this shape (read this before changing anything)

This design was worked out with the user across several corrections mid-task
-- the reasoning survived because it answers real constraints, not because
it's the first thing that was tried:

1. **The forward model.** The engine ships only as a precompiled
   `cg.dll`/`libcg.so`/`libcg.dylib` with a public `extern "C"` export table
   (`data/official/ptcg_engine/.../Export.cpp`). `cg_engine.hpp` `dlopen`s
   that SAME binary directly from C++ and calls `SearchBegin`/`SearchStep`/
   `SearchEnd` as raw function pointers -- no ctypes, no Python, no
   `PyObject` anywhere in that call. The actual state-cloning and
   rules-application happens *inside* the DLL's own native code
   (`Search::alloc`+`State::step()`, confirmed by source trace in
   `ENGINE_CLONE_LOOKAHEAD_AUDIT.md` Part 2A). This project deliberately does
   **not** recompile the engine's own source (available under
   `data/official/ptcg_engine/`) into a new binary: that source is licensed
   "competition-use-only... don't share or republish it," and bundling a
   self-compiled derivative into a submission is a redistribution question
   this task has no authority to resolve unilaterally. Calling the
   already-shipped compiled artifact through its public C ABI is the same
   sanctioned client/library boundary the official Python `cg` package
   already uses, just from C++.

2. **Only ONE Python↔C++ boundary crossing per real decision.**
   `main_v17.py` → `agent.py` → `native_bridge.native_choose_action()` makes
   exactly one `ctypes` call into `v17_choose_action`. Everything inside that
   call -- potentially hundreds of simulated `SearchStep` branches -- runs
   entirely in C++ against the native engine. This is what actually
   eliminates the Python-marshalling overhead the pure-Python search
   wrappers pay per branch (`ENGINE_CLONE_LOOKAHEAD_AUDIT.md` measured that
   overhead at ~65% of `search_step`'s cost) -- not the raw engine call
   itself, which was already cheap.

3. **JSON parsing exists in exactly one place, for one reason.** The
   engine's `SearchStep` replies are JSON strings (there is no binary struct
   ABI -- not this project's choice, a constraint of the shipped DLL), and
   those replies are read *inside* the C++ MCTS loop, where Python is never
   present to parse them instead. `json_extract.hpp` is a narrow,
   `std::string_view`-based, single-pass field extractor for exactly that --
   not a general JSON library, no heap value-tree, no `shared_ptr`. The
   ROOT observation (the one real decision Python already has as parsed
   dicts) never goes through this parser at all: `v17_abi.h` +
   `native_bridge.py`'s `ctypes.Structure` mirror flatten it directly into
   primitive arrays, exactly as requested.

4. **Compiled on the machine that runs it, not shipped prebuilt.** Kaggle's
   grading container's OS/libc/compiler are unverified from here, and no
   binary built on this dev machine (Windows) would even be the right target
   platform (Linux) anyway. `native_bridge.py`'s `_ensure_native_library_built()`
   picks a compiler by `os.name`: MSVC (`cl.exe`, via `vcvars64.bat`) first on
   Windows, falling back to g++ if MSVC isn't found; g++ directly everywhere
   else (Linux -- Kaggle's actual target). This runs **once, eagerly, at
   module import time** -- not lazily on the first real decision. That
   eagerness matters: `final_candidate_agent_v17.py` wraps every decision in
   `timeout_shield` (2.0s/decision on a single-worker thread pool); if
   compilation (which can take real seconds) landed on the first decision
   instead, it would blow that budget AND leave the single worker busy
   finishing the abandoned compile in the background, silently degrading
   every queued decision behind it to the crude legal-only fallback until it
   finished. Running the build at import time avoids that failure mode
   entirely. **The g++/Linux path -- what Kaggle will actually run --
   is still unverified**; only the MSVC path has been exercised (this dev
   machine got Visual Studio Build Tools installed mid-session, not g++). If
   no compiler is found or compilation fails, `_ensure_native_library_built()`
   returns `None`, `get_native_lib()` caches that, and the whole match runs
   on the pure-Python V6 fallback instead (see `agent.py`) -- degraded but
   never broken.

## Scope of the MCTS itself

The tree has exactly one branching level: the real legal options at the
CURRENT decision (only when `context == MAIN`, `maxCount == 1`, and there
are ≥2 options -- the same gating condition
`src/agents/dragapult_policy_v11.py`'s own macro-lookahead uses). UCB1
allocates simulation budget across the top-6 candidates by V6's own raw
score (same `MACRO_LOOKAHEAD_TOP_N` shape as V11). Each simulation steps one
candidate, then rolls out (both sides, driven by a disposable copy of V6's
own greedy scorer -- an explicit self-model-opponent simplification, the
same one this project's self-play tournament harness already relies on) for
up to 60 further decisions or until the game/turn genuinely concludes, then
backs up V11's own `post_action_state_value` from the ROOT player's
perspective.

This is a real upgrade over V11's macro-lookahead (many rollouts per
candidate with proper mean-value statistics via UCB1, instead of one
single-sample rollout per candidate), not just a language port of it. It is
**not** a full adversarial/information-set game tree (opponent decisions
inside a rollout are not their own tree nodes) -- going further would need
per-node hidden-information bookkeeping this task's timeframe doesn't
support, and per `ENGINE_CLONE_LOOKAHEAD_AUDIT.md`'s own benchmark (~0.06ms
per simulated branch), rollout *depth* is where the affordable budget
actually goes, not tree *breadth*.

## Accepted approximations (documented, not hidden)

- **RNG is shared across all simulated branches** inside one `AgentStart`
  sandbox (source-confirmed, `ENGINE_CLONE_LOOKAHEAD_AUDIT.md` Part 5, no
  engine-level fix exists). Chance-dependent cards make branch comparisons
  noisier, not incorrect in expectation over many UCB1 samples.
- **Opponent hidden-info determinization is a placeholder** (`mcts.hpp`:
  fills unknown opponent cards with a fixed filler id), matching the
  official sample notebook's own "no deep meaning" placeholder
  (`docs/search_api.md` §1). Improving this is out of this task's scope
  (Objective 2 asks for the search architecture + V6 evaluation, not a new
  opponent model).
- **`preKo`/`noItem`/`myPrizeGuess` are snapshotted at the root and carried
  forward unchanged through an entire rollout**, not re-derived per
  simulated turn (`observation.hpp`). Re-deriving them natively would need
  porting V6's full log-scanning turn-boundary state machine into the
  rollout driver for a marginal scoring effect deep in hypothetical futures.
- **`deckCounts` recomputed during rollout doesn't subtract `select.effect`**
  (a card mid-resolution, sometimes not yet reflected in any zone listing)
  -- `deck_tracking.hpp` documents this as an accepted off-by-one, affecting
  only a couple of minor `hand_score` terms deep in rollout branches, never
  the root decision (the root's `deckCounts` comes from Python, which does
  handle this correctly via the real `DragapultPolicy.add_card_count` port
  in `native_bridge.py`).

## How to actually build and test this

Done so far, on Windows with MSVC (this session, once VS Build Tools became
available): compiles clean at `/W3` with zero warnings; loaded via
`native_bridge.get_native_lib()` (the real code path, not a manual
workaround); ~10 full games played live against the real `cg.dll`
(`cg.game.battle_start`/`battle_select`), native playing one side and
`src/agents/dragapult_policy_v6.py` cross-checking every decision -- zero
crashes, zero native errors, zero scoring divergence beyond the one expected
IS_FIRST difference (see above), MCTS confirmed picking a different-from-
greedy move in a majority of eligible decisions. Four real bugs found this
way are fixed (see "What compiling and testing actually found" above).

**Still needed before this is genuinely submission-ready:**

1. **Compile with g++ on Linux** -- never done. `compile.sh` and
   `native_bridge.py`'s g++ command line are believed correct (standard
   C++17, no MSVC-specific constructs) but unverified; expect at least minor
   portability issues (e.g. `#pragma pack` behaves identically across GCC/
   Clang/MSVC for this struct shape, but hasn't been checked empirically).
2. **Confirm `g++` is actually available in Kaggle's grading container**
   (e.g. a throwaway Kaggle notebook cell) before relying on the
   compile-on-import step for a real submission -- if it isn't, V17 will
   silently run as pure-Python V6 for the whole match, which is safe but
   defeats the point.
3. **Run under a sanitizer** (`-fsanitize=address,undefined`, g++/clang only
   -- MSVC's equivalent is `/fsanitize=address`) for at least a short local
   match before fully trusting the "no memory leaks" requirement. The known
   risk points (raw-pointer-into-transient-DLL-buffer lifetimes in
   `cg_engine.hpp`, the `V17RootObservationC` struct-layout contract, RAII
   around `search_end()` in `mcts.hpp`) were reviewed by hand and survived
   ~10 real games with no observed corruption, but that is not the same
   guarantee a sanitizer run gives.
4. **Wider game-count validation** -- ~10 games is enough to have found and
   fixed four real bugs and to give reasonable confidence in the common
   paths, not enough to rule out a rare edge case (a specific card
   interaction, an unusual board state) that a much larger sample (matching
   this project's own standing statistical-rigor bar, see
   `feedback_ptcg_process.md`) would be needed to be confident about before
   treating this as ladder-ready.

## Directory layout

```
dragapult_agent_v17_cpp/
├── cpp/
│   ├── json_extract.hpp      narrow SearchStep-reply JSON extractor
│   ├── v17_abi.h             ctypes<->C++ root-observation struct contract
│   ├── cg_engine.hpp         dlopen/dlsym binding to cg.dll/libcg.so
│   ├── observation.hpp       internal Observation type + two constructors
│   ├── card_data.hpp         AllCard()/AllAttack() static tables
│   ├── v6_heuristic.hpp      V6Scorer: declarations + small methods
│   ├── v6_heuristic_scores.hpp   V6Scorer::raw_scores/select_top (the big port)
│   ├── deck_tracking.hpp     rollout-node deck_counts recompute
│   ├── mcts.hpp              UCB1 selection/expansion/rollout/backprop
│   └── v17_agent.cpp         the only .cpp -- extern "C" v17_init/v17_choose_action
├── compile.sh                 reference build (main_v17.py compiles this itself)
├── CMakeLists.txt             secondary/documentation build path
├── native_bridge.py            ctypes structs, JIT compile, V6 bookkeeping port, flattening
├── agent.py                    routes each decision to native or pure-Python V6
└── README.md                   this file
```

See also: `src/agents/dragapult_agent_v17.py` (thin binding),
`src/agents/final_candidate_agent_v17.py` (safety_wrapper + timeout_shield
composition), `main_v17.py` (repo root, Kaggle entry point).
