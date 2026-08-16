"""Divergence root-cause analysis: for every V17 decision where a real MCTS
search ran, record whether MCTS's final pick differs from V6's own raw
greedy pick, and whether any rollout backing that decision ever hit a
terminal (+-1,000,000) reward -- see cpp/mcts.hpp's `kTerminalRewardThreshold`
comment for why that specifically matters (an unweighted mean mixing rare
+-1,000,000 samples with typical few-hundred-to-few-thousand non-terminal
`state_value()` scores can swing a candidate's mean by orders of magnitude
off a single rollout).

Existing `results/v17_vs_v6_stress/raw_games.jsonl` only has per-game
aggregates (no per-decision action content), so this is a FRESH data
collection, not a re-parse of the 200-game run -- adapts the user-provided
divergence-analysis script's *intent* (bucket divergence patterns, show
fatal-vs-total occurrence, win rate when diverged, concrete examples) to
this project's actual schema (native_bridge.LAST_CALL_STATS's
greedy_index/mcts_index/hit_terminal_reward, not a `turns`/`action_taken`
per-game log that was never produced here).

Output (never overwrites prior stress-test data, writes to its own
directory): results/v17_divergence/
  - raw_decisions.jsonl   one row per V17 decision where MCTS actually ran
  - raw_games.jsonl       one row per game (winner, slot)
  - report.md             the pattern breakdown + examples

Usage:
    python tools/analyze_v17_divergence.py --games 60
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "results" / "v17_divergence"
DECISIONS_PATH = OUT_DIR / "raw_decisions.jsonl"
GAMES_PATH = OUT_DIR / "raw_games.jsonl"
REPORT_PATH = OUT_DIR / "report.md"

MAX_STEPS = 2000


def _load_card_names() -> dict:
    """id -> name, from the official card data CSV (ground truth for card
    names -- same file the rest of this project treats as authoritative)."""
    import csv

    path = REPO_ROOT / "data" / "official" / "EN Card Data.csv"
    names: dict = {}
    if not path.exists():
        return names
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                cid = int(row["Card ID"])
            except (ValueError, KeyError):
                continue
            names[cid] = row.get("Card Name", "").strip()
    return names


_CARD_NAMES = _load_card_names()


def _resolve_card_id(obs, my_index: int, option) -> "int | None":
    """PLAY and EVOLVE (among others) do NOT populate `cardId` at all -- per
    cg.api's own OptionType docstring, PLAY only carries `index` (implicitly
    into HAND, no `area` field), and EVOLVE carries `area`+`index` pointing at
    the evolution card's own location (observed to always be HAND in
    practice, but resolved generally here rather than assumed). This is the
    piece the first version of this script was missing -- it only read the
    already-populated `cardId`/`attackId` fields, which are None for exactly
    the option types (PLAY/EVOLVE) this investigation cares about."""
    from cg.api import AreaType

    if option.index is None or option.index < 0:
        return None
    my_state = obs.current.players[my_index]
    zone = None
    if option.type == 7:  # PLAY
        zone = my_state.hand
    elif option.area == int(AreaType.HAND):
        zone = my_state.hand
    elif option.area == int(AreaType.DISCARD):
        zone = my_state.discard
    if zone is None or option.index >= len(zone):
        return None
    card = zone[option.index]
    return card.id if card is not None else None


def _option_desc(obs, my_index: int, select_options: list, index: int) -> dict:
    """Compact, human-readable description of obs.select.option[index], or a
    placeholder if index is out of range (e.g. -1 sentinel: no override)."""
    if index is None or index < 0 or index >= len(select_options):
        return {"type": None, "type_name": "NONE", "attackId": None, "cardId": None, "area": None, "resolvedCardId": None, "cardName": None}
    o = select_options[index]
    from cg.api import OptionType

    try:
        type_name = OptionType(int(o.type)).name
    except ValueError:
        type_name = f"UNKNOWN({int(o.type)})"
    resolved_id = _resolve_card_id(obs, my_index, o)
    return {
        "type": int(o.type),
        "type_name": type_name,
        "attackId": o.attackId,
        "cardId": o.cardId,
        "area": int(o.area) if o.area is not None else None,
        "resolvedCardId": resolved_id,
        "cardName": _CARD_NAMES.get(resolved_id, f"UNKNOWN_ID({resolved_id})") if resolved_id is not None else None,
    }


def run_collection(n_games: int) -> None:
    from tools.tournament import load_agent
    from tools.stress_test_v17 import _play_one_game_keep_search_input

    import src.agents.final_candidate_agent_v17 as v17_mod
    import src.agents.final_candidate_agent_v6 as v6_mod
    from src.agents.dragapult_agent_v17_cpp import native_bridge
    from cg.api import to_observation_class

    v17_name, v17_fn, v17_deck = load_agent("src.agents.final_candidate_agent_v17", name_override="v17_cpp_mcts")
    v6_name, v6_fn, v6_deck = load_agent("src.agents.final_candidate_agent_v6", name_override="v6_heuristic")

    half = n_games // 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    decisions_f = open(DECISIONS_PATH, "w", encoding="utf-8")
    games_f = open(GAMES_PATH, "w", encoding="utf-8")

    for i in range(n_games):
        v17_slot0 = i < half
        decision_index = [0]

        def timed_v17(obs_dict, _i=i):
            native_bridge.LAST_CALL_STATS["eligible"] = False
            native_bridge.LAST_CALL_STATS["search_begin_ok"] = False
            native_bridge.LAST_CALL_STATS["visits"] = 0
            native_bridge.LAST_CALL_STATS["greedy_index"] = -1
            native_bridge.LAST_CALL_STATS["mcts_index"] = -1
            native_bridge.LAST_CALL_STATS["hit_terminal_reward"] = False
            pre_timeouts = v17_mod._timeout_shielded_agent.stats["timeouts"]

            turn = obs_dict.get("current", {}).get("turn") if isinstance(obs_dict, dict) else None
            select = obs_dict.get("select") if isinstance(obs_dict, dict) else None
            full_obs = None
            if select is not None:
                try:
                    full_obs = to_observation_class(obs_dict)
                except Exception:  # noqa: BLE001
                    full_obs = None

            result = v17_fn(obs_dict)

            if v17_mod._timeout_shielded_agent.stats["timeouts"] == pre_timeouts:
                s = dict(native_bridge.LAST_CALL_STATS)
                if s["eligible"] and s["search_begin_ok"] and full_obs is not None:
                    greedy_idx = s["greedy_index"]
                    mcts_idx = s["mcts_index"]
                    diverged = mcts_idx >= 0 and mcts_idx != greedy_idx
                    my_index = full_obs.current.yourIndex
                    select_options = full_obs.select.option
                    decisions_f.write(
                        json.dumps(
                            {
                                "game_index": _i,
                                "decision_index": decision_index[0],
                                "turn": turn,
                                "visits": s["visits"],
                                "hit_terminal_reward": s["hit_terminal_reward"],
                                "diverged": diverged,
                                "greedy": _option_desc(full_obs, my_index, select_options, greedy_idx),
                                "mcts": _option_desc(full_obs, my_index, select_options, mcts_idx),
                            }
                        )
                        + "\n"
                    )
            decision_index[0] += 1
            return result

        result = _play_one_game_keep_search_input(
            run_id="v17_divergence",
            game_index=i,
            agent_a_name=v17_name,
            agent_a_fn=timed_v17,
            deck_a=v17_deck,
            agent_b_name=v6_name,
            agent_b_fn=v6_fn,
            deck_b=v6_deck,
            a_slot0=v17_slot0,
            max_steps=MAX_STEPS,
        )
        games_f.write(
            json.dumps(
                {
                    "game_index": i,
                    "v17_slot0": v17_slot0,
                    "winner_agent": result.winner_agent,
                    "aborted": result.aborted,
                }
            )
            + "\n"
        )
        games_f.flush()
        decisions_f.flush()
        v17_mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0
        v6_mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0
        print(f"[{i + 1}/{n_games}] winner={result.winner_agent} aborted={result.aborted}", flush=True)

    decisions_f.close()
    games_f.close()


def build_report(n_games: int, out_dir: Path = OUT_DIR) -> None:
    games_path = out_dir / "raw_games.jsonl"
    decisions_path = out_dir / "raw_decisions.jsonl"
    report_path = out_dir / "report.md"

    games = {}
    with open(games_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                g = json.loads(line)
                games[g["game_index"]] = g

    v17_lost = {gi: (g["winner_agent"] != "v17_cpp_mcts") for gi, g in games.items()}

    total_decisions = 0
    diverged_decisions = 0
    diverged_with_terminal = 0
    non_diverged_with_terminal = 0
    pattern_total: Counter = Counter()
    pattern_in_losses: Counter = Counter()
    pattern_terminal: Counter = Counter()
    examples: dict = defaultdict(list)

    with open(decisions_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            total_decisions += 1
            lost = v17_lost.get(d["game_index"], None)
            if d["diverged"]:
                diverged_decisions += 1
                if d["hit_terminal_reward"]:
                    diverged_with_terminal += 1
                pattern = f"MCTS:[{d['mcts']['type_name']}] vs V6:[{d['greedy']['type_name']}]"
                pattern_total[pattern] += 1
                if d["hit_terminal_reward"]:
                    pattern_terminal[pattern] += 1
                if lost:
                    pattern_in_losses[pattern] += 1
                    if len(examples[pattern]) < 3:
                        examples[pattern].append(d)
            else:
                if d["hit_terminal_reward"]:
                    non_diverged_with_terminal += 1

    n_v17_losses = sum(1 for v in v17_lost.values() if v)

    lines = []
    lines.append("# V17 MCTS vs V6-Greedy Divergence Analysis")
    lines.append("")
    lines.append(f"Games: {len(games)} | V17 losses: {n_v17_losses} | V17 wins: {len(games) - n_v17_losses}")
    lines.append(f"Decisions where a real search ran: {total_decisions}")
    lines.append(f"Decisions where MCTS's final pick != V6's raw greedy pick (\"diverged\"): {diverged_decisions} ({diverged_decisions / total_decisions * 100:.1f}% of searched decisions)" if total_decisions else "No searched decisions captured.")
    lines.append("")
    lines.append("## Terminal-reward correlation (testing the mean-scaling hypothesis)")
    lines.append("")
    lines.append(
        f"- Diverged decisions where at least one backing rollout hit a terminal (+-1,000,000) reward: "
        f"{diverged_with_terminal}/{diverged_decisions} ({diverged_with_terminal / diverged_decisions * 100:.1f}%)" if diverged_decisions else "n/a"
    )
    lines.append(
        f"- Non-diverged decisions where at least one backing rollout hit a terminal reward: "
        f"{non_diverged_with_terminal}/{total_decisions - diverged_decisions} ({non_diverged_with_terminal / (total_decisions - diverged_decisions) * 100:.1f}%)"
        if (total_decisions - diverged_decisions) else "n/a"
    )
    lines.append(
        "\nIf divergence is disproportionately associated with a terminal-reward hit, that directly "
        "supports the hypothesis that a single rare simulated conclusion (not a stable multi-sample "
        "signal) is what's flipping MCTS's pick away from the greedy choice."
    )
    lines.append("")

    lines.append("## Top Divergence Patterns (MCTS override vs V6 greedy)")
    lines.append("")
    for pattern, total in pattern_total.most_common(15):
        in_losses = pattern_in_losses.get(pattern, 0)
        term = pattern_terminal.get(pattern, 0)
        win_rate_when_diverged = 100 - (in_losses / total * 100) if total else float("nan")
        lines.append(f"### {pattern}")
        lines.append(f"- Occurrences: {total} | In games V17 lost: {in_losses} | Win rate when this diverged: {win_rate_when_diverged:.1f}%")
        lines.append(f"- Of these, backed by a rollout that hit a terminal reward: {term}/{total} ({term / total * 100:.1f}%)")
        for ex in examples[pattern]:
            lines.append(
                f"  - game {ex['game_index']} decision {ex['decision_index']} (turn {ex['turn']}, visits={ex['visits']}, "
                f"hit_terminal={ex['hit_terminal_reward']}): MCTS played {ex['mcts'].get('cardName')} (attackId={ex['mcts']['attackId']}) "
                f"| V6 would have played {ex['greedy'].get('cardName')} (attackId={ex['greedy']['attackId']})"
            )
        lines.append("")

    # PLAY-vs-EVOLVE card tally: which specific cards does MCTS choose to
    # play instead of evolving, split by whether V17 ultimately won or lost
    # that game -- added to investigate a suspected "horizon effect" (MCTS
    # discarding/spending a card that would have enabled the EVOLVE greedy
    # wanted, for a short-term rollout-visible gain that doesn't reflect the
    # real cost of skipping the evolution).
    play_vs_evolve_cards_won: Counter = Counter()
    play_vs_evolve_cards_lost: Counter = Counter()
    with open(decisions_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if not d["diverged"] or d["mcts"]["type_name"] != "PLAY" or d["greedy"]["type_name"] != "EVOLVE":
                continue
            card = d["mcts"].get("cardName") or f"UNRESOLVED(id={d['mcts'].get('resolvedCardId')})"
            lost = v17_lost.get(d["game_index"], None)
            if lost:
                play_vs_evolve_cards_lost[card] += 1
            elif lost is False:
                play_vs_evolve_cards_won[card] += 1

    lines.append("## PLAY-vs-EVOLVE Card Tally (which card MCTS chose to play instead of evolving)")
    lines.append("")
    lines.append("### Cards played in games V17 LOST")
    lines.append("")
    if play_vs_evolve_cards_lost:
        for card, count in play_vs_evolve_cards_lost.most_common():
            lines.append(f"- {card}: {count}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("### Cards played in games V17 WON")
    lines.append("")
    if play_vs_evolve_cards_won:
        for card, count in play_vs_evolve_cards_won.most_common():
            lines.append(f"- {card}: {count}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Raw Data")
    lines.append("")
    lines.append(f"- Per-decision: `{decisions_path.relative_to(REPO_ROOT)}`")
    lines.append(f"- Per-game: `{games_path.relative_to(REPO_ROOT)}`")

    report = "\n".join(lines)
    report_path.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nReport written to {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument(
        "--report-only",
        metavar="DIR",
        default=None,
        help="Skip collection; rebuild the report from an existing raw_games.jsonl/raw_decisions.jsonl directory (e.g. an archived pre-fix run).",
    )
    args = parser.parse_args()
    if args.report_only:
        out_dir = Path(args.report_only).resolve()
        n_games = sum(1 for line in open(out_dir / "raw_games.jsonl", encoding="utf-8") if line.strip())
        build_report(n_games, out_dir=out_dir)
        return
    t0 = time.time()
    run_collection(args.games)
    print(f"Collection done in {time.time() - t0:.1f}s")
    build_report(args.games)


if __name__ == "__main__":
    main()
