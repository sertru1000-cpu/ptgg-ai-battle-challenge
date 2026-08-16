# Luca Episode Data Audit

**Date**: 2026-08-12. **Scope**: read-only forensic audit of Kaggle team **Luca**
(`pokemon-tcg-ai-battle`, currently **#1 on the public leaderboard, score 1232.4**) using
their own live-ladder replay data, compared against our own **V2 Balanced** agent's existing
local evaluation data. **No agent/deck/policy/submission changes were made.** V2 was not
modified. This report is the deliverable; per this project's standing process rule, it is a
checkpoint for review, not an automatic green light to implement anything below.

Every claim below is tagged **[FACT]** (directly measured from pulled data, reproducible),
**[HYPOTHESIS]** (a plausible but unconfirmed interpretation), or **[GAP]** (a real limitation
in what the data can support). Do not read HYPOTHESIS-tagged items as conclusions.

---

## 1. How Luca's data was found (methodology)

1. `KaggleApi.competition_leaderboard_view('pokemon-tcg-ai-battle')` returned Luca as rank 1,
   `teamId=16448747`, `score=1232.4`. **[FACT]**
2. `KaggleApi.competition_team_submissions(16448747)` — confirmed **public for any team, not
   just our own** — returned Luca's 2 submissions: the current live one
   (`id=55447414`, score 1232.4, submitted 2026-08-12T03:05Z) and a superseded one
   (`id=55396758`, score 634.8, submitted 2026-08-10T04:37Z). All analysis below targets
   **55447414 only** (the live, currently-scored submission). **[FACT]**
3. `KaggleApi.competition_list_episodes(55447414)` returned all 70 episodes this submission
   has played: 1 `EPISODE_TYPE_VALIDATION` (Kaggle's own pre-matchmaking self-play check, both
   slots = Luca's own submission — same pattern already confirmed for our own submission in
   session 16 — excluded from all stats) + **69 real `EPISODE_TYPE_PUBLIC` ladder games**.
   **[FACT]**
4. A 3-episode sample was pulled and inspected first (`data/luca_audit/sample_replays/`)
   before bulk-downloading, per this task's own instruction not to download blindly. Schema
   matched the already-known `kaggle_environments`/"cabt" replay format from sessions 4-17
   exactly (`info.TeamNames`, `steps[i][player]={action,observation,visualize,reward,status}`).
   Confirmed Luca's own agent stdout/stderr logs are **403 Forbidden** (we don't own that
   team) — symmetric with the already-known "opponent logs are 403" finding from session 16.
   All behavioral inference below therefore comes from the replay JSON alone (action +
   observation + spectator-only `visualize` for deck extraction), never from Luca's own code
   or logs. **[FACT]**
5. All 69 real-ladder replays were then downloaded (0 failures) plus the current
   `publicScore` for each of Luca's **43 unique opponents** via the same public
   `competition_team_submissions` endpoint (0 failures). **[FACT]**
6. Parsing reused, not reinvented, three pieces of already-validated project tooling:
   `src/meta_analysis/episode_parser.py` (deck extraction), `src/meta_analysis/
   archetype_signatures.py` (archetype tagging), and the categorization/missed-knockout logic
   from `tools/kaggle_replay_forensic.py` (session 17, already validated on 46 of our own
   ladder games incl. 3 real bugs caught and fixed there).

New tooling: `tools/pull_luca_data.py` (data pull), `tools/build_luca_audit_v1.py` (Luca-side
parse+analyze), `tools/build_v2_behavior_comparison_v1.py` (V2-side comparable metrics from
already-existing local data). Raw data: `data/luca_audit/` (gitignored, matches project
convention). Structured outputs: `results/luca_audit/{luca_games,luca_decisions,
luca_missed_knockouts,v2_games,v2_decisions,comparison_summary}.csv` +
`{luca,v2}_behavior_summary.json` — raw per-decision/per-game data preserved, never discarded
after aggregation, per this project's standing rule.

