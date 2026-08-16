"""Local A/B tournament harness driving the real cg engine directly
(cg.game.battle_start/battle_select/battle_finish) -- lighter weight than
kaggle_environments for local iteration.

Key properties (see docs/environment.md and the plan file for how these were
verified against the C++ engine source, not guessed):

- No engine-level RNG seed exists, so statistical confidence comes from
  running many games, not from reproducing a specific game.
- Player slot 0 always answers the "go first?" coin flip -- a real,
  non-symmetric advantage. This harness alternates which agent occupies slot
  0 across games and records the slot assignment per game so results can be
  split by first-player advantage.
- cg.game is a process-wide single-battle singleton: games run strictly
  sequentially, never concurrently, in this process.
- obs.current.yourIndex is exactly which player must act next.

Usage:
    python tools/tournament.py --agent-a src.agents.abomasnow_agent \
        --agent-b src.agents.iono_agent --games 20 --out-dir results/smoke
"""

import argparse
import importlib
import importlib.util
import json
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

import cg.game as g  # noqa: E402
from cg.api import LogType, to_observation_class  # noqa: E402

from src.logging.decision_logger import DecisionLogger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class GameResult:
    run_id: str
    game_index: int
    agent_a_name: str
    agent_b_name: str
    agent_a_slot: int  # 0 or 1: which engine slot agent A occupied this game
    first_player_slot: int | None  # 0 or 1: which slot answered "go first" yes
    winner_slot: int | None  # 0/1 winner, 2 draw, None if aborted
    winner_agent: str | None  # resolved name, or "draw", or None if aborted
    win_reason: int | None  # RESULT log reason: 1=0 prizes,2=decked,3=no active,4=card effect
    turns: int
    steps: int
    aborted: bool
    error: str | None


def load_agent(spec: str, deck_override: str | None = None, name_override: str | None = None):
    """spec: a dotted module path (e.g. src.agents.abomasnow_agent) OR a
    filesystem path to a .py file (e.g. the official sample_submission's
    main.py, which lives under the git-ignored data/official/ and is not a
    dotted-importable package member).

    Returns (name, agent_fn, deck: list[int]).
    """
    p = Path(spec)
    if spec.endswith(".py") or p.suffix == ".py":
        p = p.resolve()
        mod_name = f"_tournament_loaded_{p.stem}_{abs(hash(str(p))) % 10**8}"
        spec_obj = importlib.util.spec_from_file_location(mod_name, p)
        module = importlib.util.module_from_spec(spec_obj)
        sys.modules[mod_name] = module
        spec_obj.loader.exec_module(module)
        name = p.stem
    else:
        module = importlib.import_module(spec)
        name = spec.rsplit(".", 1)[-1]

    if name_override:
        name = name_override

    agent_fn = module.agent
    if deck_override:
        deck_path = Path(deck_override)
        deck = [int(x) for x in deck_path.read_text().split("\n")[:60]]
    else:
        deck = getattr(module, "DECK", None)
        if deck is None:
            raise ValueError(f"{spec} exposes no DECK attribute; pass a deck override for it")
    return name, agent_fn, deck


def play_one_game(
    run_id: str,
    game_index: int,
    agent_a_name: str,
    agent_a_fn,
    deck_a: list[int],
    agent_b_name: str,
    agent_b_fn,
    deck_b: list[int],
    a_slot0: bool,
    max_steps: int,
    decision_logger: DecisionLogger | None,
) -> GameResult:
    game_id = f"{run_id}_{game_index}"
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
            obs.pop("search_begin_input", None)
            idx = obs["current"]["yourIndex"]
            action = slot_fns[idx](obs)
            if decision_logger is not None and decision_logger.enabled:
                decision_logger.log_decision(game_id, to_observation_class(obs), action)
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
                # log.type/log.reason are raw ints from the engine's JSON (the
                # to_dataclass() helper does not coerce scalar fields into
                # their IntEnum types), so compare against LogType.RESULT's
                # int value directly.
                if log.type == LogType.RESULT:
                    win_reason = log.reason
    except Exception as e:  # noqa: BLE001 - a single bad game must not kill the batch
        aborted = True
        error = f"{type(e).__name__}: {e}"
    finally:
        if battle_started:
            try:
                g.battle_finish()
            except Exception:
                pass

    return GameResult(
        run_id=run_id,
        game_index=game_index,
        agent_a_name=agent_a_name,
        agent_b_name=agent_b_name,
        agent_a_slot=agent_a_slot,
        first_player_slot=first_player_slot,
        winner_slot=winner_slot,
        winner_agent=winner_agent,
        win_reason=win_reason,
        turns=turns,
        steps=steps,
        aborted=aborted,
        error=error,
    )


