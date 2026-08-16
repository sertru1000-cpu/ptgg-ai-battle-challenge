# Experiment: Abomasnow deck fix (notebook-faithful decklist)

```
Experiment: abomasnow_deck_fix_v1
Hypothesis: the on-disk decks/abomasnow_ex.csv substitutes Ultra Ball, Precious
  Trolley, Carmine, and Surfing Beach (all specifically scored by name in
  src/agents/abomasnow_agent.py) with four unrelated cards (Mega Signal, Maximum
  Belt, Cyrano, Waitress) that receive no special-case scoring at all -- see
  results/abomasnow_deck_audit.md. Hypothesis: restoring the notebook-faithful
  decklist (decks/abomasnow_ex_corrected_v1.csv) improves Abomasnow ex's measured
  win rate, since three purpose-built scoring branches would go from dead code to
  active and four cards would go from "scored by irrelevant generic default" to
  "scored by their actual (Carmine/Ultra Ball/Surfing Beach) logic."
Change: new file decks/abomasnow_ex_corrected_v1.csv (60 cards, built directly from
  the notebook's named-constant/comment counts). src/agents/abomasnow_agent.py
  UNCHANGED. decks/abomasnow_ex.csv UNCHANGED (kept for reproducibility of the
  FIRST REPORT numbers).
Baseline: decks/abomasnow_ex.csv (agent_a_slot alternated), from the FIRST REPORT's
  1200-game benchmark: vs random_agent 91.5% (183/200), vs iono_agent 18.5%
  (37/200), vs dragapult_agent 44.0% (88/200).
Opponent: random_agent, dragapult_agent, iono_agent (unchanged agent code/decks).
Games: 300 per opponent (900 total) for the corrected deck, vs. the existing 200
  per opponent for the current deck (raw data preserved from session 1, not rerun).
Result (two-proportion z-test, current n=200 vs corrected n=300):
  vs random_agent:    current 91.50% [87.6%,95.4%] -> corrected 94.67% [92.1%,97.2%]  z=1.40
  vs iono_agent:       current 18.50% [13.1%,23.9%] -> corrected 20.00% [15.5%,24.5%]  z=0.42
  vs dragapult_agent:  current 44.00% [37.1%,50.9%] -> corrected 46.33% [40.7%,52.0%]  z=0.51
Confidence: all three |z| < 1.96 (not significant at p<0.05); every CI overlaps
  heavily with the corresponding current-deck CI. The direction is consistently
  positive (small win-rate increase in all 3 matchups) but this sample cannot
  distinguish that from noise.
Runtime: 900 games in well under a minute (native engine, consistent with prior
  benchmarks).
Conclusion: the deck-vs-notebook mismatch is real and confirmed (results/
  abomasnow_deck_audit.md), and fixing it makes 3 of the agent's card-specific
  scoring branches live instead of dead code -- but at this sample size it has NOT
  been shown to be the cause of Abomasnow's comparatively weak measured win rate
  (especially the ~18-20% vs Iono's). The weakness persists in both decks. This
  should be re-checked with the larger Phase 8 benchmark, where tighter CIs might
  resolve the small positive trend seen here.
Keep/Revert: KEEP as the new default deck going forward
  (decks/abomasnow_ex_corrected_v1.csv becomes BEST_ABOMASNOW_DECK) on fidelity
  grounds -- it is what the official example actually intends and removes an
  unexplained, undocumented deviation -- not on demonstrated win-rate grounds.
  decks/abomasnow_ex.csv is preserved unmodified for reproducibility of session-1
  results, never deleted.
```
