# Real Meta v2

Tags used throughout: **[FACT]** verified directly from source data, **[RESULT]**
computed this session from the dataset described below, **[HYPOTHESIS]**
plausible/untested, **[INFERRED]** derived via a statistical resolution method that
was validated and found weak/unreliable (see §6), **[QUESTION]** open.

## 1. Dataset

**[FACT]** **3,499 episodes** (6,998 side-rows in the normalized long-format
dataset), built via an incremental streaming pipeline
(`tools/extract_meta_v3.py`) that never held more than one raw episode's JSON in
memory at a time and discarded it immediately after field extraction. 1,125 of
these episodes were reused at zero extra cost from already-parsed compact CSVs
left over from an earlier (superseded) scale-up attempt this session; 2,374 were
newly streamed one-at-a-time with checkpointing every 50 episodes
(`results/meta/processing_checkpoint.json`). 1 episode failed (a 404 from the
Kaggle API, logged with reason in `results/meta/processing_failures.csv`) and was
skipped without stopping the pipeline.

**[FACT]** Date range: **2026-06-16 to 2026-08-10** (the full 56-day span of the
official episode-dump datasets).

**[RESULT]** Sample distribution, stratified by time into 3 periods (EARLY = the
first 3 of 8 calendar weeks, MIDDLE = weeks 4-5, RECENT = weeks 6-8, boundaries
computed from the manifest's own date range):

| Period | Episodes | % |
|---|---|---|
| EARLY | 500 | 14.3% |
| MIDDLE | 1,000 | 28.6% |
| RECENT | 1,999 | 57.1% |

This lands inside the requested 10-15% / 25-30% / 55-60% bands. Sampling within
each period was stratified evenly across calendar days (not a simple "first N"
or single-day sample), seeded and reproducible
(`tools/build_meta_v3_selection.py`, `tools/extract_meta_v3.py`).

**[RESULT] Data quality** (full detail in `reports/meta_data_quality.md`):
duplicate episode_ids = 0; missing `player_rating` = 0.23% (16/6,998 rows, all
episodes lacking manifest score data); missing `player_deck_hash` / `result` /
`timestamp` / `game_length` = 0.00% each; 0 suspicious values found
(`rating<=0`, `game_length<=0`, identical player/opponent IDs, impossible
results). **The one important caveat is that `player_rating`/`opponent_rating`
are INFERRED, not observed — see §6.**

**[FACT]** Unique players (team names, both sides pooled): **960**. Unique exact
decklists (`deck_hash`): **619**, clustering into **83 archetype/family groups**
(`cluster_id` — see §5 methodology).

---

## 2. Meta Overview

**[RESULT]** Archetype-level frequency and win rate (DECISIVE games only, both
sides pooled, n = 6,982 deck-slots across 3,491 decisive episodes):

| Archetype | Games | Share | Win rate | 95% CI | Confidence |
|---|---|---|---|---|---|
| Marnie's Grimmsnarl ex | 2,225 | 31.9% | 0.490 | [0.470, 0.511] | USABLE |
| Fezandipiti ex | 1,355 | 19.4% | 0.471 | [0.444, 0.498] | USABLE |
| Mega Kangaskhan ex | 668 | 9.6% | 0.497 | [0.459, 0.535] | USABLE |
| Team Rocket's Mewtwo ex | 349 | 5.0% | 0.513 | [0.461, 0.565] | USABLE |
| Dragapult ex | 337 | 4.8% | 0.552 | [0.499, 0.604] | USABLE |
| Cynthia's Garchomp ex | 296 | 4.2% | 0.527 | [0.470, 0.583] | USABLE |
| Mega Lopunny ex | 289 | 4.1% | 0.554 | [0.496, 0.610] | USABLE |
| Mega Lucario ex | 262 | 3.8% | 0.515 | [0.455, 0.575] | USABLE |
| Teal Mask Ogerpon ex | 199 | 2.9% | 0.558 | [0.488, 0.625] | USABLE |
| UNLABELED_CLUSTER_01 | 191 | 2.7% | 0.518 | [0.448, 0.588] | USABLE |
| *(73 more clusters, mostly <2% share)* | | | | | |

**[RESULT] Marnie's Grimmsnarl ex is the single dominant deck at nearly a third
of all games (31.9%)**, more than the next two archetypes combined. Fezandipiti
ex is a clear second (19.4%). Everything else is a long tail under 10% each.

**[RESULT] Deck-family resolution improved substantially over the pilot**: only
**13.8% of deck-slots are UNLABELED-derived clusters** (i.e. not one of the 12
previously-known named archetypes) at this scale, down from 25% in the
1,040-episode pilot (`reports/real_meta_pilot_v1.md`). The deterministic
clustering method (§5) resolved most of what used to be an undifferentiated
"UNLABELED" bucket into named families like `UNLABELED_CLUSTER_01`
(Abra/Kadabra/Alakazam, 2.7% share) and `UNLABELED_CLUSTER_02`
(Archaludon ex family, 1.8% share).

**[RESULT] Win rates cluster near 50% for every archetype (0.44-0.56)** — this is
expected on a Bayesian-skill-matched ladder (matchmaking pairs similar-rated
opponents) and should **not** be read as "all decks are equally strong." See §4
and §6 for what raw win rate can and cannot tell us here.

---

## 3. Meta Evolution

**[RESULT]** Share and win rate by period for the 16 archetypes with ≥30 games
overall (full table: `results/meta/deck_stats.csv`, `analysis_out_v3.txt`):

| Archetype | Share EARLY | Share MIDDLE | Share RECENT | WR EARLY | WR MIDDLE | WR RECENT |
|---|---|---|---|---|---|---|
| Marnie's Grimmsnarl ex | 8.5% | 18.6% | **44.3%** | 0.612 | 0.491 | 0.484 |
| Fezandipiti ex | 8.1% | **30.2%** | 16.8% | 0.531 | 0.459 | 0.474 |
| Mega Kangaskhan ex | 2.1% | 14.9% | 8.8% | 0.524 | 0.490 | 0.501 |
| Team Rocket's Mewtwo ex | 0.9% | 6.0% | 5.5% | 0.444 | 0.563 | 0.489 |
| Dragapult ex | 6.4% | 4.5% | 4.6% | 0.422 | 0.607 | 0.571 |
| Mega Lopunny ex | 0.2% | 0.7% | 6.8% | 0.500 | 0.286 | 0.568 |
| Mega Lucario ex | **17.5%** | 1.4% | 1.5% | 0.474 | 0.556 | 0.617 |
| Teal Mask Ogerpon ex | 0.3% | 0.3% | 4.8% | 1.000 | 0.800 | 0.545 |

**[RESULT] The meta has shifted hard, confirming and sharpening the pilot's
finding**: Marnie's Grimmsnarl ex grew from 8.5% (EARLY) to 44.3% (RECENT) —
now capturing nearly half of all recent games, up from the pilot's 43.1%
RECENT-period estimate on a much smaller sample. This is now a **high-confidence**
finding (n=1,769 RECENT-period games for this one archetype alone).

**[RESULT] Fezandipiti ex peaked in MIDDLE (30.2%) and has since declined to
16.8% in RECENT** — a genuine rise-then-decline pattern, not noise (n in the
hundreds at every period).

**[RESULT] Mega Lucario ex and the largest early UNLABELED clusters were an
EARLY-period phenomenon that has essentially disappeared**: Mega Lucario ex fell
from 17.5% (EARLY, one of the 4 official local sample decks) to 1.5% (RECENT).
Rising decks in RECENT: Mega Lopunny ex (0.2% → 6.8%) and Teal Mask Ogerpon ex
(0.3% → 4.8%) are the two clearest **rising** decks with adequate sample
(n=273 and n=191 in RECENT respectively). **Declining**: Fezandipiti ex, Mega
Lucario ex. **Stable**: Mega Kangaskhan ex (8-15% across all 3 periods).

**[RESULT] Win-rate changes across periods are mostly within noise given the
per-period sample sizes**, with one exception worth flagging as at least
**moderate confidence**: Marnie's Grimmsnarl ex's EARLY win rate (0.612, n=85)
is well above its MIDDLE/RECENT win rate (~0.49, n=371/1,769) — but n=85 for the
EARLY estimate keeps this at moderate rather than high confidence, and is
plausibly explained by EARLY-period rating non-convergence (see
`reports/episode_sampling_plan.md` §1) rather than a real deck-strength change.

---

## 4. Matchups

**[RESULT]** Matchup identity used here is the **archetype/cluster level**
(`cluster_id`), not raw exact-decklist (`deck_hash`) — documented explicitly
because at deck_hash granularity, of 1,462 exact-deck matchup pairs observed,
essentially all are far below any usable sample size (619 distinct decks means
most exact pairings are seen only 1-3 times). `results/meta/matchup_matrix.csv`
contains **both** granularities (a `level` column distinguishes `EXACT` from
`ARCHETYPE` rows) so the raw exact-deck data is not discarded, but the
report's conclusions below use `ARCHETYPE` rows only.

**[FACT] Confidence thresholds used** (as specified): <20 games = INSUFFICIENT,
20-49 = LOW_CONFIDENCE, ≥50 = USABLE.

**[RESULT]** Of 289 archetype-vs-archetype pairs observed: **11 USABLE, 15
LOW_CONFIDENCE, 263 INSUFFICIENT.** The 11 USABLE pairs (all involving the top
~8 archetypes) are the only matchup conclusions this report treats as reliable:

| Row deck | Col deck | n | Row win rate | 95% CI |
|---|---|---|---|---|
| Team Rocket's Mewtwo ex | Fezandipiti ex | 85 | **0.765** | [0.664, 0.842] |
| Marnie's Grimmsnarl ex | Teal Mask Ogerpon ex | 77 | **0.182** | [0.112, 0.282] |
| Mega Kangaskhan ex | Marnie's Grimmsnarl ex | 210 | 0.548 | [0.480, 0.614] |
| Fezandipiti ex | Dragapult ex | 76 | 0.355 | [0.257, 0.467] |
| Marnie's Grimmsnarl ex | Dragapult ex | 76 | 0.395 | [0.293, 0.507] |
| Fezandipiti ex | Cynthia's Garchomp ex | 57 | 0.561 | [0.433, 0.682] |
| Fezandipiti ex | Marnie's Grimmsnarl ex | 417 | 0.456 | [0.409, 0.504] |
| Fezandipiti ex | Mega Kangaskhan ex | 160 | 0.519 | [0.442, 0.595] |
| Team Rocket's Mewtwo ex | Marnie's Grimmsnarl ex | 134 | 0.403 | [0.324, 0.488] |
| Marnie's Grimmsnarl ex | Mega Lopunny ex | 98 | 0.429 | [0.335, 0.527] |
| Marnie's Grimmsnarl ex | Cynthia's Garchomp ex | 98 | 0.429 | [0.335, 0.527] |

**[RESULT] Strongest favorable matchup found (high confidence)**: **Team
Rocket's Mewtwo ex beats Fezandipiti ex 76.5% of the time** (n=85, CI
[0.664, 0.842] — does not come close to touching 0.5). This is a credible,
statistically distinguishable counter-relationship, not a small-sample artifact.

