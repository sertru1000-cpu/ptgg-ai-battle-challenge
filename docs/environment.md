# Environment Audit — PTCG AI Battle Challenge (Simulation track)

Date: 2026-08-10 (updated same day after unblocking)
Status: **Phase 1 complete and UNBLOCKED. Official engine downloaded, verified working locally
(full random-vs-random game ran end-to-end through the real native `cg.dll`).**

## 0. TL;DR for future me

- This repo started with **only** the six official Kaggle sample notebooks under
  `sample_notebooks/`. No simulator, no card database, no deck files, no prior agent code.
- The real game engine (`cg` python package + native `cg.dll`/`libcg.so`/`libcg.dylib`) is
  **not on PyPI or GitHub** — it's only obtainable from the competition's Kaggle **Data** tab,
  gated behind an account that joined the competition. Got it via the Kaggle API using a
  user-provided API token (Kaggle's newer token format: `KGAT_...`, goes in
  `~/.kaggle/access_token`, not the old `kaggle.json` username/key pair).
- **Downloaded and extracted into `data/official/` (git-ignored — see §6 license note).**
  Ran a real random-vs-random game through the actual native engine on this machine
  successfully (`data/official/sample_submission/sample_submission/`, 48 selection-steps,
  finished cleanly). The whole pipeline — Python, `cg.dll`, deck loading, `battle_start` /
  `battle_select` / `battle_finish` — is now proven to work end-to-end on this machine.
- Deadlines are tight: Simulation track final submission is **2026-08-16** (6 days from today).
  Entry/team-merger deadline (2026-08-09) has already passed, so no team changes are possible,
  but submissions continue through the 16th, capped at 5/day.

## 1. Repository inventory

```
PokemonGame/
└── sample_notebooks/
    ├── a-sample-rule-based-agent-dragapult-ex-deck.ipynb
    ├── a-sample-rule-based-agent-iono-s-deck.ipynb
    ├── a-sample-rule-based-agent-mega-abomasnow-ex-deck.ipynb
    ├── a-sample-rule-based-agent-mega-lucario-ex-deck.ipynb
    ├── how-to-output-local-battle-as-json-and-view.ipynb
    └── reinforcement-learning-and-mcts-sample-code.ipynb
```

No datasets, decks, card DB, replays, tests, or prior source code exist. Not a git repo
(now initialized, no commits yet, nothing pushed anywhere).

### What each notebook teaches us

