"""V21/BC dataset: (state, option, was_chosen) rows from the top-100
Dragapult teams' OWN decisions in their real ladder episodes -- the training
set for a behavioral-cloning ranker (imitate 1041-1217-rated play directly,
rather than learn a value function from it as B1 did).

Row = one legal option at one real decision of a leader team:
  87 state features (src/ml/vectorizer.py, same as B1)
  + option features (type/area/index/count/attackId + resolved card props)
  + label: 1 if this is (one of) the option(s) the leader actually picked.
Group id (episode_id, step) allows listwise/grouped evaluation: the model's
argmax within a group should be the chosen option (top-1 accuracy).

Only decisions by the 19 known top-100 Dragapult TEAMS (results/top100_audit/
leaderboard_decks.csv) are kept -- their opponents' play is NOT imitation-
worthy. maxCount==1 decisions only (single-pick; multi-pick selects like
Phantom Dive counter spreads have combinatorial action spaces -- deferred,
the V19 heuristic keeps handling those at inference).

Usage:
    python tools/build_bc_dataset.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import AreaType, Observation, to_observation_class  # noqa: E402

from src.agents.common import get_card  # noqa: E402
from src.ml.vectorizer import ObservationVectorizer  # noqa: E402

EPISODE_DIRS = [
    REPO_ROOT / "data" / "leader_episodes",
    REPO_ROOT / "data" / "top100_audit" / "replays",
]
LEADERBOARD_CSV = REPO_ROOT / "results" / "top100_audit" / "leaderboard_decks.csv"
OUT_DIR = REPO_ROOT / "results" / "b1"

# Option-level feature names (order is the contract with the exporter/agent).
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


def main() -> None:
    import pandas as pd
    from cg.api import all_attack, all_card_data

    card_table = {c.cardId: c for c in all_card_data()}
    attack_table = {a.attackId: a for a in all_attack()}
    vec = ObservationVectorizer()

    rows_lb = list(csv.DictReader(open(LEADERBOARD_CSV, encoding="utf-8")))
    leader_teams = {r["team_name"] for r in rows_lb if "Dragapult" in r.get("archetype", "")}
    print(f"Leader Dragapult teams: {len(leader_teams)}")

    files: list[Path] = []
    seen: set[str] = set()
    for d in EPISODE_DIRS:
        if d.exists():
            for p in sorted(d.glob("episode-*-replay.json")):
                if p.name not in seen:
                    seen.add(p.name)
                    files.append(p)

    all_rows: list[dict] = []
    n_decisions = 0
    bad = 0
    for fi, path in enumerate(files):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            team_names = data.get("info", {}).get("TeamNames", [None, None])
            episode_id = str(data.get("info", {}).get("EpisodeId", path.stem))
            leader_sides = [pi for pi in (0, 1) if team_names[pi] in leader_teams]
            if not leader_sides:
                continue
            for step_i, step in enumerate(data["steps"]):
                for pi in leader_sides:
                    obs_dict = step[pi].get("observation")
                    action = step[pi].get("action")
                    if not obs_dict or obs_dict.get("select") is None or not action:
                        continue
                    if isinstance(action, list) and len(action) == 60:
                        continue  # deck declare
                    try:
                        obs = to_observation_class(obs_dict)
                    except Exception:  # noqa: BLE001
                        continue
                    select = obs.select
                    if select is None or select.maxCount != 1 or len(select.option) < 2:
                        continue
                    chosen = set(int(a) for a in action if isinstance(a, (int, float)))
                    if not chosen or max(chosen) >= len(select.option):
                        continue
                    state_feats = vec.vectorize(obs)
                    n_decisions += 1
                    for oi, option in enumerate(select.option):
                        of = option_features(obs, option, card_table, attack_table)
                        all_rows.append({
                            "episode_id": episode_id,
                            "step": step_i,
                            "player": pi,
                            "team": team_names[pi],
                            "option_i": oi,
                            "chosen": 1 if oi in chosen else 0,
                            **{f"s{j}": v for j, v in enumerate(state_feats)},
                            **{f"o{j}": v for j, v in enumerate(of)},
                        })
        except Exception as ex:  # noqa: BLE001
            bad += 1
            print(f"  [skip] {path.name}: {ex}")
        if (fi + 1) % 100 == 0:
            print(f"[{fi + 1}/{len(files)}] decisions={n_decisions} rows={len(all_rows)} bad={bad}", flush=True)

    df = pd.DataFrame(all_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "bc_dataset.parquet"
    df.to_parquet(out, index=False)
    print(f"Wrote {out}: {len(df)} option-rows, {n_decisions} decisions, "
          f"{df['episode_id'].nunique()} episodes, mean options/decision "
          f"{len(df) / max(1, n_decisions):.1f}")


if __name__ == "__main__":
    main()
