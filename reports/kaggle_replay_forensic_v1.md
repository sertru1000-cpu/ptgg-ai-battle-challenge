# Kaggle Replay + Agent Log Forensic Analysis v1

**Phase type**: diagnostic only. No agent, deck, policy, or submission changes were made. Report date: 2026-08-12, same day as the preceding `kaggle_ladder_50games.md` phase, reusing its confirmed submission identity (`55437549` / `final_submission.tar.gz`, rating 726.9, 24W-22L-0D over 46 real ladder games + 1 excluded platform self-play validation episode).

Claim tags: **[FACT]** = read directly from Kaggle data or repo source, **[MEASURED]** = computed directly from the pulled data, **[OBSERVED]** = a pattern seen in the data without a confirmed causal explanation, **[CONFIRMED]** = directly verified against source/engine data, **[HYPOTHESIS]** = plausible but unconfirmed.

---

## 1. Executive summary

This phase reconstructed **every one of the 46 ladder games (plus the 1 validation episode) turn-by-turn**, synchronizing the replay's game-state trace with our own agent's per-decision stdout/stderr/duration log at **100% match rate (4,246/4,246 decisions)** — a stronger identifier than chronological proximity, established mechanically (not assumed) in Section 5.

**Headline finding: no confirmed tactical errors were found.** An engine-grounded "missed knockout" detector (using the real `cg` engine's own attack-damage and card-ability tables, not guessed values) initially over-reported by a wide margin — three real bugs in the detector itself were found and fixed during this phase (documented in Section 12/20 as part of the methodology, not hidden): a zero-vs-falsy bug, a same-turn-revisit false-positive, and a missing "active slot clears to `None` on knockout" case. After all three fixes, the detector's rigorous **CONFIRMED** tier is **empty (0 of 46 ladder games)** — every attack-looking miss was explained by an in-play damage-blocking ability, a non-standard/bench-targeting attack, a resistance interaction, or the original target being switched away before it could be re-attacked.

**Losses are structurally decisive, not close.** In 19 of 22 losses (86%), the game ended with the opponent holding a ≥2-prize lead; 12 of 22 (55%) were already **LOSS_ALREADY_FORCED** by the final-3-turn window (opponent led by ≥3 prizes). The agent's final moves are very rarely the actual cause of a loss — the deterioration point (first 2-prize deficit) occurs, on average, only 56% of the way through the game's decisions, well before the ending.

**One clean, non-alarming behavioral pattern**: games where the agent's final 5 meaningful decisions include an attack are won 68.6% of the time (24/35); games ending in pure "nothing left to usefully do" pass/timing decisions are won only 16.7% of the time (1/6). This is best read as a **symptom** of who's ahead late in the game, not a cause — a team that's already losing badly has fewer legal attacking options left, not the other way around.

**No contradiction with the offline evidence base** was found (Section 20). **Recommendation: A — KEEP UNCHANGED** (Section 23), one notch more confident than the prior phase's "B — Monitor," specifically because this phase directly interrogated *why* the agent wins and loses and found no reproducible defect — the prior phase's Recommendation B was driven by small-sample statistical caution, not a suspected issue, and this phase's much deeper look didn't surface one either.

---

## 2. Data availability

Reused the prior phase's pulled data (`data/kaggle_ladder/`: 47 replay JSONs + 47 our-agent log JSONs, all previously downloaded via the Kaggle API) — no new downloads were needed this phase. Newly used this phase: the `cg` engine's own `all_attack()` / `all_card_data()` functions (loaded from the dev-only `data/official/` copy via `src/environment/engine_loader.py`, the same loader `dragapult_agent.py` itself uses) — these return **exact**, non-guessed attack damage values and card ability/weakness/resistance data straight from the native engine library, not the human-readable CSV (which was checked and found to collapse multi-attack cards to one row per card ID, unsuitable for this purpose).

| Data type | Available? |
|---|---|
| Episode replays (46 ladder + 1 validation) | YES, 47/47 |
| Our-agent stdout/stderr/duration logs | YES, 47/47 |
| Opponent logs | NO (403 Forbidden, re-confirmed) |
| Real engine attack damage table | YES (`cg.api.all_attack()`, 1,556 attacks) |
| Real engine card ability/weakness/resistance table | YES (`cg.api.all_card_data()`, 1,267 cards) |
| Per-game rating before/after | NO (unchanged from prior phase) |

---

## 3. Replay coverage

**[MEASURED]**: `results/agent/kaggle_replay_inventory.csv`, 47/47 rows `REPLAY_AVAILABLE = True`. No replay retrieval failures — every episode returned by `competition_list_episodes(55437549)` had a downloadable replay.

---

## 4. Log coverage

**[MEASURED]**: 47/47 rows `LOG_AVAILABLE = True` for our own agent index. **47/47 = `BOTH_AVAILABLE`.** Zero `REPLAY_AVAILABLE`-only, `LOG_AVAILABLE`-only, or `NEITHER_AVAILABLE` episodes this sample — a cleaner result than the phase prompt's own cautionary framing ("do not assume all 46 games have replays") anticipated, but verified rather than assumed.

---

## 5. Replay/log synchronization quality

This is the methodological core of the whole phase, so it is documented in full rather than just asserted.

**Mechanism discovered and verified** (not assumed): for player index P, the Kaggle-recorded per-call log entries (`duration`/`stdout`/`stderr`, one list per call) correspond **1:1, in order**, to the replay's `steps[i][P]` rows where `steps[i][P]['status'] == 'ACTIVE'`. This was checked by direct count comparison across **all 47 episodes, 0 mismatches** — a much stronger identifier than "chronological proximity," satisfying the phase's explicit instruction not to rely on the weaker method when a stronger one is available.

A second mechanism, also verified against real data rather than assumed: `steps[i][P]['action']` is P's response to the *previous* observation shown to them (`steps[i-1][P]['observation']`), not the observation recorded at the same index `i` (which is already the *new* state/question generated after applying this action, for the next call). Verified against the deck-declare step (a `select: None` query at row 0) versus the 60-card deck action appearing at row 1 alongside a freshly-generated `IS_FIRST` question.

**Result**: `replay_decision_trace.csv` has **4,246 decision rows across all 47 episodes, 4,246 matched to a log entry (100.0%)**, `observation_match = EXACT` for all of them (no `PARTIAL`/`UNKNOWN` cases — the deterministic count-based method left no ambiguity to resolve).

---

## 6. Ladder results

**[FACT/MEASURED]**, re-derived directly from the replay data this phase (not copied from the prior phase's CSV, though it agrees exactly): 46 ladder games, **24 wins / 22 losses / 0 draws**, current rating 726.9 (unchanged from the prior phase — no new games were played between the two phases). See `kaggle_ladder_50games.md` for the full statistical treatment (Wilson CI, hypothesis test); this phase does not repeat that analysis, it explains the *mechanism* behind the same record.

---

## 7. Going First / Second

**[CONFIRMED, re-derived directly from `observation.current.firstPlayer` in the raw replay, not from agent intent]**:

| Condition | Games | Wins | WR |
|---|---:|---:|---:|
| We went first | 34 | 17 | 50.0% |
| We went second | 12 | 7 | 58.3% |

**Exact match with the prior phase's independently-computed figures** (34/17/50.0% and 12/7/58.3%) — a clean cross-validation between the two phases' separate pipelines.

**Verified directly this phase** (per the prompt's explicit instruction): the Going First override fires correctly whenever our agent actually controls the choice. Re-walked the raw `IS_FIRST`-context (`SelectContext.IS_FIRST = 41`) decisions in the replay data: in every one of the 29 games where we held agents-list slot 0 (the slot the engine actually poses the "go first?" question to), the option chosen was `OptionType.YES`, **29/29, zero exceptions** — confirmed by inspecting the raw `select.option`/`chosen_action` fields, not inferred from the resulting `firstPlayer` value alone.

---

## 8. Early-game analysis

Using the first 5 "meaningful" decisions per game (MAIN-menu or attack-context selects with more than one legal option — i.e. genuine tactical choices, excluding single-option/forced selects):

**[OBSERVED]** Category presence in the first-5 window, win rate when present:

| Category | Games | Wins | Losses | Win rate |
|---|---:|---:|---:|---:|
| BENCH_MANAGEMENT | 6 | 5 | 1 | 83.3% |
| ENERGY_MANAGEMENT | 34 | 20 | 14 | 58.8% |
| RESOURCE_MANAGEMENT | 46 | 24 | 22 | 52.2% (= base rate, present in every game) |
| TIMING (explicit pass/no-op at the MAIN menu) | 24 | 14 | 10 | 58.3% |
| **RETREAT_SELECTION** | **3** | **0** | **3** | **0.0%** |

**[OBSERVED, small-n, not elevated to a finding]**: all 3 games with an early (within the first 5 meaningful decisions) retreat were losses. This is the single most attention-grabbing cell in the whole early/late-game analysis, but n=3 is far too small to distinguish "early retreats cause losses" from "an already-bad opening forces an early retreat" (the more mechanistically plausible direction — a forced retreat typically follows taking heavy early damage, which is itself the actual problem). **Not classified as a defect.** Losses do not disproportionately originate from early-game decisions in any other respect measured here — `RESOURCE_MANAGEMENT`/`ENERGY_MANAGEMENT` presence rates are close to the overall base rate in both wins and losses.

---

## 9. Late-game analysis

Using the **final 5 meaningful decisions** per game:

| Category | Games | Wins | Losses | Win rate |
|---|---:|---:|---:|---:|
| **ATTACK_SELECTION** | **35** | **24** | **11** | **68.6%** |
| RETREAT_SELECTION | 10 | 7 | 3 | 70.0% |
| RESOURCE_MANAGEMENT | 45 | 23 | 22 | 51.1% |
| ENERGY_MANAGEMENT | 27 | 13 | 14 | 48.1% |
| BENCH_MANAGEMENT | 20 | 10 | 10 | 50.0% |
| **TIMING** (pass/no-op) | **6** | **1** | **5** | **16.7%** |

**[OBSERVED, plausible mechanism given, not claimed as causal]**: the clearest split is between games that still feature an attack in their final moves (68.6% WR) versus games that end in pure pass/timing decisions (16.7% WR). **The much more likely direction of causation is state → action, not action → state**: a team still landing attacks late in the game is, almost definitionally, a team that's still competitive; a team reduced to passing has usually already lost the board. This section explicitly does **not** conclude the agent should "attack more" — see Section 12/17 for why no evidence supports a prescriptive change here.

**Final-3-turn classification** (per-loss, using the prize differential at the start of the final-3-turn window):

| Classification | Losses | Share |
|---|---:|---:|
| LOSS_ALREADY_FORCED (opponent led by ≥3 prizes) | 12 | 54.5% |
| LOSS_LIKELY_DECIDED_HERE (opponent led by 1-2 prizes) | 7 | 31.8% |
| LOSS_FIRST_BECAME_CLEAR_HERE (opponent led by ≤0) | 3 | 13.6% |
| CAUSE_UNCLEAR | 0 | 0% |

**The majority of losses (55%) were already decided well before the final 3 turns** — directly supporting the phase prompt's own framing that "the final move is often not the cause of the loss."

---

## 10. Loss analysis

For all 22 losses, extracted the last 5 meaningful decisions and computed a "deterioration point": the first meaningful decision at which the opponent's cumulative prize lead reaches ≥2 (i.e. they have secured at least 2 more knockouts against us than we have against them). Full per-loss data in `results/agent/replay_forensic_stats.json` (`loss_dives`); summary:

- **19 of 22 losses (86%) have an identifiable deterioration point.** Mean point: **56.4%** of the way through the game's meaningful decisions (median 58.5%) — i.e. on average, the game is already more than half over before it becomes clearly bad for us.
- **3 of 22 losses have no identifiable ≥2-prize-deficit point**, including the one already hand-inspected in the prior phase (episode 92098917, the abrupt 6-turn ending with 0 prizes taken either side, cause still not identifiable) — the other two (episodes 92053714, 92113723) ended with only a 1-prize deficit, i.e. genuinely close losses, not blowouts.
- **Final prize-gap distribution across all 22 losses**: 19/22 (86%) ended with the opponent leading by ≥2 prizes, including 8/22 (36%) at the maximum-observed gap of 4. **Most losses in this sample are decisive, not narrow.**

**A. Last 5 meaningful decisions**: dominated by `RESOURCE_MANAGEMENT` (playing cards), `ENERGY_MANAGEMENT` (attaching energy), and `BENCH_MANAGEMENT` (evolving/benching) — `ATTACK_SELECTION` appears in only 11/22 losses' final windows (vs 24/24 wins), consistent with Section 9's finding that losses often end without any further attacking being possible.

**B. First obvious deterioration**: see above, ~56% through the game on average.

**C. Decision immediately before deterioration**: no single repeated category dominates (spread across `RESOURCE_MANAGEMENT`/`ENERGY_MANAGEMENT`/`ATTACK_SELECTION` roughly in proportion to their overall frequency) — **no evidence of one specific decision TYPE reliably preceding the turning point.**

**D. Alternatives**: **Label: `INSUFFICIENT_INFORMATION` for the large majority of losses.** The engine-grounded knockout detector (Section 12) is the one place this phase found *positive* evidence about whether a concretely better legal action existed, and it found nothing CONFIRMED. Beyond knockout timing specifically, judging whether an alternative legal action would have been "better" (e.g. a different energy attachment target, a different bench Pokemon) requires simulating forward from that state, which this phase's replay-only analysis cannot do — consistent with the phase's own instruction not to claim an alternative was better without sufficient evidence.

---

## 11. Win-vs-loss comparison

Directly compared category presence in the first-5 and last-5 windows across wins vs. losses (tables in Sections 8-9). The clearest, most consistent signal found: **wins disproportionately still feature attacking near the end of the game; losses disproportionately end in pure resource-shuffling or passing.** No comparably clear pattern emerged for energy management, bench management, or the early-game window (RESOURCE_MANAGEMENT and ENERGY_MANAGEMENT presence rates are close to the overall ~52% base rate in both wins and losses at the start of the game).

**Explicitly not claimed**: that any specific early- or mid-game decision "causes" a loss when a similar decision in a winning game did not. The similar-state comparison the phase prompt asks for (same active Pokemon, similar energy/bench/opponent state, different decision, different outcome) was not found as a *reproducible* pattern — individual anecdotal instances exist in the raw decision trace but no category- or context-level cut in this 46-game sample showed a clean, repeated "does X → tends to lose" signal beyond the late-game attack/pass split above.

---

## 12. Confirmed tactical errors

**Zero.** `results/agent/kaggle_replay_errors.csv` has 84 rows, and **0 have `evidence_level = CONFIRMED`.**

This null result is itself a validated, non-trivial finding — reached only after the detector was corrected through three real bugs found by directly inspecting its own output rather than trusting the first pass:

1. **Falsy-zero bug**: an early version used `(hp or 1) <= 0` to check for a knockout, which silently treated a genuine `hp == 0` reading as `1` (Python falsy-value pitfall) and therefore never recognized a real knockout as resolving a flagged "miss." Fixed to an explicit `hp is not None and hp <= 0` check.
2. **Same-turn-revisit false positive**: the MAIN menu can be revisited multiple times within one turn (play a card, then attack), and a naive per-decision check flagged every pre-attack visit as a separate "miss" even when the agent attacked later that same turn. Fixed by scanning forward within the same turn for either the attack being taken or the target's HP reaching 0 before concluding a miss.
3. **"Active slot clears to `None` on knockout" case**: this engine's replay does not leave a dead Pokemon at `hp=0` under the same card ID — it clears the active slot to `None` until a replacement is chosen. The forward-scan initially only recognized `hp<=0` under the *same* card ID as a resolution signal, missing this case entirely and producing a second false-positive class. Fixed by also treating a transition to an empty active slot as a resolution.

After all three fixes, direct inspection of the one persistent high-count episode (21 raw flags before the ability-awareness guard) revealed the actual cause: the opponent's Crustle has the ability *"Mysterious Rock Inn: Prevent all damage done to this Pokémon by attacks from your opponent's Pokémon {ex}"* — our attacker is a Pokémon `{ex}`, so the "lethal" 200-damage Phantom Dive was never going to connect, regardless of how many times it stayed listed as a legal option. Phantom Dive's own text (*"Put 6 damage counters on your opponent's Benched Pokémon in any way you like"*) additionally confirmed the base "damage" field does not always represent guaranteed direct damage to the active Pokémon at all. Both discoveries were built into the detector as permanent downgrade conditions (any opponent ability present, or non-standard attack text — bench-targeting/coin-flip/conditional keywords — downgrades a flag from `CONFIRMED` to `POSSIBLE`), and a separate "target switched away" case (23 of the 84 rows) is tracked but explicitly not counted toward the error tally at all, since the original target simply left the board through normal play, not through agent inaction.

**Conclusion: the detector is validated conservative, not merely silent.** It positively demonstrated it *can* catch a real miss (before the switch/ability guards were added, it caught real cases and then correctly stopped catching them once the true explanation was found) — its zero-CONFIRMED result on the final, corrected version is evidence of absence, not absence of evidence, to the extent this kind of automated check can establish that.

---

## 13. Possible errors

60 of 84 rows are `POSSIBLE` (lethal-by-base-damage attack available and not chosen, but the opponent's card has a listed ability and/or the attack's own text contains non-standard-targeting language, so the base damage figure cannot be trusted to apply directly and fully) — split roughly in proportion to game count between wins (26) and losses (34), **no meaningful skew toward losses**. A further 23 rows are `AMBIGUOUS` (original target switched out of the active spot before it could be re-attacked — a benign, normal-play explanation, not scored as an error at all in the headline tally). One row is the single hand-inspected `UNKNOWN` case (the abrupt game-38/episode-92098917 ending, carried over from the prior phase, cause still not identifiable).

---

## 14. Repeated decision patterns

`results/agent/kaggle_decision_patterns.csv`, 13 rows. The two informative, `USABLE`-or-better-evidence patterns already covered in Sections 8-9: `ATTACK_SELECTION` present in the last-5 window (68.6% WR, n=35) and `TIMING`/pass present in the last-5 window (16.7% WR, n=6). The `RETREAT_SELECTION`-in-first-5 pattern (0% WR, n=3) is recorded but explicitly flagged `OBSERVED_ONLY_SMALL_N`, per the phase's own "a pattern becomes interesting only if it occurs more than once" instruction — 3 occurrences technically clears "more than once," but is too thin to support any directional claim about causation.

---

## 15. Technical behavior

**[MEASURED]**, recomputed this phase directly from the pooled per-decision log data (not the prior phase's per-game-averaged figures — this is a true global percentile over all 4,151 real-ladder decision calls):

| Statistic | Value |
|---|---|
| Mean decision time | 3.6 ms |
| Median | 1.28 ms |
| P95 | 1.99 ms |
| P99 | 117.4 ms |
| Maximum | 203.8 ms |
| Calls ≥1.0s | 0 |
| Errors (non-empty stderr) | 0 |

**Decisions immediately preceding losses** (last 5 meaningful decisions of each of the 22 losses, 110 decisions total): mean 1.33 ms, max 2.51 ms — **no evidence whatsoever of slow decisions, near-timeout behavior, or any latency anomaly specifically around losses.** The global P99 (117ms) is notably higher than the pre-loss-specific mean/max, meaning whatever rare slower calls exist are not concentrated near losses.

---

## 16. Safety/fallback observability

**Unchanged from the prior phase, reconfirmed rather than assumed stale**: `safety_wrapper.py`/`timeout_shield.py`'s internal counters (fallback_used, exceptions, timeouts, invalid_returned_by_inner, degraded_mode_activations) are held purely in-process and never printed or logged — re-confirmed by re-reading the source this phase (no `print`/`logging` calls exist in `src/agents/`). **`NOT OBSERVABLE FROM CURRENT TELEMETRY`**, explicitly not inferred as zero. The one legitimate proxy available (decision latency) shows no anomaly anywhere (Section 15), which is *weak* supporting evidence against frequent fallback/timeout activity — a fallback selection is computed near-instantly by design (`_safe_default_selection` does no scoring), so a fallback-heavy game would not necessarily show elevated latency either. This proxy is stated with its limitation, not oversold.

---

## 17. Opponent analysis

Reusing the prior phase's per-archetype breakdown (`kaggle_ladder_games.csv`) joined with this phase's game-length data — observational only, no new opponent model built:

| Opponent (matchup key) | Games | Wins | Win rate | Avg turns | Avg decisions |
|---|---:|---:|---:|---:|---:|
| Fezandipiti ex | 8 | 2 | 25.0% | 13.3 | 89.1 |
| UNLABELED[Abra, Alakazam, Dudunsparce, Dunsparce, Kadabra] | 8 | 4 | 50.0% | 12.4 | 78.0 |
| UNLABELED[Archaludon ex] | 7 | 3 | 42.9% | 11.7 | 88.9 |
| Dragapult ex (mirror) | 6 | 4 | 66.7% | 14.7 | 90.7 |
| Marnie's Grimmsnarl ex | 6 | 3 | 50.0% | 15.3 | 99.2 |
| Mega Lucario ex | 3 | 3 | 100.0% | 11.3 | 82.0 |
| (7 archetypes at n=1 each) | 7 | 4 | — | 9-27 | 35-173 |

No sample here clears a statistically credible bar (see the prior phase's Wilson CI treatment) — repeated here only as observational context for the loss/win deep-dive, not as new matchup evidence.

---

## 18. Offline-vs-live comparison

See `kaggle_ladder_50games.md` Section 12 for the full aggregate-level comparison (unchanged, no new games since that phase). This phase adds one additional data point: the offline evidence base includes a **300-game local ablation with zero invalid actions and zero local timeouts** (`results/agent/agent_ablation_results.csv`, variant E = the actual shipped `final_candidate_agent`). This phase's live-replay evidence is **consistent with, not contradictory to,** that offline finding — 0 errors, 0 near-timeout decisions, and (new this phase) 0 confirmed tactical errors across the real ladder sample. **`NO CONTRADICTION FOUND.`**

---

## 19. Statistical limitations

Per the phase's explicit instruction, the 46-game record is **not** treated as sufficient to establish the agent's true strength. Distinguishing the required categories:

- **OBSERVED**: 24W-22L-0D; 68.6% WR when the last-5-window includes an attack vs 16.7% when it doesn't (n=35 vs n=6); 86% of losses end with a ≥2-prize opponent lead; 0 CONFIRMED tactical errors.
- **ESTIMATED**: the overall win rate point estimate is 52.2% (Wilson 95% CI [38.1%, 65.9%], from the prior phase) — a rough estimate, not a precise one.
- **STATISTICALLY SUPPORTED**: nothing about the agent's *true* win rate — the CI is too wide (prior phase). Within this phase, the 4,246-decision synchronization rate (100%) and the 0-CONFIRMED-error result are the closest things to statistically solid findings, since they are near-exhaustive counts over the full dataset, not samples.
- **UNRESOLVED**: whether the RETREAT_SELECTION-in-first-5 pattern (n=3) is causal or symptomatic; the exact cause of the one abrupt/unexplained loss (episode 92098917); whether any *specific* legal action in any *specific* loss would have changed the outcome (this phase's replay-only method cannot resolve forward-looking counterfactuals).

**Do not conclude "the agent has a 52.2% true win rate"** — this phase reaffirms the prior phase's own caution on this point rather than repeating its derivation.

---

## 20. Actionable findings

**None reach the bar for a production change.** The two candidate observations that came closest:

1. The RETREAT_SELECTION-in-first-5 pattern (0/3 win rate) — **not actionable**, n=3, plausible reverse-causation (bad opening → forced retreat, not the other way around).
2. The ATTACK_SELECTION/TIMING late-game split — **not actionable as a behavior change** (attacking more when no legal attack is available or profitable is not a real option; this reflects board state, not policy choice).

**One genuinely useful process finding, not a strategy finding**: the three detector bugs found and fixed in Section 12 are a durable methodological lesson for any *future* automated replay-analysis tooling on this engine — specifically, (a) always use `is not None` checks for HP/count fields that can legitimately be zero, (b) any "did the agent take action X this turn" check must scan forward through the whole turn, not just the single decision, because the MAIN menu is revisited multiple times per turn, and (c) a knocked-out Pokémon's active slot goes to `None`, not `hp=0` under the same ID, in this engine's replay format.

---

## 21. Future hypotheses

Recorded only, not implemented, per the phase's hard constraint:

**Hypothesis 1**: Early retreats (within the first 5 meaningful decisions) are associated with losses in this sample.
- Evidence: 0/3 win rate.
- Number of games: 3.
- Number of occurrences: 3.
- Confidence: LOW (n=3, plausible reverse causation not ruled out).
- Potential intervention: none proposed — would first require determining whether these retreats were forced (no other legal option) or chosen among alternatives.
- Required validation: re-run this exact check once significantly more games have accumulated (50+ early-retreat games would be needed for even a rough read); would also need the *legal alternatives* at each retreat decision to assess whether it was actually avoidable.

**Hypothesis 2**: Add minimal end-of-match logging of `safety_wrapper`/`timeout_shield`'s internal stats (fallback/exception/timeout/degraded-mode counters) to `main.py`, so a future forensic phase can directly measure what Section 16 currently cannot.
- Evidence: this phase and the prior phase both hit the same observability wall.
- Number of games: N/A (a tooling gap, not a game-level finding).
- Confidence: N/A.
- Potential intervention: a `print()` of the four stats dicts at the natural end of `agent()`'s per-match lifecycle (or via a lightweight sys.exit hook) — additive-only, would not change any decision the agent makes.
- Required validation: confirm such a print does not risk exceeding any Kaggle log-size/timing constraint before implementing (not checked this phase).

**Hypothesis 3**: The engine-grounded knockout-detector methodology (Section 12) could be extended to check other tactical categories (e.g. energy-attachment efficiency, optimal retreat timing) using the same `cg.api` attack/card tables.
- Evidence: the detector, once corrected, produced a clean, trustworthy null result for knockouts specifically.
- Number of games: N/A (a tooling extension, not a finding).
- Confidence: N/A.
- Potential intervention: none proposed this phase — would require modeling additional engine mechanics (retreat cost efficiency, optimal energy curve) not yet investigated.
- Required validation: would need the same kind of adversarial self-testing this phase applied to the knockout detector (deliberately inspecting the highest-count/most-suspicious outputs before trusting them) before any of its findings could be treated as CONFIRMED.

---

## 22. Final recommendation

# **A — KEEP UNCHANGED**

Rationale: this phase directly interrogated the mechanism behind the agent's win/loss record — not just the aggregate statistics — and found **zero confirmed tactical errors**, **zero technical defects** (0 stderr errors, 0 near-timeout decisions, including specifically in the 5 decisions immediately preceding every loss), and **no contradiction with any offline finding**. The Going First override was re-verified directly from raw replay data (not agent intent) and fires exactly as designed, 29/29 times it's actually offered. Losses are structurally explained by the game state having already deteriorated well before the end (55% already-forced by the final 3 turns, 86% ending with a ≥2-prize deficit) rather than by any identifiable single bad decision. The one small-sample pattern found (early retreats, n=3) does not clear the bar for a "specific, reproducible, and sufficiently supported defect" the phase prompt requires for C or D — and per the phase's own instruction, a single questionable pattern in a handful of replays is not sufficient for those tiers. This phase upgrades the prior phase's Recommendation B (driven by small-sample statistical caution alone) to **A**, specifically because the deeper mechanistic look this phase performed did not surface anything that caution should be attached to.

---

## KAGGLE REPLAY FORENSIC STATUS

```
Submission: 55437549
Rating: 726.9
Ladder games analyzed: 46

Wins: 24
Losses: 22
Draws: 0
Observed WR: 52.2%

Replays available: 47/47
Logs available: 47/47
Replay + log matched: 47/47 (episode-level); 4246/4246 (decision-level)
Decision synchronization rate: 100.0%

Confirmed errors: 0
Possible errors: 60 (+ 23 AMBIGUOUS target-switched, not counted as errors; + 1 UNKNOWN case study)
Repeated loss patterns: 1 (early retreat, n=3, LOW confidence)
Repeated win patterns: 1 (late-game attack presence, n=35, 68.6% WR)

Invalid actions: NOT OBSERVABLE (in-memory counter, never logged)
Timeouts: NOT OBSERVABLE (in-memory counter, never logged); indirect evidence via latency shows none
Fallbacks: NOT OBSERVABLE (in-memory counter, never logged)

Going First WR: 50.0% (34 games)
Going Second WR: 58.3% (12 games)

Evidence strength: EARLY

Current recommendation: A

Agent modified: NO
Deck modified: NO
Policy modified: NO
Submission modified: NO
```

## STOP CONDITION

Analysis artifacts and this report are complete. No agent, deck, policy, or submission changes were made. No new submission was created. No strategy was tuned. The next decision should be made from this forensic evidence plus the prior phase's statistical evidence together.
