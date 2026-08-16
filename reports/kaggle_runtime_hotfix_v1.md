# Kaggle Runtime Compatibility Hotfix v1 (Phase 4.7.1)

Date: 2026-08-11. Scope: runtime compatibility only — no strategy, deck, or
policy change. Companion to `reports/final_agent_v1.md` (Phase 4.7).

## 1. Root Cause

Kaggle's real submission validation failed immediately, before any game
logic ran:

```
NameError: name '__file__' is not defined
```

at `/kaggle_simulations/agent/main.py`, on the line:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

Kaggle's `kaggle_environments` agent runner loads a file-path agent by
reading its source as text and executing it via `exec(compiled_source,
namespace)` in a fresh namespace, rather than running it as a real script
(`python main.py`) or loading it via a normal `import`. Both of the latter
always populate `__file__` in the module's namespace — `exec()` on a bare
code object does not, unless the caller explicitly injects a `__file__` key
into the namespace first, which `kaggle_environments` does not do. This is
why the bug was never caught locally: every local test up to this point ran
`main.py` via a real script invocation or a normal `import main`, both of
which silently have a working `__file__` and therefore never exercised the
failure mode.

## 2. Exact Code/Path Issue

Only `main.py`'s own top-level code is affected. Everything `main.py`
subsequently reaches via genuine `import`/`from ... import` statements
(`src.agents.final_candidate_agent`, `src.agents.dragapult_agent_always_first`,
`src.agents.dragapult_agent`, `src.agents.common`,
`src.environment.engine_loader`, `cg.api`, `cg.game`, `cg.sim`) goes through
Python's real import machinery once reached, which always sets `__file__`
correctly on those modules regardless of how the top-level entry point was
invoked — this is a language guarantee, not specific to Kaggle's sandbox.
Grepping the full runtime-critical import chain confirms three files still
contain `__file__` references beyond the fixed line:

| File | Usage | In critical path? | Needs a fix? |
|---|---|---|---|
| `main.py` (old) | `os.path.dirname(os.path.abspath(__file__))` at the top-level, exec'd directly | Yes | **Yes — this was the actual bug** |
| `src/environment/engine_loader.py` | `Path(__file__).resolve().parents[2]` (module-level constant) | Yes, via normal `import` | No (see empirical confirmation below) |
| `src/agents/dragapult_agent.py` | `Path(__file__).resolve().parents[2] / "decks" / "dragapult_ex.csv"` (module-level constant) | Yes, via normal `import` | No |
| `cg/sim.py` | native-library path resolution (official, Kaggle-provided code, not ours to modify) | Yes, via normal `import` | No, and out of scope regardless |

Per this phase's own instruction to prefer eliminating unnecessary
dependencies but not to touch what doesn't need it: these three were left
unchanged and instead **empirically verified** (§4) rather than assumed
safe, since "these are reached via normal imports so they're fine" is a
claim worth testing, not just asserting.

## 3. Fix Applied

`main.py`: replaced the single `__file__`-dependent line with
`_ensure_submission_root_importable()`, a function that never reads
`__file__` and tries, in order, stopping at the first one that actually
makes `src` importable:

1. **No change at all.** The official sample `main.py` does
   `from cg.api import ...` with zero path setup and is known to work on
   Kaggle — the most likely explanation is that `kaggle_environments`
   already puts the submission directory on `sys.path` (or `chdir`s into
   it) before `exec`-ing, in which case `cg` and `src` (both bundled
   alongside `main.py`) are already importable with no help needed.
2. **`os.getcwd()`** — tried only as a fallback and verified with
   `importlib.util.find_spec("src")` before relying on it, per this
   phase's explicit instruction not to assume cwd is the submission root.
3. **`/kaggle_simulations/agent`** — not a guess: this is the exact
   absolute path the live Kaggle error traceback showed `main.py` actually
   running from, and the same path every official sample notebook already
   hardcodes as its `deck.csv` fallback path.

No other file was modified. `src/agents/final_candidate_agent.py`,
`dragapult_agent_always_first.py`, `dragapult_agent.py`, `safety_wrapper.py`,
`timeout_shield.py`, `deck.csv`, and every Phase 4.1–4.7 research artifact
are byte-for-byte unchanged.

## 4. Kaggle-style `exec()` Test Result

`tools/fix_kaggle_runtime_v1.py` reproduces the failure mode faithfully,
addressing two fidelity gaps a naive local test would have:

- **`__file__` absence**: reads the staged `main.py`'s source as text and
  `exec()`s it in a namespace containing only `{"__name__": "__main__"}` —
  no `__file__` key — matching `kaggle_environments`' actual loading model,
  not a real script/import invocation.
