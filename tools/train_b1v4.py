"""B1v4: P(win) trained on a STRATIFIED sample of the real pool
(weak/mid/strong min_score quantile tiers, data/tiered_episodes/) -- the
"должна быть выборка из сильных, средних и слабых" recipe, executed.

Deliverable: results/b1/b1v4_report.md with the money table --
per-tier valid AUC for B1v4 vs B1v1 (leaders-only) evaluated on the SAME
validation games. Expectation being tested: B1v1 degrades on the weak tier
(coverage gap that cost us the Lucario-cluster losses); B1v4 holds across
tiers.

Usage:
    python tools/train_b1v4.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import to_observation_class  # noqa: E402

from src.ml.vectorizer import ObservationVectorizer  # noqa: E402

TIER_DIR = REPO_ROOT / "data" / "tiered_episodes"
B1_DIR = REPO_ROOT / "results" / "b1"


def episode_rows(path: Path, vec: ObservationVectorizer, tier: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rewards = data.get("rewards") or [None, None]
    r0, r1 = rewards[0], rewards[1]
    if r0 == 1 and r1 == -1:
        winner = 0
    elif r1 == 1 and r0 == -1:
        winner = 1
    else:
        return []
    episode_id = str(data.get("info", {}).get("EpisodeId", path.stem))
    rows = []
    for step in data["steps"]:
        for pi in (0, 1):
            obs_dict = step[pi].get("observation")
            action = step[pi].get("action")
            if not obs_dict or obs_dict.get("select") is None or not action:
                continue
            if isinstance(action, list) and len(action) == 60:
                continue
            try:
                obs = to_observation_class(obs_dict)
                feats = vec.vectorize(obs)
            except Exception:  # noqa: BLE001
                continue
            rows.append({
                "episode_id": episode_id, "tier": tier, "player": pi,
                "label_win": 1 if winner == pi else 0,
                **{f"f{j}": v for j, v in enumerate(feats)},
            })
    return rows


def main() -> None:
    import numpy as np
    import pandas as pd
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    # Tiers are pre-extracted to per-tier parquet parts (raw JSONs discarded
    # after a verified write -- the disk-budget workflow this run enforced).
    parts = []
    for tier in ("weak", "mid", "strong"):
        part = pd.read_parquet(B1_DIR / f"b1v4_part_{tier}.parquet")
        print(f"{tier}: rows={len(part)} episodes={part.episode_id.nunique()}")
        parts.append(part)
    df = pd.concat(parts, ignore_index=True)
    feat_cols = [f"f{i}" for i in range(87)]
    print(f"total rows={len(df)} episodes={df.episode_id.nunique()}")

    rng = np.random.default_rng(42)
    eps = np.array(sorted(set(df["episode_id"])))
    rng.shuffle(eps)
    valid_eps = set(eps[: max(1, len(eps) // 5)].tolist())
    is_valid = df["episode_id"].isin(valid_eps)
    tr, va = df[~is_valid], df[is_valid]
    print(f"train {len(tr)} / valid {len(va)}")

    model = xgb.XGBClassifier(
        n_estimators=500, max_depth=6, learning_rate=0.08,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        eval_metric="logloss", early_stopping_rounds=40, n_jobs=4,
    )
    model.fit(tr[feat_cols], tr["label_win"], eval_set=[(va[feat_cols], va["label_win"])], verbose=100)
    model.save_model(B1_DIR / "xgb_pwin_v4.json")

    b1v1 = xgb.XGBClassifier()
    b1v1.load_model(B1_DIR / "xgb_pwin.json")

    lines = ["# B1v4 (stratified real-pool) vs B1v1 (leaders-only)", "",
             f"training rows={len(tr)}, episodes={df.episode_id.nunique()}, valid rows={len(va)}", "",
             "| tier | n valid | B1v4 AUC | B1v1 AUC |", "|---|---|---|---|"]
    p4 = model.predict_proba(va[feat_cols])[:, 1]
    p1 = b1v1.predict_proba(va[feat_cols])[:, 1]
    y = va["label_win"].to_numpy()
    tiers_np = va["tier"].to_numpy()
    for tier in ("weak", "mid", "strong", None):
        mask = np.ones(len(va), dtype=bool) if tier is None else (tiers_np == tier)
        label = tier or "ALL"
        if mask.sum() > 500 and len(set(y[mask])) == 2:
            a4 = roc_auc_score(y[mask], p4[mask])
            a1 = roc_auc_score(y[mask], p1[mask])
            lines.append(f"| {label} | {int(mask.sum())} | {a4:.4f} | {a1:.4f} |")
    report = "\n".join(lines)
    (B1_DIR / "b1v4_report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