---

## 2. Headline numbers

| Metric | Luca (n=69, real ladder) | V2 Balanced (n=150, local vs V1) |
|---|---|---|
| Win rate (decisive) | **73.9%** (51W-18L), Wilson 95% CI [62.5%, 82.8%] | **57.3%** (86W-64L), CI [49.3%, 65.0%] |
| Win rate going first | 74.3% (n=35), CI [57.9%, 85.8%] | 49.3% (n=75), CI [38.3%, 60.4%] |
| Win rate going second | 73.5% (n=34), CI [56.9%, 85.4%] | 65.3% (n=75), CI [54.1%, 75.1%] |
| Avg game length (turns) | 10.8 (wins 10.9 / losses 10.4) | 11.9 (wins 11.9 / losses 11.9) |
| Retreat rate (per decision) | 1.0% | 1.5% |
| Turn-level attack rate (attacked when legally able) | 81.2% | 78.8% (approx., see §6 caveat) |
| Games hitting a 2+ prize deficit | 20.3% (14/69) | 37.3% (56/150) |
| Avg peak deficit faced, in wins | 0.27 prizes | 0.72 prizes |
| Avg peak deficit faced, in losses | 1.89 prizes | 2.39 prizes |
| Comeback rate when 2+ behind | 35.7% (5/14) | 21.4% (12/56) |
| Missed confirmed knockouts | **0 / 69 games** | not computable (see §6 gap) |
| Deck | Fixed, single 60-card Mega Lucario ex build, **identical across all 69 games** | Fixed Dragapult ex (unrelated archetype) |

**[FACT]** — Luca went 51-18 (73.9%) over its 69 real ladder games with the live submission,
and its own opponents (matchmaking pairs by rating proximity) currently sit at a
mean/median rating of 977/1003 — Luca's win rate against its 54 currently-≥900-rated opponents
specifically is 70.4% (38/54), i.e. close to its overall rate, not propped up by farming weak
new entrants. **[GAP]**: opponent ratings are their *current* score, not their rating at the
time they played Luca — this competition's rating-per-side data is structurally unresolvable
after the fact (a limitation this project already established independently across sessions
5-12 for the bulk historical dataset), so this is directional, not exact.

**[GAP]**: no per-game rating/score trajectory exists for either side — Kaggle exposes only
each submission's *current* aggregate score, never a per-episode delta (confirmed again this
session, matching session 16's finding). "Reward/score progression" below is therefore win/loss
sequence over time (`create_time`), not an Elo-style curve.

---

## 3. Deck-level finding (Layer A, not gameplay policy)

Luca's deck was extracted independently from all 69 games via the exact-decklist method
(first 60-card action / cross-checked against spectator `visualize.deck`) already validated
across the 3,499-episode historical dataset. **[FACT]**: Luca plays the **exact same 60-card
decklist in every single game** (identical deck hash `eb1222900df9baf0` across all 69) — no
deck-switching, no meta-adaptive deck selection detected.

**[FACT]**: That decklist is **50/60 cards identical** to this project's own local reference
`decks/lucario_ex.csv` (the deck backing our `lucario_ex_agent` sparring bot). The other 10
cards are a clean, coherent swap:

| Slot | Our local deck | Luca's deck | Effect (from card data) |
|---|---|---|---|
| Search x4 | Dusk Ball | **Ultra Ball** | Dusk Ball only looks at the bottom 7 cards; Ultra Ball searches the *entire* deck at the cost of discarding 2 cards — strictly more reliable. |
| Supporter x4 | Carmine | **Judge** | Carmine's hand-refresh is first-turn-only; Judge refreshes (and disrupts the opponent's hand) *every* turn it's played. |
| Stadium x2 | Gravity Mountain | **Wally's Compassion** | Gravity Mountain is a situational anti-Stage-2 stadium; Wally's Compassion heals damage from **and returns attached Energy to hand from** a Mega Evolution ex Pokémon — a direct preservation/recursion tool for exactly the kind of attacker this deck runs. |

