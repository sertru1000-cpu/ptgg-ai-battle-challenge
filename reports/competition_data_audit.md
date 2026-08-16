# Official Competition Data Audit (Competitive V2, Part 0)

Sources used, in the order actually available to this environment: the Kaggle
API (`kaggle` Python package, authenticated, per
[[reference-kaggle-ptcg-access]]) for the competition's Data page file
listing, page content (Overview/Data/Rules/Timeline/FAQ), and forum topic
text; `WebFetch` for the external (non-Kaggle) API docs mirror; and the
already-downloaded `data/official/` assets (card CSVs, engine C++ source,
sample submission) re-verified against the live API's file listing rather
than assumed unchanged. Kaggle's own competition subpages (`/data`,
`/overview`, `/rules` as rendered HTML) are JS-gated and return only a page
title to an unauthenticated fetch — confirmed again this session, matching
the session-1 finding in `docs/environment.md` — so the Kaggle **API**
(`competition_list_files`, `competition_list_pages`,
`competition_list_topic_messages`), not `WebFetch` on the Kaggle URLs
directly, was the mechanism that actually worked for those pages.

## 1. Official Data page assets — complete, verified listing

**[FACT]** `kaggle competitions files -c pokemon-tcg-ai-battle` (paginated via
the Python API to get all pages, not just the first) returns **exactly 60
files**, and this list is byte-identical in name/count to what
`data/official/` already contains from session 1 — nothing new has been
added to the Data page since then. The 60 files are: `Card_ID List_EN_.pdf`
(137.6MB), `Card_ID List_JP_.pdf` (182.3MB), `EN Card Data.csv` (358KB),
`JP Card Data.csv` (443KB), 46 files under `ptcg_engine/ptcgProgram 22/`
(C++ header/source, license, project files), and 9 files under
`sample_submission/sample_submission/` (the `cg` Python package + native
libs for all 3 platforms, `deck.csv`, `main.py`).

**[FACT]** There is **no separate "restricted card list" file, no additional
decklist file, and no replay/episode/meta file anywhere on the official Data
page.** Everything the competition provides for deck/card research is the
two CSVs + two PDFs (card metadata/reference) and the engine source (ground
truth for rules/legality behavior).

## 2. Card pool — exact, engine-verified inventory

**[FACT]** (`all_card_data()` called live against the loaded `cg.dll`):
**1267 unique cards** total, card IDs contiguous `1..1267`. Breakdown by
`CardType`: **1056 Pokemon, 77 Item, 61 Supporter, 27 Tool, 26 Stadium, 12
Special Energy, 8 Basic Energy.** Of the Pokemon: **121 have the `ex` flag,
30 have the `megaEx` flag** (Mega ex, a subset counted separately from
plain `ex` in the API — not verified here whether `megaEx` also implies
`ex`, flagged as a minor open detail), **32 have the `tera` flag** (Tera
Pokemon take no damage from attacks while benched, per
`docs/environment.md`), **29 cards have the `aceSpec` flag** (max 1 per deck).

**[FACT]** `EN Card Data.csv` / `JP Card Data.csv` have **2022 rows**, not
1267 — this is **not** a discrepancy in the card pool; it's a **row-per-
attack** schema (a Pokemon with 2 attacks gets 2 rows sharing the same Card
ID). Verified directly: Card ID 678 (Mega Lucario ex) has exactly 2 rows,
one for "Aura Jab" and one for "Mega Brave", both listing the same Card ID.
Cross-checked the full ID sets: `set(csv Card IDs) == set(engine
all_card_data() IDs)`, both exactly 1267 unique values, zero symmetric
difference. **The CSV and the engine agree exactly; there is one unified
card pool, not two.**

**[FACT]** `EN Card Data.csv`'s "Category" column (distinct from
`CardType`) encodes special deck-legality/rule tags, not a card-type
taxonomy — `n/a` (1630 rows, ordinary cards), `Tera(*)` (competition Tera
sub-types, ~120 rows across colors), `Trainer's Pokemon(<name>)` (~200+ rows,
Supporter-linked "Trainer's Pokemon" tie-in cards for named Trainers like
Iono, N, Hop, Ethan, Larry, Steven, Cynthia, Marnie, Erika, Misty, Arven,
Lillie — this is the mechanic our own Iono's deck and its "Iono's Voltorb"
etc. cards use), `Ancient`/`Future` (Paldean-timeline mechanics), `Fossil`,
`Technical Machine`. These are real official-format mechanics reflected
faithfully in the engine, not competition-specific inventions.

