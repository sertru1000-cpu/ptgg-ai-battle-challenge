// Block A1.5: deck-agnostic policy driving the OPPONENT's decisions inside
// MCTS rollouts.
//
// Why this exists: A1 (opponent_model.py + oppHiddenPool) gives the simulated
// opponent the right CARDS, but V17/V18-A1 still drove their DECISIONS with
// V6Scorer -- a heuristic specialized for OUR Dragapult deck (its hand_score
// knows our card ids and scores foreign Kangaskhan/Grimmsnarl cards at
// 0/defaults), so the simulated opponent held the right deck but played it
// like a confused Dragapult pilot. This policy scores options using only
// generic signals (damage, KO, prize value, stage, energy counts) available
// from the C++ CardTable -- a trimmed line-for-line port of
// src/agents/generic_policy_agent.py's band system (the SAME policy that
// pilots the meta decks in the gauntlet, so rollouts now model the gauntlet
// opponent with the matching policy class). Trimmings vs the Python original,
// deliberate: no card-text keyword reads (skill text isn't in the C++
// CardTable; supporters/items get flat in-band scores instead) and no
// IS_FIRST special case (never occurs mid-rollout).
//
// Used ONLY for nodes where the acting player != the root decision-maker
// (mcts.hpp::simulate_one routes on obs.myIndex) -- our own side keeps the
// full V6Scorer. Side benefit: the V6 scratch scorer's cross-call MAIN-state
// (plan_a_/plan_b_/use_support_) is no longer polluted by opponent-board
// decisions, and recompute_deck_counts' our-deck-minus-their-visible garbage
// on opponent-perspective nodes (a pre-existing V17 inconsistency) stops
// influencing anything, since this policy never reads deckCounts.
#pragma once

#include <algorithm>
#include <vector>

#include "card_data.hpp"
#include "observation.hpp"
#include "v6_heuristic.hpp"  // enums:: + V6Scorer::select_top (static)

namespace v17 {

namespace generic_bands {
// Mirrors generic_policy_agent.py's BAND_SCORE exactly.
constexpr double kWinningAttack = 1000000.0;
constexpr double kPreventLoss = 500000.0;
constexpr double kGuaranteedKo = 200000.0;
constexpr double kPrizeEfficientAttack = 50000.0;
constexpr double kSetupEvolution = 20000.0;
constexpr double kEnergyAcceleration = 10000.0;
constexpr double kDrawConsistency = 8000.0;
constexpr double kBoardDevelopment = 5000.0;
constexpr double kFallback = 0.0;

// Option/context ids the v6 enums namespace doesn't define (checked against
// cg/api.py's IntEnums).
constexpr int OPT_NO = 2, OPT_TOOL_CARD = 4, OPT_DISCARD = 11, OPT_END = 14, OPT_SKILL = 15,
              OPT_SPECIAL_CONDITION = 16;
constexpr int CTX_TO_FIELD = 6;
}  // namespace generic_bands

class GenericOpponentPolicy {
 public:
  explicit GenericOpponentPolicy(const CardTable& cards) : cards_(cards) {}

  std::vector<int> choose(const Observation& obs) const {
    std::vector<double> scores(obs.options.size(), generic_bands::kFallback);
    for (size_t i = 0; i < obs.options.size(); ++i) {
      scores[i] = score_option(obs, obs.options[i]);
    }
    return V6Scorer::select_top(obs, scores);
  }

 private:
  const CardTable& cards_;

  static int prize_value(const CardData& d) { return d.megaEx ? 3 : d.ex ? 2 : 1; }

  // generic_policy_agent.py's estimate_damage: base damage with a simple x2
  // weakness / -20 resistance model (approximate by design -- affects
  // scoring only, never legality).
  int estimate_damage(const AttackData& attack, const CardData& attacker, const CardData& defender) const {
    int dmg = attack.damage;
    if (defender.weakness >= 0 && defender.weakness == attacker.energyType) dmg *= 2;
    if (defender.resistance >= 0 && defender.resistance == attacker.energyType) dmg = std::max(0, dmg - 20);
    return dmg;
  }

