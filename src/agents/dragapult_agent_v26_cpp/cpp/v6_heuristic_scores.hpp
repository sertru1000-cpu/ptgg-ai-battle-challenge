// Out-of-line definitions of V6Scorer::raw_scores / select_top -- split from
// v6_heuristic.hpp purely to keep individual files reviewable; logically
// part of the same class. #include v6_heuristic.hpp before this file.
//
// This is the direct translation of dragapult_policy_v6.py's `agent()`
// method body: the field/hand/discard counting preamble, the `attach_score`/
// `hand_score` nested closures (here: `std::function` locals capturing by
// reference, exactly mirroring Python's closures over the same mutable
// locals), and the per-option `for o in select.option: ...` dispatch.
// Statement order is preserved deliberately (see v6_heuristic.hpp's header
// comment) because several values are genuinely order-dependent
// (hand_counts/support_count are mutated mid-loop and read by later
// iterations, exactly as in the Python original).
#pragma once

#include "v6_heuristic.hpp"

namespace v17 {

inline std::vector<double> V6Scorer::raw_scores(const Observation& obs) {
  using namespace enums;

  // --- field_counts / bench_attacker / evolve-eligibility preamble ---
  // (dragapult_policy_v6.py: the two `for card in my_state.active/bench`
  // loops, unconditional every call.)
  std::unordered_map<int, int> field_counts;
  int active_id = 0;
  bool bench_attacker = false;
  bool can_evolve_dreepy = false;
  int evolve_dreepy_count = 0;
  bool can_evolve_drakloak = false;
  const int damage = 200;

  if (obs.myActive.present) {
    active_id = obs.myActive.id;
    field_counts[obs.myActive.id] += 1;
    if (!obs.myActive.appearThisTurn) {
      if (obs.myActive.id == Dreepy) {
        can_evolve_dreepy = true;
        evolve_dreepy_count += 1;
      } else if (obs.myActive.id == Drakloak) {
        can_evolve_drakloak = true;
      }
    }
  }
  for (const auto& card : obs.myBench) {
    if (!card.present) continue;
    field_counts[card.id] += 1;
    if (!card.appearThisTurn) {
      if (card.id == Dreepy) {
        can_evolve_dreepy = true;
        evolve_dreepy_count += 1;
      } else if (card.id == Drakloak) {
        can_evolve_drakloak = true;
      }
    }
    if (card.id == Dragapult_ex && static_cast<int>(card.energies.size()) >= 2) bench_attacker = true;
  }

  int main_pokemon_count = field_counts[Dreepy] + field_counts[Drakloak] + field_counts[Dragapult_ex];
  bool no_more_dex = field_counts[Dragapult_ex] * 2 >= obs.oppPrizeCount;
  int stadium_id = obs.stadiumCardId;
  int support_count = 0;

  std::unordered_map<int, int> discard_counts;
  for (const auto& c : obs.myDiscard) discard_counts[c.id] += 1;

  std::unordered_map<int, int> deck_counts_map;
  for (const auto& kv : obs.deckCounts) deck_counts_map[kv.first] = kv.second;
  auto deck_count = [&](int id) -> int {
    auto it = deck_counts_map.find(id);
    return it == deck_counts_map.end() ? 0 : it->second;
  };

  const bool pre_ko = obs.preKo;
  const bool no_item = obs.noItem;
  const int prize_diff = obs.myPrizeCount - obs.oppPrizeCount;

  // hand_counts is mutated DURING both the hand_scores pass below and the
  // main options loop (TO_BENCH/TO_HAND/DISCARD contexts) -- captured by
  // reference throughout, exactly matching the Python closures' behavior.
  std::unordered_map<int, int> hand_counts;

  // --- attach_score (dragapult_policy_v6.py's nested `attach_score`) ---
  auto attach_score = [&](int attach_id, const Pokemon& pokemon, bool active) -> double {
    int energy_count = static_cast<int>(pokemon.energies.size());
    if (cards_.card(attach_id).cardType == CT_TOOL) {
      double score = 60000;
      if (active) score += 1000;
      return score;
    }
    if (pokemon.id == Budew) return -1;
    // V25: Munkidori wants exactly one {D} (Adrena-Brain); {D} anywhere else
    // is a wasted slot (port of dragapult_policy_v19.py's attach_score delta).
    if (pokemon.id == Munkidori) {
      bool has_dark = false;
      for (int eid : pokemon.energyCardIds) {
        if (eid == Basic_Dark_Energy) has_dark = true;
      }
      return (attach_id == Basic_Dark_Energy && !has_dark) ? 20300 : -1;
    }
    if (attach_id == Basic_Dark_Energy) return -1;
    if (pokemon.id == Meowth_ex || pokemon.id == Fezandipiti_ex || pokemon.id == Latias_ex) {
      if (active && !can_switch_ && !obs.myAsleep && !obs.myParalyzed) {
        if (bench_attacker || field_counts[Budew] >= 1) return 22000;
        return 18000;
      }
      return -1;
    }
    if (active && can_main_attack_) return -1;
    double score = 20000;
    if (energy_count >= 2) {
      if (active && !can_switch_ && !obs.myAsleep && !obs.myParalyzed) {
        score += 200;
      } else {
        return -1;
      }
    } else if (energy_count == 1) {
      if (!pokemon.energyCardIds.empty() && attach_id == pokemon.energyCardIds[0]) return -1;
      if (pokemon.id == Dragapult_ex) score += 250;
      else if (pokemon.id == Dreepy) score -= 150;
      else score -= 200;
      if (active) score += 200;
    } else {
      if (active) {
        if (bench_attacker) score += 400;
      } else {
        if (pokemon.id == Dragapult_ex) score += 150;
        else if (pokemon.id == Dreepy) score += 100;
        else score += 50;
        if (bench_attacker) score -= 200;
      }
    }
    if (no_more_dex && (pokemon.id == Dreepy || pokemon.id == Drakloak)) score -= 500;
    return score;
  };

  // --- hand_score (dragapult_policy_v6.py's nested `hand_score`, recursive
  // via Night_Stretcher) ---
  std::function<double(int, bool)> hand_score = [&](int id, bool ignore_count) -> double {
    double score = 0;
    if (id == Dreepy) {
      score = (main_pokemon_count >= 3) ? 1000 : 18000;
    } else if (id == Drakloak) {
      score = can_evolve_dreepy ? 20000 : 3000;
    } else if (id == Dragapult_ex) {
      if (no_more_dex) {
        score = UNNECESSARY;
      } else if (can_evolve_dreepy && hand_counts[Rare_Candy] >= 1 && !no_item) {
        score = 40000;
      } else if (can_evolve_drakloak) {
        if (field_counts[Dragapult_ex] == 0) score = 30000;
        else if (field_counts[Dragapult_ex] == 1) score = 10000;
        else score = 50;
      } else {
        score = (field_counts[Dragapult_ex] >= 2) ? 50 : 2000;
      }
    } else if (id == Fezandipiti_ex) {
      if (pre_ko) score = 50000;
      else if (prize_diff <= -2) score = 5;
      else if (obs.oppPrizeCount == 1) score = UNNECESSARY;
    } else if (id == Latias_ex) {
      if (active_id == Fezandipiti_ex || active_id == Meowth_ex || active_id == Dreepy) {
        score = (field_counts[Drakloak] + field_counts[Dragapult_ex] == 0) ? 28000 : 15000;
      } else {
        score = 10;
      }
    } else if (id == Budew) {
      if (field_counts[Budew] + field_counts[Drakloak] + field_counts[Dragapult_ex] >= 1) score = UNNECESSARY;
      else if (obs.turn >= 2) score = 30000;
    } else if (id == Meowth_ex) {
      if (support_count > hand_counts[Boss_Orders] || stadium_id == Team_Rocket_Watchtower) score = 5;
      else if (obs.supporterPlayed) score = 40;
      else score = 35000;
    } else if (id == Rare_Candy) {
      if (no_more_dex) score = UNNECESSARY;
      else if (can_evolve_dreepy && hand_counts[Dragapult_ex] >= 1) score = 40000;
    } else if (id == Unfair_Stamp) {
      if (pre_ko) score = 80000;
      else if (obs.oppPrizeCount == 1) score = UNNECESSARY;
      else score = 80;
    } else if (id == Buddy_Buddy_Poffin) {
      int count = deck_count(Dreepy);
      if (count == 0) {
        score = UNNECESSARY;
      } else {
        if (obs.turn <= 2 && field_counts[Budew] == 0 && deck_count(Budew) >= 1) count += 1;
        if (count >= 2) score = 35000;
      }
    } else if (id == Night_Stretcher) {
      for (const auto& kv : discard_counts) {
        if (kv.second >= 1) {
          int card_type = cards_.card(kv.first).cardType;
          if (card_type == CT_POKEMON || card_type == CT_BASIC_ENERGY) {
            score = std::max(score, hand_score(kv.first, ignore_count));
          }
        }
      }
    } else if (id == Crushing_Hammer) {
      score = 20;
    } else if (id == Ultra_Ball) {
      score = (main_pokemon_count <= 2 || field_counts[Dreepy] >= 1) ? 70 : 5;
    } else if (id == Poke_Pad) {
      score = std::max(hand_score(Dreepy, ignore_count), hand_score(Drakloak, ignore_count));
    } else if (id == Lucky_Helmet) {
      score = 15;
    } else if (id == Boss_Orders) {
      if (plan_a_.attack > 0) score = 60000;
    } else if (id == Crispin) {
      if (!ignore_count || support_count == 0) {
        if (deck_count(Basic_Fire_Energy) == 0 || deck_count(Basic_Psychic_Energy) == 0) score = 10;
        if (!can_main_attack_ && !bench_attacker && field_counts[Dragapult_ex] >= 1) score = 55000;
        else score = 25000;
      }
    } else if (id == Brock_Scouting) {
      if (!ignore_count || support_count == 0) {
        if (obs.turn == 2 && field_counts[Budew] + field_counts[Latias_ex] == 0) score = 50000;
        else score = 30000;
      }
    } else if (id == Lillie_Determination) {
      if (!ignore_count || support_count == 0) score = 45000;
    } else if (id == Team_Rocket_Watchtower) {
      if (stadium_id != 0 && stadium_id != Team_Rocket_Watchtower) score = 4000;
    } else if (id == Munkidori) {
      // V25: bench one Munkidori; the second copy is redundancy only.
      score = (field_counts[Munkidori] == 0) ? 12000 : 5;
    } else if (id == Judge) {
      if (!ignore_count || support_count == 0) {
        score = 6000 + 2500.0 * std::max(0, obs.oppHandCount - 4);
      }
    } else if (id == Dawn) {
      if (!ignore_count || support_count == 0) {
        bool line_missing =
            (deck_count(Dreepy) > 0 && hand_counts[Dreepy] + field_counts[Dreepy] == 0) ||
            (deck_count(Drakloak) > 0 && hand_counts[Drakloak] + field_counts[Drakloak] == 0) ||
            (deck_count(Dragapult_ex) > 0 && hand_counts[Dragapult_ex] + field_counts[Dragapult_ex] == 0);
        score = line_missing ? 46000 : 8000;
      }
    } else if (id == Jamming_Tower) {
      if (stadium_id != 0 && stadium_id != Jamming_Tower) score = 4000;
    } else if (id == Basic_Dark_Energy) {
      // V25: only ever for Munkidori (attach_score enforces that).
      double max_score = -10000;
      if (obs.myActive.present) max_score = std::max(max_score, attach_score(id, obs.myActive, true));
      for (const auto& p : obs.myBench) {
        if (p.present) max_score = std::max(max_score, attach_score(id, p, false));
      }
      score = max_score - 5000;
    } else if (id == Basic_Fire_Energy || id == Basic_Psychic_Energy) {
      if (can_main_attack_ && (obs.oppPrizeCount <= 2 || (bench_attacker && obs.oppPrizeCount <= 4))) {
        score = UNNECESSARY;
      } else {
        double max_score = -10000;
        if (obs.myActive.present) max_score = std::max(max_score, attach_score(id, obs.myActive, true));
        for (const auto& p : obs.myBench) {
          if (p.present) max_score = std::max(max_score, attach_score(id, p, false));
        }
        score = max_score - 5000;
        if (can_main_attack_ || bench_attacker) score /= 10;
      }
    }

    if (!ignore_count && hand_counts[id] > 0) {
      if (id == Drakloak && hand_counts[id] < evolve_dreepy_count) score -= 10;
      else if (id == Dreepy) score -= 100;
      else score -= 100000;
    }
    return score;
  };

  // --- MAIN-context preamble: main_option_proc + use_support determination.
  // ONLY runs when context == MAIN -- everything it sets (plan_a_/plan_b_/
  // can_switch_/can_attack_/can_main_attack_/use_support_) otherwise carries
  // its value forward from the previous MAIN-context call, exactly like the
  // Python instance attributes it mirrors (see v6_heuristic.hpp header). ---
  if (obs.context == CTX_MAIN) {
    main_option_proc(obs, damage, bench_attacker);

    use_support_ = 0;
    if (!obs.supporterPlayed) {
      double support_score = 0;
      for (const Option& o : obs.options) {
        if (o.type == OPT_PLAY) {
          const Card* c = get_card_ref(obs, AREA_HAND, o.index, obs.myIndex);
          if (c && cards_.card(c->id).cardType == CT_SUPPORTER) {
            double score = hand_score(c->id, true);
            if (support_score < score) {
              support_score = score;
              use_support_ = c->id;
            }
          }
        }
      }
    }
  }

  // --- per-hand-card scores (also grows hand_counts/support_count, order-
  // dependent: a duplicate card's hand_score sees prior copies already
  // counted but not itself -- see file header). ---
  std::vector<double> hand_scores;
  int negative_hand_count = 0;
  for (const auto& card : obs.myHand) {
    double score = hand_score(card.id, false);
    hand_scores.push_back(score);
    if (score < 0) negative_hand_count += 1;
    hand_counts[card.id] += 1;
    if (cards_.card(card.id).cardType == CT_SUPPORTER && card.id != Boss_Orders) support_count += 1;
  }

  bool no_draw = obs.myDeckCount <= 8;
  bool do_switch = !can_main_attack_ && (bench_attacker || (active_id != Budew && field_counts[Budew] >= 1 && obs.turn >= 2));
  if (!do_switch) {
    do_switch = wants_defensive_retreat(obs.myActive, obs.oppActive, can_attack_);
  }
  int effect_card_id = obs.effectCardId;
  int context_card_id = obs.contextCardId;

  std::vector<double> scores;
  scores.reserve(obs.options.size());

  for (const Option& o : obs.options) {
    double score = 0;

    if (o.type == OPT_NUMBER) {
      score = o.number;
    } else if (o.type == OPT_YES) {
      score = (obs.context == CTX_IS_FIRST) ? -1 : 1;
    } else if (o.type == OPT_CARD) {
      const Pokemon* p = nullptr;
      const Card* c = nullptr;
      int card_id = -1;
      bool found = false;
      int energy_count = 0, hp = 0;
      if (o.area == AREA_ACTIVE || o.area == AREA_BENCH) {
        p = get_pokemon(obs, o.area, o.index, o.playerIndex);
        if (p && p->present) {
          found = true;
          card_id = p->id;
          energy_count = static_cast<int>(p->energies.size());
          hp = p->hp;
        }
      } else {
        c = get_card_ref(obs, o.area, o.index, o.playerIndex);
        if (c) {
          found = true;
          card_id = c->id;
        }
      }

      if (found) {
        if (obs.context == CTX_SWITCH || obs.context == CTX_TO_ACTIVE || obs.context == CTX_SETUP_ACTIVE_POKEMON) {
          if (o.playerIndex == obs.myIndex) {
            if (card_id == Dreepy) score += 10000;
            else if (card_id == Drakloak) score += (energy_count >= 1) ? 20000 : -10000;
            else if (card_id == Dragapult_ex) score += 50000;
            else if (card_id == Budew) {
              if (obs.context != CTX_SWITCH) score += 100000;
              else if (!bench_attacker) score += 30000;
            } else if (card_id == Fezandipiti_ex) {
              score -= 1000.0 / weights_.switch_risk_tolerance;
            } else if (card_id == Meowth_ex) {
              score -= 2000.0 / weights_.switch_risk_tolerance;
            }
          } else {
            if (plan_a_.attack == o.index + 1) score += 100000;
          }
          score += energy_count * 1000;
          score += hp * (1 + weights_.preservation_bias);
        } else if (obs.context == CTX_SETUP_BENCH_POKEMON) {
          if (obs.myIndex == obs.firstPlayer || card_id != Dreepy) score = -1;
        } else if (obs.context == CTX_TO_BENCH || obs.context == CTX_TO_HAND) {
          score = hand_score(card_id, false);
          hand_counts[card_id] += 1;
          if (effect_card_id == Crispin) score = 100000 - hand_score(card_id, true);
        } else if (obs.context == CTX_DISCARD) {
          hand_counts[card_id] -= 1;
          if (cards_.card(card_id).cardType == CT_SUPPORTER) support_count -= 1;
          score = -hand_score(card_id, false);
        } else if (obs.context == CTX_DAMAGE_COUNTER || obs.context == CTX_DAMAGE_COUNTER_ANY) {
          if (hp > 0 && p != nullptr) {
            score = 100000 - 10 * hp + pokemon_score(*p, false);
            if (obs.context == CTX_DAMAGE_COUNTER) {
              if (hp >= 210 && hp <= 230) {
                score += 20000 + hp * 20;
                if (o.area == AREA_ACTIVE) score += 10000;
              } else if (hp >= 40 && hp <= 90) {
                score += 10000 + hp * 20;
              } else if (hp <= 30) {
                score += -10000 + hp * 20;
              }
              if (card_id == 133 || card_id == 351) score += 30000;
            } else {
              int index = o.index + 1;
              if (std::find(plan_b_.counter.begin(), plan_b_.counter.end(), index) != plan_b_.counter.end()) {
                score += 100000;
              } else {
                int remain_damage = obs.remainDamageCounter * 10;
                if (hp >= 210 && hp <= 200 + remain_damage) score += 30000;
                else if (hp >= 20 && hp <= 60 + remain_damage) score += 10000;
                else if (hp == 10) score += 40000;  // V6 FIX #1
              }
              if (no_damage_counter_target(*p)) score = -1;
            }
          }
        } else if (obs.context == CTX_ATTACH_FROM) {
          if (p != nullptr) {
            score = attach_score(context_card_id, *p, o.area == AREA_ACTIVE);
            if (card_id == Dragapult_ex) score += 200;
          }
        } else if (effect_card_id == Munkidori && p != nullptr) {
          // V25: Adrena-Brain's source/target selects (effect-gated, port of
          // dragapult_policy_v19.py): take counters from our MOST damaged
          // Pokemon, put them on their most killable target.
          if (o.playerIndex < 0 || o.playerIndex == obs.myIndex) {
            score = static_cast<double>(p->maxHp - p->hp);
          } else {
            score = 100000 - 10.0 * p->hp + pokemon_score(*p, false);
          }
        }
      }
    } else if (o.type == OPT_ENERGY_CARD || o.type == OPT_ENERGY) {
      if (o.playerIndex != obs.myIndex) {
        score = (o.area == AREA_BENCH) ? 20 : 10;
        // Faithful port of an apparent no-op in the original: this reads the
        // POKEMON at (area,index) rather than the energy card itself, so the
        // cardType check below is never CT_SPECIAL_ENERGY in practice.
        // Preserved as-is (see file header) rather than "corrected".
        const Pokemon* p = get_pokemon(obs, o.area, o.index, o.playerIndex);
        if (p && p->present && cards_.card(p->id).cardType == CT_SPECIAL_ENERGY) score += 1;
      }
    } else if (o.type == OPT_PLAY) {
      const Card* hand_card = get_card_ref(obs, AREA_HAND, o.index, obs.myIndex);
      int card_id = hand_card ? hand_card->id : -1;
      double card_score = (o.index >= 0 && static_cast<size_t>(o.index) < hand_scores.size()) ? hand_scores[static_cast<size_t>(o.index)] : 0.0;
      if (card_id == Dreepy) {
        score = 51000;
      } else if (card_id == Fezandipiti_ex) {
        score = (card_score > 0) ? 53000 : -1;
      } else if (card_id == Latias_ex) {
        score = (active_id != Drakloak && active_id != Dragapult_ex) ? 51000 : -1;
      } else if (card_id == Budew) {
        score = (field_counts[Budew] == 0 && field_counts[Dragapult_ex] == 0) ? 52000 : -1;
      } else if (card_id == Meowth_ex) {
        if (obs.supporterPlayed || stadium_id == Team_Rocket_Watchtower) score = -1;
        else if (support_count == 0) score = 50000;
        else if (support_count == hand_counts[Boss_Orders] && plan_a_.attack > 0) score = 50000;
        else score = -1;
      } else if (card_id == Rare_Candy) {
        score = no_more_dex ? -1 : 75000;
      } else if (card_id == Unfair_Stamp) {
        score = 15000;
      } else if (card_id == Night_Stretcher) {
        score = (card_score >= 18000) ? 42000 : -1;
      } else if (card_id == Crushing_Hammer) {
        score = 40000;
      } else if (card_id == Boss_Orders) {
        score = (card_id == use_support_) ? 35000 : -1;
      } else if (card_id == Lillie_Determination) {
        score = (card_id == use_support_) ? 14000 : -1;
      } else if (card_id == Team_Rocket_Watchtower) {
        score = (stadium_id > 0 || obs.turn == 1) ? 80000 : -1;
      } else if (card_id == Munkidori) {
        score = (field_counts[Munkidori] == 0) ? 50500 : -1;  // V25
      } else if (card_id == Judge) {
        score = (card_id == use_support_) ? 14000 : -1;  // V25
      } else if (card_id == Dawn) {
        score = (card_id == use_support_) ? 34000 : -1;  // V25: line assembler, Boss-grade priority
      } else if (card_id == Jamming_Tower) {
        score = (stadium_id > 0 || obs.turn == 1) ? 80000 : -1;  // V25: Watchtower pattern
      } else if (no_draw) {
        score = -1;
      } else if (card_id == Buddy_Buddy_Poffin) {
        score = (deck_count(Dreepy) > 0) ? 46000 : -1;
      } else if (card_id == Ultra_Ball) {
        score = (negative_hand_count >= 2) ? 44000 : -1;
      } else if (card_id == Poke_Pad) {
        score = (deck_count(Dreepy) + deck_count(Drakloak) > 0) ? 45000 : -1;
      } else if (card_id == Crispin || card_id == Brock_Scouting) {
        score = (card_id == use_support_) ? 35000 : -1;
      }
    } else if (o.type == OPT_ATTACH) {
      const Card* hand_card = get_card_ref(obs, o.area, o.index, obs.myIndex);
      const Pokemon* target = get_pokemon(obs, o.inPlayArea, o.inPlayIndex, obs.myIndex);
      if (hand_card && target && target->present) {
        score = attach_score(hand_card->id, *target, o.inPlayArea == AREA_ACTIVE);
      }
    } else if (o.type == OPT_EVOLVE) {
      const Pokemon* target = get_pokemon(obs, o.inPlayArea, o.inPlayIndex, obs.myIndex);
      if (target && target->present) {
        score += static_cast<double>(target->energies.size());
        if (target->id == Dreepy) {
          score += 30000;
        } else if (field_counts[Dragapult_ex] >= 2 || (field_counts[Dragapult_ex] == 1 && obs.oppPrizeCount <= 2)) {
          score = -1;
        } else {
          score += 70000;
        }
      }
    } else if (o.type == OPT_ABILITY) {
      int card_id = -1;
      const Card* c = get_card_ref(obs, o.area, o.index, obs.myIndex);
      if (c) {
        card_id = c->id;
      } else {
        const Pokemon* p = get_pokemon(obs, o.area, o.index, obs.myIndex);
        if (p && p->present) card_id = p->id;
        else if (o.area == AREA_STADIUM) card_id = obs.stadiumCardId;
      }
      if (card_id == Munkidori) {
        // V25: Adrena-Brain -- BEFORE the no_draw guard (it moves damage
        // counters, never draws). Use it any turn one of our Pokemon
        // actually carries damage to ship across.
        bool damaged = obs.myActive.present && obs.myActive.hp < obs.myActive.maxHp;
        for (const auto& p : obs.myBench) {
          if (p.present && p.hp < p.maxHp) damaged = true;
        }
        score = damaged ? 45000 : -1;
      } else if (no_draw) score = -1;
      else if (card_id == 1267) score = 1;  // Lumiose City
      else score = 40000;
    } else if (o.type == OPT_RETREAT) {
      score = do_switch ? 10000 : -1;
    } else if (o.type == OPT_ATTACK) {
      score = o.attackId;
    }

    scores.push_back(score);
  }

  return scores;
}

inline std::vector<int> V6Scorer::select_top(const Observation& obs, const std::vector<double>& scores) {
  using namespace enums;
  if (scores.empty()) return {};
  std::vector<int> ranked(scores.size());
  for (size_t i = 0; i < scores.size(); ++i) ranked[i] = static_cast<int>(i);
  std::stable_sort(ranked.begin(), ranked.end(),
                    [&](int a, int b) { return scores[static_cast<size_t>(a)] > scores[static_cast<size_t>(b)]; });

  std::vector<int> output;
  int max_count = std::min(obs.maxCount, static_cast<int>(ranked.size()));
  for (int i = 0; i < max_count; ++i) {
    int idx = ranked[static_cast<size_t>(i)];
    double score = scores[static_cast<size_t>(idx)];
    if (score >= 0 || obs.minCount > i || (obs.context != CTX_TO_BENCH && obs.context != CTX_SETUP_BENCH_POKEMON)) {
      output.push_back(idx);
    }
  }
  return output;
}

}  // namespace v17