**[RESULT] Strongest unfavorable matchup found (high confidence)**: **Marnie's
Grimmsnarl ex loses to Teal Mask Ogerpon ex 81.8% of the time** (n=77, CI
[0.112, 0.282]) — notable because Marnie's Grimmsnarl ex is the single most
popular deck in the meta (31.9% share) yet has a hard, credible counter that is
itself a rising deck (§3).

**[RESULT] Weakest/most ambiguous matchups**: the two largest archetypes
against each other, Fezandipiti ex vs Marnie's Grimmsnarl ex, sit at 0.456
[0.409, 0.504] — essentially even, CI straddles 0.5, n=417 is the largest cell
in the whole matrix so this is a genuine (not sample-starved) near-50/50 result.

**[RESULT] 263 of 289 pairs remain INSUFFICIENT** — mostly combinations
involving the 70+ small UNLABELED clusters or rare named archetypes (Iono's,
Mega Abomasnow ex). Scaling the dataset further would only fix a modest
additional number of these (see §10) since most represent genuinely rare
pairings, not merely an under-sampled common one.

---

## 5. Deck Variants

**[FACT] Methodology**: exact decklists are clustered deterministically by the
set of "headline" (ex / Mega ex) Pokemon names present — the same convention
already used to name the 12 known archetypes (e.g. the presence of "Grimmsnarl
ex" defines "Marnie's Grimmsnarl ex"). Two exact decklists land in the same
cluster **iff** they share the identical set of headline Pokemon names; no
similarity threshold, no ML — fully deterministic and reproducible from the card
data + decklist alone (`src/meta_analysis/deck_clustering.py`). This is
explicitly **not** a claim of semantic/strategic similarity beyond shared
headline attackers — a documented limitation, not an invented one: builds that
run a different *number* of headline attackers (e.g. 2-attacker vs 3-attacker
versions of a related core strategy) can fragment across multiple clusters.

**[RESULT]** `results/meta/deck_variants.csv` — 16 archetype/cluster variants
with ≥30 games. Two illustrative extremes:

- **Cynthia's Garchomp ex: only 13 distinct exact decklists** across 296 games —
  a comparatively "solved" archetype with a small, tightly-defined build space.
- **Fezandipiti ex: 87 distinct exact decklists** across 1,355 games — no single
  build dominates; key variable cards include Buddy-Buddy Poffin (present in
  ~99% of variants, near-universal), Rare Candy, Boss's Orders, and Dudunsparce
  as common-but-not-universal tech.
- **Marnie's Grimmsnarl ex: 47 distinct decklists**, 2,225 games — an
  intermediate case.

**[RESULT]** Full key-card-difference detail for every major archetype is in
`results/meta/deck_variants.csv`'s `key_card_differences` column (top 6 most
common non-universal cards per cluster, with presence fraction).

