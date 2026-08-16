# Kaggle Ladder ~50 Games Deep Analysis

**Phase type**: read-only forensic analysis. No agent, deck, policy, or submission changes were made during this phase. Report date: 2026-08-12. Competition Simulation-track deadline: 2026-08-16 23:59 UTC (4 days from this report).

Claim tags used throughout: **[FACT]** = directly read from Kaggle API data or repo files, **[MEASURED]** = computed directly from the pulled data, **[HYPOTHESIS]** = a plausible but unconfirmed explanation, **[LIMITATION]** = something the available data cannot answer.

---

## 1. Executive summary

**[FACT]** The production submission (`submission/final_submission.tar.gz`, Kaggle submission id `55437549`) has played **46 real ladder games** (plus 1 platform self-play validation episode, excluded from all win/loss statistics) and sits at a current public score (rating) of **726.9**, up from the documented starting value of 600.

**[MEASURED]** Record: **24 wins / 22 losses / 0 draws**, win rate **52.2%**, Wilson 95% CI **[38.1%, 65.9%]**. A binomial test against H0: win rate = 50% gives **p = 0.883** — the observed record is statistically indistinguishable from a coin flip at this sample size. The +126.9 rating gain is real, but it is not backed by a win rate the data can currently distinguish from 50%; see Section 13-14 for why a Bayesian rating can still move substantially under these conditions.

**[FACT]/[CONFIRMED]** The agent ran cleanly: 0 non-`DONE` episode statuses, 0 non-empty stderr entries across 4,151 logged decision calls, 0 decision calls anywhere near the 2.0s per-decision or 600s match budgets (max observed decision time: 0.204s), and the exact committed `decks/dragapult_ex.csv` deck was played, hash-verified, in all 47 episodes. No crashes, no deck mismatches, no evidence of the timeout shield or safety wrapper's fallback path ever being needed to avoid a bad outcome — though see Section 10/15 for the important caveat that those two layers' own internal counters are never logged, so their fallback rate specifically cannot be measured, only bounded indirectly.

**[CONFIRMED, new this phase]** The Going First override behaves exactly as documented, but with a real, previously-untested-live mechanical nuance: on this engine, only ONE player per match is ever asked "go first?" (`docs/environment.md`), and this phase's data shows cleanly that our submission's agents-list slot determines which side that is. When we hold slot 0 (29/46 games), we go first **100%** of the time (29/29) — the override fires every time it is asked. When we hold slot 1 (17/46 games), the *opponent* is asked instead, and we only end up first when they choose to go second (5/17 = 29.4%). This is not a bug; it fully explains why our overall first-rate is 73.9% rather than 100%, and it is the first real-Kaggle confirmation of a mechanic previously only inferred from engine source.

**Recommendation: B — MONITOR; NO CHANGE YET** (Section 17).

---

## 2. Exact submission identification

**[FACT]**, resolved live via `KaggleApi.competition_submissions('pokemon-tcg-ai-battle')` — not assumed or hardcoded:

| Field | Value |
|---|---|
| Submission ID | `55437549` |
| File name | `final_submission.tar.gz` |
| Created | 2026-08-11T16:27:32.717Z |
| Status | COMPLETE |
| Public score (current rating) | **726.9** |
| Private score | not available (this competition has no Private Leaderboard, per prior-session Kaggle API metadata) |
| Frozen | True |
| Team | Serguei Makarov |
| Bytes | 2,016,943 |

**[FACT]** The immediately-preceding submission attempt, `55437291` (created 2026-08-11T16:15:15.407Z), has status **ERROR**, error description `"Validation Episode failed."`, and **0 games/rating impact** — this is the pre-hotfix archive from session 14 that failed on the `__file__`/`exec()` issue documented in `reports/kaggle_runtime_hotfix_v1.md` (session 15). It never went live and is excluded from all analysis here; it is direct external confirmation that the session-15 hotfix was the one that actually shipped.

