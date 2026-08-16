# Experiment: 1-ply Search API augmentation of dragapult_fix_v1's attack choice

```
Experiment: search_1ply_v1 (Phase 12/13)
Hypothesis: a single-ply Search API lookahead (search_begin once per decision,
  one search_step per candidate attack against a shared determinization,
  evaluate resulting board state, pick the best) can improve on
  dragapult_fix_v1's own attack-choice heuristic for MAIN decisions offering 2+
  attacks -- targeting exactly the high-impact decision class the prompt calls
  out (attacks, KO opportunities).
Change: new src/agents/search_lookahead.py (make_search_augmented_agent wraps
  any base agent unchanged except this one decision class) and
  tools/search_ablation_experiment.py (own game loop, does NOT strip
  obs["search_begin_input"] the way tools/tournament.py's shared harness does --
  see code comment; that stripping is harmless for every other experiment this
  session since none of them call the Search API, so the shared harness was left
  unchanged rather than risk it).
Baseline: dragapult_fix_v1 alone (src/agents/dragapult_agent_always_first.py,
  the Tier-1 agent from the Phase 7-10 formal matrix).
Opponent: abomasnow_corrected, iono_agent, lucario_ex_agent (the 3 agent-vs-agent
  opponents from the formal matrix).
Games: 500 per opponent per condition (3000 total), zero aborted, zero search
  failures (2634+3362+2590 = 8586 search_step calls all succeeded).
Result (two-proportion z-test, heuristic-only vs. plus-search):
  vs abomasnow_corrected: 56.60% -> 47.40%  z=-2.91   SIGNIFICANT, WORSE
  vs iono_agent:           66.60% -> 29.80%  z=-11.64  SIGNIFICANT, WORSE (huge)
  vs lucario_ex_agent:     48.80% -> 37.00%  z=-3.77   SIGNIFICANT, WORSE
  pooled:                  57.33% -> 38.07%  z=-10.56  SIGNIFICANT, WORSE
Runtime: no perceptible overhead (search_step calls are cheap, tens of ms; see
  docs/search_api.md Phase 12 update). Not the bottleneck -- correctness is.
Confidence: very high that this specific implementation is significantly WORSE
  than the heuristic baseline, in every matchup tested, not just noise.
Root-cause analysis (HYPOTHESIS, code-supported but not independently isolated
  by a further ablation -- flagged as such, not asserted as settled):
  src/agents/dragapult_agent.py's own attack-choice logic is not a simple
  "score this turn's damage" heuristic -- main_option_proc() runs an explicit
  subset-sum search over the opponent's bench to plan which Pokemon Phantom
  Dive's attack damage AND its 6 bench damage counters should target for a
  multi-KO sweep, storing the plan in module-global `plan_a`/`plan_b`. A later,
  SEPARATE select in the SAME turn (SelectContext.DAMAGE_COUNTER, choosing where
  to actually place those 6 bench damage counters) reads `plan_b.counter`
  directly to score its options. When search_lookahead.py overrides the MAIN
  attack choice to something OTHER than what the heuristic itself planned
  (`plan_a.attack`), `plan_b.counter` still reflects the heuristic's original,
  now-abandoned plan -- so the very next real decision (damage counter
  placement) gets scored against a stale, mismatched plan instead of the attack
  actually taken. Separately and more simply: `search_step` for a Phantom-Dive
  candidate almost certainly returns an observation still AWAITING that same
  DAMAGE_COUNTER follow-up choice (a real player decision, not an automatic
  resolution) -- meaning the 1-ply `_evaluate()` snapshot is taken BEFORE the
  bench-damage sweep is even placed, so search's own evaluation of Phantom Dive
  candidates never actually sees the attack's signature effect (the multi-KO
  bench sweep) in the first place. Both mechanisms point the same direction:
  a naive single-select-override integration is fundamentally mismatched with
  a heuristic whose value is realized across a linked PAIR of selects, not
  within one. This plausibly explains why the damage is worst vs. iono_agent
  (whose own bench-heavy, multi-Pokemon-per-turn deck style likely interacts
  with Dragapult's bench-sweep planning the most).
Conclusion: Outcome under the Phase 13 framework is a clear, statistically
  overwhelming NEGATIVE result -- not "no improvement" (Outcome C) but
  measurable harm, traced to an implementation-level state-integration bug
  rather than a fundamental flaw in the Search API itself (docs/search_api.md's
  Phase 11/12 findings -- legality, cost, usage pattern -- all held up fine
  in isolation). This is an important distinction: the API is usable and cheap;
  this specific wrapper's naive "override just the top-level choice" pattern is
  not safe to use on a heuristic with cross-select planning state without either
  (a) also invalidating/recomputing that state when overriding, or (b) letting
  the search rollout continue through the SAME agent's own follow-up decisions
  instead of stopping at one ply.
Keep/Revert: REVERT to the heuristic-only baseline for any actual deployment.
  src/agents/search_lookahead.py and tools/search_ablation_experiment.py are
  kept in the repo (not deleted) as the Phase 12/13 record and as a starting
  point for a future, correctly-scoped attempt -- but dragapult_fix_v1 alone
  remains the recommended agent, unmodified by this experiment.
```

## Phase 14 (search depth) — explicitly not pursued

Per the prompt's own instruction ("Only if 1-ply/short search demonstrates a
measurable benefit, compare... search depth 1, 2, 3..."), Phase 14 does not
apply: 1-ply search measurably HURT performance here, so there is no positive
result to extend to greater depth. Deepening a search built on the same
state-integration bug and the same crude evaluation function would likely
compound rather than fix the problem. Any future search work should first
correctly resolve the integration issue identified above at 1-ply before
considering depth.
