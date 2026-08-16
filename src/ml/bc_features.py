"""Shared option-level featurization for the V21 leader-imitation (BC)
model. MUST stay identical between training (tools/build_bc_dataset.py) and
inference (src/agents/dragapult_policy_v21.py) -- any drift silently breaks
the model's input contract. The 16 features here are appended after the 87
state features from src/ml/vectorizer.py.
"""

from __future__ import annotations

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import AreaType, Observation  # noqa: E402

from src.agents.common import get_card  # noqa: E402

OPTION_FEATURES = [
    "o_type", "o_area", "o_index", "o_player_is_self", "o_count", "o_number",
    "o_attack_id", "o_attack_damage", "o_attack_cost", "o_in_play_area",
    "o_card_id", "o_card_type", "o_card_hp", "o_card_stage", "o_card_is_ex",
    "o_card_is_pokemon",
]


def option_features(obs: Observation, option, card_table, attack_table) -> list[float]:
    my_index = obs.current.yourIndex
    o_type = float(int(option.type))
    o_area = float(int(option.area)) if option.area is not None else -1.0
    o_index = float(option.index) if option.index is not None else -1.0
    o_player = 1.0 if (option.playerIndex is None or option.playerIndex == my_index) else 0.0
    o_count = float(option.count) if option.count is not None else -1.0
    o_number = float(option.number) if option.number is not None else -1.0
    o_attack_id = float(option.attackId) if option.attackId is not None else -1.0
    atk = attack_table.get(option.attackId) if option.attackId is not None else None
    o_attack_damage = float(atk.damage) if atk is not None else -1.0
    o_attack_cost = float(len(atk.energies)) if atk is not None else -1.0
    o_in_play_area = float(int(option.inPlayArea)) if option.inPlayArea is not None else -1.0

    card_id = -1.0
    card_type = -1.0
    card_hp = -1.0
    card_stage = -1.0
    card_is_ex = -1.0
    card_is_pokemon = -1.0
    try:
        card = None
        if option.area is not None and option.index is not None:
            card = get_card(obs, option.area, option.index, option.playerIndex if option.playerIndex is not None else my_index)
        elif option.type is not None and int(option.type) == 7 and option.index is not None:  # PLAY from hand
            card = get_card(obs, AreaType.HAND, option.index, my_index)
        if card is not None:
            card_id = float(card.id)
            data = card_table.get(card.id)
            if data is not None:
                card_type = float(int(data.cardType))
                card_hp = float(data.hp)
                card_stage = 2.0 if data.stage2 else 1.0 if data.stage1 else 0.0
                card_is_ex = 1.0 if (data.ex or data.megaEx) else 0.0
                card_is_pokemon = 1.0 if int(data.cardType) == 0 else 0.0
    except Exception:  # noqa: BLE001 -- resolution quirks must not kill the row
        pass
    return [o_type, o_area, o_index, o_player, o_count, o_number, o_attack_id,
            o_attack_damage, o_attack_cost, o_in_play_area,
            card_id, card_type, card_hp, card_stage, card_is_ex, card_is_pokemon]
