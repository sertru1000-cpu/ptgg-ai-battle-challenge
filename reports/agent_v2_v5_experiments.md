# Prompt #5 — Four Experimental Agents (V2 Balanced / V3 Aggressive / V4 Defensive / V5 Adaptive)

Date: 2026-08-12. Session: same-day continuation of the PTCG project (sessions 1-17 in
`memory/project_ptcg_status.md`). Deck for every version: `decks/dragapult_ex.csv` (unchanged
from V1 — this prompt tests a gameplay-policy hypothesis, not a deck-selection hypothesis).

Claim tags follow this project's standing convention (`memory/feedback_ptcg_process.md`):
**[FACT]** = read directly from source/engine data, **[MEASURED]** = computed directly from data
produced this session, **[HYPOTHESIS]** = plausible but not confirmed, **[PRELIMINARY]** = a
measured result from a single, first, moderate-sample local run — explicitly not yet
statistically conclusive, per the project's "never call a small/first run conclusive" rule.

---

## 0. What was investigated before writing any code

Per Part 1's instruction, the current agent, its scoring logic, switching logic, memory,
opponent modeling, randomness, logging, and every prior report were read before changing
anything (see the session's own research trace: `src/agents/dragapult_agent.py`,
`dragapult_agent_always_first.py`, `final_candidate_agent.py`, `safety_wrapper.py`,
`timeout_shield.py`, `common.py`, `main.py`, `tools/tournament.py`,
`reports/final_agent_v1.md`, `reports/kaggle_ladder_50games.md`,
`reports/kaggle_replay_forensic_v1.md`, `results/dragapult_first_second_analysis.md`).

Two specific tactical hypotheses were investigated **against the real engine data** before being
accepted or rejected as hook candidates, and both were rejected — recorded here so a future
session doesn't re-derive the same dead ends:

1. **[FACT]** The MAIN-menu `ATTACK` option is scored as `score = o.attackId` in V1 — looks
   arbitrary. Checked which of the deck's Pokemon have >1 attack (`cg.api.all_card_data()` /
   `all_attack()`): only Dragapult ex (attacks 153 "Jet Headbutt" 70dmg / 154 "Phantom Dive"
   200dmg) and Dreepy (150 "Petty Grudge" 10dmg / 151 "Bite" 40dmg). In both cases the
   higher-attackId option is *also* the higher-damage option, so V1's raw-ID tie-break already
   picks correctly by coincidence. **Verified no-op for this deck — not built.**
2. **[FACT]** V1's bench-snipe KO planner (`main_option_proc`) assumes a flat `damage=200`
   regardless of the target's weakness/resistance. Read `SetProperty.h::CalcDamage` in the
   official C++ engine source directly: weakness is a real ×2 multiplier, resistance a real -30,
   both applied server-side. But Dragapult ex's own type is DRAGON (EnergyType 9), and a full
   scan of all 1056 Pokemon cards in the competition's card pool found **zero** cards with
   weakness or resistance to DRAGON. **Verified no-op for this deck — not built.**

The three hooks that *are* used below (Section 1) were chosen because they touch scoring paths
confirmed to actually fire for this deck, not because they sounded plausible in the abstract —
same standard applied to the two rejected ideas above.

---

## 1. Shared architecture (Part 4)

```
src/agents/policy_weights.py        <- PolicyWeights dataclass + 4 named profiles
src/agents/dragapult_policy_v2plus.py <- ONE shared, class-based, weight-parameterized engine
src/agents/dragapult_agent_v{2,3,4,5}.py <- thin: pick a weight profile, call make_agent()
src/agents/final_candidate_agent_v{2,3,4,5}.py <- safety_wrapper -> timeout_shield -> policy
main_v{2,3,4,5}.py                  <- Kaggle entry points (mirror main.py exactly)
```

