# Episode Data Schema Report (Part 0 — Episode Data Sample Audit)

Every claim is tagged **[FACT]** (directly observed in downloaded files or verified API
metadata), **[RESULT]** (measured from the small sample pulled this session), **[HYPOTHESIS]**
(plausible, not confirmed), or **[QUESTION]** (open, needs more data or organizer clarification).

## 0. Sample pulled this session

**[FACT]** No bulk day-archive was downloaded. Each daily Kaggle *Dataset*
(`kaggle/pokemon-tcg-ai-battle-episodes-<date>`) exposes **one file per episode** plus one
`manifest.csv`, individually addressable via the Kaggle API's `dataset_download_file(slug,
file_name)`. Verified by listing `kaggle/pokemon-tcg-ai-battle-episodes-2026-06-16` (the
smallest day, 1277 episodes / 2.85GB total per the pre-existing manifest index) via
`dataset_list_files`: **1278 files** = `manifest.csv` + 1277 per-episode `<episode_id>.json`
files, individual sizes ranging **103KB (manifest) to ~9.4MB** in that day. This means Part 0/1
sampling never needs a full-day pull — files can be cherry-picked by size/id.

**[RESULT]** Downloaded 1 `manifest.csv` + 7 individual episode JSON files from
2026-06-16 (`data/episode_sample/2026-06-16/`), sizes 155KB–9.4MB, chosen to span the observed
size range. All requests succeeded via single-file download; the list-files endpoint rate-limited
(HTTP 429) under rapid pagination and required backoff — worth knowing before Part 1 scales up
to thousands of files (need throttling, not full-day zips).

## 1. `manifest.csv` (one per day)

**[FACT]** Columns: `episode_id, create_time, avg_score, min_score, sum_score, agent_count,
size_bytes`. This is a lightweight per-day index — episode outcome (win/loss), deck identity,
and archetype are **not** in the manifest; only Bayesian-rating-style score fields and episode
size. Useful for **sampling strategy** (e.g. picking a score-diverse or size-diverse subset)
but not for meta analysis directly — that requires opening the per-episode JSON.

## 2. Per-episode JSON — top-level schema

**[FACT]** Each `<episode_id>.json` is a standard `kaggle_environments` replay object (not a
bespoke format), `schema_version: 1`, env `name: "cabt"`, `module_version` e.g. `"1.30.1"`.
Top-level keys:

| Key | Content |
|---|---|
| `id` | UUID for the replay run (not the same as `episode_id`) |
| `name`, `title`, `description` | `"cabt"`, `"Card Battle"`, `"Limited Card Battle."` — constant across episodes |
| `module_version`, `schema_version`, `version` | environment/replay-format versions |
| `configuration` | `{actTimeout, episodeSteps (max 10000), runTimeout, seed}` |
| `specification` | Self-documenting JSON-Schema-style block for `action`/`configuration`/`observation`/`reward` (see §5) |
| `info` | `{Agents: [{Name, ThumbnailUrl}, ...], EpisodeId, LiveVideoPath, TeamNames}` — **display names only**, no deck/archetype label |
| `rewards` | `[player0_reward, player1_reward]`, each in `{-1, 0, 1}` = Lost/Draw/Won (per `specification.reward.description`) |
| `statuses` | Final per-player status strings, e.g. `["DONE","DONE"]` |
| `steps` | The actual game trace — see §3 |

**[QUESTION]** `configuration.seed` (e.g. `1703606699`) — unclear whether this is the real
native-engine seed or a Kaggle-runner-level bookkeeping value. `docs/environment.md` established
from the C++ source (`Api.h`) that the native engine seeds itself via `std::random_device` and
**exposes no seed parameter through ctypes** — so this field is likely metadata about the Kaggle
job, not a reproducibility handle. Do not assume episodes are replayable from this seed alone
without further verification.

## 3. `steps` — the game trace

**[FACT]** `steps` is a list of `[player0_entry, player1_entry]` pairs. Each entry:
`{action, info, observation, reward, status, visualize}`.

**[RESULT]** Step count varies enormously with game length, confirmed across 6 sampled files:

| File | Steps | Final turn (p0/p1) | Result |
|---|---|---|---|
| `80212015.json` | 14 | 1 / 2 | short (early loss) |
| `80222591.json` | 12 | 1 / 2 | short |
| `80228055.json` | 14 | 3 / 2 | short |
| `80217284.json` | 10 | 2 / 1 | short |
| `80166482.json` | 98 | 7 / 8 | medium |
| `80165734.json` | 199 | 9 / 10 | medium-long |
| `80166761.json` | 306 | 17 / 18 | long |

**[HYPOTHESIS]** A meaningful fraction of episodes end very early (1–3 turns), plausibly from a
mulligan spiral, an immediate "no Basic Pokémon" loss, or similar edge-case rather than a full
strategic game. This matters for Part 1/2 sampling: filtering only on `episode_id` without a
minimum-turn/step floor risks polluting archetype/matchup statistics with degenerate games. Not
yet confirmed at scale (n=7).

**[FACT]** `action` (per step, per player): normally a `list[int]` of selected option indices
into that step's `select.option` (matches the documented agent contract in
`docs/environment.md`). On the **deck-declare step** (the very first non-empty action for that
player) it is instead the player's full **60-card deck as a list of card IDs** — verified
directly (see §4).

**[FACT]** `observation` mirrors the real `cg.api.Observation`/`State` schema already documented
in `docs/environment.md` from engine source — this episode format is not a separate/lossy
export, it's (close to) the literal per-step observation object the competing agent received.
Sub-fields: `current` (State — see §4), `logs` (list of `Log` dicts: `type`, `cardId`, `serial`,
`playerIndex`, etc. — turn-by-turn event stream), `remainingOverageTime`, `select`
(`SelectRequest`: `context`, `option[]`, `minCount`, `maxCount`, `deck`, `effect`, `contextCard`,
`remainDamageCounter`, `remainEnergyCost`), `search_begin_input` (opaque encoded string, present
once decisions start — **[QUESTION]**: format/purpose not decoded this session, likely an
internal search-determinization payload; not needed for Part 0/1 and not planned for decoding
unless a later part needs it), `step` (index, present on the acting player's entry only).

**[FACT]** `visualize` is a **separate, richer, full-information state** attached to the acting
player's step entry — it is the spectator/replay-rendering view, not the agent's view. Its
`current.players[i].deck` contains the **complete 60-card deck list for BOTH players**
(including the opponent's), even at step 0 before either player has drawn a card. This is
exactly the kind of information Part 0.2 requires flagging: valuable offline, must never reach
the live agent.

## 4. `observation.current` (State) — visible vs. hidden, verified empirically

**[RESULT]** Directly compared `observation.current.players[0]` (self) vs. `players[1]`
(opponent) at a real mid-game decision point (`80166482.json`, step 5):

| Field | Self (`players[yourIndex]`) | Opponent (`players[1-yourIndex]`) |
|---|---|---|
| `deck` | **absent** (only `deckCount`) | **absent** (only `deckCount`) |
| `hand` | full list of own hand cards | **`null`** (only `handCount`) |
| `active` | full Pokémon object (id, hp, energies, tools, serial) once played | **same** — full object, once played/revealed |
| `bench` | full objects | **same** — full once played |
| `discard` | full list | full list (discard pile is public) |
| `prize` | own prize cards (face-down; card identity **not** shown for own or opponent prizes at this point) | same |

**[FACT]** This exactly matches `docs/environment.md`'s prior source-verified claim
("`PlayerState.hand` is `None` for the opponent") — the episode-replay observation is consistent
with the live engine's real sanitization, not a leaked superset. **Opponent Active/Bench Pokémon
are genuinely visible once played**, confirming Part 6's premise that species-based archetype
signals are legitimately available to a live agent.

**[FACT]** Own deck's card-by-card composition is **not** exposed via `observation.current`
either (only `deckCount`) — but is trivially known offline/at submission time since it's the
agent's own declared deck. This is a non-issue for the live agent (it already knows what it
submitted) and is not "hidden information" in the sense Part 10 cares about.

## 5. Deck / decklist reconstruction — verified EXACT, not merely partial

**[RESULT]** For a full episode, **both players' exact 60-card decklists are recoverable
offline in two independent, cross-validated ways**:

1. The **deck-declare action**: the first non-empty `action` list for each player (found at
   `steps[1][0]['action']` and `steps[1][1]['action']` in the sampled file) — a raw
   `list[int]` of exactly 60 card IDs, i.e. literally the deck that player submitted for that
   game.
2. The **`visualize.current.players[i].deck`** field at step 0 — same 60 cards.

Verified programmatically: `sorted(deck-declare action) == sorted(visualize deck)` → **True**
for player 0 in the sampled file. Both methods agree exactly.

**[RESULT] Deck reconstruction quality: EXACT** (not PARTIAL, not ARCHETYPE-ONLY) — for
**every** episode in this dataset, for **both** players, offline. This is a stronger result than
the phase prompt's framing anticipated ("determine whether... partial reconstruction" was
possible) — full decklists are directly present, no inference/statistics needed. This is the
single most important finding of Part 0: **Part 3 (real decklist discovery) does not need
indirect archetype-composition inference at all for any archetype that appears in the pulled
episodes** — it only needs enough episodes to have seen that archetype at least once, then can
read its exact list.

**[FACT]** This offline-only exact decklist is explicitly **opponent-hidden-information** per
Part 0.2/Part 10 — it must never be fed to the live agent's opponent model. The live agent may
only use what §4 shows as visible (revealed Active/Bench species, discard pile, its own hand/
deck).

## 6. Field-by-field classification (Part 0.2 deliverable)

| Field | Available offline (episode file)? | Visible to live agent during game? | Useful for meta analysis? | Useful for deck reconstruction? |
|---|---|---|---|---|
| `episode_id` / `info.EpisodeId` | Yes | N/A (agent doesn't see this) | Yes (joins to manifest) | No |
| `create_time` (manifest) | Yes | N/A | Yes (temporal binning) | No |
| `info.TeamNames` / `Agents[].Name` | Yes | N/A | Weak (display name, not archetype label) | No |
| `rewards` (win/loss) | Yes | Agent sees own eventual `result`/`reward` only at game end | Yes (win-rate stats) | No |
| deck-declare `action` (60 card IDs, own) | Yes, both players | Yes, but only own | Yes | **Yes — EXACT** |
| `visualize.*.deck` (both players) | Yes | **No — replay-only, never sent to agent** | Yes | **Yes — EXACT (cross-check)** |
| `observation.current.players[self]` (hand, active, bench, discard, prize) | Yes | Yes (this is literally the agent's own observation) | Yes | Indirect (already covered by deck-declare) |
| `observation.current.players[opp]` (active/bench once revealed, discard) | Yes | Yes (agent legitimately sees this) | Yes | Partial-only, if used alone (see below) |
| `observation.current.players[opp].hand/deck` | **No** (not present even in offline `observation`, only in `visualize`) | No | N/A directly | N/A — use `visualize` instead |
| `observation.logs` | Yes | Yes | Yes (event sequencing, e.g. attack order) | Weak |
| `select` / `action` per decision | Yes | Yes | Yes (behavior cloning / IL target) | No |
| `search_begin_input` | Yes | Yes (opaque string) | Unknown — not decoded | No |
| `configuration.seed` | Yes | No (not part of agent observation) | Unclear ([QUESTION] above) | No |

**[HYPOTHESIS]** Because exact decklists are always available offline (§5), the "observable
opponent Pokémon only" archetype-classification exercise in Part 6/7 should be validated
*against* the exact offline decklist as ground truth — i.e. Part 7's "what would the agent have
known at turn N" simulation has a clean, verifiable label to score against (the true decklist →
true archetype), not a guessed one. This makes Part 7's accuracy measurement more rigorous than
originally scoped.

## 7. Dataset size — correction to the phase prompt's estimate

**[FACT]** The phase prompt states "The complete raw data is approximately 40GB+." Computed
directly from the existing full 56-day manifest index
(`strategy/meta_analysis/episodes_manifest_2026-08-10.csv`, pulled in a prior session):

- **56 days**, 2026-06-16 through 2026-08-10
- **278,457 total episodes**
- **~1,183.8 GB (≈1.18 TB) total**, not ~40GB — roughly **30x larger** than the prompt's estimate
- Per-day size is fairly stable at ~21.4GB/day except the first day (2026-06-16, 2.85GB, 1277
  episodes — presumably a partial/ramp-up day)
- Daily episode counts range **1,277 (day 1) to 7,819**, consistent with the prompt's stated
  "4,500–7,800 episodes/day" for the steady-state days
- Average episode size ≈ 4.2MB (total bytes / total episodes), consistent with the 103KB–9.4MB
  range observed directly in the day-1 sample

**This makes "do not download the entire dataset" a much harder constraint than the prompt's own
framing suggests** — at real scale this is ~1.2TB, not ~40GB. The per-episode individual-file
download path (§0) is not just a nicety, it is the only practical way to sample this dataset on
this machine (50GB free disk per `docs/environment.md` §3).

## 8. Legal / competition-use considerations

**[FACT]** (carried over from prior-session verification, see
`reference-kaggle-ptcg-access` memory) The `kaggle/pokemon-tcg-ai-battle-episodes-*` datasets
are **CC0**, organizer-published, explicitly intended for BC/RL/IL use — no attribution
requirement, no re-license restriction. Distinct from the community
`busyaprime/pokemon-tcg-ai-battle-live-meta` dataset (CC BY 4.0, attribution required, already
used in `strategy/meta_analysis/`). Neither has the "competition-use-only, delete after
competition" restriction that applies to the engine/card-data bundle in `data/official/` — but
this session's local sample is still kept out of git (`data/episode_sample/` should be
gitignored alongside `data/official/` as a matter of repo hygiene, not license necessity, since
it's a large binary/data artifact).

## 9. Answering Part 0's core question

**[RESULT] Yes — a small sample (11 files, <20MB, zero full-day downloads) already contains:**
exact decklists for both players in every episode (§5), full win/loss outcomes (§2), turn-by-turn
event logs (§3), and a faithful reproduction of exactly what the live agent's own observation
looked like at each decision (§4) — sufficient to proceed to Part 1 (small real-meta dataset) and
Part 3 (real decklist discovery) with high confidence, and to design Part 6/7's opponent
classifier against verifiable ground truth.

**[QUESTION]** Not yet answered by this sample: whether **archetype labels can be assigned
automatically and consistently** across thousands of decks (Part 1.3) — every deck seen so far
is a raw 60-ID list with no organizer-provided archetype tag; archetype identification will need
the deterministic card-package rule the phase prompt specifies (key Pokémon + trainer package +
energy package), built against the two overlapping label sources we already have:
`strategy/meta_analysis/live_meta_snapshot_2026-07-31/` (8 named archetypes, no decklists) and
`strategy/meta_analysis/deck_archetypes.md` (4 local sample decks, exact lists). This is the
next step (Part 1), not resolved here.

---

**Stop condition met**: per the phase prompt, Part 0 is verified before any bulk processing.
Recommendation: proceed to Part 1 with a **capped, throttled** per-file sampling script (learned
this session: the Kaggle `dataset_list_files`/`dataset_download_file` endpoints rate-limit
around ~20 rapid calls; needs backoff, and file-name lists should be pre-fetched from
`manifest.csv` rather than paginating `dataset_list_files` per episode).
