# Real Meta Pilot Report v1 (Part 1, Steps 2–9)

Tags: **[FACT]** verified directly, **[RESULT]** computed this session from the pilot,
**[HYPOTHESIS]** plausible/untested, **[QUESTION]** open. Raw per-episode and per-deck data are
preserved (never overwritten) at `strategy/meta_analysis/pilot_episodes_v1.csv` and
`strategy/meta_analysis/pilot_deck_registry_v1.csv`; this report is a derived summary, not a
replacement for that raw data.

## 1. Sample methodology (Step 2, recap of `reports/episode_sampling_plan.md`)

**[FACT]** 1,040 episodes downloaded via per-file Kaggle API calls (no full-day archives):
- **1,000 "main" episodes**: stratified by 8 calendar weeks x 5 within-week size-quintiles x 25
  episodes/cell, quintile boundaries computed per-week.
- **40 "anomaly" episodes**: 20 from the <200KB file-size tail, 20 from the >20MB tail,
  deliberately oversampled to characterize the extreme-length populations found in Part 0/the
  sampling plan; excluded from all win-rate/archetype/matchup statistics below to avoid biasing
  them, analyzed separately in §10.

## 2. Download / storage cost (Step 2)

**[RESULT]** Actual downloaded volume: **5.4GB** on disk for 1,040 episodes (estimate was
5.71GB — consistent). Wall-clock: **~35 minutes** end-to-end via the throttled
(`dataset_download_file` + backoff, ~0.4s between calls) sequential downloader
(`tools/download_pilot.py`). **Zero failures** (1040/1040 succeeded on first or retried
attempt). This implies per-call latency (not bandwidth) is the dominant cost — bandwidth
observed as very high (multi-hundred-MB/s) in Part 0's spot checks, but the Kaggle API's
per-file-download round-trip overhead dominates wall-clock time at this file count.

## 3. Processing cost (Step 2)

**[RESULT]** Parsing all 1,040 episodes (deck extraction + hashing + archetype tagging) took
**100 seconds** (`tools/build_pilot_dataset.py`), i.e. ~10.4 episodes/sec, effectively I/O-bound
(reading + `json.load`-ing 5.4GB). **Zero parse errors** — the `episode_parser.py` deck-declare
extraction method (Part 0 §5) worked on all 1,040 files without a single fallback to the
`visualize`-based backup path.

**[RESULT] Linear extrapolation to 5,000–20,000 episodes**: download ~2.8–11.2 hours at the
current throttle rate (dominant cost — could likely be parallelized/reduced with concurrent
requests, not attempted this session to stay conservative against rate limits), parsing
~8–32 minutes, storage ~26–104GB. All comfortably within the ~47GB free disk *if done in
batches*, but the full 20,000-episode upper bound would need either more aggressive
parallelization or disk cleanup between batches.

## 4–5. Deck distribution and exact deck frequency (Steps 3–5)

**[RESULT] 422 distinct exact decklists (by `deck_hash`) observed across 1,040 episodes**
(2,080 deck-slots since every episode has 2). This is a genuinely diverse population, not a
small handful of decks repeated — no single deck exceeds ~12% of all deck-slots (top deck:
`dc2ce39b94cbbb38`, tagged Marnie's Grimmsnarl ex, 252 decisive games out of 2,080 total
deck-slots, i.e. ~12.1%). Top 20 decks by game count are in `analysis_out.txt`-derived
`strategy/meta_analysis/pilot_deck_registry_v1.csv`, sorted by `n_games_seen`.

**[FACT]** Deck-hash identity is stable across episodes and days — e.g. deck
`dc2ce39b94cbbb38` was played by the same submitting player repeatedly across many separate
episodes (consistent with the real-world expectation that a competitor submits one deck and it
plays many ladder games), confirming the hash is doing its job as a true deck-identity key, not
producing spurious collisions or splits.

## 6. Preliminary archetype structure (Step 4 — do not assume the 8 known archetypes are complete)

**[RESULT] Archetype-level frequency (DECISIVE games only, both sides pooled, n=1,994
deck-slots)**:

