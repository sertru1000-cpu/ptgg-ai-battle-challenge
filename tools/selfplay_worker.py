"""V23 self-play data generator (one worker process).

Plays an endless round-robin of fast pure-Python matchups on OUR OWN engine
build (own_engine.dll, compiled from the official single-TU source -- see the
scratch cg-package copy prepared by tools/selfplay_launch.ps1 logic), records
EVERY decision of BOTH sides as (87 state features, acting side, outcome) and
flushes parquet shards. Several workers run in parallel; each owns its shard
namespace, so there is nothing to coordinate.

Matchup mix (round-robin) -- chosen to cover the state distributions the
V20/V22 eval actually faces (our classic deck) plus the V19 leader deck and
the 3 discriminative meta decks:
  V6 vs V6, V6 vs V19, V19 vs V19,
  V6 vs generic(Kangaskhan), V6 vs generic(Fezandipiti), V6 vs generic(Grimmsnarl),
  V19 vs generic(Kangaskhan), V19 vs generic(Grimmsnarl)

Usage (normally via Start-Process, several in parallel):
    python tools/selfplay_worker.py --worker-id 0 --own-cg-dir <scratch>/own_cg
Stops when <out-dir>/STOP exists.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", type=int, required=True)
    parser.add_argument("--own-cg-dir", type=str, required=True,
                        help="dir whose cg/ subpackage carries own_engine.dll as cg.dll")
    parser.add_argument("--out-dir", type=str, default=str(REPO_ROOT / "results" / "selfplay"))
    parser.add_argument("--games-per-shard", type=int, default=400)
    args = parser.parse_args()

    # Our engine build FIRST on sys.path -- `import cg` resolves to the copy
    # backed by own_engine.dll, before engine_loader adds the official one.
    sys.path.insert(0, args.own_cg_dir)
    import cg  # noqa: F401
    _cg_dir = Path(cg.__file__).resolve().parent
    assert Path(args.own_cg_dir).resolve() == _cg_dir.parent, \
        f"own-engine cg copy not picked up: got {_cg_dir}"

    import pandas as pd

    from cg.api import to_observation_class
    from src.ml.vectorizer import ObservationVectorizer
    from src.agents.common import load_deck_csv
    from src.agents.generic_policy_agent import make_agent as make_generic
    from src.agents.dragapult_policy_v6 import DECK as V6_DECK, make_agent as make_v6
    from src.agents.dragapult_policy_v19 import DECK as V19_DECK, make_agent as make_v19
    from src.agents.policy_weights import BALANCED
    from tools.stress_test_v17 import _play_one_game_keep_search_input

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stop_file = out_dir / "STOP"

    vec = ObservationVectorizer()

    def recording(base_fn, sink: list, side: int):
        def f(obs_dict):
            if obs_dict.get("select") is not None:
                try:
                    obs = to_observation_class(obs_dict)
                    sink.append((side, vec.vectorize(obs)))
                except Exception:  # noqa: BLE001 -- recording must never break play
                    pass
            return base_fn(obs_dict)
        return f

    decks_dir = REPO_ROOT / "decks"
    meta = {
        "kang": load_deck_csv(decks_dir / "meta_mega_kangaskhan_ex.csv"),
        "fez": load_deck_csv(decks_dir / "meta_fezandipiti_ex.csv"),
        "grimm": load_deck_csv(decks_dir / "meta_marnie_s_grimmsnarl_ex.csv"),
    }

    def fresh_agents(matchup: str):
        if matchup == "v6_v6":
            return make_v6(BALANCED, always_first=True), V6_DECK, make_v6(BALANCED, always_first=True), V6_DECK
        if matchup == "v6_v19":
            return make_v6(BALANCED, always_first=True), V6_DECK, make_v19(BALANCED, always_first=True), V19_DECK
        if matchup == "v19_v19":
            return make_v19(BALANCED, always_first=True), V19_DECK, make_v19(BALANCED, always_first=True), V19_DECK
        side, deck_key = matchup.split("_vs_")
        mk = make_v6 if side == "v6" else make_v19
        our_deck = V6_DECK if side == "v6" else V19_DECK
        return mk(BALANCED, always_first=True), our_deck, make_generic(meta[deck_key]), meta[deck_key]

    matchups = ["v6_v6", "v6_v19", "v19_v19", "v6_vs_kang", "v6_vs_fez", "v6_vs_grimm",
                "v19_vs_kang", "v19_vs_grimm"]

    rows: list[dict] = []
    game_no = 0
    shard_no = 0
    t0 = time.time()
    while not stop_file.exists():
        matchup = matchups[game_no % len(matchups)]
        agent_a, deck_a, agent_b, deck_b = fresh_agents(matchup)
        sink: list = []
        rec_a = recording(agent_a, sink, 0)
        rec_b = recording(agent_b, sink, 1)
        # First-player alternation must be DECORRELATED from the matchup
        # rotation (period 8): with `game_no % 2` every matchup type always
        # had the same slot-0 side, collapsing opening-state diversity --
        # caught live in the first 29K games' stats. Alternate per full
        # rotation instead.
        a_slot0 = (game_no // len(matchups)) % 2 == 0
        result = _play_one_game_keep_search_input(
            run_id=f"selfplay_w{args.worker_id}", game_index=game_no,
            agent_a_name="A", agent_a_fn=rec_a, deck_a=deck_a,
            agent_b_name="B", agent_b_fn=rec_b, deck_b=deck_b,
            a_slot0=a_slot0, max_steps=2000,
        )
        game_no += 1
        winner = result.winner_agent  # "A"/"B"/"draw"/None
        if winner in ("A", "B") and not result.aborted:
            win_side = 0 if winner == "A" else 1
            gid = f"w{args.worker_id}g{game_no}"
            for side, feats in sink:
                rows.append({
                    "game_id": gid, "matchup": matchup, "side": side,
                    "label_win": 1 if side == win_side else 0,
                    **{f"f{j}": v for j, v in enumerate(feats)},
                })
        if game_no % args.games_per_shard == 0 and rows:
            shard = out_dir / f"shard_w{args.worker_id}_{shard_no:04d}.parquet"
            pd.DataFrame(rows).to_parquet(shard, index=False)
            rate = game_no / max(1e-9, time.time() - t0)
            print(f"[w{args.worker_id}] games={game_no} rows_flushed={len(rows)} "
                  f"shard={shard.name} rate={rate * 60:.0f} games/min", flush=True)
            rows = []
            shard_no += 1
    if rows:
        pd.DataFrame(rows).to_parquet(out_dir / f"shard_w{args.worker_id}_{shard_no:04d}.parquet", index=False)
    print(f"[w{args.worker_id}] STOP seen; total games={game_no}", flush=True)


if __name__ == "__main__":
    main()
