# V13 Implementation Report: Turbo Consistency Deck

## Objective

Test whether a "brick-proof", highly consistent deck built specifically for
what a greedy, one-ply policy can exploit (maximal simple draw/search, no
situational/control cards, straightforward attackers) outperforms the
standard V6 meta deck (`decks/dragapult_ex.csv`), holding the decision
policy fixed. This is a **deck-selection experiment**, not a policy
experiment.

Per the governing task's explicit constraints:
- Baseline policy is **V6** (`src/agents/dragapult_policy_v6.py`), not V10's.
- **No lookahead or search** was added (V11's territory, not touched).
- **V8/V9's survival/defensive-retreat heuristics are entirely absent** --
  this file was forked directly from V6, which predates that code, not from
  V8/V9/V10 with the heuristic stripped out afterward.
- **Not submitted to Kaggle.** Built and packaged locally only, per
  instruction, awaiting explicit approval.

## Files created

| File | What it is |
|---|---|
| `src/agents/dragapult_policy_v13.py` | Byte-for-byte fork of `dragapult_policy_v6.py`, diff limited to: the deck path constant, one new `Cheren` card constant, one new `hand_score` branch, one extended `OptionType.PLAY` branch, and docstrings. |
| `src/agents/dragapult_agent_v13.py` | Thin binding, identical structure to `dragapult_agent_v6.py`, imports V13's policy module instead. |
| `src/agents/final_candidate_agent_v13.py` | Safety-wrapped submission candidate, identical structure to `final_candidate_agent_v6.py`/`_v10.py`. |
| `main_v13.py` | Local entry point, same deck.csv-mismatch caution pattern as `main_v10.py` (V13's deck differs from the shared root `deck.csv`, so it never trusts that file blindly). |
| `decks/dragapult_v13_turbo.csv` | The new 60-card turbo decklist (below). |
| `tools/verify_v13_real_game_smoke_test.py` | Local self-play/cross-play smoke test (5 real games through the compiled engine). |
| `tools/build_submission_challenger.py` | Extended (not forked) with a `v13` entry so the shared, already-validated packaging pipeline covers V13. |
| `submission/challenger_v13.tar.gz` | Packaged, NOT uploaded. |

No V6/V8/V9/V10/V11/V12 file was modified except the additive `v13` entries
in `tools/build_submission_challenger.py`'s `VALID_VERSIONS`/`DECK_SOURCE`
dicts (a shared, versioned tool all challengers already register with).

## Decklist diff (`decks/dragapult_ex.csv` -> `decks/dragapult_v13_turbo.csv`)

Both are 60 cards. Net change: 4 cards types cut entirely (8 slots), 5 cards
types added/increased (8 slots).

### Cut entirely

| Card | Count removed | Why |
|---|---|---|
| Crushing Hammer (1120) | 4 | Pure control/disruption -- coin-flip discard of an opponent's Energy. Does nothing to advance V13's own board, adds variance a greedy scorer can't plan around, and contributes zero consistency. Exactly the "situational/control card" category the task asked to remove. |
| Lucky Helmet (1156) | 1 | Reactive Pokemon Tool ("if the Pokemon this is attached to is damaged by an opponent's attack, draw 2") -- only pays off if the opponent chooses to attack it, a condition outside the deck's own control. A "situational tool" per the task's own example category. |
| Unfair Stamp (1080) | 1 | ACE SPEC, usable only "if any of your Pokemon were Knocked Out during your opponent's last turn" -- a conditional draw card gated on an event the deck doesn't control, the opposite of brick-proof. Also frees the deck's single ACE SPEC slot (now unused, which is fine -- the legality rule is "at most 1", not "exactly 1"). |
| Team Rocket's Watchtower (1256) | 2 | Situational tech stadium (only relevant against Colorless-ability decks). No effect on this deck's own consistency. |

### Unchanged (already at the legal 4-copy max, or already fully generic)

Dreepy (119) x4, Drakloak (120) x4, Dragapult ex (121) x3, Fezandipiti ex
(140) x1, Latias ex (184) x1, Budew (235) x2, Meowth ex (1071) x1, Rare Candy
(1079) x2, Buddy-Buddy Poffin (1086) x4, Night Stretcher (1097) x2, Ultra
Ball (1121) x4, Boss's Orders (1182) x3, Crispin (1198) x4, Lillie's
Determination (1227) x4.

Rare Candy was deliberately **kept**: although its play condition is
multi-part (needs a Stage-2 in hand, a same-line Basic in play that didn't
enter play this turn, not turn 1), it is the deck's core consistency engine
-- it is what lets the deck reach its attacker on turn 2 instead of turn 3+,
and V6's `hand_score`/`PLAY` scoring for it is already simple and unconditional-feeling
in practice (`no_more_dex` gate aside). Cutting it would directly hurt the
"brick-proof, fast, consistent" goal, not help it.

### Increased / added

| Card | Before | After | Rationale |
|---|---|---|---|
| **Ultra Ball** (1121) | 4 | 4 (unchanged) | Already at the legal max. This *is* the deck's "maximize generic search" card the task named -- no card in this engine's pool is literally "Nest Ball" (searches a Basic straight to Bench); Buddy-Buddy Poffin (below) fills that role instead, and Ultra Ball fills the "any Pokemon to hand" role. Both were already maxed, so no change was needed to satisfy "maximum copies." |
| **Buddy-Buddy Poffin** (1086) | 4 | 4 (unchanged) | This engine's functional analog to real-TCG "Nest Ball" (searches up to 2 Basic Pokemon, ≤70 HP, straight to the Bench). Already at the legal max of 4. |
| **Lillie's Determination** (1227) | 4 | 4 (unchanged) | This engine's functional analog to "Professor's Research" (shuffle hand into deck, draw 6 -- or 8 at exactly 6 prizes left). No plain "Professor's Research"/"Nemona"/"Hop"/"Iono" card exists in this engine's (custom) card pool -- confirmed by grepping the full card database and the compiled engine's `all_card_data()` output. Already at the legal max of 4, satisfying "Ensure 4x Professor's Research" via its closest functional equivalent. |
| **Cheren** (1224) | 0 | 4 | **New card added.** "Draw 3 cards" -- fully unconditional Supporter, no discard cost, no coin flip, no board-state requirement. This is the deck's actual answer to the task's "add simple, unconditional draw supporters (e.g., Nemona, Hop, or Iono)" instruction, substituting the closest available real equivalent since none of those exact cards exist in this pool (Urbain, cardId 1236, is a second "Draw 3" Supporter that was considered but not added -- Cheren alone already fills all 4 freed-up copies needed; adding a second distinct draw-3 card would have required cutting something else not on the "situational/control" list). |
| **Poke Pad** (1152) | 3 | 4 | Topped up to the legal max. Generic "search any non-Rule-Box Pokemon to hand" -- already correctly scored by V6's existing `hand_score`/`PLAY` logic (`elif id == Poke_Pad: ...`), so no new scoring code was needed, just more copies for search consistency. |
| **Brock's Scouting** (1210) | 2 | 3 | Generic "search up to 2 Basic or 1 Evolution Pokemon to hand" Supporter. Increased (not maxed to 4, to leave room in the 8-slot budget for the energy bump below) -- already correctly scored by existing `hand_score`/`PLAY` logic, no new scoring code needed. |
| **Basic Fire Energy** (2) | 4 | 5 | Energy consistency bump per the task's instruction. The deck ran a tight 4/4 split (8 total energy in 60 cards); +1 raises the odds of a live energy drop in the opening hands/turns without meaningfully diluting the deck. |
| **Basic Psychic Energy** (5) | 4 | 5 | Same rationale as Fire Energy -- Dragapult ex's main line runs on Psychic energy, so this is the higher-priority of the two, but both were bumped by the task's suggested "1 or 2" to keep the two energy types balanced (matches Crispin's own "search 2 different Basic Energy types" effect, which works best with both types live). |

Total: -8 (cuts) + 8 (additions/top-ups) = 0 net change, 60 cards exactly.
Deck legality (exactly 60 cards, ≤4 copies of any non-basic-energy card, ≥1
Basic Pokemon, ≤1 ACE SPEC) verified via a real `battle_start` call
(`tools/deck_validator.py decks/dragapult_v13_turbo.csv` -> `LEGAL`).

## Scoring compatibility (Objective 3)

Cheren (cardId 1224) is the only genuinely new card in the pool that V6's
engine had never seen or scored (every other added/increased card --
Poke Pad, Brock's Scouting, both basic energies -- was already handled by
V6's existing scoring branches, just needed more physical copies). Two
changes to `src/agents/dragapult_policy_v13.py`:

1. **`hand_score`**: added an `elif id == Cheren:` branch, gated the same
   way as the existing `Lillie_Determination`/`Crispin` branches
   (`if not ignore_count or support_count == 0:`, i.e. "score it fully
   unless we've already committed to a different Supporter this turn"),
   returning a hardcoded `32000`. Placed below Lillie's Determination's
   `45000` (a bigger draw wins when both are in hand) but well above generic
   Item scores, so the greedy agent always prefers playing it over doing
   nothing.
2. **`OptionType.PLAY` branch**: extended the existing
   `elif card.id == Crispin or card.id == Brock_Scouting:` clause to also
   match `Cheren`, reusing its `score = 35000 if card.id == self.use_support else -1`
   logic unchanged -- Cheren now competes for the single Supporter-per-turn
   slot exactly like every other simple Supporter already in the engine.

No other scoring branch was touched. Every attack-planning, retreat,
damage-counter, and evolution scoring path is byte-identical to V6.

## Local validation

- `tools/deck_validator.py decks/dragapult_v13_turbo.csv` -> **LEGAL**
  (errorType=0, real `battle_start` check, not a manual count).
- `tools/verify_v13_real_game_smoke_test.py` -- 5 full real games through the
  compiled engine (V13 self-play x2, vs. `abomasnow_agent`, vs. V6
  head-to-head, vs. `generic_mewtwo_agent`). All passed:
  - no crash across any game;
  - V13 attacked in every game;
  - V13 evolved (Dreepy->Drakloak or Drakloak->Dragapult ex) in every game;
  - V13 played Buddy-Buddy Poffin at least once;
  - **V13 played Cheren at least once** (games 1, 4, 5), confirming the new
    scoring branch is actually reachable and chosen by the greedy policy,
    not just present but dead code.
- `tools/build_submission_challenger.py --version v13` -- full pipeline pass:
  `main_v13.py` imports cleanly and exposes a 60-card `DECK`; deck legality
  re-validated; staged submission directory assembled and runs standalone
  (isolated from the dev-only `data/official/` path); archive built and
  inspected (`main.py`, `deck.csv`, `cg/`, `src/`, `decks/` at top level,
  no nested `main.py`).

## Deliverable

`submission/challenger_v13.tar.gz` (2.0 MB) -- packaged, **not submitted to
Kaggle**. A second, timestamped copy
(`submission/challenger_v13_20260814T035624Z.tar.gz`) was also produced by
the shared packaging tool's normal timestamping behavior; both are
byte-identical. Awaiting explicit approval before any Kaggle submission.
