// Internal, owning C++ representation of one decision point -- the native
// analogue of cg/api.py's `Observation`/`SelectData`/`State`/`PlayerState`/
// `Pokemon`/`Card` dataclasses, trimmed to exactly the fields V6Heuristic and
// Mcts actually read (skills text, log detail, etc. are never needed by the
// ported scoring logic and are omitted).
//
// Two independent ways to build one, matching the two places decisions come
// from (see ../README.md's call-chain diagram):
//   - from_ctypes(): the ONE real per-decision root observation, already
//     flattened by Python (see v17_abi.h) -- a pure field copy, no parsing.
//   - from_search_json(): every simulated node inside the MCTS tree, built
//     from the native engine's own JSON reply via json_extract.hpp. Never
//     touches Python.
//
// Every member is a plain owned value (int/bool/std::string/std::vector) --
// nothing here stores a std::string_view, so an instance is safe to keep
// alive independently of whatever buffer it was parsed from.
#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "json_extract.hpp"
#include "v17_abi.h"

namespace v17 {

struct Pokemon {
  bool present = false;
  bool faceDown = false;
  int id = 0;
  int serial = 0;
  int hp = 0;
  int maxHp = 0;
  bool appearThisTurn = false;
  std::vector<int> energies;        // EnergyType per attached energy unit
  std::vector<int> energyCardIds;   // card id per attached energy card
  std::vector<int> toolIds;
  std::vector<int> preEvoIds;
};

struct Card {
  int id = 0;
  int serial = 0;
  int playerIndex = -1;
};

struct Option {
  int type = -1;
  int number = -1;
  int area = -1;
  int index = -1;
  int playerIndex = -1;
  int toolIndex = -1;
  int energyIndex = -1;
  int count = -1;
  int inPlayArea = -1;
  int inPlayIndex = -1;
  int attackId = -1;
  int cardId = -1;
  int serial = -1;
  int specialConditionType = -1;
};

struct Observation {
  int myIndex = 0;
  int turn = 0;
  int firstPlayer = -1;
  bool supporterPlayed = false;
  bool stadiumPlayed = false;
  bool energyAttached = false;
  bool retreated = false;
  int result = -1;  // -1 == not finished; 0/1 == winner index; 2 == draw
  int stadiumCardId = 0;

  int selectType = -1;
  int context = -1;
  int minCount = 0;
  int maxCount = 0;
  int remainDamageCounter = 0;
  int remainEnergyCost = 0;
  int contextCardId = 0;
  int effectCardId = 0;

  int myDeckCount = 0;
  int oppDeckCount = 0;
  int myPrizeCount = 0;
  int oppPrizeCount = 0;
  int oppHandCount = 0;

  bool myPoisoned = false;
  bool myBurned = false;
  bool myAsleep = false;
  bool myParalyzed = false;
  bool myConfused = false;

  // V20 additions -- required by vectorizer.hpp (B1 learned eval): fields
  // the B1 model was trained on that V17/V18 never carried.
  int turnActionCount = 0;
  int oppDiscardCount = 0;
  bool oppPoisoned = false;
  bool oppBurned = false;
  bool oppAsleep = false;
  bool oppParalyzed = false;
  bool oppConfused = false;

  // Carried-forward from the real decision point, NOT re-derived per
  // simulated turn inside a rollout -- see README.md's "accepted
  // approximations" section for why (mirrors the project's existing
  // documented-limitation style, e.g. the shared-RNG caveat in
  // ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 5).
  bool preKo = false;
  bool noItem = false;

  Pokemon myActive;
  Pokemon oppActive;
  std::vector<Pokemon> myBench;
  std::vector<Pokemon> oppBench;
  std::vector<Card> myHand;
  std::vector<Card> myDiscard;

  // select.deck: present whenever a decision offers AreaType.DECK options
  // (cg/api.py: "None unless selecting cards from the deck") -- covers both
  // the deck-declare exchange (never reaches this struct, handled in Python
  // before native_choose_action) and later deck-searching effects, which DO
  // reach here. get_card()-equivalent resolution for AreaType.DECK indexes
  // into this.
  std::vector<Card> selectDeck;

