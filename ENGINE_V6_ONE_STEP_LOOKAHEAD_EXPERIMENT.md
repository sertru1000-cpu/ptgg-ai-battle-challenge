# V6 One-Step Engine-Backed Lookahead: Research Prototype & Report

**Scope**: an isolated research prototype and evaluation, per the governing
research prompt. Nothing in `main.py`, `main_v6.py`, `main_v10.py`,
`decks/dragapult_ex.csv`, or `src/agents/policy_weights.py` was modified.
No MCTS, minimax, multi-turn search, or Value Model was built. No V11 was
created. Nothing was submitted to Kaggle. Two new files were added:
`experiments/v6_one_step_lookahead.py` (the prototype library) and
`tools/v6_lookahead_experiment_runner.py` (the local-only runner that
produced the data in this report). Raw per-decision data is preserved at
`results/v6_lookahead_experiment/*_decisions.csv` (970 rows) and
`*_games.csv`/`*_meta.json` — nothing was discarded after aggregation.

**Claim tagging** (per this project's standing process rule): every
quantitative claim below is a **[MEASURED]** result from the one run
described in this report (24 local self-play games, 970 in-scope
decisions), a **[FACT]** verified directly against engine/card-data source,
a **[HYPOTHESIS]** flagged explicitly as unconfirmed, or a **[FUTURE
QUESTION]**. This is a single preliminary run — see the Verdict section for
why it is not treated as statistically conclusive.

---

## Executive Summary

**The research question**: *"Can one-step engine-backed lookahead improve
the decisions of our proven V6 greedy agent without requiring a new
heuristic?"*

**[MEASURED]** Across 970 real in-scope decisions (24 local self-play games,
V6 vs. `lucario_ex_agent`, real `cg.dll` engine, V6's own unmodified
greedy choice always driving the actual game trajectory):

- At the primary configuration (N=5 candidates), V6 and V6+lookahead
  **disagreed on 116/970 decisions (12.0%)**.
- Of those 116, only **68 (7.0% of all decisions)** are "clean" — both the
  real V6 choice and the lookahead's choice were RNG-independent
  (`DETERMINISTIC`) and did not touch the win/loss terminal-value override.
  These 68 are the trustworthy evidence base for "does lookahead find a
  genuinely different tactical assessment."
- **28 (2.9%)** of the 116 disagreements are contaminated by this deck's one
  real RNG-sharing risk (Crushing Hammer's coin flip, or a deck-shuffling
  trainer) and are reported as **UNCERTAIN**, not silently treated as clean.
- **14 (1.4%)** are a distinct, important, and largely reassuring artifact:
  the lookahead detected a simulated **win** (terminal +1,000,000 value) on
  an early sub-decision of a turn where V6's real, different sequence of
  actions **also went on to win the same real game** (mechanically verified
  against this run's own recorded game outcomes, not assumed) — a 1-ply
  horizon blind spot ("this alternative also wins, just one step later"),
  not evidence of a missed win. Classified **EQUIVALENT**.
- Latency is fine: **[MEASURED]** median/p95/max total decision latency at
  N=5 is 32.6 / 77.9 / 236.7 ms — several orders of magnitude under the
  documented 10-minute whole-match Kaggle budget, even summed across every
  decision in a full match. No crashes across 2,910 evaluate calls; memory
  growth is +14.8 MB over the whole 24-game run (no leak risk).
- **We do not have outcome (win-rate) evidence that acting on the
  lookahead's choice would actually improve results** — this experiment
  deliberately never let the lookahead's choice steer a real game (shadow
  mode only, to keep V6's own validated trajectory uncontaminated and to
  avoid fabricating a win-rate claim from a decision-agreement metric, per
  this project's explicit "do not convert counterfactual decisions into
  fake win-rate improvements" instruction).

**Verdict: D — INSUFFICIENT DATA.** See the Verdict section for the full
reasoning. In short: the engine mechanism and prototype work correctly, and
there is a real, non-trivial, RNG-independent disagreement signal (7% of
decisions) worth investigating further, but this experiment's design
(shadow-mode only) cannot answer whether acting on it helps — that requires
a follow-up where the lookahead's choice actually drives some real games.

---

## Part 1 — V6 Production Decision Path

**[FACT]**, traced directly (not inferred) from
`src/agents/dragapult_policy_v6.py`, `src/agents/dragapult_agent_v6.py`,
`src/agents/final_candidate_agent_v6.py`, `main_v6.py`.

**Chain**: `main_v6.py:agent()` → `final_candidate_agent_v6.agent` (wraps
`safety_wrapper` + `timeout_shield`) → `dragapult_agent_v6.agent` (built by
`dragapult_policy_v6.make_agent(BALANCED, adaptive=False, always_first=True)`)
→ `DragapultPolicy.agent(obs_dict)` (`dragapult_policy_v6.py:431`).

- **Candidate enumeration**: the engine itself provides `obs.select.option`
  (a list of `cg.api.Option` records with `.type`, `.area`, `.index`,
  `.attackId`, `.cardId`, etc.) every decision; V6 does not generate
  candidates itself, it only iterates them.
- **Scoring**: one inline pass in `DragapultPolicy.agent()`
  (`dragapult_policy_v6.py:749-919`), a big `if/elif` over `o.type`
  (`NUMBER/YES/CARD/ENERGY_CARD/PLAY/ATTACH/EVOLVE/ABILITY/RETREAT/ATTACK`),
  producing one `scores: list[float]` aligned to `select.option`. Key
  helpers it calls: `pokemon_score()` (per-Pokemon tactical value —
  prize-on-KO, energy count, tool count, evolution stage, raw HP),
  `main_option_proc()` (a bitmask/backtracking subset-sum planner deciding
  which bench Pokemon Phantom Dive's 6 damage counters should target, run
  once per real `MAIN` decision), `hand_score()`/`attach_score()` (per-card
  trainer/attach scoring closures).
- **Selection**: `select_top()` (`src/agents/common.py:74-97`) — plain
  argmax over `select.maxCount` slots via a stable sort (Python's
  `sorted()`), so exact-score ties resolve to the lowest original option
  index deterministically. **[FACT]** no `random.*` call exists anywhere in
  `dragapult_policy_v6.py`/`common.py` — V6's own decision-making is 100%
  deterministic given a fixed observation.
- **Phantom Dive target selection is a two-stage mechanism, not one scored
  option**: (1) the `MAIN`-context `ATTACK` option itself is scored
  trivially as `score = o.attackId` (`dragapult_policy_v6.py:916-917`) —
  i.e. V6's own raw "should I attack" score barely encodes any tactical
  judgment (see Part 10 for why this matters a great deal for the
  lookahead comparison); the REAL targeting intelligence lives in
  `main_option_proc`'s subset-sum combo search, computed once per `MAIN`
  decision and stashed in `self.plan_b`. (2) the actual bench-damage-counter
  placement happens in up to 6 *separate*, subsequent
  `SelectContext.DAMAGE_COUNTER_ANY` decisions, each scored by looking up
  whether that bench slot is in `self.plan_b.counter`
  (`dragapult_policy_v6.py:814-816`, `+100000` if so).
- **This project's own V6 fixes** (relative to `dragapult_policy_v2plus.py`):
  a backwards `score -= 100000` → `score += 40000` fix for a
  one-counter-kills-it target, and a fix preventing Phantom Dive's generic
  `damage=200` constant from being wrongly applied to the opponent's Active
  (Phantom Dive never touches the Active — only bench). Neither touched by
  this prototype.

**Do-not-touch boundary** (verified, not the same files as V6/V10's own
chains): the actual live Kaggle submission is `main.py` (root) →
`final_candidate_agent.py` → `dragapult_agent_always_first.py` →
`dragapult_agent.py` (+ `safety_wrapper.py`/`timeout_shield.py`) — this is
V1 ("dragapult_fix_v1"/"BEST_DRAGAPULT_AGENT"), confirmed byte-identical to
`submission/_staging/main.py`. V6's and V10's own chains are themselves
already-isolated, never-submitted research forks; this prototype reads from
V6's chain (imports only, see Part 2) and never touches any of the four
files above.

---

## Part 2 — Clone/Simulation Architecture

Reused, unmodified, from the already-audited
`ENGINE_CLONE_LOOKAHEAD_AUDIT.md` (GREEN verdict) and
`src/agents/search_lookahead_v2.py` (already-audited Search V2
infrastructure) — **[FACT]**, this prototype imports
`_begin_shared_search` and `_resolve_full_chain` from
`search_lookahead_v2.py` directly rather than reimplementing them, per the
governing research prompt's explicit instruction to use "the existing
proven infrastructure."

```
capture V6's real per-candidate scores (score capture, Part 3 below)
    |
    v
rank candidates by V6's own score; take top N
    |
    v
ONE search_begin()   (shared root clone; one determinization per REAL
    |                  decision, reused for every candidate)
    v
for each of the N candidates:
    search_step(root, candidate)      (candidate's own action)
    + _resolve_full_chain(...)         (same-player follow-up selects --
                                         e.g. Phantom Dive's own damage-
                                         counter placements -- driven by a
                                         DISPOSABLE deep-copied policy
                                         instance, see below)
    -> post_action_state_value(resulting obs)   (Part 3)
    lookahead_score = v6_current_action_score + post_action_state_value
    |
    v
search_end()
    |
    v
argmax(lookahead_score) across the N candidates == V6_LOOKAHEAD's pick
```

**One deliberate architectural improvement over `search_lookahead_v2.py`**:
V2's `make_search_v2_agent` reuses the SAME live policy instance (and
therefore the same `.policy` object whose cross-call state — `self.prize`,
`self.pre_turn_log`/`self.current_turn_log`, `self.plan_a`/`self.plan_b` —
is trusted to reflect real game history) to drive hypothetical chain
resolution. Tracing `DragapultPolicy.agent()`'s top: it unconditionally
appends `obs.logs` into `self.current_turn_log`/`self.pre_turn_log` every
call (`dragapult_policy_v6.py:448-452`), including on a **hypothetical**
hand-off observation — meaning V2's own pattern **[HYPOTHESIS, not proven
here]** risks bleeding hypothetical-branch log entries into the state a
subsequent REAL decision reads for `pre_ko`/`no_item` logic. This
prototype avoids the risk entirely: each candidate's chain resolution is
driven by `copy.deepcopy(policy)` (a **fresh, disposable** shadow instance
per candidate), never the live instance. This is valid and cheap —
`DragapultPolicy` holds zero ctypes/native handles (only plain Python
ints/lists/dicts/sets), so `deepcopy` on it is NOT the same "deepcopy is
invalid" case `ENGINE_CLONE_LOOKAHEAD_AUDIT.md` found for the ctypes
`c_void_p` engine handle — that finding was about the engine boundary, not
about this pure-Python policy object.