**Important scoping note**: this is a comparison against our **sparring-bot reference deck**,
not our shipped competitive decklist — V2 Balanced itself plays **Dragapult ex**, an unrelated
archetype, not Lucario. This finding does not say "copy this deck into V2." It says: a
real, apparently strong, independently-built Mega Lucario ex list made exactly the kind of
upgrade (weak partial search → full search; single-use refresh → repeatable refresh;
generic stadium → attacker-specific preservation) that is worth auditing for on
`decks/dragapult_ex.csv` too, on its own terms.

---

## 4. Behavioral patterns distinguishing Luca (ranked)

1. **[HYPOTHESIS]** Near-zero first/second win-rate asymmetry (74.3% vs 73.5%, CIs almost
   fully overlapping) vs V2's 16pp gap (49.3% vs 65.3%, CIs partially overlapping). Confidence
   is limited by sample size on both sides, but the contrast is large and directionally clean.
2. **[FACT]** Tighter prize-race control: Luca falls into a 2+ prize deficit in only 20.3% of
   games vs V2's 37.3%, and when Luca wins, its average worst deficit is 0.27 prizes vs V2's
   0.72 — Luca's wins look more "in control" throughout, not comeback-driven.
3. **[FACT]** Shorter games on average (10.8 vs 11.9 turns) across wins and losses alike.
4. **[FACT, null result]** Attack aggression is essentially identical (81.2% vs 78.8% of turns
   with a legal attack end up attacking) — **not** a differentiator. V2.1 effort should not be
   spent trying to make the agent "more aggressive" on this axis.
5. **[FACT, null result]** Tactical knockout execution shows **0 confirmed missed lethals**
   across Luca's 69 games — identical to our own agent's 0/46 finding from session 17. Luca is
   not winning because it's tactically sharper at taking free knockouts; neither are we
   tactically behind on this specific, precisely-measurable axis.
6. **[FACT]** Zero deck-switching: Luca commits to one fixed decklist across its entire
   sampled history. Whatever produces the 1232 rating is Layer A (deck construction) and/or
   Layer B (in-game policy), not opponent-aware deck selection.
7. **[FACT]** Deck-level consistency/preservation upgrade vs our own reference build (§3) — a
   concrete, inspectable artifact, not an inference.
8. **[HYPOTHESIS]** Voluntary-retreat rate is in the same order of magnitude as our own agents
   (~1.0% vs ~1.5% of all decisions) — not obviously a large behavioral gap, though the
   "retreat when a retreat-eligible menu is actually shown" rate (18.7% for Luca) trends higher
   than V2's rough proxy (3.2%); flagged HYPOTHESIS because the two denominators are not
   strictly equivalent (see §6).
9. **[FACT, with caveat]** Solid record against currently-strong opponents specifically
   (70.4% vs currently-≥900-rated opponents, n=54) — not just farming weak new entrants,
   though "currently-rated" is not "rated at match time" (§2 gap).
10. **[FACT, small-n]** No single faced archetype is a hard counter at this sample size —
    weakest point estimates are Dragapult ex (63.6%, n=22, Wilson CI [43.0%, 80.3%]) and Teal
    Mask Ogerpon ex (62.5%, n=8) — both still majority wins. Best matchup, Fezandipiti ex
    (10/10, Wilson lower bound 72.2%), does **not** clear this project's own established
    credibility gate (n≥50, from Phase 4.2) — flagged, not treated as proven.

---

## 5. Evidence-backed hypotheses for V2.1

Ranked by (evidence strength × actionability). None of these have been implemented or tested
this phase — this is the evidence base for a future decision, per the standing "report is the
checkpoint" rule.

