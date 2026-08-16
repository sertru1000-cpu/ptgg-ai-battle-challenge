"""B1v4 data pull: downloads the stratified tier selection
(results/b1/tier_selection.json -- weak/mid/strong by min_score quantiles of
the recent real pool) via the competition replay endpoint (fast, ~60/min,
same path that fetched the leader episodes). Resumable by file existence.

Usage:
    python tools/pull_tiered_episodes.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT = REPO_ROOT / "data" / "tiered_episodes"


def main() -> None:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    sel = json.loads((REPO_ROOT / "results" / "b1" / "tier_selection.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    ok = fail = skip = 0
    t0 = time.time()
    total = sum(len(v) for v in sel.values())
    done_n = 0
    for tag, ids in sel.items():
        tier_dir = OUT / tag
        tier_dir.mkdir(exist_ok=True)
        for eid in ids:
            done_n += 1
            target = tier_dir / f"episode-{eid}-replay.json"
            if target.exists():
                skip += 1
                continue
            for attempt in range(3):
                try:
                    api.competition_episode_replay(eid, path=str(tier_dir), quiet=True)
                    break
                except Exception as ex:  # noqa: BLE001
                    time.sleep(4.0 * (attempt + 1))
            if target.exists():
                ok += 1
            else:
                fail += 1
            if done_n % 100 == 0:
                rate = done_n / max(1e-9, time.time() - t0) * 60
                print(f"[{done_n}/{total}] ok={ok} fail={fail} skip={skip} rate={rate:.0f}/min", flush=True)
            time.sleep(0.35)
    print(f"DONE ok={ok} fail={fail} skip={skip} in {(time.time() - t0) / 60:.0f} min")


if __name__ == "__main__":
    main()