  // AreaType.PRIZE / AreaType.LOOKING resolution targets. A `Card{id=0,...}`
  // entry at some index means that slot is face-down/unrevealed there (see
  // v17_abi.h) -- positions are never compacted, so Option.index still lines
  // up with the real cg.api zone.
  std::vector<Card> myPrizeCards;
  std::vector<Card> looking;

  // (card_id, remaining_count) pairs. Recomputed fresh at every node (root
  // AND every rollout step) from the DECK constant minus everything
  // currently visible in THIS node minus myPrizeGuess -- see
  // v6_heuristic.hpp's recompute_deck_counts(), which is what actually
  // fills this in; from_ctypes/from_search_json only carry the raw
  // ingredients (hand/bench/discard/active), not this derived field.
  std::vector<std::pair<int, int>> deckCounts;

  // Fixed once at the real deck-declare moment (root only), then carried
  // forward unchanged through every rollout branch -- see the preKo/noItem
  // comment above; the same "snapshot, don't re-derive mid-rollout"
  // approximation applies here for the same reason (a real prize-take
  // during a simulated branch, which would reveal one identity, is not
  // modeled).
  std::vector<int> myPrizeGuess;

  // Block A1 (V18): pre-resolved opponent hidden-zone sampling pool (see
  // v17_abi.h's oppHiddenPoolIds comment). Root only -- like myPrizeGuess,
  // never re-derived inside a rollout; empty means "not provided, use the
  // legacy mirror-minus-visible-board fallback".
  std::vector<int> oppHiddenPool;

