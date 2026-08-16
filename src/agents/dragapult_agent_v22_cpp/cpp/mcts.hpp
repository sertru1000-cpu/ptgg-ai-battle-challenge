// MCTS over the current real decision's legal options -- Selection
// (UCB1) / Expansion (one search_step per visit) / Simulation (native
// V6-greedy rollout) / Backpropagation (mean-value update per candidate),
// entirely inside C++ against the native engine (see ../README.md's
// call-chain diagram -- Python is not involved anywhere in this file).
//
// Scope, deliberately: the tree has exactly one branching level -- the K
// legal options at the CURRENT decision (mirrors dragapult_policy_v11.py's
// own gating: only `context == MAIN && maxCount == 1 && len(options) >= 2`
// gets this treatment; every other decision, including every decision
// *inside* a rollout, uses V6Scorer::choose() directly).
//
// 2026-08-14 stabilization pass (divergence investigation: whenever MCTS
// overrode V6's greedy pick it won only 8-12% of those games -- see
// MCTS:[END]/[EVOLVE]/[ABILITY] divergence buckets):
//   1. VALUE NORMALIZATION: every rollout value is squashed through
//      tanh(v / kValueSquashScale) into [-1, 1] BEFORE entering a
//      candidate's running mean. UCB1's exploration math assumes bounded
//      rewards; the previous clip-to-+-5000 left means on an arbitrary
//      unbounded heuristic scale where the exploration constant had to be
//      hand-rescaled 300x (the old kUcb1ExplorationScale) to matter at all,
//      and a single outlier sample could still swing an arm's mean past any
//      exploration correction.
//   2. RE-DETERMINIZATION: search_begin is re-issued with a FRESH randomized
//      guess of the opponent's hidden zones several times per search, and
//      candidate statistics are averaged across all determinizations.
//      Previously ONE search_begin filled the opponent's entire deck, hand,
//      and prizes with Basic Fire Energy -- every rollout then played
//      against an opponent who literally could not evolve, play a trainer,
//      or threaten anything, so lines like "end the turn, nothing bad
//      happens" scored beautifully in the tree and lost on the real board.
//      The guess pool is our own DECK constant minus the opponent's visible
//      board (mirror-match assumption -- the archetype this scorer is
//      specialized for anyway), which is far closer to reality than 60
//      energies and, critically, DIFFERENT each determinization, so a line
//      must be good across several sampled worlds to keep a high mean.
//   3. GREEDY-OVERRIDE MARGIN: MCTS's best-mean candidate replaces V6's own
//      greedy pick only when its mean beats the greedy pick's mean by a
//      clear margin on the squashed scale. At 8-12% observed override win
//      rates, an override needs real evidence, not sampling noise.
//   4. ROLLOUT TRUNCATION: rollouts stop at max_rollout_steps = 24 decisions
//      (~2 simulated turns) instead of 60, then score with state_value() --
//      horizon optimism compounds with rollout depth, and shorter rollouts
//      buy more samples per determinization inside the same budget.
#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <random>
#include <string>
#include <vector>

#include "card_data.hpp"
#include "cg_engine.hpp"
#include "deck_tracking.hpp"
#include "generic_opponent.hpp"
#include "observation.hpp"
#include "pwin_trees.hpp"
#include "v6_heuristic.hpp"
#include "v6_heuristic_scores.hpp"
#include "vectorizer.hpp"