| Label | Games | Distinct decks | Win rate | 95% CI | Usage share |
|---|---|---|---|---|---|
| **UNLABELED** | 499 | 178 | 0.505 | [0.461, 0.549] | 25.0% |
| Marnie's Grimmsnarl ex | 485 | 32 | 0.491 | [0.446, 0.535] | 24.3% |
| Fezandipiti ex | 328 | 62 | 0.503 | [0.449, 0.557] | 16.4% |
| Mega Lucario ex | 145 | 38 | 0.497 | [0.416, 0.577] | 7.3% |
| Mega Kangaskhan ex | 139 | 22 | 0.482 | [0.401, 0.564] | 7.0% |
| Dragapult ex | 106 | 26 | 0.462 | [0.370, 0.557] | 5.3% |
| Cynthia's Garchomp ex | 79 | 7 | 0.532 | [0.423, 0.638] | 4.0% |
| Team Rocket's Mewtwo ex | 77 | 20 | 0.532 | [0.422, 0.640] | 3.9% |
| Mega Lopunny ex | 66 | 10 | 0.561 | [0.441, 0.674] | 3.3% |
| Teal Mask Ogerpon ex | 45 | 16 | 0.511 | [0.370, 0.650] | 2.3% |
| Mega Abomasnow ex | 15 | 4 | 0.467 | [0.248, 0.699] | 0.8% |
| Iono's (Bellibolt/Voltorb) | 10 | 1 | 0.400 | [0.168, 0.687] | 0.5% |

**[RESULT] Every archetype's win rate sits close to 50%** (0.40–0.56, all confidence intervals
overlap 0.5 except none are extreme). **[HYPOTHESIS]**: this is very likely a **matchmaking
artifact, not evidence that all decks are equally strong** — the competition explicitly uses a
Bayesian skill-rating ladder that pairs agents of similar current rating (per
`docs/environment.md`/prior-session-verified competition mechanics), which mechanically pulls
observed win rates toward 50% regardless of a deck's "true" power, since a stronger deck's
*pilot* gets matched against correspondingly higher-rated opponents. **Raw archetype win rate on
this ladder should not be read as a power ranking** — this is an important caveat for Part 2 of
the phase prompt and for any future counter-deck selection work.

**[RESULT] A quarter of all games (25.0%) are UNLABELED — i.e., do not match any of the 8 known
live-meta archetypes or 4 local sample decks.** Per Step 4's explicit instruction not to
prematurely assume completeness, this bucket was inspected directly rather than left as a
residual. It is **not one archetype** — it decomposes into multiple distinct, internally
consistent families never previously catalogued in this project:

| Discovered family (evidence Pokemon) | Games seen (both variants pooled) |
|---|---|
| Abra / Kadabra / Alakazam | 61 |
| Hop's Phantump / Hop's Trevenant | 62 (2 variants) |
| Archaludon ex / Duraludon / Cinderace | 37 |
| Cinderace / Staryu-based Fire-Water tech | 45 (2 variants) |
| Dwebble / Crustle | 26 (2 variants) |

**[RESULT] This means the real meta has at minimum ~13–17 distinct archetype families** (12
known-labeled + ≥5 newly discovered above, some UNLABELED decks not yet clustered), **not the 8
the 2026-07-31 community snapshot reported and not the 4 official sample decks** — both prior
reference sources undercount the actual competitive diversity, especially earlier in the season
(see §8). Full clustering of all 178 distinct UNLABELED decks into named families is future work
(flagged in §12), not completed this session — this pilot's job was to determine *whether* such
clustering is worthwhile, and the answer is clearly yes.

## 7. Matchup matrix with sample sizes (Step 7)

**[RESULT]** Full matrix (labeled-vs-labeled only, DECISIVE games only,
`analysis_out.txt` has the complete table) — **18 of 45 label pairs have n≥20** and are not
flagged `[LOW-N]`:

| Matchup | n | Row win rate | 95% CI |
|---|---|---|---|
| Fezandipiti ex vs Mega Kangaskhan ex | 38 | 0.684 | [0.525, 0.809] |
| Fezandipiti ex vs Marnie's Grimmsnarl ex | 84 | 0.476 | [0.373, 0.582] |
| Fezandipiti ex vs Team Rocket's Mewtwo ex | 20 | **0.200** | [0.081, 0.416] |
| Marnie's Grimmsnarl ex vs Team Rocket's Mewtwo ex | 29 | 0.517 | [0.344, 0.686] |
| Marnie's Grimmsnarl ex vs Mega Kangaskhan ex | 39 | 0.410 | [0.271, 0.566] |
| Dragapult ex vs Marnie's Grimmsnarl ex | 20 | 0.650 | [0.433, 0.819] |
| Dragapult ex vs Fezandipiti ex | 20 | 0.550 | [0.342, 0.742] |
| Cynthia's Garchomp ex vs Marnie's Grimmsnarl ex | 27 | 0.630 | [0.442, 0.785] |