**H1 — Investigate V2's first-player weakness specifically. [MEDIUM confidence, HIGH
actionability]**
V2 wins only 49.3% going first vs 65.3% going second (16pp gap; CIs overlap, so this is not
statistically proven at n=150, but it echoes this project's own already-*validated*
first-player-advantage finding elsewhere (+8.62pp pooled, real-ladder-confirmed, session 14)
— meaning V2 going first should structurally help, yet doesn't in this data). Luca shows no
such asymmetry. Actionable: rerun V2 alone (not vs a single fixed V1 opponent) across more
games split by first/second, and ablate `dragapult_policy_v2plus.py`'s three weight hooks
(`prize_value_multiplier`, `defensive_retreat_enabled`, `preservation_bias`) individually to
find which one (if any) is suppressing first-player tempo.

**H2 — Audit `decks/dragapult_ex.csv`'s own consistency/preservation package against the
Ultra-Ball / Judge / Wally's-Compassion pattern found in Luca's build. [MEDIUM confidence on
the general lesson, deck-specific verification not yet done]**
Not "copy Luca's cards" (wrong archetype) — check whether Dragapult ex's list has comparably
strong full-deck search, repeatable (not one-shot) hand disruption/refresh, and any
attacker-specific preservation tool, or weaker analogues that could be upgraded the same way.

**H3 — Reduce how often V2 falls into a 2+ prize deficit. [MEDIUM confidence]**
37.3% of V2's games hit a 2+ deficit vs Luca's 20.3%, and V2's own wins carry a larger average
peak deficit (0.72 vs 0.27) — directionally, V2 cedes more early/mid-game tempo before
stabilizing. Actionable: inspect the turns immediately preceding a 2+ deficit in V2's own
decision log (`results/luca_audit/v2_decisions.csv`) for a common early-game pattern (e.g.
delayed first attack, under-prioritized bench setup).

**H4 — Shorter games as a secondary/derived metric, not a direct target. [LOW confidence]**
Luca's 1.1-turn-shorter average is plausibly *downstream* of H2 (faster consistency → faster
first attack), not an independent lever. Worth re-checking after any H2/H3 change, not
targeting directly.

**H5 — Do NOT prioritize aggression tuning or KO-sniping logic. [explicit null result]**
Both agents already attack ~80% of the time when legally able, and both show 0 confirmed
missed lethal knockouts. This is the one axis where the data actively argues against spending
V2.1 effort, not just "no evidence either way."

---

## 6. Limitations (read before acting on any hypothesis above)

- **Sample size**: n=69 real Luca games is genuine ladder data but modest — every split above
  (first/second, per-archetype win rates) should be treated as preliminary, per this project's
  standing rule never to call a small/first run statistically conclusive.
- **Different decks entirely**: Luca plays Mega Lucario ex; V2 plays Dragapult ex. Every
  raw-rate comparison in §2/§4 is confounded by deck identity as well as policy — none of it
  isolates "policy alone." Treat all cross-agent comparisons as directional signals about
  *where to look*, not causal claims about *why*.
- **Asymmetric opponent populations**: Luca's 69 games are against 43 distinct real-ladder
  opponents at a high rating band; V2's 150 games are all against one fixed opponent
  (V1_baseline) locally. This is the best already-existing V2 data, but it is not a real-ladder
  sample for V2.
- **Asymmetric data richness**: the Kaggle replay format carries full legal-option detail
  (attack IDs, damage), enabling exact missed-knockout detection for Luca; the local V2
  decision log (session 18) only stores an option *count*, not full option contents — so
  missed-knockout detection, and the "attack/retreat rate when available" denominators, are
  not perfectly apples-to-apples between the two sides (noted inline at each use above).
- **No opponent-agent code/logs, no rating-at-match-time, no per-game score trajectory** —
  all three are structural gaps in what Kaggle's API exposes (403 on opponent logs, no
  per-side historical rating, no per-episode score delta), not something a different query
  would have recovered.
- **Nothing here has been implemented.** V2 was not modified. Any of H1-H5 would need its own
  scoped experiment (per this project's checkpoint-and-wait process) before being adopted.
