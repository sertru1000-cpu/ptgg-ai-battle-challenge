"""One-off summarizer for results/meta_gauntlet_v6_v13's raw per-game jsonl
files: adds the first/second-player split this project's process rules
require (see feedback-ptcg-process point 2) on top of build_meta_gauntlet_v6_v13.py's
already-written summary.json aggregate.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GAMES_DIR = REPO_ROOT / "results" / "meta_gauntlet_v6_v13" / "games"

rows = []
for jf in sorted(GAMES_DIR.glob("*.jsonl")):
    parts = jf.stem.split("__vs__")
    agent_label = parts[0]
    rest = parts[1]
    deck_slug = rest.rsplit("__", 2)[0]

    agent_first_wins = agent_first_games = 0
    agent_second_wins = agent_second_games = 0
    agent_name = None
    for line in jf.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["aborted"]:
            continue
        agent_name = r["agent_a_name"]
        agent_slot = r["agent_a_slot"]
        was_first = r["first_player_slot"] == agent_slot
        won = r["winner_agent"] == agent_name
        if was_first:
            agent_first_games += 1
            agent_first_wins += 1 if won else 0
        else:
            agent_second_games += 1
            agent_second_wins += 1 if won else 0

    rows.append(
        {
            "agent_label": agent_label,
            "deck_slug": deck_slug,
            "agent_first_games": agent_first_games,
            "agent_first_wins": agent_first_wins,
            "agent_second_games": agent_second_games,
            "agent_second_wins": agent_second_wins,
        }
    )

for r in rows:
    print(
        f"{r['agent_label']:5s} vs {r['deck_slug']:45s} "
        f"first: {r['agent_first_wins']}/{r['agent_first_games']}  "
        f"second: {r['agent_second_wins']}/{r['agent_second_games']}"
    )
