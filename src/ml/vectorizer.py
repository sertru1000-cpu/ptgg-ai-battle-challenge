"""ObservationVectorizer -- turns a cg.api.Observation into a fixed-length list[float].

Safe to use both OFFLINE (training, on an Observation built from raw replay JSON via
cg.api.to_observation_class) and ONLINE (live agent inference, same object shape).

CRITICAL invariants:
  - Never raises on missing/hidden data. The opponent's `hand` is always None, and PRIZE
    entries are None (face-down) whether the observer's own or the opponent's, until
    actually revealed -- these become the MISSING sentinel below, never guessed at.
  - `cg/utils.py::to_dataclass` leaves IntEnum-typed fields (SelectContext, EnergyType,
    OptionType, ...) as plain ints, not enum instances -- so mapping them to float is
    just `float(x)`, no risk of an unknown-future-value ValueError from an enum
    constructor. `_enum()` below only has to guard against None.
  - Output length is always FEATURE_COUNT and the order always matches FEATURE_NAMES,
    regardless of which fields were present in a given Observation.
"""
from __future__ import annotations

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import CardData, Observation, Pokemon, all_card_data  # noqa: E402

MISSING = -1.0  # sentinel: "no such enum/id/card/Pokemon here" -- never a legal value
_card_table_cache: dict[int, CardData] | None = None


def _card_table() -> dict[int, CardData]:
    global _card_table_cache
    if _card_table_cache is None:
        _card_table_cache = {c.cardId: c for c in all_card_data()}
    return _card_table_cache


def _b(x) -> float:
    """Bool/None -> 0.0/1.0, None counts as falsy (not missing -- a real 'no' answer)."""
    return 1.0 if x else 0.0


def _n(x, default: float = 0.0) -> float:
    """Numeric field, None -> default (0.0 unless a count/measure that's meaningfully absent)."""
    return float(x) if x is not None else default


def _enum(x) -> float:
    """IntEnum-typed field (already a plain int per to_dataclass) -- None -> MISSING."""
    return float(x) if x is not None else MISSING


POKEMON_FEATURES = [
    "id", "hp", "maxHp", "hp_fraction", "appearThisTurn",
    "energy_count", "energy_card_count", "tool_count", "pre_evolution_count",
    "retreat_cost", "base_hp", "weakness", "resistance", "energy_type",
    "stage", "is_ex", "is_mega_ex", "is_tera", "is_ace_spec",
]


def _pokemon_features(p: Pokemon | None) -> list[float]:
    if p is None:
        return [MISSING] * len(POKEMON_FEATURES)

    data = _card_table().get(p.id)
    stage = MISSING
    is_ex = is_mega = tera = ace = MISSING
    retreat_cost = base_hp = weakness = resistance = energy_type = MISSING
    if data is not None:
        stage = 2.0 if data.stage2 else 1.0 if data.stage1 else (0.0 if data.basic else MISSING)
        is_ex = _b(data.ex)
        is_mega = _b(data.megaEx)
        tera = _b(data.tera)
        ace = _b(data.aceSpec)
        retreat_cost = _n(data.retreatCost)
        base_hp = _n(data.hp)
        weakness = _enum(data.weakness)
        resistance = _enum(data.resistance)
        energy_type = _enum(data.energyType)

    return [
        _n(p.id, MISSING),
        _n(p.hp),
        _n(p.maxHp),
        (p.hp / p.maxHp) if p.maxHp else 0.0,
        _b(p.appearThisTurn),
        float(len(p.energies or [])),
        float(len(p.energyCards or [])),
        float(len(p.tools or [])),
        float(len(p.preEvolution or [])),
        retreat_cost, base_hp, weakness, resistance, energy_type,
        stage, is_ex, is_mega, tera, ace,
    ]


PLAYER_FEATURES = (
    [f"active_{n}" for n in POKEMON_FEATURES]
    + ["bench_count", "bench_hp_sum", "bench_hp_mean", "bench_energy_sum", "bench_tool_sum"]
    + ["hand_count", "deck_count", "discard_count", "prize_count", "prize_revealed_count"]
    + ["poisoned", "burned", "asleep", "paralyzed", "confused"]
)