namespace v17 {

// tanh squash scale (stabilization note #1): typical non-terminal
// state_value() magnitudes are a few hundred to a few thousand
// (pokemon_score/prize_term), so /2500 keeps ordinary positional
// differences on tanh's responsive slope, while a genuine terminal reward
// (+-1,000,000, from the unmodified state_value() port) saturates to
// exactly +-1 -- still decisive per-sample, but no longer able to swing a
// mean by orders of magnitude off a single rollout. state_value() itself
// stays an unmodified, faithful port (this project's standing rule: scope
// the fix at the consumer, don't edit shared formula code).
constexpr double kValueSquashScale = 2500.0;

struct McTsConfig {
  double time_budget_ms = 300.0;     // wall-clock budget for one v17_choose_action call
  double safety_buffer_ms = 100.0;   // reserved, never spent on simulation (Objective 2's "100ms safety buffer")
  int max_rollout_steps = 24;        // decisions per rollout (~2 simulated turns) -- stabilization note #4
  int num_determinizations = 6;      // fresh opponent-hidden-zone samples per search -- stabilization note #2
  double ucb1_c = 1.25;              // exploration constant (B2/PUCT: multiplies the prior term)
  double greedy_override_margin = 0.20;  // note #3: minimum mean advantage (squashed scale) required to override V6's greedy pick
                                          // (0.10 -> 0.20 after the 2026-08-14 120-game run: overrides averaged ~44% WR vs the
                                          // 47.5% baseline -- low-confidence overrides still net-negative, confident ones
                                          // (ATTACK-vs-PLAY 56.5%, ATTACK-vs-ABILITY 62.1%) worth keeping)
  // V20 / Block B additions:
  bool use_pwin_eval = true;   // B1: leaf/rollout value = learned P(win) mapped to [-1,1] (replaces tanh(state_value))
  bool use_puct = true;        // B2: PUCT selection with V6-greedy-score softmax priors (replaces plain UCB1)
  bool use_det_voting = true;  // B3: candidate chosen by per-determinization vote majority, mean as tie-break
  double puct_prior_temperature = 20000.0;  // softmax temperature over raw V6 scores (typical real-option scores span 1e4-1e5)
  // B4-lite (V22): soft minimax over the first `widen_steps` decision points
  // of each rollout -- branch the acting player's top-`widen_branch` policy
  // options, evaluate each branched state immediately with the B1 eval, and
  // continue the rollout from the branch best FOR THE ACTOR (max when the
  // root player acts, min-for-root when the opponent does). Depth exactly
  // where it matters most (the direct replies to the root candidate) at a
  // bounded cost (+~widen_steps engine steps per rollout).
  int widen_steps = 2;
  int widen_branch = 2;
};

struct ChildStat {
  int option_index = -1;
  int visits = 0;
  double total_value = 0.0;
  double mean() const { return visits > 0 ? total_value / static_cast<double>(visits) : 0.0; }
};

class Mcts {
 public:
  // `cards` backs the Block-A1.5 generic opponent rollout policy (see
  // generic_opponent.hpp) -- the same static table the V6 scorer already
  // uses, passed separately because V6Scorer keeps its copy private.
  Mcts(cg::Engine& engine, const CardTable& cards, const std::vector<int>& deck_const, McTsConfig config)
      : engine_(engine), deck_const_(deck_const), config_(config), generic_opp_(cards), cards_(cards) {}

  // Returns the chosen option index (into root_obs.options), or -1 if not
  // even one simulation completed -- caller must fall back to plain V6
  // greedy (V6Scorer::choose) in that case, exactly like
  // dragapult_policy_v11.py's `_macro_lookahead_choice` returning None.
  //
  // CONTRACT: candidate_indices[0] must be V6's own greedy pick (the caller
  // passes candidates sorted by raw greedy score, descending) -- it is the
  // baseline for the greedy-override margin (stabilization note #3).
  //
  // `out_visits`/`out_begin_ok` (both nullable) report search diagnostics
  // back to the caller (real rollout counts / whether ANY determinization's
  // search_begin succeeded). `out_hit_terminal_reward` (nullable): true if
  // any rollout's RAW value magnitude reached kTerminalRewardThreshold
  // (i.e. some simulated line genuinely concluded the game).
  static constexpr double kTerminalRewardThreshold = 500000.0;