**Score capture mechanism** (how "the same V6 score for every candidate"
was obtained without duplicating/forking V6's scoring code):
`capture_v6_scores()` temporarily replaces the ONE module-level attribute
`dragapult_policy_v6.select_top` (not `src.agents.common.select_top`
itself, and not any file) with a thin wrapper that records the `scores`
list `DragapultPolicy.agent()` computes internally but never returns, then
delegates unchanged to the real `select_top`, then restores the original
attribute in a `finally` block — a single-call, always-restored, read-only
runtime swap. `main.py`'s chain never imports `dragapult_policy_v6` at all,
so this technique is unreachable from the live submission regardless.

---

## Part 3 — State Evaluation Method (and the turn-boundary problem)

**The turn-boundary hazard is real** in this engine: once a simulated
action ends our turn, `state.yourIndex` flips to the opponent, and every
other V6 scoring routine (`main_option_proc`, the inline `scores[]` loop,
`hand_score`, `attach_score`) is a function of `(obs, select, context)` —
"given THESE legal options, which is best" — so calling any of them on a
post-hand-off `Observation` would silently score the wrong player's
options. There is no "evaluate this board from my perspective regardless of
whose turn it is" entry point anywhere in `dragapult_policy_v6.py`.

**One exception exists and is safe**: `pokemon_score(pokemon,
is_attack_damage, weights)` (`dragapult_policy_v6.py:140-162`) is a pure
function of a single `Pokemon` object (HP, energy count, tool count,
evolution stage, card id) and the policy's own `weights` — it never reads
`select`/`context`/`state.yourIndex`. It is safe to call on either side's
board, in either player's post-action position.

Per the research prompt's explicit instruction ("if the existing V6 scoring
system cannot safely evaluate a simulated state directly, STOP and report
the limitation rather than inventing a new heuristic"), this prototype's
`post_action_state_value(obs, my_index, weights)` is built **entirely** from
existing numbers V6 already assigns elsewhere, with the combination itself
being the one new piece of glue code:

```
post_action_state_value =
      Σ pokemon_score(p, False, weights) over MY Active+Bench   [V6's own function, unmodified]
    − Σ pokemon_score(p, False, weights) over OPPONENT's Active+Bench
    + (opp.prize_remaining − my.prize_remaining) × 1000 × weights.prize_value_multiplier
                                                          [V6's own existing prize_diff
                                                           variable + V6's own existing
                                                           pokemon_score() prize scale]
    (terminal states: ±1,000,000 / 0, reused verbatim from
     search_lookahead_v2._evaluate, the only prior lookahead code in this repo)
```

`lookahead_score(candidate) = v6_current_action_score(candidate) +
post_action_state_value(resulting state)` — exactly the structure the
research prompt suggested. **This is explicitly NOT presented as "V6's own
evaluator"** — V6 has no such thing. It is a designed judgment call
(documented in the module docstring, not hidden) that introduces zero new
scoring *values*, only a new *aggregation* of values V6 already assigns.
**[MEASURED, important caveat]**: because `pokemon_score` returns numbers
in the thousands (prize term alone is `1000 × prize_count`), while V6's own
raw `ATTACK`-option score is just `o.attackId` (150–350 in this decklist —
see Part 1), the combined `lookahead_score` for `ATTACK` candidates is
**almost entirely determined by `post_action_state_value`**, while for
`PLAY`/`EVOLVE`/`ATTACH`/`ABILITY` candidates (whose own raw V6 scores run
14,000–75,000) both terms contribute meaningfully. This asymmetry is a
real, measured property of the combination — flagged explicitly rather than
smoothed over — and is directly responsible for the dominant disagreement
pattern found in Part 9/10 below.

---

## Part 4 — Candidate Selection & Scope

**Scope**: `SelectContext.MAIN` decisions with `select.maxCount == 1` and
2+ legal options — generalized from `search_lookahead_v2.py`'s own scoping
(originally "2+ `ATTACK` options only") to "any single-slot MAIN decision,"
because Part 1 shows `MAIN` is where V6 scores attack, retreat, evolve,
attach, and trainer-play candidates all in ONE list against each other —
exactly the decision point richest for the tactical trade-offs the research
prompt's Part 7 asks about.

**Explicitly out of scope, and reported as such rather than silently
skipped**: `SelectContext.DAMAGE_COUNTER_ANY` (Phantom Dive's own bench-
target placement) is a *separate* decision type from `MAIN` and was **not**
independently lookahead-augmented in this prototype — see Part 6 for what
this means for the "Phantom Dive target decisions" category the research
prompt asks about.

**N=3/5/10, measured on the same 970 decisions** (see Part 7 for full
numbers): all three were run as fully independent configurations (own
`search_begin` root clone each, not shared) so each N's numbers reflect
what a real deployment fixed at that N would actually cost. **[MEASURED]**
N=5 vs. N=10 chose the *same* candidate 91.2% of the time; N=5 vs. N=3
agreed 87.6% of the time. Given N=5's latency (median 32.6ms) is already
~3–4 orders of magnitude under the match budget, there is no latency
pressure to prefer N=3, and N=10's extra 8.8-point choice-agreement gain
over N=5 is small relative to its ~1.6× latency cost — **N=5 appears to be
a reasonable default**, though this is a directional read from one run, not
a tuned conclusion.

---

## Part 5 — RNG Safety Classification

**[FACT]**, sourced directly from `data/official/EN Card Data.csv`'s
"Effect Explanation" column (trainer cards) and `cg.api.all_attack()`'s
`.text` field (Pokemon attacks) for all 21 unique card IDs in
`decks/dragapult_ex.csv` — not memory, not guessed:

| Category | Cards | Reasoning |
|---|---|---|
| **DETERMINISTIC** | All 9 distinct attacks (Petty Grudge, Bite, Dragon Headbutt, Jet Headbutt, Phantom Dive, Cruel Arrow, Eon Blade, Itchy Pollen, Tuck Tail) | No coin-flip/random text in any attack's effect string, confirmed by direct query. |
| **DETERMINISTIC** | Retreat, Attach (basic energy/tool), Evolve, Ability activation | No stochastic component in this deck's card data. |
| **RNG_DEPENDENT (direct/outcome-random)** | Crushing Hammer (1120): *"Flip a coin. If heads, discard an Energy from 1 of your opponent's Pokemon."* | The card's own immediate effect is a coin flip — the ONE card in this 60-card deck with a genuinely uncertain outcome. |
| **RNG_DEPENDENT (shared-stream perturbation)** | Buddy-Buddy Poffin, Ultra Ball, Poke Pad, Crispin, Brock's Scouting (all end "...shuffle your deck.") | The *search* (which card to find) is a deterministic agent choice, but the shuffle consumes the shared native `Game::rng` — per `ENGINE_CLONE_LOOKAHEAD_AUDIT.md` Part 5, every clone from one `search_begin` sandbox shares the SAME `Game*` (and therefore the same `mt19937` stream). This does not make the immediate decision's outcome uncertain, but it means resolving one candidate that shuffles perturbs the RNG state any sibling candidate evaluated afterward (from the same root) would also read from if IT touches RNG-consuming code — a real non-independence, not silently ignored. |
| **UNKNOWN** | The `END` (pass/end-turn) option | Not covered by any of the reasoning above; the classifier returns `UNKNOWN` rather than guessing, per the research prompt's instruction not to pretend an unclassified case is safe. |

**[MEASURED]** Applied to this run's actual candidate pool (4,633
candidate-evaluations across 970 decisions × up to 5 candidates each):
3,308 DETERMINISTIC, 701 RNG_DEPENDENT, 624 UNKNOWN. Of the 116 N=5
disagreements specifically: 68 (58.6%) involved RNG_DEPENDENT/UNKNOWN on
NEITHER side (clean), 28 (24.1%) involved RNG_DEPENDENT on at least one
side, 6 (5.2%) involved the `UNKNOWN`-classified `END` option, and 14
(12.1%) are the terminal-value artifact discussed in Part 6/9 (which can
co-occur with either). **Practical conclusion**: for THIS specific deck,
RNG-dependence is a real but narrow concern (one direct-outcome card,
Crushing Hammer, plus five search-then-shuffle trainers) — most of this
deck's meaningful tactical decisions (which attack, whether to retreat,
which Pokemon to evolve/attach) are entirely DETERMINISTIC and their
lookahead comparisons are not subject to the shared-RNG caveat at all.

