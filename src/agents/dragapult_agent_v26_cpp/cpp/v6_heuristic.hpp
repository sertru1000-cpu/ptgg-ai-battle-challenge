// Faithful C++ port of src/agents/dragapult_policy_v6.py's DragapultPolicy
// (BALANCED weights) -- the exact scoring math this task requires (Objective
// 2: "EXACT mathematical heuristic extracted from V6"). Ported statement-by-
// statement against that file (read in full before writing this), preserving
// its exact evaluation order, including the handful of places where a value
// genuinely persists across calls (plan_a/plan_b/use_support -- only reset
// inside the `context == MAIN` branch, exactly like the Python instance
// attributes they mirror) and one apparent no-op branch in the original
// (ENERGY_CARD/ENERGY scoring reads the POKEMON's cardType, not the energy
// card's -- preserved verbatim rather than "fixed", per this task's fidelity
// requirement).
//
// Used in two roles (see ../README.md): (1) the MCTS rollout/default policy
// -- `choose()` drives every simulated decision after the root; (2)
// `state_value()` (ported from src/agents/dragapult_policy_v11.py's
// `post_action_state_value`, itself built on V6's own `pokemon_score`) is the
// leaf/backup value MCTS actually optimizes.
//
// One V6Scorer instance persists for the whole process (the "live" decision
// maker, exactly like Python's one long-lived DragapultPolicy instance).
// MCTS copy-constructs a disposable scratch instance per simulated branch
// (V6Scorer has no owning resources -- CardTable is a const reference to a
// single process-lifetime table -- so the implicit copy constructor is
// correct and cheap), mirroring V11's `copy.deepcopy(self)` +
// `_rollout_mode` pattern for the exact same reason: a rollout must never
// mutate the real decision-maker's plan_a_/plan_b_/use_support_ state.
#pragma once

#include <algorithm>
#include <functional>
#include <unordered_map>
#include <vector>

#include "card_data.hpp"
#include "observation.hpp"

namespace v17 {

struct PolicyWeights {
  double prize_value_multiplier = 1.0;
  bool defensive_retreat_enabled = true;
  double defensive_retreat_hp_fraction = 1.0;
  double preservation_bias = 0.1;
  double switch_risk_tolerance = 1.0;
};

// policy_weights.py's BALANCED profile -- the one V6/V11 actually play.
inline PolicyWeights balanced_weights() {
  return PolicyWeights{1.0, true, 1.0, 0.1, 1.0};
}

struct AttackPlan {
  int attack = -1;
  std::vector<int> counter;
};

// --- cg.api enum values this scorer dispatches on (cg/api.py is ground truth) ---
namespace enums {
constexpr int AREA_DECK = 1, AREA_HAND = 2, AREA_DISCARD = 3, AREA_ACTIVE = 4, AREA_BENCH = 5, AREA_PRIZE = 6,
              AREA_STADIUM = 7, AREA_LOOKING = 12;
constexpr int CT_POKEMON = 0, CT_TOOL = 2, CT_SUPPORTER = 3, CT_BASIC_ENERGY = 5, CT_SPECIAL_ENERGY = 6;
constexpr int OPT_NUMBER = 0, OPT_YES = 1, OPT_CARD = 3, OPT_ENERGY_CARD = 5, OPT_ENERGY = 6, OPT_PLAY = 7,
              OPT_ATTACH = 8, OPT_EVOLVE = 9, OPT_ABILITY = 10, OPT_RETREAT = 12, OPT_ATTACK = 13;
constexpr int CTX_MAIN = 0, CTX_SETUP_ACTIVE_POKEMON = 1, CTX_SETUP_BENCH_POKEMON = 2, CTX_SWITCH = 3,
              CTX_TO_ACTIVE = 4, CTX_TO_BENCH = 5, CTX_TO_HAND = 7, CTX_DISCARD = 8, CTX_DAMAGE_COUNTER = 13,
              CTX_DAMAGE_COUNTER_ANY = 14, CTX_ATTACH_FROM = 21, CTX_IS_FIRST = 41;
}  // namespace enums

class V6Scorer {
 public:
  explicit V6Scorer(const CardTable& cards, PolicyWeights weights = balanced_weights())
      : cards_(cards), weights_(weights) {}
  V6Scorer(const V6Scorer&) = default;