  // Minimal get_card-equivalent for the zones this policy actually scores.
  // Returns the referenced Pokemon (active/bench zones) or nullptr.
  const Pokemon* resolve_pokemon(const Observation& obs, int area, int index, int player_index) const {
    const bool mine = (player_index < 0) || (player_index == obs.myIndex);
    if (area == enums::AREA_ACTIVE) {
      const Pokemon& p = mine ? obs.myActive : obs.oppActive;
      return p.present ? &p : nullptr;
    }
    if (area == enums::AREA_BENCH) {
      const std::vector<Pokemon>& bench = mine ? obs.myBench : obs.oppBench;
      if (index >= 0 && static_cast<size_t>(index) < bench.size()) return &bench[static_cast<size_t>(index)];
    }
    return nullptr;
  }

  // Card-id resolution for hand/discard/deck-facing/looking/prize zones (the
  // acting player's own zones -- exactly what this policy needs).
  int resolve_card_id(const Observation& obs, int area, int index) const {
    auto pick = [&](const std::vector<Card>& zone) -> int {
      if (index >= 0 && static_cast<size_t>(index) < zone.size()) return zone[static_cast<size_t>(index)].id;
      return 0;
    };
    if (area == enums::AREA_HAND) return pick(obs.myHand);
    if (area == enums::AREA_DISCARD) return pick(obs.myDiscard);
    if (area == enums::AREA_DECK) return pick(obs.selectDeck);
    if (area == enums::AREA_LOOKING) return pick(obs.looking);
    if (area == enums::AREA_PRIZE) return pick(obs.myPrizeCards);
    return 0;
  }