def _player_features(ps) -> list[float]:
    if ps is None:
        return [MISSING] * len(PLAYER_FEATURES)

    active = ps.active[0] if ps.active else None
    active_feats = _pokemon_features(active)

    bench = ps.bench or []
    bench_hps = [p.hp for p in bench]
    bench_feats = [
        float(len(bench)),
        float(sum(bench_hps)),
        (sum(bench_hps) / len(bench_hps)) if bench_hps else 0.0,
        float(sum(len(p.energies or []) for p in bench)),
        float(sum(len(p.tools or []) for p in bench)),
    ]

    prize = ps.prize or []
    count_feats = [
        _n(ps.handCount),
        _n(ps.deckCount),
        float(len(ps.discard or [])),
        float(len(prize)),
        float(sum(1 for c in prize if c is not None)),
    ]

    status_feats = [_b(ps.poisoned), _b(ps.burned), _b(ps.asleep), _b(ps.paralyzed), _b(ps.confused)]

    return active_feats + bench_feats + count_feats + status_feats


GLOBAL_FEATURES = [
    "turn", "turn_action_count", "your_index", "first_player",
    "supporter_played", "stadium_played", "energy_attached", "retreated",
    "result", "stadium_card_id", "looking_count",
]

SELECT_FEATURES = [
    "select_present", "select_type", "select_context", "select_min_count",
    "select_max_count", "select_option_count", "select_remain_damage_counter",
    "select_remain_energy_cost",
]

FEATURE_NAMES = (
    GLOBAL_FEATURES
    + SELECT_FEATURES
    + [f"self_{n}" for n in PLAYER_FEATURES]
    + [f"opp_{n}" for n in PLAYER_FEATURES]
)
FEATURE_COUNT = len(FEATURE_NAMES)


class ObservationVectorizer:
    """Stateless (aside from the module-level card-data cache). One public method."""

    feature_names = FEATURE_NAMES
    feature_count = FEATURE_COUNT

    def vectorize(self, obs: Observation) -> list[float]:
        current = getattr(obs, "current", None)
        select = getattr(obs, "select", None)

        if current is None:
            global_feats = [MISSING] * len(GLOBAL_FEATURES)
            self_feats = [MISSING] * len(PLAYER_FEATURES)
            opp_feats = [MISSING] * len(PLAYER_FEATURES)
        else:
            stadium = current.stadium[0] if current.stadium else None
            global_feats = [
                _n(current.turn),
                _n(current.turnActionCount),
                _n(current.yourIndex, MISSING),
                _n(current.firstPlayer, MISSING),
                _b(current.supporterPlayed),
                _b(current.stadiumPlayed),
                _b(current.energyAttached),
                _b(current.retreated),
                _n(current.result, MISSING),
                _n(stadium.id if stadium is not None else None, MISSING),
                float(len(current.looking)) if current.looking is not None else 0.0,
            ]

            your_index = current.yourIndex if current.yourIndex in (0, 1) else None
            players = current.players or []
            self_ps = players[your_index] if your_index is not None and your_index < len(players) else None
            opp_ps = (
                players[1 - your_index]
                if your_index is not None and (1 - your_index) < len(players)
                else None
            )
            self_feats = _player_features(self_ps)
            opp_feats = _player_features(opp_ps)

        if select is None:
            select_feats = [0.0] + [MISSING] * (len(SELECT_FEATURES) - 1)
        else:
            select_feats = [
                1.0,
                _enum(select.type),
                _enum(select.context),
                _n(select.minCount),
                _n(select.maxCount),
                float(len(select.option or [])),
                _n(select.remainDamageCounter),
                _n(select.remainEnergyCost),
            ]

        vec = global_feats + select_feats + self_feats + opp_feats
        assert len(vec) == FEATURE_COUNT, f"vector length {len(vec)} != FEATURE_COUNT {FEATURE_COUNT}"
        return vec
