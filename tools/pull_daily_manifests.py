"""Pull manifest.csv from every daily episode dataset (cheap, ~50-600KB each).

Does NOT download any episode JSON files. Populates data/episode_manifests/<date>.csv
and concatenates into data/episode_manifests/all_episodes_manifest.csv with a `date`
column added, for full-dataset-scale sampling analysis without touching the ~1.18TB
of episode content.
"""
import csv
import os
import time

os.environ.setdefault("KAGGLE_CONFIG_DIR", os.path.expanduser("~/.kaggle"))
from kaggle.api.kaggle_api_extended import KaggleApi

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY_INDEX = os.path.join(REPO_ROOT, "strategy", "meta_analysis", "episodes_manifest_2026-08-10.csv")
OUT_DIR = os.path.join(REPO_ROOT, "data", "episode_manifests")
OUT_ALL = os.path.join(OUT_DIR, "all_episodes_manifest.csv")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    api = KaggleApi()
    api.authenticate()

    with open(DAY_INDEX, newline="") as f:
        days = list(csv.DictReader(f))

    all_rows = []
    fieldnames = None
    for i, day in enumerate(days):
        date = day["date"]
        slug = day["daily_dataset_slug"]
        full_slug = f"kaggle/{slug}"
        local_path = os.path.join(OUT_DIR, f"{date}.csv")
        if not os.path.exists(local_path):
            for attempt in range(6):
                try:
                    api.dataset_download_file(full_slug, "manifest.csv", path=OUT_DIR, force=True, quiet=True)
                    src = os.path.join(OUT_DIR, "manifest.csv")
                    os.replace(src, local_path)
                    break
                except Exception as e:
                    print(f"  retry {date} attempt {attempt}: {e}")
                    time.sleep(6 * (attempt + 1))
            time.sleep(2.0)
        print(f"[{i+1}/{len(days)}] {date} -> {local_path}")

        with open(local_path, newline="") as f:
            rows = list(csv.DictReader(f))
        if fieldnames is None:
            fieldnames = list(rows[0].keys()) + ["date"]
        for r in rows:
            r["date"] = date
            all_rows.append(r)

    with open(OUT_ALL, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} total episode rows -> {OUT_ALL}")


if __name__ == "__main__":
    main()
