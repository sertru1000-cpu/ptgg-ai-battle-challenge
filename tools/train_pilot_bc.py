"""Trains the 3 per-archetype BC pilot rankers (local benchmark use only --
xgboost stays the inference engine, no export needed).

Input: results/b1/pilot_bc_<tag>.parquet (tools/build_pilot_bc_datasets.py).
Output: results/b1/pilot_bc_<tag>.json + one-line metrics per pilot.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "results" / "b1"
TAGS = ["grimmsnarl", "kangaskhan", "fezandipiti"]


def main() -> None:
    import numpy as np
    import pandas as pd
    import xgboost as xgb

    for tag in TAGS:
        df = pd.read_parquet(OUT_DIR / f"pilot_bc_{tag}.parquet")
        feat_cols = [c for c in df.columns if (c[0] in "so") and c[1:].isdigit()]
        df["group"] = df["episode_id"].astype(str) + "/" + df["step"].astype(str) + "/" + df["player"].astype(str)
        eps = np.array(sorted(set(df["episode_id"].astype(str))))
        rng = np.random.default_rng(42)
        rng.shuffle(eps)
        valid_eps = set(eps[: max(1, len(eps) // 5)])
        is_valid = df["episode_id"].astype(str).isin(valid_eps)
        tr, va = df[~is_valid], df[is_valid]

        model = xgb.XGBClassifier(
            n_estimators=400, max_depth=7, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
            eval_metric="logloss", early_stopping_rounds=30, n_jobs=4,
        )
        model.fit(tr[feat_cols], tr["chosen"], eval_set=[(va[feat_cols], va["chosen"])], verbose=False)

        va2 = va[["group", "chosen"]].copy()
        va2["p"] = model.predict_proba(va[feat_cols])[:, 1]
        top1 = first = 0
        groups = 0
        for _, g in va2.groupby("group", sort=False):
            groups += 1
            top1 += int(g.loc[g["p"].idxmax(), "chosen"] == 1)
            first += int(g.iloc[0]["chosen"] == 1)
        model.save_model(OUT_DIR / f"pilot_bc_{tag}.json")
        print(f"{tag}: rows={len(df)} decisions={df['group'].nunique()} "
              f"top1={top1 / max(1, groups):.3f} (first-option baseline {first / max(1, groups):.3f}) "
              f"best_iter={model.best_iteration}")


if __name__ == "__main__":
    main()
