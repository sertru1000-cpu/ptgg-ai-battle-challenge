// V24 / Block B4: TRUE multi-level PUCT tree search over the engine's own
// search sandbox -- the architecture jump every prior version deferred.
//
// Empirical basis (probed live against the sandbox before writing this):
//   - search_step() chains to a real game CONCLUSION (depth 91 observed,
//     result populated) -- depth is unlimited;
//   - 5000+ sibling expansions from one node with no cap and no release;
//   - 0.13-0.23 ms per step from Python, less from C++ -- a 1400ms budget
//     affords ~5-7K node expansions per decision.
//
// Design (AlphaZero-shaped, adapted to hidden info + a stochastic engine):
//   - NO rollouts: expansion evaluates the new leaf with the learned B1v2
//     P(win) (pwin_trees.hpp via vectorizer.hpp), terminals score exactly.
//     All values stored from the ROOT player's perspective in [-1, 1].
//   - Two-player selection: at each node pick the edge maximizing
//     sign*Q + c * P * sqrt(N_parent) / (1 + N_edge), sign = +1 when the
//     node's actor is the root player, -1 otherwise (opponent minimizes our
//     value). Q of an untried edge initializes to the parent's own value
//     (standard "init-to-parent" -- optimistic enough to try each once).
//   - Priors: our nodes use a scratch V6Scorer's raw scores; opponent nodes
//     use GenericOpponentPolicy's bands; both softmaxed with a floor.
//   - Single-pick nodes branch over top-K options; multi-pick nodes (e.g.
//     Phantom Dive counter spreads -- combinatorial) traverse ONE edge:
//     the respective policy's full choice.
//   - Stochastic transitions (draws/shuffles resample per search_step):
//     each edge samples its child ONCE and keeps it -- sampling noise is
//     handled where it always was, by root determinization voting (B3).
//   - The engine sandbox owns node lifetimes; search_end() frees the whole
//     determinization's tree at once (RAII guard in the caller loop).
#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <random>
#include <string>
#include <vector>

#include "bc_option_features.hpp"
#include "bc_trees.hpp"
#include "card_data.hpp"
#include "cg_engine.hpp"
#include "generic_opponent.hpp"
#include "observation.hpp"
#include "pwin_trees.hpp"
#include "v6_heuristic.hpp"
#include "vectorizer.hpp"

namespace v17 {

struct DeepTreeConfig {
  double time_budget_ms = 300.0;
  double safety_buffer_ms = 100.0;
  int num_determinizations = 4;      // fewer worlds, deeper trees per world
  double puct_c = 1.5;
  double prior_temperature_ours = 20000.0;
  double prior_temperature_opp = 50000.0;
  double prior_floor = 0.03;
  int max_children = 6;              // top-K branching at every tree level
  int max_nodes_per_det = 4000;      // hard safety cap (probe saw no engine cap; ours)
  double greedy_override_margin = 0.10;  // on root Q scale [-1,1]; deep values are
                                          // less noisy than rollout means, so a
                                          // smaller margin than V20's 0.20
  // V26: neural priors -- OUR nodes' edge priors come from the leader-
  // imitation BC ranker (bc_trees.hpp over 87 state + 16 option features)
  // instead of hand-coded V6 scores. 46% top-1 imitation failed as a
  // STANDALONE policy (compounding errors) but is exactly the AlphaZero
  // prior regime: it only shapes exploration; the tree + learned eval
  // correct it.
  bool use_bc_priors = true;
  double bc_prior_temperature = 2.0;  // softmax over raw logit margins
};

class DeepTree {
 public:
  DeepTree(cg::Engine& engine, const CardTable& cards, const std::vector<int>& deck_const,
           DeepTreeConfig config)
      : engine_(engine), cards_(cards), deck_const_(deck_const), config_(config), generic_(cards) {}