---

## 6. Rating Analysis

**[INFERRED — see caveat] Rating distribution** (3,491 decisive episodes with
resolvable score data): min=340.3, p25=1046.6, median=1090.1, p75=1130.0,
max=1347.4, mean=1085.1.

**[FACT] Critical methodology caveat, stated once here in full**: the episode
manifest gives only an *unordered* pair of scores per match
(`min_score`, `sum_score - min_score`) — never which side is which — and the raw
episode JSON has no rating field at all. `player_rating`/`opponent_rating` in
this dataset are the output of a deck-based alternating-assignment statistical
resolution (`src/meta_analysis/rating_resolution.py`), **not observed values**.

**[RESULT] This resolution method was explicitly validated and found to carry
no reliable signal**: a labeled check (does the resolved-higher-rated side
actually win more often?) returns ~49-53% across every test performed this
session, including at this full 3,491-episode scale and restricted to
frequently-seen decks/teams — statistically indistinguishable from a coin flip.
A pooled logistic regression of win probability on the resolved rating
difference found a near-zero, not-clearly-nonzero slope.

**[RESULT] Win rate by rating bucket (quintiles of inferred `player_rating`,
all decks pooled) is flat**, consistent with the above validation failure —
**not** evidence that skill doesn't matter, but evidence that this particular
rating signal cannot currently be resolved to a usable per-side value from this
data source:

