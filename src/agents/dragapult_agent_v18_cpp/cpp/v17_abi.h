// Shared binary contract between main_v17.py's `ctypes.Structure` definitions
// and this C++ library. This is the ONE root-decision observation per real
// Kaggle call -- Python already has `obs_dict` as parsed dicts (it never
// touched JSON text at all, kaggle_environments handed it a dict), so it
// flattens the handful of fields V6's heuristic/MCTS need into this struct
// and passes it by pointer via ctypes. No JSON parsing happens for this path
// on either side.
//
// (Contrast with json_extract.hpp: that parser exists ONLY for the DLL's
// SearchStep replies generated *inside* the C++ MCTS loop, which Python never
// sees -- a structurally different problem with a structurally different
// answer. See ../README.md.)
//
// CRITICAL: every field here must stay in the exact same order and exact
// same integer width on both sides. `#pragma pack(push, 1)` (mirrored by
// `_pack_ = 1` on the Python ctypes.Structure classes in py_wrapper.py)
// removes compiler-dependent padding as a variable entirely -- do not remove
// either side's pack pragma without updating the other. `abi_magic` is a
// cheap first line of defense: if the two sides' struct layouts ever drift
// out of sync, v17_choose_action rejects the call immediately instead of
// silently reading garbage into the heuristic.
//
// Every "absent/None" optional int field uses -1 as its sentinel. Checked
// against the real schema (cg/api.py) that every field using this sentinel
// has a value range of either "always >= 0" (index/count/id fields) or a
// small non-negative enum starting at 0 (e.g. SpecialConditionType 0..4) --
// -1 never collides with a real value anywhere this sentinel is used.
#pragma once

#include <cstdint>

#define V17_ABI_MAGIC 0x56313841  // "V18A" -- bumped from V17's 0x56313741 when the
                                  // oppHiddenPool fields were appended (Block A1)

#define V17_MAX_ENERGIES 12
#define V17_MAX_TOOLS 4
#define V17_MAX_PRE_EVO 3
#define V17_MAX_BENCH 8
#define V17_MAX_HAND 20
#define V17_MAX_DISCARD 64
#define V17_MAX_DECK_DISTINCT 60
#define V17_MAX_PRIZE 8
#define V17_MAX_OPTIONS 200
#define V17_MAX_OUT_INDICES 16
#define V17_MAX_SELECT_DECK 60
#define V17_MAX_LOOKING 20
#define V17_MAX_OPP_POOL 60

#pragma pack(push, 1)

typedef struct {
  int32_t present;    // 0 if this slot has no Pokemon at all (empty active/bench slot)
  int32_t faceDown;   // 1 if present but identity hidden (opponent's face-down Pokemon) -- all fields below are 0 in that case
  int32_t id;
  int32_t serial;
  int32_t hp;
  int32_t maxHp;
  int32_t appearThisTurn;
  int32_t energiesCount;
  int32_t energies[V17_MAX_ENERGIES];
  int32_t energyCardsCount;
  int32_t energyCardIds[V17_MAX_ENERGIES];
  int32_t toolsCount;
  int32_t toolIds[V17_MAX_TOOLS];
  int32_t preEvoCount;
  int32_t preEvoIds[V17_MAX_PRE_EVO];
} V17PokemonC;

typedef struct {
  int32_t id;
  int32_t serial;
  int32_t playerIndex;
} V17CardC;

typedef struct {
  int32_t type;   // OptionType (cg.api.OptionType integer value)
  int32_t number;
  int32_t area;
  int32_t index;
  int32_t playerIndex;
  int32_t toolIndex;
  int32_t energyIndex;
  int32_t count;
  int32_t inPlayArea;
  int32_t inPlayIndex;
  int32_t attackId;
  int32_t cardId;
  int32_t serial;
  int32_t specialConditionType;
} V17OptionC;

