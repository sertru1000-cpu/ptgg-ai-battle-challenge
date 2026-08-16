"""B1v2: P(win) eval retrained on self-play + leader demonstrations (V23).

Data: results/selfplay/shard_w*.parquet (own-engine self-play; stratified
subsample of N_PER_GAME states per game -- within-game states share one label
and are heavily correlated, so game diversity beats state count) + the B1
leader dataset (results/b1/dataset.parquet, all 341K rows -- the "how strong
players' games look" anchor). Same episode/game-level split discipline.

Outputs: results/b1/xgb_pwin_v2.json, train_v2_report.md, and (via
tools/export_b1_cpp.py logic inlined) the V23 package's pwin_trees.hpp.

Usage:
    python tools/train_b1v2.py [--n-per-game 6] [--max-selfplay-games 400000]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

B1_DIR = REPO_ROOT / "results" / "b1"
SP_DIR = REPO_ROOT / "results" / "selfplay"
OUT_HPP = REPO_ROOT / "src" / "agents" / "dragapult_agent_v23_cpp" / "cpp" / "pwin_trees.hpp"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-per-game", type=int, default=6)
    parser.add_argument("--max-selfplay-games", type=int, default=400000)
    parser.add_argument("--fixed-only", action="store_true", default=True,
                        help="use only the fixed-alternation shards (w3+)")
    args = parser.parse_args()

    import numpy as np
    import pandas as pd
    import xgboost as xgb
    from sklearn.metrics import log_loss, roc_auc_score

    pattern = "shard_w[3-9]_*.parquet" if args.fixed_only else "shard_w*_*.parquet"
    files = sorted(glob.glob(str(SP_DIR / pattern)))
    print(f"self-play shards: {len(files)}")

    feat_cols_early = [f"f{i}" for i in range(87)]
    need_cols = ["game_id", "side", "label_win"] + feat_cols_early

    # Memory-lean streaming (16GB box, ArrowMemoryError on the naive path):
    # read ONLY needed columns per shard, subsample immediately, keep the
    # sample as float32 numpy + a small key list -- never accumulate full
    # DataFrames.
    rng = np.random.default_rng(123)
    X_parts, y_parts, key_parts = [], [], []
    games_seen = 0
    sp_rows = 0
    for f in files:
        if games_seen >= args.max_selfplay_games:
            break
        df = pd.read_parquet(f, columns=need_cols)
        shuffled = df.sample(frac=1.0, random_state=int(rng.integers(1 << 31)))
        take = shuffled.groupby(["game_id", "side"], sort=False).head(args.n_per_game)
        X_parts.append(take[feat_cols_early].to_numpy(dtype=np.float32))
        y_parts.append(take["label_win"].to_numpy(dtype=np.int8))
        key_parts.extend("sp_" + take["game_id"].astype(str))
        sp_rows += len(take)
        games_seen += df["game_id"].nunique()
        del df, shuffled, take
    sp_X = np.concatenate(X_parts)
    sp_y = np.concatenate(y_parts)
    del X_parts, y_parts
    print(f"self-play sample: {len(sp_X)} rows from {games_seen} games")

    # Leaders: numpy float32 straight from parquet columns -- NO pandas
    # combine anywhere below (pandas concat upcasts float32->float64 and
    # OOM'd a 16GB box on 4.7M rows; the pure-numpy path peaks ~2GB).
    feat_cols = [f"f{i}" for i in range(87)]
    lead = pd.read_parquet(B1_DIR / "dataset.parquet", columns=feat_cols + ["label_win", "episode_id"])
    lead_X = lead[feat_cols].to_numpy(dtype=np.float32)
    lead_y = lead["label_win"].to_numpy(dtype=np.int8)
    lead_keys = ["ld_" + str(e) for e in lead["episode_id"]]
    del lead
    print(f"leader rows: {len(lead_X)}")

    X = np.concatenate([sp_X, lead_X])
    y = np.concatenate([sp_y, lead_y])
    src_is_sp = np.zeros(len(X), dtype=bool)
    src_is_sp[: len(sp_X)] = True
    split_keys = np.array(key_parts + lead_keys)
    del sp_X, sp_y, lead_X, lead_y, key_parts, lead_keys
    print(f"combined: {len(X)} rows, sp share {src_is_sp.mean():.2f}")

    uniq = np.unique(split_keys)
    rng2 = np.random.default_rng(42)
    rng2.shuffle(uniq)
    valid_keys = set(uniq[: max(1, int(len(uniq) * 0.15))].tolist())
    is_valid = np.fromiter((k in valid_keys for k in split_keys), dtype=bool, count=len(split_keys))
    print(f"train {int((~is_valid).sum())} / valid {int(is_valid.sum())} (game-level split)")

    model = xgb.XGBClassifier(
        n_estimators=600, max_depth=7, learning_rate=0.08,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
        eval_metric="logloss", early_stopping_rounds=40, n_jobs=4,
    )
    model.fit(X[~is_valid], y[~is_valid], eval_set=[(X[is_valid], y[is_valid])], verbose=100)

    lines = ["# B1v2 training report", ""]
    p = model.predict_proba(X[is_valid])[:, 1]
    y_va = y[is_valid]
    lines.append(f"combined valid AUC={roc_auc_score(y_va, p):.4f} "
                 f"logloss={log_loss(y_va, p):.4f} best_iter={model.best_iteration}")
    for src_name, mask in (("selfplay", src_is_sp[is_valid]), ("leaders", ~src_is_sp[is_valid])):
        if mask.sum() > 1000:
            lines.append(f"  valid[{src_name}]: AUC={roc_auc_score(y_va[mask], p[mask]):.4f} (n={int(mask.sum())})")

    model.save_model(B1_DIR / "xgb_pwin_v2.json")

    # C++ export (same exact-arrays method as tools/export_b1_cpp.py, with the
    # float32-comparison lesson baked in).
    raw = json.loads((B1_DIR / "xgb_pwin_v2.json").read_text(encoding="utf-8"))
    learner = raw["learner"]
    trees = learner["gradient_booster"]["model"]["trees"][: model.best_iteration + 1]
    base_score = float(learner["learner_model_param"]["base_score"].strip("[]"))
    margin_offset = math.log(base_score / (1.0 - base_score))
    feat, thr, left, right, tree_root = [], [], [], [], []
    for t in trees:
        offset = len(feat)
        tree_root.append(offset)
        si, sc, lc, rc = t["split_indices"], t["split_conditions"], t["left_children"], t["right_children"]
        for i in range(len(si)):
            is_leaf = lc[i] == -1
            feat.append(-1 if is_leaf else int(si[i]))
            thr.append(float(sc[i]))
            left.append(-1 if is_leaf else offset + int(lc[i]))
            right.append(-1 if is_leaf else offset + int(rc[i]))

    def arr(name: str, vals, ctype: str, fmt) -> str:
        return f"inline constexpr {ctype} {name}[] = {{{','.join(fmt(v) for v in vals)}}};\n"

    hpp = [
        "// GENERATED by tools/train_b1v2.py -- do not edit. B1v2 learned P(win)",
        "// (self-play + leader demonstrations), exact float32 arrays.",
        "#pragma once", "#include <cmath>", "", "namespace v20 {", "",
        f"inline constexpr int kPwinNumTrees = {len(tree_root)};",
        f"inline constexpr double kPwinMarginOffset = {margin_offset!r};",
        "inline constexpr int kPwinFeatureCount = 87;", "",
        arr("kPwinTreeRoot", tree_root, "int", str),
        arr("kPwinFeat", feat, "int", str),
        arr("kPwinThr", thr, "float", lambda v: f"{v!r}f"),
        arr("kPwinLeft", left, "int", str),
        arr("kPwinRight", right, "int", str),
        "inline double pwin_predict(const float* x) {",
        "  double s = kPwinMarginOffset;",
        "  for (int t = 0; t < kPwinNumTrees; ++t) {",
        "    int node = kPwinTreeRoot[t];",
        "    while (kPwinFeat[node] >= 0) {",
        "      node = (x[kPwinFeat[node]] < kPwinThr[node]) ? kPwinLeft[node] : kPwinRight[node];",
        "    }",
        "    s += kPwinThr[node];",
        "  }",
        "  return 1.0 / (1.0 + std::exp(-s));",
        "}", "", "}  // namespace v20",
    ]
    OUT_HPP.parent.mkdir(parents=True, exist_ok=True)
    OUT_HPP.write_text("\n".join(hpp), encoding="utf-8")

    # Parity: float32 semantics.
    feat_np = np.array(feat)
    thr32 = np.array(thr, dtype=np.float32)
    left_np, right_np = np.array(left), np.array(right)

    def predict_row(x32):
        s = margin_offset
        for root in tree_root:
            n = root
            while feat_np[n] >= 0:
                n = left_np[n] if x32[feat_np[n]] < thr32[n] else right_np[n]
            s += thr32[n]
        return 1.0 / (1.0 + math.exp(-s))

    X32 = X[is_valid][:300]
    ref = model.predict_proba(X32)[:, 1]
    ours = np.array([predict_row(x) for x in X32])
    max_err = float(np.max(np.abs(ours - ref)))
    lines.append(f"export parity (300 rows): {max_err:.2e}")
    print(f"parity: {max_err:.2e}")
    if max_err > 1e-5:
        raise SystemExit("PARITY FAIL")
    (B1_DIR / "train_v2_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"Wrote {OUT_HPP}")


if __name__ == "__main__":
    main()