`dragapult_policy_v2plus.py` is a class-based port of V1's own `src/agents/dragapult_agent.py`
(**every scoring formula copied unchanged** except three explicit, bounded hook points — see
`policy_weights.py`'s module docstring for the exact justification of each). It had to become a
class (V1's version uses bare module-level globals) because this prompt's own evaluation plan
runs several *differently-weighted* instances against each other in one process
(`tools/tournament.py`) — with module-level state that would corrupt itself exactly the way
V1's own docstring already warns about for a same-module mirror match. Per-instance state fixes
this for real, not just hypothetically.

**Mechanically verified equivalence** (not just argued by code review):
`tools/verify_v2_engine_equivalence.py` plays real games with V1
(`dragapult_agent_always_first`) driving actual play, and at every one of V1's own decisions
also feeds the identical observation to a NEUTRAL-weighted clone of the new shared engine,
asserting the two return identical action lists. **0 divergences across 1,966 real decisions**
(1,225 vs `abomasnow_agent`, 741 vs `iono_agent`). This is the safety net that makes trusting the
shared engine's hook points reasonable — a plain code-review argument would not have been
sufficient on its own.

The three hooks (full grounding in `policy_weights.py`'s docstring):

| Hook | What it scales in V1's existing formula | Identity value |
|---|---|---|
| `prize_value_multiplier` | the `prize_count(...) * 1000` term in `pokemon_score()` (already the dominant term) | 1.0 |
| `defensive_retreat_enabled` / `_hp_fraction` | adds a 3rd retreat trigger (deny a likely-lethal/heavy hit when unable to attack), using real `cg.api.all_attack()` damage + attached-energy counts | disabled |
| `preservation_bias` / `switch_risk_tolerance` | reweights the existing `energy_count*1000 + hp` SWITCH-target formula and the existing Fezandipiti/Meowth switch-in penalties | 0.0 / 1.0 |

---

## 2. V2 — BALANCED

**V1 behavior**: retreats only to promote a charged bench attacker or protect Budew's setup
timing; never retreats to deny a free knockout on an already-spent/immobile active Pokemon.

**Why suboptimal**: the engine data shows retreat cost, attack damage, and attached-energy
counts are all directly computable from information already visible to the agent — a Pokemon
that can't act further this turn and faces a loaded lethal is pure downside to leave active if
retreating is affordable.

**V2 change**: `prize_value_multiplier=1.0` (unchanged), `defensive_retreat_enabled=True` at
`hp_fraction=1.0` (**only** a clean likely-lethal, the highest-confidence trigger — no partial-
damage speculation), `preservation_bias=0.1` (mild lean toward bulkier switch-ins),
`switch_risk_tolerance=1.0` (unchanged). Everything else is byte-identical to V1.

**Expected effect**: small, narrow positive edge, low downside (the added trigger only ever
fires in a state V1 already can't otherwise use — no legal attack this turn).

**Measured** (`results/agent/v2_v5_experiments/`, 150-game head-to-head + 120 games/opponent
vs. 3 sparring opponents, all with `final_candidate_agent_v2` = the actual full safety-wrapped
submission candidate):

- **Head-to-head vs V1: V2 wins 57.3% (86/150)**, Wilson 95% CI [49.3%, 65.0%], z=+1.80 vs 50%
  (p≈0.072 — **[PRELIMINARY]**, directionally the strongest result in this session but does not
  clear the conventional 0.05 bar at this sample size).
- vs `iono_agent`: 75.0% (90/120) vs. V1's own 60.0% (72/120) on the same opponent —
  **[MEASURED], statistically significant** (two-proportion z=+2.48).
  vs `abomasnow_agent`: 57.5% (69/120), not significantly different from V1's 59.2%.
  vs `lucario_ex_agent`: **38.3% (46/120), notably worse than V1's 50.8%** (z=-1.95, borderline —
  not quite significant alone, but the largest and most consistent regression seen anywhere in
  this session).
- **[HYPOTHESIS]**: Lucario ex's own play pattern may make the new defensive-retreat/
  preservation hooks actively counterproductive (e.g. paying tempo to protect a Pokemon that
  didn't need protecting against this specific opponent's damage output) — this specific
  opponent-dependent regression is the single most important open question from this session,
  not yet root-caused. Every other challenger (V3/V4/V5) shows the same directional dip vs.
  Lucario, which argues it's a shared-mechanism effect, not V2-specific noise.

---

## 3. V3 — AGGRESSIVE

**V1 behavior**: `pokemon_score()` weighs prize value, energy investment, tool count, and
evolution stage together with fixed relative weights; switching into a risky support Pokemon
(Fezandipiti ex, Meowth ex) always costs a fixed -1000/-2000 penalty regardless of how good the
rest of the trade looks.

**Why suboptimal (hypothesis)**: in a KO-race deck, secondary board-development factors may be
getting overweighted relative to straightforward prize value when the two conflict, and a fixed
switch-in penalty can't adapt to situations where the gamble is otherwise clearly worth it.

**V3 change**: `prize_value_multiplier=1.35` (chase prize value harder in the bench-snipe
planner), `defensive_retreat_enabled=False` (never trade tempo for protection — "less
conservative switching," "greater willingness to accept damage"), `preservation_bias=-0.15`
(lean toward attack-ready replacements over bulk), `switch_risk_tolerance=1.3` (smaller support-
Pokemon switch-in penalty). Still fully EV-scored — no random/suicidal branch was added.

**Expected effect**: stronger performance against passive/slow opponents (more raw pressure),
possibly worse against opponents who can punish overcommitment.

**Measured**:
- Head-to-head vs V1: **statistical wash**, V3 wins 49.3% (74/150), z=+0.16 (V1's own win rate
  50.7%) — no head-to-head edge detected at this sample size.
- vs `abomasnow_agent`: **65.0% (78/120)**, largest raw point-estimate gain of any version
  against this opponent (V1: 59.2%), though the version-vs-V1-same-opponent test itself is not
  significant (z=+0.93).
- vs `iono_agent`: 71.7% (86/120) vs. V1's 60.0% (z=+1.91, close to but not past the 0.05 bar).
- vs `lucario_ex_agent`: 45.8% (55/120), directionally worse than V1 (50.8%), same pattern as
  every other challenger.
- **[HYPOTHESIS]**: V3 shows the strongest *pooled* win rate across the three sparring opponents
  (60.8% vs V1's 56.7%) but this doesn't translate into a head-to-head edge over V1 directly —
  plausible explanation is that V1 itself already plays close to optimally against V3's own
  aggressive tendencies specifically (V1's hand-tuned scoring already anticipates most
  straightforward pressure), while V3's gains show up more clearly against the less-tuned
  sparring opponents. Not confirmed, flagged for a larger V1-vs-V3 run if pursued further.

---

## 4. V4 — DEFENSIVE

**V1 behavior**: same as Section 2's V1 description — no proactive protection of a valuable,
already-spent active Pokemon.

**Why suboptimal (hypothesis)**: V1 only ever protects a Pokemon reactively/incidentally (via
the bench-attacker-promotion path), never proactively when a *substantial* (not necessarily
lethal) hit is likely.

**V4 change**: `prize_value_multiplier=0.75` (de-emphasize raw prize-chasing relative to
positional/board factors), `defensive_retreat_enabled=True` at **`hp_fraction=0.6`** (retreat
proactively — a likely hit for ≥60% of current HP is enough, not only a guaranteed lethal),
`preservation_bias=0.3` (strong lean toward bulky switch-ins), `switch_risk_tolerance=0.6`
(bigger penalty for risky support-Pokemon switch-ins — more careful switching).

**Expected effect**: fewer Pokemon lost for free, at some cost in raw pressure/tempo.

**Measured**:
- Head-to-head vs V1: **statistical wash**, V4 wins 49.3% (74/150), z=+0.16 — identical point
  estimate to V3, no detected edge either direction.
- vs `abomasnow_agent`: 58.3% (70/120), essentially tied with V1 (59.2%).
- vs `iono_agent`: 65.8% (79/120) vs. V1's 60.0%, positive but not significant (z=+0.94).
- vs `lucario_ex_agent`: 46.7% (56/120), the same directional dip seen in every challenger.
- Switching frequency (`results/agent/v2_v5_experiments/switching_stats.csv`) was **not**
  dramatically higher than V1's despite the more permissive `hp_fraction=0.6` trigger (1.58% of
  V4's decisions were RETREAT vs. V1's 1.53%) — **[MEASURED]**: the proactive-retreat trigger is
  real but fires rarely in practice against this opponent pool, so most of V4's behavioral
  difference from V1 comes from the `prize_value_multiplier`/`preservation_bias` hooks reshaping
  *other* decisions (attach targets, switch-in choice), not from retreating more often per se.

---

## 5. V5 — ADAPTIVE

**V1 behavior**: fixed scoring weights for the entire match — no in-battle read of the specific
opponent's tendencies.

**Hypothesis**: useful signal about how aggressively a specific opponent is playing is available
from `obs.logs` every single call (attack/retreat counts, TURN_END markers — all legitimately
visible information, never hidden opponent data), and reacting to it in-battle should let the
agent lean appropriately aggressive/defensive per opponent rather than using one fixed profile
for everyone.

**Mechanism** (`DragapultPolicy._observe_opponent` / `_compute_adaptive_weights` in
`dragapult_policy_v2plus.py`) — deliberately NOT a machine-learning model, per Part 3's explicit
instruction:

1. Each call, count the opponent's `ATTACK`/`SWITCH`/`TURN_END` log events (cumulative this
   match) to derive `aggression = opp_attacks / opp_turns_observed`.
2. **Confidence gate**: below 3 observed opponent turns, weights stay at the neutral **BALANCED**
   profile — "avoid assuming a pattern is certain after one observation" is a hard floor, not a
   suggestion.
3. Once confident, linearly interpolate between the AGGRESSIVE and DEFENSIVE profiles based on
   `aggression` (a pressuring opponent nudges *our* stance toward DEFENSIVE; a passive opponent
   nudges toward AGGRESSIVE) — continuous, not a binary switch, per "explicitly account for
   uncertainty."
4. A second, more specific "recognizable situation → response" tracker (the prompt's own
   example) watches whether the opponent's active Pokemon, once it drops ≤30% HP, gets
   voluntarily retreated (via serial-number tracking across calls, resolved against
   bench/discard placement) vs. left in — if the opponent reliably protects wounded Pokemon
   (≥2 observations, ≥66% retreat rate), V5 nudges its own `switch_risk_tolerance` down slightly
   (play a bit more carefully itself too).

**Measured**:
- Head-to-head vs V1: **V5 wins 53.3% (80/150)**, z=-0.82 (not significant, but the
  second-largest point estimate this session after V2).
- vs `abomasnow_agent`: 65.8% (79/120) vs. V1's 59.2%, z=+1.07 (not significant alone).
- vs `iono_agent`: 69.2% (83/120) vs. V1's 60.0%, z=+1.48 (not significant alone).
- vs `lucario_ex_agent`: **50.8% (61/120), exactly tied with V1's own 50.8%** — the *only*
  version that does not show the directional regression against Lucario seen in V2/V3/V4.
- **[HYPOTHESIS]**: this is consistent with the adaptive mechanism doing something real — rather
  than applying V2's fixed defensive-retreat/preservation lean unconditionally (which appears to
  cost value specifically against Lucario ex), V5 only leans that way when its own in-battle read
  supports it, and apparently reads Lucario ex as not warranting it. Plausible but not isolated
  from confounds (e.g. simple variance) at this sample size — the cleanest, most valuable
  possible follow-up experiment from this whole session is a larger, dedicated V5-vs-Lucario run
  to check whether this holds up.

---

## 6. Run instructions

```bash
# Any single version, standalone (identical structure to running V1 via main.py)
python -c "import main_v2; print(main_v2.agent({'select': None})[:5])"

# Local tournament, any pair, any game count (tools/tournament.py, unchanged)
python tools/tournament.py --agent-a src.agents.final_candidate_agent_v2 \
    --agent-b src.agents.final_candidate_agent --games 100 --out-dir results/smoke

# Full comparison battery reproduced exactly (this session's own run):
python tools/build_v2_v5_experiments.py --games-vs-opponent 120 --games-head-to-head 150
# Recompute only the switching/decision-stats summary from already-played games:
python tools/build_v2_v5_experiments.py --skip-run

# Mechanically re-verify the shared engine == V1 at NEUTRAL weights:
python tools/verify_v2_engine_equivalence.py --games 15
```

## 7. Submit instructions

**Nothing was submitted to Kaggle this session.** V1's own archive
(`submission/final_submission.tar.gz`, currently the live Champion, Kaggle submission id
`55437549`, rating 726.9 as of session 16) is untouched. To package any challenger locally
(never touches V1's staging dir or archive):

```bash
python tools/build_submission_challenger.py --version v2   # -> submission/challenger_v2_<ts>.tar.gz
python tools/build_submission_challenger.py --version v3
python tools/build_submission_challenger.py --version v4
python tools/build_submission_challenger.py --version v5
```

Each run validates (same checks as V1's own `tools/build_submission_v1.py`): the version's
`main_vN.py` imports cleanly and returns a legal 60-card deck, `deck.csv` passes real
`battle_start` legality, the staged copy runs fully standalone (no dependency on this dev
machine's paths), and the archive has `main.py` at its top level. Actually uploading a built
archive to Kaggle (`kaggle competitions submit ...` or the website) is left as an explicit,
separate action for the user — track results in `results/agent/submission_registry.csv`
(Part 7's registry, pre-filled with V1's real Kaggle history; empty rows ready for V2-V5).

## 8. Recommended order for the first 5 submissions

Given the daily cap is 5 and V1 already occupies the Champion slot (no need to "re-submit" it —
it's already live), and per Part 9's "do not assume the latest version is best":

1. **V2 (BALANCED)** — the single largest, if still preliminary (p≈0.07), head-to-head edge over
   V1 (57.3%, n=150) and the narrowest, lowest-downside change (one high-confidence-only safety
   net + a small lean). Best "first challenger" per Part 8's own philosophy: minimum risk,
   real signal.
2. **V5 (ADAPTIVE)** — second-largest head-to-head edge (53.3%) and the only version that didn't
   regress against the one sparring opponent (Lucario ex) where every other challenger dipped;
   most novel mechanism, most valuable to get a real Kaggle read on early given the deadline.
3. **V3 (AGGRESSIVE)** — no head-to-head edge over V1 detected locally, but the strongest raw
   gains against the two more-tunable sparring opponents; worth a real-ladder read since the real
   Kaggle meta (per `reports/real_meta_v2.md`) is dominated by different archetypes than any of
   this project's 4 local sparring decks, and V3's profile (more prize-value-driven, less
   passive) could interact differently there than locally.
4. **V4 (DEFENSIVE)** — no head-to-head edge, smallest differentiation from V1 of the four
   (switching frequency barely moved) — lowest-priority slot, submit if slots 1-3 don't clearly
   resolve the picture.
5. Reserve, or re-submit whichever of V1/V2/V3/V4/V5 is currently strongest once slots 1-4 have
   real Kaggle data, per Part 8's Champion/Challenger process (never spend all 5 slots blind).

## 9. Which version is expected to be strongest, and why

**V2 (BALANCED)**, with real but bounded confidence. It has the largest local head-to-head
margin against V1, the only individually-*significant* single-matchup win in the whole session
(75.0% vs `iono_agent`, up from V1's 60.0%), and it is architecturally the smallest, most
narrowly-justified deviation from an already-thoroughly-vetted baseline (three prior forensic
sessions found zero confirmed tactical errors in V1 across 46 live Kaggle games — see
`reports/kaggle_replay_forensic_v1.md` — so a large behavioral departure would need unusually
strong evidence to be trusted over it, and V2 doesn't attempt one). Its one real weakness — a
directional regression against Lucario ex shared by V2/V3/V4 but *not* V5 — is worth watching
specifically on Kaggle, since the real ladder's actual opponent distribution
(`reports/real_meta_v2.md`) doesn't contain a Lucario-ex-like archetype anyway (this project's
local Lucario sparring partner has no confirmed real-ladder counterpart), so this weakness may
matter less in practice than it does in the local benchmark.

**Caveat, stated explicitly per Part 6's own instruction**: none of this is validated against
the real Kaggle meta. All five versions here were tested only against this project's own 4-deck
local sandbox (`abomasnow_agent`, `iono_agent`, `lucario_ex_agent`, and each other) — the
project's own much larger meta-analysis (`reports/real_meta_v2.md`) already found the real ladder
is dominated by entirely different archetypes (Marnie's Grimmsnarl ex at ~44% share, none of
which overlap this local pool except Dragapult ex itself). Local win-rate deltas are a real,
useful signal for catching outright regressions and confirming a mechanism does *something* non-
trivial, but they are not a reliable predictor of real-ladder rating movement, exactly as this
project's own V1 experience already showed (the local ablation predicted a comfortable margin;
the real 46-game ladder sample came back statistically indistinguishable from a coin flip).

## 10. Known risks and limitations

1. **All comparisons are [PRELIMINARY]** — a single 120-150-game local run per matchup, not
   independently replicated. The strongest single result (V2's 57.3% head-to-head win rate)
   does not clear the conventional p<0.05 bar (p≈0.072). Per this project's standing rule, this
   is reported as a real but not yet statistically conclusive signal, not a proof.
2. **Local sparring opponents are not the real Kaggle meta** (Section 9's caveat) — a version
   that wins locally could plausibly perform differently against the actual ladder's archetype
   distribution.
3. **The Lucario ex regression is unexplained.** Shared across V2/V3/V4, absent in V5 — a real,
   reproducible pattern worth investigating before trusting any of V2/V3/V4 broadly, not just a
   footnote.
4. **V5's opponent model is intentionally simple** and has known blind spots: it only tracks
   aggregate attack/retreat rates and one specific low-HP-retreat pattern; it cannot distinguish
   "opponent forced to attack because no other legal option existed" from "opponent chose to
   attack aggressively," and its per-instance state (like V1's own documented limitation) would
   corrupt itself if two V5 instances were ever run against each other in the same process
   (never an issue in a real Kaggle match, where the opponent is a separate process).
5. **Zero technical defects observed**: 0 aborted/crashed games, 0 invalid actions across all
   2,400+ games played this session (`results/agent/v2_v5_experiments/leaderboard.csv`,
   `aborted` column all-zero) — the shared engine's safety composition
   (`safety_wrapper`+`timeout_shield`, identical to V1's) held up under the same battery.
6. **V1/BASELINE was never modified.** Confirmed by construction: no `Edit` or `Write` call this
   session touched `src/agents/dragapult_agent.py`, `dragapult_agent_always_first.py`,
   `final_candidate_agent.py`, `common.py`, `safety_wrapper.py`, `timeout_shield.py`, `main.py`,
   or `decks/dragapult_ex.csv` — only `Read`. Additionally confirmed behaviorally: the
   equivalence tool (Section 1) proves the new shared engine reproduces V1's exact decisions at
   NEUTRAL weights across 1,966 real-game decisions.
7. **Nothing was submitted to Kaggle.** Per the prompt's explicit final rule.
