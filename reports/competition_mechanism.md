# Competition Mechanism Audit (Competitive V2, Part 0.7)

Source: official competition page content fetched via the Kaggle API's
`competition_list_pages('pokemon-tcg-ai-battle')` (Evaluation, Rules,
Timeline, FAQ, Data-description, "How to Submit" pages — full raw text, not
paraphrased from memory or general Kaggle knowledge), and
`competitions_list` metadata (deadlines, submission limits, team size,
reward, team count). All facts below are quoted or directly paraphrased from
that official text; anything not stated there is marked [QUESTION], not
guessed.

## 1. Matchmaking / rating mechanism

**[FACT]**, quoted from the official "Evaluation" page: *"Each Submission
has an estimated Skill Rating which is modeled by a Gaussian N(μ,σ²) where μ
is the estimated skill and σ represents the uncertainty of that estimate
which will decrease over time."* This is a Bayesian skill-rating system
(structurally the same family as TrueSkill/Glicko), not a simple win-rate
leaderboard.

**[FACT]**: *"When you upload a Submission, we first play a Validation
Episode where that Submission plays against copies of itself to make sure it
works properly. If the Episode fails, the Submission is marked as Error...
Otherwise, we initialize the Submission with μ0=600 and it joins the pool of
All Submissions for ongoing evaluation."*

**[FACT]**: *"We repeatedly run Episodes from the pool of All Submissions,
and try to pick Submissions with similar ratings for fair matches. Newly
submitted agents will be given an increased rate in the number of episodes
run to give you faster feedback."* — matchmaking is rating-proximity-based
(you mostly play opponents near your current skill estimate), not random
pairing across the whole field.

**[FACT]**: *"After an Episode finishes, we'll update the Rating estimate
for all Submissions in that Episode. If one Submission won, we'll increase
its μ and decrease its opponent's μ -- if the result was a draw, then we'll
move the two μ values closer towards their mean. The updates will have
magnitude relative to the deviation from the expected result based on the
previous μ values, and also relative to each Submission's uncertainty σ. We
also reduce the σ terms relative to the amount of information gained by the
result. **The score by which your agent wins or loses an Episode does not
affect the skill rating updates.**"* — this is the single most important
mechanical fact for strategy: **margin of victory is irrelevant.** A
narrow win counts exactly the same as a dominant one. This has direct
implications for how much value a stronger/riskier line that increases win
probability at the cost of "how convincingly" you win is worth (answer:
full value — there is no bonus for style points), and conversely that a
close, ugly win is exactly as good as a blowout.

**[FACT]**: *"On the leaderboard only your best scoring agent will be shown,
but you can track the progress of all of your submissions on your
Submissions page."* / *"we only track the latest 2 submissions and use those
for final submissions"* — confirmed by `competitions_list` metadata too
(implicit in "up to 2 Final Submissions", see §2). Older submissions beyond
the most recent 2 stop being used for final ranking, though (per the
Evaluation page) *"Every agent submitted will continue to play episodes
until the end of the competition"* — i.e. stale/superseded submissions keep
accumulating games in the background pool (presumably still usable as
matchmaking opponents / rating-estimation data for others) even though they
won't be your Final Submission.

## 2. Submission mechanics

**[FACT]** (Rules §2.2, `competitions_list` metadata, cross-confirmed): max
**5 submissions/day**; up to **2 Final Submissions** selected for judging;
max team size **5**; entry/merger deadlines already passed for this
project's timeline (`newEntrantDeadline` 2026-08-09, `mergerDeadline`
2026-08-10 — both before this session's date). Submission format (per the
"How to Submit" page): a `.tar.gz` with `main.py` at the top level (not
nested) plus `deck.csv`, e.g. `tar -czvf submission.tar.gz *`; uploaded via
the "My Submissions" tab; every new submission's first game is always a
scheduled self-play validation match before it enters the real matchmaking
pool.

