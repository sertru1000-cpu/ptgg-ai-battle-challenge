# Twenty-Seven Agents in Five Days: an Iteration-Economy Approach to PTCG AI

We entered five days before the deadline against teams iterating since June 16.
That handicap dictated the method: **treat every ladder submission as a
controlled experiment.** We built 27 agent versions in six families, peaking at
**691** (μ₀ = 600). Several versions were deliberately *worse* agents whose only
job was to isolate one variable.

| Agent | What changed | Ladder μ |
|---|---|---|
| V6 | hand-tuned heuristic core | 683.7 |
| V17 | native C++ MCTS, V6 evaluation | 679.9 |
| V18 | + opponent-archetype determinization, V6 evaluation | 506 |
| V19 | leader decklist on the V6 policy | 674.0 |
| **V20** | + learned P(win) evaluation, PUCT, determinization voting | **691** |
| V23 | V20 shell, evaluator retrained on self-play | 595 |
| V24 | true multi-level PUCT tree (~13 plies) | 666 |
| V25 / V26 | final pair: leader deck + stratified evaluator | 587.5 / 601.3 |

## Deck strategy

Our deck is built on **Dragapult ex**. *Phantom Dive* does two things at once:
200 damage to the Active Pokémon and 6 damage counters onto the Bench. That
second clause is the strategic core, because it breaks the prize race's basic
symmetry of one knockout per turn. A deck converting bench damage into a second
knockout takes prizes ~1.5× faster than an opponent trading evenly, which wins
the race even against higher raw damage.

The list is 16 Pokémon / 36 Trainer / 8 Energy: 4 Dreepy, 4 Drakloak, 3
Dragapult ex, 2 Budew, 1 each Fezandipiti ex / Latias ex / Meowth ex; a dense
search-and-draw package (4 Buddy-Buddy Poffin, 4 Ultra Ball, 4 Lillie's
Determination, 3 Poké Pad, 2 Rare Candy); 4 Crispin for energy, 4 Crushing
Hammer for disruption, 3 Boss's Orders to gust the target that completes a
double knockout, and 4+4 Basic {P}/{R} Energy. Acceleration is deliberately
minimal — the attack cost is low, and in simulation acceleration cards were dead
draws in most games. The deck's failure mode is not "not enough energy", it is
"no Dragapult ex in play by turn 3".

**We then audited the ecology.** Recovering the exact lists of top-100 teams from
published replays, we found **13 of 19 top-100 Dragapult teams (ranks 2–94,
ratings 1011–1217) run a pairwise identical list**, differing from ours by the
same 12 slots: they add Munkidori, {D} Energy, Jamming Tower, Judge, Dawn, a
Poké Pad; they cut Rare Candy, Brock's Scouting, Watchtower, Latias ex, Lucky
Helmet, a Crispin. The "Munkidori package" moves damage counters onto the target
that matters — on paper a strict upgrade to our engine.

**We built that exact list and it lost rating.** V19/V25/V26 field it; V19 rated
674 against V20's 691 on the same policy, and the deep-search versions finished
at 587.5 and 601.3. The diff explains it: leaders cut *consistency and recovery*
to add *precision and disruption*. Precision pays when both players execute
nearly perfectly — the 1000–1200 band leaders occupy. In our ~650–700 band,
games are decided by whether your own engine stalls.

**Deck strength is pool-relative.** Copying a leader's list without the leader's
policy quality is copying the answer to a different question. Our final pair
fielded both lists as a hedge, not a bet.

## Model architecture

A three-layer hybrid; each layer is only worth building because the one below it
is already strong.

**Layer 1 — heuristic core (V6, 683.7).** A hand-written evaluator over prize
differential, energy efficiency, bench development and attack reach, plus
explicit *Phantom Dive* counter placement — the deck's highest-leverage decision,
and the source of two engine-level bugs we found by reading the official C++
engine sources rather than inferring from behaviour. A strong greedy baseline
earns rating immediately, bounds every later search layer as a prior, and serves
as the control for every ablation. This ~700-line heuristic finished within 8
points of our best learned agent.

**Layer 2 — bounded, margin-gated search.** We shipped three depths: greedy (V6),
one-step lookahead with a margin gate (V20), and full C++ MCTS / ~13-ply PUCT
(V17, V24–V27). The search is a single-translation-unit C++ core compiled on
first import, ~200K simulated turns/second, numerical parity 1.5 × 10⁻⁷ to the
Python reference — comfortably inside the 10-minute per-game wall clock. Our best
agent uses the *shallowest* search that still exploits the learned evaluator, and
may override the greedy choice only when the learned value margin exceeds a
threshold. That gate is our defense on consistency: in the worst case the agent
degrades toward V6, a known-683.7 policy, not toward the evaluator's most
confident mistake.

**Layer 3 — learned state-value model.** XGBoost P(win) over an 87-feature state
vector, trained on positions from published replays of real ladder games, labeled
by final outcome, exported to static C++ arrays with bit-exact parity so the
shipped agent is dependency-free and search can call it ~10⁵ times per turn.
Trained on 341K top-ladder positions (AUC 0.833) it added **+21 rating over the
identical agent without it** — our largest verified gain.

**Training data mattered more than capacity.** Same shell, same search, only the
evaluator's data changed: top-ladder games → **691**; our own self-play (212K
games) → **595**, −96. Self-play is circular — the model learns the biases of the
policy it will then guide, scoring its own lines as safe.

