"""Phase 2 Objective 1: train an XGBoost win-probability classifier on the Phase 1
vectorized dataset (results/ml/vectorizer_pilot_sample.parquet, from src/ml/extractor.py).

Split is done by episode_id (group split), NOT by row: rows from the same episode are
highly correlated (same game, both players' perspectives, adjacent turns share almost
all board state) -- a naive random row-level 80/20 split would put near-duplicate states
from one game on both sides of the split and overstate validation AUC. scikit-learn has
no built-in "split by group, no CV, single holdout" one-liner, so this is done directly.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, roc_auc_score

from src.ml.vectorizer import FEATURE_NAMES, MISSING

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "results" / "ml" / "vectorizer_pilot_sample.parquet"
MODEL_PATH = REPO_ROOT / "src" / "agents" / "xgb_model.json"
META_PATH = MODEL_PATH.with_suffix(".meta.json")
VAL_FRACTION = 0.2
RANDOM_SEED = 42

HYPERPARAMS = dict(
    max_depth=4,
    n_estimators=100,
    learning_rate=0.1,
    objective="binary:logistic",
    eval_metric="logloss",
    missing=MISSING,
    n_jobs=4,
    random_state=RANDOM_SEED,
)


def group_split(episode_ids: pd.Series, val_fraction: float, seed: int) -> tuple[set, set]:
    """Shuffle unique episode_ids and split at the episode level."""
    unique_ids = sorted(episode_ids.unique().tolist())
    rng = random.Random(seed)
    rng.shuffle(unique_ids)
    n_val = max(1, round(len(unique_ids) * val_fraction))
    val_ids = set(unique_ids[:n_val])
    train_ids = set(unique_ids[n_val:])
    return train_ids, val_ids


def main() -> int:
    if not DATASET_PATH.exists():
        print(f"Dataset not found at {DATASET_PATH} -- run `python -m src.ml.extractor` first (Phase 1).")
        return 1

    df = pd.read_parquet(DATASET_PATH)
    print(f"Loaded {len(df)} rows x {len(df.columns)} cols from {DATASET_PATH}")

    missing_features = [c for c in FEATURE_NAMES if c not in df.columns]
    if missing_features:
        print(f"ERROR: dataset missing {len(missing_features)} expected feature columns: {missing_features[:10]}")
        return 1

    train_ids, val_ids = group_split(df["episode_id"], VAL_FRACTION, RANDOM_SEED)
    train_df = df[df["episode_id"].isin(train_ids)]
    val_df = df[df["episode_id"].isin(val_ids)]
    print(
        f"Episodes: {df['episode_id'].nunique()} total -> "
        f"{len(train_ids)} train / {len(val_ids)} val (split by episode_id, not row, to avoid leakage)"
    )
    print(f"Rows: {len(train_df)} train / {len(val_df)} val")

    X_train = train_df[FEATURE_NAMES].to_numpy(dtype=np.float32)
    y_train = train_df["label"].to_numpy(dtype=np.float32)
    X_val = val_df[FEATURE_NAMES].to_numpy(dtype=np.float32)
    y_val = val_df["label"].to_numpy(dtype=np.float32)

    model = xgb.XGBClassifier(**HYPERPARAMS)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    val_proba = model.predict_proba(X_val)[:, 1]
    val_pred = (val_proba >= 0.5).astype(int)

    auc = float(roc_auc_score(y_val, val_proba))
    acc = float(accuracy_score(y_val, val_pred))

    print("=" * 70)
    print("PHASE 2 OBJECTIVE 1: TRAINING REPORT")
    print("=" * 70)
    print(f"Hyperparameters: {HYPERPARAMS}")
    print(f"Train rows: {len(X_train)}  Val rows: {len(X_val)}")
    print(f"Validation ROC-AUC:  {auc:.4f}")
    print(f"Validation Accuracy: {acc:.4f}")
    print("=" * 70)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(MODEL_PATH))
    print(f"Saved model -> {MODEL_PATH}")

    meta = {
        "feature_names": FEATURE_NAMES,
        "feature_count": len(FEATURE_NAMES),
        "missing_sentinel": MISSING,
        "train_rows": len(X_train),
        "val_rows": len(X_val),
        "train_episodes": len(train_ids),
        "val_episodes": len(val_ids),
        "val_roc_auc": auc,
        "val_accuracy": acc,
        "hyperparameters": {k: v for k, v in HYPERPARAMS.items() if k != "missing"} | {"missing": MISSING},
    }
    META_PATH.write_text(json.dumps(meta, indent=2))
    print(f"Saved metadata -> {META_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