def compute_leaderboard(games_dir: Path) -> list[dict]:
    """Recomputes an aggregate leaderboard from EVERY raw per-game jsonl file
    under games_dir (not just the most recent run), keyed by unordered agent
    pair, split by which agent occupied slot 0 (first-player advantage).
    Never reads/writes over the raw per-game files themselves.
    """
    pair_stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "games": 0,
            "aborted": 0,
            "draws": 0,
            "x_wins": 0,
            "y_wins": 0,
            "x_wins_as_slot0": 0,
            "x_games_as_slot0": 0,
            "x_wins_as_slot1": 0,
            "x_games_as_slot1": 0,
        }
    )
    for jsonl_path in sorted(games_dir.glob("*.jsonl")):
        if jsonl_path.name.endswith("_decisions.jsonl"):
            continue
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            a, b = r["agent_a_name"], r["agent_b_name"]
            x, y = sorted((a, b))
            stats = pair_stats[(x, y)]
            stats["games"] += 1
            if r["aborted"]:
                stats["aborted"] += 1
                continue
            if r["winner_agent"] == "draw":
                stats["draws"] += 1
                continue
            winner = r["winner_agent"]
            x_was_slot0 = (a == x and r["agent_a_slot"] == 0) or (b == x and r["agent_a_slot"] == 1)
            if x_was_slot0:
                stats["x_games_as_slot0"] += 1
            else:
                stats["x_games_as_slot1"] += 1
            if winner == x:
                stats["x_wins"] += 1
                if x_was_slot0:
                    stats["x_wins_as_slot0"] += 1
                else:
                    stats["x_wins_as_slot1"] += 1
            elif winner == y:
                stats["y_wins"] += 1

    rows = []
    for (x, y), s in sorted(pair_stats.items()):
        decided = s["games"] - s["aborted"] - s["draws"]
        rows.append(
            {
                "agent_x": x,
                "agent_y": y,
                "games": s["games"],
                "aborted": s["aborted"],
                "draws": s["draws"],
                "x_wins": s["x_wins"],
                "y_wins": s["y_wins"],
                "x_win_rate_overall": round(s["x_wins"] / decided, 4) if decided else None,
                "x_win_rate_as_slot0": round(s["x_wins_as_slot0"] / s["x_games_as_slot0"], 4) if s["x_games_as_slot0"] else None,
                "x_win_rate_as_slot1": round(s["x_wins_as_slot1"] / s["x_games_as_slot1"], 4) if s["x_games_as_slot1"] else None,
                "x_games_as_slot0": s["x_games_as_slot0"],
                "x_games_as_slot1": s["x_games_as_slot1"],
            }
        )
    return rows


def write_leaderboard_csv(rows: list[dict], path: Path) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "agent_x",
        "agent_y",
        "games",
        "aborted",
        "draws",
        "x_wins",
        "y_wins",
        "x_win_rate_overall",
        "x_win_rate_as_slot0",
        "x_win_rate_as_slot1",
        "x_games_as_slot0",
        "x_games_as_slot1",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_tournament(
    agent_a_spec: str,
    agent_b_spec: str,
    n_games: int,
    out_dir: str,
    deck_a: str | None = None,
    deck_b: str | None = None,
    name_a: str | None = None,
    name_b: str | None = None,
    max_steps: int = 2000,
    log_decisions: bool = False,
) -> Path:
    out_dir_p = Path(out_dir)
    games_dir = out_dir_p / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    jsonl_path = games_dir / f"{run_id}.jsonl"

    agent_a_name, agent_a_fn, deck_a_cards = load_agent(agent_a_spec, deck_a, name_a)
    agent_b_name, agent_b_fn, deck_b_cards = load_agent(agent_b_spec, deck_b, name_b)

    decision_logger = None
    if log_decisions:
        decision_logger = DecisionLogger(enabled=True, out_path=games_dir / f"{run_id}_decisions.jsonl")

    print(f"Run {run_id}: {agent_a_name} vs {agent_b_name}, {n_games} games, max_steps={max_steps}")

    results: list[GameResult] = []
    for i in range(n_games):
        a_slot0 = i % 2 == 0
        result = play_one_game(
            run_id, i, agent_a_name, agent_a_fn, deck_a_cards, agent_b_name, agent_b_fn, deck_b_cards, a_slot0, max_steps, decision_logger
        )
        results.append(result)
        if decision_logger is not None:
            decision_logger.finalize_game(
                f"{run_id}_{i}",
                {"winner_slot": result.winner_slot, "winner_agent": result.winner_agent, "win_reason": result.win_reason, "aborted": result.aborted},
            )
        status = "ABORTED: " + result.error if result.aborted else f"winner={result.winner_agent} reason={result.win_reason}"
        print(f"  [{i + 1}/{n_games}] a_slot0={a_slot0} steps={result.steps} turns={result.turns} {status}")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")

    rows = compute_leaderboard(games_dir)
    write_leaderboard_csv(rows, out_dir_p / "leaderboard.csv")

    n_aborted = sum(1 for r in results if r.aborted)
    print(f"Done. {n_games - n_aborted}/{n_games} completed cleanly. Raw results: {jsonl_path}")
    print(f"Leaderboard (all runs under {games_dir}): {out_dir_p / 'leaderboard.csv'}")
    return jsonl_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-a", required=True, help="dotted module path or .py file path")
    parser.add_argument("--agent-b", required=True, help="dotted module path or .py file path")
    parser.add_argument("--deck-a", default=None, help="deck.csv path override for agent A (required if it has no DECK attribute)")
    parser.add_argument("--deck-b", default=None, help="deck.csv path override for agent B")
    parser.add_argument("--name-a", default=None, help="display name override for agent A")
    parser.add_argument("--name-b", default=None, help="display name override for agent B")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--out-dir", default="results")
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--log-decisions", action="store_true")
    args = parser.parse_args()

    run_tournament(
        args.agent_a,
        args.agent_b,
        args.games,
        args.out_dir,
        deck_a=args.deck_a,
        deck_b=args.deck_b,
        name_a=args.name_a,
        name_b=args.name_b,
        max_steps=args.max_steps,
        log_decisions=args.log_decisions,
    )


if __name__ == "__main__":
    main()
