# Meta Representation v1

Tags used throughout: **[FACT]** verified directly from source data, **[RESULT]**
computed this session from the dataset described below, **[DESIGN]** a modeling
choice made this session (threshold, formula, rule), **[LIMITATION]** an explicit
gap or caveat, **[QUESTION]** open. This phase is descriptive/representational —
no model was trained, no rating feature was used anywhere below.

Built by `tools/build_meta_representation_v1.py`, which reads only
`results/meta/episodes_summary.parquet` (the canonical Phase 4.1 dataset). No
additional raw episodes were downloaded.

---

## 1. Dataset

**[FACT]** Canonical dataset, unchanged from Phase 4.1: **3,499 episodes**
(6,998 side-rows; 6,982 decisive deck-slots after excluding 10 DRAW and 6
ERROR_OR_TIMEOUT episodes' side-rows), **619 unique exact decklists**
(`deck_hash`), clustering into **83 archetype/family groups** (`cluster_id`).
Period breakdown: EARLY 500 episodes / 1,000 deck-slots, MIDDLE 1,000 / 2,000,
RECENT 1,999 / 3,998 (period boundaries and definitions are Phase 4.1's, reused
unchanged here).

**[FACT]** Rating was **not** used as a feature anywhere in this phase's
outputs, per Phase 4.1's finding that it cannot be reliably resolved from this
data source (§6 of `reports/real_meta_v2.md`). `rating_analysis.csv` is
retained for documentation only and is not referenced by any file produced
this phase.

---

## 2. Archetype Universe

**[RESULT]** All 83 archetypes are represented, with no exceptions and no
`UNKNOWN` mappings — `results/meta/deck_to_archetype.csv` maps all 619 exact
decklists to exactly one archetype each (0 hashes map to more than one
archetype, 0 `UNKNOWN`). This was possible because Phase 4.1's deterministic
clustering (`src/meta_analysis/deck_clustering.py`) already assigns every deck
a cluster, either a known name or an `UNLABELED_CLUSTER_NN` id — there was no
genuinely unclassifiable deck in this dataset.

**[DESIGN]** For the 71 `UNLABELED_CLUSTER_NN` archetypes, a human-readable
`archetype_name` was derived from their representative deck's headline
(ex/Mega ex) Pokemon signature (the same convention Phase 4.1 already used to
name the 12 known archetypes), e.g. `UNLABELED_CLUSTER_02` →
**"Archaludon ex"**, `UNLABELED_CLUSTER_04` → **"Cornerstone Mask Ogerpon ex"**
(a distinct Ogerpon build from the already-named "Teal Mask Ogerpon ex").
`results/meta/archetype_canonical.csv` and `archetype_features.csv` use these
derived names; `deck_to_archetype.csv` also carries them.

**[RESULT]** The canonical per-archetype representation (Section 4 of the
phase prompt) is `results/meta/archetype_canonical.csv` — one row per
archetype with `archetype_id`, `archetype_name`, `representative_deck_hash`,
`representative_deck_list` (card names, not raw IDs), `exact_deck_count`,
`games`, `usage_share`, `wins`, `losses`, `win_rate`, and the three
period-share/win-rate sextet (`early_share`/`middle_share`/`recent_share`,
`early_win_rate`/`middle_win_rate`/`recent_win_rate`). The representative deck
is the single exact decklist with the most games seen within that archetype's
cluster.

---

## 3. Current Meta

**[RESULT]** Reproduces Phase 4.1's headline finding exactly from source:
Marnie's Grimmsnarl ex is dominant at **31.9% overall share, 44.3% of RECENT
deck-slots** (1,769 RECENT games), more than double the next archetype.
Fezandipiti ex is second (19.4% overall, 16.8% RECENT). Everything else is a
long tail — only 9 of 83 archetypes have ≥20 RECENT-period games (see §12,
Meta Prior).

| Archetype | Games | Usage share | Recent share | Win rate |
|---|---|---|---|---|
| Marnie's Grimmsnarl ex | 2,225 | 31.87% | 44.34% | 0.4903 |
| Fezandipiti ex | 1,355 | 19.41% | 16.82% | 0.4708 |
| Mega Kangaskhan ex | 668 | 9.57% | 8.75% | 0.4970 |
| Team Rocket's Mewtwo ex | 349 | 5.00% | 5.54% | 0.5129 |
| Dragapult ex | 337 | 4.83% | 4.61% | 0.5519 |
| Cynthia's Garchomp ex | 296 | 4.24% | 4.19%(*) | 0.5270 |
| Mega Lopunny ex | 289 | 4.14% | 6.84% | 0.5536 |
| Mega Lucario ex | 262 | 3.75% | 1.50% | 0.5153 |
| Teal Mask Ogerpon ex | 199 | 2.85% | 4.79% | 0.5578 |

(*) Cynthia's Garchomp ex recent_games=167; its filtered meta-prior share
(§12) uses only the 9-archetype filtered denominator, so numbers differ
slightly from the "of all 83" recent_share column — see §12 for which
normalization applies where.

Full 83-row table: `results/meta/archetype_canonical.csv` /
`archetype_features.csv`.

---

## 4. Archetype Strength

**[DESIGN]** Per the phase prompt's explicit instruction not to rank by raw
win rate alone, `archetype_features.csv` reports, for every archetype:
`win_rate`, `win_rate_wilson_lo`/`hi` (95% Wilson CI), `shrinkage_win_rate`
(Beta-Binomial shrinkage toward 0.5 with pseudo-count K=30 — chosen because
the pooled dataset is exactly 50/50 wins/losses by construction, making 0.5
the natural shrinkage prior; K=30 pulls a 30-game archetype about halfway back
toward 0.5 while leaving archetypes with hundreds/thousands of games nearly
unshrunk), and a `strength_class`.

**[DESIGN] strength_class rule** (reused the same 20/50/100 tiering as
matchup confidence, §5 below, for consistency):

- `LOW_SAMPLE_UNCERTAIN`: games < 50 (69 of 83 archetypes — most of the
  UNLABELED long tail)
- `HIGH_CONFIDENCE_STRONG`: games ≥ 50 AND wilson_lo > 0.50
- `HIGH_CONFIDENCE_WEAK`: games ≥ 50 AND wilson_hi < 0.50
- `HIGH_USAGE_AVERAGE`: games ≥ 50 AND the CI straddles 0.50

**[RESULT]** Distribution: 69 `LOW_SAMPLE_UNCERTAIN`, 13 `HIGH_USAGE_AVERAGE`,
1 `HIGH_CONFIDENCE_WEAK` (Fezandipiti ex, wilson_hi=0.4975 — just barely below
50%), **0 `HIGH_CONFIDENCE_STRONG`**. This is a direct, expected consequence
of Phase 4.1's finding 8 (win rates cluster 0.44–0.56 under Bayesian
skill-matched matchmaking) — not a bug: even Teal Mask Ogerpon ex's raw 55.8%
win rate has a Wilson lower bound of 48.8% at n=199, so it does not clear the
STRONG bar. **This is itself an informative result**: at this sample size, no
single archetype's *overall* field win rate is statistically distinguishable
from 50% — deck strength differentiation shows up in the *matchup* structure
(§5), not in aggregate win rate.