**[FACT]**: *"No Ingress or Egress: During the evaluation of an episode your
Submission may not pull in or use any information external to the
Submission and Environment and may not send any information out."* (Rules
§2.12) — a hard constraint ruling out any live external lookup (e.g. a
network call to a hosted model, or fetching updated meta stats at
inference time) during actual grading. Anything used by a submitted agent
must be bundled into the submission itself (code + any static data files).

**[FACT]**: *"There is no Private Leaderboard in Simulation competitions."*
(Rules §2.10) and *"Each Submission will be scored based on their
performance in an episode, and your performances in episodes will be
aggregated to determine your position on the Leaderboard."* — unlike typical
Kaggle prediction competitions, there is no held-out private test set; the
leaderboard **is** the live, ongoing rating estimate.

## 3. Evaluation period / timeline

**[FACT]** (Timeline page, exact quoted text): *"June 16, 2026 11:00 am UTC
- Start Date"* ... *"[Final Submission Deadline]"* ... *"August 17, 2026 to
(approx.) August 31, 2026 - We will continue to run games, or until the
leaderboard has reached convergence. At the conclusion of this period, the
leaderboard is final."* Cross-confirmed via `competitions_list` metadata:
`deadline: 2026-08-16T23:59:00.000Z`. So: submissions lock at the
2026-08-16 deadline, but **games keep being played against your locked
Final Submission(s) for roughly two more weeks** (into ~August 31) purely to
let the skill-rating estimate (σ) converge — the final score is not fixed
the instant you stop submitting.

**[FACT]**: reward for this (Simulation) track is **"Knowledge"** — no cash
prize (`competitions_list` metadata, `reward: 'Knowledge'`,
`awardsPoints: True`). The linked Strategy track
(`pokemon-tcg-ai-battle-challenge-strategy`) carries a **"240,000 USD"**
reward pool instead, per the same metadata call — confirming the two-track
structure already known from project memory, now with the exact reward
figures verified. Team counts differ enormously: **6,715 teams** entered in
Simulation vs. **341 teams** in Strategy — the Simulation ladder is a much
larger, more saturated field.

## 4. Opponent visibility / hidden information

**[FACT]** (from the Overview/Description page, quoted): *"Not knowing what
cards an opponent holds presents a core challenge for an AI Training
Agent."* — explicit, official confirmation that opponent hand/deck/prize
identity is intentionally hidden information, not an engine limitation to
work around; it's the stated core challenge of the competition. Consistent
with everything already verified from the API itself (`PlayerState.hand` is
`None` for the opponent, etc.).

**[FACT]**: opponent archetype/deck identity is not directly exposed by the
API at any point during a real match — the only signal available is what's
naturally observable through play (revealed cards via logs, board state,
timing). Whether that signal is strong enough to usefully infer archetype is
an open empirical question, addressed in `reports/competitive_v2.md` Part C.

## 5. Documented simulator-vs-official-rules differences

**[FACT]**, from the official pinned forum post (competition discussion
topic id 708586, "Slightly difference between simular and game rules",
fetched via `competition_list_topic_messages`, posted 2026-06-16 by the
organizers and treated by them as authoritative — quoted: *"In this
competition, please note that the simulator behavior will be treated as the
correct behavior."*): three documented deviations from official real-world
Pokemon TCG rules, all judged low-impact by the organizers themselves:
1. Some attacks that would be legal-to-declare-but-fail-to-resolve under
   official rules (e.g. an effect that would put a Basic Pokemon onto a
   full Bench, or draw from an empty deck, or interact with an opponent's
   empty hand) are instead simply **not offered as selectable options** in
   the simulator. Organizers: "we believe the end result is the same."
2. Mega Zygarde ex's "Nullifying Zero" resolves target/coin order
   automatically left-to-right instead of letting the attacker choose order
   (real-rules micro-decision removed) — judged to not matter since
   Knock Outs are processed simultaneously either way.
3. When both players' Pokemon are KO'd simultaneously, the simulator's
   prize-taking order differs from official rules (next-player takes prizes
   immediately rather than both players choosing first, then taking
   simultaneously) — judged not to matter because the competition rules
   already treat "both players take all their remaining prizes
   simultaneously" as a **draw**, regardless of the exact resolution order.

**[QUESTION — community-reported, NOT organizer-confirmed]**: the same
forum thread contains several *unconfirmed* community bug reports (not
addressed by an organizer reply in the fetched thread) — e.g. a claim that
Mega Lopunny ex's "Gale Thrust" bonus damage fails to trigger correctly when
promoted to Active via certain shuffle-self-into-deck abilities, and a claim
that Cinderace's ability should allow playing it from hand during the setup
turn but doesn't. These are flagged here as **unverified user reports**,
not incorporated as fact anywhere else in this project, and not relevant to
any of our 4 current decks' cards (Mega Lopunny ex and Cinderace are not in
our roster) — noted only because Part 0 asks for a complete, honest picture
of what's documented, including open community-reported issues.