**[FACT]** **`ENGINE CARD POOL` == `COMPETITION-LEGAL CARD POOL` == `CARD
DATA CSV POOL`** — all three are the same 1267-card set, per the
cross-verification above and per §3's deck-validation-source-code finding
that there is no additional restricted-list check beyond what's in
`Api.h`. This **corrects an unverified claim carried over from session 1**
(`docs/environment.md`, sourced from unauthenticated web research): "Rules
are 'Standard format... uniquely tailored for this tournament' with only
cards from an organizer-provided restricted list" — no such separate
restricted list exists as a file or as an extra validation check; the
engine's own `CardTable` (all 1267 cards) together with the 4 construction
rules in §3 **is** the complete legality definition, confirmed by reading
the exact validation source below.

**[FACT]** `CARDS USED BY OFFICIAL SAMPLE DECKS` is a tiny slice of the
1267-card pool: the 4 sample decks (§5) collectively use on the order of
60-70 distinct card IDs (exact count in `strategy/card_pool_inventory.md`).
The overwhelming majority of the legal card pool (>1200 cards) is untouched
by any of our current agents or decks.

## 3. Deck construction rules — exact, from engine source

**[FACT]** Read directly from `data/official/ptcg_engine/ptcgProgram
22/Api.h`'s `ApiBattleStart` (the actual function `battle_start()` calls)
and `Core.h`:

```cpp
constexpr int DECK_SIZE = 60;            // Core.h:11
constexpr int DECK_SAME_CARD_MAX = 4;    // Core.h:19
```

Validated, in this exact order, per deck (both players' decks independently):
1. Every card ID must exist in `CardTable` (else `errorType=1`).
2. At most 1 card with `aceSpec == true` (else `errorType=4`).
3. **Copy limit is keyed by card `name`, not card ID** — `nameCount[master.
   name]` must not exceed `DECK_SAME_CARD_MAX` (4), **except** for cards
   with `cardType == BasicEnergy`, which are exempt entirely (else
   `errorType=2`). This means two different card IDs that share the same
   printed name would count together toward the same 4-copy cap — not
   verified whether any such same-name/different-ID pairs actually exist in
   the current 1267-card pool (flagged as a **[QUESTION]** for deck-building
   tooling to check before it matters).
4. At least one card with `cardType == Pokemon && evolutionType == Basic`
   must be present (else `errorType=3`).
5. Deck must be exactly 60 cards (`DECK_SIZE`).

**[FACT]** No other check exists in `ApiBattleStart`. In particular, there
is **no check against any external/restricted card list** — confirming §2's
finding.

## 4. Official sample decks — complete inventory

**[FACT]** Exactly **4** rule-based sample decks exist across the official
sample notebooks (`sample_notebooks/a-sample-rule-based-agent-*-deck.ipynb`,
6 total notebooks in the repo, no others found): Mega Abomasnow ex
("Beginner Friendly"), Iono's ("Intermediate Level"), Mega Lucario ex
("Intermediate Level"), Dragapult ex ("Advanced Level"). All 4 are already
ported (`src/agents/*.py`, `decks/*.csv`), audited for notebook-fidelity
(Competitive V1 for Dragapult; this session cross-checked Abomasnow/Lucario/
Iono construction against `CardImpl.h` in the Search V2 audit's Part A2 —
see `results/search_v2_audit.md`), and confirmed engine-legal via
`battle_start` (`errorType=0` for all 4, including the corrected
`decks/abomasnow_ex_corrected_v1.csv`). No 5th sample deck or additional
deck-construction notebook exists anywhere in the provided materials —
verified by re-listing both the local `sample_notebooks/` directory and the
live Data-page file listing above, neither of which contains anything else.

**[FACT]** `data/official/sample_submission/sample_submission/deck.csv` (the
official minimal template, paired with the random-choice `main.py`) is a
**5th distinct legal decklist** already in use throughout this project as
"random_agent"'s deck — not a rule-based sample deck (no accompanying
heuristic), but a genuine 5th legal decklist worth noting for completeness.

**[FACT]** The RL/MCTS sample notebook's `sample_deck` (63 cards) is
explicitly **not legal** (wrong card count, `docs/environment.md` already
noted this in session 1) and is a template placeholder only — reconfirmed,
not a real 5th archetype.

## 5. Replay / episode / meta data

**[FACT]**, confirmed directly from the Data-page description text (via
`competition_list_pages`, not inferred): *"You can access episode replays
for your Submissions from the Submissions tab... You can download replay
files from other teams from the Leaderboard, and **we will enable a daily
episode export of the top rated episodes** (to help BC/RL/IL). This will be
posted in the competition forums."* This is an **official, organizer-
sanctioned** data channel, explicitly intended to support behavior-cloning/
RL/imitation-learning research — not an incidental leak.