---

## 5. Matchup Structure

**[FACT]** Matchup identity is archetype-level (`cluster_id`), matching Phase
4.1's documented rationale (exact-decklist matchups are almost all n<5).
`results/meta/archetype_matchups.csv` contains **289 unordered archetype
pairs** — one row per pair, not one row per direction, per the phase prompt's
explicit instruction not to treat A-vs-B and B-vs-A as independent
observations. Each row carries both `win_rate_A` and `win_rate_B`
(`win_rate_B = 1 - win_rate_A` by construction, guaranteeing
`wins_A + wins_B == games` exactly — verified in §13).

**[DESIGN] `archetype_A` / `archetype_B` ordering convention**: A is the
archetype with the larger overall game count (ties broken alphabetically) —
purely a display/readability convention, `win_rate_A` always means "A's win
rate in games against B," so direction is never ambiguous regardless of which
side is labeled A.

**[DESIGN] Matchup confidence thresholds** (as suggested by the phase prompt,
inspected against the actual distribution before adopting):

| Tier | Games | Count (of 289 pairs) |
|---|---|---|
| INSUFFICIENT | < 20 | 263 |
| LOW_CONFIDENCE | 20–49 | 15 |
| USABLE | 50–99 | 7 |
| HIGH_CONFIDENCE | ≥ 100 | 4 |

