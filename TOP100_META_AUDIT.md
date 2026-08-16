# Real-Ladder Meta / Deck Audit — Top-100 (pokemon-tcg-ai-battle)

**Date**: 2026-08-13. **Scope**: read-only meta-intelligence report. **No agent, weight, deck,
or submission changes were made. No V9 was created. V8 was not modified.** This is a
checkpoint deliverable, not an implementation — per this project's standing process rule, it is
the decision point for a human call, not an automatic green light.

Every claim is tagged **[FACT]** (directly measured from pulled real data), **[SUPPORTED]**
(a claim backed by real data that clears a stated confidence bar), **[HYPOTHESIS]** (plausible,
not yet conclusively established), or **[INSUFFICIENT DATA]**.

**Central question posed**: is our Dragapult ex deck a strategically viable choice in the
current Kaggle meta, or are we optimizing an agent around a fundamentally suboptimal deck?

**Headline answer**: the real Top-100 leaderboard data does **not** support "Dragapult ex is
strategically inferior." Dragapult ex is **tied for the single most-represented archetype in
the Top-100** (19%), and its representation **increases**, not decreases, at higher rank tiers
(19% → 24% → 30% → 30% from Top100→Top50→Top20→Top10), piloted by **19 independent agents**
spanning a 206-point rating range including the #2 and #3 spots overall. The evidence points to
**Hypothesis B** (viable deck, specific bad matchups our policy handles poorly) as the
best-supported reading, with a real, mechanistically-explained bad matchup against the
Crustle/Mega Kangaskhan ex line (Part 5, Part 7).

---

## Methodology (Part 1 — how the data was obtained)

Reused, not reinvented, the exact public-Kaggle-API mechanism validated in `LUCA_AUDIT.md`:

1. `KaggleApi.competition_leaderboard_view('pokemon-tcg-ai-battle')`, paginated
   (`page_size`/`page_token`) to the top 150 entries, pulled 2026-08-13. **[FACT]**
2. For each of the top 100 ranks: `competition_team_submissions(team_id)` (confirmed public for
   any team, not just our own) → the most-recent submission by `dateSubmitted` is treated as the
   team's current live entry. **[FACT]**
3. `competition_list_episodes(submission_id)`, filtered to `EPISODE_TYPE_PUBLIC` +
   `state=COMPLETED` (excludes Kaggle's own self-play validation episode, same exclusion used in
   the Luca audit). **[FACT]**
4. Up to 3 episodes per team, spread across their episode history (first/middle/last by episode
   id), downloaded and parsed with the already-validated exact-decklist method
   (`src/meta_analysis/episode_parser.py`: first 60-card action = deck-declare, cross-checked
   against spectator-only `visualize.deck`) — the same method that recovered exact ground-truth
   decklists for all 3,499 episodes of this project's earlier historical dataset and for Luca's
   69 real games. **[FACT]**
5. Archetype tagging reused `src/meta_analysis/archetype_signatures.py` (12 known named
   archetypes) with `src/meta_analysis/deck_clustering.py`'s headline-Pokemon-name method as a
   deterministic fallback for anything unmatched. **[FACT]**

**Results**: 100/100 ranks resolved to a team+submission; **99/100 decks successfully
extracted** (1 `UNKNOWN`, rank 34 "JB Bryant" — their current submission has 0 completed public
episodes yet, i.e. genuinely no observable data, not a pull failure). **[FACT]**. Every sampled
team showed **deck_consistent = True** (0/99 deck-switchers across the sample) — matching
Luca's own single-fixed-decklist pattern. **[FACT]**. Exactly 1 archetype not in the prior
12-name catalogue was found this session: **N's Zoroark ex** (rank 17, "Oshbocker", rating
1115.0) — a real, previously-uncatalogued Top-20 archetype. **[FACT]**

New tooling: `tools/pull_top100_ladder_audit.py` (data pull, checkpointed/resumable),
`tools/build_top100_meta_audit_v1.py` (analysis). Raw data preserved in
`data/top100_audit/{leaderboard_raw.json, teams/, replays/}` (gitignored, per project
convention) and `results/top100_audit/{pull_checkpoint.json, leaderboard_decks.csv,
tier_archetype_frequency.csv, tier_summary.csv, archetype_tier_pivot.csv,
special_archetype_representation.csv, policy_vs_deck_top100.csv}` — the full 100-row table is
in `leaderboard_decks.csv`, not reproduced row-by-row below to keep this report readable; the
Top-20 is shown in full in Part 2.

**[GAP]**: the pull sampled ≤3 episodes/team, not every game — fine for confirming a fixed
single-decklist (which held 99/99 times) but means a team that switched decks on exactly the
unsampled episodes would not be caught. **[GAP]**: this snapshot is a single point in time
(2026-08-13); the competition's Simulation track ends 2026-08-16 with ~2 more weeks of rating
convergence after, so today's exact ranks are not final.

---

## Part 2 — Top100 → Top50 → Top20 → Top10 snapshots

**[FACT]**, computed directly from the 99 resolved decks:

| Tier | n resolved | unique archetypes | n UNKNOWN | avg rating | median rating | top archetype | top archetype share |
|---|---:|---:|---:|---:|---:|---|---:|
| Top100 | 100 | 11 | 1 | 1063.2 | 1042.7 | Dragapult ex (tied) | 19.0% |
| Top50 | 50 | 10 | 1 | 1104.0 | 1090.0 | Dragapult ex | 24.0% |
| Top20 | 20 | 8 | 0 | 1149.1 | 1136.6 | Mega Kangaskhan ex (tied) | 30.0% |
| Top10 | 10 | 5 | 0 | 1178.3 | 1166.5 | Mega Kangaskhan ex (tied) | 30.0% |

**Archetype × tier table** (all 11 archetypes found; `max_rating` = highest-rated pilot found in
Top-100):

