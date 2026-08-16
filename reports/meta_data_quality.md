# Meta Data Quality Report (Part 4.1 v3)

Generated from `results/meta/episodes_summary.parquet` (6998 side-rows,
3499 episodes). Source: incremental streaming extraction
(`tools/extract_meta_v3.py`), reusing 1125
episodes already downloaded/parsed in earlier sessions plus
2374 newly streamed this session.

## Attempted / parsed / failed

From `results/meta/processing_checkpoint.json` (the authoritative counts from the
streaming run) and `results/meta/processing_failures.csv` (per-episode detail):

- Total episodes attempted (new-download stream only; the 1,125 reused episodes
  were already known-good from prior sessions, see below): **2,375**
- Successfully parsed and captured: **2,374**
- Failed: **1** -- episode `89919753`, stage `download`, reason `404 Client Error:
  Not Found` (the episode file was not present at the expected Kaggle dataset path
  at fetch time; not retried further after the standard 6-attempt backoff).
- Skipped (already processed on a prior run / resumed): 0 in this final run (all
  2,375 were fresh); the pipeline's resumability was exercised across 4 separate
  process restarts earlier in the session (see conversation/session log), each
  correctly skipping already-captured episode_ids.
- Reused (no re-download or re-parse; pulled from already-parsed compact CSVs left
  over from an earlier, superseded scale-up attempt this session): **1,125**
- **Total episodes in the final dataset: 3,499** (2,374 new + 1,125 reused)
- Duplicate episode_ids found in the final combined dataset: **0** (none)

## Missing fields (of 6998 side-rows)

| Field | Missing | % |
|---|---|---|
| player_rating (INFERRED, see caveat below) | 16 | 0.23% |
| player_deck_hash | 0 | 0.00% |
| result | 0 | 0.00% |
| timestamp | 0 | 0.00% |
| game_length | 0 | 0.00% |

**0.23%** of side-rows are missing at least one of
{player_rating, player_deck_hash, result, game_length}.

## IMPORTANT CAVEAT: player_rating / opponent_rating are INFERRED, not observed

The raw episode data (and the Kaggle manifest) never records which of a match's two
scores belongs to which side -- only an unordered pair
(`min_score`, `sum_score - min_score`) per episode, and the episode JSON itself has
no rating field at all (confirmed by direct inspection). `player_rating` /
`opponent_rating` here are the output of a statistical resolution method
(deck-based alternating assignment, see `src/meta_analysis/rating_resolution.py`)
that was validated against a labeled-outcome check (does the inferred-higher-rated
side actually win more often?) and found to show **no signal reliably above chance**
(~49-53% in every test run, including restricted to frequently-seen teams/decks).
Treat every rating-based number in this report as a labeled, low-confidence
**INFERRED** estimate, not a verified fact -- this is the single most important data
quality caveat in this dataset.

## Suspicious values

- `player_rating <= 0`: 0 rows
- `game_length <= 0`: 0 rows
- identical player_id / opponent_id in the same episode: 0 rows
- impossible `result` values (outside WIN/LOSS/DRAW/ERROR_OR_TIMEOUT/null): 0 (validated by construction in `result_for_side()`)

No suspicious records were removed -- flagged only, per the standing process rule
against silently discarding data. If any of the above counts are non-zero they are
visible in this report for manual follow-up, not filtered out of the analysis
dataset.

## Coverage

- Date range: 2026-06-16 to 2026-08-10
- Unique players (team names, both sides pooled): 960
- Unique exact decklists (deck_hash, both sides pooled): 619
- Period breakdown (episodes): {'RECENT': 1999, 'MIDDLE': 1000, 'EARLY': 500}
