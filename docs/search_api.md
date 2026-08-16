# Search API — Phase 11 reference

Source of truth: `data/official/sample_submission/sample_submission/cg/api.py`
(`search_begin`/`search_step`/`search_end`/`search_release`, `SearchState`,
`ApiResult`) and `cg/game.py` (`_get_battle_data`, where `search_begin_input` is
produced), cross-checked against `sample_notebooks/reinforcement-learning-and-mcts-
sample-code.ipynb` (the only official example that actually calls it). This document
covers the API's mechanics (what it is and how it behaves) established by reading the
source. Runtime/memory cost and "how many steps are practical" are empirical
questions answered in Phase 12 (`docs/search_api.md` will be updated with those
numbers once measured — this section currently only records what's knowable from the
API surface itself).

## 1. What information the Search API receives

`search_begin(agent_observation, your_deck, your_prize, opponent_deck,
opponent_prize, opponent_hand, opponent_active, manual_coin=False) -> SearchState`

- **FACT**: `agent_observation` must be the *live* `Observation` your `agent()`
  function was actually called with this decision — specifically its
  `search_begin_input` field, an opaque ASCII string minted fresh by the engine on
  every `_get_battle_data()` call (`cg/game.py:15`,
  `ctypes.string_at(sd.data, sd.count)`). `search_begin` raises `ValueError("Not
  agent observation.")` if this is `None`. Practically: **search can only be started
  from inside a real `agent(obs_dict)` call handling a genuinely live observation**,
  not from a stored/replayed/reconstructed one (e.g. from a decision log) — the token
  is tied to the live battle's internal state pointer at that instant.
- **FACT**: you must supply your own guess for every zone the search can't already
  see, as concrete `list[int]` card-ID lists whose *lengths* must match the real
  known counts exactly (`len(your_deck) >= players[you].deckCount`, etc. — checked in
  `search_begin`'s Python wrapper before the native call, raising typed `ValueError`s
  on mismatch):
  - `your_deck` — your own remaining deck (composition you actually know; the
    engine already knows your true deck since you provided it, but shuffled order
    is hidden even from you, so you're really guessing an *ordering*/subset, not
    invented card IDs — skipped entirely if `agent_observation.select.deck != None`,
    i.e. during the initial deck-declare exchange).
  - `your_prize` — your own prize cards (also really-known composition, hidden
    ordering only).
  - `opponent_deck`, `opponent_prize`, `opponent_hand` — genuinely hidden from you;
    the engine enforces only that the *counts* match, not plausibility.
  - `opponent_active` — only required if the opponent's Active Pokemon is currently
    face-down/unrevealed to you (`active[0] == None`); must be a real Pokemon card
    ID (`ValueError("Active card must be the ID of a Pokémon card.")` otherwise
    from the native layer, `error==2`).
  - `manual_coin` — if `True`, the search caller can choose coin-flip outcomes
    instead of leaving them to chance; default `False`.
- **FACT**: the engine does **not** sample or validate plausibility of hidden-info
  guesses for you — it is a pure determinization primitive. "Garbage in, garbage
  lookahead" (already flagged in `docs/environment.md`, confirmed again here from
  the source). The sample notebook's own determinization is explicitly a
  placeholder, not a considered strategy: opponent's unseen deck/hand are filled
  with `[1072]*n` (Snorlax) / `[1]*n` (Basic {Grass} Energy) respectively, with an
  inline comment "(There is no deep meaning)". A real Phase-12/13 agent should
  determinize from actual visible information (revealed opponent cards via
  `obs.logs`, legal-deck-construction constraints, discard pile, etc.) rather than
  copy this placeholder verbatim.

## 2. What state it searches

- **FACT**: search runs against a **separate, native-engine-backed hypothetical
  battle state**, distinct from the real one (`Battle.battle_ptr`). It is driven
  through its own `agent_ptr` handle (lazily created once per process:
  `if "agent_ptr" not in globals(): agent_ptr = lib.AgentStart()`) and identified
  per-tree by a `search_id` (`SearchState.searchId`) returned from `search_begin`
  and threaded through subsequent `search_step(search_id, select)` calls. Advancing
  or discarding a search tree never touches or affects the real battle.
- **FACT**: `search_step` requires the *same* selection shape as a real
  `battle_select` — a `list[int]` of chosen option indices — and the returned
  `SearchState.observation` is a normal `Observation` (`.current.result`,
  `.select`, etc., all populated exactly like a live one), so existing heuristic
  scoring code can, in principle, be reused unchanged to decide what to do inside a
  search rollout.

## 3. Does it perform determinization?

**FACT, restated precisely**: no — *you* perform the determinization by supplying
concrete card-ID guesses (§1); the engine's only job is to resolve the hypothetical
game forward deterministically-in-the-sense-of-"replayable-rules" from that fully
specified state. This is a manual/explicit determinization primitive, not an
automatic Information Set MCTS-style sampler.

## 4. Does it respect legal actions?

**FACT**: yes, identically to the live game. `search_step` enforces
`Observation.select.minCount <= len(select) <= select.maxCount` (native error 4 ->
`ValueError`), rejects out-of-range/duplicate indices, and raises typed errors for a
bad `search_id` (error 1), a released search state reused (error 2), or a search
continued after the hypothetical battle already ended (error 3). There is no
separate legality surface to reimplement — the option list you search over is
produced by the same rules engine that produces real `select.option` lists.