The distribution is heavily right-skewed (median pair n=2, max n=417) — the
suggested 20/50/100 thresholds were kept unchanged because they land at
natural breakpoints in the data (7 pairs cleanly separate into USABLE, 4 into
HIGH_CONFIDENCE) rather than splitting a dense cluster arbitrarily.

**[RESULT]** The 4 HIGH_CONFIDENCE + 7 USABLE = 11 pairs match Phase 4.1's
count exactly (report used a 2-tier ≥50 "USABLE" cut = 11 pairs). Sanity
cross-check passed: no games-mirror mismatches (the count of A-vs-B games
observed from A's side-rows equals the count from B's side-rows, for all 289
pairs).

---

## 6. Counter Relationships

**[DESIGN] Credibility gate**, deliberately requiring both sample size and CI
magnitude, not raw win_rate>50%: an archetype-pair is a **credible counter**
iff `games >= 50` (USABLE or better) **and** the Wilson 95% CI lower bound of
the favored side's win rate is **> 0.50** (i.e., the CI excludes a coin flip
entirely). This directly implements the phase prompt's requirement that an
82%-at-n=7 result must not outrank a 64%-at-n=150 result: the n=7 case would
never pass the games>=50 gate at all, and even a large win-rate gap at small n
typically fails the wilson_lo>0.5 test too (a 60% win rate at n=30 has
wilson_lo≈0.41, not credible).

**[RESULT] 4 credible counter relationships found** among the 289 pairs (all
at USABLE or HIGH_CONFIDENCE):

| Counters | Countered | Games | Counter win rate | Wilson lo |
|---|---|---|---|---|
| Team Rocket's Mewtwo ex | Fezandipiti ex | 85 | 76.5% | 0.664 |
| Teal Mask Ogerpon ex | Marnie's Grimmsnarl ex | 77 | 81.8% | 0.718 |
| Marnie's Grimmsnarl ex | Team Rocket's Mewtwo ex | 134 | 59.7% | 0.512 |
| Dragapult ex | Fezandipiti ex | 76 | 64.5% | 0.533 |

**[RESULT]** The first two reproduce Phase 4.1's two flagship findings exactly
(76.5%/n=85 and 81.8%/n=77, both re-derived independently from the raw parquet
in this session, not copied from the prior report). **The specific
prompt-flagged relationship — Teal Mask Ogerpon ex countering Marnie's
Grimmsnarl ex — is confirmed statistically credible**, not just a raw
win-rate observation: Wilson lower bound 71.8%, far clear of 50%, at a USABLE
sample size (n=77).

**[RESULT]** Two additional credible counters emerge at this level of
analysis that Phase 4.1's report did not call out explicitly (it only
highlighted the single strongest favorable/unfavorable pair): Marnie's
Grimmsnarl ex has a credible counter of its own against Team Rocket's Mewtwo
ex (59.7%, n=134, HIGH_CONFIDENCE), and Dragapult ex credibly beats
Fezandipiti ex (64.5%, n=76, USABLE).