  // Same contract as Mcts::search: candidate_indices[0] is V6's greedy pick;
  // returns chosen option index or -1 (caller falls back to greedy).
  int search(const Observation& root_obs, const std::vector<int>& candidate_indices,
             const std::string& search_begin_input, const V6Scorer& live_scorer,
             int* out_visits = nullptr, bool* out_begin_ok = nullptr, int* out_max_depth = nullptr) {
    if (out_visits) *out_visits = 0;
    if (out_begin_ok) *out_begin_ok = false;
    if (out_max_depth) *out_max_depth = 0;
    if (candidate_indices.empty()) return -1;

    auto t_start = std::chrono::steady_clock::now();
    auto elapsed_ms = [&]() {
      return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t_start).count();
    };
    const double budget = std::max(0.0, config_.time_budget_ms - config_.safety_buffer_ms);

    std::vector<int> my_deck = expand_my_deck(root_obs);
    std::vector<int> my_prize = root_obs.myPrizeGuess;
    while (static_cast<int>(my_prize.size()) < root_obs.myPrizeCount) my_prize.push_back(2);

    const size_t K = candidate_indices.size();
    std::vector<double> root_N(K, 0.0), root_W(K, 0.0);
    std::vector<int> det_votes(K, 0);
    int det_completed = 0;
    int total_visits = 0;
    int max_depth_seen = 0;

    struct EndGuard {
      cg::Engine& e;
      ~EndGuard() { e.search_end(); }
    };

    const int num_det = std::max(1, config_.num_determinizations);
    for (int det = 0; det < num_det && elapsed_ms() < budget; ++det) {
      std::vector<int> opp_deck, opp_prize, opp_hand;
      sample_opponent_hidden(root_obs, opp_deck, opp_prize, opp_hand);
      std::vector<int> opp_active;
      if (!root_obs.oppActive.present || root_obs.oppActive.faceDown) {
        int guess = 119;
        for (int cid : root_obs.oppHiddenPool) {
          const CardData& d = cards_.card(cid);
          if (d.cardType == enums::CT_POKEMON && d.basic) { guess = cid; break; }
        }
        opp_active = {guess};
      }
      cg::RawSearchResult begin = engine_.search_begin(search_begin_input, my_deck, my_prize,
                                                        opp_deck, opp_prize, opp_hand, opp_active, false);
      if (!begin.ok) continue;
      if (out_begin_ok) *out_begin_ok = true;
      EndGuard guard{engine_};

      nodes_.clear();
      nodes_.reserve(1024);
      // Root node: children restricted to the pruned candidate list (keeps
      // the greedy-margin contract); prior from live_scorer's raw scores is
      // supplied by the caller implicitly via candidate order -- root uses
      // uniform priors over the already-pruned set (they were top-K by score).
      Node root;
      root.search_id = begin.search_id;
      root.obs = root_obs;
      root.actor_is_root = true;
      root.value = 0.0;
      // V26: root candidate priors from the BC ranker too (uniform otherwise).
      std::vector<double> root_prior(K, 1.0 / static_cast<double>(K));
      if (config_.use_bc_priors) {
        float x[v20::kVecFeatureCount + v26::kBcOptionFeatureCount];
        v20::vectorize_observation(root_obs, cards_, x);
        std::vector<double> margins(K);
        double mx = -1e300;
        for (size_t i = 0; i < K; ++i) {
          v26::bc_option_features(root_obs, root_obs.options[static_cast<size_t>(candidate_indices[i])],
                                  cards_, x + v20::kVecFeatureCount);
          margins[i] = v26::bc_predict_margin(x);
          mx = std::max(mx, margins[i]);
        }
        double denom = 0.0;
        for (size_t i = 0; i < K; ++i) {
          root_prior[i] = std::exp((margins[i] - mx) / config_.bc_prior_temperature);
          denom += root_prior[i];
        }
        for (double& pr : root_prior) pr = std::max(config_.prior_floor, pr / denom);
      }
      for (size_t i = 0; i < K; ++i) {
        Edge e;
        e.choice = {candidate_indices[i]};
        e.prior = root_prior[i];
        root.edges.push_back(e);
      }
      nodes_.push_back(std::move(root));

      std::vector<double> det_N(K, 0.0), det_W(K, 0.0);
      const double det_deadline = std::min(budget, budget * static_cast<double>(det + 1) / num_det);

      while (elapsed_ms() < det_deadline && static_cast<int>(nodes_.size()) < config_.max_nodes_per_det) {
        int depth = 0;
        double leaf_value = 0.0;
        int root_edge = simulate_once(0, root_obs, live_scorer, depth, leaf_value);
        if (root_edge < 0) break;
        ++total_visits;
        max_depth_seen = std::max(max_depth_seen, depth);
        root_N[static_cast<size_t>(root_edge)] += 1.0;
        root_W[static_cast<size_t>(root_edge)] += leaf_value;
        det_N[static_cast<size_t>(root_edge)] += 1.0;
        det_W[static_cast<size_t>(root_edge)] += leaf_value;
      }

      int best = -1;
      double best_n = 0.0;
      for (size_t i = 0; i < K; ++i) {
        if (det_N[i] > best_n) { best_n = det_N[i]; best = static_cast<int>(i); }
      }
      if (best >= 0) { det_votes[static_cast<size_t>(best)] += 1; ++det_completed; }
    }

