"""B1 data prep: per-decision (state -> final outcome) training rows from the
top-100 Dragapult teams' real ladder episodes (data/leader_episodes/ +
data/top100_audit/replays/, pulled by tools/pull_leader_episodes.py).

Design (the anti-V16 choice): the label source is DEMONSTRATED TOP-LEVEL play
-- states from games where at least one side is a known top-100 Dragapult
team (their opponents are near-rating peers via matchmaking, so both sides'
states are usable) -- not self-play of our own ~600-rated agents. Each row is
one acting-player decision state, featurized with the SAME
src/ml/vectorizer.py ObservationVectorizer V16 already validated end-to-end,
labeled with whether the acting side ultimately won that episode
(DECISIVE episodes only; draws/crashes excluded).

Output: results/b1/dataset.parquet (features f0..fN + metadata columns) --
consumed by tools/train_b1_model.py. Resumable per episode file; safe to run
on a partial download (skips unreadable/incomplete files with a logged count).

Usage:
    python tools/build_b1_dataset.py [--dragapult-side-only]
"""

from __future__ import annotations

import argparse
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

EPISODE_DIRS = [
    REPO_ROOT / "data" / "leader_episodes",
    REPO_ROOT / "data" / "top100_audit" / "replays",
]
OUT_DIR = REPO_ROOT / "results" / "b1"
DRAGAPULT_EX_ID = 121


def _episode_rows(path: Path, vec: ObservationVectorizer, dragapult_side_only: bool):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rewards = data.get("rewards") or [None, None]
    r0, r1 = rewards[0], rewards[1]
    if r0 == 1 and r1 == -1:
        winner = 0
    elif r1 == 1 and r0 == -1:
        winner = 1
    else:
        return []  # draw / crash / timeout: excluded from win-probability training

    team_names = data.get("info", {}).get("TeamNames", [None, None])
    episode_id = str(data.get("info", {}).get("EpisodeId", path.stem))

    decks = [None, None]
    for step in data["steps"]:
        for pi in (0, 1):
            if decks[pi] is None:
                action = step[pi].get("action")
                if action and isinstance(action, list) and len(action) == 60:
                    decks[pi] = action
        if decks[0] is not None and decks[1] is not None:
            break
    plays_dragapult = [decks[pi] is not None and DRAGAPULT_EX_ID in decks[pi] for pi in (0, 1)]

    rows = []
    for step_i, step in enumerate(data["steps"]):
        for pi in (0, 1):
            if dragapult_side_only and not plays_dragapult[pi]:
                continue
            obs_dict = step[pi].get("observation")
            if not obs_dict or obs_dict.get("select") is None:
                continue  # not this player's decision (or deck-declare handled via action above)
            try:
                obs = to_observation_class(obs_dict)
                features = vec.vectorize(obs)
            except Exception:  # noqa: BLE001 -- schema quirks in old episodes: skip row, keep episode
                continue
            rows.append({
                "episode_id": episode_id,
                "step": step_i,
                "player": pi,
                "team": team_names[pi],
                "plays_dragapult": plays_dragapult[pi],
                "turn": obs.current.turn,
                "label_win": 1 if winner == pi else 0,
                **{f"f{j}": v for j, v in enumerate(features)},
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dragapult-side-only", action="store_true",
                        help="keep only rows where the acting side plays a Dragapult-ex deck")
    args = parser.parse_args()

    import pandas as pd

    vec = ObservationVectorizer()
    files: list[Path] = []
    seen: set[str] = set()
    for d in EPISODE_DIRS:
        if d.exists():
            for p in sorted(d.glob("episode-*-replay.json")):
                if p.name not in seen:
                    seen.add(p.name)
                    files.append(p)
    print(f"Episode files: {len(files)}")

    all_rows: list[dict] = []
    bad = 0
    for i, path in enumerate(files):
        try:
            all_rows.extend(_episode_rows(path, vec, args.dragapult_side_only))
        except Exception as ex:  # noqa: BLE001 -- one corrupt file must not kill the batch
            bad += 1
            print(f"  [skip] {path.name}: {ex}")
        if (i + 1) % 50 == 0:
            print(f"[{i + 1}/{len(files)}] rows={len(all_rows)} bad_files={bad}", flush=True)

    df = pd.DataFrame(all_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "dataset.parquet"
    df.to_parquet(out, index=False)
    print(f"Wrote {out}: {len(df)} rows, {df['episode_id'].nunique()} episodes, "
          f"{int(df['label_win'].sum())} win-labeled, bad_files={bad}")
    if "plays_dragapult" in df.columns and len(df):
        print(df.groupby("plays_dragapult")["label_win"].agg(["count", "mean"]))


if __name__ == "__main__":
    main()