**[LIMITATION]** Only 11 pairs reach the USABLE+ sample-size floor required to
even be *eligible* as a credible counter — the counter-relationship graph is
necessarily sparse and concentrated on the top ~8 archetypes. This is not a
methodology gap; it is the same combinatorial-tail limitation Phase 4.1 already
documented (83 archetypes → 3,403 possible pairs, most rare by construction).

---

## 7. Recent Meta

**[RESULT]** RECENT-period (period=`RECENT`, 3,998 deck-slots) stats for every
archetype are in `archetype_features.csv` (`recent_games`, `recent_share`,
`recent_win_rate`). Only **9 of 83 archetypes** clear 20 RECENT-period games
(the INSUFFICIENT floor) — the RECENT meta is effectively described by these
9, with the other 74 too thin to say anything about their current state.

**[DESIGN] `meta_tags`** (non-exclusive tags, not a single classification —
an archetype can be simultaneously `CURRENT_DOMINANT` and `CURRENT_RISING`,
for example, so a strict 5-way partition would force artificial choices the
prompt's own examples don't support):

- `CURRENT_DOMINANT`: recent-period confidence ≥ USABLE AND recent_share ≥ 15%
- `CURRENT_RISING` / `CURRENT_DECLINING`: recent-period confidence not
  INSUFFICIENT AND `share_change_early_to_recent` ≥ +3pp / ≤ −3pp (§8 drift
  thresholds)
- `CURRENT_COUNTER`: has ≥1 credible counter (§6 gate) against an archetype
  tagged `CURRENT_DOMINANT`
- `CURRENT_UNCERTAIN`: recent_games < 20 — overrides/accompanies any other
  tag as a data-quality flag

**[RESULT]** Tags assigned:

| Archetype | Tags |
|---|---|
| Marnie's Grimmsnarl ex | CURRENT_DOMINANT, CURRENT_RISING |
| Fezandipiti ex | CURRENT_DOMINANT, CURRENT_RISING |
| Mega Kangaskhan ex | CURRENT_RISING |
| Team Rocket's Mewtwo ex | CURRENT_RISING, CURRENT_COUNTER |
| Dragapult ex | CURRENT_COUNTER |
| Mega Lopunny ex | CURRENT_RISING |
| Mega Lucario ex | CURRENT_DECLINING |
| Teal Mask Ogerpon ex | CURRENT_RISING, CURRENT_COUNTER |
| (74 others) | CURRENT_UNCERTAIN only |