  // `out_begin_fail_count`/`out_begin_last_error` (nullable): search_begin
  // failure diagnostics for the ~9-10%-of-eligible-decisions-never-search
  // investigation -- how many determinizations' search_begin calls failed
  // this decision, and the engine's raw error code from the most recent
  // failure (RawSearchResult::error; -1 = empty reply).
  // `candidate_raw_scores` (nullable; parallel to candidate_indices): V6's
  // raw greedy scores for the candidates -- B2/PUCT priors. When null,
  // uniform priors (plain-UCB1-equivalent exploration weighting).
  int search(const Observation& root_obs, const std::vector<int>& candidate_indices,
             const std::string& search_begin_input, const V6Scorer& live_scorer,
             int* out_visits = nullptr, bool* out_begin_ok = nullptr,
             bool* out_hit_terminal_reward = nullptr, int* out_begin_fail_count = nullptr,
             int* out_begin_last_error = nullptr,
             const std::vector<double>* candidate_raw_scores = nullptr) {
    if (out_visits) *out_visits = 0;
    if (out_begin_ok) *out_begin_ok = false;
    if (out_hit_terminal_reward) *out_hit_terminal_reward = false;
    if (out_begin_fail_count) *out_begin_fail_count = 0;
    if (out_begin_last_error) *out_begin_last_error = 0;
    bool hit_terminal = false;

    auto t_start = std::chrono::steady_clock::now();
    auto elapsed_ms = [&]() {
      return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t_start).count();
    };
    const double budget = std::max(0.0, config_.time_budget_ms - config_.safety_buffer_ms);
    if (candidate_indices.empty()) return -1;

    std::vector<int> my_deck = expand_deck(root_obs);
    // Defensive padding, same reasoning as expand_deck() below: SearchBegin's
    // native side (Export.cpp's CopyIdPtr) copies exactly
    // `state.players[myIndex].prize.size()` elements out of whatever pointer
    // we hand it, UNCONDITIONALLY -- a short buffer here is a guaranteed
    // null/short read (hit empirically against cg.game.battle_start()'s
    // local dev harness; see git history of this comment for the full
    // trace). Never hand the native engine a short buffer for a count it
    // will unconditionally read.
    std::vector<int> my_prize = root_obs.myPrizeGuess;
    while (static_cast<int>(my_prize.size()) < root_obs.myPrizeCount) my_prize.push_back(DETERMINIZATION_FILLER_CARD_ID);

    std::vector<ChildStat> children;
    children.reserve(candidate_indices.size());
    for (int idx : candidate_indices) children.push_back(ChildStat{idx, 0, 0.0});

    // B2: softmax priors over V6's raw greedy scores (uniform when absent).
    std::vector<double> priors(children.size(), 1.0 / static_cast<double>(children.size()));
    if (config_.use_puct && candidate_raw_scores && candidate_raw_scores->size() == children.size()) {
      double mx = -1e300;
      for (double s : *candidate_raw_scores) mx = std::max(mx, s);
      double denom = 0.0;
      for (size_t i = 0; i < children.size(); ++i) {
        priors[i] = std::exp(((*candidate_raw_scores)[i] - mx) / config_.puct_prior_temperature);
        denom += priors[i];
      }
      for (double& p : priors) p = std::max(0.02, p / denom);  // floor: no candidate starved outright
    }

    // B3: per-determinization vote tally (index into children).
    std::vector<int> det_votes(children.size(), 0);
    int det_completed = 0;

    int total_visits = 0;
    bool any_success = false;
    bool any_begin_ok = false;

    // RAII guard: one search_end() per successful search_begin(), on every
    // exit path (budget exhaustion mid-determinization, exceptions) -- the
    // same "search_end() always in a finally block" discipline
    // dragapult_policy_v11.py documents.
    struct EndGuard {
      cg::Engine& e;
      ~EndGuard() { e.search_end(); }
    };

    // V20/B1: when use_pwin_eval, simulate_one already returns a value in
    // [-1, 1] (2*P(win)-1 from the root player's perspective, or exactly
    // +-1/0 for a genuinely concluded game) -- recorded as-is. Legacy path
    // keeps the tanh squash of the raw heuristic value.
    std::vector<double> det_value(children.size(), 0.0);  // per-det sums, reset each det (B3)
    std::vector<int> det_visits(children.size(), 0);
    auto record = [&](size_t child_i, bool ok, double raw_value) {
      ChildStat& child = children[child_i];
      child.visits += 1;
      total_visits += 1;
      double v;
      if (ok) {
        v = config_.use_pwin_eval ? raw_value : std::tanh(raw_value / kValueSquashScale);
        any_success = true;
        if (config_.use_pwin_eval ? (std::fabs(raw_value) >= 0.999)
                                  : (std::fabs(raw_value) >= kTerminalRewardThreshold)) {
          hit_terminal = true;
        }
      } else {
        // A candidate whose simulation errors out gets the worst possible
        // sample (-1, the same floor as a genuine loss) -- stops the
        // selection loop re-picking a dead branch without conflating a
        // transient engine hiccup with anything larger than one loss sample.
        v = -1.0;
      }
      child.total_value += v;
      det_value[child_i] += v;
      det_visits[child_i] += 1;
    };

