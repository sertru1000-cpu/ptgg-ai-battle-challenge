"""Meta-Deck Gauntlet: V6 vs V13, each against a deck-agnostic baseline
piloting the 10 real Kaggle-meta decklists found under decks/meta_*.csv.

Per-agent-under-test structure (matches the user's Russian-language task
prompt): V6 and V13 each keep their OWN fixed deck/policy throughout: the
thing that varies is the opponent's decklist, not the agent under test's.
The opponent is `src.agents.generic_policy_agent.make_agent(deck)` -- the
repo's existing deck-agnostic scoring policy (Phase 4.7, Layer B), rebuilt
fresh per meta deck via `make_agent(deck)` so it never carries hand-tuned
knowledge of any specific decklist. This is the "baseline agent piloting the
meta decks" the task calls for; using V6 itself as that baseline would
confound the V6 gauntlet (V6 vs V6 mirror ambiguity) and bias the V13
gauntlet since V13 is a deliberate deck-only variant of V6's own policy.

For each of the 10 meta decks: 20 games (10 with the agent-under-test in
engine slot 0, 10 in slot 1 -- tournament.py's existing alternation), i.e.
200 games for V6 + 200 games for V13 = 400 games total.

Usage:
    python tools/build_meta_gauntlet_v6_v13.py --games-per-deck 20 \
        --out-dir results/meta_gauntlet_v6_v13
"""

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.tournament import load_agent, play_one_game  # noqa: E402
from src.agents.common import load_deck_csv  # noqa: E402
from src.agents.generic_policy_agent import make_agent as make_baseline_agent  # noqa: E402

DECKS_DIR = REPO_ROOT / "decks"

META_DECKS = [
    ("Cynthia's Garchomp ex", DECKS_DIR / "meta_cynthia_s_garchomp_ex.csv"),
    ("Dragapult ex", DECKS_DIR / "meta_dragapult_ex.csv"),
    ("Fezandipiti ex", DECKS_DIR / "meta_fezandipiti_ex.csv"),
    ("Marnie's Grimmsnarl ex", DECKS_DIR / "meta_marnie_s_grimmsnarl_ex.csv"),
    ("Mega Kangaskhan ex", DECKS_DIR / "meta_mega_kangaskhan_ex.csv"),
    ("Mega Lopunny ex", DECKS_DIR / "meta_mega_lopunny_ex.csv"),
    ("Mega Lucario ex", DECKS_DIR / "meta_mega_lucario_ex.csv"),
    ("Teal Mask Ogerpon ex", DECKS_DIR / "meta_teal_mask_ogerpon_ex.csv"),
    ("Team Rocket's Mewtwo ex", DECKS_DIR / "meta_team_rocket_s_mewtwo_ex.csv"),
    ("Abra/Kadabra/Alakazam (unlabeled cluster 01)", DECKS_DIR / "meta_unlabeled_cluster01_abra_alakazam.csv"),
]

AGENTS_UNDER_TEST = {
    "V6": "main_v6.py",
    "V13": "main_v13.py",
}


def run_one_gauntlet(agent_label: str, agent_spec: str, n_games_per_deck: int, out_dir: Path, max_steps: int) -> list[dict]:
    games_dir = out_dir / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    agent_name, agent_fn, agent_deck = load_agent(agent_spec)
    rows = []

    for deck_label, deck_path in META_DECKS:
        deck_slug = deck_path.stem
        baseline_deck = load_deck_csv(deck_path)
        baseline_fn = make_baseline_agent(baseline_deck)
        baseline_name = f"baseline__{deck_slug}"

        run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        jsonl_path = games_dir / f"{agent_label}__vs__{deck_slug}__{run_id}.jsonl"

        print(f"\n=== {agent_label} vs baseline piloting '{deck_label}' ({n_games_per_deck} games) ===")
        results = []
        for i in range(n_games_per_deck):
            a_slot0 = i % 2 == 0
            result = play_one_game(
                run_id, i, agent_name, agent_fn, agent_deck, baseline_name, baseline_fn, baseline_deck, a_slot0, max_steps, None
            )
            results.append(result)
            status = "ABORTED: " + result.error if result.aborted else f"winner={result.winner_agent} reason={result.win_reason}"
            print(f"  [{i + 1}/{n_games_per_deck}] a_slot0={a_slot0} steps={result.steps} turns={result.turns} {status}")

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(asdict(r)) + "\n")

        wins = sum(1 for r in results if not r.aborted and r.winner_agent == agent_name)
        losses = sum(1 for r in results if not r.aborted and r.winner_agent == baseline_name)
        draws = sum(1 for r in results if not r.aborted and r.winner_agent == "draw")
        aborted = sum(1 for r in results if r.aborted)
        rows.append(
            {
                "agent_label": agent_label,
                "deck_label": deck_label,
                "deck_slug": deck_slug,
                "games": n_games_per_deck,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "aborted": aborted,
                "jsonl_path": str(jsonl_path.resolve().relative_to(REPO_ROOT)),
            }
        )
        print(f"  -> {agent_label}: {wins}W-{losses}L-{draws}D ({aborted} aborted) vs '{deck_label}'")

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-deck", type=int, default=20)
    parser.add_argument("--out-dir", default="results/meta_gauntlet_v6_v13")
    parser.add_argument("--max-steps", type=int, default=2000)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for agent_label, agent_spec in AGENTS_UNDER_TEST.items():
        all_rows.extend(run_one_gauntlet(agent_label, agent_spec, args.games_per_deck, out_dir, args.max_steps))

    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=2)
    print(f"\nWrote summary: {summary_path}")


if __name__ == "__main__":
    main()