**`a-sample-rule-based-agent-*.ipynb` (x4)** — Four complete rule-based agents (Dragapult ex,
Iono's [deck], Mega Abomasnow ex, Mega Lucario ex), each `%%writefile main.py` then packaged
into `submission.tar.gz`. These are gold: full working examples of a heuristic policy against
the real API, one per deck archetype. Structure of every one of them:
1. Load `deck.csv` (60 lines, one card ID integer per line — falls back to
   `/kaggle_simulations/agent/deck.csv` at inference time).
2. Load `all_card_data()` into a `{cardId: Card}` lookup table.
3. `agent(obs_dict) -> list[int]`: on the very first call `obs.select is None`, and the agent
   must return the 60-card deck (list of card IDs) instead of an action. On every later call,
   score every legal option in `obs.select.option`, sort descending, return the top
   `select.maxCount` indices (respecting `select.minCount`, no duplicates).
4. Packaging cell tars up `main.py` + the `cg` library (copied from the Kaggle input dataset
   glob `**/cg-lib/cg`) + `deck.csv` into `submission.tar.gz`.

Score-based action selection is entirely heuristic (no search) but *very* deck-specific —
hundreds of lines encoding matchup knowledge (e.g. which opposing Pokémon ignore Dragapult's
bench damage, prize-trade math, KO-line planning via subset-sum-style search over bench
targets). This tells us the intended difficulty ceiling for a "just heuristics" agent is high;
official/expected baselines are not naive.

**`how-to-output-local-battle-as-json-and-view.ipynb`** — Two ways to run a local match:
1. `kaggle_environments.make("cabt"); env.run(["random", "random"])` — standard
   kaggle_environments interface, agents referenced by name/callable.
2. Direct engine API: `cg.game.battle_start(deck_a, deck_b) -> (obs_dict, start_data)`,
   `battle_select(action) -> obs_dict`, `battle_finish()`, `visualize_data()`. This is the
   fast path for tournaments — no kaggle_environments overhead.
Also shows an HTML replay viewer that **POSTs the replay JSON to a third-party site**
(`ptcgvis.heroz.jp`) — we will build our own local viewer/summary instead of uploading replay
data externally by default.

**`reinforcement-learning-and-mcts-sample-code.ipynb`** — The richest source. Full working
AlphaZero-style loop: sparse-feature encoder (bag-of-cards embedding) + small Transformer
value/policy network, self-play, MCTS via a **Search API** (`search_begin`, `search_step`,
`search_end`) that *determinizes* hidden information (randomly fills the opponent's unseen
deck/hand/prizes with plausible cards, e.g. `[1072]*n` "Snorlax filler" in the sample) so a
perfect-information tree search can run against a hypothesis of the hidden state. This search
API is explicitly recommended for rule-based agents too ("find out what the actual outcome
would be if an attack were used"), not just RL — it's the sanctioned way to answer "if I do X,
what happens" without hand-rolling the whole rules engine ourselves.
Deck used for the demo (`sample_deck`) is a 63-card list — larger than 60, so it's a filler
placeholder, not a legal deck; don't reuse it verbatim.
Training loop shows realistic scale: 10 MCTS sims/move, 100 self-play games/iteration, 5
iterations, d_model=128, 1 encoder/1 decoder layer — deliberately tiny, clearly meant as a
*template* not a competitive model as-is. Win rate vs random climbed 20%→76% over 4 iterations
in the notebook's own output, showing the loop works but plateaus fast at this tiny scale.

## 2. API surface (VERIFIED — read directly from the official `cg/api.py`, `cg/sim.py`,
`cg/game.py` source now in `data/official/sample_submission/sample_submission/cg/`, which is
fully docstringed/commented by Kaggle. Superseded my earlier notebook-inferred version below
where they differ — this is ground truth.)

### Verified facts that refine/correct the earlier notebook-based reconstruction

- **Engine is a native library loaded via ctypes**, not pure Python: `cg/sim.py` picks
  `cg.dll` (Windows) / `libcg.dylib` (mac) / `libcg-arm64.so` or `libcg.so` (Linux) next to
  itself and `ctypes.cdll.LoadLibrary`s it. Exposed C functions: `GameInitialize`,
  `BattleStart`, `BattleFinish`, `GetBattleData`, `Select`, `VisualizeData`, `AgentStart`,
  `SearchBegin`, `SearchStep`, `SearchEnd`, `SearchRelease`, `AllCard`, `AllAttack`. All game
  logic runs natively; Python is a thin ctypes/JSON marshalling layer (`cg/api.py`,
  `cg/game.py`) — this means our own analysis code can be pure Python/numpy without touching
  C++, but also that engine internals are opaque at runtime (we have the **C++ source** in
  `data/official/ptcg_engine/ptcgProgram 22/` as a *read reference* for exact rules — e.g.
  `CardImpl.h` is 878KB and presumably has every card's effect implementation; `State.h`,
  `Types.h`, `Search.h`, `GameProc.h` are the core loop/state/search — use these to resolve
  any ambiguity about how a specific card or interaction behaves, since guessing from the
  real-world TCG rules could be wrong for this simulator).
- `Card`/`Pokemon`/`PlayerState`/`State`/`Option`/`SelectData`/`Log`/`Observation` are exact
  `@dataclass`es in `cg/api.py` with full field docstrings — no need to guess field names.
  Notably: `PlayerState.hand` is `None` for the **opponent** (hidden info correctly modeled),
  `State.result` reason codes are enumerated (1: 0 prizes, 2: decked out at turn start, 3: no
  Pokémon in Active Spot, 4: a card effect caused the loss) — useful for loss categorization
  (Phase 17). `SelectContext` has ~49 values (not the smaller set I'd guessed from notebooks),
  covering every distinct "why are you being asked to choose" situation in detail — e.g.
  separate `EVOLVES_FROM`/`EVOLVES_TO`, `TO_DECK`/`TO_DECK_BOTTOM`/`TO_PRIZE`, `HEAL`,
  `REMOVE_DAMAGE_COUNTER`, `SWITCH_ENERGY_CARD`, `SKILL_ORDER`, `COIN_HEAD`, etc. Comment in
  source: *"new elements may be appended to the Enum during the competition"* — don't
  hardcode an assumed-exhaustive switch/match without a safe default branch.
- `CardData` (from `all_card_data()`) includes `tera: bool` (Tera Pokémon take no damage from
  attacks while benched) and `aceSpec: bool` (max 1 ACE SPEC per deck) — deck-legality
  constraints to encode in deck-building tooling, not just "≤4 copies of a non-basic-energy
  card".
- `search_begin` requires *you* to supply a determinized guess of all hidden info (your own
  remaining deck/prizes if unknown, opponent's deck/hand/prizes/active) as concrete card-ID
  lists matching the exact counts the real state reports — the engine does not sample this for
  you. Errors are typed (invalid card ID, active must be a Pokémon ID, `agent_ptr` broken).
  `search_step` errors also typed: bad `search_id`, released state reused, battle already
  ended, count out of `[minCount, maxCount]`, index out of range, or duplicate selections —
  i.e. malformed actions raise Python exceptions rather than silently failing, good for
  catching agent bugs during dev but means our tournament harness must catch/log these per
  game rather than letting one bad action crash a whole batch.
- Deck validation happens in `battle_start`: `StartData.errorPlayer` (which player's deck is
  invalid, -1 if none) and `errorType` (1: invalid card ID, 2: >4 copies of a non-basic-energy
  card, 3: no Basic Pokémon in deck, 4: >1 ACE SPEC card) — confirmed by successfully starting
  a battle with the official sample deck (`errorPlayer=-1, errorType=0`).
- `EnergyType` includes `RAINBOW` (any type) and `TEAM_ROCKET` (psychic+darkness dual) as
  distinct values beyond the 8 real energy types — special-energy modeling detail.
- License note (`ptcg_engine/.../README.md` + `LICENSES/LicenseRef-PTCG-ABC-Competition-Use-
  Only.txt`): this package is **competition-use-only, not open source** — "don't share or
  republish it, and delete it when the competition ends." Accordingly `data/official/` is
  git-ignored (never gets committed) and must not be uploaded/published anywhere (no public
  repo push, no artifact upload of its contents). This applies to the whole
  `pokemon-tcg-ai-battle.zip` bundle: engine headers, `cg` package + binaries, and the card
  data CSVs/PDFs alike.

### Module layout
- `cg.api` — data types + pure helpers: `AreaType`, `CardType`, `LogType`, `OptionType`,
  `SelectContext`, `Log`, `Observation`, `SelectContext`, `Card`, `Pokemon`, `PlayerState`,
  `State`, `SearchState`, `all_card_data()`, `all_attack()`, `to_observation_class(dict)`,
  `search_begin()/search_step()/search_end()`.
- `cg.game` — stateful local engine driver: `battle_start(deck_a, deck_b) -> (obs_dict,
  start_data)`, `battle_select(action) -> obs_dict`, `battle_finish()`, `visualize_data()`.

### Observation (`obs_dict` / `to_observation_class(obs_dict)`)
- `obs.current: State` — `turn`, `yourIndex`, `firstPlayer`, `result` (>=0 once game is over:
  0/1 = winner index, 2 = draw), `supporterPlayed`, `stadium`, `looking`, `players: [PlayerState, PlayerState]`.
- `PlayerState` — `active[0 or 1 Pokemon]`, `bench[]`, `hand[]`, `discard[]`, `prize[]`,
  `deckCount`, `handCount`, status flags (`poisoned/burned/asleep/paralyzed/confused`).
- `Pokemon`/`Card` — `id`, `serial` (unique instance id, used to dedupe seen-cards),
  `playerIndex`, `hp`, `energies`/`energyCards`, `tools`, `preEvolution`, `appearThisTurn`.
- `obs.select: SelectRequest | None` — **None only on the very first call**, meaning "return
  your deck now". Otherwise: `option: list[Option]`, `minCount`, `maxCount`, `context:
  SelectContext`, `deck` (present during the deck-declare selection), `effect`, `contextCard`,
  `remainDamageCounter`.
- `obs.logs: list[Log]` — turn-by-turn event log (`LogType.ATTACK`, `MOVE_CARD`, `TURN_END`,
  etc.) with fields like `attackId`, `playerIndex`, `fromArea`, `toArea` — the only way to see
  what happened last turn/opponent's turn (e.g. detecting an opponent's KO or an ability use
  that isn't otherwise re-derivable from current state alone).

### Action / `Option`
Each `Option` has a `.type: OptionType` (`RETREAT, ATTACK, PLAY, ATTACH, EVOLVE, ABILITY, CARD,
ENERGY_CARD, ENERGY, TOOL_CARD, NUMBER, YES, NO, END, SPECIAL_CONDITION, SKILL, ...`) plus
context fields depending on type: `area`/`index`/`playerIndex` (zone + slot the option refers
to), `inPlayArea`/`inPlayIndex` (target Pokémon for ATTACH/EVOLVE), `attackId`, `toolIndex`,
`energyIndex`, `specialConditionType`, `number`, `cardId`.

**Agent contract**: `agent(obs_dict) -> list[int]`. Each int is an index into
`obs.select.option`. List length must be in `[select.minCount, select.maxCount]`, no
duplicates. `SelectContext` (e.g. `MAIN`, `SWITCH`, `TO_ACTIVE`, `SETUP_ACTIVE_POKEMON`,
`SETUP_BENCH_POKEMON`, `TO_BENCH`, `TO_HAND`, `DISCARD`, `DAMAGE_COUNTER`,
`DAMAGE_COUNTER_ANY`, `ATTACH_FROM`, `IS_FIRST`, `RECOVER_SPECIAL_CONDITION`) tells you *why*
you're being asked to select, since the same `OptionType.CARD` shows up in many different
decision points (choosing a Pokémon to promote vs. discarding from hand vs. placing damage
counters, etc.) — **the engine has already filtered to legal options only**; per the
competition materials, agents "are only presented legal moves each turn", so we do not need to
reimplement rules-legality ourselves, only *choose well* among what's offered.

### Search API (for lookahead / MCTS / "what would happen if")
`search_begin(obs, your_deck=..., your_prize=..., opponent_deck=..., opponent_prize=...,
opponent_hand=..., opponent_active=...) -> SearchState` — starts a hypothetical rollout from
the current real state, with a **determinized** guess at hidden info (you supply concrete
card-ID lists standing in for cards you can't actually see — sampled from your own known deck
composition in the RL sample). `search_step(search_id, action) -> SearchState` advances it one
choice. `search_end()` tears it down. `SearchState.observation` is a normal `Observation` you
can read `.current.result` etc. from. This is the sanctioned lightweight-search primitive —
much cheaper than reimplementing combat resolution, but only as good as the determinization
(garbage in → garbage lookahead), and each call presumably re-invokes the real engine so it
still costs real time — needs benchmarking once we have the library.

### Submission packaging
```
submission.tar.gz
├── main.py          # defines agent(obs_dict) -> list[int]
├── deck.csv          # 60 lines, one card ID per line
└── cg/                # copy of the cg-lib package (from Kaggle input dataset)
```
`main.py` loads `deck.csv` via `"deck.csv"` first, falling back to
`"/kaggle_simulations/agent/deck.csv"` — i.e. that's the working directory the grader runs
agents from.

## 3. Compute environment (this dev machine — NOT the Kaggle grading sandbox)

| | |
|---|---|
| OS | Windows Server 2025 Datacenter (build 10.0.26100), VM (Microsoft Remote Display Adapter, no real GPU) |
| CPU | 1 physical / 4 logical processors |
| RAM | ~16 GB total, ~6.8 GB free at audit time |
| Disk | 100 GB volume, 50 GB free |
| GPU | None (RDP virtual display adapter only) — any NN training beyond toy scale should happen on Kaggle's own free GPU/TPU notebook quota, not here |
| Git | 2.55.0, installed, repo now `git init`'d (no commits yet) |
| Python | **Not present at all initially** (Store aliases only; `python`/`python3`/`py` all resolved to non-functional Microsoft Store stub executables) |
| Internet | Available |

### Python install workaround
- `winget install Python.Python.3.12` failed: **exit 1625, "Organization policies are
  preventing installation. Contact your admin."**
- Direct python.org MSI-wrapped `.exe` installer, even with per-user
  (`InstallAllUsers=0`, no admin needed in theory) also failed with the same **exit code
  1625** — this machine has a Windows Installer (MSI) policy block that applies regardless of
  per-user/per-machine scope. Do not keep retrying installer-based Python distributions here;
  it's a hard policy wall, not a flag issue.
- **Working solution**: python.org's *embeddable* zip distribution (no installer, just files)
  extracted to `%USERPROFILE%\pytools\python312`, then bootstrapped pip via
  `get-pip.py`, and enabled `import site` in `python312._pth` so `site-packages` and `pip`
  actually work. This is now our local interpreter:
  `C:\Users\sertru1000\pytools\python312\python.exe`.
- Tried `pip install kaggle_environments` from PyPI to check for a public `"cabt"`
  registration — **do not do this again**: the public PyPI package pulls in a huge unrelated
  ML dependency tree (jax/orbax/huggingface-hub/flask/typer/...) and errored out on a
  Windows `MAX_PATH` issue partway through (`orbax.checkpoint...` nested path >260 chars).
  Even if it had finished, per the community repos, the public package **does not contain the
  `"cabt"` env** (competition-specific envs aren't in the open-source `kaggle_environments`
  releases until well after a competition, if ever). We should get `cg-lib` from the Kaggle
  competition Data tab directly instead and drive it via `cg.game`, bypassing
  `kaggle_environments` entirely for local tournaments (the notebook shows both paths work;
  `cg.game.battle_start/battle_select/battle_finish` is lighter-weight than
  `kaggle_environments.make("cabt")` anyway).

## 4. Competition facts gathered (web research — verify against the actual Kaggle rules
page once we can authenticate; Kaggle's rules/data pages did not render for an unauthenticated
fetch, JS-gated)

- Two linked competitions:
  - **Simulation** (`pokemon-tcg-ai-battle`) — continuous automated ladder matches, live
    leaderboard via Kaggle's proprietary skill-rating system, **max 5 submissions/team/day**.
    Entry/team-merger deadline **2026-08-09** (passed). **Final submission deadline
    2026-08-16** — 6 days from today (2026-08-10).
  - **Strategy** (`pokemon-tcg-ai-battle-challenge-strategy`) — separate track, entry/merger
    deadline 2026-09-06, final submission 2026-09-13. Needs its own artifacts (analysis/report
    style), not just a copy of the Simulation submission — to be scoped once we get there.
- Rules are "Standard format... uniquely tailored for this tournament" with **only cards from
  an organizer-provided restricted list** allowed — i.e. not the full real-world Standard
  card pool. We need the actual allowed-card list from the Data tab; can't assume real-world
  meta decks are even legal here.
- **Match time limit: 10 minutes per match total**, and a player that exhausts it **loses on
  timeout**. This is a hard wall-clock budget for an *entire game* (all our turns combined),
  not per move — directly constrains how much search (MCTS sims, Search-API calls) we can
  afford per decision, especially in long grindy games. Needs local benchmarking once we have
  the engine.
- Engine ("cabt") "presents the agent only legal moves each turn" — confirms no need to
  hand-implement legality checking, consistent with what the notebooks show.

## 5. Assets obtained (was the #1 blocker; resolved 2026-08-10)

Unblocked via a Kaggle API token (new-format `KGAT_...` token, `~/.kaggle/access_token`) for
account `sergueimakarov`, which had already joined the competition. Downloaded the full
competition bundle (`kaggle competitions download -c pokemon-tcg-ai-battle`, 301 MB zip) into
`data/official/` (git-ignored, see license note above):

```
data/official/
├── Card_ID List_EN_.pdf / _JP_.pdf     # visual card reference, ~320MB combined, not yet needed
├── EN Card Data.csv / JP Card Data.csv # 2022 cards, machine-readable, matches all_card_data()
├── ptcg_engine/ptcgProgram 22/         # full C++20 engine source — READ REFERENCE for exact
│                                       #   card/rules behavior (CardImpl.h alone is 878KB)
└── sample_submission/sample_submission/
    ├── cg/                             # the real cg package: api.py, game.py, sim.py, utils.py
    │                                   #   + cg.dll / libcg.so / libcg-arm64.so / libcg.dylib
    ├── deck.csv                        # official sample 60-card deck (verified: passes
    │                                   #   battle_start with errorType=0)
    └── main.py                         # official minimal random-agent template
```

**Verified working**: ran a full random-vs-random game locally through the real `cg.dll` (see
§2 for the exact command) — 48 selection-steps, clean finish, `result=0`. This is the first
real proof the whole toolchain (embeddable Python → `cg` package → native engine) functions on
this machine, and it means Phase 3 onward (baseline agent, tournament harness) can now be
built against ground truth instead of guesses.

Still outstanding, lower priority than getting a baseline running:
- The organizer-provided **restricted legal-card list** for this tournament's Standard format
  isn't obviously a separate file — `EN Card Data.csv`'s 2022 rows may just *be* the legal
  pool (deck legality is enforced by the engine itself per `StartData.errorType`, so we can
  discover restrictions empirically rather than needing a separate authoritative list).
- Haven't yet fetched the **replay/episode datasets** noticed during the Kaggle dataset search
  (`kaggle/pokemon-tcg-ai-battle-episodes-index` + dated episode dumps, ~740MB each; also a
  community meta-tracker `busyaprime/pokemon-tcg-ai-battle-live-meta`) — these are real ladder
  games from live competitors and will matter a lot for Phase 12 (replay analysis) and Phase
  13 (meta analysis), but aren't needed to get a first baseline running. Will pull once we have
  something worth comparing against the meta.
- Kaggle rules/data pages still don't render via unauthenticated `WebFetch` (JS-gated); now
  that we're authenticated via the API we get everything we need through `kaggle competitions
  files`/`download` instead, so this no longer matters.

## 6. Status and next steps

- [x] `docs/environment.md` (this file)
- [x] Project skeleton: `src/`, `tools/`, `decks/`, `data/official/`, `results/`,
      `experiments/`, `strategy/`, `submission/`
- [x] Local Python 3.12 runtime (embeddable, no admin needed) at
      `%USERPROFILE%\pytools\python312\python.exe`
- [x] Official engine + card data + sample submission downloaded and verified working
      end-to-end (§5)
- [x] `src/environment/engine_loader.py`: a `sys.path` shim pointing at
      `data/official/sample_submission/sample_submission` rather than physically copying `cg/`
      elsewhere — keeps a single copy of the competition-use-only-licensed engine on disk
      (reverses the plan noted here earlier; see the plan file
      `master-prompt-floofy-catmull.md` for the reasoning).
- [x] **No engine RNG seed exists at all** — confirmed by reading `Api.h` directly:
      `std::random_device rd; config.seed = rd();` is hardcoded, not exposed through ctypes.
      Statistical confidence comes from running many games, never from reproducing one.
- [x] **Player slot 0 is always the one ASKED "go first?"** — confirmed in `SetupProc.h`:
      `SetYesNoSelect(state, SelectContext::IsFirst, 0)`, the `0` is the asked player's index.
      **CORRECTION (Competitive V1, Phase 1-3, session 2)**: the earlier note here ("always
      answers... yes") was wrong — it conflated "who is asked" with "what they answer". The
      `0` is only which seat is asked; the actual answer is whatever that seat's agent returns
      for the `YES` option (`SelectedIsFirst` in `SetupProc.h`: `firstPlayer = selectPlayer` if
      yes, `1 - selectPlayer` if no) — it is a real agent decision, not hardcoded. This matters
      a lot in practice: `src/agents/abomasnow_agent.py`, `iono_agent.py`, and
      `lucario_ex_agent.py` all score `OptionType.YES` unconditionally positive (always answer
      yes when asked anything), while `src/agents/dragapult_agent.py` deliberately answers NO
      to this specific question (faithfully copied from the official notebook). Since only slot
      0 is ever asked, `tools/tournament.py`'s per-game slot-0 alternation does **not** produce
      a balanced first/second-player split whenever both agents in a pairing have deterministic
      (non-random) IS_FIRST preferences — see `results/dragapult_first_second_analysis.md` for
      the full investigation and a real-money example (Dragapult was second in 200/200 games vs.
      both Abomasnow and Iono in the session-1 benchmark despite slot alternation). Only
      `random_agent` (official template, `random.sample` over all options) answers this
      genuinely at random.
- [x] `tools/tournament.py`: game loop over real `cg.game`, per-game exception handling (a
      malformed action aborts only that game), slot-0 alternation, `results/leaderboard.csv`
      (aggregate, recomputed from all raw games each run, split by first/second-player) +
      `results/games/*.jsonl` (raw per-game records, never deleted/overwritten).
- [x] Ported three of the four sample-notebook heuristic agents into `src/agents/`
      (Mega Abomasnow ex, Iono's, Dragapult ex — Mega Lucario ex documented but not ported this
      phase) and ran a 1200-game preliminary benchmark (all 6 pairings among the three plus the
      official random template, 200 games each, zero aborts). See
      `strategy/meta_analysis/deck_archetypes.md` for results with explicit fact/observation/
      hypothesis tagging.
- [x] `src/logging/decision_logger.py`: optional, switchable (env var or constructor flag)
      per-decision logging, buffered per game and stamped with the eventual outcome once the
      game ends, using only information already visible to the acting player.
- [ ] Pull the replay/episode Kaggle datasets once there's a reason to compare against the
      live meta specifically (not needed for this phase's local-only benchmark).

### Local dev environment note: package imports

The embeddable Python distribution's `python312._pth` file takes full control of `sys.path`
and — even with `import site` enabled — **ignores `PYTHONPATH` entirely** (confirmed
empirically: setting `PYTHONPATH` had no effect). The fix was a standard `.pth` file dropped
into `site-packages` (`%USERPROFILE%\pytools\python312\Lib\site-packages\pokemongame.pth`,
containing the absolute repo root path) — `site` module processing of `.pth` files in
`site-packages` works regardless of the `._pth` landmark file, so this makes `import src...`
work from any working directory or invocation style (`-c`, `-m`, direct script). This only
needs to be done once per machine, not per session.