    if (out_visits) *out_visits = total_visits;
    if (out_max_depth) *out_max_depth = max_depth_seen;
    if (total_visits == 0) return -1;

    // Final pick: vote majority (B3) over per-det most-visited, else global
    // most-visited; margin gate vs greedy (index 0) on mean-Q scale.
    int best_i = 0;
    double best_n = -1.0;
    for (size_t i = 0; i < K; ++i) {
      if (root_N[i] > best_n) { best_n = root_N[i]; best_i = static_cast<int>(i); }
    }
    if (det_completed >= 2) {
      int vb = -1, vm = 0;
      for (size_t i = 0; i < K; ++i) {
        if (det_votes[i] > vm) { vm = det_votes[i]; vb = static_cast<int>(i); }
      }
      if (vb >= 0 && 2 * vm > det_completed) best_i = vb;
    }
    if (best_i != 0 && root_N[0] > 0.0 && root_N[static_cast<size_t>(best_i)] > 0.0) {
      const double q_best = root_W[static_cast<size_t>(best_i)] / root_N[static_cast<size_t>(best_i)];
      const double q_greedy = root_W[0] / root_N[0];
      if (q_best - q_greedy < config_.greedy_override_margin) best_i = 0;
    }
    return candidate_indices[static_cast<size_t>(best_i)];
  }

 private:
  struct Edge {
    std::vector<int> choice;
    double prior = 0.0;
    int child = -1;   // index into nodes_, -1 = unexpanded
    double N = 0.0;
    double W = 0.0;   // sum of root-perspective values
  };
  struct Node {
    long long search_id = 0;
    Observation obs;
    bool terminal = false;
    bool actor_is_root = true;
    double value = 0.0;  // root-perspective leaf evaluation at creation
    std::vector<Edge> edges;
  };

  cg::Engine& engine_;
  const CardTable& cards_;
  const std::vector<int>& deck_const_;
  DeepTreeConfig config_;
  GenericOpponentPolicy generic_;
  std::mt19937 rng_{std::random_device{}()};
  std::vector<Node> nodes_;

