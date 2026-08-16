"""Phase 1 validation script: run ObservationVectorizer over a small sample of real
replay files and extract (state_vector, label) pairs.

label = 1.0 if the state's acting player (yourIndex) went on to win the game, else 0.0.
Only DECISIVE episodes are used (outcome_type from src.meta_analysis.episode_parser) --
DRAW / ERROR_OR_TIMEOUT games have no reliable win/loss signal to attach to their states.

This is a Phase 1 SANITY-CHECK script (small sample, prints a crash/shape report), not
the full-scale dataset builder -- that comes in a later phase once this is validated.
"""
from __future__ import annotations

import json
import sys
import traceback
from collections import Counter
from pathlib import Path

import pandas as pd

from src.environment.engine_loader import ensure_cg_on_path
from src.meta_analysis.episode_parser import parse_episode_file
from src.ml.vectorizer import FEATURE_COUNT, FEATURE_NAMES, ObservationVectorizer

ensure_cg_on_path()

from cg.api import to_observation_class  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "data" / "episode_pilot"
# 30 files (Phase 1 sanity check) produced only ~24 train / 6 val episodes -- too few
# for a trustworthy Phase 2 validation metric (train AUC ~0.999, val AUC swung 0.19-0.82
# across random split seeds, pure small-sample noise, not a vectorizer bug -- confirmed
# via sanity checks on the extracted features/labels before raising this). 400 files
# gives a much more stable ~320/80 train/val episode split while still running in
# minutes against the already-downloaded local replay data.
MAX_FILES = 400
OUTPUT_PATH = REPO_ROOT / "results" / "ml" / "vectorizer_pilot_sample.parquet"


def find_sample_files(sample_dir: Path, max_files: int) -> list[Path]:
    files = sorted(sample_dir.glob("*/*.json"))
    return files[:max_files]


def main() -> int:
    files = find_sample_files(SAMPLE_DIR, MAX_FILES)
    if not files:
        print(f"No episode files found under {SAMPLE_DIR}")
        return 1

    vectorizer = ObservationVectorizer()

    rows: list[dict] = []
    files_decisive = 0
    files_skipped_outcome: Counter[str] = Counter()
    files_load_errors = 0
    step_errors: Counter[str] = Counter()
    step_error_examples: list[str] = []

    for path in files:
        date = path.parent.name
        try:
            record = parse_episode_file(str(path), date)
        except Exception as exc:  # noqa: BLE001 -- report, don't abort the batch
            files_load_errors += 1
            step_error_examples.append(f"{path.name}: parse_episode_file failed: {type(exc).__name__}: {exc}")
            continue

        if record.outcome_type != "DECISIVE":
            files_skipped_outcome[record.outcome_type] += 1
            continue
        files_decisive += 1

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            files_load_errors += 1
            step_error_examples.append(f"{path.name}: json.load failed: {type(exc).__name__}: {exc}")
            continue

        steps = data.get("steps", [])
        for step_idx, step in enumerate(steps):
            for player_idx in (0, 1):
                try:
                    entry = step[player_idx]
                    obs_dict = entry.get("observation")
                    if not obs_dict or obs_dict.get("select") is None:
                        continue
                    obs = to_observation_class(obs_dict)
                    vec = vectorizer.vectorize(obs)
                    label = 1.0 if player_idx == record.winner else 0.0
                    row = dict(zip(FEATURE_NAMES, vec))
                    row["label"] = label
                    row["episode_id"] = record.episode_id
                    row["player_index"] = player_idx
                    row["step_idx"] = step_idx
                    rows.append(row)
                except Exception as exc:  # noqa: BLE001 -- this IS what Phase 1 is checking for
                    key = f"{type(exc).__name__}"
                    step_errors[key] += 1
                    if len(step_error_examples) < 20:
                        tb = traceback.format_exc(limit=2)
                        step_error_examples.append(
                            f"{path.name} step={step_idx} player={player_idx}: {type(exc).__name__}: {exc}\n{tb}"
                        )

    print("=" * 70)
    print("PHASE 1 VECTORIZER/EXTRACTOR VALIDATION REPORT")
    print("=" * 70)
    print(f"Sample dir: {SAMPLE_DIR}")
    print(f"Files considered: {len(files)}")
    print(f"Files DECISIVE (used): {files_decisive}")
    print(f"Files skipped (non-decisive outcome): {dict(files_skipped_outcome)}")
    print(f"Files with load errors: {files_load_errors}")
    print(f"FEATURE_COUNT (vector dimensionality): {FEATURE_COUNT}")
    print(f"Rows extracted: {len(rows)}")
    if rows:
        label_counts = Counter(r["label"] for r in rows)
        print(f"Label balance: {dict(label_counts)}")
    print(f"Per-step exceptions encountered: {dict(step_errors)} (total={sum(step_errors.values())})")
    if step_error_examples:
        print("-" * 70)
        print("Exception examples (up to 20):")
        for ex in step_error_examples:
            print(ex)
    print("=" * 70)

    if rows:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(rows)
        df.to_parquet(OUTPUT_PATH, index=False)
        print(f"Saved {len(df)} rows x {len(df.columns)} cols -> {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