**[RESULT] Fezandipiti ex vs Team Rocket's Mewtwo ex (n=20, 20.0% win rate for Fezandipiti) is
the most lopsided matchup with an adequate sample** — its CI [0.081, 0.416] does not include
0.5, i.e. this is the one cell in the whole pilot matrix that's statistically distinguishable
from an even matchup at this sample size. **[HYPOTHESIS]**: possible real counter-relationship,
worth confirming at larger n before treating as established (n=20 is adequate to flag, not to
finalize).

**[RESULT] The other 27 of 45 cells are `[LOW-N]` (n<20, several n=1–4)** — per process rules,
these are explicitly **not** treated as reliable strategic facts. Scaling to 5,000–20,000
episodes (§12) is necessary before the full matchup matrix is trustworthy, especially for rarer
archetypes like Mega Lopunny ex (n=66 total games) or Teal Mask Ogerpon ex (n=45).

## 8. Temporal differences (Step 2.2 target, Step 5 temporal level)

**[RESULT] The meta is NOT stable — it shifted dramatically across the 8-week window**:

| Archetype | EARLY (wk 1–3) | MIDDLE (wk 4–5) | RECENT (wk 6–8) |
|---|---|---|---|
| UNLABELED | **52.1%** | 17.2% | **2.9%** |
| Mega Lucario ex | 16.7% | 1.8% | 1.5% |
| Marnie's Grimmsnarl ex | 8.9% | 19.4% | **43.1%** |
| Fezandipiti ex | 8.1% | **30.0%** | 15.7% |
| Mega Kangaskhan ex | 1.9% | 12.6% | 8.4% |
| Mega Lopunny ex | 0.3% | 0.8% | 8.1% |
| Teal Mask Ogerpon ex | 0.3% | 0.2% | 5.6% |

**[RESULT] Three clear regimes**: EARLY is dominated by UNLABELED decks (52%) plus Mega Lucario
ex (one of our 4 known local sample decks, 16.7%) — consistent with players starting from the
official sample-notebook decks and ad-hoc early builds before the field matured. By RECENT,
UNLABELED collapses to 2.9% and **Marnie's Grimmsnarl ex alone reaches 43.1% usage** —
**directionally consistent with, though not numerically identical to**, the pre-existing
community snapshot (`live_meta_snapshot_2026-07-31/tier_and_usage.csv`, pulled in a prior
session) which reported Marnie's Grimmsnarl ex at 63.8% usage on that single date. The
difference in magnitude (43% pooled-over-3-weeks here vs. 63.8% on one specific day) is expected
given the RECENT bucket spans 3 weeks including some of the MIDDLE-period transition, not just
2026-07-31 itself — this pilot broadly **corroborates** rather than contradicts the earlier
snapshot.

**[RESULT] Direct answer to the phase prompt's "is the 07-31 snapshot still representative"
question**: **partially, and trending further toward Grimmsnarl-dominance, not away from it** —
the archetype that was already dominant on 07-31 continued gaining share into the RECENT period
of this pilot (which extends to 08-10). This is a meaningfully different picture from the phase
prompt's framing of "8 roughly co-equal named archetypes" — the real meta has one clearly
dominant archetype in the most recent weeks, with the rest as a long tail.

**[HYPOTHESIS]** The EARLY-period UNLABELED spike is very plausibly the community's
still-forming deck pool (early experimentation, sample-deck reuse) rather than a systematically
different archetype set — consistent with the score-convergence pattern found in
`reports/episode_sampling_plan.md` §1 (ratings only stabilize after ~2 weeks). Not fully
confirmed without clustering the EARLY UNLABELED decks specifically.

## 9. Deck variance within top archetypes (Step 6)

