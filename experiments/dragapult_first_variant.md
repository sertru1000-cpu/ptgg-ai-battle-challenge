# Experiment: Dragapult ex "always go first" variant (dragapult_fix_v1)

```
Experiment: dragapult_fix_v1 (Phase 4)
Hypothesis: results/dragapult_first_second_analysis.md (Phase 1/2) found, via a
  fully controlled experiment (same unmodified BEST_DRAGAPULT_AGENT code, engine
  slot fixed at 0, IS_FIRST answer forced), that Dragapult ex wins significantly
  more often when it goes first vs. Abomasnow ex (67.1% vs 56.3%, n=1000/condition,
  z=-4.97) and is directionally better-or-equal first vs. every other opponent
  tested (Random, Iono's, Lucario ex -- never significantly worse). Hypothesis: a
  minimal variant that always elects to go first (instead of the official
  notebook's unconditional "always go second") should improve Dragapult's overall
  performance against the current opponent pool, with no other behavioral change.
Change: new file src/agents/dragapult_agent_always_first.py. It is NOT a rewrite --
  it imports the real, completely unmodified src.agents.dragapult_agent module and
  wraps only the single IS_FIRST decision (returns YES directly instead of calling
  the wrapped agent's scoring for that one select event); every other decision is
  delegated unchanged to dragapult_agent.agent(). src/agents/dragapult_agent.py
  itself is untouched and preserved permanently as BEST_DRAGAPULT_AGENT (the
  faithful notebook port, for reproducibility and as the fallback/reference).
Baseline: src/agents/dragapult_agent.py (BEST_DRAGAPULT_AGENT) under natural
  tournament-harness slot alternation. Because BEST always answers NO and
  abomasnow_agent/iono_agent/lucario_ex_agent all always answer YES, BEST ends up
  as the second player in effectively 100% of its games against those three
  (same confound documented in Phase 1/2) -- i.e. this baseline already reflects
  BEST's real, natural "mostly-second" deployed behavior, not an artificially
  handicapped one.
Opponent: random_agent, abomasnow_agent (corrected deck,
  decks/abomasnow_ex_corrected_v1.csv), iono_agent, lucario_ex_agent.
Games: 500 per opponent (2000 total) for the variant, natural slot alternation
  (results/dragapult_variant_benchmark/). Compared against each opponent's most
  recent available natural-alternation BEST_DRAGAPULT_AGENT data (300 games vs.
  abomasnow_corrected from the Phase-5 experiment; 200 games each vs. iono_agent,
  random_agent, lucario_ex_agent from session-1 / Phase-6 data). Sample sizes and
  deck versions are NOT identical across the two sides of each comparison below
  (flagged explicitly, not hidden) -- this is a real limitation of reusing
  existing runs rather than a fresh matched design.
Result (two-proportion z-test, BEST-natural vs. variant-natural):
  vs abomasnow_corrected: BEST 53.67% (n=300) -> variant 56.60% (n=500)  z=0.81  not significant
  vs iono_agent:            BEST 65.50% (n=200) -> variant 63.40% (n=500)  z=-0.52 not significant
  vs random_agent:          BEST 97.50% (n=200) -> variant 97.40% (n=500)  z=-0.08 not significant
  vs lucario_ex_agent:      BEST 52.00% (n=200) -> variant 49.20% (n=500)  z=-0.67 not significant
  Pooled (all 4 opponents):  BEST 65.67% (n=900) -> variant 66.65% (n=2000) z=0.52  not significant
Confidence: none of the individual or pooled "which one wins more overall"
  comparisons reach significance at these sample sizes -- this aggregate
  comparison is noisier than Phase 1's dedicated experiment (smaller n per cell,
  and it mixes in deck-version/sample-size mismatches noted above). It should NOT
  be read as contradicting Phase 1: Phase 1's forced-condition design (same agent
  code, n=1000/condition, only the coinflip forced) is the higher-quality causal
  estimate, and it robustly shows first >= second for BEST_DRAGAPULT_AGENT in
  every matchup tested, significantly so vs. Abomasnow. The aggregate numbers here
  are directionally consistent with that (positive vs. abomasnow and pooled,
  small/mixed elsewhere) but too noisy on their own to confirm it independently.
Runtime: 2000 games well under a minute (native engine).
Conclusion: the highest-quality available evidence (Phase 1's controlled
  experiment) supports the change; the lower-powered aggregate re-check here does
  not contradict it and is directionally consistent, just underpowered to confirm
  it alone. There is no matchup where the variant was significantly worse.
  Adopting it also has a methodological benefit beyond raw win rate: it makes
  Dragapult's IS_FIRST preference match the other three ported agents
  (all unconditionally prefer yes), which means ordinary tournament-harness slot
  alternation now produces a genuine, balanced 50/50 first/second split for every
  Dragapult matchup going forward, instead of requiring the special
  forced-coinflip experiment machinery from Phase 1 to get a valid split.
Keep/Revert: PROMOTE src/agents/dragapult_agent_always_first.py as the Dragapult
  representative used in the Phase 7/8 formal matrix and going forward
  (versioned dragapult_fix_v1). src/agents/dragapult_agent.py is NEVER modified or
  deleted -- it remains BEST_DRAGAPULT_AGENT / the reference notebook-faithful
  port, kept permanently for reproducibility of the FIRST REPORT and this
  session's Phase 1-3 analysis, and as the fallback if future evidence
  reverses this call.
```