- **Dev-machine shortcut leakage**: this dev machine has a global `.pth`
  file that makes `import src` resolve to this repo's own `src/` from any
  process or working directory — a convenience that does not exist on
  Kaggle's sandbox. Left in place, the test could pass for the wrong reason
  (silently falling back to the dev tree instead of the staged, self-
  contained copy). The test strips that exact path entry from `sys.path`
  before running, and additionally asserts that the `src` module which
  actually got imported resolves to the **staged** copy's own path, not the
  dev repo's.

Result:

```
OK: main.py executed via exec() with no __file__ defined, no NameError
OK: agent() and DECK both correctly defined in the exec'd namespace
OK: first observation (select=None) correctly returns the 60-card deck
OK: `src` resolved from the staged copy (...\submission\_staging\src), not the dev repo
OK: self-play game via the exec'd agent completed cleanly, result=0 steps=150
OK: game vs abomasnow_agent via the exec'd agent completed cleanly, result=1 steps=103
KAGGLE EXEC COMPAT TEST: PASS
```

This run also exercises `engine_loader.py`'s and `dragapult_agent.py`'s
`__file__`-dependent module-level constants (both are imported deep inside
the exec'd `main.py`'s own import chain) — their clean pass is direct,
empirical confirmation that those two are safe as-is under Kaggle's
`exec()` model, not just a theoretical argument.

## 5. Local Smoke-Test Result

`tools/run_submission_smoke_test_v1.py` (the pre-existing Phase 4.7 smoke
test, re-run unchanged against the rebuilt staging):

```
OK: agent initialized, deck loaded (60 cards)
OK: first observation (select=None) correctly returns the 60-card deck
OK: self-play validation episode completed cleanly, result=0 steps=157
OK: game vs abomasnow_agent completed cleanly, result=1 steps=57
SMOKE TEST: PASS
```

Additional instrumented run (6 games: 3 self-play + 3 vs. `abomasnow_agent`,
737 total decisions) confirms the safety/timeout counters directly:

```
safety_wrapper stats:  {'calls': 737, 'fallback_used': 0, 'exceptions': 0, 'invalid_returned_by_inner': 0}
timeout_shield stats:  {'calls': 737, 'timeouts': 0, 'inner_exceptions': 0,
                         'cumulative_elapsed_seconds': 0.39, 'degraded_mode_activations': 0}
```

0 invalid actions, 0 timeouts, 0 exceptions, 0 crashes — 0.39 cumulative
seconds of decision time across 737 decisions, far under the 600-second
match budget.

## 6. Archive Structure Verification

Rebuilt via the unchanged `tools/build_submission_v1.py`:
`submission/final_submission.tar.gz` (copied from the freshly-built
timestamped archive, 1.92 MB, 45 members):

```
top-level entries: ['cg', 'deck.csv', 'decks', 'main.py', 'src']
main.py at root: True
nested main.py: []  (no accidental "final_submission/main.py" nesting)
deck.csv at root: True
decks/dragapult_ex.csv present: True
src/ present: True
cg/ present: True
```

## 7. Confirmation: Strategy/Deck/Policy Unchanged

- Deck: `decks/dragapult_ex.csv` — unchanged, re-validated legal
  (`errorType=0`).
- Policy: `src/agents/dragapult_agent_always_first.py` →
  `src/agents/dragapult_agent.py` — unchanged.
- Safety: `src/agents/safety_wrapper.py`, `src/agents/timeout_shield.py` —
  unchanged.
- No RL, Glicko, Jaccard, Bayesian opponent prediction, MCTS, or search code
  was touched or introduced.
- `results/meta/`, `results/agent/` (except this fix's own untouched
  research artifacts), and `reports/final_agent_v1.md` were not modified —
  only this new report and the two `tools/` scripts were added, plus the
  single-function edit to `main.py`.

## 8. Final Recommendation

The archive is Kaggle-runtime-compatible and ready for submission. Recommend
re-uploading `submission/final_submission.tar.gz` as the next submission
attempt.

## FINAL STATUS

Root cause: __file__ incompatibility with Kaggle exec() runtime
Strategy changed: NO
Deck changed: NO
Policy changed: NO

Kaggle-style exec test: PASS
Self-play smoke test: PASS
External-opponent smoke test: PASS
Invalid actions: 0
Timeouts: 0
Crashes: 0

Archive: submission/final_submission.tar.gz
Archive structure: PASS

Kaggle submission ready: YES
