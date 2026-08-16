// Static card/attack metadata tables -- the C++ analogue of V6's
// `_card_table`/`_attack_table` (dragapult_policy_v6.py: `{c.cardId: c for c
// in all_card_data()}` / `{a.attackId: a for a in all_attack()}`). Parsed
// ONCE at v17_init() time from the engine's `AllCard()`/`AllAttack()` exports
// (not inside the hot MCTS loop -- this is a startup cost, same as the
// Python agents already pay via `all_card_data()`/`all_attack()` at import
// time), using the same json_extract.hpp helpers as everywhere else.
#pragma once

#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "json_extract.hpp"

namespace v17 {

struct CardData {
  int cardId = 0;
  std::string name;
  int cardType = -1;      // CardType
  int retreatCost = 0;
  int hp = 0;
  int weakness = -1;      // EnergyType, -1 if null
  int resistance = -1;    // EnergyType, -1 if null
  int energyType = 0;     // EnergyType
  bool basic = false;
  bool stage1 = false;
  bool stage2 = false;
  bool ex = false;
  bool megaEx = false;
  bool tera = false;
  bool aceSpec = false;
  std::vector<int> attacks;  // attack IDs
};

struct AttackData {
  int attackId = 0;
  std::string name;
  int damage = 0;
  std::vector<int> energies;  // EnergyType cost list
};

class CardTable {
 public:
  void load(const std::string& all_card_json, const std::string& all_attack_json) {
    for (auto item : jx::array_items(all_card_json)) {
      CardData c;
      c.cardId = jx::to_int(jx::object_member(item, "cardId"), 0);
      c.name = jx::to_unescaped_string(jx::object_member(item, "name"), "");
      c.cardType = jx::to_int(jx::object_member(item, "cardType"), -1);
      c.retreatCost = jx::to_int(jx::object_member(item, "retreatCost"), 0);
      c.hp = jx::to_int(jx::object_member(item, "hp"), 0);
      c.weakness = jx::to_int(jx::object_member(item, "weakness"), -1);
      c.resistance = jx::to_int(jx::object_member(item, "resistance"), -1);
      c.energyType = jx::to_int(jx::object_member(item, "energyType"), 0);
      c.basic = jx::to_bool(jx::object_member(item, "basic"), false);
      c.stage1 = jx::to_bool(jx::object_member(item, "stage1"), false);
      c.stage2 = jx::to_bool(jx::object_member(item, "stage2"), false);
      c.ex = jx::to_bool(jx::object_member(item, "ex"), false);
      c.megaEx = jx::to_bool(jx::object_member(item, "megaEx"), false);
      c.tera = jx::to_bool(jx::object_member(item, "tera"), false);
      c.aceSpec = jx::to_bool(jx::object_member(item, "aceSpec"), false);
      auto attacks = jx::object_member(item, "attacks");
      if (attacks.has_value()) {
        for (auto a : jx::array_items(*attacks)) c.attacks.push_back(jx::to_int(a, 0));
      }
      cards_[c.cardId] = std::move(c);
    }

    for (auto item : jx::array_items(all_attack_json)) {
      AttackData a;
      a.attackId = jx::to_int(jx::object_member(item, "attackId"), 0);
      a.name = jx::to_unescaped_string(jx::object_member(item, "name"), "");
      a.damage = jx::to_int(jx::object_member(item, "damage"), 0);
      auto energies = jx::object_member(item, "energies");
      if (energies.has_value()) {
        for (auto e : jx::array_items(*energies)) a.energies.push_back(jx::to_int(e, 0));
      }
      attacks_[a.attackId] = std::move(a);
    }
  }

  // Returns a default-constructed CardData (cardId 0, empty name) for an
  // unknown id rather than throwing -- callers that index this table with a
  // card id sourced from live engine data should never hit this, but a
  // silent-default is safer than a crash mid-MCTS-rollout given the engine's
  // own documented "new fields/cards may be appended" schema-evolution note.
  const CardData& card(int id) const {
    static const CardData kEmpty;
    auto it = cards_.find(id);
    return it == cards_.end() ? kEmpty : it->second;
  }

  const AttackData& attack(int id) const {
    static const AttackData kEmpty;
    auto it = attacks_.find(id);
    return it == attacks_.end() ? kEmpty : it->second;
  }

  bool has_card(int id) const { return cards_.find(id) != cards_.end(); }

 private:
  std::unordered_map<int, CardData> cards_;
  std::unordered_map<int, AttackData> attacks_;
};

}  // namespace v17
