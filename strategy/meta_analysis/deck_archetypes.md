# Deck Archetypes — Initial Meta/Deck Analysis (Step 12)

Every claim below is explicitly tagged as one of:
**[FACT]** verified from official notebooks/engine source, **[RESULT]** measured from our own
tournament runs, **[HYPOTHESIS]** plausible but untested, or **[QUESTION]** open for future
research. Do not treat RESULT or HYPOTHESIS items as established competitive meta — they come
from small, local, non-adversarial samples (see [Scope and limits](#scope-and-limits) below).

## The four official sample decks

**[FACT]** The competition ships four complete rule-based agent examples, one per deck, in
`sample_notebooks/`. Three are ported and running in `src/agents/` this phase; one
(Mega Lucario ex) is documented here only.

| Deck | Stated difficulty | Core concept (from the notebook's own markdown cell) | Ported this phase? |
|---|---|---|---|
| Mega Abomasnow ex | "Beginner Friendly" | Attacks with Hammer-lanche (discard top 6 deck cards, 100 dmg per Basic Water Energy discarded); large Basic Water Energy count to fuel it; Kyogre provides an alternate attacker so the deck doesn't run out of gas. | Yes — `src/agents/abomasnow_agent.py`, `decks/abomasnow_ex.csv` |
| Iono's deck | "Intermediate Level" | Bellibolt ex's Electric Streamer ability attaches unlimited basic Lightning Energy in one turn, feeding Voltorb's Voltaic Chain attack for very high, uncapped damage; Voltorb is a regular (non-ex) Pokemon so losing it only costs the opponent 1 prize; Kilowattrel refills the hand. | Yes — `src/agents/iono_agent.py`, `decks/iono.csv` |
| Dragapult ex | "Advanced Level" | Aggressive early setup aiming to attack as soon as possible; Phantom Dive can take multiple KOs (up to 3 prizes) in a single turn via 6 spread damage counters across the opponent's board; runs 4x Crispin for consistency. | Yes — `src/agents/dragapult_agent.py`, `decks/dragapult_ex.csv` |
| Mega Lucario ex | "Intermediate Level" | Flexible multi-attacker deck: Mega Lucario ex for high damage, Hariyama/Solrock as lighter/situational secondary attackers, switching attack plan turn-to-turn based on board state; Lunatone refills the hand, Fighting Gong develops the board. | No — documented only, not built/validated this phase |

**[FACT]** All four notebooks share, near-verbatim, the same `get_card()` helper and the same
overall shape (load `deck.csv`, build a `{cardId: CardData}` table from `all_card_data()`,
score every legal option, pick the top-scoring ones). They differ in **which selection tail**
they use: Abomasnow ex and Iono's always fill to `select.maxCount` regardless of score sign;
Dragapult ex (and, from this notebook, apparently Mega Lucario ex — not independently
re-verified this phase) can decline down to `select.minCount` when only negative-scoring
choices remain in bench/setup selections. See `src/agents/common.py` for where this is
preserved per-deck rather than unified away.

**[FACT]** Only Mega Abomasnow ex had an official, engine-verified-legal `deck.csv` available
on disk (`data/official/sample_submission/sample_submission/deck.csv`) — its actual support
cards (IDs 1145, 1158, 1205, 1235) differ from what the notebook's own scoring ladder names
(Ultra Ball, Precious Trolley, Carmine, Surfing Beach), so those specific decision points fall
back to generic default scores rather than deck-tuned ones in our port. Iono's and Dragapult
ex's deck files were hand-constructed from each notebook's stated per-card counts (independently
summed to exactly 60 for both) and confirmed legal via `battle_start` (`errorType=0`) before
being trusted.

## Preliminary local benchmark results

**[RESULT]** All numbers below are from `tools/tournament.py` runs of 200 games per matchup
(1200 games total, alternating which agent occupied engine slot 0 every game, zero aborted
games). Raw per-game records are preserved at `results/games/*.jsonl`; this table is a derived
summary, not a replacement. See [Scope and limits](#scope-and-limits) — **this is a
preliminary benchmark, not statistically conclusive evidence of relative agent strength.**

Win rate of row agent over column agent (200 games each pairing):

| | Abomasnow ex | Dragapult ex | Iono's | Random (official template) |
|---|---|---|---|---|
| **Abomasnow ex** | — | 0.440 | 0.185 | 0.915 |
| **Dragapult ex** | 0.560 | — | 0.655 | 0.975 |
| **Iono's** | 0.815 | 0.345 | — | 0.985 |
| **Random** | 0.085 | 0.025 | 0.015 | — |

Full first-player-split breakdown: `results/leaderboard.csv`. Raw games: `results/games/`.
Loss categorization: `tools/analyze_games.py --agent <name>`.

**[RESULT]** All three ported heuristic decks beat the official random-agent template
decisively (91.5%–98.5%), a basic sanity check that each port is doing something purposeful
rather than being broken/degenerate.

**[RESULT]** Among the three heuristic decks, the observed local ordering is
Iono's > Dragapult ex > Abomasnow ex (Iono's beat both others; Dragapult ex beat Abomasnow ex).
This is the deck/pilot-quality combination we happened to port, not a claim about the cards
themselves — see limits below.

**[RESULT]** Loss-reason breakdown (`tools/analyze_games.py`) shows "no Pokemon in Active
Spot" (engine reason 3) as the dominant loss reason for Abomasnow ex (221/292 losses) and a
minor one for Iono's/Dragapult ex, while "zero prizes remaining" (reason 1) dominates for
Iono's (139/171) and Dragapult ex (143/162). This suggests Abomasnow ex's losses often come
from running out of board presence rather than a straight prize race, while the other two more
often lose a full prize race.

**[HYPOTHESIS]** First-player status appears to correlate with losing for two of the three
decks (Abomasnow ex: 202/292 losses as first player; Iono's: 146/171 losses as first player) —
plausibly connected to the real Pokemon TCG rule that the first player doesn't draw a card or
attack on their first turn, a real tempo cost baked into the engine. **This is a plausible
but untested explanation**, not confirmed causally.

**[HYPOTHESIS]** Dragapult ex shows the *opposite* pattern: 160/162 of its losses happened
while playing *second*, not first — a striking reversal from the other two decks that we do not
have a confirmed explanation for. One candidate mechanism worth checking: Dragapult ex's ported
logic has a setup-phase rule (`SETUP_BENCH_POKEMON` scoring) that behaves differently depending
on `state.firstPlayer == my_index`, so its own bench-building differs by first/second-player
status in a way none of the other three decks' logic does — but we have not traced this through
to confirm it's the actual cause. Flagged as a concrete next investigation, not a conclusion.

## Scope and limits

**[FACT]** This analysis reflects only: (a) the four official notebooks' *stated* design intent,
and (b) 1200 games among four specific agents (three heuristic ports plus the official random
template) on this machine. It does **not** reflect the actual competitive Kaggle ladder meta —
we have not yet pulled the live-ladder replay/episode datasets
(`kaggle/pokemon-tcg-ai-battle-episodes-index` and dated dumps, plus the community
`busyaprime/pokemon-tcg-ai-battle-live-meta` dataset) noted in `docs/environment.md` §5. Treat
every RESULT/HYPOTHESIS above as "what these four specific implementations did to each other
locally," not "which deck is objectively strongest" or "what the field is actually playing."

**[QUESTION]** Does the observed Iono's > Dragapult ex > Abomasnow ex ordering hold against a
wider pool of opponents, or is it an artifact of these three specific ports' tuning quality
(e.g. Abomasnow's mismatched support-card lineup, noted above, may be underselling that deck)?

**[QUESTION]** Is the first/second-player loss split (and Dragapult ex's reversal of it) a real
structural property of each deck's strategy, or a bug/quirk specific to how each notebook's
setup-phase logic happens to be written?

**[QUESTION]** How does local performance correlate with actual Kaggle ladder skill rating,
once we can compare against real ladder data?
