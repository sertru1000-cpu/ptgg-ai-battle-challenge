"""B1 model training: P(win | decision state) from top-level demonstrations.

Input: results/b1/dataset.parquet (tools/build_b1_dataset.py). Trains an
XGBoost binary classifier with EPISODE-level splits (never split one game's
states across train/valid -- states within an episode share the label and are
heavily correlated; a row-level split would leak and overstate AUC, the same
class of mistake this project's rating-resolution work already documented).

Reports: valid AUC, log-loss, calibration-by-decile, and AUC as a function of
turn number (early-game states are genuinely harder -- a model that only
learns "6 prizes left at turn 20 means winning" is useless as an eval; the
turn-stratified AUC is the honest capability measure for MCTS-eval use).

Outputs:
  results/b1/xgb_pwin.json         -- the trained model (xgboost native)
  results/b1/train_report.md       -- metrics
  results/b1/pwin_trees.py         -- dependency-free Python export of the
                                      ensemble (nested if/else on f{i}), for
                                      an agent that must not import xgboost
                                      at inference time (Kaggle grader may
                                      not install requirements.txt -- the
                                      V16 gamble, not repeated).

Usage:
    python tools/train_b1_model.py [--dragapult-side-only]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "results" / "b1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dragapult-side-only", action="store_true")
    parser.add_argument("--valid-frac", type=float, default=0.2)
    parser.add_argument("--n-estimators", type=int, default=400)
    parser.add_argument("--max-depth", type=int, default=6)
    args = parser.parse_args()

    import numpy as np
    import pandas as pd
    import xgboost as xgb
    from sklearn.metrics import log_loss, roc_auc_score

    df = pd.read_parquet(OUT_DIR / "dataset.parquet")
    if args.dragapult_side_only and "plays_dragapult" in df.columns:
        df = df[df["plays_dragapult"]].reset_index(drop=True)
    feat_cols = [c for c in df.columns if c.startswith("f")]
    print(f"rows={len(df)} episodes={df['episode_id'].nunique()} features={len(feat_cols)} "
          f"win_rate={df['label_win'].mean():.3f}")

    rng = np.random.default_rng(42)
    episodes = np.array([str(e) for e in df["episode_id"].unique()])  # plain numpy: Arrow-backed arrays shuffle unreliably
    rng.shuffle(episodes)
    n_valid = max(1, int(len(episodes) * args.valid_frac))
    valid_eps = set(episodes[:n_valid])
    is_valid = df["episode_id"].isin(valid_eps)
    tr, va = df[~is_valid], df[is_valid]
    print(f"train: {len(tr)} rows / {df['episode_id'].nunique() - n_valid} eps; "
          f"valid: {len(va)} rows / {n_valid} eps (episode-level split)")

    model = xgb.XGBClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        eval_metric="logloss",
        early_stopping_rounds=30,
        n_jobs=4,
    )
    model.fit(tr[feat_cols], tr["label_win"], eval_set=[(va[feat_cols], va["label_win"])], verbose=50)

    p = model.predict_proba(va[feat_cols])[:, 1]
    auc = roc_auc_score(va["label_win"], p)
    ll = log_loss(va["label_win"], p)
    lines = ["# B1 P(win) training report", "",
             f"rows={len(df)}, episodes={df['episode_id'].nunique()}, features={len(feat_cols)}",
             f"valid AUC={auc:.4f}  log_loss={ll:.4f}  best_iteration={model.best_iteration}", ""]

    lines.append("## AUC by turn bucket (valid)")
    va2 = va.assign(p=p)
    for lo, hi in [(0, 2), (3, 5), (6, 9), (10, 14), (15, 99)]:
        m = va2[(va2["turn"] >= lo) & (va2["turn"] <= hi)]
        if len(m) > 100 and m["label_win"].nunique() == 2:
            lines.append(f"- turns {lo}-{hi}: AUC={roc_auc_score(m['label_win'], m['p']):.4f} (n={len(m)})")
    lines.append("")
    lines.append("## Calibration by predicted-probability decile (valid)")
    va2["bucket"] = pd.qcut(va2["p"], 10, labels=False, duplicates="drop")
    for b, grp in va2.groupby("bucket"):
        lines.append(f"- decile {b}: pred_mean={grp['p'].mean():.3f} actual={grp['label_win'].mean():.3f} n={len(grp)}")

    model.save_model(OUT_DIR / "xgb_pwin.json")

    # Dependency-free export: every tree as nested if/else over f{i} features.
    booster = model.get_booster()
    dumped = booster.get_dump(dump_format="json")
    # Newer xgboost fits base_score to the label mean; the dumped trees carry
    # only the deltas, so the exported sum must start from logit(base_score)
    # (this was the 0.037 parity error on the first run -- caught by the
    # parity check below, exactly what it exists for).
    cfg = json.loads(booster.save_config())
    # base_score is serialized as a bracketed vector string, e.g. '[5.002261E-1]'
    base_score = float(cfg["learner"]["learner_model_param"]["base_score"].strip("[]"))
    base_score_offset = float(np.log(base_score / (1.0 - base_score)))
    # Early stopping: predict_proba scores with trees [0, best_iteration];
    # get_dump returns every tree ever built -- export only the used prefix.
    dumped = dumped[: model.best_iteration + 1]

    def emit_node(node, indent):
        pad = "    " * indent
        if "leaf" in node:
            return f"{pad}s += {node['leaf']!r}\n"
        fid = int(node["split"][1:])  # 'f123' -> 123
        thr = node["split_condition"]
        yes_id, no_id = node["yes"], node["no"]
        kids = {k["nodeid"]: k for k in node["children"]}
        missing = node.get("missing", yes_id)
        cond = f"x[{fid}] < {thr!r}"
        out = f"{pad}if {cond}:\n"
        out += emit_node(kids[yes_id], indent + 1)
        out += f"{pad}else:\n"
        out += emit_node(kids[no_id], indent + 1)
        return out

    code = ['"""GENERATED by tools/train_b1_model.py -- do not edit."""',
            "import math", "",
            "def predict_pwin(x):",
            '    """x: feature list (same order as src/ml/vectorizer.py). Returns P(win)."""',
            "    s = 0.0"]
    for tree_json in dumped:
        node = json.loads(tree_json)
        code.append(emit_node(node, 1).rstrip("\n"))
    code.append(f"    s += {base_score_offset!r}")
    code.append("    return 1.0 / (1.0 + math.exp(-s))")
    (OUT_DIR / "pwin_trees.py").write_text("\n".join(code), encoding="utf-8")

    # Parity check: exported code vs xgboost on a sample.
    ns: dict = {}
    exec((OUT_DIR / "pwin_trees.py").read_text(encoding="utf-8"), ns)
    sample = va[feat_cols].head(500).to_numpy()
    exported = np.array([ns["predict_pwin"](row.tolist()) for row in sample])
    reference = model.predict_proba(va[feat_cols].head(500))[:, 1]
    max_err = float(np.max(np.abs(exported - reference)))
    lines.append("")
    lines.append(f"## Export parity: max |exported - xgboost| over 500 rows = {max_err:.6f}")
    print(f"export parity max_err={max_err:.6f}")

    (OUT_DIR / "train_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"Wrote {OUT_DIR / 'xgb_pwin.json'}, pwin_trees.py, train_report.md")


if __name__ == "__main__":
    main()
