// Recomputes Observation::deckCounts for a simulated MCTS node -- the native
// analogue of dragapult_policy_v6.py's `set_card_counts` (DECK constant
// minus everything currently visible). Used ONLY for nodes built via
// from_search_json (i.e. every node inside the MCTS tree); the ROOT
// observation already carries an exact deckCounts computed in Python by
// literally reusing DragapultPolicy's own bookkeeping (main_v17.py), so this
// is never called on it.
//
// Deliberately simpler than the Python original: V6's `add_card_count` dedupes
// by card `serial` because it scans several OVERLAPPING zone listings
// (hand/discard/bench/active/stadium/looking/select.effect) where the same
// physical card could otherwise be double-subtracted. Here we only subtract
// from disjoint zones (active/bench/hand/discard/stadium) -- a card cannot
// physically be in two of those at once -- so no dedup bookkeeping is needed.
// The one accepted gap: `select.effect` (a card mid-resolution, sometimes not
// yet reflected in any zone listing) is not subtracted, so deckCounts can be
// off by one for the exact instant an effect card is resolving. This affects
// only a few minor hand_score terms (Buddy_Buddy_Poffin/Crispin energy-count
// checks) deep inside rollout branches, never the root decision -- an
// accepted approximation in the same spirit as the preKo/noItem/myPrizeGuess
// snapshot-vs-rederive tradeoff documented in observation.hpp.
#pragma once

#include <unordered_map>
#include <utility>
#include <vector>

#include "observation.hpp"

namespace v17 {

inline void recompute_deck_counts(Observation& o, const std::vector<int>& deck_const) {
  std::unordered_map<int, int> counts;
  counts.reserve(deck_const.size());
  for (int id : deck_const) counts[id] += 1;

  auto subtract = [&](int id) {
    auto it = counts.find(id);
    if (it != counts.end() && it->second > 0) it->second -= 1;
  };
  auto subtract_pokemon = [&](const Pokemon& p) {
    if (!p.present || p.faceDown) return;
    subtract(p.id);
    for (int eid : p.energyCardIds) subtract(eid);
    for (int tid : p.toolIds) subtract(tid);
    for (int pid : p.preEvoIds) subtract(pid);
  };

  subtract_pokemon(o.myActive);
  for (const auto& p : o.myBench) subtract_pokemon(p);
  for (const auto& c : o.myHand) subtract(c.id);
  for (const auto& c : o.myDiscard) subtract(c.id);
  if (o.stadiumCardId != 0) subtract(o.stadiumCardId);
  for (int id : o.myPrizeGuess) subtract(id);

  o.deckCounts.clear();
  o.deckCounts.reserve(counts.size());
  for (const auto& kv : counts) o.deckCounts.emplace_back(kv.first, kv.second);
}

}  // namespace v17