| Rating bucket | Games | Win rate | 95% CI |
|---|---|---|---|
| 340-1034 | 1,397 | 0.508 | [0.481, 0.534] |
| 1034-1074 | 1,396 | 0.506 | [0.480, 0.532] |
| 1074-1105 | 1,396 | 0.469 | [0.443, 0.495] |
| 1105-1141 | 1,396 | 0.513 | [0.487, 0.539] |
| 1141-1347 | 1,397 | 0.505 | [0.479, 0.531] |

**[RESULT] The same flat pattern holds within every major archetype's own
rating-bucket breakdown** (`results/meta/rating_analysis.csv`, `row_type=
DECK_BY_BUCKET`) — no archetype shows a clean monotonic win-rate trend across
its own rating tiers.

**[RESULT — acceptable correlational framing]** Average inferred player rating
does differ modestly by archetype: Team Rocket's Mewtwo ex (1,118), Mega
Kangaskhan ex (1,113), Fezandipiti ex (1,102) skew toward the higher end; Mega
Lucario ex (1,012) and Mega Abomasnow ex (684) skew lower — **Mega Lucario ex
and Mega Abomasnow ex are associated with lower-rated players** in this dataset
(both are also EARLY-period-heavy decks, §3, and EARLY-period ratings had not
yet converged per prior-session findings — so this may reflect the rating
system's own convergence period more than genuine archetype-skill association).
This is explicitly a correlational, not causal, observation.

**[QUESTION] Whether the near-null rating-outcome relationship is a genuine
property of this game/ladder or an artifact of the unresolvable score-ordering
problem remains open** — it cannot be settled by collecting more episodes from
this same source, since the ambiguity is structural (every episode has the same
unresolvable ordering problem), not a sample-size problem. Resolving it would
need either a different data field (a real per-agent rating snapshot, which the
organizer does not appear to publish per-episode) or a fundamentally different
identification strategy than attempted here.

---

## 7. Short Games

**[RESULT] Game-length distribution** (decisive episodes, `game_length` =
recorded steps): p5=70, p25=131, median=160, p75=189, p95=237.

**[RESULT] Short-game threshold set at the 10th percentile: ≤97 steps`**,
chosen because the distribution has no other natural break point (verified in
the prior pilot session that a hard floor near 20 steps separates genuine fast
games from a distinct crashed/errored population — that floor is far below the
10th-percentile threshold used here, confirming these are legitimate fast
decisive games, not anomalies; see `reports/real_meta_pilot_v1.md` §10).

**[RESULT] Short-game (≤97 steps) archetype performance, USABLE-confidence
only**:

| Archetype | Games | Win rate | Overall win rate | Δ |
|---|---|---|---|---|
| Fezandipiti ex | 135 | **0.652** | 0.471 | **+18.1pp** |
| Marnie's Grimmsnarl ex | 84 | 0.548 | 0.490 | +5.7pp |
| Mega Kangaskhan ex | 109 | **0.239** | 0.497 | **-25.8pp** |

**[RESULT] Fezandipiti ex performs disproportionately well in short games**
(65.2% vs its 47.1% overall win rate, both USABLE-confidence, n=135) — a
genuinely large and credible gap, consistent with an aggressive/fast-attacker
archetype identity. **Mega Kangaskhan ex performs disproportionately poorly in
short games** (23.9% vs 49.7% overall, n=109) — also large and credible,
consistent with a ramp/setup-dependent archetype that is punished when games
end before it can establish its board.

---

## 8. Key Findings

1. **[RESULT, high confidence]** Marnie's Grimmsnarl ex is the dominant deck at
   31.9% overall share and 44.3% of RECENT games — continuing and sharpening a
   trend already visible in the pilot.
2. **[RESULT, high confidence]** The meta has shifted substantially over the
   56-day window: Mega Lucario ex (17.5%→1.5%) and multiple early UNLABELED
   clusters have nearly vanished; Mega Lopunny ex (0.2%→6.8%) and Teal Mask
   Ogerpon ex (0.3%→4.8%) are the clearest rising decks.
3. **[RESULT, high confidence]** Team Rocket's Mewtwo ex beats Fezandipiti ex
   76.5% of the time (n=85) — the single strongest, best-evidenced
   counter-relationship found.
4. **[RESULT, high confidence]** Marnie's Grimmsnarl ex — despite being the
   most popular deck — loses to Teal Mask Ogerpon ex 81.8% of the time (n=77),
   a hard credible counter to the format's dominant deck.
5. **[RESULT, high confidence]** Fezandipiti ex is disproportionately strong in
   short games (+18pp vs its overall win rate); Mega Kangaskhan ex is
   disproportionately weak in short games (-26pp).
6. **[RESULT, high confidence]** Deterministic archetype clustering resolved
   the "UNLABELED" population from 25% (pilot) to 13.8% of games at this scale,
   recovering several previously-uncatalogued families (Abra/Kadabra/Alakazam,
   Archaludon ex, and others).
7. **[RESULT, high confidence — a validated null result]** The rating field
   available in this data source **cannot be reliably resolved to per-side
   values**, and the resulting inferred-rating-vs-win-rate relationship is flat
   at every level tested (overall, by bucket, and within every major
   archetype). This is not "no effect exists" — it is "this data source cannot
   currently measure it."
8. **[RESULT, moderate confidence]** Raw archetype win rates cluster near 50%
   (0.44-0.56) for essentially every archetype — expected under Bayesian
   skill-matched matchmaking, and (per finding 7) not something this session
   could rating-adjust away, so it should not be read as "all decks are
   equally strong."
9. **[RESULT, high confidence]** Deck-list flexibility varies hugely by
   archetype: Cynthia's Garchomp ex has only 13 distinct builds across 296
   games (comparatively solved); Fezandipiti ex has 87 distinct builds across
   1,355 games (no dominant build).
10. **[RESULT, moderate confidence]** Even at 3,499 episodes, 263 of 289
    archetype-vs-archetype matchup cells remain below a usable sample size —
    the top ~8 archetypes' matchups against each other are now well-covered,
    but the long tail of rarer archetype pairings is not, and would need a
    much larger (and likely combinatorially impractical) sample to fully
    resolve.

---

## 9. Limitations

- **Rating is unresolved, not just uncertain** (§6) — this is the single
  largest limitation. Every rating-conditioned claim in this report is
  correlational at best and should be treated with real skepticism.
- **Sampling is a ~1.3% draw of the full 278,457-episode population** — large
  enough for archetype-level and top-matchup conclusions, not for exhaustive
  matchup-matrix or rare-archetype coverage.
- **Archetype identity is a deterministic heuristic** (shared headline-Pokemon
  set), not a verified ground-truth grouping — it can fragment genuinely
  related builds that vary in attacker count, and was not cross-validated
  against any external labeling beyond the pilot's hand-identified families.
- **EARLY-period statistics are the least reliable period slice** — the
  competition's Bayesian ratings had not converged during the first ~2 weeks
  (prior-session finding), so EARLY win rates and the EARLY-vs-later
  comparisons in §3 carry extra uncertainty beyond what their raw n suggests.
- **Selection bias from reuse**: 1,125 of 3,499 episodes were carried over from
  an earlier stratified sample built under slightly different (now-superseded)
  proportions; both the reused and newly-streamed portions used seeded random
  sampling within each period/day, so this is not expected to introduce a
  systematic bias, but it is a deviation from a single uniform sampling pass.
- **Team/player identity (`player_id`) is a team display name string**, not a
  stable account ID verified against any Kaggle account registry — assumed
  stable based on prior-session cross-checks (same deck_hash repeatedly played
  by the same team name), not independently re-verified this session.
- **1 episode failed to download** (404, logged) — negligible (0.03% of the
  target selection) but noted per the "explain every filtering decision" rule;
  it was not filtered, it simply could not be fetched.

---

## 10. Recommended Next Steps

**[RESULT] Adaptive-scaling assessment (required by the phase prompt, §21)**:
the major archetype-level and top-matchup conclusions in this report are
statistically stable at 3,499 episodes — the top ~9 archetypes all have
hundreds to thousands of games (USABLE confidence throughout), and 11
archetype-matchup pairs newly crossed the USABLE (≥50) threshold that were
LOW-N or absent in the 1,040-episode pilot. **Recommendation: STOP at 3,499
episodes for this phase** — do not automatically scale to 5,000/7,500/10,000
(see §21 justification below).

**Why not scale further right now**:
1. The rating-resolution problem (§6) is structural, not sample-size-limited —
   more episodes from this same source will not fix it.
2. Matchup-matrix completeness for the long tail of rare archetype pairs (§4,
   §9) would need an amount of additional data disproportionate to the
   marginal value gained, given the combinatorial number of possible
   archetype pairs (83 clusters → 3,403 possible pairs) versus the realistic
   game-count ceiling for rare pairings.
3. The competition's Simulation-track deadline is close; further large-scale
   data collection has a real opportunity cost against acting on what this
   report already supports.

**If a future session does need more data, it should be targeted, not
blanket**: specifically re-sampling toward the ~15 LOW_CONFIDENCE matchup
pairs (20-49 games) that are closest to crossing into USABLE, rather than an
undifferentiated scale-up.

**Suggested follow-ups, not part of this phase**:
1. Use the §4 matchup findings (Team Rocket's Mewtwo ex > Fezandipiti ex;
   Teal Mask Ogerpon ex > Marnie's Grimmsnarl ex) as concrete, evidence-backed
   candidates if/when counter-deck selection work is authorized.
2. If rating ever becomes analyzable (e.g. a future organizer data release
   with resolved per-agent ratings), re-run §6 — the infrastructure
   (`rating_resolution.py`) and validation methodology are already in place.
3. Consider whether `player_id` (team display name) stability should be
   independently verified before it is used as a load-bearing identity key in
   any future longitudinal analysis.

**Per the phase prompt's explicit instruction, this report and its supporting
files are the stop condition — no agent/RL/MCTS/search/opponent-model work
should follow from this session without separate authorization.**
