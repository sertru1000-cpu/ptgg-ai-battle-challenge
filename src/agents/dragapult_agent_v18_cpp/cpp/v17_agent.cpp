// Top-level C ABI entrypoint -- the ONLY translation unit in this library
// (every other file here is header-only), so the whole build is one
// compiler invocation: `g++ -O3 -shared -fPIC -std=c++17 -o libv17.so
// v17_agent.cpp -ldl` (see ../compile.sh). This single-TU design is
// deliberate: main_v17.py compiles this on first import (see ../README.md's
// "Compilation" section), and a one-file build has the smallest possible
// surface for that to go wrong on an unknown grading container.
//
// Two exported functions:
//   v17_init(cg_lib_path, deck_ids, deck_len) -- once per process, at Python
//     module import time. Loads the native engine, static card/attack
//     tables, and the DECK constant.
//   v17_choose_action(obs, search_begin_input, ..., out_indices, ...) --
//     once per real Kaggle decision. Everything between entry and return
//     stays in C++; see mcts.hpp's header for the call-chain shape.
//
// No heap object crosses this boundary in either direction: `obs` is a
// caller-owned, pointer-passed struct (v17_abi.h) copied into an owned
// v17::Observation immediately; the response is written into a
// caller-provided `out_indices` buffer. There is nothing for main_v17.py to
// free -- eliminates an entire class of cross-allocator freeing bugs by
// construction, not by convention.
#include <algorithm>
#include <memory>
#include <string>
#include <vector>

#include "card_data.hpp"
#include "cg_engine.hpp"
#include "mcts.hpp"
#include "observation.hpp"
#include "v17_abi.h"
#include "v6_heuristic.hpp"
#include "v6_heuristic_scores.hpp"

namespace {

std::unique_ptr<cg::Engine> g_engine;
v17::CardTable g_cards;
std::vector<int> g_deck;
std::unique_ptr<v17::V6Scorer> g_live_scorer;
bool g_initialized = false;

// V11's own MACRO_LOOKAHEAD_TOP_N (dragapult_policy_v11.py) -- same
// candidate-narrowing shape, reused here for the same reason: bound the
// branching factor before spending simulation budget.
constexpr int kTopNCandidates = 6;

}  // namespace