## What we measured about measurement

**1. Local benchmarks did not rank our own agents — under two independent
designs.** A fixed archetype gauntlet against generic pilots gives Pearson
r = 0.25, Spearman ρ = 0.03 (n = 6) against real ladder ratings; excluding V18's
outlier collapse, r = −0.28. An anchored round-robin — 192 games of a new agent
against eight of our own agents with known ratings spanning 587–691 — gives
**r = −0.004**, zero to three decimals: it beat our 691 champion 10:6 and lost to
our 595 straggler 6:10. And the row needing no statistics: **the highest local
win rate we ever recorded (57/60, V25) belonged to our second-worst agent on the
ladder.** A family round-robin measures rock-paper-scissors among agents sharing
a deck and therefore blind spots; a fixed gauntlet measures play against our own
assumptions about the meta. More local games shrink the interval and leave the
bias exactly where it was.

**2. Search amplifies the tails of evaluation error.** Same architectural change,
opposite sign: adding the deep tree to a pool-matched evaluator gained **+71**
(V24 vs V23); adding the same depth on an evaluator facing an off-distribution
pool lost **−86.5** (V25 vs V19). Search maximizes over the evaluator's output,
so it steers into the positions where that evaluator is most wrong — the
optimizer's curse. **Mean AUC differences of 1–3 points concealed this
entirely.** An evaluator under a deep search must be judged on worst-case
positions, not average discrimination; our margin gate is the consequence of
having no offline metric that predicts the sign.

**3. The evaluator's training ecology is a silent 10-point AUC tax.** Retrained on
data stratified across ladder strength tiers (215,622 positions, 1,632 episodes)
and scored on a neutral 52,961-position set, the stratified model beats the
leaders-only model on *every* tier (weak 0.740 vs 0.714, mid 0.725 vs 0.717,
strong 0.793 vs 0.781, all 0.751 vs 0.736). The instructive pair: the
leaders-only model scores **0.833 on its home distribution and 0.736 on the
neutral pool.** The model did not get worse — the yardstick did. This is the
measurable form of over-fitting to specific matchups, and nothing local flagged
it until we built the stratified validation set.

**4. Iterations, not ideas, were the binding constraint.** We gained ~+20–30 per
genuine ladder-informed iteration, and every offline shortcut we tried to
compress that loop failed a later ground-truth check. Reaching 750+ needed 3–5
more turns of the search → data → evaluator loop. Teams starting June 16 had ~60
daily cycles; we had 5.

## Robustness

Across all 57 episodes our final pair played, broken down by opponent archetype,
we hold an even or positive record against six of nine archetypes with no
matchup-specific code (Abomasnow 5–1, Alakazam/Fezandipiti 6–6, Dragapult mirror
2–1, other 9–5). We report the hole rather than averaging it away: **Mega Lucario
ex 2–8** — a fast single-prize aggressor that wins the race before our loop comes
online. The answer is a deck tech we cut for consistency, and per finding 1 we do
not believe our local benchmark could have told us whether it works.

Two honesty notes: our correlation results are n = 6 and n = 8 agents — they
support "this proxy is unusable for ranking", not a precise effect size. And
early ladder readings drift: our final pair read 610/613 on deadline day and
converged to 587.5/601.3 two weeks later, so every number here is a settled
reading, never a fresh one.

## Negative results, kept

The mechanisms transfer, so we report them:

- **Behavioural cloning of top players.** A policy imitating top-ladder players
  at 46% top-1 accuracy lost 0–6 even to our own baseline. Imitation accuracy is
  per-decision; games are sequential, so small errors compound into states the
  demonstrator never visited.
- **Minimax widening.** Broadening the search's action set amplified evaluation
  error instead of averaging it — finding 2, one layer up.
- **Two generations of local pilots.** Both generic-policy and imitation pilots
  ranked the ladder-*worst* agent first.
- **Determinization with an unmatched evaluator (V18).** Better hidden-information
  modeling and +6 in the local gauntlet produced a collapse to 506; swapping in
  the learned evaluator, everything else fixed, gave 691. We did not retain that
  submission's per-episode logs, so we present the rating as measured and the
  mechanism as our best explanation rather than a demonstrated one.

## Conclusions

1. A tuned heuristic with bounded search reaches ~98% of a learned system's
   rating at a fraction of the cost; the learned evaluator earned its +21 only
   on top of that anchor.
2. Deck strength is pool-relative. Thirteen top-100 teams converged on one list;
   that list made *our* agents worse, explicably. Validate a borrowed list at
   your own rating band.
3. Train evaluators on opponent-stratified real data, never self-play alone
   (−96), and judge them by tail behaviour whenever search sits above them —
   average AUC hid a 158-point swing between agents differing only in depth.
4. Budget ladder submissions as experiments from day one. They are the only
   instrument that measures the scored quantity, and we can now put a number on
   how little the usual substitutes measure it: **r = −0.00**.

*All claims are reproducible from the attached artifacts: the full agent line
V1–V27 with its C++ search core, the per-team leader decklist diffs, every game
of the 192-game anchored round-robin, all 57 final-pair episodes, the tier-
stratified training data, and the figure scripts. The official competition
engine is competition-use-only and is therefore not redistributed.*