`CURRENT_COUNTER` correctly picks out exactly the 3 archetypes with a credible
counter against a `CURRENT_DOMINANT` archetype (Team Rocket's Mewtwo ex and
Marnie's Grimmsnarl ex itself both counter each other reciprocally at
different games; Dragapult ex counters Fezandipiti ex; Teal Mask Ogerpon ex
counters Marnie's Grimmsnarl ex) — reproducing the strategically important
relationships from §6 as a queryable tag rather than free text.

---

## 8. Meta Drift

**[DESIGN] Drift thresholds** (percentage-point change in `usage_share` from
EARLY to RECENT period), chosen so the known Marnie's Grimmsnarl ex example
(+35.8pp) lands unambiguously in the top bucket and small noise (most
UNLABELED clusters shift by <1pp simply because they have near-zero games in
both periods) doesn't get mislabeled as a trend:

- strongly rising / declining: ≥ +10pp / ≤ −10pp
- moderately rising / declining: +3pp to +10pp / −3pp to −10pp
- stable: within ±3pp

Win-rate drift uses a separate, smaller threshold (±5pp) since archetype win
rates cluster tightly (0.44–0.56, §3): meaningful increase/decrease ≥5pp,
else stable.

**[RESULT]** Among archetypes with ≥30 games (16 archetypes, matching Phase
4.1's `DECK_LOW_N` cutoff):

**Rising:**

| Archetype | Recent share | Δ share (early→recent) |
|---|---|---|
| Marnie's Grimmsnarl ex | 44.34% | **+35.82pp** (strongly rising) |
| Fezandipiti ex | 16.82% | +8.70pp (moderately rising) |
| Mega Kangaskhan ex | 8.75% | +6.64pp (moderately rising) |
| Mega Lopunny ex | 6.84% | +6.64pp (moderately rising) |
| Team Rocket's Mewtwo ex | 5.54% | +4.64pp (moderately rising) |
| Teal Mask Ogerpon ex | 4.79% | +4.49pp (moderately rising) |

**Declining:**

| Archetype | Recent share | Δ share (early→recent) |
|---|---|---|
| Mega Lucario ex | 1.50% | **−16.03pp** (strongly declining) |

**[RESULT] The known example reproduces exactly and independently from raw
data**: Marnie's Grimmsnarl ex 8.5%→44.3% (+35.8pp), correctly classified
`strongly rising`. Mega Lucario ex (17.5%→1.5%, −16.0pp) is the clearest
decliner among archetypes with adequate overall sample.

**[LIMITATION]** Win-rate drift is noisier than share drift at these sample
sizes — no archetype's win-rate change clears the ±5pp bar at both EARLY and
MIDDLE/RECENT confidence simultaneously except Marnie's Grimmsnarl ex itself
(EARLY 61.2% → RECENT 48.5%, a −12.7pp swing), and Phase 4.1 already flagged
that specific number as only moderate-confidence (EARLY n=85) and plausibly a
rating-non-convergence artifact rather than a real strength change — that
caveat is preserved here, not re-litigated as new evidence.

---

## 9. Short-Game Profiles

**[FACT]** Short-game threshold recomputed directly from source this session:
10th percentile of `game_length` (decisive episodes) = **97 steps**, matching
Phase 4.1 exactly.

**[DESIGN] Classification**, requiring `short_game_sample >= 20` (below that,
class is `uncertain` regardless of the observed delta — a 3-game short-game
sample proves nothing): `short_game_advantaged` if delta ≥ +10pp,
`short_game_disadvantaged` if delta ≤ −10pp, else `neutral`. The 10pp bar was
chosen because it is well above the noise band implied by the archetype win
rates' own overall spread (12pp, 0.44–0.56, §3) — a short-game shift smaller
than that overall spread would not be distinguishable from ordinary
archetype-to-archetype variance.

**[RESULT]** Both known examples reproduce exactly, independently recomputed
from the raw parquet:

| Archetype | Overall WR | Short-game WR | Δ | n (short) | Class |
|---|---|---|---|---|---|
| Fezandipiti ex | 47.08% | 65.19% | **+18.11pp** | 135 | short_game_advantaged |
| Mega Kangaskhan ex | 49.70% | 23.85% | **−25.85pp** | 109 | short_game_disadvantaged |

**[RESULT]** 7 of 83 archetypes clear the n≥20 short-game sample floor with a
non-`uncertain` classification: 3 `short_game_advantaged`, 4
`short_game_disadvantaged`; the remaining 76 (mostly the UNLABELED long tail)
are `uncertain`.

---

## 10. Meta Graph

**[FACT]** `results/meta/meta_graph.json`: **83 nodes, 289 edges**, all
archetypes connected to at least one other archetype in the observed data (0
isolated nodes) — every archetype has been seen playing against at least one
other archetype at least once.

**[DESIGN]** Nodes carry `usage_share`, `recent_share`, `win_rate`,
`recent_win_rate`, `game_count`, `confidence`, `strength_class`, `meta_tags`,
plus two simple graph-native metrics: `observed_opponent_degree` (how many
distinct archetypes this one has ever been recorded against, any sample size)
and `credible_matchup_degree` (how many of those are backed by a §6-credible
counter relationship in either direction). Edges are single objects per
unordered pair (matching `archetype_matchups.csv`, §5) carrying both
directions' win rates plus the RECENT-period slice.

**[RESULT]** No networkx dependency was available in this environment (not
installed); graph metrics were computed directly (adjacency counting) rather
than adding a new dependency for a lightweight 83-node graph — the JSON is
also directly loadable by networkx downstream (`nx.node_link_graph`-compatible
shape) if a future phase wants richer graph algorithms (centrality, community
detection).

**[RESULT] Highly connected nodes**: the 9 archetypes with ≥20 RECENT games
(§7) unsurprisingly have the highest `observed_opponent_degree` — Marnie's
Grimmsnarl ex and Fezandipiti ex, the two largest archetypes, are each
recorded against dozens of distinct opponents (most at INSUFFICIENT
confidence individually, but collectively giving these two nodes the densest
connectivity in the graph). Most of the 71 UNLABELED nodes have low degree (a
handful of observed opponents each), consistent with their small sample
sizes.

**[LIMITATION]** No strategic cycle (e.g., A counters B counters C counters A)
was found among the 4 credible-counter edges (§6) — there are simply too few
credible edges (4) to form a cycle at this sample size, so this analysis does
not claim a rock-paper-scissors structure exists or doesn't; it is
unresolved, not "no cycle" as a positive finding.

---

## 11. Opponent Archetype Representation

**[RESULT]** `results/meta/opponent_archetypes.json` — one `OpponentProfile`
per archetype (83 total), each containing exactly the fields listed in the
phase prompt's §16: `identity`, `popularity`, `strength`, `recent_strength`,
`trend`, `matchup_vector` (every observed opponent, any sample size, each
tagged with its own confidence — nothing hidden per the standing
"don't hide low-sample uncertainty" rule), `counter_targets`,
`countered_by`, `short_game_profile`, `uncertainty`.

**[DESIGN]** This is explicitly a **representation**, not an inference engine
— there is no code anywhere in this phase that takes partial gameplay
observations and outputs a predicted archetype. The `uncertainty` block on
every profile explicitly states rating was not used.

---

## 12. Meta Prior

**[RESULT]** `results/meta/meta_prior.csv`: `prior_raw` = each archetype's
share of RECENT-period deck-slots, normalized so `sum(prior_raw) == 1.0`
across all 83 archetypes (validated, §13). `prior_filtered` additionally
excludes archetypes below the INSUFFICIENT floor (recent_games < 20) and
renormalizes over the remaining 9, so `sum(prior_filtered) == 1.0` over that
9-archetype subset (74 excluded rows carry `prior_filtered=0`, not removed
from the file — raw counts are never silently dropped).

| Archetype | Recent games | prior_raw | prior_filtered |
|---|---|---|---|
| Marnie's Grimmsnarl ex | 1,769 | 0.4434 | 0.4553 |
| Fezandipiti ex | 671 | 0.1682 | 0.1727 |
| Mega Kangaskhan ex | 349 | 0.0875 | 0.0898 |
| Mega Lopunny ex | 273 | 0.0684 | 0.0703 |
| Team Rocket's Mewtwo ex | 221 | 0.0554 | 0.0569 |
| Teal Mask Ogerpon ex | 191 | 0.0479 | 0.0492 |
| Dragapult ex | 184 | 0.0461 | 0.0474 |
| Cynthia's Garchomp ex | 167 | 0.0419 | 0.0430 |
| Mega Lucario ex | 60 | 0.0150 | 0.0154 |
| *(74 more, each < 20 recent games)* | — | small | 0 |

**[DESIGN]** `prior_raw` (over all 83) is the honest, complete estimate of
"what is the opponent likely playing right now"; `prior_filtered` (over the 9)
is what a downstream consumer should actually condition decisions on, since
the other 74 archetypes' RECENT-period estimates are individually
statistically meaningless (most have 0–5 RECENT games).

---

## 13. Data Quality & Uncertainty

**[RESULT] All required validations pass** (full output in the build script's
console log):

- **Games consistency**: `sum(archetype games) = 6,982` exactly equals total
  decisive deck-slots (6,982). No games were dropped or double-counted.
- **Probability consistency**: `sum(meta_prior.prior_raw) = 1.000000`;
  `sum(meta_prior.prior_filtered over included) = 1.000000`.
- **Matchup consistency**: `wins_A + wins_B == games` for all 289 rows (0
  violations) — guaranteed by construction (`wins_B := games - wins_A`, valid
  because the decisive subset has no draws), then cross-checked against an
  independently computed mirror count (`games` observed from each side
  separately) with **0 mismatches** across all 289 pairs.
- **Mapping consistency**: every one of 619 exact deck hashes maps to exactly
  one archetype (0 hashes with >1 distinct archetype assignment across all
  occurrences as either player-side or opponent-side deck), 0 `UNKNOWN`.

**[LIMITATION, carried forward from Phase 4.1, unchanged]**: rating remains
structurally unresolvable from this data source and was excluded from every
output in this phase, per instruction. Archetype identity remains a
deterministic heuristic (shared headline-Pokemon signature), not a verified
ground truth. EARLY-period statistics remain the least reliable slice
(pre-rating-convergence). None of this phase's work could or attempted to
resolve these — they are inherited data-source limitations, not artifacts of
this phase's methodology.

**[LIMITATION, new this phase]**: the counter-credibility gate (§6, games≥50
AND wilson_lo>0.5) is a single reasonable choice among several defensible
ones — a stricter gate (e.g., wilson_lo>0.55) would find fewer counters (likely
just the 2 already flagged in Phase 4.1); a looser one (games≥20) would admit
LOW_CONFIDENCE pairs the phase prompt explicitly warns against treating as
credible. The 4 counters reported here should be read as "the counters
defensible at this specific, documented bar," not an exhaustive or provably
optimal list.

---

## 14. Limitations

1. Rating excluded throughout (Phase 4.1 finding, unchanged).
2. 74 of 83 archetypes have <20 RECENT-period games — the "recent meta"
   representation (§7, §12) is effectively a 9-archetype picture; the other
   74 exist in the files (nothing hidden) but cannot support any recent-period
   claim.
3. Only 11 of 289 archetype pairs reach USABLE+ matchup confidence — the
   matchup/counter/graph representations are necessarily sparse outside the
   top ~8 archetypes, inherited directly from Phase 4.1's sampling scale.
4. `archetype_name` for UNLABELED clusters is a derived label (headline-Pokemon
   signature), not a verified competitive-community name — treat as
   descriptive, not authoritative.
5. The `meta_tags` and `strength_class` rules are one reasonable, documented
   parameterization each; different (still defensible) threshold choices
   would shift which archetypes get which tags at the margins, though the
   headline archetypes' classifications (Grimmsnarl dominant/rising, Mega
   Lucario declining, etc.) are robust to reasonable threshold variation
   given how large their underlying deltas are.
6. No temporal recency weighting was applied *within* the RECENT period
   itself (e.g., last week vs. three weeks ago) — RECENT is treated as one
   uniform window, matching Phase 4.1's period definition.

---

## 15. Proposed Interface for Future Agent

**[DESIGN]** Embedded machine-readably in `opponent_archetypes.json` under
`interface_schema.OpponentState`, and repeated here for readability:

```text
OpponentState
    observed_deck            -- list[card_id] or partial observation of what
                                 the opponent has actually played so far this
                                 game (NOT implemented/populated this phase)
    inferred_archetype       -- archetype_id string; a future phase's
                                 classifier output (NOT implemented this phase)
    archetype_confidence     -- float or category; how sure that inference is
                                 (NOT implemented this phase)
    meta_prior                -- dict[archetype_id -> float], defaults to
                                 meta_prior.csv's prior_filtered (or prior_raw
                                 if the consumer wants the full 83-archetype
                                 spread) as the pre-observation baseline
    matchup_vector             -- for the agent's OWN archetype, the relevant
                                 slice of archetype_matchups.csv /
                                 opponent_archetypes.json[own_id].matchup_vector
                                 -- i.e. "how do I do against each opponent
                                 archetype," keyed by opponent_archetype_id
    temporal_context          -- EARLY | MIDDLE | RECENT, selects which
                                 share/win-rate columns are relevant (a future
                                 agent competing live should always use RECENT)
```

**[DESIGN]** This schema is a **data contract**, not an implementation — no
inference logic (deck→archetype classification from partial observations,
Bayesian updating of `meta_prior` as more of the opponent's deck is revealed,
etc.) exists yet. `deck_to_archetype.csv` is the ground-truth lookup a future
classifier would be trained or evaluated against; `archetype_matchups.csv` /
`opponent_archetypes.json[*].matchup_vector` is the ground truth a future
deck-selection or in-game strategy module would condition on.

---

## 16. Key Findings

1. **[RESULT]** All 7 required output files were generated and pass every
   validation check in §13 — games-sum, probability-sum, matchup
   wins-consistency, and 1:1 deck→archetype mapping all hold exactly.
2. **[RESULT]** Every numerically-specific example named in the phase prompt
   reproduced exactly from an independent recomputation off the raw parquet:
   Marnie's Grimmsnarl ex 8.5%→44.3% share drift (`strongly rising`),
   Fezandipiti ex +18.1pp / Mega Kangaskhan ex −25.9pp short-game deltas, and
   the Teal Mask Ogerpon ex → Marnie's Grimmsnarl ex relationship confirmed as
   a statistically credible counter (Wilson lower bound 71.8% at n=77, not
   just a raw win-rate observation).
3. **[RESULT]** Only **4 matchup pairs** (of 289 observed) clear this phase's
   documented counter-credibility bar (games≥50 AND wilson_lo>0.5) — two
   reproduce Phase 4.1's flagship findings (Mewtwo ex > Fezandipiti ex 76.5%;
   Ogerpon ex > Grimmsnarl ex 81.8%), two are new at this level of analysis
   (Grimmsnarl ex > Mewtwo ex 59.7%, n=134, HIGH_CONFIDENCE; Dragapult ex >
   Fezandipiti ex 64.5%, n=76, USABLE).
