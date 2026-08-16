"""BC-pilot experiment (user-ordered, deadline-eve): per-archetype imitation
datasets from the HIGH-RATED OPPONENTS in the leader episodes.

The 714+288 downloaded episodes contain, on the non-leader side, opponents
matched near the leaders' own ratings -- i.e. strong pilots of the real meta
decks. This extracts THEIR decisions for the 3 gauntlet archetypes
(Marnie's Grimmsnarl ex / Mega Kangaskhan ex / Fezandipiti ex), keyed by
signature card presence in the side's exact declared 60.

Rows are identical in shape to results/b1/bc_dataset.parquet (87 state
features + 16 option features + chosen), one parquet per archetype:
results/b1/pilot_bc_<tag>.parquet.

Usage:
    python tools/build_pilot_bc_datasets.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import all_attack, all_card_data, to_observation_class  # noqa: E402

from src.ml.bc_features import option_features  # noqa: E402
from src.ml.vectorizer import ObservationVectorizer  # noqa: E402

EPISODE_DIRS = [
    REPO_ROOT / "data" / "leader_episodes",
    REPO_ROOT / "data" / "top100_audit" / "replays",
]
LEADERBOARD_CSV = REPO_ROOT / "results" / "top100_audit" / "leaderboard_decks.csv"
OUT_DIR = REPO_ROOT / "results" / "b1"

# archetype tag -> signature card NAME (exact match against the engine table);
# a side belongs to the archetype iff its declared 60 contains the card.
SIGNATURES = {
    "grimmsnarl": "Marnie's Grimmsnarl ex",
    "kangaskhan": "Mega Kangaskhan ex",
    "fezandipiti": "Fezandipiti ex",
}


def main() -> None:
    import pandas as pd

    card_table = {c.cardId: c for c in all_card_data()}
    attack_table = {a.attackId: a for a in all_attack()}
    name_to_id = {c.name: c.cardId for c in all_card_data()}
    sig_ids = {tag: name_to_id[nm] for tag, nm in SIGNATURES.items()}
    print("signature ids:", sig_ids)
    # Fezandipiti ex appears as a 1-of tech in OTHER decks too (even ours) --
    # guard: a side counts as the archetype only if it does NOT also carry a
    # higher-priority signature. Priority: grimmsnarl > kangaskhan > fezandipiti.
    priority = ["grimmsnarl", "kangaskhan", "fezandipiti"]

    rows_lb = list(csv.DictReader(open(LEADERBOARD_CSV, encoding="utf-8")))
    top_teams = {r["team_name"] for r in rows_lb}  # all top-100 (any archetype)

    vec = ObservationVectorizer()
    files: list[Path] = []
    seen: set[str] = set()
    for d in EPISODE_DIRS:
        if d.exists():
            for p in sorted(d.glob("episode-*-replay.json")):
                if p.name not in seen:
                    seen.add(p.name)
                    files.append(p)

    buckets: dict[str, list[dict]] = {t: [] for t in SIGNATURES}
    n_dec = {t: 0 for t in SIGNATURES}
    for fi, path in enumerate(files):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            team_names = data.get("info", {}).get("TeamNames", [None, None])
            episode_id = str(data.get("info", {}).get("EpisodeId", path.stem))
            decks = [None, None]
            for step in data["steps"]:
                for pi in (0, 1):
                    if decks[pi] is None:
                        action = step[pi].get("action")
                        if action and isinstance(action, list) and len(action) == 60:
                            decks[pi] = set(action)
                if decks[0] is not None and decks[1] is not None:
                    break
            side_tag = [None, None]
            DRAGAPULT_EX = 121
            for pi in (0, 1):
                if decks[pi] is None:
                    continue
                # A Dragapult deck is NONE of the three archetypes even though
                # it carries Fezandipiti ex as a 1-of tech (all leader lists
                # do) -- without this guard every leader side polluted the
                # fezandipiti bucket (caught live: 19,683 vs 2,458 decisions).
                if DRAGAPULT_EX in decks[pi]:
                    continue
                for tag in priority:
                    if sig_ids[tag] in decks[pi]:
                        side_tag[pi] = tag
                        break
            if not any(side_tag):
                continue
            for step_i, step in enumerate(data["steps"]):
                for pi in (0, 1):
                    tag = side_tag[pi]
                    if tag is None:
                        continue
                    obs_dict = step[pi].get("observation")
                    action = step[pi].get("action")
                    if not obs_dict or obs_dict.get("select") is None or not action:
                        continue
                    if isinstance(action, list) and len(action) == 60:
                        continue
                    try:
                        obs = to_observation_class(obs_dict)
                    except Exception:  # noqa: BLE001
                        continue
                    select = obs.select
                    if select is None or select.maxCount != 1 or len(select.option) < 2:
                        continue
                    chosen = set(int(a) for a in action if isinstance(a, (int, float)))
                    if not chosen or max(chosen) >= len(select.option):
                        continue
                    state_feats = vec.vectorize(obs)
                    n_dec[tag] += 1
                    for oi, option in enumerate(select.option):
                        of = option_features(obs, option, card_table, attack_table)
                        buckets[tag].append({
                            "episode_id": episode_id, "step": step_i, "player": pi,
                            "team": team_names[pi], "option_i": oi,
                            "chosen": 1 if oi in chosen else 0,
                            **{f"s{j}": v for j, v in enumerate(state_feats)},
                            **{f"o{j}": v for j, v in enumerate(of)},
                        })
        except Exception as ex:  # noqa: BLE001
            print(f"  [skip] {path.name}: {ex}")
        if (fi + 1) % 200 == 0:
            print(f"[{fi + 1}/{len(files)}] decisions: {n_dec}", flush=True)

    for tag, rows in buckets.items():
        df = pd.DataFrame(rows)
        out = OUT_DIR / f"pilot_bc_{tag}.parquet"
        df.to_parquet(out, index=False)
        print(f"{tag}: {n_dec[tag]} decisions, {len(df)} rows, "
              f"{df['episode_id'].nunique() if len(df) else 0} episodes -> {out}")


if __name__ == "__main__":
    main()