  // One selection->expansion->backup pass. Returns the ROOT edge index this
  // pass descended through (-1 on hard failure), sets `depth` and the leaf
  // value that was backed up.
  int simulate_once(int root_index, const Observation& root_obs, const V6Scorer& live_scorer,
                    int& depth, double& leaf_value) {
    std::vector<std::pair<int, int>> path;  // (node index, edge index)
    int cur = root_index;
    int root_edge = -1;

    while (true) {
      Node& node = nodes_[static_cast<size_t>(cur)];
      if (node.terminal) { leaf_value = node.value; break; }
      if (node.edges.empty()) { leaf_value = node.value; break; }  // no legal branching recorded

      // Select edge by signed PUCT.
      double parent_n = 1.0;
      for (const Edge& e : node.edges) parent_n += e.N;
      const double sign = node.actor_is_root ? 1.0 : -1.0;
      int best_e = -1;
      double best_u = -1e300;
      for (size_t ei = 0; ei < node.edges.size(); ++ei) {
        const Edge& e = node.edges[ei];
        const double q = e.N > 0.0 ? (e.W / e.N) : node.value;  // init-to-parent
        const double u = sign * q + config_.puct_c * e.prior * std::sqrt(parent_n) / (1.0 + e.N);
        if (u > best_u) { best_u = u; best_e = static_cast<int>(ei); }
      }
      if (best_e < 0) { leaf_value = node.value; break; }
      if (cur == root_index) root_edge = best_e;
      path.emplace_back(cur, best_e);

      Edge& edge = nodes_[static_cast<size_t>(cur)].edges[static_cast<size_t>(best_e)];
      if (edge.child < 0) {
        int child = expand(cur, best_e, root_obs, live_scorer);
        if (child < 0) {
          // Expansion failed (engine/parse): score as a lost line for the
          // acting side rather than crashing the whole pass.
          leaf_value = nodes_[static_cast<size_t>(cur)].actor_is_root ? -1.0 : 1.0;
          break;
        }
        edge.child = child;
        leaf_value = nodes_[static_cast<size_t>(child)].value;
        depth = static_cast<int>(path.size());
        break;
      }
      cur = edge.child;
      depth = static_cast<int>(path.size());
    }

    for (auto& [ni, ei] : path) {
      Edge& e = nodes_[static_cast<size_t>(ni)].edges[static_cast<size_t>(ei)];
      e.N += 1.0;
      e.W += leaf_value;
    }
    return root_edge;
  }

  // Steps the engine along `edge`, builds and evaluates the child node.
  int expand(int parent_index, int edge_index, const Observation& root_obs, const V6Scorer& live_scorer) {
    Node& parent = nodes_[static_cast<size_t>(parent_index)];
    const Edge& edge = parent.edges[static_cast<size_t>(edge_index)];
    cg::RawSearchResult step = engine_.search_step(parent.search_id, edge.choice);
    if (!step.ok) return -1;
    auto parsed = from_search_json(step.observation_json, parent.obs);
    if (!parsed.has_value()) return -1;

    Node child;
    child.search_id = step.search_id;
    child.obs = std::move(*parsed);
    recompute_deck_counts(child.obs, deck_const_);
    child.actor_is_root = (child.obs.myIndex == root_obs.myIndex);

    if (child.obs.result >= 0) {
      child.terminal = true;
      child.value = (child.obs.result == root_obs.myIndex) ? 1.0 : (child.obs.result == 2 ? 0.0 : -1.0);
    } else {
      float features[v20::kVecFeatureCount];
      v20::vectorize_observation(child.obs, cards_, features);
      const double p_acting = v20::pwin_predict(features);
      const double p_root = child.actor_is_root ? p_acting : 1.0 - p_acting;
      child.value = 2.0 * p_root - 1.0;
      build_edges(child, live_scorer);
    }
    nodes_.push_back(std::move(child));
    return static_cast<int>(nodes_.size()) - 1;
  }

