# Dragapult ex First/Second-Player Anomaly — Analysis

Agent version: `src/agents/dragapult_agent.py` (BEST_DRAGAPULT_AGENT, unchanged)
Experiment code: `tools/dragapult_first_second_experiment.py`
Raw data: `results/dragapult_first_second/*/games/*.jsonl` (+ `*_decisions.jsonl`)

## 1. Why the natural benchmark couldn't answer this directly

**FACT**: `tools/tournament.py` alternates which agent occupies engine slot 0 every
game, on the assumption that this produces a randomized first/second-player split
(the tournament docstring/env docs describe engine slot 0 as having "a real,
non-symmetric advantage" that alternation controls for).

**FACT** (read directly from `data/official/ptcg_engine/ptcgProgram 22/SetupProc.h`
lines 227-251): the engine's "go first?" yes/no question is *always* asked to the
player in **engine slot 0** specifically (`SetYesNoSelect(state,
SelectContext::IsFirst, 0)`, the `0` is the asked player's index) — but the
**answer** is not hardcoded; it is whatever that seat's agent returns for the `YES`
option (`SelectedIsFirst`: `firstPlayer = selectPlayer` if yes, `1 - selectPlayer`
if no). **This corrects a claim in `docs/environment.md`** ("Player slot 0 always
answers 'go first?' yes") — that phrasing conflated "who is asked" (always slot 0,
correctly identified) with "what they answer" (not hardcoded at all). `docs/
environment.md` has been updated (see its changelog note) to reflect this.

**FACT** (read from all four ported agents): `src/agents/abomasnow_agent.py`,
`src/agents/iono_agent.py`, and `src/agents/lucario_ex_agent.py` all score
`OptionType.YES = 1` unconditionally (i.e. always prefer "yes" whenever asked
anything, including IS_FIRST). `src/agents/dragapult_agent.py` is the only one that
special-cases it: `score = -1 if context == SelectContext.IS_FIRST else 1` — i.e.
it deliberately answers **NO** to "go first?", electing to go second, whenever it
is the one asked. This is not a porting artifact — see §3 (Phase 3 audit): it is
copied verbatim from the official notebook.

**RESULT** (counted directly from the existing session-1 raw data,
`results/games/*.jsonl`): because only engine slot 0 is ever asked, and both sides
of a Dragapult-vs-{Abomasnow,Iono} pairing have *deterministic, opposite*
preferences (Dragapult always says no, the other three agents always say yes),
Dragapult ends up as the second player in **200/200** games vs. Abomasnow and
**200/200** games vs. Iono, regardless of which engine slot it was alternated
into — alternating engine slot 0 does *not* produce a balanced first/second split
here, because both agents' answers are deterministic functions of who gets asked,
not of chance. Vs. Random (uses `random.sample` over all options, so it answers the
coin-flip question roughly 50/50 when it's the one asked), Dragapult was second in
156/200 (78%) and first in 44/200 (22%) — still skewed, for the same reason (it is
*always* second on the 50% of games it occupies slot 0 itself, and only sometimes
first on the other 50%).

**CONCLUSION of the "anomaly" as originally stated**: the FIRST REPORT's "160/162
losses occurred when Dragapult was second" is **not evidence that going second
causes losses** — it is close to a tautology, because Dragapult was second in
essentially all (200/200, 200/200) or most (156/200) of its games in the first
place. 160 of Dragapult's 162 total losses across the 600-game session-1 sample
being "when second" is compatible with second-player status simply being the
overwhelming base rate, not with second-player status being uniquely bad. This
needed a controlled experiment to actually separate the two (§2).

## 2. Controlled experiment: forcing the coinflip

`tools/dragapult_first_second_experiment.py` always seats Dragapult in engine slot
0 (so it is always the one asked) and wraps its agent so that, **only** for the
`IS_FIRST` decision, it directly returns the desired `YES`/`NO` option index
instead of consulting the agent's own (deterministic) scoring — every other
decision is delegated to the real, unmodified `dragapult_agent.agent()` unchanged.
This fully decouples "which engine slot" from "first or second" and gives a clean,
balanced comparison. 1000 games per condition (2000 per opponent, 6000 total),
zero aborted games, zero coinflip-wrapper mismatches (sanity-checked: every forced
game's actual `first_player_slot` matched the intended condition).

| Opponent | Dragapult win rate, FIRST (n=1000) | Dragapult win rate, SECOND (n=1000) | z | Significant? |
|---|---|---|---|---|
| random_agent | 98.10% | 96.70% | -1.97 | borderline (p≈0.049) |
| abomasnow_agent | **67.10%** | **56.30%** | **-4.97** | **yes, p≪0.001** |
| iono_agent | 67.30% | 63.70% | -1.69 | not significant (p≈0.09) |

**RESULT**: going first is better for Dragapult ex against every opponent tested,
most dramatically and with the clearest statistical confidence against Abomasnow
(a 10.8-point gap, z=-4.97). This directly **contradicts the official notebook's
own strategic assumption** that Dragapult should always decline to go first.

**RESULT** (average game length, same raw data): games run longer when Dragapult
is second in every matchup (random: 8.77 -> 9.83 turns; abomasnow: 10.24 -> 10.92;
iono: 12.05 -> 12.43), and the terminal-reason mix shifts: vs. Abomasnow, "win by
board wipe" (`win_reason=3`, opponent has no Pokemon left) drops from 628/1000
(first) to 490/1000 (second) while "win by taking all prizes"
(`win_reason=1`) rises from 367/1000 to 505/1000. Vs. random_agent, `win_reason=3`
also drops when second (948 -> 870). This is consistent with Dragapult, when
second, more often grinding out a prize-race win rather than sweeping the board —
weaker, not just slower.

## 3. Root-cause mechanics (verified against the C++ engine source, not guessed)

Two turn-1-only restrictions exist in the engine (`GameProc.h`), and both apply
**only to whoever goes first, only on the very first turn of the game**:

- **FACT** (`GameProc.h:915`): `if (state.turn >= 2 || ae.attack->canUseFirst ||
  card.canAttackFirst)` — attacking is disallowed on turn 1 unless the specific
  attack/card is flagged otherwise. Turn 1 is always the first player's opening
  turn (turn numbering is a single global counter, not per-player), so **only the
  first player loses their opening-turn attack option** — the second player's
  opening turn (game turn 2) has no such restriction.
- **FACT** (`GameProc.h:824`): `if (state.turn <= 1 && !master.canPlayFirstTurn)`
  gates Supporter cards the same way — first player can't play a Supporter on turn
  1 (unless flagged), second player faces no such restriction on turn 2.
- **FACT** (`GameProc.h:994`, `Draw(state, playerIndex, 1)` inside `TurnStart`,
  unconditional): **both players draw a card on their very first turn** — there is
  no "first player skips their first draw" rule in this engine (a common variant
  in some real-world formats). This matters because it means going first is not
  penalized by a missed draw here; the only first-turn cost is the attack/Supporter
  restriction above.
- **RESULT** (from `*_decisions.jsonl`, Dragapult's own MAIN-context choices on its
  first two actual turns, vs. Abomasnow): far more `ATTACK` actions logged in the
  `dragapult_second` condition (1591, across turns {2,4}) than in
  `dragapult_first` (632, across turns {1,3}) — directly reflecting the turn-1
  attack restriction landing on whichever side goes first.

**HYPOTHESIS** (not fully isolated from the raw decision counts above, offered as
the most likely explanation given all of the above): the second player's
turn-1-attack/Supporter freedom is a real but *smaller* advantage than it looks,
because Dragapult ex's own game plan is an evolution/energy-engine buildup
(Dreepy -> Drakloak -> Dragapult ex, ideally via Rare Candy) toward a single
high-value Phantom Dive sweep rather than an immediate-attack deck — being able to
attack a turn earlier is worth comparatively little to this deck, while losing a
full absolute turn of board development (since going second means your "turn 1" is
the game's turn 2, one full round behind) costs more. This is offered as an
explanation for *why* the measured effect exists, not as an independently verified
mechanism — it has not been isolated from other confounding factors (e.g. Rare
Candy/evolution timing specifically) and should be treated as a hypothesis for any
future, deeper investigation, not a settled fact.

## 4. Was this a bug?

**No.** Every part of the mechanism is either a faithful, verified-identical port
of the official notebook's own explicit design choice (§3 in
`results/abomasnow_deck_audit.md`'s sibling Phase-3 audit — see
`experiments/` — confirms `dragapult_agent.py` matches the notebook byte-for-byte
on this logic) or a genuine, source-confirmed engine rule. The "anomaly" is real
(Dragapult ex measurably performs worse when forced to go second, most clearly vs.
Abomasnow) but it is a **strategic weakness in the official notebook's own
IS_FIRST heuristic**, not a porting bug, not an engine bug, and not a tournament-
harness bug (though the harness's assumption that slot alternation implies
first/second alternation is corrected by this investigation — worth a code comment
update so it isn't relied on again for deterministic-preference agents).

## 5. Generalization check

The same deterministic-YES-vs-deterministic-NO mechanism also fully determines the
existing (unforced) session-1 Dragapult-vs-Lucario data (both engine-slot
arrangements land Dragapult as second, exactly as with Abomasnow/Iono, since
`lucario_ex_agent.py` also answers YES unconditionally). Ran the same forced
1000-games/condition experiment vs. `lucario_ex_agent` for completeness:

| Opponent | First win rate (n=1000) | Second win rate (n=1000) | z | Verdict |
|---|---|---|---|---|
| lucario_ex_agent | 46.60% | 47.90% | 0.58 | not significant |

**RESULT**: the first-player advantage does **not** generalize uniformly — vs.
Lucario ex it's a statistical wash (both conditions land near 47%, i.e. Dragapult
vs. Lucario is a close-to-even matchup regardless of who goes first). Combined with
§2's table, the effect is opponent-dependent: clearly positive vs. Abomasnow,
weakly positive (not significant alone) vs. Iono's and random, neutral vs. Lucario.
Phase 4's variant is still expected to help on average across this 4-opponent pool
(3 of 4 point the same direction, none point the other way), but this is not a
universal "always prefer first" law for Dragapult ex — it is specific to the
current opponent roster and would need re-checking against different decks.

## 6. Recommendation (feeds Phase 4)

Given a statistically significant, sizeable (10.8pp vs. Abomasnow) real
improvement from simply electing to go first, Phase 4 tests a minimal,
single-line modification (always answer YES to IS_FIRST, matching the other three
agents, with **no other change**) as a new candidate variant, benchmarked against
the same opponent pool and compared to the unmodified `dragapult_agent.py`
(preserved as `BEST_DRAGAPULT_AGENT` regardless of outcome, per the versioning
rule) before deciding whether to promote the variant. See
`experiments/dragapult_first_variant.md`.