**[FACT]** That daily export is the Kaggle dataset family
`kaggle/pokemon-tcg-ai-battle-episodes-<date>` (published by the `kaggle`
org account, not a third party), confirmed present via
`kaggle datasets list -s pokemon-tcg-ai-battle`: **56 daily dumps from
2026-06-16 (the competition's own Start Date) through 2026-08-10** (the day
before this session), each containing **~4,500-7,800 episodes** and roughly
21GB uncompressed (~750MB compressed) per day. License: **CC0-1.0** (public
domain equivalent). A companion tiny (2KB) `kaggle/pokemon-tcg-ai-battle-
episodes-index` dataset provides `manifest.csv` — one row per day with
episode count, total bytes, and top/median average skill score for that
day's episode set (copied into the repo:
`strategy/meta_analysis/episodes_manifest_2026-08-10.csv`).

**[FACT]** Only the tiny index dataset was downloaded and inspected this
session — the 56 daily ~750MB raw episode dumps themselves (potentially
>40GB combined) were **not** downloaded, due to time/storage budget in this
session, not a legality or accessibility barrier. This is an explicit,
honest scope limitation, not a claim that the raw data is inaccessible.

**[FACT]** A separate, **community-published** (not organizer-published)
dataset, `busyaprime/pokemon-tcg-ai-battle-live-meta` (CC BY 4.0, requires
attribution), aggregates a 2026-07-31 snapshot of the live ladder meta —
almost certainly derived from the official daily episode exports above.
Downloaded and inspected in full (all 5 files, each under 10KB):
`tier_and_usage.csv`, `matchup_grid_winrate.csv`, `matchup_grid_games.csv`,
`deck_recommender.csv`, `game_length.csv` — copied into the repo at
`strategy/meta_analysis/live_meta_snapshot_2026-07-31/`. Contents analyzed
in full in `strategy/card_pool_inventory.md` and `reports/competitive_v2.md`
§6 (Meta Research) — headline: **8 named archetypes were active on the live
ladder as of 2026-07-31, and only 1 of them (Dragapult ex) overlaps with our
local 4-deck pool.**

**[FACT — availability/accessibility/usability, explicitly separated per
the prompt's instruction]**:
- **AVAILABLE?** Yes — both the official daily raw-episode exports and the
  community meta-aggregation dataset exist and are indexed/discoverable via
  the Kaggle Datasets API.
- **ACCESSIBLE?** Yes for both, via the same authenticated Kaggle API/CLI
  already used for the competition's own Data page (`kaggle datasets
  download`). Verified by actually downloading the two small ones; the raw
  per-day dumps were not downloaded this session (time/storage, not
  inaccessibility).
- **COMPETITION-USABLE?** Yes, with the license terms respected. The
  official episode exports are explicitly organizer-sanctioned for BC/RL/IL
  use per the Data-page text above, and Competition Rules section "2.6
  External Data and Tools" (see `reports/competition_mechanism.md`)
  permits External Data provided it's "publicly available and equally
  accessible to use by all Participants... at no cost" — both datasets
  qualify (CC0 and CC BY respectively, free, Kaggle-hosted, discoverable by
  any participant). The community dataset's CC BY 4.0 license requires
  attribution if its content/derived numbers are published or shared, which
  this project does (`strategy/meta_analysis/live_meta_snapshot_2026-07-31/`
  is attributed to `busyaprime` in this document and in
  `reports/competitive_v2.md`).
- **COMPETITIVELY USEFUL?** Yes, directly — see §6 of
  `reports/competitive_v2.md`: it's the only evidence in this project of
  what the actual competitive meta looks like, and it materially changes
  how confidently we can extrapolate from the local 4-deck benchmark to the
  real leaderboard (see Part E / anti-overfitting discipline).

## 6. Known unknowns (explicit, per instruction not to fabricate)

**[QUESTION]** Whether any two distinct card IDs in the 1267-card pool share
the exact same `name` (relevant to the copy-limit rule in §3) — not checked
this session.

**[QUESTION]** The raw daily episode dumps' internal schema/format (JSON
structure of a single episode) — not inspected, since none were downloaded.
Would need to be established before any direct replay-parsing work (Part C /
opponent modeling) could begin.

**[QUESTION]** Whether the `busyaprime` community meta dataset's 2026-07-31
snapshot is still representative 11 days later (as of this session) — no
more recent community snapshot was found; the underlying official daily
episode exports are current through 2026-08-10, so a fresher meta snapshot
could in principle be computed from them, but wasn't, this session.

**[QUESTION]** Whether `megaEx` and `ex` card-flag counts (30 and 121
respectively) overlap (i.e. does every `megaEx` card also report `ex=True`)
— not disambiguated this session.

See `reports/competition_mechanism.md` for the separate audit of
matchmaking/rating/submission mechanics (Part 0.7), and
`strategy/card_pool_inventory.md` for the full card/deck/meta data tables
(Part B deliverable).
