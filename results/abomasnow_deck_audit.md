# Mega Abomasnow ex Deck Audit

Agent version: `src/agents/abomasnow_agent.py` (unchanged this phase)
Deck versions compared: `decks/abomasnow_ex.csv` (on-disk, pre-existing) vs.
`decks/abomasnow_ex_corrected_v1.csv` (new, this phase)
Source of truth: `sample_notebooks/a-sample-rule-based-agent-mega-abomasnow-ex-deck.ipynb`

## 1. What deck does the official notebook actually expect?

The notebook's code cell defines named constants with count comments (comments only —
the notebook never enumerates a literal 60-ID list, since it loads `deck.csv` from the
Kaggle dataset at runtime rather than hardcoding one):

| Card ID | Name | Count (per notebook comment) | Category |
|---|---|---|---|
| 721 | Kyogre | 2 | Pokemon |
| 722 | Snover | 4 | Pokemon |
| 723 | Mega Abomasnow ex | 4 | Pokemon |
| 1121 | Ultra Ball | 4 | Item |
| 1126 | Precious Trolley | 1 | Item |
| 1192 | Carmine | 4 | Supporter |
| 1227 | Lillie's Determination | 4 | Supporter |
| 1262 | Surfing Beach | 3 | Stadium |
| 3 | Basic Water Energy | 34 | Basic Energy |

**FACT**: these counts sum to exactly 60 (2+4+4+4+1+4+4+3+34=60), consistent with a
legal, complete decklist.

**FACT**: all four of `Ultra_Ball` (1121), `Precious_Trolley` (1126), `Carmine` (1192),
and `Surfing_Beach` (1262) are referenced by ID in the agent's scoring logic (see §3) —
they are not just flavor comments, the heuristic is written assuming these specific
cards are actually in the deck.

## 2. What deck is currently in `decks/abomasnow_ex.csv`?

**RESULT** (counted programmatically, all 60 lines parsed):

| Card ID | Name | On-disk count | Notebook-expected count |
|---|---|---|---|
| 3 | Basic Water Energy | 35 | 34 |
| 721 | Kyogre | 2 | 2 |
| 722 | Snover | 4 | 4 |
| 723 | Mega Abomasnow ex | 4 | 4 |
| 1121 | Ultra Ball | **0** | 4 |
| 1126 | Precious Trolley | **0** | 1 |
| **1145** | **Mega Signal** (Item) | **4** | 0 |
| **1158** | **Maximum Belt** (Pokemon Tool) | **1** | 0 |
| 1192 | Carmine | **0** | 4 |
| **1205** | **Cyrano** (Supporter) | **2** | 0 |
| 1227 | Lillie's Determination | 4 | 4 |
| **1235** | **Waitress** (Supporter) | **4** | 0 |
| 1262 | Surfing Beach | **0** | 3 |

Total: 60 cards on both sides, and the four Pokemon lines (Kyogre, Snover, Mega
Abomasnow ex) plus Lillie's Determination match exactly. The mismatch is confined to
the trainer/stadium package plus one extra basic Energy filling the count gap.

## 3. Which cards differ, and is the scoring logic dependent on them?

**FACT**: the on-disk deck entirely omits `Ultra_Ball` (1121), `Precious_Trolley`
(1126), `Carmine` (1192), and `Surfing_Beach` (1262), and instead includes four
cards the notebook never mentions: `Mega_Signal` (1145, ×4), `Maximum_Belt` (1158,
×1), `Cyrano` (1205, ×2), `Waitress` (1235, ×4). This is not a 1:1 substitution (11
substitute cards vs. 12 expected cards); the last card is made up by one extra Basic
Water Energy (35 instead of 34).

**FACT** (read directly from `src/agents/abomasnow_agent.py`, confirmed identical in
the notebook source):
- `OptionType.PLAY` branch special-cases `card.id == Ultra_Ball` (draw-conditioned
  score of 4000 or -1) and `card.id == Carmine` (score -1 or 3000, conditioned on
  Snover/Mega Abomasnow ex board state).