    const int num_det = std::max(1, config_.num_determinizations);
    for (int det = 0; det < num_det && elapsed_ms() < budget; ++det) {
      // Stabilization note #2: a FRESH hidden-state sample per
      // determinization -- statistics accumulate across all of them, so a
      // candidate's mean reflects its value across several sampled worlds,
      // not one fixed (previously: absurdly passive) one.
      std::vector<int> opp_deck, opp_prize, opp_hand;
      sample_opponent_hidden(root_obs, opp_deck, opp_prize, opp_hand);
      std::vector<int> opp_active;
      if (!root_obs.oppActive.present || root_obs.oppActive.faceDown) {
        // Prefer a Basic Pokemon from the archetype pool as the face-down
        // active guess (Block A1.5 refinement) -- a Grimmsnarl opponent's
        // hidden active should be an Impidimp, not a Dreepy. Falls back to
        // the original Dreepy filler if the pool has no Basic Pokemon.
        int guess = DETERMINIZATION_FILLER_POKEMON_ID;
        for (int cid : root_obs.oppHiddenPool) {
          const CardData& d = cards_.card(cid);
          if (d.cardType == enums::CT_POKEMON && d.basic) {
            guess = cid;
            break;
          }
        }
        opp_active = {guess};
      }

      cg::RawSearchResult begin = engine_.search_begin(search_begin_input, my_deck, my_prize, opp_deck,
                                                        opp_prize, opp_hand, opp_active, /*manual_coin=*/false);
      if (!begin.ok) {  // a bad sample shouldn't kill the whole search; try the next determinization
        if (out_begin_fail_count) ++(*out_begin_fail_count);
        if (out_begin_last_error) *out_begin_last_error = begin.error;
        continue;
      }
      any_begin_ok = true;
      if (out_begin_ok) *out_begin_ok = true;
      EndGuard end_guard{engine_};

      // Even time slice per determinization (remaining slices absorb any
      // slack if an earlier begin failed fast).
      const double det_deadline = std::min(budget, budget * static_cast<double>(det + 1) / static_cast<double>(num_det));

      // B3: fresh per-determinization stats for this world's vote.
      std::fill(det_value.begin(), det_value.end(), 0.0);
      std::fill(det_visits.begin(), det_visits.end(), 0);

      // Bootstrap: every arm sampled once under THIS determinization before
      // the selection formula is used on it.
      for (size_t i = 0; i < children.size(); ++i) {
        if (elapsed_ms() >= det_deadline) break;
        double raw = 0.0;
        bool ok = simulate_one(begin.search_id, root_obs, children[i].option_index, live_scorer, raw);
        record(i, ok, raw);
      }

      // Main selection loop for this determinization's time slice --
      // PUCT (B2) when enabled, plain UCB1 otherwise.
      while (elapsed_ms() < det_deadline && total_visits > 0) {
        int best = -1;
        double best_ucb = -1e300;
        for (size_t i = 0; i < children.size(); ++i) {
          const ChildStat& c = children[i];
          double ucb;
          if (c.visits == 0) {
            ucb = 1e18;  // never-tried arm still gets tried first
          } else if (config_.use_puct) {
            ucb = c.mean() + config_.ucb1_c * priors[i] *
                                 std::sqrt(static_cast<double>(total_visits)) /
                                 (1.0 + static_cast<double>(c.visits));
          } else {
            ucb = c.mean() + config_.ucb1_c * std::sqrt(std::log(static_cast<double>(total_visits)) /
                                                         static_cast<double>(c.visits));
          }
          if (ucb > best_ucb) {
            best_ucb = ucb;
            best = static_cast<int>(i);
          }
        }
        if (best < 0) break;
        double raw = 0.0;
        bool ok = simulate_one(begin.search_id, root_obs, children[static_cast<size_t>(best)].option_index,
                                live_scorer, raw);
        record(static_cast<size_t>(best), ok, raw);
      }

      // B3: this determinization's vote = best per-det mean among arms it
      // actually sampled (a det that ran out of time before sampling
      // anything casts no vote).
      int det_best = -1;
      double det_best_mean = -1e300;
      for (size_t i = 0; i < children.size(); ++i) {
        if (det_visits[i] > 0) {
          const double m = det_value[i] / static_cast<double>(det_visits[i]);
          if (m > det_best_mean) {
            det_best_mean = m;
            det_best = static_cast<int>(i);
          }
        }
      }
      if (det_best >= 0) {
        det_votes[static_cast<size_t>(det_best)] += 1;
        det_completed += 1;
      }
    }

