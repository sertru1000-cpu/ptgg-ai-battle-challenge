"""Download the episodes listed in data/episode_manifests/pilot_selection.csv.

Resumable (skips files already on disk), throttled, retries with backoff on
rate-limit/network errors. Groups by date to minimize slug re-resolution.
"""
import csv
import os
import time
from collections import defaultdict

os.environ.setdefault("KAGGLE_CONFIG_DIR", os.path.expanduser("~/.kaggle"))
from kaggle.api.kaggle_api_extended import KaggleApi

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELECTION = os.path.join(REPO_ROOT, "data", "episode_manifests", "pilot_selection.csv")
OUT_ROOT = os.path.join(REPO_ROOT, "data", "episode_pilot")
SLEEP_BETWEEN = 0.4


def main():
    with open(SELECTION, newline="") as f:
        rows = list(csv.DictReader(f))

    by_date = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r["episode_id"])

    api = KaggleApi()
    api.authenticate()

    total = len(rows)
    done = 0
    failed = []

    for date in sorted(by_date):
        slug = f"kaggle/pokemon-tcg-ai-battle-episodes-{date}"
        outdir = os.path.join(OUT_ROOT, date)
        os.makedirs(outdir, exist_ok=True)
        for episode_id in by_date[date]:
            fname = f"{episode_id}.json"
            local_path = os.path.join(outdir, fname)
            done += 1
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                continue
            ok = False
            for attempt in range(6):
                try:
                    api.dataset_download_file(slug, fname, path=outdir, force=True, quiet=True)
                    ok = True
                    break
                except Exception as e:
                    wait = 5 * (attempt + 1)
                    print(f"  retry {date}/{fname} attempt {attempt}: {e} (sleep {wait}s)")
                    time.sleep(wait)
            if not ok:
                failed.append((date, episode_id))
            if done % 25 == 0:
                print(f"[{done}/{total}] {date} done")
            time.sleep(SLEEP_BETWEEN)

    print(f"\nDone. {total - len(failed)}/{total} succeeded.")
    if failed:
        print("FAILED:", failed)
        with open(os.path.join(OUT_ROOT, "failed.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "episode_id"])
            w.writerows(failed)


if __name__ == "__main__":
    main()
