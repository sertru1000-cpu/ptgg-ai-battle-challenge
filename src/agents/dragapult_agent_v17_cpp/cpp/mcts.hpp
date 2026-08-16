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

#include "cg_engine.hpp"
#include "deck_tracking.hpp"
#include "observation.hpp"
#include "v6_heuristic.hpp"
#include "v6_heuristic_scores.hpp"

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
  double ucb1_c = 1.25;              // standard-order exploration constant -- valid again now that means live in [-1, 1]
  double greedy_override_margin = 0.20;  // note #3: minimum mean advantage (squashed scale) required to override V6's greedy pick
                                          // (0.10 -> 0.20 after the 2026-08-14 120-game run: overrides averaged ~44% WR vs the
                                          // 47.5% baseline -- low-confidence overrides still net-negative, confident ones
                                          // (ATTACK-vs-PLAY 56.5%, ATTACK-vs-ABILITY 62.1%) worth keeping)
};

struct ChildStat {
  int option_index = -1;
  int visits = 0;
  double total_value = 0.0;
  double mean() const { return visits > 0 ? total_value / static_cast<double>(visits) : 0.0; }
};

class Mcts {
 public:
  Mcts(cg::Engine& engine, const std::vector<int>& deck_const, McTsConfig config)
      : engine_(engine), deck_const_(deck_const), config_(config) {}

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

  int search(const Observation& root_obs, const std::vector<int>& candidate_indices,
             const std::string& search_begin_input, const V6Scorer& live_scorer,
             int* out_visits = nullptr, bool* out_begin_ok = nullptr,
             bool* out_hit_terminal_reward = nullptr) {
    if (out_visits) *out_visits = 0;
    if (out_begin_ok) *out_begin_ok = false;
    if (out_hit_terminal_reward) *out_hit_terminal_reward = false;
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

    auto record = [&](ChildStat& child, bool ok, double raw_value) {
      child.visits += 1;
      total_visits += 1;
      if (ok) {
        child.total_value += std::tanh(raw_value / kValueSquashScale);
        any_success = true;
        if (std::fabs(raw_value) >= kTerminalRewardThreshold) hit_terminal = true;
      } else {
        // A candidate whose simulation errors out gets the worst possible
        // squashed sample (-1, the same floor as a genuine clipped loss) --
        // stops UCB1 re-selecting a dead branch every iteration without
        // conflating a transient engine/parse hiccup with anything larger
        // than one full-loss sample.
        child.total_value += -1.0;
      }
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
        opp_active = {DETERMINIZATION_FILLER_POKEMON_ID};
      }

      cg::RawSearchResult begin = engine_.search_begin(search_begin_input, my_deck, my_prize, opp_deck,
                                                        opp_prize, opp_hand, opp_active, /*manual_coin=*/false);
      if (!begin.ok) continue;  // a bad sample shouldn't kill the whole search; try the next determinization
      any_begin_ok = true;
      if (out_begin_ok) *out_begin_ok = true;
      EndGuard end_guard{engine_};

      // Even time slice per determinization (remaining slices absorb any
      // slack if an earlier begin failed fast).
      const double det_deadline = std::min(budget, budget * static_cast<double>(det + 1) / static_cast<double>(num_det));

      // Bootstrap: every arm sampled once under THIS determinization before
      // UCB1's log(total_visits) term is used on it.
      for (auto& child : children) {
        if (elapsed_ms() >= det_deadline) break;
        double raw = 0.0;
        bool ok = simulate_one(begin.search_id, root_obs, child.option_index, live_scorer, raw);
        record(child, ok, raw);
      }

      // Main UCB1 loop for this determinization's time slice.
      while (elapsed_ms() < det_deadline && total_visits > 0) {
        int best = -1;
        double best_ucb = -1e300;
        for (size_t i = 0; i < children.size(); ++i) {
          const ChildStat& c = children[i];
          double ucb;
          if (c.visits == 0) {
            ucb = 1e18;  // never-tried arm still gets tried first
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
        record(children[static_cast<size_t>(best)], ok, raw);
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

    // Greedy-override margin (stabilization note #3): children[0] is V6's
    // own greedy pick per this function's contract. Deviating from it
    // requires a clear mean advantage on the squashed [-1, 1] scale --
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
  std::mt19937 rng_{std::random_device{}()};

  // Filler ids for whatever the sampled pool cannot cover (see
  // sample_opponent_hidden) -- Basic Fire Energy is always a legal guess,
  // and the face-down-Active guess must be a real Pokemon id (SearchBegin
  // requires this).
  static constexpr int DETERMINIZATION_FILLER_CARD_ID = 2;
  static constexpr int DETERMINIZATION_FILLER_POKEMON_ID = 119;  // Dreepy

  // Stabilization note #2: one randomized guess of the opponent's hidden
  // zones. Pool = our own DECK constant (mirror-match assumption) minus
  // every card visible on the opponent's board, shuffled, then dealt to
  // hand/prize/deck at the exact counts SearchBegin requires. Cards the
  // pool cannot cover (e.g. a large unseen opponent discard, or a
  // non-mirror opponent with more cards than our 60) fall back to the
  // energy filler -- but the leading cards of every zone are now real,
  // playable archetype cards, so the simulated opponent evolves, plays
  // trainers, and attacks back instead of passing every turn.
  void sample_opponent_hidden(const Observation& obs, std::vector<int>& opp_deck,
                              std::vector<int>& opp_prize, std::vector<int>& opp_hand) {
    std::vector<int> pool = deck_const_;
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
      std::vector<int> choice = scratch.choose(obs);
      cg::RawSearchResult next = engine_.search_step(node_id, choice);
      if (!next.ok) break;  // evaluate whatever state we already reached
      auto next_obs = from_search_json(next.observation_json, obs);
      if (!next_obs.has_value()) break;
      obs = *next_obs;
      recompute_deck_counts(obs, deck_const_);
      node_id = next.search_id;
      ++steps;
    }

    out_value = scratch.state_value(obs, root_obs.myIndex);
    return true;
  }
};

}  // namespace v17
