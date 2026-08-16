"""Phase 1 controlled experiment: isolate Dragapult ex's win rate when going
first vs. second, against each opponent, with a large enough sample per
condition to draw a conclusion.

Why this can't just be "alternate engine slot 0/1 and look at the natural
first_player_slot" (what tools/tournament.py's normal alternation gives you):
the engine only ever asks the player in ENGINE SLOT 0 the "go first?"
yes/no question (verified directly against
data/official/ptcg_engine/ptcgProgram 22/SetupProc.h: SetYesNoSelect(state,
SelectContext::IsFirst, 0) -- the 0 is the asked player index, not a
hardcoded answer). Both src/agents/dragapult_agent.py (answers NO
unconditionally -- score=-1 for YES under SelectContext.IS_FIRST, vs. NO's
unscored default of 0) and src/agents/abomasnow_agent.py /
src/agents/iono_agent.py (answer YES unconditionally -- score=1 for YES,
still beats NO's default 0) are DETERMINISTIC on this decision. So natural
alternation of which agent sits in engine slot 0 does not naturally produce
a balanced first/second split for Dragapult vs. Abomasnow/Iono -- confirmed
empirically against the existing results/games/*.jsonl raw data: Dragapult
was second in 200/200 games vs. both Abomasnow and Iono, regardless of
engine slot.

This script instead always seats Dragapult in engine slot 0 (so it is
always the one asked) and wraps its agent function so that, ONLY for the
IS_FIRST decision, the wrapper directly returns the desired YES or NO
option index -- bypassing the agent's own (deterministic) scoring for that
one decision but leaving every other decision completely untouched. This
gives a clean, fully-controlled first-vs-second comparison. It does not
modify src/agents/dragapult_agent.py itself (BEST_DRAGAPULT_AGENT is
untouched); the wrapper lives only in this experiment script.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

from cg.api import OptionType, SelectContext, to_observation_class  # noqa: E402

from tools.tournament import (  # noqa: E402
    DecisionLogger,
    compute_leaderboard,
    load_agent,
    play_one_game,
    write_leaderboard_csv,
)

import json  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from dataclasses import asdict  # noqa: E402


def force_is_first_wrapper(agent_fn, force_yes: bool):
    """Wraps agent_fn so the IS_FIRST select is answered deterministically
    (force_yes=True -> always go first; False -> always go second), and every
    other decision is delegated unchanged to agent_fn."""

    def wrapped(obs_dict: dict) -> list[int]:
        if obs_dict.get("select") is not None:
            obs = to_observation_class(obs_dict)
            if obs.select is not None and obs.select.context == SelectContext.IS_FIRST:
                want = OptionType.YES if force_yes else OptionType.NO
                for i, o in enumerate(obs.select.option):
                    if o.type == want:
                        return [i]
        return agent_fn(obs_dict)

    return wrapped


REPO_ROOT = Path(__file__).resolve().parents[1]
RANDOM_MAIN = str(REPO_ROOT / "data" / "official" / "sample_submission" / "sample_submission" / "main.py")
RANDOM_DECK = str(REPO_ROOT / "data" / "official" / "sample_submission" / "sample_submission" / "deck.csv")

ABOMASNOW_CORRECTED_DECK = str(REPO_ROOT / "decks" / "abomasnow_ex_corrected_v1.csv")

OPPONENTS = {
    "random_agent": (RANDOM_MAIN, RANDOM_DECK, "random_agent"),
    "abomasnow_agent": ("src.agents.abomasnow_agent", ABOMASNOW_CORRECTED_DECK, "abomasnow_corrected"),
    "iono_agent": ("src.agents.iono_agent", None, None),
    "lucario_ex_agent": ("src.agents.lucario_ex_agent", None, None),
}


def run_condition(opponent_key: str, force_yes: bool, n_games: int, out_dir: Path, max_steps: int):
    condition = "dragapult_first" if force_yes else "dragapult_second"
    cond_dir = out_dir / f"{opponent_key}__{condition}"
    games_dir = cond_dir / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    drag_name, drag_fn, drag_deck = load_agent("src.agents.dragapult_agent")
    drag_fn = force_is_first_wrapper(drag_fn, force_yes)

    spec, deck_override, name_override = OPPONENTS[opponent_key]
    opp_name, opp_fn, opp_deck = load_agent(spec, deck_override, name_override)

    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    jsonl_path = games_dir / f"{run_id}.jsonl"
    decision_logger = DecisionLogger(enabled=True, out_path=games_dir / f"{run_id}_decisions.jsonl")

    print(f"[{condition} vs {opponent_key}] {n_games} games, dragapult always engine-slot0, forced_yes={force_yes}")
    results = []
    for i in range(n_games):
        result = play_one_game(
            run_id, i, drag_name, drag_fn, drag_deck, opp_name, opp_fn, opp_deck,
            True,  # dragapult ALWAYS engine slot 0 -- it's always the one asked IS_FIRST
            max_steps, decision_logger,
        )
        results.append(result)
        decision_logger.finalize_game(
            f"{run_id}_{i}",
            {"winner_slot": result.winner_slot, "winner_agent": result.winner_agent, "win_reason": result.win_reason, "aborted": result.aborted},
        )
        if (i + 1) % 100 == 0 or i == n_games - 1:
            n_done = i + 1
            n_ab = sum(1 for r in results if r.aborted)
            print(f"  [{n_done}/{n_games}] aborted={n_ab}")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")

    rows = compute_leaderboard(games_dir)
    write_leaderboard_csv(rows, cond_dir / "leaderboard.csv")

    n_aborted = sum(1 for r in results if r.aborted)
    n_decided = n_games - n_aborted
    n_drag_wins = sum(1 for r in results if not r.aborted and r.winner_agent == drag_name)
    win_rate = n_drag_wins / n_decided if n_decided else None
    # sanity check: first_player_slot must equal 0 (dragapult's engine slot) for every
    # forced-first game, and 1 for every forced-second game, or the wrapper is broken.
    bad = [r for r in results if not r.aborted and ((r.first_player_slot == 0) != force_yes)]
    print(f"  RESULT: dragapult win_rate={win_rate} ({n_drag_wins}/{n_decided}), aborted={n_aborted}, "
          f"coinflip-mismatch(should be 0)={len(bad)}")
    return {
        "opponent": opponent_key,
        "condition": condition,
        "games": n_games,
        "aborted": n_aborted,
        "decided": n_decided,
        "dragapult_wins": n_drag_wins,
        "win_rate": win_rate,
        "coinflip_mismatch": len(bad),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--out-dir", default="results/dragapult_first_second")
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--opponents", nargs="+", default=list(OPPONENTS.keys()))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    summary = []
    for opp in args.opponents:
        for force_yes in (True, False):
            summary.append(run_condition(opp, force_yes, args.games, out_dir, args.max_steps))

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary written to {summary_path}")
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