| Archetype | Top100 % | Top50 % | Top20 % | Top10 % | Max Rating |
|---|---:|---:|---:|---:|---:|
| **Dragapult ex** | **19.0%** | **24.0%** | **30.0%** | **30.0%** | 1217.0 |
| Marnie's Grimmsnarl ex | 19.0% | 12.0% | 5.0% | 10.0% | 1140.2 |
| Mega Lopunny ex | 16.0% | 16.0% | 0.0% | 0.0% | 1088.8 |
| Teal Mask Ogerpon ex | 14.0% | 16.0% | 15.0% | 20.0% | 1175.3 |
| **Mega Kangaskhan ex** | **13.0%** | **14.0%** | **30.0%** | **30.0%** | **1227.1 (#1)** |
| Fezandipiti ex | 12.0% | 6.0% | 5.0% | 0.0% | 1120.0 |
| Mega Lucario ex | 3.0% | 6.0% | 5.0% | 10.0% | 1197.5 |
| Cynthia's Garchomp ex | 1.0% | 2.0% | 5.0% | 0.0% | 1126.6 |
| N's Zoroark ex (new find) | 1.0% | 2.0% | 5.0% | 0.0% | 1115.0 |
| Team Rocket's Kangaskhan ex | 1.0% | 0.0% | 0.0% | 0.0% | 1038.7 |
| UNKNOWN | 1.0% | 2.0% | 0.0% | 0.0% | — |

**[FACT] — the headline pattern**: two archetypes **rise** sharply from Top100 to Top10
(Dragapult ex 19→30%, Mega Kangaskhan ex 13→30%) while two **fall off a cliff** at the very top
(Mega Lopunny ex 16→0%, Fezandipiti ex 12→0%). Marnie's Grimmsnarl ex — by far the most popular
deck in the *general* ladder population (see Part 12) — is only tied-2nd in the Top-100 and
drops to a modest 10% of the Top-10, well behind Dragapult and Kangaskhan. Teal Mask Ogerpon ex
rises steadily and consistently across every tier (14→16→15→20%).

---

## Part 3 — Deck performance (general-ladder population, historical dataset)

This section reuses this project's already-existing 3,499-episode historical dataset
(2026-06-16 to 2026-08-10, `results/meta/*.csv`, built across sessions 4–12) rather than
re-deriving win rates from scratch — it is the same real-ladder data source, just a different
(much larger, but not skill-filtered) population than the Top-100 snapshot above. **This
project's own prior finding, reconfirmed here, applies throughout this section: 0 of 83
archetypes show an aggregate win rate statistically distinguishable from 50%** (Bayesian
matchmaking by rating proximity evens out raw win rate) — **so raw win rate must NOT be read as
"this archetype is stronger,"** per the task's own explicit instruction. It reflects
matchmaking-adjusted performance, not deck power in isolation.

| Archetype | Games | Exact variants | Win rate | Wilson 95% CI | Recent-period win rate | Confidence |
|---|---:|---:|---:|---|---:|---|
| Marnie's Grimmsnarl ex | 2225 | 47 | 49.03% | [46.96%, 51.11%] | 48.45% (↓ trend) | HIGH |
| Fezandipiti ex | 1355 | 87 | 47.08% | [44.44%, 49.75%] | 47.39% (↓ trend) | HIGH |
| Mega Kangaskhan ex | 668 | 48 | 49.70% | [45.92%, 53.48%] | 50.14% (flat) | HIGH |
| Team Rocket's Mewtwo ex | 349 | 30 | 51.29% | [46.06%, 56.49%] | 48.87% | HIGH |
| **Dragapult ex** | **337** | **50** | **55.19%** | not separately computed | **57.07% (↑ trend)** | MEDIUM (usage small) |
| Cynthia's Garchomp ex | 296 | 13 | — | — | — | HIGH (nearly "solved," 88.2% top-list share) |
| Mega Lopunny ex | 289 | — | — | — | 56.78% (↑ trend) | MEDIUM |
| **Mega Lucario ex** | **262** | — | — | — | **61.67% (↑ trend, but only 60 recent games)** | LOW (declining sample) |
| Teal Mask Ogerpon ex | 199 | — | — | — | 54.45% (↓ trend) | MEDIUM |

**[FACT]**: Dragapult ex has **50 distinct exact decklists across 337 games** — the single
biggest exact variant is only 19% of Dragapult's own games (64/337). **This archetype is
nowhere near "solved" in the general population** — contrast Cynthia's Garchomp ex (88.2%
top-list share, 13 variants total but 1 dominant, verified against the full 296-game dataset)
which effectively is. **[HYPOTHESIS]**: this means the 55.19%
aggregate "Dragapult ex win rate" figure is an average over 50 meaningfully different builds of
plausibly very different quality — a single well-optimized Dragapult list could reasonably
outperform this blended average by a wide margin, and conversely a weak list drags it down; the
aggregate number should not be read as "the ceiling of the archetype."

**[FACT]**: Dragapult's recent-period win rate (57.07%) is trending **up** while its share
(4.6%, "stable" trend — not rising) stays flat. Mega Lucario ex shows the highest recent win
rate of any tracked archetype (61.67%) but on a **strongly declining, small (n=60) recent
sample** — too small to trust as a stable estimate. **[INSUFFICIENT DATA]** for a precise
Lucario recent-win-rate claim; directionally interesting only.

---

## Part 4 — Current meta matchups: Dragapult ex vs the field

