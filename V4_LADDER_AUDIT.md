# V4 Defensive — Real Kaggle Ladder Behavioral Audit vs V2 Balanced

**Date**: 2026-08-13. **Scope**: data comparison only, not strategy redesign. Compare V2 and V4
on their real Kaggle ladder results, identify what changed in V4's behavioral metrics, and
identify which metrics correlate with V4's losses. **No agent/deck/policy/submission changes
made. No code changes proposed.** This is a checkpoint for review.

Every claim is tagged **[FACT]**, **[HYPOTHESIS]**, or **[GAP]**, per this project's standing
process rule.

---

## 0. First finding: V4 has real ladder data that wasn't in the project's records yet

**[FACT]** Two Kaggle submissions exist for V4 Defensive's identical build (same
`fileName=challenger_v4_20260812T053037Z.tar.gz`, same `totalBytes=2028232`):

| Submission ID | Submitted (UTC) | Public score | Real ladder games |
|---|---|---|---|
| 55449825 | 2026-08-12 05:31:16Z | 600.0 (never moved) | **0** (only the self-play validation episode — same "superseded before matchmaking" pattern already found for V2's first submission) |
| **55471848** | 2026-08-13 02:18:12Z | 739.7 | **17** real `EPISODE_TYPE_PUBLIC` games (+1 validation) |

`memory/project_ptcg_status.md` and `results/agent/submission_registry.csv` only knew about
55449825 (0 games) — this resubmission (55471848) happened after the last session and had not
been pulled or analyzed before this task. Verified directly via `competition_submissions`
before committing to it, matching the same "use the one that actually has data" reasoning
already applied to V2. New tooling: `tools/pull_v4_ladder_data.py`,
`tools/build_v4_ladder_behavior_audit.py`, `tools/build_v2_v4_case_analysis.py` (reuses the
identical `src/meta_analysis/ladder_behavior_audit.py` parser and
`tools/build_ladder_audit_case_analysis.py` Part-C logic already validated on Luca/V2 — no
forked methodology). Raw data: `data/v4_ladder_audit/` (gitignored). Structured outputs:
`results/ladder_behavior_audit/v4_{games,decisions,missed_knockouts,loss_analysis,
stayed_critical_outcomes}.csv`, `v2_v4_both_summaries.json`.

**[FACT]** V4's 17 real games ran 2026-08-13T02:19Z–03:19Z (~1 hour, all in one burst).
**[FACT]** Both V2 and V4 play the **exact same 60-card decklist** (`deck_own_hash` =
`59138a345c6b933a` for both) — only the policy weight profile differs (BALANCED vs DEFENSIVE,
per `reports/agent_v2_v5_experiments.md` §4). Unlike the Luca comparison, **deck mechanics are
not a confound here** — this is a clean same-deck, same-engine, weights-only comparison.

---

## 1. Headline comparison

| Metric | V2 (n=43) | V4 (n=17) | Note |
|---|---:|---:|---|
| Win rate | 62.8% (27-16), Wilson CI [47.9%, 75.6%] | **41.2%** (7-10), CI [21.6%, 64.0%] | CIs overlap — not fully statistically separated at this n |
| Win rate, first | 61.3% (19/31), CI [43.8%, 76.3%] | 53.8% (7/13), CI [29.1%, 76.8%] | Similar, both CIs wide |
| Win rate, second | 66.7% (8/12), CI [39.1%, 86.2%] | **0.0%** (0/4), CI [0.0%, 49.0%] | See §3 — small n, but a real, stark directional gap |
| Avg game length (turns) | 12.51 | 10.06 | V4's games run ~2.5 turns shorter |
| KO success rate per attack | 68.9% (104/151), CI [61.1%, 75.7%] | 68.9% (33/48), CI [54.7%, 80.1%] | **Essentially identical** — expected, since KO conversion is dominated by deck mechanics (Phantom Dive hits the bench, not the active — see `V2_LADDER_AUDIT.md` §9), which is unchanged between V2 and V4 |
| 2+ prize deficit | 44.2% of games | 52.9% of games | V4 slightly worse, CIs would overlap heavily at n=17 |
| Avg peak deficit faced | 1.51 prizes | 1.88 prizes | Same direction |
| Retreat rate (per decision) | 1.81% | 1.47% | **V4 retreats LESS**, not more — see §4 |
| Retreat rate when legal | 4.98% | 4.33% | Same direction, roughly equal |
| Retreat in critical situations (A∧B∧C∧D∧E) | 3.3% (3/90), CI [1.1%, 9.3%] | **0.0%** (0/77), CI [0%, 4.8%] | See §4 |
| Mean opponent current rating | **617.8** | **763.3** | **The single largest confound — see §2** |
| Comeback rate from 2+ deficit | 42.1% (8/19) | 22.2% (2/9) | V4 lower |

---

## 2. The dominant confound: V4's opponent pool is far stronger

**[FACT, HIGH confidence]** V4's 17 opponents currently average rating **763.3** (median 804.1)
vs V2's 43 opponents at **617.8** (median 623.6) — a **~145-point gap**. V4's per-game opponent
scores ranged from 351.4 to 1009.9, with 12 of 17 opponents rated above 700 (V2 faced only 8 of
43 opponents above 700). This is the same structural limitation already documented in
`V2_LADDER_AUDIT.md` §9 (opponent ratings are current snapshots, not ratings at match time), but
the gap here is larger and in the opposite direction of what V4's lower win rate might suggest —
V4 is losing more *against tougher opponents*, not against equivalent ones.

**[FACT]** Despite a 41.2% win rate (worse than a coin flip), V4's rating **rose** from 600.0 to
739.7 over these 17 games — it beat several very high-rated opponents (906.5, 1009.9, 910.2,
776.8, 675.6 among its 7 wins) while most losses came against opponents in the 700-970 range,
plus one outlier loss to a 351.4-rated opponent. **[HYPOTHESIS]**: this pattern (net rating gain
despite a sub-50% raw win rate) is consistent with a Bayesian/Elo-style system crediting upsets
over strong opponents more than it penalizes losses to strong opponents — not confirmed against
the engine's actual rating-update formula this session, just the directionally-consistent
explanation for an otherwise-counterintuitive number.

**Within-agent correlation of opponent rating with winning** (point-biserial r, win=1/loss=0):
V2 r=-0.232 (n=43), V4 r=-0.067 (n=17) — weak in both, essentially negligible for V4. **This
means V4's losses are not simply "V4 loses to the highest-rated opponents it faces and wins
against the weaker ones"** — the loss pattern doesn't track opponent rating cleanly even though
the *overall pool* V4 faced was much tougher than V2's.

---

## 3. Going-second win rate: the most distinctive real V4 vs V2 gap

**[FACT, LOW-MEDIUM confidence — n=4]** V4 lost **all 4** of its real games played going second
(0/4, Wilson CI [0%, 49.0%]), while going first it won 53.8% (7/13) — roughly in line with V2's
own first-player rate (61.3%). V2, by contrast, won 66.7% going second (8/12) — its *better*
side, not its worse one. These 4 losses account for 40% of V4's 10 total losses.

**[HYPOTHESIS, not confirmed]**: this could be a real second-player weakness introduced by V4's
weight profile (`prize_value_multiplier=0.75`, `defensive_retreat_enabled` at the looser
`hp_fraction=0.6`, `preservation_bias=0.3`, `switch_risk_tolerance=0.6` — see
`reports/agent_v2_v5_experiments.md` §4), or it could be n=4 noise compounded by 3 of those 4
opponents being rated 849.5/858.5/966.4 (well above V4's own pool average). **Cannot be
separated with this data** — the sample is too small and too confounded by opponent strength to
support a causal claim either way. Flagged as the most concrete, specific follow-up question
this audit raises, not as a finding.

---

## 4. Retreat behavior: V4 (the "Defensive" profile) does not actually retreat more in real games

**[FACT]** V4's real-ladder retreat rate is **lower** than V2's on every cut measured:
overall (1.47% vs 1.81%), when legally available (4.33% vs 4.98%), and — most notably — in
"critical situations" (all of: 2+-prize active, damaged, opponent lethal *now*, retreat legal,
bench target exists): V4 retreated **0 times out of 77** such situations (CI [0%, 4.8%]) vs
V2's 3/90 (3.3%, CI [1.1%, 9.3%]).

This directly replicates a finding already flagged locally in `reports/
agent_v2_v5_experiments.md` §4 ("switching frequency was **not** dramatically higher than V1's
despite the more permissive `hp_fraction=0.6` trigger... most of V4's behavioral difference...
comes from `prize_value_multiplier`/`preservation_bias` reshaping *other* decisions, not from
retreating more often per se") — that local, 150-game finding is now **confirmed on real ladder
data**: V4's proactive-retreat hook (triggered at a *likely* 60%-HP hit, a looser bar than V2's
*guaranteed*-lethal-only trigger) still doesn't translate into more actual retreats. **[GAP]**:
the "critical situation" gate used here requires `opp_lethal_now` (a certain KO), which is a
narrower condition than V4's own 60%-HP-hit trigger — so it's possible V4's hook fires in
non-lethal-but-heavy-hit situations this specific cut doesn't capture. But the *overall* retreat
rate (1.47% vs 1.81%) is also lower, which that explanation can't account for — the more direct
read is that the hook simply doesn't activate often against real opponents' actual attack
profiles, consistent with the local finding.

**[FACT, n=1, same pattern as the V2/Luca report]**: V4 has exactly one "stayed in a critical
situation → confirmed knocked out on the very next decision" event across its 17 games (vs 0/90
for V2 in the earlier audit) — retreat cost 1.0, energy loss if retreated would have been 1.0,
1 ready bench attacker existed, opponent's best attack was 200 damage, game result: LOSS. With
n=1, **no general conclusion can be drawn** — reported because it exists, per this project's
"never fabricate confidence from n=1" rule, same caveat as the Luca audit's own n=1 case.

---

## 5. Correlation analysis: what predicts a V4 loss (within V4's own 17 games)

Point-biserial correlation (win=1, loss=0) between each metric and game result, per agent:

| Metric | V2 r (n=43/41) | V4 r (n=17/15) |
|---|---:|---:|
| KOs landed (count) | +0.594 | **+0.587** |
| Final prize margin (+ = behind) | -0.586 | **-0.775** |
| Max prize deficit faced | -0.358 | **-0.535** |
| Turn-level attack rate | +0.507 | +0.313 |
| KO rate per attack | +0.439 | +0.485 |
| Attacks thrown (count) | +0.382 | +0.451 |
| Opponent current rating | -0.232 | -0.067 |
| Game length (turns) | +0.066 | +0.229 |
| Retreats chosen (count) | -0.060 | +0.202 |

**[FACT, MEDIUM confidence given n=17]** The strongest correlates of a V4 loss are **prize-race
metrics**, not behavioral-policy metrics: final prize margin (r=-0.775) and max prize deficit
faced (r=-0.535) dominate, essentially the same ranking as V2. KOs landed and KO rate per attack
correlate similarly for both agents (~0.44-0.59) — **not a V4-specific pattern**, just "landing
knockouts predicts winning," true for both. Retreat count is weakly *positive* for V4 (r=+0.202,
opposite of the "under-retreating causes losses" hypothesis) and near-zero for V2 — **neither
agent shows retreat frequency as a loss predictor**, consistent with `V2_LADDER_AUDIT.md`'s own
conclusion that this specific mechanism ("stay in danger → get punished") essentially never
fires for either agent.