**[RESULT]** Major difference in how "solved" each archetype's build is:

| Archetype | Distinct lists | Games | Top-list share | Core cards (in 100% of lists) |
|---|---|---|---|---|
| Cynthia's Garchomp ex | 7 | 79 | **0.85** | 12 |
| Marnie's Grimmsnarl ex | 32 | 487 | 0.52 | 10 |
| Fezandipiti ex | 62 | 353 | 0.46 | **1** |
| Dragapult ex | 26 | 109 | 0.32 | 8 |
| Mega Lucario ex | 39 | 151 | 0.32 | 5 |
| Mega Kangaskhan ex | 22 | 148 | 0.25 | **1** |

**[RESULT] Cynthia's Garchomp ex is essentially "solved"** — only 7 distinct 60-card lists
across 79 games, one list covering 85% of them, 12 cards fixed across every copy. **Fezandipiti
ex and Mega Kangaskhan ex are the opposite** — only the single namesake ex Pokémon is universal;
everything else (energy split, ball/search package, support Pokémon) varies build-to-build. This
is a genuinely useful finding for Part 3 (decklist discovery): claiming a single "the Fezandipiti
ex decklist" would be misleading — there isn't one, there are at least 62 meaningfully different
approaches sharing only the headline card. Marnie's Grimmsnarl ex sits in between: consistent
core (10 fixed cards) but real tech-slot variation (Night Stretcher 30/32, Team Rocket's Petrel
24/32, Froslass 22/32 — clearly optional inclusions).

## 10. Game-length distribution (Step 8, extending Part 0)

**[RESULT] Corrected picture vs. Part 0's tiny 7-file sample**: in a properly stratified
1,000-episode random draw, **only 1/1000 (0.1%) games have fewer than 20 steps** — Part 0's
observation that 3/7 sampled files were very short was a small-sample artifact of day-1
(launch-day) sampling, not representative of the general population. Main-sample step-count
distribution: min=19, p25=122, median=153, p75=183, max=369.

**[RESULT] Outcome-type breakdown reveals the real explanation for extreme file sizes** (this
required fixing a bug in the initial parser, which conflated true draws with
error/timeout-terminated games — see `src/meta_analysis/episode_parser.py`'s `outcome_type`
field, added this session):

| Population | DECISIVE | DRAW (true 0/0) | ERROR/TIMEOUT |
|---|---|---|---|
| Main stratified sample (n=1000) | 997 (99.7%) | 3 (0.3%) | 0 (0.0%) |
| Anomaly-short, <200KB (n=20) | 12 (60%) | 0 | **8 (40%)** |
| Anomaly-long, >20MB (n=20) | 9 (45%) | 2 (10%) | **9 (45%)** |

**[RESULT] A normal random game essentially never errors or times out (0/1000 in the main
sample)** — reliability issues are concentrated almost entirely in the file-size tails:
- **Very short files are disproportionately agent crashes**, not fast decisive play: 8/20
  (40%) of the <200KB sample ended with one side's status = `ERROR` (malformed/crashing
  action), reward pattern `(1, None)` — the "winner" only won because the opponent's agent
  broke, not because of deck strength. Only 12/20 were genuine short decisive games.
- **Very long files are disproportionately timeouts or true stalemate draws**: 9/20 (45%) ended
  `TIMEOUT` (one side exceeded the documented 10-minute wall-clock match budget from
  `docs/environment.md`), 2/20 (10%) were genuine `(0,0)` draws with both sides reaching `DONE`
  (i.e. hit the step/episode cap without a winner). **A clean threshold was found**: every
  anomaly-long episode with >1,000 recorded steps (7/7) ended in a draw or timeout; every one
  with <1,000 steps (13/13) had a decisive winner except 2 draws right at the boundary (826,
  1045 steps). This is strong, if small-n, evidence that the extreme tail is a distinct
  "stuck/grinding" population, not merely "longer strategic games."

**[RESULT] Answering Part 0's open [HYPOTHESIS] directly**: very short/long games are **not**
representative of normal play and should be **excluded from win-rate and archetype
statistics** (already done in this report, §6–9 use `DECISIVE`-only games) but **retained and
studied separately** as a reliability signal — e.g., an opponent-archetype classifier trained
on this data should not learn from ERROR/TIMEOUT episodes as if they were normal games.