Matrix built from `results/meta/archetype_matchups.csv` (historical dataset, Wilson lower bound
computed on the smaller side's win count). Classification thresholds: **GOOD** = point estimate
≥60% with n≥30; **BAD** = point estimate ≤40% with n≥30; **NEUTRAL** = 40–60% or n<30 but with a
usable point estimate; **UNKNOWN** = n<10.

| Opponent archetype | Dragapult ex win rate | n | Confidence | Classification |
|---|---:|---:|---|---|
| Fezandipiti ex | 64.5% | 76 | USABLE, **credible counter** | **GOOD** |
| Marnie's Grimmsnarl ex | 60.5% | 76 | USABLE (not credible-counter-tier) | GOOD (lean) |
| Mega Lopunny ex | 64.7% | 17 | INSUFFICIENT | NEUTRAL/lean-GOOD (small n) |
| Cynthia's Garchomp ex | 53.9% | 13 | INSUFFICIENT | NEUTRAL |
| Teal Mask Ogerpon ex | 40.0% | 10 | INSUFFICIENT | NEUTRAL/lean-BAD (small n) |
| **Mega Kangaskhan ex** | **37.8%** | **37** | LOW_CONFIDENCE | **BAD** (mechanistically explained, Part 7) |
| Team Rocket's Mewtwo ex | 16.7% | 12 | INSUFFICIENT | BAD (small n, striking) |
| **Mega Lucario ex** | **12.5%** | **16** | INSUFFICIENT | **BAD** (small n, striking, see Part 6) |

**[FACT]**: Dragapult ex has genuinely good, reasonably-sampled (n=76 each) matchups against the
meta's **two most popular general-population decks** (Grimmsnarl, Fezandipiti — together 51% of
all general-population games) — this is the single most reassuring data point for deck
viability. **[HYPOTHESIS, small-n]**: Dragapult loses badly to Mega Kangaskhan ex, Mega Lucario
ex, and Team Rocket's Mewtwo ex, but every one of these three matchups sits at n=12–37 —
directionally real but not yet at this project's own established credibility bar (n≥50). Two of
these three losing matchups (Kangaskhan, Lucario) are exactly the two archetypes disproportionately
concentrated at the very top of the real Top-100 leaderboard (Part 2) — this convergence across
two independent data sources (historical matchup stats and today's leaderboard composition) is
worth taking seriously even though neither alone clears a strict statistical bar.

---

## Part 5 — Dragapult ex's position in the meta (the central question)

**[FACT]**, all from the new Top-100 pull:

1. **Top-100 representation: 19/99 resolved decks (19.2%)** — tied for the single most common
   archetype in the entire Top-100.
2. **Top-50: 12/50 (24.0%)** — the single most common archetype.
3. **Top-20: 6/20 (30.0%)** — tied for most common (with Mega Kangaskhan ex).
4. **Top-10: 3/10 (30.0%)** — tied for most common (with Mega Kangaskhan ex).
5. **Highest-rated Dragapult agent: "flg", rank 2, rating 1217.0** — one rank below the overall
   #1.
6. **Median rating of the 19 Top-100 Dragapult agents: 1075.8** (range 1010.7–1217.0, a 206.3-point
   spread).
7. **Dragapult is NOT disproportionately absent from the top tier — the opposite is true**: its
   share *rises* monotonically from 19%→24%→30%→30% as the tier tightens. This is the single
   clearest, most decisive finding in this whole audit.

**Compare to overall representation**: 19% of the Top-100 field plays Dragapult ex, rising to
30% of the Top-10 — vs. only **4.6% of the general ladder population** (historical dataset,
Part 3/12). Dragapult ex is *heavily* over-represented among successful/skilled agents relative
to its popularity among the ladder at large.

### Hypothesis test (Part 5's required A/B/C decision)

- **Hypothesis A** ("viable deck, our problem is mainly policy quality"): **SUPPORTED** by the
  representation data (19 independent successful pilots spanning a wide rating range, not one
  outlier) and by the good matchups vs the two most popular general-population decks (Part 4).
- **Hypothesis B** ("viable but has specific bad matchups our agent handles poorly"): also
  **SUPPORTED** — the Kangaskhan/Lucario/Mewtwo matchup weakness (Part 4) is real (if
  small-sample) and mechanistically explained for at least one of the three (Part 7's Crustle
  finding).
- **Hypothesis C** ("Dragapult ex is currently strategically inferior to the dominant meta
  decks"): **NOT SUPPORTED** by this data. The real Top-100 leaderboard is the single strongest
  piece of evidence available in this whole project against this hypothesis — a genuinely
  inferior deck would not be tied for the #1 most-represented archetype at the very top of a
  skill-rated ladder, piloted by 19 independent agents including the #2 overall.

**Verdict for Part 5: A and B are both supported, in combination; C is contradicted by the
strongest data source available (real Top-100 representation).**

---

## Part 6 — Mega Lucario ex analysis

**[FACT]**:

- Top-100 representation: **3/99 (3.0%)** — Luca (rank 4, 1197.5), "sadwat" (rank 40, 1063.1),
  "カントー地方マスター(KantoRegionMaster)" (rank 41, 1059.1).
- Top-50: 3/50 (6.0%). Top-20: 1/20 (5.0%, Luca only). Top-10: 1/10 (10.0%, Luca only).
- Highest rating: Luca, 1197.5 (down from 1232.4 two days ago at the time of `LUCA_AUDIT.md` —
  the leaderboard has shifted; Luca is now rank 4, not rank 1).
- Median rating across the 3 Top-100 Lucario agents: **1063.1** — driven far more by Luca alone
  (1197.5) than by the other two (1063.1, 1059.1, essentially tied with each other).
- General-population historical data: only 262 total games, 60 in the RECENT period (declining
  share, "strongly declining" trend) but the **highest recent win rate of any tracked archetype**
  (61.67%, small-n).

### Explicit hypothesis test (per the task's instruction not to assume "Luca is #1 → deck is best")

Reusing this project's own established test (from session 9's counter-model work): *if several
independent agents all do well with a deck, that supports deck strength; if one outlier carries
the average while others are unremarkable, that points to policy/skill driving the result, not
the deck.*

**[SUPPORTED]**: Mega Lucario ex fits the **"niche, high-skill deck" pattern, not "widely
dominant."** Only 3 of 99 resolved Top-100 decks use it (vs. Dragapult's 19 or Kangaskhan's 13) —
far too thin a population to claim general dominance — and of those 3, one (Luca) is dramatically
stronger (1197.5) than the other two (~1060, essentially at the bottom of the Top-100 rating
range). This is the classic signature of "works extremely well in the hands of one particular
skilled/well-tuned policy," not "the deck itself confers a structural edge that most competent
pilots can realize." **This directly reproduces and reinforces `LUCA_AUDIT.md`'s own earlier
caution**: Luca's ~74% win rate is real, but this new data adds that it is *not* representative
of Lucario pilots generally — it is closer to a **policy-and-deck-construction-quality outlier**
riding a real but narrow deck (Luca's own decklist deviates from this project's local reference
build in exactly the ways `LUCA_AUDIT.md` §3 already documented: full-deck search, repeatable
disruption, attacker-specific preservation — Layer A quality, not just "the archetype").

**Answer to Part 6's five options: "niche high-skill deck."** Not "genuinely dominant," not
"widely strong," not "impossible to determine" (n=3 is thin but the internal spread within that
n=3 is itself informative).

---

## Part 7 — Crustle analysis (high priority)

**[FACT]**: Crustle does **not** appear as a standalone archetype anywhere in the Top-100 (0
entries under "Crustle/Dwebble" as a named deck). It also does not appear as a standalone
archetype in the general-population historical dataset above token levels (largest pure
Crustle/Dwebble cluster: 41 games, 0.59% share, LOW_CONFIDENCE, 43.9% win rate — not a strong
deck on its own).

**However — Crustle is a near-universal 4-of TECH PIECE inside the meta's most successful
archetype.** **[FACT]**, confirmed directly against `results/meta/deck_to_archetype.csv`: every
single archetype in the historical dataset that runs Crustle/Dwebble at all — Mega Kangaskhan ex
(the representative, most-played build), Teal Mask Ogerpon ex, Cornerstone Mask Ogerpon ex, and
every dedicated Crustle/Dwebble cluster — runs the **same specific print**, card ID 345
("Mysterious Rock Inn"), never the alternative print (card ID 533, "Sturdy"). This is not a
coincidence of naming; it is a real, consistent, deliberate deckbuilding choice across
independent agents.

**[FACT, card text, `data/official/EN Card Data.csv`]** — Crustle (345)'s ability, **Mysterious
Rock Inn**: *"Prevent all damage done to this Pokémon by attacks from your opponent's Pokémon
{ex}."* No "while Active" or "while Benched" qualifier — the ability applies in either board
position. **Every headline attacker examined in this audit (Dragapult ex, Grimmsnarl ex,
Fezandipiti ex, Mega Lucario ex, Mega Kangaskhan ex, Mega Lopunny ex, Teal Mask Ogerpon ex,
Cynthia's Garchomp ex, Team Rocket's Mewtwo ex) is itself an `{ex}`-rule-box Pokémon** — meaning
Crustle (345) is a **generic wall against the entire class of 2-prize attackers that currently
defines this meta**, not a Dragapult-specific counter-tech. Framed narrowly around Dragapult, this
looks like "a hard counter"; framed correctly, it is "a broadly-applicable answer to `{ex}`
attackers that happens to include Dragapult ex."

**[FACT, engine-verified, not just card text]** — this project's own prior forensic audit
(`PHANTOM_DIVE_FORENSIC.md` §0, session prior to this one) already confirmed the engine actually
enforces this against our own Dragapult ex on real ladder replays: episode 92217792 turn 12 shows
a Crustle bench target's HP staying completely flat (150/150) across all 6 of Phantom Dive's
damage-counter placements. That same audit found immunity removed **5 of 68 (7.4%)** naively-counted
KO opportunities in a 43-game V2 sample — a real but not overwhelming fraction *in that specific
sample*, which did not happen to include many Kangaskhan-line opponents.

**[FACT]**: Jet Headbutt (Dragapult ex's other attack, 70 single-target damage) would be equally
nullified by an **Active** Crustle (345), by the same unqualified ability text — this specific
mechanic (Jet Headbutt vs. Active Crustle) was not directly measured this session (only Phantom
Dive vs. Benched Crustle was engine-verified in the prior audit), so this is **[HYPOTHESIS]**
pending direct verification, though the card text gives no reason to expect otherwise.

**[FACT]**: Mega Kangaskhan ex — the archetype that runs this Crustle package as standard
inclusion — is Dragapult's worst *reasonably-sampled* matchup (37.8% Dragapult win rate, n=37,
Part 4) and is simultaneously the **#1 overall rated deck in the real Top-100** (1227.1, 13% of
the field rising to 30% of the Top-10). These two facts connect directly: a deck that (a) is
demonstrably successful at the very top of the ladder and (b) structurally nullifies a large
share of Dragapult's own damage output, is a coherent, mechanistically-explained bad matchup —
not a statistical fluke.