    if (out_visits) *out_visits = total_visits;
    if (out_hit_terminal_reward) *out_hit_terminal_reward = hit_terminal;
    if (!any_begin_ok || !any_success) return -1;

    int best_i = -1;
    double best_mean = -1e300;
    for (size_t i = 0; i < children.size(); ++i) {
      if (children[i].visits > 0 && children[i].mean() > best_mean) {
        best_mean = children[i].mean();
        best_i = static_cast<int>(i);
      }
    }
    if (best_i < 0) return -1;

    // B3 (determinization voting): the candidate that wins the per-world
    // vote MAJORITY replaces the pooled-mean argmax -- robust to one
    // corrupted/unlucky sampled world dominating the pooled mean. Requires
    // a strict majority of completed determinizations; otherwise falls back
    // to the pooled-mean pick.
    if (config_.use_det_voting && det_completed >= 2) {
      int vote_best = -1, vote_max = 0;
      for (size_t i = 0; i < children.size(); ++i) {
        if (det_votes[i] > vote_max) {
          vote_max = det_votes[i];
          vote_best = static_cast<int>(i);
        }
      }
      if (vote_best >= 0 && 2 * vote_max > det_completed) best_i = vote_best;
      best_mean = children[static_cast<size_t>(best_i)].mean();
    }

    // Greedy-override margin (stabilization note #3): children[0] is V6's
    // own greedy pick per this function's contract. Deviating from it
    // requires a clear mean advantage on the [-1, 1] value scale --
    // sampling noise alone (a few hundredths) can no longer flip the
    // decision away from the known-decent greedy baseline.
    const ChildStat& greedy = children[0];
    if (best_i != 0 && greedy.visits > 0 &&
        (best_mean - greedy.mean()) < config_.greedy_override_margin) {
      return greedy.option_index;
    }
    return children[static_cast<size_t>(best_i)].option_index;
  }

 private:
  cg::Engine& engine_;
  const std::vector<int>& deck_const_;
  McTsConfig config_;
  GenericOpponentPolicy generic_opp_;  // Block A1.5 opponent rollout policy
  const CardTable& cards_;
  std::mt19937 rng_{std::random_device{}()};

  // Filler ids for whatever the sampled pool cannot cover (see
  // sample_opponent_hidden) -- Basic Fire Energy is always a legal guess,
  // and the face-down-Active guess must be a real Pokemon id (SearchBegin
  // requires this).
  static constexpr int DETERMINIZATION_FILLER_CARD_ID = 2;
  static constexpr int DETERMINIZATION_FILLER_POKEMON_ID = 119;  // Dreepy

