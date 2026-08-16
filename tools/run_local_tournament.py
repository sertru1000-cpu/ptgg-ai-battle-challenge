"""Fast headless local A/B tournament: V6 (Balanced weights, static heuristic)
vs V16 (XGBoost dynamic weight switching).

1000 games total against the real cg engine (cg.game.battle_start /
battle_select / battle_finish, via tools.tournament.play_one_game). V6
occupies engine slot 0 for exactly the first 500 games and V16 occupies
engine slot 0 for exactly the remaining 500 games -- a clean 500/500 split
of first-turn advantage between the two agents.

Why alternating engine slot 0 is enough to control who is "Player 1": the
engine only ever asks the agent in slot 0 the "go first?" yes/no question
(see tools/dragapult_first_second_experiment.py's docstring for the C++
source citation), and both dragapult_agent_v6.agent and
dragapult_agent_v16.agent are built with always_first=True (they answer YES
unconditionally whenever asked). So whichever agent sits in slot 0 always
wins the coin flip and goes first -- no forced-answer wrapper is needed here,
just an exact 500/500 split of which agent occupies slot 0.

Usage:
    python tools/run_local_tournament.py
"""

import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.tournament import load_agent, play_one_game  # noqa: E402

N_GAMES = 1000
MAX_STEPS = 2000

WIN_REASON_LABELS = {
    1: "All Prizes Taken",
    2: "Deck Out",
    3: "No Active Pokemon",
    4: "Card Effect",
}


def run_tournament():
    v6_name, v6_fn, v6_deck = load_agent("src.agents.dragapult_agent_v6")
    v16_name, v16_fn, v16_deck = load_agent("src.agents.dragapult_agent_v16")

    half = N_GAMES // 2  # 500

    results = []
    for i in range(N_GAMES):
        v6_is_player1 = i < half  # first 500 games: V6 in slot 0 (Player 1); remaining 500: V16 in slot 0
        with contextlib.redirect_stdout(io.StringIO()):
            result = play_one_game(
                run_id="v6_vs_v16_local",
                game_index=i,
                agent_a_name=v6_name,
                agent_a_fn=v6_fn,
                deck_a=v6_deck,
                agent_b_name=v16_name,
                agent_b_fn=v16_fn,
                deck_b=v16_deck,
                a_slot0=v6_is_player1,
                max_steps=MAX_STEPS,
                decision_logger=None,
            )
        results.append((result, v6_is_player1))

    return v6_name, v16_name, results


def build_report(v6_name: str, v16_name: str, results: list) -> str:
    n_games = len(results)
    aborted = [r for r, _ in results if r.aborted]
    decided = [(r, v6_first) for r, v6_first in results if not r.aborted and r.winner_agent != "draw"]
    draws = [r for r, _ in results if not r.aborted and r.winner_agent == "draw"]

    v6_wins = [r for r, _ in decided if r.winner_agent == v6_name]
    v16_wins = [r for r, _ in decided if r.winner_agent == v16_name]
    n_decided = len(decided)

    v6_winrate = len(v6_wins) / n_decided if n_decided else float("nan")
    v16_winrate = len(v16_wins) / n_decided if n_decided else float("nan")

    # Winrate by starting position (Player 1 = engine slot 0).
    v6_as_p1 = [(r, f) for r, f in decided if f]
    v6_as_p2 = [(r, f) for r, f in decided if not f]
    v6_wins_as_p1 = sum(1 for r, _ in v6_as_p1 if r.winner_agent == v6_name)
    v6_wins_as_p2 = sum(1 for r, _ in v6_as_p2 if r.winner_agent == v6_name)
    v16_wins_as_p1 = sum(1 for r, _ in v6_as_p2 if r.winner_agent == v16_name)  # V16 is P1 when V6 is not
    v16_wins_as_p2 = sum(1 for r, _ in v6_as_p1 if r.winner_agent == v16_name)  # V16 is P2 when V6 is P1

    v6_p1_rate = v6_wins_as_p1 / len(v6_as_p1) if v6_as_p1 else float("nan")
    v6_p2_rate = v6_wins_as_p2 / len(v6_as_p2) if v6_as_p2 else float("nan")
    v16_p1_rate = v16_wins_as_p1 / len(v6_as_p2) if v6_as_p2 else float("nan")
    v16_p2_rate = v16_wins_as_p2 / len(v6_as_p1) if v6_as_p1 else float("nan")

    # Average game length (turns) for games won by each agent.
    def avg_turns(rs):
        return sum(r.turns for r in rs) / len(rs) if rs else float("nan")

    v6_avg_turns = avg_turns(v6_wins)
    v16_avg_turns = avg_turns(v16_wins)

    # Win conditions.
    reason_counts = {label: 0 for label in WIN_REASON_LABELS.values()}
    reason_counts["Unknown"] = 0
    for r, _ in decided:
        label = WIN_REASON_LABELS.get(r.win_reason, "Unknown")
        reason_counts[label] += 1
    n_timeout = len(aborted)

    lines = []
    lines.append("# Local Tournament Report: V6 (Static Heuristic) vs V16 (XGBoost Dynamic)")
    lines.append("")
    lines.append(f"Games played: {n_games} | Decided: {n_decided} | Draws: {len(draws)} | Aborted/Timeout: {n_timeout}")
    lines.append("")
    lines.append("## Overall Winrate")
    lines.append("")
    lines.append("| Agent | Wins | Winrate |")
    lines.append("|---|---|---|")
    lines.append(f"| V6 ({v6_name}) | {len(v6_wins)} | {v6_winrate:.1%} |")
    lines.append(f"| V16 ({v16_name}) | {len(v16_wins)} | {v16_winrate:.1%} |")
    lines.append("")
    lines.append("## Winrate by Starting Position (Player 1 = went first)")
    lines.append("")
    lines.append("| Agent | As Player 1 | As Player 2 |")
    lines.append("|---|---|---|")
    lines.append(f"| V6 | {v6_wins_as_p1}/{len(v6_as_p1)} ({v6_p1_rate:.1%}) | {v6_wins_as_p2}/{len(v6_as_p2)} ({v6_p2_rate:.1%}) |")
    lines.append(f"| V16 | {v16_wins_as_p1}/{len(v6_as_p2)} ({v16_p1_rate:.1%}) | {v16_wins_as_p2}/{len(v6_as_p1)} ({v16_p2_rate:.1%}) |")
    lines.append("")
    lines.append("## Average Game Length (turns, wins only)")
    lines.append("")
    lines.append("| Agent | Avg Turns (in wins) |")
    lines.append("|---|---|")
    lines.append(f"| V6 | {v6_avg_turns:.1f} |")
    lines.append(f"| V16 | {v16_avg_turns:.1f} |")
    lines.append("")
    lines.append("## Win Conditions (decided games)")
    lines.append("")
    lines.append("| Condition | Count |")
    lines.append("|---|---|")
    for label, count in reason_counts.items():
        lines.append(f"| {label} | {count} |")
    lines.append(f"| Timeout (max_steps exceeded) | {n_timeout} |")
    lines.append("")

    return "\n".join(lines)


def main():
    v6_name, v16_name, results = run_tournament()
    report = build_report(v6_name, v16_name, results)
    print(report)


if __name__ == "__main__":
    main()
