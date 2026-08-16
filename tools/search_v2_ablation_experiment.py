"""Competitive V2, Part A6-A9: BEST_HEURISTIC vs. BEST_HEURISTIC + SEARCH_V2
ablation harness. Generalized over which agent is search-augmented (Dragapult
ex fix_v1 or Mega Lucario ex), per Part A7's required matchup list.

Records win rate, first/second-player split, game length, search call counts,
percentage of decisions searched, search failures/fallbacks, average search
latency, total game latency, and aborts -- Part A8's required metrics -- plus
a decision-level log (Part A9: when search changes the heuristic's choice, was
it right?) using only information visible to the acting player.
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
from cg.api import LogType, OptionType, SelectContext, to_observation_class  # noqa: E402

from src.agents import abomasnow_agent, dragapult_agent_always_first as dragapult_v, iono_agent, lucario_ex_agent  # noqa: E402
from src.agents.search_lookahead_v2 import SearchV2Stats, make_search_v2_agent  # noqa: E402
from tools.tournament import GameResult, compute_leaderboard, write_leaderboard_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
ABOMASNOW_CORRECTED_DECK = [int(x) for x in (REPO_ROOT / "decks" / "abomasnow_ex_corrected_v1.csv").read_text().split("\n")[:60]]
RANDOM_MAIN = REPO_ROOT / "data" / "official" / "sample_submission" / "sample_submission" / "main.py"
RANDOM_DECK = [int(x) for x in (REPO_ROOT / "data" / "official" / "sample_submission" / "sample_submission" / "deck.csv").read_text().split("\n")[:60]]


def _load_random_agent():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_random_main_v2", RANDOM_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


AGENTS = {
    "abomasnow_agent": (abomasnow_agent.agent, ABOMASNOW_CORRECTED_DECK, "abomasnow_corrected"),
    "iono_agent": (iono_agent.agent, iono_agent.DECK, "iono_agent"),
    "lucario_ex_agent": (lucario_ex_agent.agent, lucario_ex_agent.DECK, "lucario_ex_agent"),
    "dragapult_agent": (dragapult_v.agent, dragapult_v.DECK, "dragapult_fix_v1"),
    "random_agent": (None, RANDOM_DECK, "random_agent"),  # loaded lazily below
}

BASE_AGENTS = {
    "dragapult_fix_v1": (dragapult_v.agent, dragapult_v.DECK, "dragapult_fix_v1"),
    "lucario_ex_agent": (lucario_ex_agent.agent, lucario_ex_agent.DECK, "lucario_ex_agent"),
}


def play_one_game_search_safe(run_id, game_index, agent_a_name, agent_a_fn, deck_a, agent_b_name, agent_b_fn, deck_b, a_slot0, max_steps, decision_log, search_side_is_a, search_stats):
    """Same shape as tools.tournament.play_one_game but (a) does not strip
    obs["search_begin_input"] (see tools/search_ablation_experiment.py's
    identical rationale) and (b) records per-decision search-vs-heuristic
    disagreement data for Part A9, using only info visible to the acting
    player -- no hidden opponent state is read.
    """
    slot_names = [agent_a_name, agent_b_name] if a_slot0 else [agent_b_name, agent_a_name]
    slot_fns = [agent_a_fn, agent_b_fn] if a_slot0 else [agent_b_fn, agent_a_fn]
    search_slot = (0 if a_slot0 else 1) if search_side_is_a else (1 if a_slot0 else 0)
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
    t_start = time.perf_counter()

    try:
        obs, start = g.battle_start(deck0, deck1)
        if start.errorPlayer != -1:
            raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")
        battle_started = True

        while obs["current"]["result"] < 0 and steps < max_steps:
            idx = obs["current"]["yourIndex"]
            pre_changed = search_stats.search_changed_choice if idx == search_slot else None
            action = slot_fns[idx](obs)
            if idx == search_slot and decision_log is not None and pre_changed is not None and search_stats.search_changed_choice > pre_changed:
                o = to_observation_class(obs)
                decision_log.append({
                    "turn": o.current.turn,
                    "context": SelectContext(o.select.context).name if o.select else None,
                    "n_options": len(o.select.option) if o.select else None,
                    "chosen": action,
                })
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
            if decision_log is not None:
                for rec in decision_log:
                    rec["game_outcome"] = winner_agent
    except Exception as e:  # noqa: BLE001
        aborted = True
        error = f"{type(e).__name__}: {e}"
    finally:
        if battle_started:
            try:
                g.battle_finish()
            except Exception:
                pass

    elapsed = time.perf_counter() - t_start
    result = GameResult(
        run_id=run_id, game_index=game_index, agent_a_name=agent_a_name, agent_b_name=agent_b_name,
        agent_a_slot=agent_a_slot, first_player_slot=first_player_slot, winner_slot=winner_slot,
        winner_agent=winner_agent, win_reason=win_reason, turns=turns, steps=steps, aborted=aborted, error=error,
    )
    return result, elapsed


def run_condition(base_name: str, opponent_key: str, use_search: bool, n_games: int, out_dir: Path, max_steps: int):
    condition = f"{base_name}_plus_search_v2" if use_search else f"{base_name}_heuristic_only"
    cond_dir = out_dir / f"{base_name}__vs__{opponent_key}__{condition}"
    games_dir = cond_dir / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    base_fn, base_deck, base_display = BASE_AGENTS[base_name]

    if opponent_key == "random_agent":
        opp_fn = _load_random_agent()
        opp_deck = RANDOM_DECK
        opp_name = "random_agent"
    else:
        opp_fn, opp_deck, opp_name = AGENTS[opponent_key]

    stats = SearchV2Stats()
    if use_search:
        agent_fn = make_search_v2_agent(base_fn, base_deck, opp_deck, stats)
    else:
        agent_fn = base_fn

    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    jsonl_path = games_dir / f"{run_id}.jsonl"
    decisions_path = games_dir / f"{run_id}_decisions.jsonl"

    print(f"[{condition} vs {opponent_key}] {n_games} games")
    results = []
    latencies = []
    all_decision_logs = []
    for i in range(n_games):
        a_slot0 = i % 2 == 0
        decision_log = [] if use_search else None
        result, elapsed = play_one_game_search_safe(
            run_id, i, base_display, agent_fn, base_deck, opp_name, opp_fn, opp_deck,
            a_slot0, max_steps, decision_log, search_side_is_a=True, search_stats=stats,
        )
        results.append(result)
        latencies.append(elapsed)
        if decision_log:
            all_decision_logs.extend(decision_log)
        if (i + 1) % 100 == 0 or i == n_games - 1:
            n_ab = sum(1 for r in results if r.aborted)
            n_wins = sum(1 for r in results if not r.aborted and r.winner_agent == base_display)
            print(f"  [{i + 1}/{n_games}] aborted={n_ab} wins_so_far={n_wins}")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")
    if all_decision_logs:
        with open(decisions_path, "w", encoding="utf-8") as f:
            for rec in all_decision_logs:
                f.write(json.dumps(rec) + "\n")

    rows = compute_leaderboard(games_dir)
    write_leaderboard_csv(rows, cond_dir / "leaderboard.csv")

    n_aborted = sum(1 for r in results if r.aborted)
    n_decided = n_games - n_aborted
    n_wins = sum(1 for r in results if not r.aborted and r.winner_agent == base_display)
    n_wins_first = sum(1 for r in results if not r.aborted and r.winner_agent == base_display and r.first_player_slot == r.agent_a_slot)
    n_games_first = sum(1 for r in results if not r.aborted and r.first_player_slot == r.agent_a_slot)
    n_wins_second = n_wins - n_wins_first
    n_games_second = n_decided - n_games_first
    win_rate = n_wins / n_decided if n_decided else None
    avg_turns = sum(r.turns for r in results if not r.aborted) / n_decided if n_decided else None
    avg_latency = sum(latencies) / len(latencies) if latencies else None
    summary = {
        "base_agent": base_name, "opponent": opponent_key, "condition": condition, "games": n_games,
        "aborted": n_aborted, "decided": n_decided, "wins": n_wins, "win_rate": win_rate,
        "win_rate_first": (n_wins_first / n_games_first) if n_games_first else None,
        "win_rate_second": (n_wins_second / n_games_second) if n_games_second else None,
        "games_first": n_games_first, "games_second": n_games_second,
        "avg_turns": avg_turns, "avg_game_latency_s": avg_latency,
        "search_stats": asdict(stats) if use_search else None,
    }
    print(f"  RESULT: win_rate={win_rate} ({n_wins}/{n_decided}), aborted={n_aborted}, avg_latency={avg_latency:.4f}s, search_stats={stats if use_search else 'n/a'}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=500)
    parser.add_argument("--out-dir", default="results/search_v2_ablation")
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--matchups", nargs="+", required=True, help="base_agent:opponent pairs, e.g. dragapult_fix_v1:iono_agent")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    summary = []
    for m in args.matchups:
        base_name, opponent_key = m.split(":")
        for use_search in (False, True):
            summary.append(run_condition(base_name, opponent_key, use_search, args.games, out_dir, args.max_steps))

    summary_path = out_dir / f"summary_{uuid.uuid4().hex[:8]}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary written to {summary_path}")
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
