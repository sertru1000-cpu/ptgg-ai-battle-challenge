# Twenty-Seven Agents in Five Days: an Iteration-Economy Approach to PTCG AI

*Subtitle: How a late-entry team climbed to 691 by treating ladder submissions as scarce experiments — and measured exactly why offline evaluation cannot replace them.*

> DRAFT v1 — 2026-08-16. TODO before submit: final converged V25/V26 ratings (~08-31), figure exports, attach repo + notebooks.

---

## 1. Approach overview

We entered five days before the deadline, against teams iterating since June 16. That handicap dictated our core strategy: **treat every ladder submission as a controlled experiment**, maximize information per submission, and build agents whose components could be ablated independently. Over five days we built 27 agent versions in six architectural families; our peak rating was **691** (V20), achieved by combining a hand-tuned heuristic policy, bounded one-step search, and a learned state-value model trained on 341K positions from top-ladder replay data.

This writeup documents the design rationale (§3), the deck reasoning (§2), and — since we believe it is our most transferable contribution — quantified evidence on **when local evaluation of card-game agents can and cannot be trusted** (§4). All claims below are backed by ladder ratings (ground truth) or by experiments whose raw data is attached.

## 2. Deck strategy

**Concept.** Our deck is built around **Dragapult ex** as the primary attacker: a two-prize attacker whose *Phantom Dive* simultaneously pressures the Active Pokémon (200 damage) and places 6 damage counters on the bench, enabling multi-prize turns that break the symmetry of one-KO-per-turn exchanges. The deck's game plan is tempo-based: reach the *Phantom Dive* loop by turn 2–3, use bench snipe to set up double knockouts, and win the prize race even against decks with higher raw damage output.

**Key cards.** Supporting the plan: a draw engine dense enough to survive aggressive discarding (we tuned Supporter counts empirically against dead-hand rates measured over thousands of simulated games); recovery cards to sustain the attacker line against KOs; and a small tech package for the mirror and for common bench-sitter threats. Energy acceleration is deliberately minimal — *Phantom Dive*'s cost is low, and our simulations showed acceleration cards were dead draws in >60% of games.

**Ecology-driven validation.** Mid-competition we ran a forensic diff of top-ladder decklists (from organizer-published replay episodes) and found that **11 of the top teams converged on one shared decklist within ±12 cards** — a Dragapult variant with a "Munkidori package" adding damage-counter mobility. We built and tested that exact list (V19/V25/V26). The result is a genuine strategic finding: **deck strength is not intrinsic but pool-relative**. The leaders' list, piloted by our agents in the rating band where our agents actually played, performed *worse* than our original list (−60 to −100 rating points in ablations), because its tech choices answer threats that are common at 750+ but rare below 700. Deck and rating band co-evolve; copying a leader deck without the leader's rating is copying the answer to a different question. Our final pair therefore fields both lists — one finalist on each — as an intentional hedge across rating bands.

## 3. Model architecture and rationale

Our final architecture (V20, rating 691) is a three-layer hybrid:

**Layer 1 — heuristic policy core (V1–V6, rating 683.7).** A hand-written evaluator scoring board tempo: prize-race differential, energy-attachment efficiency, bench development, and attack-reach. We invested in this first because a strong greedy baseline (a) earns rating immediately, (b) provides a *prior* that bounds later search layers, and (c) is itself an ablation control. Notably, this 700-line heuristic finished within 8 points of our best learned agent — a data point on the cost-effectiveness frontier that we believe many teams skipped past.

**Layer 2 — bounded search.** We tested three search depths: greedy (V6), one-step lookahead with margin gating (V20), and full C++ MCTS / multi-ply tree search (V17, V24–V27; ~200K simulated turns/sec after a NumPy→C++ port with 1.5e-07 numerical parity). The counterintuitive result: **deeper search is not monotonically better — its value depends on evaluation-function quality in the positions the search visits** (§4.2). Our best agent uses the *shallowest* search that still exploits the learned evaluator, with the heuristic core as anchor: search may only override the greedy choice when the learned value margin exceeds a threshold. This margin gate is our main defense on the rubric's "consistency under repeated matches" axis: it caps the damage of any single evaluation error, making performance stable across seeds and matchups rather than optimized for best-case lines.

**Layer 3 — learned state-value model (the B1 line).** An XGBoost P(win) model over an 87-feature state vector (prize/tempo/energy/bench/hand features), trained on positions extracted from organizer-published replays of top-ladder games, labeled by final game outcome. B1v1: AUC 0.833 on held-out top-tier games; integrated into V20 it added **+21 rating over the identical agent without it** — our single largest verified improvement. The model is compiled to C++ tables (115–161 trees, parity ≤1.5e-07) so search can call it ~10⁵ times per turn.