  double score_option(const Observation& obs, const Option& o) const {
    using namespace generic_bands;
    const int t = o.type;

    if (t == OPT_END || t == OPT_NO || t == OPT_DISCARD) return kFallback;
    if (t == enums::OPT_YES) return kSetupEvolution;  // accept beneficial yes/no by default

    if (t == enums::OPT_ATTACK) {
      const AttackData& attack = cards_.attack(o.attackId);
      if (!obs.myActive.present || !obs.oppActive.present || attack.attackId == 0) {
        return kPrizeEfficientAttack;
      }
      const CardData& attacker = cards_.card(obs.myActive.id);
      const CardData& defender = cards_.card(obs.oppActive.id);
      const int dmg = estimate_damage(attack, attacker, defender);
      const bool is_ko = dmg >= obs.oppActive.hp;
      if (is_ko && prize_value(defender) >= obs.myPrizeCount) return kWinningAttack + dmg;
      if (is_ko) return kGuaranteedKo + dmg;
      return kPrizeEfficientAttack + dmg;
    }

    if (t == enums::OPT_RETREAT) {
      if (obs.myActive.present) {
        const double hp_frac =
            static_cast<double>(obs.myActive.hp) / static_cast<double>(std::max(1, obs.myActive.maxHp));
        if (hp_frac <= 0.34 || obs.myAsleep || obs.myParalyzed || obs.myConfused) return kPreventLoss;
      }
      return kFallback - 1.0;
    }

    if (t == enums::OPT_EVOLVE) {
      double bonus = 0.0;
      const int evolved_id = resolve_card_id(obs, o.area, o.index);
      if (evolved_id != 0) {
        const CardData& d = cards_.card(evolved_id);
        bonus = d.stage2 ? 300.0 : d.stage1 ? 150.0 : 0.0;
      }
      const Pokemon* target = resolve_pokemon(obs, o.inPlayArea, o.inPlayIndex, obs.myIndex);
      if (target) bonus += static_cast<double>(target->energies.size());
      return kSetupEvolution + bonus;
    }

    if (t == enums::OPT_ATTACH) {
      double bonus = 0.0;
      const int card_id = resolve_card_id(obs, o.area, o.index);
      if (card_id != 0 && cards_.card(card_id).cardType == enums::CT_TOOL) bonus += 500.0;
      if (o.inPlayArea == enums::AREA_ACTIVE) bonus += 200.0;
      const Pokemon* target = resolve_pokemon(obs, o.inPlayArea, o.inPlayIndex, obs.myIndex);
      if (target) bonus -= 50.0 * static_cast<double>(target->energies.size());
      return kEnergyAcceleration + bonus;
    }

    if (t == enums::OPT_ABILITY) {
      if (obs.myDeckCount <= 3) return kFallback;  // deck-out risk
      return kDrawConsistency;
    }

    if (t == enums::OPT_PLAY) {
      const int card_id = resolve_card_id(obs, enums::AREA_HAND, o.index);
      if (card_id == 0) return kBoardDevelopment;
      const CardData& d = cards_.card(card_id);
      if (d.cardType == enums::CT_POKEMON) return kSetupEvolution - 100.0;
      if (d.cardType == enums::CT_SUPPORTER) return kDrawConsistency + 500.0;
      if (d.cardType == enums::CT_TOOL) return kBoardDevelopment + 200.0;
      // stadium / item / energy-as-item: plain board development
      return kBoardDevelopment;
    }

    if (t == enums::OPT_CARD) {
      const int ctx = obs.context;
      if (ctx == enums::CTX_SWITCH || ctx == enums::CTX_TO_ACTIVE || ctx == enums::CTX_SETUP_ACTIVE_POKEMON) {
        const Pokemon* p = resolve_pokemon(obs, o.area, o.index, o.playerIndex);
        if (p && (o.playerIndex < 0 || o.playerIndex == obs.myIndex)) {
          const CardData& d = cards_.card(p->id);
          const double stage_bonus = d.stage2 ? 300.0 : d.stage1 ? 150.0 : 0.0;
          return kSetupEvolution + stage_bonus + p->hp + 50.0 * static_cast<double>(p->energies.size());
        }
        // Hand/bench-list selects during setup reference cards, not in-play
        // Pokemon -- prefer higher-HP basics via the card table.
        const int card_id = resolve_card_id(obs, o.area, o.index);
        if (card_id != 0) return kSetupEvolution + cards_.card(card_id).hp;
        return kFallback;
      }
      if (ctx == enums::CTX_SETUP_BENCH_POKEMON || ctx == enums::CTX_TO_BENCH || ctx == generic_bands::CTX_TO_FIELD) {
        const int card_id = resolve_card_id(obs, o.area, o.index);
        if (card_id != 0) {
          const CardData& d = cards_.card(card_id);
          return kBoardDevelopment + (d.stage2 ? 200.0 : d.stage1 ? 100.0 : 0.0);
        }
        return kBoardDevelopment;
      }
      if (ctx == enums::CTX_DAMAGE_COUNTER || ctx == enums::CTX_DAMAGE_COUNTER_ANY) {
        const Pokemon* p = resolve_pokemon(obs, o.area, o.index, o.playerIndex);
        if (p && o.playerIndex >= 0 && o.playerIndex != obs.myIndex) {
          return kGuaranteedKo - p->hp + 50.0 * prize_value(cards_.card(p->id));
        }
        return kFallback;
      }
      if (ctx == enums::CTX_DISCARD) {
        const int card_id = resolve_card_id(obs, o.area, o.index);
        if (card_id == 0) return kFallback;
        const int ct = cards_.card(card_id).cardType;
        // Least-valuable-first: basic energy < special energy < item < tool <
        // pokemon/stadium < supporter (generic_policy_agent.py's rank table).
        int rank = 3;
        if (ct == enums::CT_BASIC_ENERGY) rank = 0;
        else if (ct == enums::CT_SPECIAL_ENERGY) rank = 1;
        else if (ct == enums::CT_TOOL) rank = 3;
        else if (ct == enums::CT_POKEMON) rank = 4;
        else if (ct == enums::CT_SUPPORTER) rank = 5;
        else rank = 2;  // item / stadium-as-item flows
        return kFallback + (5 - rank) * 10.0;
      }
      if (ctx == enums::CTX_ATTACH_FROM) {
        const Pokemon* p = resolve_pokemon(obs, o.area, o.index, o.playerIndex);
        if (p) return kEnergyAcceleration - 50.0 * static_cast<double>(p->energies.size());
        return kEnergyAcceleration;
      }
      if (ctx == enums::CTX_TO_HAND) return kDrawConsistency;
      return kFallback;
    }

    if (t == enums::OPT_ENERGY || t == enums::OPT_ENERGY_CARD || t == generic_bands::OPT_TOOL_CARD) {
      return kEnergyAcceleration;
    }
    if (t == enums::OPT_NUMBER) return static_cast<double>(std::max(0, o.number));
    if (t == generic_bands::OPT_SKILL) return kDrawConsistency;
    if (t == generic_bands::OPT_SPECIAL_CONDITION) return kPreventLoss;

    return kFallback;  // unmodeled option type: safe neutral, never a crash
  }
};

}  // namespace v17
