# Episode Sampling Plan (Part 1, Step 1)

Tags: **[FACT]** verified from the full manifest, **[RESULT]** computed this session,
**[HYPOTHESIS]** plausible/untested, **[QUESTION]** open.

## 1. Manifest analysis (Step 1)

**[FACT]** Pulled `manifest.csv` from all 56 daily episode datasets (`tools/pull_daily_manifests.py`)
— **no episode content downloaded**, only the lightweight per-episode index (`episode_id,
create_time, avg_score, min_score, sum_score, agent_count, size_bytes`). Concatenated with a
`date` column into `data/episode_manifests/all_episodes_manifest.csv` (gitignored, 278,457 rows,
~28MB).

**[RESULT] Episode counts per day**: confirmed range 1,277 (2026-06-16, first day, clear
ramp-up outlier) to 7,819 (2026-06-17). From 2026-07-04 onward, daily volume settles into a
slow decline from ~5,000 to ~4,340–4,700/day, roughly stable for the second half of the range.

**[RESULT] `agent_count` is always exactly 2** across all 278,457 episodes — confirms every
episode is a standard 1v1 match, no multi-agent or bye-round episodes to special-case.

**[RESULT] `episode_id` is a single globally monotonically increasing counter across the whole
56-day range**, not per-day-reset and not random — verified directly: day *N*'s maximum
`episode_id` is always less than day *N+1*'s minimum (e.g. 2026-06-16 max `80233999` <
2026-06-17 min `80234350`; 2026-08-09 max `91474919` < 2026-08-10 min `91475487`). This means
`episode_id` order is a reliable chronological proxy within and across days, useful if `date`
is ever unavailable for a given episode reference.

**[RESULT] `size_bytes` distribution (proxy for game length/turn count)**, computed over all
278,457 rows:

| Percentile | Size |
|---|---|
| p0 (min) | 50KB |
| p5 | 1.19MB |
| p25 | 3.18MB |
| p50 (median) | 4.25MB |
| p75 | 5.23MB |
| p95 | 6.81MB |
| p99 | 8.48MB |
| p100 (max) | **269.7MB** |

Mean 4.25MB, matching Part 0's small-sample estimate almost exactly (4.2MB). Total: 1,183.8GB,
confirming the Part 0 correction to the phase prompt's ~40GB estimate.

**[RESULT] Heavy right tail, worth deliberate oversampling, not filtering out**: 1,133 episodes
(0.41%) exceed 10MB; 175 (0.06%) exceed 20MB; 67 (0.024%) exceed 100MB, up to the 269.7MB
maximum. This tail is a tiny share of episode *count* but essentially all of it maps to Part
0's short/long-game open question — a 200–270MB episode JSON implies an enormous number of
recorded steps (the largest sampled Part-0 file, 306 steps, was 9.4MB; linear extrapolation puts
a 270MB file at ~8,700 steps, near the `episodeSteps: 10000` cap seen in `configuration`).
**[HYPOTHESIS]**: the extreme tail is disproportionately games that hit or approach the
step/time cap (stalemates, loops, or decking-out grinds) rather than normal decisive games —
this is exactly what Step 8 (game-length analysis) needs to check empirically, not assume.

**[RESULT] Short-game population**: 3,236 episodes (1.16%) are under 500KB, consistent with
Part 0's observation that 1–2 turn games exist and aren't vanishingly rare.

**[RESULT] Score/rating trend across the 56 days** (from the pre-existing day-level index,
`strategy/meta_analysis/episodes_manifest_2026-08-10.csv`): median `avg_score` climbs sharply
from 627.8 (day 1) to ~1,180 by 2026-07-01, then oscillates in a much narrower 1,020–1,140 band
for the remaining ~40 days. **[HYPOTHESIS]**: this looks like Bayesian-rating convergence during
the first ~2 weeks (consistent with the competition's Gaussian skill-rating system settling as
more games accumulate per agent), after which the population is comparatively stable — i.e. the
first 1–2 weeks may not be representative of the "converged" ladder meta. This directly motivates
using date-based strata rather than treating all 56 days as interchangeable, and flagging
2026-06-16 (partial day, lowest volume, lowest score, likely launch day) as a probable outlier
to inspect separately rather than pool blindly into "EARLY."

## 2. Sampling design (Step 2 prep)

**[FACT]** The full date range splits into exactly **8 calendar weeks** (56 days / 7,
2026-06-16 → 2026-08-10) — used as the temporal strata instead of only 3, since Step 1's
manifest-only cost is negligible and finer temporal resolution is explicitly preferred when
cheap. These 8 weeks collapse cleanly into the required EARLY/MIDDLE/RECENT split for reporting
(weeks 1–2/3, 4–5, 6/7–8) while preserving enough resolution to see the rating-convergence
pattern found above.

**[RESULT] Two-part sample, implemented in `tools/build_pilot_selection.py`** (seeded RNG,
reproducible episode-ID list at `data/episode_manifests/pilot_selection.csv`):

1. **Main stratified sample — 1,000 episodes**: 8 weeks × 5 within-week size-quintiles × 25
   episodes/cell, quintile boundaries computed **per week** (not globally) so each week
   contributes an equal, length-diverse sample regardless of that week's own size
   distribution. This is the dataset used for win-rate/archetype/matchup/temporal analysis in
   Part 1 Steps 3–8 — it is a length-stratified random sample, not a length-biased one, since
   sampling only by pure random draw would under-represent the short/long tails relative to
   their behavioral importance while still keeping the *typical*-game population dominant (80%
   of the 1,000 falls in the 3 middle quintiles, matching the bulk of real games).
2. **Targeted anomaly sub-sample — 40 episodes (kept separate from main stats)**: 20 sampled
   from the <200KB tail, 20 from the >20MB tail (deliberately including a few of the most
   extreme cases up to 260MB, since Step 8 needs to characterize what the extreme tail actually
   *is*, not just confirm it exists). These are excluded from archetype/matchup/win-rate
   aggregates to avoid distorting them, and analyzed separately in the game-length section of
   the pilot report.

**[RESULT] Estimated pilot download volume: 5.71GB** (4.24GB main sample + 1.46GB anomaly
sample, the latter dominated by 6 files over 50MB). This is a deliberate, justified cost — not
an accident — since the anomaly sub-sample exists specifically to explain the size distribution
found in §1, and is <0.5% of the full 1.18TB dataset.

**[FACT]** Sampling is **without replacement across the whole selection** (`used_ids` tracked)
so no episode appears twice, and RNG-seeded so the exact selection is reproducible from
`data/episode_manifests/all_episodes_manifest.csv` alone (not re-randomized on re-run).

## 3. What this sample will and won't establish

**[FACT]** 1,040 episodes out of 278,457 is 0.37% of the total population — sufficient for a
first structural read (deck/archetype frequency, rough win rates, temporal shape) per-week at
n≈125/week, but **not** sufficient for high-confidence matchup-cell win rates on rare
archetype pairs (Part 1 Step 7 explicitly requires flagging low-n cells rather than treating
them as fact). The pilot's job is to determine whether scaling to 5,000–20,000 episodes is
worth the additional ~20–85GB it would cost, not to be the final answer.

**[QUESTION]** Whether 25 episodes/(week×quintile) is enough to see distinct decks (vs. just
one or two dominant decks per cell) will only be known once the pilot is parsed — flagged for
the pilot report's scaling recommendation (Step 9).