  std::vector<Option> options;
};

inline Pokemon pokemon_from_ctypes(const V17PokemonC& p) {
  Pokemon out;
  out.present = p.present != 0;
  out.faceDown = p.faceDown != 0;
  out.id = p.id;
  out.serial = p.serial;
  out.hp = p.hp;
  out.maxHp = p.maxHp;
  out.appearThisTurn = p.appearThisTurn != 0;
  for (int i = 0; i < p.energiesCount && i < V17_MAX_ENERGIES; ++i) out.energies.push_back(p.energies[i]);
  for (int i = 0; i < p.energyCardsCount && i < V17_MAX_ENERGIES; ++i) out.energyCardIds.push_back(p.energyCardIds[i]);
  for (int i = 0; i < p.toolsCount && i < V17_MAX_TOOLS; ++i) out.toolIds.push_back(p.toolIds[i]);
  for (int i = 0; i < p.preEvoCount && i < V17_MAX_PRE_EVO; ++i) out.preEvoIds.push_back(p.preEvoIds[i]);
  return out;
}

inline Observation from_ctypes(const V17RootObservationC& c) {
  Observation o;
  o.myIndex = c.myIndex;
  o.turn = c.turn;
  o.firstPlayer = c.firstPlayer;
  o.supporterPlayed = c.supporterPlayed != 0;
  o.stadiumPlayed = c.stadiumPlayed != 0;
  o.energyAttached = c.energyAttached != 0;
  o.retreated = c.retreated != 0;
  o.result = c.result;
  o.stadiumCardId = c.stadiumCardId;

  o.selectType = c.selectType;
  o.context = c.context;
  o.minCount = c.minCount;
  o.maxCount = c.maxCount;
  o.remainDamageCounter = c.remainDamageCounter;
  o.remainEnergyCost = c.remainEnergyCost;
  o.contextCardId = c.contextCardId;
  o.effectCardId = c.effectCardId;

  o.myDeckCount = c.myDeckCount;
  o.oppDeckCount = c.oppDeckCount;
  o.myPrizeCount = c.myPrizeCount;
  o.oppPrizeCount = c.oppPrizeCount;
  o.oppHandCount = c.oppHandCount;

  o.myPoisoned = c.myPoisoned != 0;
  o.myBurned = c.myBurned != 0;
  o.myAsleep = c.myAsleep != 0;
  o.myParalyzed = c.myParalyzed != 0;
  o.myConfused = c.myConfused != 0;

  o.turnActionCount = c.turnActionCount;
  o.oppDiscardCount = c.oppDiscardCount;
  o.oppPoisoned = c.oppPoisoned != 0;
  o.oppBurned = c.oppBurned != 0;
  o.oppAsleep = c.oppAsleep != 0;
  o.oppParalyzed = c.oppParalyzed != 0;
  o.oppConfused = c.oppConfused != 0;

  o.preKo = c.preKo != 0;
  o.noItem = c.noItem != 0;

  o.myActive = pokemon_from_ctypes(c.myActive);
  o.oppActive = pokemon_from_ctypes(c.oppActive);

  for (int i = 0; i < c.myBenchCount && i < V17_MAX_BENCH; ++i) o.myBench.push_back(pokemon_from_ctypes(c.myBench[i]));
  for (int i = 0; i < c.oppBenchCount && i < V17_MAX_BENCH; ++i) o.oppBench.push_back(pokemon_from_ctypes(c.oppBench[i]));

  for (int i = 0; i < c.myHandCount && i < V17_MAX_HAND; ++i) {
    o.myHand.push_back(Card{c.myHand[i].id, c.myHand[i].serial, c.myHand[i].playerIndex});
  }
  for (int i = 0; i < c.myDiscardCount && i < V17_MAX_DISCARD; ++i) {
    o.myDiscard.push_back(Card{c.myDiscard[i].id, c.myDiscard[i].serial, c.myDiscard[i].playerIndex});
  }
  for (int i = 0; i < c.selectDeckCount && i < V17_MAX_SELECT_DECK; ++i) {
    o.selectDeck.push_back(Card{c.selectDeck[i].id, c.selectDeck[i].serial, c.selectDeck[i].playerIndex});
  }
  for (int i = 0; i < c.myPrizeCardsCount && i < V17_MAX_PRIZE; ++i) {
    o.myPrizeCards.push_back(Card{c.myPrizeCards[i].id, c.myPrizeCards[i].serial, c.myPrizeCards[i].playerIndex});
  }
  for (int i = 0; i < c.lookingCount && i < V17_MAX_LOOKING; ++i) {
    o.looking.push_back(Card{c.looking[i].id, c.looking[i].serial, c.looking[i].playerIndex});
  }

  for (int i = 0; i < c.myPrizeGuessCount && i < V17_MAX_PRIZE; ++i) o.myPrizeGuess.push_back(c.myPrizeGuessIds[i]);

  for (int i = 0; i < c.oppHiddenPoolCount && i < V17_MAX_OPP_POOL; ++i) o.oppHiddenPool.push_back(c.oppHiddenPoolIds[i]);

  for (int i = 0; i < c.deckDistinctCount && i < V17_MAX_DECK_DISTINCT; ++i) {
    o.deckCounts.emplace_back(c.deckIds[i], c.deckCounts[i]);
  }

  for (int i = 0; i < c.optionCount && i < V17_MAX_OPTIONS; ++i) {
    const V17OptionC& op = c.options[i];
    Option out;
    out.type = op.type;
    out.number = op.number;
    out.area = op.area;
    out.index = op.index;
    out.playerIndex = op.playerIndex;
    out.toolIndex = op.toolIndex;
    out.energyIndex = op.energyIndex;
    out.count = op.count;
    out.inPlayArea = op.inPlayArea;
    out.inPlayIndex = op.inPlayIndex;
    out.attackId = op.attackId;
    out.cardId = op.cardId;
    out.serial = op.serial;
    out.specialConditionType = op.specialConditionType;
    o.options.push_back(out);
  }

  return o;
}

namespace detail {

inline Pokemon parse_pokemon(std::optional<std::string_view> node) {
  Pokemon p;
  if (!node.has_value()) {
    p.present = false;
    return p;
  }
  p.present = true;
  // A present-but-face-down Pokemon serializes as a JSON `null` inside the
  // active array (cg/api.py: "None if the card is facedown"); object_member
  // already normalizes null -> nullopt for the id/serial/hp lookups below,
  // so a face-down Pokemon naturally comes out as id=0/serial=0/hp=0 -- we
  // still record faceDown explicitly so callers don't mistake that for a
  // real 0-HP Pokemon.
  bool has_id = jx::object_member(*node, "id").has_value();
  p.faceDown = !has_id;
  p.id = jx::to_int(jx::object_member(*node, "id"), 0);
  p.serial = jx::to_int(jx::object_member(*node, "serial"), 0);
  p.hp = jx::to_int(jx::object_member(*node, "hp"), 0);
  p.maxHp = jx::to_int(jx::object_member(*node, "maxHp"), 0);
  p.appearThisTurn = jx::to_bool(jx::object_member(*node, "appearThisTurn"), false);

  auto energies = jx::object_member(*node, "energies");
  if (energies.has_value()) {
    for (auto item : jx::array_items(*energies)) p.energies.push_back(jx::to_int(item, 0));
  }
  auto energy_cards = jx::object_member(*node, "energyCards");
  if (energy_cards.has_value()) {
    for (auto item : jx::array_items(*energy_cards)) p.energyCardIds.push_back(jx::to_int(jx::object_member(item, "id"), 0));
  }
  auto tools = jx::object_member(*node, "tools");
  if (tools.has_value()) {
    for (auto item : jx::array_items(*tools)) p.toolIds.push_back(jx::to_int(jx::object_member(item, "id"), 0));
  }
  auto pre_evo = jx::object_member(*node, "preEvolution");
  if (pre_evo.has_value()) {
    for (auto item : jx::array_items(*pre_evo)) p.preEvoIds.push_back(jx::to_int(jx::object_member(item, "id"), 0));
  }
  return p;
}

// `arr_val` is the raw span of a `list[Pokemon]`/`list[Card]` JSON array
// (e.g. `state.players[i].bench`), read via object_member on the enclosing
// PlayerState object.
inline std::optional<Pokemon> parse_pokemon_slot0(std::optional<std::string_view> arr_val) {
  if (!arr_val.has_value()) return std::nullopt;
  auto items = jx::array_items(*arr_val);
  if (items.empty()) return std::nullopt;  // array present but empty -> no active Pokemon at all
  return parse_pokemon(items[0]);
}

inline std::vector<Pokemon> parse_pokemon_list(std::optional<std::string_view> arr_val) {
  std::vector<Pokemon> out;
  if (!arr_val.has_value()) return out;
  for (auto item : jx::array_items(*arr_val)) out.push_back(parse_pokemon(item));
  return out;
}

inline std::vector<Card> parse_card_list(std::optional<std::string_view> arr_val) {
  std::vector<Card> out;
  if (!arr_val.has_value()) return out;
  for (auto item : jx::array_items(*arr_val)) {
    Card c;
    c.id = jx::to_int(jx::object_member(item, "id"), 0);
    c.serial = jx::to_int(jx::object_member(item, "serial"), 0);
    c.playerIndex = jx::to_int(jx::object_member(item, "playerIndex"), -1);
    out.push_back(c);
  }
  return out;
}

}  // namespace detail

// Parses one Observation JSON object (as returned by a SearchBegin/SearchStep
// call, already unwrapped from its ApiResult envelope by cg_engine.hpp) into
// our internal struct. `carry_forward` supplies the fields this node cannot
// derive on its own (preKo/noItem/myPrizeGuess -- see the Observation struct
// comments above for why those are intentionally snapshotted rather than
// re-derived per simulated step) plus `myIndex`, which the engine's
// Observation reports per the CURRENT acting player -- when a simulated
// branch reaches a decision point for the OPPONENT instead of us, the
// caller (mcts.hpp) is responsible for recognizing that via
// `current.yourIndex` and routing to opponent-modeling logic rather than
// calling this with the wrong `carry_forward.myIndex`.
//
// Returns nullopt if `select` is null (this only happens on the very first
// deck-declare call in a real game, which the caller never routes into the
// search sandbox in the first place -- treated as a hard "shouldn't happen"
// rather than silently guessed).
inline std::optional<Observation> from_search_json(const std::string& obs_json, const Observation& carry_forward) {
  auto select = jx::object_member(obs_json, "select");
  auto current = jx::object_member(obs_json, "current");
  if (!select.has_value() || !current.has_value()) return std::nullopt;

  Observation o;
  o.preKo = carry_forward.preKo;
  o.noItem = carry_forward.noItem;
  o.myPrizeGuess = carry_forward.myPrizeGuess;

  o.myIndex = jx::to_int(jx::object_member(*current, "yourIndex"), carry_forward.myIndex);
  o.turn = jx::to_int(jx::object_member(*current, "turn"), 0);
  o.turnActionCount = jx::to_int(jx::object_member(*current, "turnActionCount"), 0);  // V20: B1 feature
  o.firstPlayer = jx::to_int(jx::object_member(*current, "firstPlayer"), -1);
  o.supporterPlayed = jx::to_bool(jx::object_member(*current, "supporterPlayed"), false);
  o.stadiumPlayed = jx::to_bool(jx::object_member(*current, "stadiumPlayed"), false);
  o.energyAttached = jx::to_bool(jx::object_member(*current, "energyAttached"), false);
  o.retreated = jx::to_bool(jx::object_member(*current, "retreated"), false);
  o.result = jx::to_int(jx::object_member(*current, "result"), -1);

  auto stadium_arr = jx::object_member(*current, "stadium");
  o.stadiumCardId = 0;
  if (stadium_arr.has_value()) {
    auto items = jx::array_items(*stadium_arr);
    if (!items.empty()) o.stadiumCardId = jx::to_int(jx::object_member(items[0], "id"), 0);
  }

  o.selectType = jx::to_int(jx::object_member(*select, "type"), -1);
  o.context = jx::to_int(jx::object_member(*select, "context"), -1);
  o.minCount = jx::to_int(jx::object_member(*select, "minCount"), 0);
  o.maxCount = jx::to_int(jx::object_member(*select, "maxCount"), 0);
  o.remainDamageCounter = jx::to_int(jx::object_member(*select, "remainDamageCounter"), 0);
  o.remainEnergyCost = jx::to_int(jx::object_member(*select, "remainEnergyCost"), 0);
  auto context_card = jx::object_member(*select, "contextCard");
  o.contextCardId = context_card.has_value() ? jx::to_int(jx::object_member(*context_card, "id"), 0) : 0;
  auto effect = jx::object_member(*select, "effect");
  o.effectCardId = effect.has_value() ? jx::to_int(jx::object_member(*effect, "id"), 0) : 0;

  auto players = jx::object_member(*current, "players");
  std::vector<std::string_view> player_states = players.has_value() ? jx::array_items(*players) : std::vector<std::string_view>{};
  int my_idx = o.myIndex;
  int opp_idx = 1 - my_idx;

  if (static_cast<size_t>(my_idx) < player_states.size() && static_cast<size_t>(opp_idx) < player_states.size()) {
    std::string_view my_ps = player_states[my_idx];
    std::string_view opp_ps = player_states[opp_idx];

    auto my_active_slot = detail::parse_pokemon_slot0(jx::object_member(my_ps, "active"));
    o.myActive = my_active_slot.value_or(Pokemon{});
    auto opp_active_slot = detail::parse_pokemon_slot0(jx::object_member(opp_ps, "active"));
    o.oppActive = opp_active_slot.value_or(Pokemon{});

    o.myBench = detail::parse_pokemon_list(jx::object_member(my_ps, "bench"));
    o.oppBench = detail::parse_pokemon_list(jx::object_member(opp_ps, "bench"));

    o.myHand = detail::parse_card_list(jx::object_member(my_ps, "hand"));
    o.myDiscard = detail::parse_card_list(jx::object_member(my_ps, "discard"));
    o.selectDeck = detail::parse_card_list(jx::object_member(*select, "deck"));
    o.myPrizeCards = detail::parse_card_list(jx::object_member(my_ps, "prize"));
    o.looking = detail::parse_card_list(jx::object_member(*current, "looking"));

    o.myDeckCount = jx::to_int(jx::object_member(my_ps, "deckCount"), 0);
    o.oppDeckCount = jx::to_int(jx::object_member(opp_ps, "deckCount"), 0);
    o.oppHandCount = jx::to_int(jx::object_member(opp_ps, "handCount"), 0);

    auto my_prize = jx::object_member(my_ps, "prize");
    o.myPrizeCount = my_prize.has_value() ? static_cast<int>(jx::array_items(*my_prize).size()) : 0;
    auto opp_prize = jx::object_member(opp_ps, "prize");
    o.oppPrizeCount = opp_prize.has_value() ? static_cast<int>(jx::array_items(*opp_prize).size()) : 0;

    o.myPoisoned = jx::to_bool(jx::object_member(my_ps, "poisoned"), false);
    o.myBurned = jx::to_bool(jx::object_member(my_ps, "burned"), false);
    o.myAsleep = jx::to_bool(jx::object_member(my_ps, "asleep"), false);
    o.myParalyzed = jx::to_bool(jx::object_member(my_ps, "paralyzed"), false);
    o.myConfused = jx::to_bool(jx::object_member(my_ps, "confused"), false);

    // V20: opponent-side fields for the B1 vectorizer.
    auto opp_discard = jx::object_member(opp_ps, "discard");
    o.oppDiscardCount = opp_discard.has_value() ? static_cast<int>(jx::array_items(*opp_discard).size()) : 0;
    o.oppPoisoned = jx::to_bool(jx::object_member(opp_ps, "poisoned"), false);
    o.oppBurned = jx::to_bool(jx::object_member(opp_ps, "burned"), false);
    o.oppAsleep = jx::to_bool(jx::object_member(opp_ps, "asleep"), false);
    o.oppParalyzed = jx::to_bool(jx::object_member(opp_ps, "paralyzed"), false);
    o.oppConfused = jx::to_bool(jx::object_member(opp_ps, "confused"), false);
  }

  auto options = jx::object_member(*select, "option");
  if (options.has_value()) {
    for (auto item : jx::array_items(*options)) {
      Option op;
      op.type = jx::to_int(jx::object_member(item, "type"), -1);
      op.number = jx::to_int(jx::object_member(item, "number"), -1);
      op.area = jx::to_int(jx::object_member(item, "area"), -1);
      op.index = jx::to_int(jx::object_member(item, "index"), -1);
      op.playerIndex = jx::to_int(jx::object_member(item, "playerIndex"), -1);
      op.toolIndex = jx::to_int(jx::object_member(item, "toolIndex"), -1);
      op.energyIndex = jx::to_int(jx::object_member(item, "energyIndex"), -1);
      op.count = jx::to_int(jx::object_member(item, "count"), -1);
      op.inPlayArea = jx::to_int(jx::object_member(item, "inPlayArea"), -1);
      op.inPlayIndex = jx::to_int(jx::object_member(item, "inPlayIndex"), -1);
      op.attackId = jx::to_int(jx::object_member(item, "attackId"), -1);
      op.cardId = jx::to_int(jx::object_member(item, "cardId"), -1);
      op.serial = jx::to_int(jx::object_member(item, "serial"), -1);
      op.specialConditionType = jx::to_int(jx::object_member(item, "specialConditionType"), -1);
      o.options.push_back(op);
    }
  }

  return o;
}

}  // namespace v17
