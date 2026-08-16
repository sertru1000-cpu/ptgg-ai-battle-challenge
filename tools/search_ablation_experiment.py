"""Phase 12/13: BEST HEURISTIC (dragapult_fix_v1) vs. HEURISTIC + 1-ply SEARCH
(src.agents.search_lookahead wrapping dragapult_fix_v1 for multi-attack MAIN
decisions only). Same decks, same opponents, same games-per-condition, same
first-player handling (natural slot alternation -- both the heuristic and the
search-augmented version delegate the IS_FIRST decision to the unmodified
dragapult_fix_v1 agent underneath, so both share its "always elect first"
behavior and therefore get a genuine, balanced 50/50 first/second split
against every opponent here, same as Phase 7/8).
"""

import argparse
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

import cg.game as g  # noqa: E402
from cg.api import LogType, to_observation_class  # noqa: E402

from src.agents import abomasnow_agent, dragapult_agent_always_first as dragapult_variant, iono_agent, lucario_ex_agent  # noqa: E402
from src.agents.search_lookahead import SearchStats, make_search_augmented_agent  # noqa: E402
from tools.tournament import GameResult, compute_leaderboard, write_leaderboard_csv  # noqa: E402


def play_one_game_search_safe(run_id, game_index, agent_a_name, agent_a_fn, deck_a, agent_b_name, agent_b_fn, deck_b, a_slot0, max_steps):
    """Same as tools.tournament.play_one_game, EXCEPT it does NOT strip
    obs["search_begin_input"] before calling the agent -- that field is
    required for search_begin() to work (see src/agents/search_lookahead.py),
    and tools.tournament.play_one_game's `obs.pop("search_begin_input", None)`
    (needed there only because raw obs dicts were otherwise never touched
    post-hoc) would make every search_begin() call fail with "Not agent
    observation." Kept as a separate function rather than changing the shared
    harness, since no other experiment in this project uses the Search API and
    the shared harness's existing behavior shouldn't change for them.
    """
    slot_names = [agent_a_name, agent_b_name] if a_slot0 else [agent_b_name, agent_a_name]
    slot_fns = [agent_a_fn, agent_b_fn] if a_slot0 else [agent_b_fn, agent_a_fn]
    deck0 = deck_a if a_slot0 else deck_b
    deck1 = deck_b if a_slot0 else deck_a
    agent_a_slot = 0 if a_slot0 else 1

    steps = 0
    turns = 0
    first_player_slot = None
    winner_slot = None
    winner_agent = None
    win_reason = None
    aborted = False
    error = None
    battle_started = False

    try:
        obs, start = g.battle_start(deck0, deck1)
        if start.errorPlayer != -1:
            raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")
        battle_started = True

        while obs["current"]["result"] < 0 and steps < max_steps:
            idx = obs["current"]["yourIndex"]
            action = slot_fns[idx](obs)
            obs = g.battle_select(action)
            steps += 1
            turns = obs["current"]["turn"]

        if obs["current"]["result"] < 0:
            aborted = True
            error = f"max_steps ({max_steps}) exceeded without a result"
        else:
            final = to_observation_class(obs)
            winner_slot = final.current.result
            first_player_slot = final.current.firstPlayer
            if winner_slot in (0, 1):
                winner_agent = slot_names[winner_slot]
            elif winner_slot == 2:
                winner_agent = "draw"
            for log in final.logs:
                if log.type == LogType.RESULT:
                    win_reason = log.reason
    except Exception as e:  # noqa: BLE001
        aborted = True
        error = f"{type(e).__name__}: {e}"
    finally:
        if battle_started:
            try:
                g.battle_finish()
            except Exception:
                pass

    return GameResult(
        run_id=run_id, game_index=game_index, agent_a_name=agent_a_name, agent_b_name=agent_b_name,
        agent_a_slot=agent_a_slot, first_player_slot=first_player_slot, winner_slot=winner_slot,
        winner_agent=winner_agent, win_reason=win_reason, turns=turns, steps=steps, aborted=aborted, error=error,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
ABOMASNOW_CORRECTED_DECK = [int(x) for x in (REPO_ROOT / "decks" / "abomasnow_ex_corrected_v1.csv").read_text().split("\n")[:60]]

OPPONENTS = {
    "abomasnow_agent": (abomasnow_agent.agent, ABOMASNOW_CORRECTED_DECK, "abomasnow_corrected"),
    "iono_agent": (iono_agent.agent, iono_agent.DECK, "iono_agent"),
    "lucario_ex_agent": (lucario_ex_agent.agent, lucario_ex_agent.DECK, "lucario_ex_agent"),
}


def run_condition(opponent_key: str, use_search: bool, n_games: int, out_dir: Path, max_steps: int):
    condition = "dragapult_plus_search" if use_search else "dragapult_heuristic_only"
    cond_dir = out_dir / f"{opponent_key}__{condition}"
    games_dir = cond_dir / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    opp_fn, opp_deck, opp_name = OPPONENTS[opponent_key]

    stats = SearchStats()
    if use_search:
        drag_fn = make_search_augmented_agent(dragapult_variant.agent, dragapult_variant.DECK, opp_deck, stats)
    else:
        drag_fn = dragapult_variant.agent

    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    jsonl_path = games_dir / f"{run_id}.jsonl"

    print(f"[{condition} vs {opponent_key}] {n_games} games")
    results = []
    for i in range(n_games):
        a_slot0 = i % 2 == 0
        result = play_one_game_search_safe(
            run_id, i, "dragapult_fix_v1", drag_fn, dragapult_variant.DECK, opp_name, opp_fn, opp_deck,
            a_slot0, max_steps,
        )
        results.append(result)
        if (i + 1) % 100 == 0 or i == n_games - 1:
            n_ab = sum(1 for r in results if r.aborted)
            n_wins = sum(1 for r in results if not r.aborted and r.winner_agent == "dragapult_fix_v1")
            print(f"  [{i + 1}/{n_games}] aborted={n_ab} wins_so_far={n_wins}")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")

    rows = compute_leaderboard(games_dir)
    write_leaderboard_csv(rows, cond_dir / "leaderboard.csv")

    n_aborted = sum(1 for r in results if r.aborted)
    n_decided = n_games - n_aborted
    n_wins = sum(1 for r in results if not r.aborted and r.winner_agent == "dragapult_fix_v1")
    win_rate = n_wins / n_decided if n_decided else None
    print(f"  RESULT: win_rate={win_rate} ({n_wins}/{n_decided}), aborted={n_aborted}, search_stats={stats if use_search else 'n/a'}")
    return {
        "opponent": opponent_key, "condition": condition, "games": n_games, "aborted": n_aborted,
        "decided": n_decided, "wins": n_wins, "win_rate": win_rate,
        "search_stats": asdict(stats) if use_search else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=500)
    parser.add_argument("--out-dir", default="results/search_1ply_experiment")
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--opponents", nargs="+", default=list(OPPONENTS.keys()))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    summary = []
    for opp in args.opponents:
        for use_search in (False, True):
            summary.append(run_condition(opp, use_search, args.games, out_dir, args.max_steps))

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nSummary:")
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