  // Stabilization note #2 + Block A1 (V18): one randomized guess of the
  // opponent's hidden zones. Preferred path: obs.oppHiddenPool -- the
  // archetype-conditioned pool Python already resolved (classified
  // archetype's canonical 60 minus the opponent's visible board AND their
  // discard -- see opponent_model.py) -- used verbatim, no further
  // subtraction here. Fallback path (empty pool, defensive only): V17's
  // original mirror assumption, our own DECK constant minus the opponent's
  // visible board. Either way the pool is shuffled fresh per
  // determinization and dealt to hand/prize/deck at the exact counts
  // SearchBegin requires; whatever the pool cannot cover falls back to the
  // energy filler.
  void sample_opponent_hidden(const Observation& obs, std::vector<int>& opp_deck,
                              std::vector<int>& opp_prize, std::vector<int>& opp_hand) {
    std::vector<int> pool;
    if (!obs.oppHiddenPool.empty()) {
      pool = obs.oppHiddenPool;
    } else {
      pool = deck_const_;
      auto remove_one = [&](int id) {
        auto it = std::find(pool.begin(), pool.end(), id);
        if (it != pool.end()) pool.erase(it);
      };
      auto remove_visible = [&](const Pokemon& p) {
        if (!p.present || p.faceDown) return;
        remove_one(p.id);
        for (int eid : p.energyCardIds) remove_one(eid);
        for (int tid : p.toolIds) remove_one(tid);
        for (int pid : p.preEvoIds) remove_one(pid);
      };
      remove_visible(obs.oppActive);
      for (const auto& p : obs.oppBench) remove_visible(p);
    }
    std::shuffle(pool.begin(), pool.end(), rng_);
    auto deal = [&](int count) {
      std::vector<int> out;
      out.reserve(static_cast<size_t>(std::max(0, count)));
      for (int i = 0; i < count; ++i) {
        if (!pool.empty()) {
          out.push_back(pool.back());
          pool.pop_back();
        } else {
          out.push_back(DETERMINIZATION_FILLER_CARD_ID);
        }
      }
      return out;
    };
    opp_hand = deal(obs.oppHandCount);
    opp_prize = deal(obs.oppPrizeCount);
    opp_deck = deal(obs.oppDeckCount);
  }

  // `your_deck` must match our OWN known remaining-deck composition (a real
  // guess at ORDER, not identity -- see docs/search_api.md §1), which
  // root_obs.deckCounts already gives us as (id, count) pairs.
  static std::vector<int> expand_deck(const Observation& obs) {
    std::vector<int> out;
    out.reserve(static_cast<size_t>(std::max(0, obs.myDeckCount)));
    for (const auto& kv : obs.deckCounts) {
      for (int i = 0; i < kv.second; ++i) out.push_back(kv.first);
    }
    // SearchBegin requires an exact count match; pad defensively with the
    // filler id if our own bookkeeping came up short for any reason.
    while (static_cast<int>(out.size()) < obs.myDeckCount) out.push_back(DETERMINIZATION_FILLER_CARD_ID);
    return out;
  }