**[FACT]** V4's losses are, on average, **shorter games than its wins** (9.4 vs 11.0 turns) —
several losses ended in 5-7 turns (vs a 351.4-rated opponent, and two ~800-rated opponents).
V2's losses and wins are nearly the same length (12.19 vs 12.70). **[HYPOTHESIS]**: V4's losses
look more like fast, decisive defeats than slow bleeds — worth checking against the "slower,
Stage-2 Dragapult ex development" explanation from `V2_LADDER_AUDIT.md` §9 (a deck that's slow
to power up should be especially vulnerable to being run over before it gets going), though this
can't be confirmed from win/loss timing alone at n=10 losses.

**[FACT]** Opponent-archetype breakdown of V4's losses (n=10, too small for per-archetype rates):
Marnie's Grimmsnarl ex 2W-3L, Fezandipiti ex 2W-1L, Dragapult ex mirror 1W-1L, UNLABELED 0W-2L,
Mega Kangaskhan ex/Mega Lopunny ex/Mega Lucario ex each 0W-1L, Team Rocket's Mewtwo ex 1W-0L,
Teal Mask Ogerpon ex 1W-0L. No single archetype stands out as a hard V4-specific counter at this
n — the meta's #1 deck (Grimmsnarl) is a losing matchup for both V2 (4-4) and V4 (2-3), same
direction, not a new finding.