  void build_edges(Node& node, const V6Scorer& live_scorer) {
    const Observation& o = node.obs;
    if (o.options.empty()) return;

    if (o.maxCount != 1) {
      // Multi-pick: one edge -- the acting side's full policy choice.
      Edge e;
      if (node.actor_is_root) {
        V6Scorer scratch = live_scorer;
        e.choice = scratch.choose(o);
      } else {
        e.choice = generic_.choose(o);
      }
      if (e.choice.empty()) return;
      e.prior = 1.0;
      node.edges.push_back(std::move(e));
      return;
    }

    // Single-pick: top-K options by the acting side's policy score, softmax priors.
    std::vector<double> scores;
    double temperature;
    if (node.actor_is_root && config_.use_bc_priors) {
      // V26: leader-imitation ranker margins as prior scores.
      float x[v20::kVecFeatureCount + v26::kBcOptionFeatureCount];
      v20::vectorize_observation(o, cards_, x);
      scores.resize(o.options.size());
      for (size_t i = 0; i < o.options.size(); ++i) {
        v26::bc_option_features(o, o.options[i], cards_, x + v20::kVecFeatureCount);
        scores[i] = v26::bc_predict_margin(x);
      }
      temperature = config_.bc_prior_temperature;
    } else if (node.actor_is_root) {
      V6Scorer scratch = live_scorer;
      scores = scratch.raw_scores(o);
      temperature = config_.prior_temperature_ours;
    } else {
      scores.resize(o.options.size());
      for (size_t i = 0; i < o.options.size(); ++i) scores[i] = generic_score(o, i);
      temperature = config_.prior_temperature_opp;
    }
    std::vector<int> order(scores.size());
    for (size_t i = 0; i < order.size(); ++i) order[i] = static_cast<int>(i);
    std::stable_sort(order.begin(), order.end(),
                      [&](int a, int b) { return scores[static_cast<size_t>(a)] > scores[static_cast<size_t>(b)]; });
    const int k = std::min<int>(config_.max_children, static_cast<int>(order.size()));
    double mx = scores[static_cast<size_t>(order[0])];
    double denom = 0.0;
    std::vector<double> pri(static_cast<size_t>(k));
    for (int i = 0; i < k; ++i) {
      pri[static_cast<size_t>(i)] = std::exp((scores[static_cast<size_t>(order[i])] - mx) / temperature);
      denom += pri[static_cast<size_t>(i)];
    }
    for (int i = 0; i < k; ++i) {
      Edge e;
      e.choice = {order[static_cast<size_t>(i)]};
      e.prior = std::max(config_.prior_floor, pri[static_cast<size_t>(i)] / denom);
      node.edges.push_back(std::move(e));
    }
  }

  double generic_score(const Observation& o, size_t option_index) {
    // GenericOpponentPolicy scores whole option lists via choose(); expose a
    // single option's band score by reusing its internals is private -- use a
    // cheap proxy: rank via its choose() top pick gets a bonus; others by type.
    // (Kept simple: full per-option generic scoring lives inside the policy's
    // select_top path; a proxy suffices for PRIORS, which only shape search.)
    const Option& opt = o.options[option_index];
    switch (opt.type) {
      case enums::OPT_ATTACK: return 100000.0;
      case enums::OPT_EVOLVE: return 20000.0;
      case enums::OPT_ATTACH: return 10000.0;
      case enums::OPT_ABILITY: return 8000.0;
      case enums::OPT_PLAY: return 6000.0;
      case enums::OPT_RETREAT: return 100.0;
      default: return 1000.0;
    }
  }

  void sample_opponent_hidden(const Observation& obs, std::vector<int>& opp_deck,
                              std::vector<int>& opp_prize, std::vector<int>& opp_hand) {
    std::vector<int> pool = obs.oppHiddenPool.empty() ? deck_const_ : obs.oppHiddenPool;
    std::shuffle(pool.begin(), pool.end(), rng_);
    auto deal = [&](int count) {
      std::vector<int> out;
      for (int i = 0; i < count; ++i) {
        if (!pool.empty()) { out.push_back(pool.back()); pool.pop_back(); }
        else out.push_back(2);
      }
      return out;
    };
    opp_hand = deal(obs.oppHandCount);
    opp_prize = deal(obs.oppPrizeCount);
    opp_deck = deal(obs.oppDeckCount);
  }

  static std::vector<int> expand_my_deck(const Observation& obs) {
    std::vector<int> out;
    for (const auto& kv : obs.deckCounts) {
      for (int i = 0; i < kv.second; ++i) out.push_back(kv.first);
    }
    while (static_cast<int>(out.size()) < obs.myDeckCount) out.push_back(2);
    return out;
  }
};

}  // namespace v17