**Training-data strategy matters more than model capacity.** Two controlled comparisons:

| Eval model | Training data | Ladder result (same agent shell) |
|---|---|---|
| B1v1 | top-ladder (leader) games only | **691** (V20) |
| B1v2 | our agents' self-play | 595 (V23) — **−96** |
| B1v4 | stratified: weak+mid+strong ladder tiers | see table below |

Self-play data was catastrophic: the model learns the biases of the very policy it will later guide (circularity), scoring its own line of play as safe. Stratified real-pool data, our final recipe, beats leaders-only data **on every opponent tier**:

| Validation tier | B1v4 (stratified) AUC | B1v1 (leaders-only) AUC |
|---|---|---|
| weak | **0.740** | 0.714 |
| mid | **0.725** | 0.717 |
| strong | **0.793** | 0.781 |
| all (52,961 states) | **0.751** | 0.736 |

The same table yields a clean measurement of distribution shift: B1v1 scores 0.833 on its home distribution but 0.736 on the neutral pool — a 10-point AUC drop from evaluation ecology alone. This directly addresses the rubric's "over-reliance on specific matchups" criterion: an evaluator trained on one opponent ecology silently underperforms outside it, and only stratified training data revealed the gap.

## 4. What we measured about measurement

We consider this section our most original contribution. Three findings, each with ground-truth numbers:

**4.1 Local benchmarks against your own agent family do not predict ladder strength — at all.** After the submission deadline we ran a 192-game anchored round-robin: a new agent (V27) against eight of our own ladder-rated agents spanning 595–691. Correlation between local win rate and the anchor's known ladder rating: **+0.04**; a likelihood-ratio test against "local results carry no rating information" comes out at exactly zero. V27 beat our 691 champion 10:6 and *lost* to our 595 straggler 6:10. Family round-robins measure rock-paper-scissors dynamics of shared decks and shared evaluation blind spots — not generalized strength. The ladder ranks agents against a diverse 1,800-team ecology; no monoculture proxy for that existed in our toolkit, and we submitted three agents (V18, V23) whose local scores were mirages before we proved this quantitatively.

**4.2 Deep search amplifies the tails of evaluation error.** Ablation grid (all ratings from the live ladder, same pool): adding depth to a well-matched evaluator gained +71 (V24 vs V23); adding the *same* depth on top of an evaluator facing off-distribution opponents *lost* ~60 against its own greedy baseline (V25 vs V19). Mean AUC differences of 1–3 points concealed this entirely: search actively seeks out the positions where the evaluator is most wrong (the optimizer's curse), so an evaluator for deep search must be judged by its worst-case positions, not its average discrimination. Our margin-gated shallow search is the architectural consequence.

**4.3 Iteration count on the real environment was the binding constraint.** Our rating trajectory gained roughly +20–30 per genuine ladder-informed iteration, and every offline shortcut we tried to compress that loop (gauntlets vs. sample agents, behavior-cloned pilots, self-play validation) failed a later ground-truth check. We estimate reaching the 750+ band required 3–5 more iterations of the search→data→evaluator loop — about two more weeks — rather than any idea we lacked. Teams starting on June 16 had ~60 daily cycles; we had 5.

## 5. Conclusions

1. A tuned heuristic with bounded search reaches ~98% of a learned system's rating at ~5% of its engineering cost; learned evaluation earns its +21 only on top of that anchor.
2. Deck choice is pool-relative; validate any borrowed list at your own rating band before adopting it.
3. Train evaluators on opponent-stratified real data, never self-play alone, and judge them by tail behavior if any search sits above them.
4. Budget ladder submissions as experiments from day one — they are the only instrument that measures the quantity being scored, and we can now put a number on how little local substitutes measure it: r = 0.04.

*Attachments:*
- *Dataset `sergueimakarov/ptcg-ai-battle-strategy-artifacts` — full code (agent line V1–V27, C++ search core, training pipeline), B1v4 tier datasets (parquet), anchored round-robin raw games (192), figures. Private until deadline; auto-published after.*
- *Notebook `sergueimakarov/ptcg-b1v4-per-tier-auc-reproduction` — reproduces Table 2 (per-tier AUC) from the saved models, no retraining.*
- *Media gallery: Fig. 1 rating trajectory, Fig. 2 per-tier AUC dumbbell.*