## 6. Competitive implications (Part 0.8)

**Q1 — single universal agent, or population/matchmaking environment?**
**[FACT-grounded]**: it is explicitly a **rating-based matchmaking
population environment**, not a fixed train/test split — you are matched
preferentially against opponents near your own current skill estimate, and
your rating evolves continuously from real game outcomes against whichever
opponents you're paired with, not against a static benchmark. This means
"how good is my agent" is only meaningful relative to the pool of other
submitted agents' current skill distribution at the time you're playing —
not an absolute, fixed target.

**Q2 — does opponent/deck adaptation have potential value?** **[HYPOTHESIS]**:
plausibly yes, since matches happen repeatedly against a real, evolving
population rather than one-off — but the API gives no direct signal of
opponent identity across episodes (each episode's `PlayerState.hand` for the
opponent is hidden, and nothing in the observation ties a given episode to
"the same opponent I played before"), so adaptation could only happen
*within* a single episode (reading revealed board state as the game
progresses), not *across* episodes against a recurring specific opponent.
This meaningfully limits what "adaptation" can mean here compared to, say,
a rematch-based ladder where you'd recognize a repeat opponent.

**Q3 — can opponent archetype be inferred from observable game state?**
**[QUESTION]**, addressed empirically (not just discussed) in
`reports/competitive_v2.md` Part C — the honest starting point is that no
opponent-identity field exists in the API; any inference would have to come
from indirect signals (which Pokemon/cards appear on their board/discard
over the course of a game), which only becomes informative partway through
a match, too late to change deck-level strategy (deck is fixed at
submission time) but potentially useful for in-game tactical decisions.

**Q4 — can multiple submissions be strategically complementary?**
**[FACT-grounded]**: up to 2 Final Submissions are explicitly supported and
both keep playing/rating independently, and the leaderboard shows only your
best-scoring one — so there's no mechanical reward for the *pair* being
complementary (e.g. no "best of your two vs. a given opponent" scoring);
each submission is rated independently and only the higher-rated one
counts for leaderboard position. **[HYPOTHESIS]**: the practical value of a
2nd submission is therefore closest to **risk-hedging / A-B testing**
(submit two different candidates — e.g. `dragapult_fix_v1` and
`lucario_ex_agent`, currently statistically tied locally — and let the live
ladder's much larger sample resolve which one actually performs better),
not a coordinated dual-agent strategy.

**Q5 — is deck selection as important as action selection?**
**[HYPOTHESIS]**, informed by but not proven from the mechanism facts above:
since margin of victory doesn't matter (§1) and matchmaking is
rating-proximity-based against a large (6,715-team), presumably
deck-diverse population, a deck with a systematically better matchup
distribution against *whatever decks are actually common in that
population* could matter as much as or more than incremental
action-selection quality within a fixed deck — this is exactly why Part 0's
meta-data findings (`reports/competitive_v2.md` §6) matter: our local
4-deck pool cannot answer this because it doesn't reflect the real
population's deck distribution. Not proven here; a reason to treat deck
research as a live, evidence-backed direction rather than a settled
non-issue.