- `OptionType.CARD` under `SelectContext.DISCARD` special-cases `card.id == Carmine`
  (+30 if `Lillie's Determination` in hand).
- `OptionType.ABILITY` special-cases `card.id == Surfing_Beach` (score 2000 if a
  switch is preferred, else -1 — this is how the agent decides to use Surfing
  Beach's switch-effect instead of retreating).
- `Precious_Trolley` (1126) is *not* referenced anywhere in the scoring code even in
  the notebook itself — it has no special case and falls through to whatever generic
  default applies to its option type (e.g. the flat `score = 10000` PLAY default).
  This is a pre-existing property of the *notebook*, not something introduced by the
  deck mismatch.

**RESULT**: because the on-disk deck never contains `Ultra_Ball`, `Carmine`, or
`Surfing_Beach`, three of the four card-ID-specific branches above are **dead code**
under the current deck — they can never fire, no matter how the game plays out,
because `hand_score`/option-scoring only sees cards that can actually be drawn. The
four substitute cards (Mega Signal, Maximum Belt, Cyrano, Waitress) receive **no
special-case handling at all** in the agent and are scored purely by the generic
per-option-type defaults (e.g. any hand Supporter matching `OptionType.PLAY` with no
matching `elif` falls through to the flat `score = 10000` baseline, indistinguishable
from every other unscored card). Concretely:
- Mega Signal (Item, drawn via `OptionType.PLAY`) always scores the flat default,
  played as readily as anything else with a 10000 baseline.
- Waitress and Cyrano (Supporters) are likewise unscored specifically and compete
  only on the generic default, with no logic representing their actual effects
  (unlike Carmine, whose Lillie's-Determination-redundancy check and board-state gate
  reflect real thought about when to prefer/skip it).
- Maximum Belt is a Pokemon Tool, an entirely different card *category* than the Item
  `Precious_Trolley` it appears to be standing in for by slot — the agent's very
  narrow tool-handling (`ATTACH` branch scores any tool implicitly via the generic
  `energy_count`-based Pokemon-focused logic; there is no tool-specific branch at all
  in this agent, so Maximum Belt's attach decision is not meaningfully different from
  how it'd be scored blind either way).
- Surfing Beach's absence means the agent's one stadium/switch-avoidance interaction
  never gets exercised in real games with this deck.

**HYPOTHESIS**: this heuristic gap (four cards played by generic fallback score
instead of purpose-built logic, three purpose-built branches never firing) is a
plausible contributor to Abomasnow's comparatively weak measured performance,
especially the 18.5% win rate vs. Iono's from the FIRST REPORT — but this is not yet
demonstrated causally; see §5 for the controlled comparison.

**QUESTION**: how did the on-disk deck end up with this specific substitute-card set?
Nothing in the repo's history/docs from session 1 documents a deliberate reason (e.g.
an intentional experiment) — the most likely explanation is a copy/paste or
placeholder deck built independently of the notebook's actual named list, but this is
not verified and is flagged here rather than assumed.

## 4. Corrected deck

Created `decks/abomasnow_ex_corrected_v1.csv`: 60 cards built directly from the
notebook's named constants and comment counts (§1 table), i.e. 2× Kyogre (721), 4×
Snover (722), 4× Mega Abomasnow ex (723), 4× Ultra Ball (1121), 1× Precious Trolley
(1126), 4× Carmine (1192), 4× Lillie's Determination (1227), 3× Surfing Beach (1262),
34× Basic Water Energy (3). Validated via `battle_start`: `errorPlayer=-1,
errorType=0` (legal). The original `decks/abomasnow_ex.csv` is left untouched (not
overwritten) so the previous 1200-game benchmark's deck is still reproducible.

## 5. Corrected vs. current — controlled comparison

See `results/abomasnow_deck_comparison/` for the raw per-game data and
`experiments/abomasnow_deck_fix.md` for the experiment record (hypothesis, exact
change, sample size, result, conclusion, keep/revert decision). Summary duplicated
into the Competitive V1 report once complete.