## 5. Is search deterministic (same inputs -> same outputs)?

**HYPOTHESIS** (not yet empirically verified — flagged for Phase 12): almost
certainly **no**, for the same reason the live engine isn't: `docs/environment.md`
already established as verified fact (read directly from `Api.h`) that the engine
has **no exposed RNG seed** anywhere (`std::random_device rd; config.seed = rd();`
hardcoded) and `search_begin`'s signature has no seed parameter either. Any chance
element inside a searched rollout (coin flips not covered by `manual_coin`, card
effects with a random component) should therefore vary run-to-run even given
byte-identical determinized inputs. This needs a direct empirical check (call
`search_begin`/`search_step` twice with identical inputs from the same real
decision point and diff the resulting observations) before being treated as settled
— done as part of Phase 12, not asserted here as fact.

**Phase 12 update**: ran a small direct check (identical `search_begin` inputs,
same 3-action sequence replayed twice from the same real mid-game decision point)
and got byte-identical resulting turn/hand-count signatures both times. This is
weak evidence, not confirmation either way -- the specific 3-step rollout tested
didn't obviously hit a coin-flip or random-effect resolution, so it mainly shows
`search_step`'s own bookkeeping is deterministic given identical actions, not that
chance elements inside a rollout necessarily are. Left as an open item rather than
settled fact.

## 6. How many steps are practical / runtime & memory cost

Not answered by reading the source — the Python wrapper does no batching or
internal looping (each `search_step` is one native call, `ctypes`-marshalled
through JSON like every other API call), so cost scales with however many
`search_step` calls you make and however expensive each underlying rules
resolution is. `docs/environment.md` already flagged this as unbenchmarked
("presumably re-invokes the real engine so it still costs real time"). The sample
notebook's own config (`SEARCH_COUNT = 10` MCTS simulations/move, 5 training
iterations × 100 self-play games, tiny `d_model=128` value/policy net) is
explicitly a *template scale*, not a tuned or competitive setting, and is a
neural-MCTS loop rather than a bare heuristic-plus-lookahead usage, so it doesn't
transfer directly to "how many search_step calls can a heuristic agent afford per
decision within the 10-minute/match wall-clock budget." **Measured directly in
Phase 12** (`results/search_1ply_experiment/` once run) rather than assumed here.

**Phase 12 measurement**: a 1-ply attack-comparison search (`src/agents/
search_lookahead.py` -- one shared `search_begin` per real decision, then one
`search_step` per candidate attack, 2-4 calls typically) added no perceptible
wall-clock overhead in a 20-game timed batch (~0.1s/game total including all
non-search decisions; ~90 `search_step` calls across those 20 games). This is
several orders of magnitude below the 10-minute/match budget even generously
attributing all of that time to search. Not a rigorous microbenchmark (game time
and search time aren't isolated from each other here), but sufficient to establish
that a handful of `search_step` calls per decision, restricted to genuinely
high-impact decisions (not every single select), is clearly affordable.

## 7. How the final action is extracted (usage pattern)

**FACT**, read directly out of the sample notebook's `mcts_agent()`:

```
current real decision point (root)
    │
    ├─ search_begin(obs, ...determinized hidden info...)  -> fresh, separate search tree
    │
    ├─ repeatedly: search_step(search_id, candidate_action) -> hypothetical outcome
    │        (root's *direct children* are exactly the real legal options at the
    │         current decision; search explores forward from each)
    │
    ├─ pick the best root-level child by whatever evaluation criterion
    │        (MCTS notebook: most-visited child; a plain heuristic-lookahead agent
    │         could instead just compare final/near-term game state score per
    │         candidate first move)
    │
    ├─ search_end()   -- tears down ALL search state for this agent_ptr
    │
    └─ battle_select(that root-level action)   -- applied to the REAL battle,
             completely separately from the search calls above
```

Search never commits anything to the real battle itself — it is purely advisory.
The pattern is always "spin up a disposable hypothetical tree rooted at the real
current decision, evaluate candidate first moves by rolling them forward, throw the
tree away, then make the real move normally via `battle_select`." `search_end()`
frees the whole current search context ("memory used during the search will be
reused in the next search" — an allocator-reuse hint, not a correctness
requirement); `search_release(search_id)` frees a single search-tree node without
ending the broader context, for finer-grained memory management inside deeper
trees.

## 8. Open items carried into Phase 12/13

- Empirically confirm/refute §5 (determinism) with a direct twice-repeated call.
- Measure `search_step` latency (ms/call) and memory growth vs. tree size, and
  therefore how many calls are affordable inside the 10-minute/match wall-clock
  budget (`docs/environment.md` §4) without risking a timeout loss.
- Decide a non-placeholder determinization strategy for opponent hidden info
  (§1) before using search in real matches — copying the notebook's constant-fill
  placeholder into a competitive agent would likely bias searched outcomes.
- Confirm whether repeated `search_begin`/`search_step` calls across many real
  decisions in the same game leak memory if `search_release`/`search_end` are not
  called precisely (the notebook always calls `search_end()` once per real decision,
  after extracting the chosen action, and never calls `search_release` — establish
  whether that's sufficient hygiene or whether unreleased individual nodes
  accumulate across a full game).