typedef struct {
  int32_t abi_magic;  // must equal V17_ABI_MAGIC -- checked first, see file header

  int32_t myIndex;
  int32_t turn;
  int32_t firstPlayer;
  int32_t supporterPlayed;
  int32_t stadiumPlayed;
  int32_t energyAttached;
  int32_t retreated;
  int32_t result;          // -1 if the match has not concluded
  int32_t stadiumCardId;   // 0 if no stadium in play

  int32_t selectType;
  int32_t context;         // SelectContext
  int32_t minCount;
  int32_t maxCount;
  int32_t remainDamageCounter;
  int32_t remainEnergyCost;
  int32_t contextCardId;   // 0 if select.contextCard is None
  int32_t effectCardId;    // 0 if select.effect is None

  int32_t myDeckCount;
  int32_t oppDeckCount;
  int32_t myPrizeCount;
  int32_t oppPrizeCount;
  int32_t oppHandCount;

  int32_t myPoisoned;
  int32_t myBurned;
  int32_t myAsleep;
  int32_t myParalyzed;
  int32_t myConfused;

  // Bookkeeping computed in Python (see main_v17.py's small ported preamble,
  // mirroring dragapult_policy_v6.py's pre_turn_log scan) -- both require
  // state that persists across calls within our own turn, which is cheap and
  // already implemented/validated in the existing Python module, so it is
  // NOT reimplemented in C++. Nothing about this data changes per simulated
  // MCTS branch (it describes what happened before this decision, not a
  // hypothetical future), so computing it once in Python per real decision
  // is correct and free of the performance concerns that motivate C++ for
  // the rollout loop itself.
  int32_t preKo;
  int32_t noItem;

  V17PokemonC myActive;
  V17PokemonC oppActive;

  int32_t myBenchCount;
  V17PokemonC myBench[V17_MAX_BENCH];
  int32_t oppBenchCount;
  V17PokemonC oppBench[V17_MAX_BENCH];

  int32_t myHandCount;
  V17CardC myHand[V17_MAX_HAND];

  int32_t myDiscardCount;
  V17CardC myDiscard[V17_MAX_DISCARD];

  // select.deck: cards visible via a deck-facing select (cg.api.py:
  // "None unless selecting cards from the deck") -- NOT only the initial
  // deck-declare exchange (which never reaches this struct at all, handled
  // entirely in Python before native_choose_action is called), but ALSO any
  // later decision where AreaType.DECK options reference these cards
  // directly (e.g. a search-your-deck effect). get_card()-equivalent
  // resolution for AreaType.DECK indexes into this list.
  int32_t selectDeckCount;
  V17CardC selectDeck[V17_MAX_SELECT_DECK];

  // Actual prize-card objects when their identity is currently visible (a
  // taken/revealed prize) -- NOT the same as myPrizeGuessIds below (an
  // identity GUESS used for hidden-info determinization). A None/face-down
  // slot is encoded as id=0 (a real card id is never 0 in this game's ID
  // space) at its ORIGINAL index position -- positions must stay aligned
  // with what Option.index refers to, entries are never skipped/compacted.
  int32_t myPrizeCardsCount;
  V17CardC myPrizeCards[V17_MAX_PRIZE];

  // state.looking: cards currently being revealed by a search/look effect
  // (cg/api.py: "None if not looking cards"). Same id=0 sentinel/positional
  // rule as myPrizeCards above.
  int32_t lookingCount;
  V17CardC looking[V17_MAX_LOOKING];

  // Sparse (card_id, remaining_count) pairs describing "what's still in my
  // deck", per V6's own set_card_counts bookkeeping (DECK minus everything
  // currently visible minus the prize guess below) -- computed in Python
  // (cheap, O(deck size)=60 per real decision) and handed over already
  // resolved, rather than re-deriving DECK-minus-visible in C++.
  int32_t deckDistinctCount;
  int32_t deckIds[V17_MAX_DECK_DISTINCT];
  int32_t deckCounts[V17_MAX_DECK_DISTINCT];

  // Our own prize-card-identity guess (fixed once at the deck-declare call,
  // held constant thereafter, exactly mirroring V6's self.prize) -- used both
  // by the heuristic's hand_score() logic and as the `your_prize` argument to
  // the native engine's SearchBegin.
  int32_t myPrizeGuessCount;
  int32_t myPrizeGuessIds[V17_MAX_PRIZE];

  int32_t optionCount;
  V17OptionC options[V17_MAX_OPTIONS];

  // Block A1 (V18): the ready-to-deal sampling pool for the OPPONENT's hidden
  // zones (deck + hand + prizes), already fully resolved by Python: the
  // classified archetype's canonical 60-card list (or our own deck as the
  // mirror fallback) minus every opponent card visible on the board and in
  // their discard. The native side must use it VERBATIM (shuffle + deal, pad
  // with the energy filler if short) -- no further visible-board subtraction,
  // that has already been done. Count 0 => Python could not build a pool
  // (defensive); the native side then falls back to V17's own mirror-minus-
  // visible-board logic.
  int32_t oppHiddenPoolCount;
  int32_t oppHiddenPoolIds[V17_MAX_OPP_POOL];
} V17RootObservationC;

#pragma pack(pop)