---

## 6. What did NOT change between V2 and V4

**[FACT, HIGH confidence]** KO conversion per attack is **statistically indistinguishable**
between V2 (68.9%, CI [61.1%,75.7%]) and V4 (68.9%, CI [54.7%,80.1%]) — expected, since this is
overwhelmingly a deck-mechanics effect (Dragapult ex's own strongest attack, Phantom Dive, hits
the opponent's bench rather than their active — established in `V2_LADDER_AUDIT.md` §9) and the
deck is byte-identical between the two versions. This rules out "V4's policy changes made attack
targeting worse" as an explanation for anything in this report.

**[FACT]** First-player win rates are similar (61.3% V2 vs 53.8% V4, CIs overlap heavily) — the
first-player side is not where these two versions differ.

---

## 7. Limitations

- **n=17 for V4 is small** — smaller than V2's already-modest n=43, and much smaller than
  Luca's n=69. Every V4-specific number above should be treated as preliminary, per this
  project's standing rule never to call a small/first run conclusive.
- **Opponent-pool strength is a large, uncontrolled confound** (§2) — V4's raw win rate cannot
  be compared to V2's raw win rate as a policy-quality signal without adjusting for the ~145-point
  opponent-rating gap, which this data source cannot do reliably (per the project's own
  established rating-resolution limitation, `memory/project_ptcg_status.md` session 5).
- **All 17 V4 games happened in a single ~1-hour burst** the day after V2's data (2026-08-13 vs
  V2's 2026-08-12) — the real ladder meta could have shifted slightly between the two pulls
  (the project's own meta-analysis found week-over-week archetype-share drift is real and
  sometimes large), an additional confound on top of opponent rating.
- **Second-player win rate (§3) is the most interesting single number in this report and the
  least trustworthy (n=4)** — flagged prominently rather than either ignored or overstated.
- **No causal mechanism is established for V4's lower win rate.** The data supports "V4 faced
  tougher opponents and lost more" and "V4's proactive-retreat hook doesn't fire more than V2's
  in practice" as facts; it does not support "V4's weight changes caused the lower win rate" as
  opposed to "opponent-pool variance caused it" — these are not separable with 17 games against
  17 unique real opponents.

---

## 8. Summary

V2 and V4 run the identical deck, so this comparison (unlike the Luca audit) isolates
policy-weight effects from deck mechanics. On real ladder data: V4's win rate (41.2%, n=17) is
numerically lower than V2's (62.8%, n=43) but the CIs overlap and V4 faced a real-ladder
opponent pool averaging ~145 rating points stronger — the single largest confound in this report.
KO conversion is unchanged (as expected, deck-driven). V4's proactive-retreat weight change does
not show up as more actual retreats in real games, replicating a local-benchmark finding from
`reports/agent_v2_v5_experiments.md`. The most distinctive, if smallest-sample, real behavioral
difference is V4's 0/4 record going second vs V2's 8/12 — flagged as the most concrete follow-up
question, not a conclusion. Prize-race metrics (final margin, max deficit, KOs landed) are the
strongest correlates of winning for both agents, with no V4-specific behavioral metric emerging
as a distinct loss driver beyond what already predicts V2's losses.

**No code changes proposed.** This is the data-comparison checkpoint requested; the next
decision is the user's.