extern "C" {

#if defined(_WIN32)
#define V17_API __declspec(dllexport)
#else
#define V17_API __attribute__((visibility("default")))
#endif

// Returns 0 on success. Any nonzero return means main_v17.py must fall back
// to the pure-Python V6 agent for the entire game -- there is no partial
// "native for some decisions" mode once init has failed.
V17_API int v17_init(const char* cg_lib_path, const int* deck_ids, int deck_len) {
  try {
    if (!cg_lib_path || !deck_ids || deck_len <= 0) return 1;
    g_engine = std::make_unique<cg::Engine>(std::string(cg_lib_path));
    g_cards.load(g_engine->all_card_json(), g_engine->all_attack_json());
    g_deck.assign(deck_ids, deck_ids + deck_len);
    g_live_scorer = std::make_unique<v17::V6Scorer>(g_cards, v17::balanced_weights());
    g_initialized = true;
    return 0;
  } catch (...) {
    g_engine.reset();
    g_live_scorer.reset();
    g_initialized = false;
    return 2;
  }
}

// Returns 0 on success (out_indices[0..*out_count) populated). Any nonzero
// return means main_v17.py must fall back to the pure-Python V6 agent for
// THIS decision only (the native library and live scorer state remain valid
// for subsequent calls -- a single bad decision's error should not force
// falling back for the rest of the match, matching this project's existing
// try/except-per-call safety pattern in src/agents/search_lookahead_v2.py).
//
// out_eligible/out_search_begin_ok/out_visits (all optional/nullable, all
// written 0 before any early return): search-budget diagnostics added for
// the deep-search-budget experiment -- lets Python report real rollout
// counts and distinguish "this decision didn't qualify for search at all"
// from "it qualified but search_begin failed" from "it actually ran N
// simulations", instead of only ever seeing the final chosen action.
//
// out_greedy_index/out_mcts_index/out_hit_terminal_reward (all optional/
// nullable, -1/-1/0 before any early return or when not eligible): added for
// the divergence root-cause investigation (200-game deep-search run showed
// V17 losing to plain V6 78% of the time once search was confirmed actually
// running) -- lets the caller see, per decision, whether MCTS's final pick
// differs from V6's own raw greedy pick, and whether that pick was informed
// by any rollout that reached a real (simulated) game conclusion (see
// Mcts::kTerminalRewardThreshold's comment for why that matters -- state_value's
// +-1,000,000 terminal reward, faithfully ported from dragapult_policy_v11.py's
// one-shot-per-candidate usage, was never previously averaged with mundane
// few-hundred-to-few-thousand heuristic scores in an unweighted mean the way
// UCB1's `total_value / visits` does).
V17_API int v17_choose_action(const V17RootObservationC* obs_c, const char* search_begin_input,
                               int search_begin_input_len, double time_budget_ms, int* out_indices,
                               int out_indices_cap, int* out_count, int* out_eligible,
                               int* out_search_begin_ok, int* out_visits, int* out_greedy_index,
                               int* out_mcts_index, int* out_hit_terminal_reward,
                               int* out_begin_fail_count, int* out_begin_last_error) {
  if (out_count) *out_count = 0;
  if (out_eligible) *out_eligible = 0;
  if (out_search_begin_ok) *out_search_begin_ok = 0;
  if (out_visits) *out_visits = 0;
  if (out_greedy_index) *out_greedy_index = -1;
  if (out_mcts_index) *out_mcts_index = -1;
  if (out_hit_terminal_reward) *out_hit_terminal_reward = 0;
  if (out_begin_fail_count) *out_begin_fail_count = 0;
  if (out_begin_last_error) *out_begin_last_error = 0;
  if (!g_initialized || !g_engine || !g_live_scorer) return 10;
  if (!obs_c || !out_indices || !out_count || out_indices_cap <= 0) return 11;
  if (obs_c->abi_magic != V17_ABI_MAGIC) return 12;  // struct-layout mismatch between Python and this build -- never guess, hard-fail

  try {
    v17::Observation root_obs = v17::from_ctypes(*obs_c);

    // Always computed: this is V6's own unmodified greedy choice, exactly
    // mirroring dragapult_policy_v11.py's `scores = ...` (step 1) -- also
    // the side-effecting call that updates plan_a_/plan_b_/use_support_ for
    // this decision (only when context == MAIN; see v6_heuristic.hpp).
    std::vector<double> scores = g_live_scorer->raw_scores(root_obs);
    std::vector<int> greedy_choice = v17::V6Scorer::select_top(root_obs, scores);
    std::vector<int> final_choice = greedy_choice;
    if (out_greedy_index && !greedy_choice.empty()) *out_greedy_index = greedy_choice[0];

    bool eligible_for_search = (root_obs.context == v17::enums::CTX_MAIN) && (root_obs.maxCount == 1) &&
                                (static_cast<int>(root_obs.options.size()) >= 2) && search_begin_input &&
                                (search_begin_input_len > 0);
    if (out_eligible) *out_eligible = eligible_for_search ? 1 : 0;

    if (eligible_for_search) {
      std::vector<int> ranked(scores.size());
      for (size_t i = 0; i < scores.size(); ++i) ranked[i] = static_cast<int>(i);
      std::stable_sort(ranked.begin(), ranked.end(),
                        [&](int a, int b) { return scores[static_cast<size_t>(a)] > scores[static_cast<size_t>(b)]; });

      // Candidate pruning (2026-08-14 stabilization -- see mcts.hpp's header
      // notes): V6 marks deliberately-bad moves with negative scores (-1 /
      // UNNECESSARY) and leaves unmodeled options (notably plain end-turn)
      // at the 0 default. Neither belongs in the search tree when V6 sees a
      // genuinely good action available (score >= 1000): at the observed
      // 8-12% divergence win rates, letting a 0-scored END or a
      // negative-scored option win on noisy rollout means is pure downside
      // (the MCTS:[END]-vs-V6:[PLAY] bucket, 60 occurrences / 11.7% WR).
      // The greedy top-1 is always candidates[0] -- Mcts::search's contract
      // (it is the margin-gating baseline).
      std::vector<int> candidates;
      const double best_score = scores[static_cast<size_t>(ranked[0])];
      for (size_t i = 0; i < ranked.size() && static_cast<int>(candidates.size()) < kTopNCandidates; ++i) {
        const double s = scores[static_cast<size_t>(ranked[i])];
        if (!candidates.empty() && (s < 0.0 || (best_score >= 1000.0 && s <= 0.0))) break;  // sorted descending -- nothing later qualifies either
        candidates.push_back(ranked[i]);
      }

      if (static_cast<int>(candidates.size()) >= 2) {
        v17::McTsConfig cfg;
        cfg.time_budget_ms = time_budget_ms;
        v17::Mcts mcts(*g_engine, g_cards, g_deck, cfg);
        std::string sbi(search_begin_input, static_cast<size_t>(search_begin_input_len));
        int visits = 0;
        bool begin_ok = false;
        bool hit_terminal = false;
        int begin_fail_count = 0;
        int begin_last_error = 0;
        int chosen = mcts.search(root_obs, candidates, sbi, *g_live_scorer, &visits, &begin_ok, &hit_terminal,
                                  &begin_fail_count, &begin_last_error);
        if (out_begin_fail_count) *out_begin_fail_count = begin_fail_count;
        if (out_begin_last_error) *out_begin_last_error = begin_last_error;
        if (out_search_begin_ok) *out_search_begin_ok = begin_ok ? 1 : 0;
        if (out_visits) *out_visits = visits;
        if (out_hit_terminal_reward) *out_hit_terminal_reward = hit_terminal ? 1 : 0;
        if (out_mcts_index) *out_mcts_index = chosen;
        if (chosen >= 0) {
          final_choice = {chosen};
        }
        // else: `final_choice` stays the plain-greedy result computed above --
        // the same safety net as dragapult_policy_v11.py's
        // `_macro_lookahead_choice` returning None.
      }
      // Fewer than 2 surviving candidates: every alternative was one V6
      // itself vetoed -- searching would only create chances to override a
      // correct greedy pick with noise. Play greedy.
    }

    int n = std::min(static_cast<int>(final_choice.size()), out_indices_cap);
    for (int i = 0; i < n; ++i) out_indices[i] = final_choice[static_cast<size_t>(i)];
    *out_count = n;
    return 0;
  } catch (...) {
    return 13;
  }
}

}  // extern "C"
