# Search V2 Audit — What Was Wrong With Search V1

Scope: Part A1 of Competitive V2. Inspects the existing Search V1 implementation
(`src/agents/search_lookahead.py`, unchanged by this audit), the official Search
notebook, the Search API, the current heuristic action pipeline, and the C++
engine source for exactly how linked/multi-select decisions chain together
during attack resolution. Tags per project convention: FACT / RESULT /
HYPOTHESIS / QUESTION.

## 1. What Search V1 actually did

**FACT** (read from `src/agents/search_lookahead.py`, unchanged): for a MAIN
decision offering 2+ `ATTACK` options, V1 called `search_begin` once (shared
determinization), then for each candidate attack index called exactly **one**
`search_step(root.searchId, [idx])` and evaluated whatever `Observation` came
back immediately, picking the highest-scoring candidate.

**FACT**: this evaluates the state after only the *first* select following the
attack choice — not necessarily a "resolved" board state. Whether that first
returned select is itself a fully-resolved terminal-of-this-decision state, or
an intermediate follow-up select still belonging to the same action, depends
entirely on the specific attack and what it triggers.

## 2. Why that's wrong for at least one real card in the current roster

**FACT** (read from `src/agents/dragapult_agent.py`, verified identical to
the official notebook in Competitive V1's Phase 3 audit): Dragapult ex's main
attack (Phantom Dive, attack ID 154) does damage to the active Pokemon AND
places up to 6 damage counters across the opponent's bench, intended to set up
multiple simultaneous knockouts. `main_option_proc()` computes which
bench Pokemon to target with a subset-sum search over 60 damage, storing the
plan in module-global `plan_a`/`plan_b`. A **separate, later** select in the
same turn (`SelectContext.DAMAGE_COUNTER`) reads `plan_b.counter` to decide
where to actually place each counter.

**FACT** (verified directly against the C++ source this session, not
guessed):
- `data/official/ptcg_engine/ptcgProgram 22/EffectInstant.h:116`:
  `state.setSelect(SelectType::Card, SelectContext::DamageCounter,
  state.effectPlayerIndex())` — the damage-counter placement select is
  addressed to `effectPlayerIndex()`, i.e. **the attacker** (me, if I'm the one
  who attacked). This is a decision that belongs to the same player as the
  attack that triggered it, not an automatic/engine-resolved side effect.
- `data/official/ptcg_engine/ptcgProgram 22/EffectProc.h:1029-1041` (`KOProc3`):
  when a Pokemon is knocked out, `SelectPrize(state, 1 - playerIndex, prize, 0)`
  is pushed — prize-taking is addressed to `1 - playerIndex`, i.e. **the
  player who scored the KO** (me, if my attack caused it). Confirmed via
  `SelectProc.h:408` (`SelectPrize`) which itself pushes `SelectContext::ToHand`
  for that same player (`SelectProc.h:394`, `SelectPrize2`).
- `data/official/ptcg_engine/ptcgProgram 22/EffectProc.h:1012-1019`
  (`ActiveCheckPush`): if a player's active area is empty after KOs are
  resolved, `SelectActivePokemon(state, i)` is pushed **for that player** (the
  one who lost their active) — `SelectProc.h:126-132` confirms this uses
  `SelectContext::ToActive` addressed to `selectPlayer` = the player whose
  active was KO'd. **This is the opponent's decision, not mine**, if my attack
  KO'd their active.

**RESULT (the actual chain for a Phantom-Dive-into-multi-KO turn)**:
```
MAIN (me): choose ATTACK (Phantom Dive)
    -> DAMAGE_COUNTER (me): place bench counters  [plan_b.counter read here]
        -> (KOs resolved automatically by the engine)
        -> TO_HAND (me): take prize card(s) for each KO I scored
            -> TO_ACTIVE (OPPONENT): if their active was also KO'd, they
               must promote a new active -- this is the first point in the
               chain that is NOT my decision.
```
Search V1's single `search_step(root, [attack_index])` call only ever
resolved the **first** link (the attack choice → whatever comes right after),
which for Phantom Dive is the `DAMAGE_COUNTER` select — evaluated using
`_evaluate()` on a board state where the bench damage counters *haven't been
placed yet by search itself* (that's still a pending select at that point) and
prizes haven't been taken. This is exactly the "artificial intermediate state"
the governing prompt warned about, and it is now source-confirmed, not just
inferred from the Competitive V1 win-rate regression.

## 3. The `plan_b`-staleness mechanism, now confirmed as the more direct bug

**FACT**: Search V1's wrapper (`make_search_augmented_agent`) still calls
`base_agent_fn(obs_dict)` once per decision — purely for a stats comparison —
which invokes the REAL `dragapult_agent.agent()` on the real observation. This
sets `plan_a`/`plan_b` as a side effect, reflecting the heuristic's *own*
planned attack (`plan_a.attack`), regardless of which attack search ultimately
picks.

**RESULT**: when the REAL game later reaches the REAL `DAMAGE_COUNTER` select
(a consequence of whichever attack was actually taken, which may be search's
override, not the heuristic's own pick), `dragapult_agent.agent()` is called
again on the real `obs_dict`. It does **not** recompute `plan_a`/`plan_b` at
that point (`main_option_proc()`, which computes them, only runs when
`context == SelectContext.MAIN`) — so it scores the damage-counter options
against a plan that may describe a different attack than the one that was
actually taken. This is a second, compounding source of incorrect behavior,
independent of the "incomplete-chain evaluation" issue in §2 — it corrupts the
*real* game's own damage-counter decision, not just search's hypothetical
evaluation of one.

## 4. What must change (Search V2 requirements, derived from the above)

1. **Search must resolve the full chain of decisions that still belong to
   *me*, not stop at the first select.** Per §2/§3, "belongs to me" is exactly
   captured by `resulting_observation.current.yourIndex == my_index` — the
   chain naturally and correctly terminates the instant it becomes the
   opponent's turn to decide something (confirmed as the right boundary: it's
   precisely where MY action's consequences end and a genuinely unknown
   opponent choice begins).
2. **The sub-decisions within that chain must be answered by the SAME real
   heuristic agent function**, called on the search's own (hypothetical)
   observations — not by an arbitrary/default choice — so that e.g. the real
   damage-counter placement heuristic (which knows about `plan_b`) is what
   actually gets exercised inside the search rollout too. This also sidesteps
   §3's real-game corruption risk in a specific way: if Search V2 evaluates a
   *complete* chain using the heuristic to drive every sub-decision, and then
   the REAL top-level action taken matches search's chosen candidate, the
   REAL game's subsequent `plan_a`/`plan_b` (set moments before, during the
   real MAIN call) will describe that same real chosen attack correctly. The
   staleness bug in §3 only bites when the ACTUAL attack taken differs from
   what `plan_a`/`plan_b` describes — which happens if and only if search
   overrides the heuristic's own top pick. This is unavoidable in an
   architecture where search can override the heuristic (the whole point),
   so V2 cannot fully eliminate it by chain-completion alone — see open
   item in §5.
3. **A safety cap on chain length** is needed regardless (defensive, per Part
   A4's "no crash" requirement) — nothing in the engine source rules out a
   pathological long same-player chain, and search must never be able to hang.
4. **Determinization stays a shared, single `search_begin` per real decision**
   (this part of V1 was already correct — Competitive V1's fix for the
   "re-randomize per candidate" noise issue is unaffected by this audit).

## 5. Open items / what this audit does NOT resolve

**QUESTION**: does completing the chain fully solve the `plan_b`-staleness
issue (§3), or does it only reduce its blast radius to "search-overridden
attacks specifically"? Per point 4.2 above, the latter — the real game's
`plan_a`/`plan_b` will still be stale for the fraction of decisions where
Search V2's final chosen action differs from the heuristic's own top pick.
Whether this remaining exposure is small enough to ignore, or needs a second
fix (e.g. re-deriving `plan_a`/`plan_b` from the actual chosen action before
returning it, or calling `main_option_proc`-equivalent logic again), is left
to Part A3's implementation and A9's decision-level analysis to determine
empirically.

**QUESTION**: are there OTHER linked chains beyond the Dragapult
Phantom-Dive example, for the other three agents (Abomasnow, Iono, Lucario)?
Addressed directly in Part A2 below — do not assume Dragapult's case
generalizes without checking.

## 7. Part A6-A10 — benchmark result, decision analysis, promotion decision

**[RESULT]** (full benchmark in `experiments/search_v2_ablation.md`, 7000
games): Search V2 (full-chain resolution, verified mechanically correct --
0 chain-cap hits, 0 search failures, sensible 2-9 step chain lengths) is
**significantly WORSE** than the heuristic baseline in 6 of 7 matchups
tested (z from -4.19 to -8.49, effect sizes -12pp to -27pp), the one
exception being the random-agent sanity check (which the prompt explicitly
says not to weight heavily). This is a clean, well-powered, unambiguous
result: **the chain-completion fix from Parts A1-A3 was a genuine
correctness improvement but did not recover competitive performance.**

**[HYPOTHESIS]**, most likely explanation: the evaluation function
(deliberately kept identical to V1, to isolate the chain-completion change)
is too crude relative to the heuristics' own hand-tuned, domain-specific
attack-choice logic (KO-immunity checks, prize-count-threshold reasoning,
multi-turn plan continuity) for exactly the decision class Search V2
targets. See `experiments/search_v2_ablation.md` for the full reasoning.

**[RESULT]** (Part A9, decision-level log, `search_side_is_a` records in
each condition's `*_decisions.jsonl`, using only information visible to the
acting player -- no hidden opponent state logged): search changed the
heuristic's own top choice on 55-92% of the multi-attack decisions it
engaged on, across matchups. A quick pass on one matchup (dragapult vs.
iono) found search-driven decision changes were *not* obviously concentrated
in eventually-lost games specifically (711 decision-change records occurred
in the 197 games Dragapult won, 694 in the 303 games it lost -- i.e. ~3.6
changed decisions/game in wins vs. ~2.3/game in losses) -- a nuance worth
flagging rather than the simpler "search sabotages the games it touches"
story. **[QUESTION]**: this per-decision analysis does not establish
*causally* whether individual search-driven changes were locally correct or
incorrect (that would require counterfactual replay of both choices from
the same state, not attempted this session) -- left as an open item for any
future revisit of search.

**[Part A10 — promotion decision]**: **Search V2 is NOT promoted.**
Per the promotion criteria (directionally consistent improvement + adequate
sample + practical runtime + no regressions), this result fails on the
first and most basic criterion -- the directionally consistent result is a
significant *regression*, not an improvement. `BEST_AGENT` remains
`dragapult_fix_v1` / `lucario_ex_agent` (statistically tied, per
Competitive V1); `src/agents/search_lookahead_v2.py` is preserved in the
repo as correct, working infrastructure and a documented negative result,
not as a recommended configuration.

**HYPOTHESIS**: the `_evaluate()` function itself (prize race + HP diff +
bench-count diff) may still be too coarse even once full-chain resolution is
implemented — e.g. it has no notion of hand quality, energy curve, or
multi-turn setup value. This audit does not attempt to fix the evaluation
function; Part A3's implementation keeps it as-is (changing one thing at a
time, per the project's core experiment-discipline rule) so that any measured
change in Part A7's ablation can be attributed specifically to the
chain-completion fix, not conflated with an evaluation-function change.

## 6. Part A2 — linked decision chains, verified per-deck (not inferred from
card names)

Checked every attack actually referenced by each of the 4 ported agents'
decklists directly against `CardImpl.h` (the C++ attack/effect definitions),
looking for any `effect*`/`postEffect*` call that itself sets up a further
player select (`SelectAttachTo`, `TrashEnergy`, `DamageCounter`, etc.) versus
effects that resolve automatically with no player choice.

| Deck | Attack (ID) | Linked select? | Verified detail |
|---|---|---|---|
| Dragapult ex | Phantom Dive (154) | **YES** | Places bench damage counters via a separate `SelectContext.DamageCounter` select, addressed to the attacker (`EffectInstant.h:116`, `state.effectPlayerIndex()`). Confirmed in §2/§3 above. |
| Mega Lucario ex | Aura Jab (982) | **YES** | `effectSelectAttachBasicEnergyTrash(3)` (`CreateCard.h:1447`) — select up to 3 Basic Fighting Energy from discard, then `effectAttachFromEach().targetBench()` — select which bench Pokemon each goes to. Both steps are `EffectType::SelectAttachTo` targeting `Me` (`CreateCard.h:1450`). This is Mega Lucario ex's lower-damage (130) attack — `lucario_ex_agent.py`'s own planning code already anticipates its value (`base_score += 60 * min(3, discard_counts[Basic_Fighting_Energy])`), meaning the heuristic already "knows" this attack is worth more than its base damage suggests, precisely because of this chain. |
| Mega Lucario ex | Mega Brave (983) | **NO** | Just a "can't reuse next turn" self-effect (`postEffectMe(CannotUseThisAttackNextTurn)`), fully automatic, no select. |
| Mega Abomasnow ex | Hammer-lanche (1046) | **NO** | `DeckToTrash(Me, 6)` (top-6 discard) + a damage-count adjustment are both automatic, no player choice in which cards get discarded. |
| Mega Abomasnow ex | Riptide (1042, Kyogre) | **NO** | Reveals + shuffles automatically, no select. |
| Mega Abomasnow ex | Swirling Waves (1043, Kyogre's 2nd attack) | **YES, but not currently in scope** | `postEffectTrashEnergyMe(2)` — discard 2 attached Energy, a player choice. Not referenced by name/ID anywhere in `abomasnow_agent.py`'s scoring (falls through to the generic `score=1000` ATTACK default) and, more importantly, Abomasnow was never the *search-augmented* side in the Phase 12/13 ablation (only Dragapult was) — so this chain did not contribute to the V1 regression, but should be accounted for before ever search-augmenting Abomasnow itself. |
| Iono's | Voltaic Chain (363), Thump-Thump Boom (364), Electric Ball (365), Tiny Charge (367), Thunderous Bolt (368), Quick Attack (369) | **NO** (all six) | All of Iono's own deck's attacks resolve automatically (coin flips, self-damage, an automatic `effect(Ko, Enemy)`, damage-scaling by board state) — none set up a further player select. Iono's Bellibolt ex's **ability** (Electric Streamer, skill 97, not an attack) does have a linked select (`effectSelectAttachBasicEnergyHand(1)` + `AttachSelectedCard`), but abilities are outside Search V1/V2's current scope (only `OptionType.ATTACK` choices are searched), so this doesn't affect the ablation either way — flagged for a future scope extension, not acted on this phase (§A5 explicitly limits initial scope). |

**RESULT**: this fully and independently explains why Competitive V1's search
ablation found a large, significant regression for **both** search-augmented
agents tested (Dragapult ex AND Mega Lucario ex) — both of their signature/
highest-value attacks have a real linked decision chain that Search V1's
single-`search_step` evaluation cut short. It also explains, by absence, why
this specific mechanism would NOT have caused a regression had Iono's or
(Hammer-lanche-only) Abomasnow ex been the search-augmented side instead —
useful context for interpreting Part A7's new ablation results relative to
V1's.

**Reusable decision-chain semantics for Search V2** (per Part A2's
instruction to "create a reusable description," used directly in Part A3's
implementation): a real, meaningful decision boundary in this engine is not
"one select" but "every consecutive select still addressed to the same
player who made the initiating choice." That boundary is exactly
`resulting_observation.current.yourIndex == my_index`, confirmed against three
independent engine mechanisms this session (`SelectContext.DamageCounter` via
`effectPlayerIndex()`, `SelectContext.ToHand` prize-taking via
`1 - koVictimPlayerIndex`, `SelectContext.SelectAttachTo` via explicit `Me`
targeting) — all three consistently route "my consequence" selects back to me
and only hand control to the opponent once something outside my own chosen
action requires *their* choice (e.g. `SelectContext.ToActive` after their own
Pokemon is KO'd). This generalizes beyond just attacks — the same rule applies
to any option type that can trigger a follow-up select for the acting player
(confirmed structurally true from the engine's `effectPlayerIndex()` /
explicit-`Me`-targeting pattern, not attack-specific).
