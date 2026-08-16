# Statistical Summary — Competitive V1

All CIs are Wald 95% intervals on a single proportion; comparisons use a
two-proportion pooled z-test (`tools/stats.py`). "Significant" means |z| > 1.96
(≈p<0.05, two-tailed) — treated as "likely real", not proof; everything here is
still a local-only, small-to-moderate-sample result (see the caveats in
[[feedback-ptcg-process]]: never call these statistically conclusive on their own,
and never generalize from local agent-vs-agent play to the real Kaggle ladder meta).

## Phase 1/2 — Dragapult ex first vs. second player (forced-coinflip experiment)

n=1000 per condition per opponent (see `results/dragapult_first_second_analysis.md`
for full methodology and mechanism).

| Opponent | First win rate [95% CI] | Second win rate [95% CI] | z | Verdict |
|---|---|---|---|---|
| random_agent | 98.10% [97.2%,99.0%] | 96.70% [95.6%,97.8%] | -1.97 | borderline (p≈0.049) |
| abomasnow_agent | 67.10% [64.2%,70.0%] | 56.30% [53.2%,59.4%] | -4.97 | **significant, large gap** |
| iono_agent | 67.30% [64.4%,70.2%] | 63.70% [60.7%,66.7%] | -1.69 | not significant (p≈0.09) |

Consistent direction in all three (first > second), strongest and clearest vs.
Abomasnow.

## Phase 5 — Abomasnow deck fix (current vs. notebook-faithful decklist)

Current deck n=200 (session-1 data), corrected deck n=300 (this session). See
`experiments/abomasnow_deck_fix.md`.

| Opponent | Current [95% CI] | Corrected [95% CI] | z | Verdict |
|---|---|---|---|---|
| random_agent | 91.50% [87.6%,95.4%] | 94.67% [92.1%,97.2%] | 1.40 | not significant |
| iono_agent | 18.50% [13.1%,23.9%] | 20.00% [15.5%,24.5%] | 0.42 | not significant |
| dragapult_agent | 44.00% [37.1%,50.9%] | 46.33% [40.7%,52.0%] | 0.51 | not significant |

Direction consistently positive but not distinguishable from noise at this sample
size — deck correction adopted on fidelity grounds (see audit doc), not
demonstrated win-rate grounds.

## Phase 4 — Dragapult "always go first" variant vs. BEST_DRAGAPULT_AGENT

See `experiments/dragapult_first_variant.md`. Pooled across 4 opponents (n=900
BEST vs n=2000 variant): 65.67% -> 66.65%, z=0.52, not significant on its own;
directionally consistent with Phase 1's higher-powered controlled result.
Promoted to `dragapult_fix_v1` on the strength of Phase 1's evidence.

## Phase 7-10 — Full 5-agent formal matrix

See `results/formal_matrix_v1/README.md` for the full matrix, first/second
splits, and terminal-reason breakdown. Headline: `dragapult_fix_v1` and
`lucario_ex_agent` are statistically tied for best (z=-0.78 aggregate, z=-1.77
head-to-head, neither significant); both significantly beat `iono_agent`
(z=-6.68, z=-7.46); `iono_agent` significantly beats `abomasnow_corrected`
(z=-3.96); `abomasnow_corrected` is the weakest of the four (loses to all three
others significantly).

## Phase 12/13 — Search-augmented agent vs. best heuristic

See `experiments/search_1ply.md`. dragapult_fix_v1 alone vs. +1-ply search,
n=500/opponent/condition:

| Opponent | Heuristic-only | + search | z | Verdict |
|---|---|---|---|---|
| abomasnow_corrected | 56.60% | 47.40% | -2.91 | significant, worse |
| iono_agent | 66.60% | 29.80% | -11.64 | significant, much worse |
| lucario_ex_agent | 48.80% | 37.00% | -3.77 | significant, worse |
| pooled | 57.33% | 38.07% | -10.56 | significant, worse |

Large, consistent, statistically overwhelming regression — traced (HYPOTHESIS,
not independently isolated) to a state-integration bug where overriding
Dragapult's attack choice leaves its own module-global KO-planning state
(`plan_b.counter`, used by the very next damage-counter-placement decision)
stale/mismatched. Not evidence against the Search API itself (§4.2 of the
report: cheap, reliable, zero crashes) — see `reports/competitive_v1.md` §4.3.