---

## Part 6 — Historical Replay Methodology (and a real technical constraint)

**A genuine engine constraint, verified by source, changes what "historical
replay" can mean here**: `search_begin`'s token is tied to a **live**
`battle_ptr` (`ENGINE_CLONE_LOOKAHEAD_AUDIT.md` Part 2B — "tied to the live
battle's internal state pointer at that instant... not something you can
manufacture from a deepcopy of a dataclass"). The real historical V6 ladder
replay JSON that exists in this repo (`data/v6_ladder_audit/replays/*.json`,
31 games; `results/ladder_behavior_audit/v6_decisions.csv`, 2,883 decision
rows from real Kaggle ladder games) has **no live engine process behind
it** — it is a dead JSON dump. Engine-backed lookahead **cannot** be
retroactively applied to those old games; there is no way to resume a
`search_begin` from a JSON snapshot.

**Resolution used here**: fresh **local self-play** through the real
`cg.dll` engine (`tools/v6_lookahead_experiment_runner.py`, using
`cg.game.battle_start/battle_select/battle_finish` directly, the same
underlying mechanism `tools/tournament.py` already uses) — NOT Kaggle, NOT
a new ladder submission, still V6's real unmodified policy. Every real
game's ACTUAL trajectory is driven ONLY by V6's real greedy choice
(`policy.agent(obs)`); the lookahead prototype runs in **shadow mode**,
evaluating the same live decision point in parallel without ever feeding
its own choice back into the real game. This is the closest correct
interpretation of "historical replay" available under the live-handle
constraint, and it is more rigorous than attempting (impossible) replay-JSON
reconstruction would have been — it uses genuinely live, uncorrupted search
state.

**Run**: 24 games, V6 (dragapult ex) vs. `lucario_ex_agent`
(deliberately reusing an existing repo opponent, per prior sessions'
`search_v2_ablation_experiment.py` methodology — nothing about the deck or
opponent selection was modified for this experiment), first-player slot
alternated across games (project convention). **[MEASURED]** 970 in-scope
decisions, 122.7s wall-clock. **[MEASURED]** V6 (real, unmodified) went
17-7 (70.8%) against this specific opponent in this run — reported for
context only; this experiment does not claim this is a general V6 win
rate, and it is **not** what this report uses to judge the lookahead
prototype (shadow mode never affected these outcomes).

**Per-category coverage, honestly reported**:

| Research-prompt category | Coverage in this run |
|---|---|
| Attack vs. retreat | **[MEASURED]** 1 direct instance found (Part 9 #5) — rare because V6's `RETREAT` option is itself gated behind a narrow `do_switch`/defensive-retreat condition (Part 1), so it is legal-and-competitive in relatively few decisions. |
| Immediate KO vs. preparation | **[MEASURED]** Indirectly covered by the dominant ATTACK→PLAY/EVOLVE/ABILITY pattern (Part 9/10) — 1-step lookahead cannot directly tag "this specific attack KOs," but the post-action board-value swing correlates with it. |
| Saving a 2-prize attacker vs. tempo | **[FUTURE QUESTION]** not cleanly isolated in this pass — would need per-decision board-state (HP/prize) logging, which this run's schema does not include (documented gap, not fabricated). |
| Energy preservation / attach targeting | **[MEASURED]** 9 ATTACH↔ATTACH disagreements found (Part 9 #3). |
| Evolution decisions | **[MEASURED]** 10 EVOLVE↔EVOLVE disagreements found (Part 9 #4). |
| **Phantom Dive target allocation** | **[MEASURED as N/A — out of scope by design]**, see Part 4: `DAMAGE_COUNTER_ANY` is a separate decision type, never independently lookahead-augmented here. When Phantom Dive IS the winning `MAIN` candidate, the resulting simulated state correctly reflects V6's own unchanged subset-sum combo planner's target choice (chain resolution drives the real, unmodified code) — but no A/B comparison of the *targeting itself* was performed. |

---

## Part 7 — Counterfactual Decision Examples (12, spanning every measured category)

All scores below are from the actual run (`results/v6_lookahead_experiment/1786649941_9e821c33_decisions.csv`, N=5). "V6 real outcome" is the ACTUAL recorded result of the real game this decision occurred in (never the lookahead's choice, which never touched the real game) — used per the research prompt's explicit instruction to inspect actual subsequent trajectories rather than assume a choice was better because it looks better.

| # | Game/Turn | V6 chose | V6 raw score | Lookahead's post-value total | Lookahead chose | Lookahead's total | RNG | V6's real game outcome | Classification |
|---|---|---|---|---|---|---|---|---|---|
| 1 | g0 t4 | ATTACK: Itchy Pollen | 323 | −1,027 | PLAY (idx1) | 619 | both DETERMINISTIC | v6_win | **UNCERTAIN** — lookahead judges board-development now as better than attacking now; without HP/prize context this can't be scored as strictly better, but it is a genuine, non-RNG, non-terminal disagreement (see Part 10 pattern discussion). |
| 2 | g0 t6 | ATTACK: Phantom Dive | 154 | 2,724 | PLAY (idx1) | 4,539 | both DETERMINISTIC | v6_win | **UNCERTAIN** (same pattern as #1, larger magnitude). |
| 3 | g0 t10 | ATTACH idx2 (Active) | 61,000 | 61,450 | ATTACH idx6 (Bench) | 61,800 | both DETERMINISTIC | v6_win | **UNCERTAIN, low-confidence** — a genuinely close call (350-point gap on a ~61,000-point base, i.e. <1% relative difference); not distinguishable from noise in the evaluation formula given the coarse `pokemon_score` unit scale. |
| 4 | g0 t12 | EVOLVE idx5 (Bench) | 70,002 | 81,462 | EVOLVE idx6 (Bench) | **1,070,001** (terminal +1,000,000) | both DETERMINISTIC | v6_win | **EQUIVALENT** — terminal-value artifact (Part 6/9-cluster below): the real game, via V6's own different sequence, also won. |
| 5 | g16 t4 | ATTACK: Itchy Pollen | 323 | 6,976 | **RETREAT** | 7,299 | both DETERMINISTIC | v6_win | **UNCERTAIN** — the ONE attack-vs-retreat disagreement found. Lookahead judges retreating now as marginally better (323-point gap on ~7,300) than attacking; too small a margin, and too little state context captured, to call this confidently better — flagged as the highest-value case for follow-up investigation given the research prompt specifically asked for this category. |
| 6 | g12 t6 | ABILITY idx7 | 40,000 | 42,480 | ABILITY idx8 | 44,900 | both DETERMINISTIC | v6_win | **UNCERTAIN, low-confidence** — which Pokemon's ability to activate; 2,420-point gap on a 40,000-point base (~6% relative). |
| 7 | g6 t8 | PLAY idx5 | 44,000 | 37,180 | PLAY idx6 | 37,480 | **both RNG_DEPENDENT** | v6_loss | **UNCERTAIN — RNG-confounded**, explicitly not trusted as a clean comparison (Part 5 caveat: both candidates' branches may have been perturbed by the shared RNG stream depending on evaluation order). Included specifically to illustrate what an RNG-confounded row looks like, not as evidence either way. |
| 8 | g8 t8 | PLAY idx1 | 15,000 | 8,290 | PLAY idx4 | 10,890 | both DETERMINISTIC | v6_win | **UNCERTAIN** — both candidates score negative-post-value (a losing-tempo turn within a game V6 still won overall), lookahead prefers the less-bad option. |
| 9 | g0/g12/g20 (cluster) | ATTACK: Phantom Dive / ABILITY / EVOLVE / PLAY (varies) | (various) | (various) | ATTACK: Phantom Dive (in every case) | **~1,000,154 – 1,070,001** (terminal) | mixed | **v6_win in all 14/14 instances, mechanically verified** | **EQUIVALENT (verified, not assumed)** — see the dedicated discussion immediately below. This is the single most important classification-methodology result of Part 7. |
| 10 | g22 t8 | END (pass) | 0 | −3,280 | PLAY idx0 | −1,311 | UNKNOWN vs DETERMINISTIC | v6_win | **UNCERTAIN** — `END`'s RNG status is `UNKNOWN` by design (not silently assumed safe); both candidates are negative (a bad turn either way). |
| 11 | g7 t4 | EVOLVE idx2 (Bench) | 30,001 | 30,161 | EVOLVE idx3 (Bench) | 31,610 | both DETERMINISTIC | v6_win | **UNCERTAIN** — which bench Pokemon to evolve first; 1,449-point gap. |
| 12 | g20 t14 | EVOLVE idx3 (Bench) | 70,002 | 83,172 | ATTACK: Phantom Dive | 1,000,154 | both DETERMINISTIC | v6_win | Part of cluster #9 (listed separately since V6's own choice here was EVOLVE, not ABILITY/PLAY like its siblings in the cluster). |

### The terminal-value cluster (14 instances, cluster #9): a verified EQUIVALENT finding, not a missed win

**[MEASURED, mechanically verified against real game outcomes — not
inferred]**: 14 of the 116 N=5 disagreements have a lookahead-side score
exceeding 500,000 in magnitude, meaning the simulated branch reached
`state.result == my_index` (a win) inside the same-player decision chain.
All 14 occurred at multi-action turns (turn numbers 10–18, i.e. mid-to-late
game) where the SAME turn offered several sequential `MAIN` decisions (play
a card, use an ability, evolve, *then* attack — all legal within one real
turn before ending it). In every one of the 14 cases, this project cross-
referenced the row's `game_id` against this run's own recorded
`*_games.csv` outcome: **all 14 belong to games where V6's real, different,
non-attack-first sequence also went on to win** (games 0, 12, 15, 19, 20 —
all `v6_win`). This directly supports the interpretation that the
lookahead's "attack now, don't bother developing first" suggestion and
V6's actual "develop first, then attack" sequence reach the **same**
winning outcome — the 1-ply lookahead simply cannot see past its own
single simulated action to notice that the alternative branch (do the
non-attack action, THEN attack next decision) also terminates in a win a
step later. This is an honest, load-bearing limitation of a strictly 1-ply
evaluator, reported plainly per the research prompt's explicit instruction
not to claim an action is better "merely because it looks intuitively
better" — a naive read of these 14 rows' raw score deltas (thousands of
points in the lookahead's favor) would have overclaimed 14 near-misses
avoided; the verified real outcomes show they are not misses at all.

---

## Part 8 — Critical A/B Result

**[MEASURED]**, N=5, 970 decisions, one run:

| Metric | Value |
|---|---|
| Disagreement % (raw) | 116/970 = **12.0%** |
| Disagreement %, RNG/UNKNOWN-clean only | 68/970 = **7.0%** |
| Disagreement %, RNG-confounded (either side RNG_DEPENDENT) | 28/970 = **2.9%** |
| Disagreement %, terminal-value artifact (verified EQUIVALENT) | 14/970 = **1.4%** |
| Disagreement %, involves `UNKNOWN`-classified option | 6/970 = **0.6%** |

**Conservative estimate of historical V6 "mistakes" avoided**: **zero can
be responsibly claimed from this run.** The 14 highest-magnitude
disagreements (which would, on raw score alone, look like the strongest
candidates for "mistakes avoided") were mechanically verified to be
EQUIVALENT, not improvements — the real V6 games in question were already
winning either way. The remaining 68 clean disagreements are genuine
differences in tactical *assessment*, but this experiment's shadow-mode
design never let the lookahead's choice actually play out in a real game,
so there is no outcome evidence (win/loss, subsequent trajectory) to
support a directional claim for any of them individually beyond the
single-step score delta already shown in Part 7. Per the research prompt's
explicit instruction, this is reported as an honest gap, not converted into
a fabricated win-rate estimate.

---

## Part 9 — Latency Benchmark

**[MEASURED]**, 970 decisions, three independent configurations (each with
its own `search_begin` root clone, so each reflects the true cost of a real
deployment fixed at that N):

| N | Median | p95 | Max | Mean | Disagreement rate |
|---|---|---|---|---|---|
| 3 | 21.5 ms | 52.8 ms | 76.9 ms | 24.7 ms | 7.4% |
| 5 | 32.6 ms | 77.9 ms | 236.7 ms | 37.0 ms | 12.0% |
| 10 | 53.6 ms | 127.0 ms | 206.2 ms | 61.0 ms | 14.9% |

**An important correction to `ENGINE_CLONE_LOOKAHEAD_AUDIT.md`'s earlier
raw-engine estimate**: that audit measured ~0.61–0.93 ms for 5–10
simulations using ONLY raw `search_begin`/`search_step` ctypes calls. This
prototype's end-to-end latency (32.6–53.6 ms median) is **30–60× higher**,
not because the engine is slower, but because the realistic pipeline also
(a) runs V6's own full heuristic scoring function multiple times per
candidate to resolve same-player decision chains, (b) round-trips each
hypothetical `Observation` through `dataclasses.asdict`/JSON, and (c)
deep-copies a policy object per candidate. **This is the number any future
deployment decision should use, not the raw-engine number** — flagged
explicitly since the two audits could otherwise be read as contradictory.

**Against the Kaggle budget**: the only documented constraint is a
whole-match 10-minute (600,000 ms) wall-clock budget
(`ENGINE_CLONE_LOOKAHEAD_AUDIT.md` Part 7, no per-decision limit found).
**[MEASURED]** this run averaged 970/24 ≈ 40 in-scope decisions per game; at
N=5's median (32.6 ms), that is **~1.3 seconds of added latency per full
match** — even at N=10's p95 (127.0 ms), **~5.1 seconds per match**. Both
are three to four orders of magnitude under budget. No timeout risk.

---

## Part 10 — Performance & Memory

**[MEASURED]**: 0 crashes / 0 unhandled exceptions across 2,910
`evaluate_decision_with_lookahead` calls (970 decisions × 3 N-configs) plus
an earlier 2-game smoke-test batch used during development. RSS grew from
35.0 MB to 49.9 MB over the full 24-game run (**+14.8 MB total**, ≈0.015
MB/decision across ~18 branch simulations/decision, i.e. even lower
per-clone growth than `ENGINE_CLONE_LOOKAHEAD_AUDIT.md`'s own worst-case
figure) — no OOM risk, consistent with the prior audit's GREEN memory
verdict. `search_end()` is called (in a `finally` block) after every
decision's candidate loop, matching correct hygiene.

**Deterministic actions handled correctly**: **[FACT]** verified — 3,308 of
4,633 evaluated candidates were classified `DETERMINISTIC`, and the module
never treats an unclassified option type as safe (falls through to
`UNKNOWN` rather than guessing).

**RNG-dependent actions clearly isolated**: **[MEASURED]** yes — every
disagreement row is tagged with both sides' RNG classification, and the
Part 7/8 analysis explicitly separates RNG-confounded rows (28/116) from
clean ones (68/116) rather than blending them.

---

## Part 11 — Decision Disagreement Analysis (why V6 and V6+lookahead diverge)

**[MEASURED, load-bearing finding]**: the dominant disagreement pattern —
55 of 116 N=5 disagreements (47.4%) — is `V6 chose ATTACK` →
`lookahead chose PLAY`. This traces directly to the Part 3 finding: V6's
own raw `ATTACK`-option score is just `o.attackId` (150–350), while
`PLAY`/`EVOLVE`/`ATTACH`/`ABILITY` options score in the tens of thousands.
This means `post_action_state_value` (thousands-scale) **always dominates**
the combined `lookahead_score` for ATTACK candidates specifically, while
for non-ATTACK candidates the two terms are comparable. **[MEASURED,
directly checked to rule out a scale-artifact confound]**: because
`v6_choice` is always V6's own true argmax over the FULL candidate list
(not just the evaluated top-N), every one of these 55 rows is a case where
V6's own raw scoring genuinely ranked ATTACK above every other candidate
including the one PLAY option lookahead prefers — so this is a real
divergence in *simulated-consequence* assessment, not an artifact of
lookahead trivially favoring high-raw-score option types. **[HYPOTHESIS,
not tested this run]**: this pattern is consistent with — but does not
prove — a real property of V6's design: because you can take multiple
`MAIN` actions in one turn before attacking (play/attach/evolve, THEN
attack), V6's steeply front-loaded non-attack scores may function as an
intentional-by-construction "do beneficial prep first, attack once nothing
better remains" sequencing device, in which case many of these 55
"disagreements" could represent lookahead recommending V6 attack ONE STEP
EARLIER in a sequence V6 would reach the equivalent of shortly after
anyway (directly analogous to the verified terminal-value cluster in Part
9) rather than a genuinely different final sequence of actions for the
turn. This project does not have the per-turn full-sequence data to confirm
or refute this hypothesis and flags it explicitly as the top candidate
explanation for the dominant disagreement pattern, worth resolving before
trusting the 68-clean-disagreement count as "68 real tactical differences."

Other measured patterns: EVOLVE↔EVOLVE (10, which Pokemon to evolve first),
ATTACH↔ATTACH (9, which Pokemon to attach energy to), ABILITY↔ABILITY (7,
which Pokemon's ability to use), PLAY↔ATTACK (6, reversed direction of the
dominant pattern — lookahead sometimes prefers attacking over V6's chosen
play), ATTACK↔EVOLVE (4), ABILITY↔ATTACK (3), and single instances of
ATTACK↔RETREAT and EVOLVE↔ATTACK.

---

## Part 12 — GO / NO-GO Verdict

### **D — INSUFFICIENT DATA**

Infrastructure works correctly (Part 2/10: 0 crashes, negligible memory
growth, latency 3–4 orders of magnitude under budget, real deterministic
vs. RNG-dependent candidates correctly and conservatively classified). A
real, non-trivial, RNG-independent disagreement signal exists (Part 8: 7.0%
of all decisions). But **this experiment cannot responsibly answer whether
acting on that signal would improve V6's win rate**, for two compounding
reasons discovered during the analysis itself, not assumed in advance:

1. **By design**, the lookahead's choice never drove a real game (shadow
   mode only) — there is no outcome data, only single-step score deltas.
   This was a deliberate, correct choice (per the research prompt's
   instruction not to fabricate win-rate claims from counterfactual
   decisions), but it means the natural next step — not this report — is
   where outcome evidence would come from.
2. **The dominant disagreement pattern (Part 11, 47% of disagreements) has
   an unresolved, plausible EQUIVALENT explanation** (V6 "attacks last in a
   sequence that reaches the same place"), directly analogous to the
   mechanically-verified 14-case terminal-value cluster (Part 7/9) where
   the naive reading of the score delta would have overclaimed. Until this
   is resolved, the 68 "clean" disagreements cannot be treated as 68
   confirmed tactical improvements — some unknown fraction of them may be
   further instances of the same 1-ply-horizon artifact.

This is a **conservative, evidence-following** call: the prompt was
explicit that "Be conservative. Do NOT convert counterfactual decisions
into fake win-rate improvements," and a middling STRONG GO or CONDITIONAL
GO cannot be honestly supported without either outcome data or resolution
of the sequencing-artifact hypothesis above. Equally, NO-GO is not
supported either — nothing found here indicates lookahead is *harmful* or
*ineffective*; the RNG-clean 7% disagreement rate and the (verified, not
assumed) fact that the terminal-value cluster never represented an actual
missed win are both mildly reassuring, not damning.

---

## Recommended Next Research Step

**Not a Value Model, not MCTS, not V11** — per the research prompt's own
constraint, and because nothing found here indicates the bottleneck is
evaluator sophistication rather than missing outcome data.

The single most information-dense next step, directly motivated by this
report's own two open questions:

1. **Resolve the sequencing-artifact hypothesis (Part 11)** first, cheaply,
   without any new game-playing: for the 55 ATTACK→PLAY (and reverse)
   disagreements, check — using data already available in this run's raw
   CSV plus one small addition (log `decision_num` sequences within a
   turn) — whether V6's real turn eventually reaches an attack anyway a
   few `decision_num`s later, and whether the OPPONENT gets an intervening
   real turn in between (which would break the "equivalent, just delayed"
   argument, since the opponent could act on the extra turn a lookahead-
   preferred immediate attack would have denied them). This is a re-
   analysis of existing data, not a new experiment.
2. **Then, only for whichever disagreements survive step 1**, run a small,
   pre-registered live A/B (a few hundred games, first-player alternated,
   per this project's standing process rules) where the lookahead's choice
   ACTUALLY drives the game for a narrowly-scoped decision type (e.g. just
   the ATTACK-vs-PLAY case), to get real outcome evidence — the one thing
   this report structurally could not produce. This is the natural,
   minimal follow-up implied by the "D: insufficient data" verdict, not a
   scope expansion.
