// C++ port of src/ml/bc_features.py's option_features -- MUST stay
// feature-for-feature identical to what the BC ranker was trained on.
// Known, accepted deviation: options referencing OPPONENT hand/discard
// cards cannot be resolved from our Observation (their card lists aren't
// carried) and fall back to the same -1 sentinels Python's exception path
// produced; verified immaterial by the live parity test in the smoke
// harness.
#pragma once

#include "card_data.hpp"
#include "observation.hpp"
#include "v6_heuristic.hpp"  // enums::

namespace v26 {

inline constexpr int kBcOptionFeatureCount = 16;

inline void bc_option_features(const v17::Observation& o, const v17::Option& opt,
                               const v17::CardTable& cards, float* out) {
  using namespace v17::enums;
  const bool player_is_self = (opt.playerIndex < 0) || (opt.playerIndex == o.myIndex);
  out[0] = static_cast<float>(opt.type);
  out[1] = opt.area >= 0 ? static_cast<float>(opt.area) : -1.0f;
  out[2] = opt.index >= 0 ? static_cast<float>(opt.index) : -1.0f;
  out[3] = player_is_self ? 1.0f : 0.0f;
  out[4] = opt.count >= 0 ? static_cast<float>(opt.count) : -1.0f;
  out[5] = opt.number >= 0 ? static_cast<float>(opt.number) : -1.0f;
  out[6] = opt.attackId >= 0 ? static_cast<float>(opt.attackId) : -1.0f;
  float atk_dmg = -1.0f, atk_cost = -1.0f;
  if (opt.attackId >= 0) {
    const v17::AttackData& a = cards.attack(opt.attackId);
    if (a.attackId != 0) {
      atk_dmg = static_cast<float>(a.damage);
      atk_cost = static_cast<float>(a.energies.size());
    }
  }
  out[7] = atk_dmg;
  out[8] = atk_cost;
  out[9] = opt.inPlayArea >= 0 ? static_cast<float>(opt.inPlayArea) : -1.0f;

  // Card resolution (bc_features.py: get_card on (area,index) else HAND for
  // PLAY). Own zones only -- see header note.
  int card_id = -1;
  auto pick = [&](const std::vector<v17::Card>& zone, int idx) {
    if (idx >= 0 && static_cast<size_t>(idx) < zone.size()) card_id = zone[static_cast<size_t>(idx)].id;
  };
  if (opt.area >= 0 && opt.index >= 0) {
    if (opt.area == AREA_ACTIVE) {
      const v17::Pokemon& p = player_is_self ? o.myActive : o.oppActive;
      if (p.present && !p.faceDown) card_id = p.id;
    } else if (opt.area == AREA_BENCH) {
      const std::vector<v17::Pokemon>& b = player_is_self ? o.myBench : o.oppBench;
      if (static_cast<size_t>(opt.index) < b.size() && b[static_cast<size_t>(opt.index)].present) {
        card_id = b[static_cast<size_t>(opt.index)].id;
      }
    } else if (player_is_self) {
      if (opt.area == AREA_HAND) pick(o.myHand, opt.index);
      else if (opt.area == AREA_DISCARD) pick(o.myDiscard, opt.index);
      else if (opt.area == AREA_DECK) pick(o.selectDeck, opt.index);
      else if (opt.area == AREA_LOOKING) pick(o.looking, opt.index);
      else if (opt.area == AREA_PRIZE) pick(o.myPrizeCards, opt.index);
    }
  } else if (opt.type == OPT_PLAY && opt.index >= 0) {
    pick(o.myHand, opt.index);
  }

  float ct = -1.0f, chp = -1.0f, cstage = -1.0f, cex = -1.0f, cpoke = -1.0f;
  if (card_id > 0) {
    const v17::CardData& d = cards.card(card_id);
    if (d.cardId != 0) {
      ct = static_cast<float>(d.cardType);
      chp = static_cast<float>(d.hp);
      cstage = d.stage2 ? 2.0f : d.stage1 ? 1.0f : 0.0f;
      cex = (d.ex || d.megaEx) ? 1.0f : 0.0f;
      cpoke = (d.cardType == CT_POKEMON) ? 1.0f : 0.0f;
    }
  }
  out[10] = card_id > 0 ? static_cast<float>(card_id) : -1.0f;
  out[11] = ct;
  out[12] = chp;
  out[13] = cstage;
  out[14] = cex;
  out[15] = cpoke;
}

}  // namespace v26
