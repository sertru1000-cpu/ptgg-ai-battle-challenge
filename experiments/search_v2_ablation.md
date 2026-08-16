# Experiment: Search V2 (full-chain resolution) vs. BEST_HEURISTIC

```
Experiment: search_v2_ablation_v1 (Part A4-A8)
Hypothesis: Search V1's regression (Competitive V1, experiments/search_1ply.md)
  was caused by evaluating an artificial intermediate state (stopping after one
  search_step even when the chosen attack triggers a linked follow-up decision
  like Dragapult's DamageCounter placement or Lucario's SelectAttachTo chain --
  see results/search_v2_audit.md Parts A1/A2, source-verified against
  EffectInstant.h/EffectProc.h/CreateCard.h). Hypothesis: Search V2
  (src/agents/search_lookahead_v2.py), which resolves the FULL same-player
  decision chain (driven by the real heuristic on each hypothetical
  sub-decision, stopping only when control passes to the opponent or the game
  ends) before evaluating, should recover some or all of V1's lost performance.
Change: new src/agents/search_lookahead_v2.py. Same evaluation function as V1
  (deliberately unchanged, to isolate the chain-completion fix as the only
  variable -- see search_v2_audit.md section 5). A real implementation bug was
  found and fixed during development (search_step chaining used the ROOT
  search_id for every step instead of the previous step's returned searchId,
  causing every "continuation" call to silently re-branch from the original
  position -- confirmed via chain_cap_hit=28/93 and searches_failed=9/93 before
  the fix, 0/0 after, see search_v2_audit.md and code comments). Base
  heuristics (dragapult_fix_v1, lucario_ex_agent) themselves UNCHANGED.
Baseline: BEST_HEURISTIC alone (dragapult_fix_v1 / lucario_ex_agent), same
  opponents, same games, natural slot alternation (both prefer "yes" to
  IS_FIRST, so this gives genuine 50/50 first/second splits per
  Competitive V1's finding).
Opponent: iono_agent, lucario_ex_agent/dragapult_agent (cross), abomasnow_agent
  (corrected deck), random_agent (sanity check only, per instruction).
Games: 500/condition/matchup, 7 matchups x 2 conditions = 7000 games total,
  zero aborted, zero search failures, zero chain-length-cap hits (max 20).
Result (two-proportion z-test, heuristic-only vs. Search V2):
  dragapult vs iono:       66.2% -> 39.4%  z=-8.49  SIGNIFICANT, MUCH WORSE
  dragapult vs lucario:    49.0% -> 32.6%  z=-5.28  SIGNIFICANT, WORSE
  dragapult vs abomasnow:  57.4% -> 43.4%  z=-4.43  SIGNIFICANT, WORSE
  dragapult vs random:     97.4% -> 96.2%  z=-1.08  not significant
  lucario vs iono:         78.4% -> 65.8%  z=-4.44  SIGNIFICANT, WORSE
  lucario vs dragapult:    53.0% -> 39.8%  z=-4.19  SIGNIFICANT, WORSE
  lucario vs random:       95.6% -> 98.0%  z=+2.16  SIGNIFICANT, better (only
                            positive result; opponent is the random sanity
                            check, explicitly the least informative matchup)
Search coverage / mechanics (Part A6): search engaged on 900-1650 attack
  decisions per matchup (multi-attack MAIN choices), 100% success rate (0
  failures across 16,000+ total search_step calls this run), average
  same-player chain length 2.4-4.7 steps (matches expectation: Phantom Dive/
  Aura Jab chains genuinely need several linked selects), search disagreed
  with the heuristic's own top pick 55-92% of the time it engaged.
Runtime: average per-game latency 0.04s-0.16s across conditions -- Search V2
  adds real but small overhead (roughly 1.3-2x a plain heuristic game, e.g.
  dragapult-vs-iono 0.125s -> 0.159s), nowhere close to threatening the
  10-minute/match competition budget even at these decision-rich matchups.
Confidence: very high that this specific Search V2 implementation is worse
  than the heuristic baseline in every serious (non-random) matchup tested --
  6 of 7 matchups significant at p<0.0001-level z-scores, effect sizes from
  -12pp to -27pp, consistent direction and magnitude across two different base
  heuristics (Dragapult, Lucario) and three different opponents. This is not
  noise and not the same bug as V1 (chain resolution and search mechanics are
  now confirmed correct: 0 failures, 0 cap hits, chains resolve to sensible
  lengths).
HYPOTHESIS (root cause, not further isolated this session -- flagged as
  explanation, not proven mechanism): the chain-completion fix was necessary
  but not sufficient. `_evaluate()` (prize race + HP differential + bench-count
  differential, deliberately kept unchanged from V1 to isolate the chain fix)
  is a crude, generic board-state score. Both base heuristics' own attack-choice
  logic is considerably more sophisticated for the exact decisions Search V2
  targets -- Dragapult's main_option_proc() runs an explicit subset-sum search
  over the opponent's bench factoring in prize-count math, KO-immunity flags
  (no_damage_dex/no_damage_counter), and multi-turn plan continuity; Lucario's
  planning loop similarly factors in weakness/resistance, prize-count
  thresholds, and multi-turn setup value. A linear "prize diff + HP diff +
  bench diff" score has no notion of any of this domain knowledge, so on the
  55-92% of decisions where it disagrees with the heuristic, it is very
  plausibly just a worse judge of the position -- not because it's looking at
  an incomplete state anymore, but because its complete-state evaluation
  itself is worse than the hand-tuned heuristic's decision logic for this
  specific, narrow decision class. This would explain why fixing the
  well-verified state-incompleteness bug did not recover performance: it
  removed one source of error but left the (apparently larger) evaluation-
  quality gap fully in place.
Conclusion: Search V2 is a genuine correctness improvement over V1 (fixes a
  real, source-verified bug, confirmed via mechanics: 0 chain-cap-hits, 0
  search failures, sensible chain lengths) but does NOT recover competitive
  performance -- it is significantly worse than the heuristic baseline in
  every serious matchup, by a wide and consistent margin. Per the Part A8
  promotion criteria (do not promote on raw win rate alone; require
  directionally consistent improvement, adequate sample size, and no
  correctness regressions) -- this fails the very first criterion
  (directionally consistent IMPROVEMENT); the directionally consistent result
  here is the opposite. This is exactly the valid, useful negative result the
  prompt anticipates ("If Search V2 does not improve performance: Keep the
  heuristic. That is a valid and useful result").
Keep/Revert: DO NOT PROMOTE Search V2. BEST_AGENT remains dragapult_fix_v1 /
  lucario_ex_agent (statistically tied, per Competitive V1). src/agents/
  search_lookahead_v2.py is kept in the repo (not deleted) as a correct,
  working implementation of full-chain search -- valuable infrastructure and
  a documented negative result -- but is not used by any recommended
  configuration. Any future search attempt should replace `_evaluate()` with
  something that captures at minimum KO-immunity and prize-count-threshold
  reasoning before being worth re-testing; extending search depth or
  decision-type coverage on top of the current evaluation function is not
  expected to help, per this session's evidence, and is not recommended as a
  next step (see reports/competitive_v2.md's leaderboard-strategy ranking).
```