  // One full simulation for `option_index`: step it from this
  // determinization's root, then roll out (both sides, driven by a
  // disposable copy of the live scorer) until the game concludes or the
  // truncation cap is hit (stabilization note #4), then score the reached
  // state from the ROOT player's perspective. `out_value` is the RAW
  // state_value() -- the caller squashes it (and checks the terminal
  // threshold against the raw magnitude) via record(). Returns false on any
  // engine/parse failure.
  bool simulate_one(long long root_search_id, const Observation& root_obs, int option_index,
                     const V6Scorer& live_scorer, double& out_value) {
    cg::RawSearchResult step = engine_.search_step(root_search_id, std::vector<int>{option_index});
    if (!step.ok) return false;
    auto parsed = from_search_json(step.observation_json, root_obs);
    if (!parsed.has_value()) return false;

    Observation obs = *parsed;
    recompute_deck_counts(obs, deck_const_);

    // `_rollout_mode` equivalent: a disposable copy so plan_a_/plan_b_/
    // use_support_ mutations during rollout never touch the live decision-
    // maker's own state (see v6_heuristic.hpp header).
    V6Scorer scratch = live_scorer;

    long long node_id = step.search_id;
    int steps = 0;
    while (steps < config_.max_rollout_steps && obs.result < 0) {
      const bool actor_is_root = (obs.myIndex == root_obs.myIndex);

      // B4-lite (V22): soft-minimax widening on the first widen_steps
      // decision points. Branch the actor's top-widen_branch single-pick
      // options, evaluate each branched state with the B1 eval, continue
      // from the branch best FOR THE ACTOR (max root-value when we act,
      // min root-value when the opponent does). Falls through to the plain
      // policy step for multi-pick decisions or if every branch fails.
      if (config_.use_pwin_eval && steps < config_.widen_steps && obs.maxCount == 1 &&
          static_cast<int>(obs.options.size()) >= 2) {
        std::vector<double> opt_scores =
            actor_is_root ? scratch.raw_scores(obs) : generic_opp_.raw_scores(obs);
        std::vector<int> order(opt_scores.size());
        for (size_t i = 0; i < order.size(); ++i) order[i] = static_cast<int>(i);
        std::stable_sort(order.begin(), order.end(),
                          [&](int a, int b) { return opt_scores[static_cast<size_t>(a)] > opt_scores[static_cast<size_t>(b)]; });
        const int m = std::min(config_.widen_branch, static_cast<int>(order.size()));
        bool have_best = false;
        double best_actor_val = -1e300;
        long long best_id = 0;
        Observation best_obs;
        for (int bi = 0; bi < m; ++bi) {
          cg::RawSearchResult nx = engine_.search_step(node_id, std::vector<int>{order[static_cast<size_t>(bi)]});
          if (!nx.ok) continue;
          auto nobs = from_search_json(nx.observation_json, obs);
          if (!nobs.has_value()) continue;
          const double v_root = eval_obs(*nobs, root_obs.myIndex);
          const double actor_val = actor_is_root ? v_root : -v_root;
          if (!have_best || actor_val > best_actor_val) {
            have_best = true;
            best_actor_val = actor_val;
            best_id = nx.search_id;
            best_obs = std::move(*nobs);
          }
        }
        if (have_best) {
          obs = std::move(best_obs);
          recompute_deck_counts(obs, deck_const_);
          node_id = best_id;
          ++steps;
          continue;
        }
        // all branches failed: fall through to the plain policy step below
      }

      // Block A1.5: decisions alternate between players during a rollout
      // (obs.myIndex tracks whoever is CURRENTLY acting). Our own side keeps
      // the full V6 scorer; the opponent's side uses the deck-agnostic
      // generic policy (see generic_opponent.hpp's header for why V6Scorer
      // was the wrong driver for foreign-archetype cards).
      std::vector<int> choice = actor_is_root ? scratch.choose(obs) : generic_opp_.choose(obs);
      cg::RawSearchResult next = engine_.search_step(node_id, choice);
      if (!next.ok) break;  // evaluate whatever state we already reached
      auto next_obs = from_search_json(next.observation_json, obs);
      if (!next_obs.has_value()) break;
      obs = *next_obs;
      recompute_deck_counts(obs, deck_const_);
      node_id = next.search_id;
      ++steps;
    }

    if (config_.use_pwin_eval) {
      out_value = eval_obs(obs, root_obs.myIndex);
    } else {
      out_value = scratch.state_value(obs, root_obs.myIndex);
    }
    return true;
  }

  // B1 evaluator: learned P(win) mapped to [-1, 1] from the ROOT player's
  // perspective. A genuinely concluded game is scored exactly (+1/-1/0);
  // the model is only consulted for unresolved positions. The model
  // predicts for the feature vector's ACTING player (obs.myIndex) -- the
  // probability is flipped when that is not the root player (trained on
  // both sides of top-level games, so both directions are in-distribution).
  double eval_obs(const Observation& obs, int root_index) const {
    if (obs.result >= 0) {
      return (obs.result == root_index) ? 1.0 : (obs.result == 2 ? 0.0 : -1.0);
    }
    float features[v20::kVecFeatureCount];
    v20::vectorize_observation(obs, cards_, features);
    const double p_acting = v20::pwin_predict(features);
    const double p_root = (obs.myIndex == root_index) ? p_acting : 1.0 - p_acting;
    return 2.0 * p_root - 1.0;
  }
};

}  // namespace v17