## 11. Unexpected findings

1. **The `outcome_type` bug**: the initial naive winner-parsing logic (`reward∈{-1,1}` else
   draw) silently conflated true draws with agent crashes/timeouts — caught only by manually
   inspecting a "draw" episode and finding `statuses=['DONE','ERROR']`. Fixed and re-run; this
   is exactly the kind of bug raw-data preservation is meant to catch (re-derivable from the
   preserved `pilot_episodes_v1.csv` + source JSON without re-downloading).
2. **Novel archetype families genuinely exist** and are not small — Abra/Kadabra/Alakazam alone
   appeared in 61 games in a 1,000-episode sample, more than 4 of the 8 "known" live-meta
   archetypes (Team Rocket's Mewtwo ex, Mega Lopunny ex, Teal Mask Ogerpon ex, Mega Abomasnow ex
   individually all had fewer games).
3. **Archetype win rates cluster near 50% almost regardless of archetype** — a reminder that
   this is a rating-matched ladder, not a fixed metagame tournament; win rate alone cannot be
   used to rank deck power without controlling for opponent rating, which this pilot's data does
   not currently capture (manifest has `avg_score` per episode but this pilot didn't join it in;
   flagged for the next iteration).
4. **The meta shift is large enough that EARLY-period statistics are close to useless for
   predicting RECENT-period matchups** — e.g. Mega Lucario ex was 16.7% of EARLY games and 1.5%
   of RECENT games. Any future scaling to 5,000–20,000 episodes should weight toward
   RECENT/current data if the goal is deployment-relevant meta knowledge, not toward a uniform
   56-day sample.

## 12. Recommendation for scaling to 5,000–20,000 episodes

**[RESULT]** The pilot demonstrates the sampling/parsing/tagging pipeline works cleanly at 1,040
episodes with zero parse failures and clear, actionable signal. Recommended next-iteration
changes before scaling:

1. **Weight toward RECENT weeks, not uniform-across-56-days** — given §8's finding that the meta
   has shifted substantially, a scale-up aimed at "what should the meta-aware agent actually
   expect to face" should oversample the last 2–3 weeks rather than replicate this pilot's
   equal-per-week design (which was correct for *detecting* the shift, but is not the right
   weighting for *deploying against* the current meta).
2. **Join `avg_score`/rating into the per-episode record** — needed to check whether the
   near-50%-everywhere win rates (§6, §11.3) really are a matchmaking artifact or whether some
   genuine skill differences leak through; not done this pilot, cheap to add (already in the
   manifest, just not joined into the analysis).
3. **Cluster the 178 distinct UNLABELED decks into named families** — §6 hand-identified 5
   families by inspection; a real pass (e.g. connected-components over shared "core cards" the
   way §9 identified cores) would likely resolve most of the 25% UNLABELED bucket into proper
   archetypes before Part 3 (decklist discovery) and Part 6 (opponent classifier) are built on
   top of it.
4. **Scale target: 8,000–10,000 episodes, weighted 70% RECENT / 20% MIDDLE / 10% EARLY**, rather
   than the prompt's flat 5,000–20,000 range — sized to get every one of the 8 known archetypes
   past n=100 decisive games (Iono's/Mega Abomasnow currently sit at n=10–15, too small for
   their own matchup-matrix rows) while respecting time/disk cost (§2–3 extrapolation puts this
   around 5–7 hours download + ~15 minutes parsing, ~35–45GB disk).

**[QUESTION]** Whether the near-50%-win-rate pattern survives once rating is controlled for is
the single most important open question before Part 2's counter-deck-identification work — if
it's purely a matchmaking artifact, "which archetype is strongest" may not be answerable from
win rate at all, and a different signal (e.g. rating trajectory of players who switch onto an
archetype) would be needed instead.

---

**Stop condition met per Part 1 Step 9.** Per-episode and per-deck raw pilot data preserved at
`strategy/meta_analysis/pilot_episodes_v1.csv` / `pilot_deck_registry_v1.csv` (not overwritten
by future runs — future scale-ups should write new versioned files). Not proceeding to the
5,000–20,000-episode scale-up or any of Parts 2–14 without explicit go-ahead, per standing
process rules and this phase prompt's own checkpoint requirement.