  // Decklist constants (dragapult_policy_v6.py module-level constants).
  static constexpr int Dreepy = 119, Drakloak = 120, Dragapult_ex = 121, Fezandipiti_ex = 140, Latias_ex = 184,
                        Budew = 235, Meowth_ex = 1071, Rare_Candy = 1079, Unfair_Stamp = 1080,
                        Buddy_Buddy_Poffin = 1086, Night_Stretcher = 1097, Crushing_Hammer = 1120,
                        Ultra_Ball = 1121, Poke_Pad = 1152, Lucky_Helmet = 1156, Boss_Orders = 1182,
                        Crispin = 1198, Brock_Scouting = 1210, Lillie_Determination = 1227,
                        Team_Rocket_Watchtower = 1256, Basic_Fire_Energy = 2, Basic_Psychic_Energy = 5,
                        // V25: leader-list ("Munkidori package") additions -- port of
                        // dragapult_policy_v19.py's constants. Removed cards' constants
                        // above stay; their branches are inert at 0 copies.
                        Basic_Dark_Energy = 7, Munkidori = 112, Judge = 1213, Dawn = 1231,
                        Jamming_Tower = 1246;
  static constexpr double UNNECESSARY = -10000000.0;
  static constexpr int PHANTOM_DIVE_ATTACK_ID = 154;

  // The full per-option score vector for `obs.options` -- direct C++
  // translation of dragapult_policy_v6.py's `agent()` method body (minus the
  // deck-declare/IS_FIRST short-circuits, both handled in Python before this
  // is ever reached -- see main_v17.py).
  std::vector<double> raw_scores(const Observation& obs);

  // dragapult_policy_v6.py's select_top(): sorts by score descending
  // (stable, matching Python's stable sort), returns the top maxCount
  // indices, with the same TO_BENCH/SETUP_BENCH_POKEMON "allow declining
  // below maxCount on an all-negative field" quirk preserved.
  static std::vector<int> select_top(const Observation& obs, const std::vector<double>& scores);

  // raw_scores() + select_top() -- V6's complete plain-greedy decision.
  // This is both the MCTS rollout/default policy and the ultimate fallback
  // if a root-level MCTS search cannot complete even one full evaluation.
  std::vector<int> choose(const Observation& obs) {
    std::vector<double> scores = raw_scores(obs);
    return select_top(obs, scores);
  }

  // Ported unchanged from dragapult_policy_v11.py's `post_action_state_value`
  // (itself built on V6's own `pokemon_score`) -- the MCTS leaf/backup value.
  //
  // `perspective_index` is the ROOT decision-maker's player index -- NOT
  // necessarily `obs.myIndex`. Decisions alternate between players during a
  // rollout (the engine's `yourIndex` tracks whoever is CURRENTLY acting,
  // which is frequently the opponent by the time a rollout ends), so
  // `obs.myActive`/`obs.myBench` may actually describe the OPPONENT's board
  // by the final step. This function swaps sides internally whenever
  // `perspective_index != obs.myIndex` so the returned value is always "how
  // good is this outcome for the player who owns the real decision this
  // whole search is for" -- getting this backwards would make MCTS
  // systematically prefer moves that are good for the OPPONENT whenever the
  // final rollout step happened to land on an opponent decision, which is a
  // silent, high-impact scoring-sign bug, not a cosmetic one.
  double state_value(const Observation& obs, int perspective_index) const;

  double pokemon_score(const Pokemon& p, bool is_attack_damage) const;

 private:
  const CardTable& cards_;
  PolicyWeights weights_;

  // Cross-call state -- ONLY mutated when context == MAIN, exactly mirroring
  // the Python instance attributes of the same name (see file header).
  AttackPlan plan_a_;
  AttackPlan plan_b_;
  bool can_switch_ = false;
  bool can_attack_ = false;
  bool can_main_attack_ = false;
  int use_support_ = 0;

  int prize_count(const Pokemon& p, bool is_attack_damage) const;
  static bool no_damage_dex(int id) { return id == 158 || id == 207 || id == 330 || id == 345; }
  static bool no_damage_counter_target(const Pokemon& p) {
    if (p.id == 28 || p.id == 199 || p.id == 203 || p.id == 207 || p.id == 362 || p.id == 1136) return true;
    for (int eid : p.energyCardIds) {
      if (eid == 11 || eid == 20) return true;
    }
    return false;
  }