4. **[RESULT]** No archetype's *overall field* win rate is statistically
   distinguishable from 50% at USABLE+ sample size (0 `HIGH_CONFIDENCE_STRONG`,
   1 `HIGH_CONFIDENCE_WEAK` out of 83) — deck strength differentiation in this
   meta shows up in matchup-specific structure, not aggregate win rate,
   consistent with (and sharpening) Phase 4.1's matchmaking-artifact
   hypothesis.
5. **[RESULT]** The RECENT-period meta is effectively described by only **9
   of 83 archetypes** (those clearing 20 RECENT games) — `meta_prior.csv`'s
   `prior_filtered` column is the honest current-meta prior; the remaining 74
   archetypes are preserved in every file (never silently dropped) but
   individually uninformative for RECENT-period claims.
6. **[RESULT]** The meta graph is fully connected (0 isolated archetypes among
   83) but very sparsely *credibly* connected (4 credible-counter edges) — no
   evidence for or against a rock-paper-scissors cycle structure at this
   sample size; genuinely unresolved, not a negative finding.
7. **[DESIGN, no overfitting]** No ML model, embedding, search, or opponent
   policy was trained or implemented — every output is a direct, documented,
   reproducible statistical transformation of the Phase 4.1 dataset.

---

**Rating used: NO.** **Additional raw episodes downloaded: 0.**
**Representation complete: YES.** Per the phase prompt's explicit instruction,
no agent/RL/MCTS/search/opponent-policy implementation follows from this
report without separate authorization.