**[FACT]** Leaderboard position: not resolved this phase — `competition_leaderboard_view` requires enumerating the full leaderboard and searching for the team; spot-checked the top of the leaderboard (`competition_leaderboard_download`) and confirmed the endpoint works and returns `{team_name, score, submission_date}` tuples (top score observed: 1244.2), but a full rank lookup for team "Serguei Makarov" specifically was not completed this phase (out of scope relative to the phase's own priorities; can be added on request).

---

## 3. Available Kaggle game/episode data

**[FACT]**, tested directly against the live API rather than assumed:

| Data type | Available? | Source |
|---|---|---|
| Game/episode history | YES | `competition_list_episodes(submission_id)` |
| Match results (W/L/D) | YES | `episode.agents[].reward`, cross-checked against `replay.rewards` |
| Opponent names | YES | `episode.agents[].teamName` / replay `info.TeamNames` |
| Opponent ratings | **NO** | not exposed by any endpoint tested this phase |
| Timestamps | YES | `episode.createTime` / `endTime` |
| Rewards | YES | `-1/0/1` per side |
| Win/loss/draw | YES | derived from reward pair |
| Game IDs | YES | numeric `episode.id` |
| Full game logs (turn-by-turn state/action) | YES | `competition_episode_replay(episode_id)` — full `kaggle_environments` replay JSON, ~4-5MB/episode |
| Our own agent stdout/stderr + per-call duration | YES | `competition_episode_agent_logs(episode_id, our_agent_index)` |
| **Opponent** agent stdout/stderr/duration | **NO — 403 Forbidden**, confirmed by direct API call, not assumed | |
| Action traces | YES (ours and opponent's, both sides are visible in the replay) | replay `steps[i][player].action` |
| Observation traces | YES (agent-visible fields; opponent-hidden fields are also present in the replay's spectator-only `visualize` block, used here only for offline archetype analysis, never fed back into the live agent) | replay `steps[i][player].observation` |
| Deck information | YES, exact 60-card list, both sides, hash-verified two independent ways (first 60-card action + `visualize.deck`) | |
| First/second information | YES, via `observation.current.firstPlayer` | |
| **Per-game rating before/after** | **NO** | not exposed by any tested endpoint — see Limitations |

Also confirmed: `competition_list_episodes` accepts a submission ID and returns **every** episode for that submission, including the platform's own pre-matchmaking **validation** episode (`type: EPISODE_TYPE_VALIDATION`) alongside the 46 real ladder games (`type: EPISODE_TYPE_PUBLIC`) — a distinction not previously known to this project and important not to silently merge (see Section 4).

---

## 4. Game-level dataset

Built: `results/agent/kaggle_ladder_games.csv` (46 rows, one per real ladder game; the validation self-play episode is deliberately excluded from this file and reported separately). Columns beyond the prompt's minimum schema were added where the data supported it (opponent archetype tag, deck hash, decision-latency percentiles, etc.) — see the CSV header for the full column list. Fields genuinely unavailable from the API are literal `NA`/`None`, never inferred:

- `our_rating_before` / `our_rating_after` — NA for every row (Kaggle exposes only the submission's *current* score, not a per-game history)
- `opponent_rating` — NA for every row
- `invalid_actions`, `timeouts`, `fallback_count`, `safety_interventions` — NA for every row, with a documented reason (Section 10): these are in-process counters inside `safety_wrapper.py`/`timeout_shield.py` that are **never printed or persisted**, so Kaggle's exposed stdout/stderr logs cannot recover them even in principle. This is stated as a limitation, not silently worked around.

Also produced (not in the original required list, built because the data supported it and it materially improves matchup resolution): `opponent_matchup_key`, which is the known archetype label where `archetype_signatures.py`'s 12-name signature matcher finds one, and otherwise the deterministic "headline-Pokemon signature" (`deck_clustering.py`'s method, applied per-deck since this sample is too small to build a multi-game registry) — this cuts the raw 41% `UNLABELED` rate down by giving named clusters like `UNLABELED[Abra, Alakazam, Dudunsparce, Dunsparce, Kadabra]` and `UNLABELED[Archaludon ex]`, both of which independently reproduce archetype families first identified in Phase 4.1 (session 4) from a much larger historical dataset — a cross-validation of that earlier finding, not a new discovery.

---

## 5. Aggregate result statistics

**[MEASURED]**, all from `kaggle_ladder_games.csv`:

| Metric | Value |
|---|---|
| Total games | 46 |
| Wins | 24 |
| Losses | 22 |
| Draws | 0 |
| Win rate | 52.17% |
| Loss rate | 47.83% |
| Draw rate | 0.00% |
| Current rating | 726.9 |
| Rating change from 600 | **+126.9** |
| Average / median opponent rating | **NA** (not exposed) |
| Opponent rating range | **NA** |
| Unique opponents | 45 of 46 (one rematch: "Toru59er", games 44 and 45 back-to-back, both losses — see Section 10.H) |

**Results by first/second**: see Section 8. **Results by game length**: see Section 9. **Results by opponent**: see Section 7 (matchup table) — with only 45 unique opponents across 46 games, "by individual opponent" is nearly the same as "by game," so the archetype-level matchup table is the more informative cut.

**Cumulative win rate by game number** — full table in `results/agent/kaggle_rating_trajectory.csv`; headline shape **[MEASURED]**: opened 1/1 (100%), dipped to a low of 4/11 (36.4%) around game 11, climbed to a local high of 14/21 (66.7%) around game 21, then drifted back down to settle at 24/46 (52.2%) by game 46. This kind of wander is exactly what a ~50%-true-rate binomial process produces by chance over 46 trials (a 3-day-old real ladder score wandering in a corridor roughly matching the pooled Wilson CI) — see Section 6/13 for why this should not be read as "the agent got worse," and Section 13 for why it also should not be read as evidence of a stable >50% rate.

---

## 6. Rating trajectory

Built: `results/agent/kaggle_rating_trajectory.csv`.

**[LIMITATION]** This is the single biggest data-availability gap in this phase: Kaggle's API exposes only the submission's **current** aggregate score, not a historical per-game or per-day snapshot. The CSV therefore has real values in exactly two cells — `rating_before` = 600 (game 1, documented mu0 default, verified via Kaggle API competition metadata in session 3) and `rating_after` = 726.9 (game 46, the live current public score) — and `NA` everywhere else. **No per-game rating delta, no "largest positive/negative movement," and no assessment of whether the rating is "stabilizing" can be computed from this data source.** This should not be read as "the rating is flat" or "the rating is volatile" — it is genuinely unknown between the two endpoints.

What CAN be said: starting rating 600 [FACT], current rating 726.9 [FACT], net change +126.9 [MEASURED], both are single confirmed data points, not a trajectory. Section 14 discusses what is and is not inferable about *why* the rating moved this much given only these two points plus the 52.2% observed win rate.

---

## 7. Matchup analysis

Full table (also in the game-level CSV via `opponent_matchup_key`), Wilson 95% CIs, credibility gate reused from Phase 4.2 (`games >= 20 AND wilson_lo > 50%` = `STATISTICALLY_CREDIBLE`; `games >= 5` = `OBSERVED_ONLY_SMALL_N`; else `INSUFFICIENT_SAMPLE`):

| Opponent (matchup key) | Games | Wins | Losses | Win Rate | Wilson 95% CI | Credibility |
|---|---:|---:|---:|---:|---|---|
| Fezandipiti ex | 8 | 2 | 6 | 25.0% | [7.1%, 59.1%] | OBSERVED_ONLY_SMALL_N |
| UNLABELED[Abra, Alakazam, Dudunsparce, Dunsparce, Kadabra] | 8 | 4 | 4 | 50.0% | [21.5%, 78.5%] | OBSERVED_ONLY_SMALL_N |
| UNLABELED[Archaludon ex] | 7 | 3 | 4 | 42.9% | [15.8%, 75.0%] | OBSERVED_ONLY_SMALL_N |
| Dragapult ex (mirror) | 6 | 4 | 2 | 66.7% | [30.0%, 90.3%] | OBSERVED_ONLY_SMALL_N |
| Marnie's Grimmsnarl ex | 6 | 3 | 3 | 50.0% | [18.8%, 81.2%] | OBSERVED_ONLY_SMALL_N |
| Mega Lucario ex | 3 | 3 | 0 | 100.0% | [43.8%, 100%] | INSUFFICIENT_SAMPLE |
| Iono's (Bellibolt/Voltorb) | 1 | 1 | 0 | 100.0% | — | INSUFFICIENT_SAMPLE |
| Mega Kangaskhan ex | 1 | 0 | 1 | 0.0% | — | INSUFFICIENT_SAMPLE |
| Team Rocket's Kangaskhan ex | 1 | 1 | 0 | 100.0% | — | INSUFFICIENT_SAMPLE |
| Team Rocket's Mewtwo ex (mirror) | 1 | 1 | 0 | 100.0% | — | INSUFFICIENT_SAMPLE |
| UNLABELED[Crustle, Dwebble, Great Tusk, Terrakion] | 1 | 1 | 0 | 100.0% | — | INSUFFICIENT_SAMPLE |
| UNLABELED[Crustle, Dwebble] | 1 | 0 | 1 | 0.0% | — | INSUFFICIENT_SAMPLE |
| UNLABELED[Mega Froslass ex, Mega Starmie ex] | 1 | 0 | 1 | 0.0% | — | INSUFFICIENT_SAMPLE |
| UNLABELED[Mega Starmie ex] | 1 | 1 | 0 | 100.0% | — | INSUFFICIENT_SAMPLE |

**No matchup clears the `STATISTICALLY_CREDIBLE` bar** — the largest sample against any single archetype is 8 games. **[OBSERVED, not credible]** The weakest point estimate is Fezandipiti ex at 25% (2/8), which is directionally the *opposite* of the offline evidence (`Dragapult ex > Fezandipiti ex`, 64.5% at n=76, USABLE-tier per Phase 4.2/4.6) — but the Wilson CI [7%, 59%] on this 8-game sample comfortably contains that offline 64.5% figure, so this is fully consistent with sampling noise on a small sample, **not** evidence the offline counter finding was wrong. Per the phase's explicit instruction, **no strategic change is warranted from n=8** or any other cell in this table.

---

## 8. Going First / Second analysis

| Condition | Games | Wins | Win Rate | Wilson 95% CI |
|---|---:|---:|---:|---|
| Going First | 34 | 17 | 50.0% | [34.1%, 65.9%] |
| Going Second | 12 | 7 | 58.3% | [32.0%, 80.7%] |

Difference: +8.3pp in favor of going second (opposite sign from the offline-validated effect), two-proportion z = -0.497, **p = 0.619 — not significant**, and the CI on the difference is wide given n=12 for "going second." **This does not contradict the offline evidence** (a controlled 1000-games/condition local experiment found going-first significantly better vs. Abomasnow specifically, +10.8pp, and the real-ladder archetype-level re-analysis from session 14 found Dragapult ex's own pooled first-advantage on the wider meta dataset was **not** statistically credible either: 59.1% first vs 52.5% second, n=137/200, CI crosses 0). The 46-game live sample here is simply too small and too imbalanced (34 vs 12) to add or subtract confidence either way.

**[CONFIRMED, new finding]** — see Executive Summary and Section 15: the override's *effective* first-rate depends entirely on which agents-list slot Kaggle assigns us. Cross-tab:

| Our slot index | Games | Went first | First rate |
|---|---:|---:|---:|
| 0 (we are asked) | 29 | 29 | **100.0%** |
| 1 (opponent is asked) | 17 | 5 | 29.4% |

This mechanically explains the 34/46 = 73.9% overall first-rate and is a clean, exact confirmation that `dragapult_agent_always_first`'s single `IS_FIRST` override fires correctly and unconditionally every time it is actually offered the choice — 29/29, zero misses.

---

## 9. Game-length analysis

Data-driven terciles on `turns` (33rd/67th percentile = 13/14 turns — the distribution is heavily clustered around 13, so the buckets are close together):

| Bucket | Games | Wins | Win Rate | Wilson 95% CI | Avg turns | Avg decisions |
|---|---:|---:|---:|---|---:|---:|
| SHORT (≤13 turns) | 27 | 12 | 44.4% | [27.6%, 62.7%] | 11.1 | 75.7 |
| MEDIUM (14 turns) | 7 | 6 | 85.7% | [48.7%, 97.4%] | 14.0 | 104.6 |
| LONG (>14 turns) | 12 | 6 | 50.0% | [25.4%, 74.6%] | 19.2 | 114.5 |

**[OBSERVED, not statistically credible]** MEDIUM-length games have a notably higher point-estimate win rate, but n=7 with a CI spanning [49%, 97%] is too wide to treat as a real effect, and there is no obvious mechanism proposed for why exactly-14-turn games specifically would be favorable — flagged as a pattern to watch at larger sample size, not a finding. SHORT and LONG games are statistically indistinguishable from each other and from 50%.

---

## 10. Agent behavior analysis from logs

**A. Going First** — [CONFIRMED]: fires 29/29 times when actually offered the choice (Section 8). No deviation from the intended always-yes policy was found in any of the 46 games' `IS_FIRST`-context decisions inspected via the replay's `select.context` field.

**B. Safety wrapper** — **[LIMITATION]**: `safety_wrapper.py`'s `stats` dict (`calls`, `fallback_used`, `exceptions`, `invalid_returned_by_inner`) is held purely in the agent process's memory and is never printed to stdout/stderr or otherwise persisted — confirmed by reading the module source (no `print`/`logging` calls exist anywhere in `src/agents/`). Kaggle's exposed per-call log only records `duration`/`stdout`/`stderr`, so **the actual fallback rate cannot be directly measured from this data, in either direction.** The only available proxy is indirect: 0 non-empty stderr entries across 4,151 calls means the wrapped inner agent never raised an exception that survived to produce visible stderr output at the process level (note: `safety_wrapper` catches exceptions internally before they reach stderr, so this proxy is weak — see caveat below).

**C. Fallback behavior** — same limitation as B; not directly observable. No indirect evidence of it either (no visible symptom in the replay data, like the deterministic minimal-legal-action fallback pattern, was systematically checked for this phase beyond the single hand-inspected loss in Section 11).

**D. Invalid actions** — **[LIMITATION]**: same reasoning; `safety_wrapper`'s `invalid_returned_by_inner` counter is never logged. Indirectly, every one of the 46 games completed with status `DONE` (not an engine-level rejection/forfeit), which is weak positive evidence that no *engine-visible* illegal action ever occurred, but says nothing about how often the safety net silently substituted a legal-but-suboptimal fallback for an inner-agent selection the engine would have rejected.

**E. Timeouts** — **[MEASURED, strong evidence of none]**: 0 of 4,151 logged decision calls took ≥1.0 second, and the single highest decision time observed across all 46 games was **0.204 seconds** — two orders of magnitude below the 2.0s per-decision cap and nowhere close to the 150s safety margin that triggers `timeout_shield`'s permanent degraded mode. This is much stronger evidence than the fallback/invalid-action items above, because *latency* (unlike the internal counters) is directly logged by Kaggle for every call.

**F. Errors** — **[MEASURED]**: 0 non-empty stderr entries across all 4,151 calls in the 46 ladder games (and 0 in the validation episode too). No exceptions visibly escaped to the process level in any game.

**G. Decision latency** (pooled across all 4,151 logged calls, computed as the mean of each game's own mean/median/p95/p99 — a per-game-then-pooled average, stated explicitly since it is not the same as a global percentile over all calls):

| Statistic | Value |
|---|---|
| Mean (of per-game means) | 4.0 ms |
| Median (of per-game medians) | 1.2 ms |
| Mean of per-game P95 | 1.8 ms |
| Mean of per-game P99 | 38.3 ms |
| Maximum (any single call, any game) | 203.8 ms |

Decisions are extremely fast relative to both budgets. The P99-vs-median gap (38ms vs 1.2ms) shows a small number of slower calls per game (plausibly the deck-declare call or a state with more legal options to score), but even the tail never approaches a risk regime.

**H. Repeated patterns** — **[OBSERVED]**: the one opponent rematch in the sample ("Toru59er", games 44 and 45, back-to-back in time, same `UNLABELED[Abra, Alakazam, Dudunsparce, Dunsparce, Kadabra]` archetype cluster) was a loss both times. This is **plausible** evidence of a specific weak matchup against that one opponent/deck, but n=2 against that exact opponent (and 4/8=50% against the whole archetype cluster including those 2 games) is nowhere near enough to distinguish a real pattern from chance — not elevated to a finding.

---

## 11. Loss analysis

Built: `results/agent/kaggle_losses.csv` (22 rows). Every loss's structural facts (opponent, archetype/matchup key, going first/second, turns, steps, decision count, stderr count, near-budget-call count, max decision duration) are populated for all 22 rows. **Full turn-by-turn tactical root-cause reconstruction was performed for 1 illustrative case (below); the remaining 21 losses are categorized `LOG_INSUFFICIENT`** per the phase's own "don't force a classification" instruction — the structural data alone does not support a tactical/strategic verdict without the kind of deep, per-loss card-effect tracing that was out of scope for this phase's time budget.

**Case study — game 38 (episode 92098917), the shortest loss (7 turns, 16 decisions), vs a Dragapult ex mirror**: directly inspected the replay's full observation trace. The game ended abruptly at turn ~6 with **0 prizes taken by either side**, our active Pokemon at 10/320 HP (not yet knocked out), no status conditions (poisoned/burned/confused/asleep/paralyzed all `False`) active at the final observed step, and episode status `DONE` (not `ERROR`/`TIMEOUT`). **[OBSERVED, cause not identified]**: the available observation-level fields do not show a clear KO, deck-out, or other conventional end condition at the moment the episode terminated — resolving this would require reconstructing the exact card-effect/rule that fired, which is beyond what the replay's high-level `observation.current` snapshot exposes. Category: `RANDOMNESS_UNCLEAR`.

**Structural pattern across all 22 losses [MEASURED]**: 17/22 (77%) occurred while going first (vs. 34/46 = 74% of all games going first — essentially the base rate, no going-first-specific loss concentration). 0/22 had any non-empty stderr. 0/22 had any decision call near the timeout budget. Losses are spread across turn counts 7-20 with a mode at 13 turns (9 of 22), matching the SHORT bucket's overall lower observed win rate from Section 9 but not conclusively (SHORT bucket CI is wide).

**Category breakdown**: `RANDOMNESS_UNCLEAR` ×1 (hand-inspected), `LOG_INSUFFICIENT` ×21 (structural data only, no tactical trace performed). **Zero losses were classified `IDENTIFIABLE_TACTICAL`, `IDENTIFIABLE_STRATEGIC`, or `POLICY_LIMITATION`** — none of those labels were reached with actual evidence; per the phase's instruction, they were not forced.

---

## 12. Kaggle vs offline evidence comparison

| Offline finding | Kaggle-observed | Consistent? |
|---|---|---|
| Local ablation win rate ~51.7–58.3% (mixed local sparring pool, not real meta) | 52.2% (real ladder, n=46) | **Broadly consistent** — both sit in the low-to-mid 50s, though the offline figure is against a very different (weaker, non-adaptive) opponent pool, so this is a coincidence of similar point estimates more than a controlled comparison |
| Going First override: locally validated vs. Abomasnow specifically (+10.8pp significant); real-ladder archetype-level re-analysis (session 14) found Dragapult ex's own pooled first-advantage NOT credible (CI crosses 0) | +8.3pp in favor of **second** this sample, not significant (p=0.62) | **Not contradicted** — offline evidence for Dragapult ex specifically was already "not credible," so a small, non-significant, opposite-sign estimate on 46 games changes nothing |
| Dragapult ex > Fezandipiti ex, 64.5% win rate, n=76, USABLE-tier (Phase 4.2/4.6) | 25.0% (2/8) this sample | **Not contradicted, but worth watching** — the CI on 8 games [7%, 59%] fully contains the offline 64.5% figure; still, if this matchup continues trending unfavorably as more games accumulate, it would be worth re-checking |
| General meta-aware deck/matchup selection: not reliably superior to simpler baselines (Phase 4.3/4.3b) | N/A — this submission does not use meta-aware selection at all (single fixed deck) | Not testable this phase; consistent with the decision not to build it into production |
| Bayesian opponent prediction: experimental, not wired into production | N/A — confirmed not present in `final_candidate_agent.py`'s composition (safety_wrapper → timeout_shield → dragapult_agent_always_first only) | **Consistent** — production code matches the documented design exactly, verified by direct source read this phase |
| Mewtwo → Fezandipiti counter: validated but not applicable to Dragapult ex production policy | 1 Mewtwo-ex mirror game observed (win), not relevant to this deck's own policy | **Consistent**, not applicable as expected |
| General opponent-aware agent: not justified by offline evidence | Not implemented in production | **Consistent** |

**Overall answer to "does the Kaggle evidence broadly agree with the offline evidence?": YES, broadly** — nothing observed on the real ladder contradicts a prior offline finding at a sample size large enough to be credible. The one directionally-opposite observation (Fezandipiti matchup) is well within the noise band of an 8-game sample. **46 games does not prove the agent's true strength**, and this phase does not claim otherwise.

---

## 13. Statistical assessment

**[MEASURED]** Overall win rate 52.17% (24/46), Wilson 95% CI **[38.1%, 65.9%]**. Two-sided exact binomial test against H0: p=0.5 gives **p = 0.883** — nowhere near conventional significance thresholds. **This sample cannot distinguish the agent's true win rate from 50% at all.**

This is only a rough diagnostic, for the reasons the phase prompt itself flags and that apply directly here:
- **Opponent strength varies and is completely unobserved** (no opponent rating data at all — Section 3) — a 52% win rate against a mix of stronger/weaker opponents means something different than 52% against a fixed-strength pool, and we cannot tell which regime this is.
- **Games are not fully independent** — matchmaking by rating proximity (documented competition mechanism) means opponent strength is correlated with our own current rating over time, which is itself changing.
- **Kaggle's rating system may affect matchmaking** in ways that make a flat "coin flip" null hypothesis an imperfect model even if the agent's true skill were constant.
- **n=46 is a small sample** by the standards this project has otherwise used (the meta-analysis phases worked with thousands of episodes before treating any matchup as credible).

**Is rating ~727 consistent with random early variance, a moderately strong agent, or a clearly strong agent?** Given a win rate statistically indistinguishable from 50%, the data **do not support "clearly strong agent."** The rating increase is real (Section 6), but see Section 14 for why a Bayesian rating system can move substantially even from a near-50% record early in a season — this is most consistent with **"random early variance in a Bayesian system with a wide initial uncertainty band,"** possibly overlaid with a small real edge the current sample is too small to detect, not disprove either.

---

## 14. Critical question: why is rating ~725?

**[HYPOTHESIS, not confirmed]** — decomposed as far as the available evidence allows:

- **Wins/losses**: 24W-22L, a +2 net record, win rate 52.2% [FACT/MEASURED].
- **Opponent strength**: entirely unknown (Section 3/13) — cannot be factored into this decomposition at all. This is the single largest gap preventing a fuller answer.
- **Rating trajectory**: only the two endpoints (600 → 726.9) are known; no intermediate curve is available (Section 6), so it is not possible to say whether the +126.9 came from a few large early swings, a steady accumulation, or something else.
- **Matchup distribution**: spread across at least 8 distinct opponent archetypes plus several UNLABELED clusters, none individually decisive (Section 7) — no single matchup drove the result.
- **First/second distribution**: 74%/26% split, no significant WR difference between the two conditions (Section 8) — does not explain the rating movement either way.

**What the evidence actually supports, stated plainly**: a near-50% observed win rate coexists with a +126.9 rating gain. The most defensible explanation, consistent with the documented rating mechanism (**Bayesian skill rating, Gaussian mu/sigma, mu0=600** — confirmed competition metadata, session 3) is that **early-season rating movement in this kind of system is large relative to win rate alone**, because a fresh submission (and, plausibly, many of its early opponents, who may also be freshly-entered agents given the competition is still accepting submissions) starts with high uncertainty (large sigma), so each game shifts mu more than it will once sigma narrows. **This is a plausible mechanism, not a confirmed one** — this phase did not have access to the rating engine's actual update formula or to opponents' own rating histories, so it cannot be verified directly. It is explicitly **not** correct to conclude "725 means the agent is strong" from this data alone; it is equally not correct to conclude the rating gain is meaningless. The honest position is: **the rating gain is real and directionally positive, but the current win-rate evidence is too thin to independently corroborate "strong," and the rating number by itself should not be treated as stronger evidence than the win-rate CI already given in Section 13.**

---

## 15. Search for unexpected behavior

Checked explicitly, per the phase's own list:

- **Intended always-first but agent sometimes chooses otherwise**: **NOT FOUND** — 29/29 = 100% when actually offered the choice (Section 8). The only reason the *overall* first-rate is 74% rather than 100% is the documented single-player-is-asked engine mechanic, now confirmed live for the first time (Section 8/Executive Summary) — this is a **clarification of expected behavior**, not a discrepancy.
- **Safety wrapper firing unexpectedly**: **CANNOT BE CHECKED** directly (Section 10.B) — no discrepancy found, but also no positive confirmation is possible from this data source.
- **Fallback actions occurring frequently**: same limitation, **CANNOT BE CHECKED** directly.
- **Agent making decisions inconsistent with `final_candidate_agent`**: **NOT FOUND** — read `main.py` and `final_candidate_agent.py` source directly this phase (Section 12) and confirmed the composition matches exactly what's documented (`safety_wrapper` → `timeout_shield` → `dragapult_agent_always_first`), with zero `print`/`logging` calls anywhere in `src/agents/`, which is itself the reason B/C/D above are unobservable — a real, if unglamorous, discrepancy between "what we'd like to observe" and "what the shipped code actually emits," worth fixing in a *future*, purely-additive-logging change (see Future Hypotheses), but not evidence of a behavioral bug.
- **Production package using an unexpected agent/module**: **NOT FOUND** — deck hash-verified identical to `decks/dragapult_ex.csv` across all 47 episodes (46 ladder + 1 validation), zero mismatches (Section 15/deck verification in Section "4").
- **Local and Kaggle behavior differing**: **NOT ASSESSED THIS PHASE** — no fresh local re-run was performed to compare against; the closest evidence is the offline ablation panel (Section 12), which used different opponents entirely, so it is not a like-for-like comparison of *behavior*, only of aggregate outcome.
- **Deck mismatch**: **NOT FOUND**, actively checked and hash-verified (see above).

**Summary: one genuine new mechanistic confirmation (Going First slot-dependence), zero behavioral bugs found, and one honest observability gap (safety/fallback/timeout counters are never logged) that limits how much of Section 10 can be verified either way.**

---

## 16. Required outputs

All produced this phase:

- `results/agent/kaggle_ladder_games.csv` — 46 rows, one per real ladder game
- `results/agent/kaggle_rating_trajectory.csv` — 46 rows, mostly NA per Section 6's limitation
- `results/agent/kaggle_losses.csv` — 22 rows
- `results/agent/kaggle_behavior_summary.csv` — 22 summary metrics
- `results/agent/kaggle_ladder_stats.json` — full computed-statistics dump backing every number in this report (overall/cumulative/going-first-second/matchups/game-length/latency)
- `reports/kaggle_ladder_50games.md` — this report

Raw pulled data (not a required deliverable, kept for reproducibility/future extension): `data/kaggle_ladder/` — `episodes_raw.json`, `submissions_raw.json`, 47 replay JSONs (`replays/`), 47 our-agent log JSONs (`agent_logs/`).

---

## 17. Recommendation

# **B — MONITOR; NO CHANGE YET**

Rationale: at 46 games, the win-rate evidence is statistically indistinguishable from 50% (Section 13), no matchup clears a credible sample-size bar (Section 7), and the going-first evidence neither confirms nor contradicts the offline-validated design (Section 8). No concrete, reproducible technical defect was found — the agent runs cleanly (0 errors, 0 near-timeout calls, 0 deck mismatches across 47 episodes) and its documented policies (deck, Going First override, safety composition) all verified as actually running in production, exactly as designed. The one real observability gap (safety-wrapper/timeout-shield counters never logged) is a monitoring limitation, not a behavioral problem, and does not on its own justify a code change under this phase's explicit "no optimization" constraint. Per the phase's own instruction, this defaults to A or B at this sample size — B is chosen over A specifically to flag two things worth re-checking as more games accumulate before the 2026-08-16 deadline: the Fezandipiti ex matchup (currently 2/8, opposite direction from — but not contradicting — the offline finding) and the still-completely-unobserved opponent-rating dimension, which is the single biggest thing that would sharpen Section 13-14's conclusions if it ever became available.

**Future hypotheses** (explicitly not implemented this phase, recorded only):
1. Add plain, minimal `print()`-based logging of `safety_wrapper`/`timeout_shield` stats at the end of each match inside `main.py` (or a thin wrapper) so future phases can actually measure fallback/invalid-action/degraded-mode rates from Kaggle's exposed stdout — currently the single biggest observability gap found this phase (Section 10/15).
2. Re-run this exact analysis once significantly more games have accumulated (e.g. 150-200+), when matchup-level Wilson CIs would start to narrow enough to potentially clear the credibility bar for Fezandipiti ex and the Abra/Alakazam/Archaludon clusters specifically.
3. Investigate whether `competition_leaderboard_download`/`competition_leaderboard_view` or any other endpoint can be coaxed into exposing a rating *history* rather than only the current score, which would directly resolve Section 6/14's biggest limitation.
4. The abrupt, cause-unclear ending of game 38 (Section 11) could be revisited with a deeper per-action/card-effect trace if a similar pattern recurs.

---

## 18. Limitations

- No per-game rating before/after data exists in any tested Kaggle API surface — only the two endpoints (mu0=600 documented default, current public score 726.9) are real.
- No opponent rating data exists in any tested API surface.
- Opponent agent logs are 403-Forbidden — only our own side's stdout/stderr/duration is retrievable.
- `safety_wrapper`/`timeout_shield` internal counters (fallback_used, exceptions, timeouts, degraded_mode_activations, invalid_returned_by_inner) are never logged anywhere Kaggle exposes, so this phase can only bound them indirectly (via latency and stderr proxies), never measure them directly.
- 46 games is a small sample by this project's own established standards (the meta-analysis phases treated nothing as credible below n=20, and preferred n≥50); every matchup/first-second/game-length cut in this report is explicitly sub-credible.
- Full per-loss tactical root-cause tracing was performed for only 1 of 22 losses (time-budget decision, not a data-availability limitation) — the other 21 have complete structural data but no tactical narrative.
- Leaderboard rank was not resolved this phase (endpoint confirmed working, lookup not completed).
- This analysis is a single snapshot as of 2026-08-12; it will be stale as soon as more games are played (which happens continuously on this ladder).

---

## KAGGLE LADDER STATUS

```
Submission: 55437549 / final_submission.tar.gz

Games analyzed: 46
Wins: 24
Losses: 22
Draws: 0
Win rate: 52.2%

Starting rating: 600
Current rating: 726.9
Rating change: +126.9

Average opponent rating: NA
Opponent data available: NO
Match-level data available: YES
Agent logs available: YES (our side only; opponent logs are 403 Forbidden)

Going First games: 34
Going First WR: 50.0%
Going Second games: 12
Going Second WR: 58.3%

Invalid actions: NA (not logged)
Timeouts: 0 (indirect evidence via latency; internal counter not logged)
Crashes: 0
Fallback actions: NA (not logged)
Safety interventions: NA (not logged)

Evidence strength: EARLY

Current recommendation: B

Agent modified: NO
Submission modified: NO
```

## STOP CONDITION

Analysis artifacts and this report are complete. No agent, deck, policy, or submission changes were made. Per the phase's own stop condition, the next decision (whether to act on any of the Future Hypotheses above) is left to the user.