  void main_option_proc(const Observation& obs, int damage, bool bench_attacker);
  bool wants_defensive_retreat(const Pokemon& my_active, const Pokemon& op_active, bool can_attack_now) const;
  double board_value_side(const Pokemon& active, const std::vector<Pokemon>& bench) const;

  // Returns nullptr for a face-down Pokemon, not just an absent one --
  // matches Python's `get_card()`, which returns the raw slot contents and
  // is `None` for BOTH "no active Pokemon at all" (empty list) AND "active
  // Pokemon present but face-down" (a `None` array element, cg/api.py:
  // "None if the card is facedown") -- V6 never distinguishes the two
  // cases, always treating both as `is None`. Only `obs.oppActive`/
  // `obs.oppBench` can ever be face-down (we always see our own board in
  // full), but the check costs nothing to apply uniformly.
  const Pokemon* get_pokemon(const Observation& obs, int area, int index, int player_index) const {
    bool mine = (player_index == obs.myIndex);
    const Pokemon* p = nullptr;
    if (area == enums::AREA_ACTIVE) {
      p = mine ? &obs.myActive : &obs.oppActive;
    } else if (area == enums::AREA_BENCH) {
      const std::vector<Pokemon>& bench = mine ? obs.myBench : obs.oppBench;
      if (index >= 0 && static_cast<size_t>(index) < bench.size()) p = &bench[static_cast<size_t>(index)];
    }
    if (p && p->present && !p->faceDown) return p;
    return nullptr;
  }