**[FACT, incidental]**: our own current `decks/dragapult_ex.csv` runs **Team Rocket's
Watchtower** (silences {C}-type Pokémon abilities) — checked directly against card data: Crustle
(345) is **{G}-type (Grass), not {C} (Colorless)**, so this card in our own build does **not**
neutralize Mysterious Rock Inn. This is stated as a fact about our current build, not a
recommendation (out of scope per this task's instructions).

### Part 7's required classification (A/B/C/D)

**Crustle is (B) a niche threat with (D) a real, mechanistically-catastrophic interaction where
it does appear.** It is not (A) a common standalone meta threat (0% standalone Top-100
representation) and it is not simply (C) rare-and-ignorable — it rides inside the single most
successful archetype at the top of the ladder (Mega Kangaskhan ex) as a deliberate, consistent
tech choice, and the interaction with Dragapult ex specifically is a full damage-immunity, not a
partial disadvantage. **Do not overstate from the small matchup sample (n=37)** — the mechanism
is verified fact; the resulting win-rate magnitude is directional, not statistically proven at
this sample size.

---

## Part 8 — Deck design features across the Top archetypes

Grounded strictly in card text pulled this session (`data/official/EN Card Data.csv`) for the
headline attacker(s) of every archetype covering ≥1% of the Top-100 field, plus the staple
support cards that recur across multiple archetypes' representative decklists
(`results/meta/archetype_canonical.csv`). No feature below is asserted without a specific card
and effect text backing it.

| Archetype | HP (headline) | Prize value | Single-target | Spread/bench-snipe | Energy accel | Ability-based dmg/util | Card-draw/consistency engine | Notable other |
|---|---:|---|---|---|---|---|---|---|
| **Dragapult ex** | 320 | 2-prize | Jet Headbutt (70) | Phantom Dive (6 counters, bench-only, **never hits Active**) | none native | none offensive; defensive bench-immunity ability | none native | Retreat cost 1 |
| Marnie's Grimmsnarl ex | 320 | 2-prize | Shadow Bullet (180) | + 30 bench spread (hybrid) | **Punk Up**: search+attach up to 5 Energy on evolve | — | — | Strong ramp-on-evolve |
| Fezandipiti ex | 210 | 2-prize | Cruel Arrow (100, **any** opp. Pokémon incl. bench) | (Cruel Arrow doubles as flexible snipe) | — | **Flip the Script**: draw 3 after a KO | comeback-oriented draw engine | Lower HP (fragile) |
| Mega Lucario ex | 340 | 2-prize | Aura Jab (130) / Mega Brave (270, 1-turn cooldown) | — | **Aura Jab**: reattach up to 3 discarded Energy to bench | — | — | Highest HP + biggest single hit in the set |
| Mega Kangaskhan ex | 300 | 2-prize | Rapid-Fire Combo (200+, coin-flip scaling) | — | — | **Run Errand**: draw 2/turn (must be Active) | strong draw engine | + Crustle immunity wall tech |
| Mega Lopunny ex | 330 | 2-prize | Gale Thrust (60→230 if just benched→active) / Spiky Hopper (160, ignores opp. Active effects) | — | — | — | — | Switch-in reward (bench→active tempo) |
| Teal Mask Ogerpon ex | 210 | 2-prize | Myriad Leaf Shower (30 + 30/energy on both actives) | — | **Teal Dance**: attach 1 Energy/turn + draw | self-ramp + draw, self-sufficient | — | Lower HP, high self-sufficiency |
| Cynthia's Garchomp ex | 330 | 2-prize | Corkscrew Dive (100 + hand-refill to 6) / Draconic Buster (260, discards own Energy after) | — | — | — | hand-refill on 1st attack | Nearly "solved" list (85% share) |
| Team Rocket's Mewtwo ex | 280 | 2-prize | Erasure Ball (160 + 60/bench-Energy discarded, up to 280) | — | — | — bench-energy-discard payoff | — | Requires 4+ TR Pokémon to attack at all (build-around tax) |

**[FACT] — cross-cutting staples** found in ≥2 top archetypes' representative decklists: **Buddy-
Buddy Poffin** (search 2 Basics ≤70HP to bench — consistency/setup, in Grimmsnarl, Fezandipiti,
Kangaskhan, Ogerpon, and the historical Dragapult representative build), **Munkidori**
(ability moves damage counters between Pokémon + inflicts Confusion — cross-meta utility/
disruption piece), **Boss's Orders** (gusting/prize-race control, universal), **Ultra Ball**
(full-deck search, universal).

### Trend from Top100 → Top50 → Top20 → Top10 (Part 8's required question)

**[SUPPORTED]**: the two archetypes that *rise* toward the top (Dragapult ex, Mega Kangaskhan
ex) both combine **very high HP (300–320)** with either **a strong card-draw ability engine**
(Kangaskhan's Run Errand) or **flexible damage placement + a wide, still-undiscovered build
space** (Dragapult, Part 3's 50-variant finding). The two archetypes that *collapse* to 0% by
Top-10 (Mega Lopunny ex, Fezandipiti ex) share **comparatively situational payoffs** — Lopunny's
biggest hit requires a specific bench-to-active switch that turn, Fezandipiti's best mode
(Flip the Script) requires *already having lost a Pokémon*, i.e. is reactive/behind-oriented
rather than proactive. **[HYPOTHESIS]**: consistent, self-sufficient card advantage (Kangaskhan's
unconditional Run Errand draw, or a wide Dragapult build space allowing skilled pilots to
out-build the field) may matter more at the very top than raw peak damage numbers, but this is
inferred from only 2 rising + 2 falling data points and should not be treated as proven.

---

## Part 9 — Policy vs. Deck effect

New table, computed directly from the Top-100 pull (not the historical dataset — this is a
genuinely new capability this session's real-leaderboard data provides that the historical
dataset alone could not, since the historical dataset has no per-agent-skill signal):

| Archetype | # independent Top-100 agents | Rating range | Median | Max | Interpretation |
|---|---:|---|---:|---:|---|
| **Dragapult ex** | **19** | 1010.7–1217.0 (206.3 spread) | 1075.8 | 1217.0 | **Deck-effect-supported**: wide, independently-successful population, not one outlier |
| Marnie's Grimmsnarl ex | 19 | 1007.4–1140.2 (132.8 spread) | 1024.4 | 1140.2 | Wide population but a noticeably *lower* ceiling than Dragapult/Kangaskhan despite equal count |
| Mega Lopunny ex | 16 | 1010.7–1088.8 (78.1 spread) | 1041.0 | 1088.8 | Wide population, capped ceiling (never reaches Top-20, Part 2) |
| Teal Mask Ogerpon ex | 14 | 1011.6–1175.3 (163.7 spread) | 1050.6 | 1175.3 | Wide population, strong ceiling |
| **Mega Kangaskhan ex** | **13** | 1012.0–1227.1 (215.1 spread) | 1074.4 | **1227.1 (#1)** | **Deck-effect-supported**: fewer pilots than Dragapult but the single highest ceiling in the field |
| Fezandipiti ex | 12 | 1008.0–1120.0 | 1027.85 | 1120.0 | Wide population, modest ceiling |
| **Mega Lucario ex** | **3** | 1059.1–1197.5 | 1063.1 | 1197.5 | **Policy-effect pattern**: thin population, one outlier (Luca) far above the other two |

**[SUPPORTED]**: Dragapult ex and Mega Kangaskhan ex both show the "several independent agents,
all reasonably successful" pattern this project's own methodology treats as evidence of genuine
deck strength (not just one skilled policy). Mega Lucario ex shows the opposite pattern (n=3,
one clear outlier) — **policy/implementation quality, not the archetype itself, is the more
likely driver of Luca's specific result**, reinforcing Part 6.

---

## Part 10 — Top-10 deck feature profile (qualitative synthesis)

**[SUPPORTED, from Parts 2/8/9 combined, not invented]**: the Top-10 of the real ladder
(avg rating 1178.3, median 1166.5) is dominated by exactly two archetypes (Dragapult ex and Mega
Kangaskhan ex, 60% combined) plus Teal Mask Ogerpon ex (20%), with everything else reduced to
single entries. The common thread across these three specifically:

- **Very high HP 2-prize attackers** (320, 300, 210 respectively — Ogerpon is the outlier here,
  compensated by strong self-sufficiency, see below).
- **Either a resource/consistency engine (Kangaskhan's unconditional card draw, Ogerpon's
  attach+draw ability) or a wide, actively-still-diversifying build space (Dragapult's 50
  distinct decklists) rather than a single "solved" list.**
- **Flexible or bench-reaching damage** (Dragapult's Phantom Dive, Ogerpon's scaling attack) more
  than raw single-hit ceiling — Mega Lucario ex has the single biggest attack in the entire
  survey (270) yet only 3 Top-100 pilots.
- **No healing, no explicit prize-denial, no resource-recursion-heavy engine** was found among
  the Top-10's dominant archetypes' headline cards in this session's card-text pull — this
  absence is reported as a **[GAP]** (not checked in every support card, only headline attackers
  and cross-cutting staples), not asserted as a confirmed negative finding.

---

## Part 11 — Our Dragapult ex gap (V8's actual decklist vs. the observed meta)

**[FACT]**, comparing `decks/dragapult_ex.csv` (our current build) against
`results/meta/archetype_canonical.csv`'s Dragapult ex representative build (the single
most-played exact list in the historical dataset, 337 games, 55.19% win rate, 4.83% share):

| Card | Our build | Representative meta build | Note |
|---|---:|---:|---|
| Buddy-Buddy Poffin | **0** | 4 | **Absent from our build entirely** — appears in Grimmsnarl, Fezandipiti, Kangaskhan, Ogerpon, AND the Dragapult representative build (Part 8) — closest thing to a universal meta staple found this session |
| Munkidori | **0** | 2 | Also absent — cross-meta utility/disruption staple (Part 8) |
| Dawn | 0 | 1 | Absent (search a Basic/Stage1/Stage2 to hand) |
| Judge | 0 | 1 | Absent (mutual hand refresh/disruption) |
| Jamming Tower | 0 | 2 | Absent — we run Team Rocket's Watchtower instead (different stadium, see Part 7 — does not interact with Crustle) |
| Rare Candy | 2 | 0 | We run it; representative build doesn't |
| Basic Energy split | R×4, P×4 (8 total, 2 types) | D×2, P×4, R×4 (10 total, 3 types) | Our build runs less total Energy and omits Darkness entirely |
| Brock's Scouting, Latias ex, Lucky Helmet, Team Rocket's Watchtower | present (2/1/1/2) | absent | Our build's unique additions |

**[HYPOTHESIS]**: the Buddy-Buddy Poffin / Munkidori absence looks like a genuine **Layer A
(deck construction) gap**, not a policy issue — it is the same category of finding
`LUCA_AUDIT.md` §3/§5(H2) already flagged for this exact deck ("audit `decks/dragapult_ex.csv`'s
own consistency/preservation package") — this session adds concrete, real-meta-grounded
specifics (which two cards, how universal they are) rather than a general "consider auditing"
note.

**Separating POLICY from DECK/META weakness (as the task requires)**:

- **DECK/META evidence**: Part 5/9 show the Dragapult ex *archetype* is not disadvantaged —
  19 independent real agents succeed with it, including 2 in the Top-3. The specific *exact
  decklist* we run has at least two identifiable staple-card gaps relative to what's actually
  winning on the ladder (above) — this is a deck-construction finding, separable from agent
  policy quality.
- **MATCHUP evidence**: the Kangaskhan/Crustle interaction (Part 7) is a real, mechanistic,
  deck-vs-deck problem that no amount of policy tuning can fully solve (Phantom Dive and, by
  card text, Jet Headbutt both structurally cannot damage an `{ex}`-immune Crustle) — this is
  irreducibly a deck/meta-level gap for as long as we run an `{ex}` Pokémon as our sole attacker
  against that specific 13%-of-Top100 archetype.
- **POLICY evidence**: out of scope for this report by design (see `V8_NEXT_BOTTLENECK_AUDIT.md`,
  `PHANTOM_DIVE_FORENSIC.md` for the existing, separate policy-layer findings — e.g., the ~48%
  Phantom Dive allocation miss rate is a policy issue, independent of whether the target was even
  reachable at all).

**[FACT] — do not over-read V8's current low live rating as evidence against the deck**: this
report deliberately does not use V8's own recent submission scores as meta-viability evidence,
per the task's explicit framing that this is a meta report, not a V8 diagnosis — those numbers
are covered by the project's other, policy-focused audits.

---

## Part 12 — Current meta vs. historical meta

**[FACT]**, comparing the historical dataset's RECENT-period share (general population, ending
2026-08-10) against today's real Top-100 leaderboard share (2026-08-13, skilled-agent population):

| Archetype | General-population RECENT share | Top-100 (skilled) share | Gap |
|---|---:|---:|---:|
| Marnie's Grimmsnarl ex | **44.3%** (n=1769) | 19.0% | **-25.3pp** |
| Fezandipiti ex | 16.8% (n=671) | 12.0% | -4.8pp |
| Mega Kangaskhan ex | 8.7% (n=349) | 13.0% | +4.3pp |
| Mega Lopunny ex | 6.8% (n=273) | 16.0% | +9.2pp |
| Teal Mask Ogerpon ex | 4.8% (n=191) | 14.0% | +9.2pp |
| **Dragapult ex** | **4.6%** (n=184) | **19.0%** | **+14.4pp** |
| Mega Lucario ex | 1.5% (n=60, declining) | 3.0% | +1.5pp |

**[SUPPORTED] — this is the single most important structural insight of this audit**: the
archetype that dominates the *general* ladder population (Grimmsnarl, played by nearly half of
all recent games) is dramatically **less** represented among the *skilled/successful* population
(Top-100) than its raw popularity would predict — while Dragapult ex shows the opposite pattern
by the widest margin of any archetype tracked (+14.4 percentage points, over 4x its general-
population share). This is directly consistent with two things this project already knew
independently and did not previously connect: (1) Grimmsnarl's own recent-period win-rate trend
is a "meaningful decrease" even as its popularity keeps "strongly rising" (Part 3) — a real
overhype/underperformance signal in the general population; (2) Dragapult's recent win-rate
trend is a "meaningful increase" on a flat/unpopular pick rate (Part 3) — an underexplored,
apparently-improving pick.

**[HYPOTHESIS, not fully disentangled]**: this gap could reflect (a) genuinely superior deck
power once piloted well, (b) selection bias (only more sophisticated/deliberate builders choose
a less-popular deck like Dragapult, so its Top-100 pilots are a skill-filtered sample even before
accounting for the deck itself), or (c) both. This report cannot cleanly separate (a) from (b)
with the data pulled this session — flagged explicitly as the **[MOST IMPORTANT UNKNOWN]**
(Part 15).

**[GAP]**: the historical dataset ends 2026-08-10; the Top-100 pull is from 2026-08-13 — only a
3-day gap, unlikely to itself explain a swing this large, but not a perfectly time-matched
comparison. **[GAP]**: the historical dataset is an unweighted sample of ladder games (all skill
levels mixed via matchmaking), not itself a skill-stratified snapshot — the comparison above is
"all-players" vs. "best 100 players," which is the intended contrast, but means the two
populations are not otherwise controlled for anything else that correlates with skill (e.g.
newer accounts, submission recency).

---

## Part 13 — Statistical discipline recap

Explicitly restating sample sizes for every headline claim in this report, per the task's
requirement:

| Claim | n | Confidence label |
|---|---:|---|
| Dragapult ex Top-100/50/20/10 representation | 99 resolved / 19 Dragapult | Real census of the current leaderboard — not a sample, a full pull (subject to the 1-team-unresolved and ≤3-episode-sample caveats in Part 1) |
| Dragapult vs. Fezandipiti/Grimmsnarl matchup (GOOD) | 76 each | USABLE tier (this project's own established gate) |
| Dragapult vs. Kangaskhan/Lucario/Mewtwo matchup (BAD) | 37 / 16 / 12 | LOW_CONFIDENCE / INSUFFICIENT / INSUFFICIENT — directional only |
| Crustle immunity mechanism itself | engine-verified on ≥1 concrete replay (not a statistical claim) | FACT, not a sample-size question |
| Crustle-package prevalence across archetypes | exhaustive check of `deck_to_archetype.csv`, all matching decks use card 345 | FACT (full enumeration, not a sample) |
| Dragapult's 50-variant "unsolved" finding | 337 games / 50 exact lists | FACT (full enumeration of the historical dataset's Dragapult games) |
| Mega Lucario ex "niche/policy-driven" finding | n=3 Top-100 agents | Directional only — 3 is too thin for a population claim, but the internal spread (1 outlier vs. 2 near-identical others) is itself the evidence, not the raw count |
| General-vs-Top100 share gap (Part 12) | 184 (Dragapult recent) vs. 19/99 (Top-100) | Both real, neither huge; the **direction and rough magnitude** of the gap is the claim, not a precise percentage |

No claim in this report treats a single-digit-n matchup as proven. Every BAD-matchup claim
against Dragapult is explicitly labeled directional/small-sample except the Crustle **mechanism**
itself, which is a card-text + engine-verification fact, not a statistical inference.

---

## Part 14 — Final decision matrix

**Q1. Is Dragapult ex represented among successful Top-100 agents?**
Yes — 19/99 resolved (19.2%), tied for the most common archetype in the field. **[FACT]**

**Q2. Is Dragapult represented in Top-20?**
Yes — 6/20 (30.0%), tied for the most common. **[FACT]**

**Q3. Is Dragapult represented in Top-10?**
Yes — 3/10 (30.0%), tied for the most common, including rank #2 overall. **[FACT]**

**Q4. Is there evidence Dragapult itself imposes a strategic ceiling?**
Partial. It does not appear capped in overall representation (rises toward the top, not away
from it) — but it does have at least one real, mechanistically-explained bad matchup (Crustle/
Kangaskhan, Part 7) that no policy improvement alone can fully close while it runs a sole `{ex}`
attacker. **[SUPPORTED, narrow]**: a ceiling exists against *that specific opponent type*, not
against the field broadly.

**Q5. Is Mega Lucario demonstrably stronger than Dragapult in the current meta?**
No. Lucario has a far smaller, thinner Top-100 population (3 vs. 19) with a policy-outlier
pattern (Part 6/9), while Dragapult shows the broader "many independent successful pilots"
pattern this project treats as the stronger evidence standard. **[SUPPORTED]**: Dragapult has
the stronger population-level evidence; Lucario's best single data point (Luca) is strong but
narrow.

**Q6. Is Crustle a major structural counter to Dragapult?**
Yes, mechanistically — but it is a **generic `{ex}`-attacker wall** riding inside one specific
archetype (Mega Kangaskhan ex, 13% of Top-100), not a dedicated or common standalone threat.
**[FACT for the mechanism; HYPOTHESIS/directional for the resulting win-rate magnitude]**.

**Q7. What archetype has the strongest evidence of being meta-dominant?**
**Mega Kangaskhan ex** — #1 overall rating (1227.1), rises from 13%→30% Top100→Top10, 13
independent successful pilots (Part 9's deck-effect pattern), plus a coherent built-in answer
(Crustle) to the field's dominant `{ex}`-attacker paradigm. **Dragapult ex is a close second** by
representation breadth (19 pilots vs. 13, tied at the Top-10 tier) even though its single
highest rating (1217.0) is marginally below Kangaskhan's (1227.1).

**Q8. What strategic features distinguish Top-10 decks from the broader Top-100?**
Very high HP (Part 10), plus either an unconditional resource/consistency engine or a wide,
undiscovered build space rather than one "solved" list, plus flexible/bench-reaching damage over
raw single-hit ceiling (Part 8/10). No healing or heavy resource-recursion pattern was found in
this session's card-text sample.

**Q9. Is our current problem primarily policy, deck, matchup, both, or insufficient data?**

**D — both policy and deck/matchup**, with the deck-level component narrower than a naive
reading of "our rating is low" would suggest:
- Genuine deck-construction gap exists (Buddy-Buddy Poffin/Munkidori absence, Part 11) —
  addressable without changing archetype.
- Genuine, mechanistic matchup gap exists against one specific, real, top-tier archetype
  (Crustle/Kangaskhan) — not addressable by policy tuning alone, but also not evidence the
  archetype itself is wrong, since it doesn't block Dragapult's other matchups.
- Separately, this project's own existing policy audits (`V8_NEXT_BOTTLENECK_AUDIT.md`,
  `PHANTOM_DIVE_FORENSIC.md`) already document real, independent policy-layer inefficiencies
  (unanswered lethal threats, ~48% Phantom Dive allocation misses) unrelated to deck choice.
- **Not** primarily "the deck is wrong" (C alone) — the strongest data source in this whole
  project (real Top-100 representation) argues against that reading.

---

## Part 15 — Final verdict

### DRAGAPULT STATUS: **2 — VIABLE BUT MATCHUP-DEPENDENT**

Real Top-100 leaderboard data is the strongest evidence this project has assembled on deck
viability to date, and it points clearly away from "strategically inferior" and toward "a viable,
even disproportionately successful archetype among skilled agents, with at least one real,
mechanistically-explained hard matchup." This is not "1 — STRONG/META-VIABLE" only because a
genuine, structural bad matchup exists against a top-tier opponent (Mega Kangaskhan ex/Crustle)
that cannot be fully resolved without either a deck change or a specific counter-plan — but it
is well clear of "3 — QUESTIONABLE" or "4 — META-DISADVANTAGED," both of which the representation
data actively contradicts.

### MOST IMPORTANT META INSIGHT

**The general ladder population's deck popularity is a poor, sometimes inverted, proxy for what
wins among skilled agents.** Grimmsnarl dominates the general population (44.3% recent share)
while its win-rate trend is declining and its Top-100 share is less than half that (19.0%);
Dragapult ex is nearly invisible in the general population (4.6%) while over-represented by more
than 4x among the field's actual top performers (19.0%, rising to 30% at Top-10). Any future
meta-analysis work in this project that relies on the general-population historical dataset alone
(as most of sessions 4–12 did) should be read with this gap explicitly in mind — general
popularity and top-tier success are measuring different things on this ladder.

### MOST IMPORTANT UNKNOWN

Whether Dragapult's strong Top-100 representation reflects genuine deck power once well-piloted,
or a selection effect (only more sophisticated builders/agents choose an unpopular deck, so its
Top-100 sample is pre-filtered for skill independent of the deck itself) — Part 12 flags this
explicitly and this session's data cannot cleanly separate the two. Resolving it would need
either a controlled comparison (same policy, different decks) or tracking whether Dragapult's
share among *new* Top-100 entrants keeps rising as the ladder matures.

### "Should we seriously consider testing a different deck after V8?"

**NOT YET.**

The representation and matchup evidence does not support abandoning Dragapult ex on deck-choice
grounds — it is one of the two most successful archetypes at the top of the real ladder, piloted
successfully by a broad, independent population. The case for *reconsidering* would need to rest
specifically on the Crustle/Kangaskhan structural matchup (Q6) becoming a large enough share of
our actual opponent pool to matter, which this report does not measure (that would require our
own agent's real opponent-archetype distribution, out of scope here — see the existing
`V8_NEXT_BOTTLENECK_AUDIT.md` opponent-mix data for the closest existing proxy, itself flagged
there as small-n/INSUFFICIENT DATA). Given the deadline pressure (Simulation final submission
2026-08-16, `[[project-ptcg-status]]`), a full deck change carries real switching cost against
uncertain payoff; the better-supported next step, if any, is narrower: address the identified
deck-construction gap (Part 11) and/or a specific Crustle counter-plan, not a wholesale deck
change. This is a report, not an implementation — no such follow-up was started here.

---

## Deliverables

`tools/pull_top100_ladder_audit.py` (data pull), `tools/build_top100_meta_audit_v1.py`
(analysis). Raw: `data/top100_audit/{leaderboard_raw.json, teams/*_episodes.json, replays/}`
(gitignored). Structured: `results/top100_audit/{pull_checkpoint.json, leaderboard_decks.csv,
tier_archetype_frequency.csv, tier_summary.csv, archetype_tier_pivot.csv,
special_archetype_representation.csv, policy_vs_deck_top100.csv}` — full 100-row detail
preserved, never discarded after aggregation, per this project's standing raw-data-preservation
rule. No agent, deck, weight, or submission changes were made in the course of this audit.
