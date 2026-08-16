// C++ port of src/ml/vectorizer.py's ObservationVectorizer -- MUST stay
// feature-for-feature identical (same order, same MISSING sentinel, same
// None-handling) to what B1's model was trained on. 87 features:
//   GLOBAL(11) + SELECT(8) + self PLAYER(34) + opp PLAYER(34),
//   PLAYER = active POKEMON(19) + bench aggregates(5) + counts(5) + status(5).
//
// Deliberate deviations from the Python original, both constant-valued in
// the training data and therefore safe:
//   - prize_revealed_count (self and opp) is forced to 0.0: in training
//     (real acting-player observations) prizes are face-down (None) until
//     taken, so this feature was ~always 0; inside the SEARCH SANDBOX the
//     determinized prize guesses would wrongly count as "revealed" if we
//     counted non-null entries.
//   - select_present is always 1.0 (we only evaluate decision nodes).
#pragma once

#include <vector>

#include "card_data.hpp"
#include "observation.hpp"

namespace v20 {

constexpr float kVecMissing = -1.0f;
constexpr int kVecFeatureCount = 87;

inline void vectorize_pokemon(const v17::Pokemon& p, const v17::CardTable& cards, float* out) {
  // POKEMON_FEATURES order: id, hp, maxHp, hp_fraction, appearThisTurn,
  // energy_count, energy_card_count, tool_count, pre_evolution_count,
  // retreat_cost, base_hp, weakness, resistance, energy_type,
  // stage, is_ex, is_mega_ex, is_tera, is_ace_spec
  if (!p.present || p.faceDown) {
    // Python: active None (incl. face-down, which cg.api reports as None)
    for (int i = 0; i < 19; ++i) out[i] = kVecMissing;
    return;
  }
  const v17::CardData& d = cards.card(p.id);
  const bool have_data = d.cardId != 0;
  out[0] = static_cast<float>(p.id);
  out[1] = static_cast<float>(p.hp);
  out[2] = static_cast<float>(p.maxHp);
  out[3] = p.maxHp ? static_cast<float>(p.hp) / static_cast<float>(p.maxHp) : 0.0f;
  out[4] = p.appearThisTurn ? 1.0f : 0.0f;
  out[5] = static_cast<float>(p.energies.size());
  out[6] = static_cast<float>(p.energyCardIds.size());
  out[7] = static_cast<float>(p.toolIds.size());
  out[8] = static_cast<float>(p.preEvoIds.size());
  if (have_data) {
    out[9] = static_cast<float>(d.retreatCost);
    out[10] = static_cast<float>(d.hp);
    out[11] = d.weakness >= 0 ? static_cast<float>(d.weakness) : kVecMissing;
    out[12] = d.resistance >= 0 ? static_cast<float>(d.resistance) : kVecMissing;
    out[13] = static_cast<float>(d.energyType);
    out[14] = d.stage2 ? 2.0f : d.stage1 ? 1.0f : (d.basic ? 0.0f : kVecMissing);
    out[15] = d.ex ? 1.0f : 0.0f;
    out[16] = d.megaEx ? 1.0f : 0.0f;
    out[17] = d.tera ? 1.0f : 0.0f;
    out[18] = d.aceSpec ? 1.0f : 0.0f;
  } else {
    for (int i = 9; i < 19; ++i) out[i] = kVecMissing;
  }
}

// `self_side` selects between the observation's my*/opp* field families --
// the Python original indexes players[yourIndex]/players[1-yourIndex]; our
// Observation has already split them the same way.
inline void vectorize_player(const v17::Observation& o, const v17::CardTable& cards, bool self_side, float* out) {
  const v17::Pokemon& active = self_side ? o.myActive : o.oppActive;
  vectorize_pokemon(active, cards, out);

  const std::vector<v17::Pokemon>& bench = self_side ? o.myBench : o.oppBench;
  float hp_sum = 0.0f, energy_sum = 0.0f, tool_sum = 0.0f;
  for (const auto& p : bench) {
    hp_sum += static_cast<float>(p.hp);
    energy_sum += static_cast<float>(p.energies.size());
    tool_sum += static_cast<float>(p.toolIds.size());
  }
  out[19] = static_cast<float>(bench.size());
  out[20] = hp_sum;
  out[21] = bench.empty() ? 0.0f : hp_sum / static_cast<float>(bench.size());
  out[22] = energy_sum;
  out[23] = tool_sum;

  if (self_side) {
    out[24] = static_cast<float>(o.myHand.size());
    out[25] = static_cast<float>(o.myDeckCount);
    out[26] = static_cast<float>(o.myDiscard.size());
    out[27] = static_cast<float>(o.myPrizeCount);
  } else {
    out[24] = static_cast<float>(o.oppHandCount);
    out[25] = static_cast<float>(o.oppDeckCount);
    out[26] = static_cast<float>(o.oppDiscardCount);
    out[27] = static_cast<float>(o.oppPrizeCount);
  }
  out[28] = 0.0f;  // prize_revealed_count -- see header note

  if (self_side) {
    out[29] = o.myPoisoned ? 1.0f : 0.0f;
    out[30] = o.myBurned ? 1.0f : 0.0f;
    out[31] = o.myAsleep ? 1.0f : 0.0f;
    out[32] = o.myParalyzed ? 1.0f : 0.0f;
    out[33] = o.myConfused ? 1.0f : 0.0f;
  } else {
    out[29] = o.oppPoisoned ? 1.0f : 0.0f;
    out[30] = o.oppBurned ? 1.0f : 0.0f;
    out[31] = o.oppAsleep ? 1.0f : 0.0f;
    out[32] = o.oppParalyzed ? 1.0f : 0.0f;
    out[33] = o.oppConfused ? 1.0f : 0.0f;
  }
}

// Fills out[0..86]. Perspective: "self" is the observation's ACTING player
// (obs.myIndex), matching how training rows were built -- the caller maps
// the returned P(win) to the root player's perspective.
inline void vectorize_observation(const v17::Observation& o, const v17::CardTable& cards, float* out) {
  // GLOBAL(11)
  out[0] = static_cast<float>(o.turn);
  out[1] = static_cast<float>(o.turnActionCount);
  out[2] = static_cast<float>(o.myIndex);
  out[3] = o.firstPlayer >= 0 ? static_cast<float>(o.firstPlayer) : kVecMissing;
  out[4] = o.supporterPlayed ? 1.0f : 0.0f;
  out[5] = o.stadiumPlayed ? 1.0f : 0.0f;
  out[6] = o.energyAttached ? 1.0f : 0.0f;
  out[7] = o.retreated ? 1.0f : 0.0f;
  out[8] = static_cast<float>(o.result);  // Python: _n(result, MISSING); result is -1 when unfinished, matching MISSING
  out[9] = o.stadiumCardId != 0 ? static_cast<float>(o.stadiumCardId) : kVecMissing;
  out[10] = static_cast<float>(o.looking.size());
  // SELECT(8)
  out[11] = 1.0f;
  out[12] = o.selectType >= 0 ? static_cast<float>(o.selectType) : kVecMissing;
  out[13] = o.context >= 0 ? static_cast<float>(o.context) : kVecMissing;
  out[14] = static_cast<float>(o.minCount);
  out[15] = static_cast<float>(o.maxCount);
  out[16] = static_cast<float>(o.options.size());
  out[17] = static_cast<float>(o.remainDamageCounter);
  out[18] = static_cast<float>(o.remainEnergyCost);
  // self(34) + opp(34)
  vectorize_player(o, cards, /*self_side=*/true, out + 19);
  vectorize_player(o, cards, /*self_side=*/false, out + 19 + 34);
}

}  // namespace v20
