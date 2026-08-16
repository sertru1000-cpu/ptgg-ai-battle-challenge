"""BC pilot: a meta-deck opponent that plays like the HIGH-RATED humans'
agents from the real ladder (imitation ranker per archetype) instead of the
weak generic band policy. LOCAL BENCHMARK USE ONLY (loads xgboost at
inference; never shipped in a submission).

make_bc_pilot(tag, deck) -> agent(obs_dict) -> list[int]:
  - single-pick decisions: argmax of the archetype's BC ranker over options;
  - everything else (multi-pick, deck declare, errors): generic_policy_agent
    fallback (the same pilot the old gauntlet used -- so the DELTA between
    old and new gauntlets is exactly the single-pick policy quality).
"""

from __future__ import annotations

from pathlib import Path

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import all_attack, all_card_data, to_observation_class  # noqa: E402

from src.agents.common import select_top  # noqa: E402
from src.agents.generic_policy_agent import make_agent as make_generic  # noqa: E402
from src.ml.bc_features import option_features  # noqa: E402
from src.ml.vectorizer import ObservationVectorizer  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_card_table = {c.cardId: c for c in all_card_data()}
_attack_table = {a.attackId: a for a in all_attack()}


def make_bc_pilot(tag: str, deck: list[int]):
    import xgboost as xgb

    model = xgb.XGBClassifier()
    model.load_model(_REPO / "results" / "b1" / f"pilot_bc_{tag}.json")
    vec = ObservationVectorizer()
    fallback = make_generic(deck)
    stats = {"bc": 0, "fallback": 0, "errors": 0}

    def agent(obs_dict: dict) -> list[int]:
        try:
            if obs_dict.get("select") is None:
                return fallback(obs_dict)
            obs = to_observation_class(obs_dict)
            select = obs.select
            if select is None or select.maxCount != 1 or len(select.option) < 2:
                stats["fallback"] += 1
                return fallback(obs_dict)
            state_feats = vec.vectorize(obs)
            X = [state_feats + option_features(obs, o, _card_table, _attack_table)
                 for o in select.option]
            p = model.predict_proba(X)[:, 1]
            stats["bc"] += 1
            return select_top(select, select.context, [float(x) for x in p])
        except Exception:  # noqa: BLE001
            stats["errors"] += 1
            return fallback(obs_dict)

    agent.stats = stats  # type: ignore[attr-defined]
    agent.__name__ = f"bc_pilot_{tag}"
    return agent