  // Matches Python's get_card() (src/agents/common.py) exactly: DECK/
  // PRIZE/LOOKING are resolved directly from their own zone, independent of
  // `player_index` (that field isn't consulted for them at all there --
  // each is always OUR OWN visible zone), while HAND/DISCARD go through the
  // owning player's zone. A PRIZE/LOOKING slot holding a face-down/
  // unrevealed card is represented as id==0 (see v17_abi.h) -- treated as
  // "not found", matching Python's `ps.prize[index]` being `None` there.
  const Card* get_card_ref(const Observation& obs, int area, int index, int player_index) const {
    if (area == enums::AREA_DECK) {
      if (index >= 0 && static_cast<size_t>(index) < obs.selectDeck.size()) return &obs.selectDeck[static_cast<size_t>(index)];
      return nullptr;
    }
    if (area == enums::AREA_PRIZE) {
      if (index >= 0 && static_cast<size_t>(index) < obs.myPrizeCards.size()) {
        const Card& c = obs.myPrizeCards[static_cast<size_t>(index)];
        return c.id != 0 ? &c : nullptr;
      }
      return nullptr;
    }
    if (area == enums::AREA_LOOKING) {
      if (index >= 0 && static_cast<size_t>(index) < obs.looking.size()) {
        const Card& c = obs.looking[static_cast<size_t>(index)];
        return c.id != 0 ? &c : nullptr;
      }
      return nullptr;
    }
    bool mine = (player_index == obs.myIndex);
    if (!mine) return nullptr;  // V6 never CARD-references the opponent's hidden hand/discard by index
    if (area == enums::AREA_HAND) {
      if (index >= 0 && static_cast<size_t>(index) < obs.myHand.size()) return &obs.myHand[static_cast<size_t>(index)];
    } else if (area == enums::AREA_DISCARD) {
      if (index >= 0 && static_cast<size_t>(index) < obs.myDiscard.size()) return &obs.myDiscard[static_cast<size_t>(index)];
    }
    return nullptr;
  }
};

inline double V6Scorer::pokemon_score(const Pokemon& p, bool is_attack_damage) const {
  const CardData& data = cards_.card(p.id);
  // Rebalanced 2026-08-14 (reward-hacking investigation into the
  // MCTS:[PLAY] vs V6:[EVOLVE] pathology, ~11% win rate when diverged in the
  // 80-game post-clip run): prize-count term was 1000x-scaled vs. a mere
  // +130/+250 evolution-stage bonus, so a rollout-visible EX/prize-heavy
  // basic Pokemon could dominate the score against evolving toward a
  // stronger board, even when evolving was clearly better long-term. Only
  // affects V17's OWN internal C++ scorer (this file) -- the actual V6
  // opponent agent in tournament play is pure Python
  // (dragapult_policy_v6.py, a separate, untouched implementation), so this
  // does not change the baseline being played against, only V17's own
  // candidate ranking/rollout evaluation.
  double score = static_cast<double>(prize_count(p, is_attack_damage)) * 300.0 * weights_.prize_value_multiplier;
  score += static_cast<double>(p.energies.size()) * 150.0;
  score += static_cast<double>(p.toolIds.size()) * 100.0;
  if (data.stage2) score += 1000;
  else if (data.stage1) score += 600;
  int id = p.id;
  if (id == 173 || id == 174 || id == 190 || id == 1071) score -= 200;
  if (id == 112 && !p.energies.empty()) score += 300;  // Munkidori
  score += p.hp;
  return score;
}

inline int V6Scorer::prize_count(const Pokemon& p, bool is_attack_damage) const {
  const CardData& data = cards_.card(p.id);
  int count = data.megaEx ? 3 : (data.ex ? 2 : 1);
  if (is_attack_damage) {
    for (int eid : p.energyCardIds) {
      if (eid == 12) count -= 1;  // Legacy Energy
    }
    for (int tid : p.toolIds) {
      if (tid == 1172 && data.name.find("Lillie") != std::string::npos) count -= 1;  // Lillie's Pearl
    }
  }
  return std::max(0, count);
}

inline double V6Scorer::board_value_side(const Pokemon& active, const std::vector<Pokemon>& bench) const {
  double total = 0.0;
  if (active.present && !active.faceDown) total += pokemon_score(active, false);
  for (const auto& p : bench) {
    if (p.present && !p.faceDown) total += pokemon_score(p, false);
  }
  return total;
}

inline double V6Scorer::state_value(const Observation& obs, int perspective_index) const {
  if (obs.result >= 0) {
    if (obs.result == perspective_index) return 1000000.0;
    if (obs.result == 1 - perspective_index) return -1000000.0;
    return 0.0;
  }
  bool same_side = (perspective_index == obs.myIndex);
  const Pokemon& me_active = same_side ? obs.myActive : obs.oppActive;
  const std::vector<Pokemon>& me_bench = same_side ? obs.myBench : obs.oppBench;
  const Pokemon& opp_active = same_side ? obs.oppActive : obs.myActive;
  const std::vector<Pokemon>& opp_bench = same_side ? obs.oppBench : obs.myBench;
  int me_prize = same_side ? obs.myPrizeCount : obs.oppPrizeCount;
  int opp_prize = same_side ? obs.oppPrizeCount : obs.myPrizeCount;
  double prize_term = static_cast<double>(opp_prize - me_prize) * 1000.0 * weights_.prize_value_multiplier;
  return board_value_side(me_active, me_bench) - board_value_side(opp_active, opp_bench) + prize_term;
}

inline bool V6Scorer::wants_defensive_retreat(const Pokemon& my_active, const Pokemon& op_active, bool can_attack_now) const {
  if (!weights_.defensive_retreat_enabled) return false;
  if (can_attack_now) return false;
  if (!my_active.present || !op_active.present || op_active.faceDown) return false;
  if (!cards_.has_card(op_active.id)) return false;
  const CardData& op_card = cards_.card(op_active.id);
  int op_energy_count = static_cast<int>(op_active.energies.size());
  double threshold = my_active.hp * weights_.defensive_retreat_hp_fraction;
  for (int aid : op_card.attacks) {
    const AttackData& atk = cards_.attack(aid);
    if (atk.damage <= 0) continue;  // also naturally skips an unknown attack id (default damage=0)
    if (op_energy_count >= static_cast<int>(atk.energies.size()) && atk.damage >= threshold) return true;
  }
  return false;
}

// Verbatim (list-operation-for-list-operation) port of main_option_proc's
// subset-sum DFS over "which bench Pokemon to also place Phantom Dive's 6
// damage counters on" -- see V6 FIX #1/#2 comments in the .cpp/py source this
// mirrors. Deliberately NOT rewritten into a cleaner recursive form: the
// iterative stack-based traversal order affects nothing observable here
// (every valid subset is still found), but a literal port is far easier to
// audit against the original than a reimplementation would be.
inline void V6Scorer::main_option_proc(const Observation& obs, int damage, bool bench_attacker) {
  can_switch_ = false;
  can_attack_ = false;
  can_main_attack_ = false;
  for (const Option& o : obs.options) {
    if (o.type == enums::OPT_RETREAT) can_switch_ = true;
    else if (o.type == enums::OPT_ATTACK) {
      can_attack_ = true;
      if (o.attackId == PHANTOM_DIVE_ATTACK_ID) can_main_attack_ = true;
    }
  }

  plan_a_.attack = -1;
  plan_a_.counter.clear();
  plan_b_.attack = -1;
  plan_b_.counter.clear();
  if (!can_main_attack_ && !(bench_attacker && can_switch_)) return;
  // Defensive: Python's un-ported equivalent (`op_state.active[0]`) would
  // crash here if the opponent's Active is absent or face-down; there is
  // nothing to plan against either way, so bail out cleanly instead (bench
  // entries are never face-down -- cg/api.py types `bench: list[Pokemon]`,
  // not `list[Pokemon|None]` -- only the single Active slot can be).
  if (!obs.oppActive.present || obs.oppActive.faceDown) return;

  std::vector<Pokemon> cards;
  cards.push_back(obs.oppActive);
  for (const auto& p : obs.oppBench) cards.push_back(p);

  std::vector<std::vector<int>> counter_indices;
  std::vector<int> ci = {0};
  int remain_damage = 60;
  while (!ci.empty()) {
    int index = ci.back();
    int hp = cards[static_cast<size_t>(index)].hp;
    if (remain_damage >= hp) {
      counter_indices.push_back(ci);
      if (index < static_cast<int>(cards.size()) - 1) {
        remain_damage -= hp;
        ci.push_back(index + 1);
        continue;
      }
    }
    if (index == static_cast<int>(cards.size()) - 1) {
      ci.pop_back();
      if (!ci.empty()) remain_damage += cards[static_cast<size_t>(ci.back())].hp;
    }
    if (!ci.empty()) ci.back() += 1;
  }
  counter_indices.push_back({});

  int remain_prize = obs.myPrizeCount;
  double plan_score = 0;
  for (int i = 0; i < static_cast<int>(cards.size()); ++i) {
    const Pokemon& pokemon = cards[static_cast<size_t>(i)];
    int base_prize_count = 0;
    double base_score = pokemon_score(pokemon, true);
    int active_damage;
    if (i == 0 && can_main_attack_) {
      // V6 FIX #2: Phantom Dive never damages the opponent's Active.
      active_damage = 0;
    } else {
      active_damage = no_damage_dex(pokemon.id) ? 0 : damage;
    }
    if (pokemon.hp <= active_damage) {
      base_prize_count += prize_count(pokemon, true);
    } else {
      base_score *= static_cast<double>(active_damage) / static_cast<double>(pokemon.hp);
    }
    std::vector<int> best_indices;
    double max_score = base_score;
    if (remain_prize <= base_prize_count) {
      max_score = 50000;
    } else {
      for (const auto& indices : counter_indices) {
        if (std::find(indices.begin(), indices.end(), i) != indices.end()) continue;
        int prize = base_prize_count;
        double score = base_score;
        for (int index : indices) {
          prize += prize_count(cards[static_cast<size_t>(index)], false);
          score += pokemon_score(cards[static_cast<size_t>(index)], false);
        }
        if (remain_prize <= prize) {
          score = 50000;
        } else if (prize >= 2) {
          if (remain_prize <= 4) score -= 1200;
        } else if (prize == 1) {
          score -= 300;
        } else {
          score += 1200;
        }
        if (max_score < score) {
          max_score = score;
          best_indices = indices;
        }
      }
    }
    if (plan_score < max_score) {
      plan_score = max_score;
      plan_a_.attack = i;
      plan_a_.counter = best_indices;
    }
    if (i == 0) {
      plan_b_.attack = plan_a_.attack;
      plan_b_.counter = plan_a_.counter;
    }
  }
}

}  // namespace v17
