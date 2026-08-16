# Meta-Deck Gauntlet: V6 vs V13 vs the Real Kaggle Meta

**Status: preliminary, single run, n=20 games per cell — not statistically conclusive.**
Raw per-game data preserved under `results/meta_gauntlet_v6_v13/games/*.jsonl` (400 games,
0 aborted); do not discard when re-running or scaling up.

## Method

- **Question**: does testing V13 exclusively against V6 (mirror matches) risk overfitting to
  V6's own play patterns, vs. how V6 and V13 each actually perform against the real ladder
  meta?
- **Agents under test**: `main_v6.py` (BALANCED policy) and `main_v13.py` (same policy engine
  + one Cheren scoring branch, piloting the TURBO CONSISTENCY deck) — each kept its **own**
  fixed deck throughout, exactly as they'd run on Kaggle.
- **Opponent**: `src.agents.generic_policy_agent.make_agent(deck)`, this repo's existing
  deck-agnostic Layer-B scoring policy, rebuilt fresh per meta deck. Chosen over "V6 itself"
  as the baseline because using V6 as the opponent would (a) make the V6 gauntlet a mirror
  match against itself, confounding the result, and (b) bias the V13 gauntlet, since V13 is a
  deliberate deck-only variant of V6's own policy — a shared-policy opponent would not be a
  neutral yardstick for either agent.
- **Meta decks**: all 10 files under `decks/meta_*.csv` (real archetypes recovered from the
  live Kaggle episode data in earlier phases — see `reports/real_meta_v2.md`).
- **Games**: 20 per (agent, meta deck) pair, alternating which engine slot the agent-under-test
  occupies every game (`tools/tournament.py`'s existing convention) → 200 games for V6 + 200 for
  V13 = 400 total. **Verified directly from `first_player_slot`** (not assumed from slot
  alternation, per this project's standing process rule): every one of the 20 cells split
  exactly 10 games first / 10 games second.
- Engine: real `cg.dll` via `cg.game.battle_start/battle_select/battle_finish`, no RNG seed
  control (none exists in the engine) — statistical confidence comes only from game count.

## Results

| Meta Deck | V6 Win Rate (of 20) | V13 Win Rate (of 20) | Delta (V13 − V6) |
|---|---|---|---|
| Cynthia's Garchomp ex | 19 (95.0%) | 20 (100.0%) | +1 |
| Dragapult ex | 20 (100.0%) | 20 (100.0%) | 0 |
| Fezandipiti ex | 17 (85.0%) | 10 (50.0%) | **−7** |
| Marnie's Grimmsnarl ex | 18 (90.0%) | 16 (80.0%) | −2 |
| Mega Kangaskhan ex | 11 (55.0%) | 10 (50.0%) | −1 |
| Mega Lopunny ex | 19 (95.0%) | 20 (100.0%) | +1 |
| Mega Lucario ex | 19 (95.0%) | 20 (100.0%) | +1 |
| Teal Mask Ogerpon ex | 18 (90.0%) | 20 (100.0%) | +2 |
| Team Rocket's Mewtwo ex | 18 (90.0%) | 18 (90.0%) | 0 |
| Abra/Kadabra/Alakazam (unlabeled cluster 01) | 17 (85.0%) | 19 (95.0%) | +2 |
| **Aggregate (200 games each)** | **176 (88.0%)** | **173 (86.5%)** | **−1.5pp** |

**[Measured result]** V6 and V13 are statistically close in aggregate (88.0% vs 86.5%, −1.5pp,
n=200 each) — small enough that it should not be read as one agent being clearly stronger
overall against this external-meta gauntlet.

**[Measured result]** V13's one real weak spot in this run is **Fezandipiti ex** — it drops all
the way to a 50/50 coin flip (10/20) where V6 wins 85% (17/20), a 7-game/35pp gap that is large
relative to every other cell measured. **Mega Kangaskhan ex** is the one deck where *both*
agents are weak (V6 55%, V13 50%) — the only other cell at or near a coin flip for either agent.
Everywhere else, V13 matches or slightly beats V6 (by 1-2 games/20).

**[Hypothesis, not verified this run]** The Fezandipiti ex gap plausibly traces to V13's deck
swap: `decks/dragapult_v13_turbo.csv` was purpose-built for "brick-proof, maximal-draw,
one-ply-greedy consistency" (see `V13_IMPLEMENTATION_REPORT.md`), which may sacrifice
resilience against a specific matchup the original deck handled better. This is not diagnosed
here (would need per-game replay inspection) and should not be treated as confirmed.

### First/second-player split (aggregate, per process rule)

| Agent | As first player | As second player |
|---|---|---|
| V6 | 90/100 (90.0%) | 86/100 (86.0%) |
| V13 | 83/100 (83.0%) | 90/100 (90.0%) |

**[Measured result, directional only — n=100 per cell]** V6 was slightly stronger going first;
V13 was slightly stronger going second, and specifically weaker going first against Fezandipiti
ex (4/10) and Mega Kangaskhan ex (4/10) — the same two matchups driving its aggregate dip. Not
enough games to call this a real first/second-player effect for either agent; flagged as a
future research question, not a finding.

## Conclusion

**Neither agent is decisively "more robust against the external meta" at this sample size** —
the 1.5pp aggregate gap is well within what 200 games can produce by chance alone. What the
data does show with more confidence (7-game gap on a single 20-game matchup) is that **V13
carries one real regression risk (Fezandipiti ex) that V6 does not have**, without a
compensating advantage anywhere close to that size. If a single conclusion has to be drawn:
**V6 looks marginally more robust** — it never drops below 55% against any of the 10 real meta
decks tested, whereas V13 hits an exact coin flip against two of them. This should be read as a
lean, not a verdict, and specifically motivates re-running Fezandipiti ex at higher n (and/or
inspecting a handful of V13-vs-Fezandipiti replays) before making any submission decision on
V13's behalf.

## Artifacts

- `tools/build_meta_gauntlet_v6_v13.py` — gauntlet runner (reusable, `--games-per-deck` /
  `--out-dir` flags).
- `tools/summarize_meta_gauntlet_v6_v13.py` — first/second-player split summarizer.
- `results/meta_gauntlet_v6_v13/summary.json` — per-(agent, deck) aggregate.
- `results/meta_gauntlet_v6_v13/games/*.jsonl` — all 400 raw per-game records (untouched, not
  overwritten by future re-runs of the same script — new run_id per invocation).
