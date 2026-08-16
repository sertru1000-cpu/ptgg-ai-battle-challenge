"""Cheap re-analysis of existing V6 lookahead-experiment data to resolve the
sequencing-artifact hypothesis raised in
ENGINE_V6_ONE_STEP_LOOKAHEAD_EXPERIMENT.md, Part 11 and "Recommended Next
Research Step" #1.

QUESTION THIS SCRIPT ANSWERS
-----------------------------
The governing report found that the dominant N=5 disagreement pattern (55 of
116 disagreements) is "V6's real choice at this decision was ATTACK, but the
lookahead's counterfactual preference was PLAY" -- plus a small 6-case
reverse pattern ("V6's real choice was PLAY, lookahead preferred ATTACK").
Part 11 raised, but explicitly did NOT test, the hypothesis that many of
these are not real tactical disagreements at all: V6 can take several MAIN
actions in one turn before attacking (play/attach/evolve/ability, THEN
attack), so a "V6 attacked, lookahead wanted to play a card" disagreement
at one specific decision could just mean V6 already played a card earlier
THAT SAME TURN (i.e. reached the "play first, then attack" sequence the
lookahead wanted, just one decision earlier or later than the specific row
being compared) -- an artifact of comparing single decisions in isolation,
not a genuine difference in what V6 ultimately did that turn.

This script resolves that hypothesis using ONLY data already collected in
results/v6_lookahead_experiment/*_decisions.csv (each row already records
game_id, turn, decision_num, and V6's REAL per-decision choice) -- no new
games, no engine calls, no changes to V6/V10/production agents, nothing
submitted anywhere.

METHOD
------
For each ATTACK<->PLAY disagreement at the primary N=5 configuration, walk
V6's real decision sequence (ordered by decision_num, which is monotonic
per game) within the SAME `turn` value as the disagreement row:

  - ATTACK_TO_PLAY (V6 really chose ATTACK, lookahead wanted PLAY): scan
    backward for an earlier real PLAY action in the same turn.
  - PLAY_TO_ATTACK (V6 really chose PLAY, lookahead wanted ATTACK -- the
    reverse pattern): scan forward for a later real ATTACK action in the
    same turn.

Because this engine's `turn` field is a single shared counter that only
advances when a turn changes hands (confirmed empirically: every row
immediately following a V6 ATTACK decision has a strictly higher `turn`
value than the ATTACK row, i.e. ATTACK always ends V6's turn in this
dataset), two V6 decisions sharing the same `turn` value are, by
construction, separated by zero opponent turns. So finding both the PLAY
and the ATTACK within one matching `turn` value simultaneously answers
both of the report's questions:
  (a) did V6's actual sequence do PLAY-then-ATTACK in the same turn, and
  (b) did the opponent get a turn in between (answer: no, whenever (a) is
      true, by the turn-counter invariant above).

CLASSIFICATION
--------------
  SAME_TURN_SEQUENCING_EQUIVALENT -- V6 played a card first, then attacked,
      in the same real turn (the "disagreement" is a sequencing artifact:
      V6 reached the lookahead's preferred sequence anyway).
  GENUINE_TACTICAL_DIVERGENCE -- no matching PLAY/ATTACK found in the same
      turn (V6 attacked without playing anything first that turn, or ended
      the turn without ever attacking): a real difference in what V6 did.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "results" / "v6_lookahead_experiment"
OUT_PATH = DATA_DIR / "sequencing_reanalysis.json"

PRIMARY_N = 5  # matches PRIMARY_N in tools/v6_lookahead_experiment_runner.py


def load_decisions() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(DATA_DIR.glob("*_decisions.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row["_source_file"] = path.name
                rows.append(row)
    if not rows:
        raise SystemExit(f"No *_decisions.csv files found under {DATA_DIR}")
    return rows


def index_by_game(rows: list[dict]) -> dict[str, list[dict]]:
    by_game: dict[str, list[dict]] = {}
    for row in rows:
        by_game.setdefault(row["game_id"], []).append(row)
    for seq in by_game.values():
        seq.sort(key=lambda r: int(r["decision_num"]))
    return by_game


def find_disagreements(rows: list[dict], direction: str) -> list[dict]:
    v6_type, la_type = direction.split("_TO_")
    out = []
    for row in rows:
        if row.get(f"n{PRIMARY_N}_disagreement") != "True":
            continue
        if row.get("v6_choice_option_type") == v6_type and row.get("lookahead_choice_option_type") == la_type:
            out.append(row)
    return out


def classify_attack_to_play(row: dict, by_game: dict[str, list[dict]]) -> dict:
    g, t, d = row["game_id"], row["turn"], int(row["decision_num"])
    seq = by_game[g]
    pos = next(i for i, r in enumerate(seq) if int(r["decision_num"]) == d)

    prior_actions_same_turn: list[str] = []
    found_play = False
    j = pos - 1
    while j >= 0 and seq[j]["turn"] == t:
        prior_actions_same_turn.append(seq[j]["v6_choice_option_type"])
        if seq[j]["v6_choice_option_type"] == "PLAY":
            found_play = True
            break
        j -= 1
    prior_actions_same_turn.reverse()

    classification = "SAME_TURN_SEQUENCING_EQUIVALENT" if found_play else "GENUINE_TACTICAL_DIVERGENCE"
    return {
        "source_file": row["_source_file"],
        "game_id": g,
        "turn": t,
        "decision_num": d,
        "direction": "ATTACK_TO_PLAY",
        "v6_real_choice": "ATTACK",
        "lookahead_choice": "PLAY",
        "prior_actions_same_turn": prior_actions_same_turn,
        "same_turn_play_then_attack": found_play,
        "opponent_turn_between": (False if found_play else None),
        "classification": classification,
    }


def classify_play_to_attack(row: dict, by_game: dict[str, list[dict]]) -> dict:
    g, t, d = row["game_id"], row["turn"], int(row["decision_num"])
    seq = by_game[g]
    pos = next(i for i, r in enumerate(seq) if int(r["decision_num"]) == d)

    later_actions_same_turn: list[str] = []
    found_attack = False
    j = pos + 1
    while j < len(seq) and seq[j]["turn"] == t:
        later_actions_same_turn.append(seq[j]["v6_choice_option_type"])
        if seq[j]["v6_choice_option_type"] == "ATTACK":
            found_attack = True
            break
        j += 1

    classification = "SAME_TURN_SEQUENCING_EQUIVALENT" if found_attack else "GENUINE_TACTICAL_DIVERGENCE"
    return {
        "source_file": row["_source_file"],
        "game_id": g,
        "turn": t,
        "decision_num": d,
        "direction": "PLAY_TO_ATTACK",
        "v6_real_choice": "PLAY",
        "lookahead_choice": "ATTACK",
        "later_actions_same_turn": later_actions_same_turn,
        "same_turn_play_then_attack": found_attack,
        "opponent_turn_between": (False if found_attack else None),
        "classification": classification,
    }


def summarize(cases: list[dict]) -> dict:
    equiv = sum(1 for c in cases if c["classification"] == "SAME_TURN_SEQUENCING_EQUIVALENT")
    genuine = len(cases) - equiv
    return {"total": len(cases), "SAME_TURN_SEQUENCING_EQUIVALENT": equiv, "GENUINE_TACTICAL_DIVERGENCE": genuine}


def print_table(title: str, cases: list[dict]) -> None:
    print(f"\n{title}")
    print(f"{'game_id':<28} {'turn':>5} {'d':>4}  {'classification':<32} detail")
    print("-" * 100)
    for c in cases:
        if c["direction"] == "ATTACK_TO_PLAY":
            detail = f"prior same-turn actions: {c['prior_actions_same_turn']}"
        else:
            detail = f"later same-turn actions: {c['later_actions_same_turn']}"
        print(f"{c['game_id']:<28} {c['turn']:>5} {c['decision_num']:>4}  {c['classification']:<32} {detail}")


def main() -> None:
    rows = load_decisions()
    by_game = index_by_game(rows)

    attack_to_play_rows = find_disagreements(rows, "ATTACK_TO_PLAY")
    play_to_attack_rows = find_disagreements(rows, "PLAY_TO_ATTACK")

    attack_to_play_cases = [classify_attack_to_play(r, by_game) for r in attack_to_play_rows]
    play_to_attack_cases = [classify_play_to_attack(r, by_game) for r in play_to_attack_rows]

    # Per-source-file breakdown, so the canonical "55" run (the report's
    # primary 24-game run) is distinguishable from any smaller/earlier runs
    # also present in this directory (e.g. dev smoke tests), rather than
    # silently blending sample sizes from different runs together.
    by_file: dict[str, dict] = {}
    for case in attack_to_play_cases + play_to_attack_cases:
        by_file.setdefault(case["source_file"], {"ATTACK_TO_PLAY": [], "PLAY_TO_ATTACK": []})
        by_file[case["source_file"]][case["direction"]].append(case)

    print("=" * 100)
    print("SEQUENCING RE-ANALYSIS -- ATTACK<->PLAY disagreement cluster (N=5, all *_decisions.csv found)")
    print("=" * 100)

    for fname, dirs in sorted(by_file.items()):
        print(f"\n### Source file: {fname}")
        print(f"  ATTACK_TO_PLAY: {summarize(dirs['ATTACK_TO_PLAY'])}")
        print(f"  PLAY_TO_ATTACK: {summarize(dirs['PLAY_TO_ATTACK'])}")

    print_table("ATTACK -> PLAY disagreements (V6 really attacked; lookahead wanted PLAY)", attack_to_play_cases)
    print_table("PLAY -> ATTACK disagreements (reverse pattern; V6 really played; lookahead wanted ATTACK)", play_to_attack_cases)

    combined_summary = summarize(attack_to_play_cases + play_to_attack_cases)
    print("\n" + "=" * 100)
    print("COMBINED TOTALS (all source files)")
    print("=" * 100)
    print(f"  ATTACK_TO_PLAY : {summarize(attack_to_play_cases)}")
    print(f"  PLAY_TO_ATTACK : {summarize(play_to_attack_cases)}")
    print(f"  ALL            : {combined_summary}")

    equiv_pct = 100.0 * combined_summary["SAME_TURN_SEQUENCING_EQUIVALENT"] / combined_summary["total"] if combined_summary["total"] else 0.0
    print(
        f"\nVerdict: {combined_summary['SAME_TURN_SEQUENCING_EQUIVALENT']}/{combined_summary['total']} "
        f"({equiv_pct:.1f}%) of ATTACK<->PLAY disagreements are SAME_TURN_SEQUENCING_EQUIVALENT -- "
        "V6's real trajectory reached the same play-then-attack sequence the lookahead wanted, just "
        "compared at a different single decision than where the lookahead's own alternative was scored. "
        f"{combined_summary['GENUINE_TACTICAL_DIVERGENCE']}/{combined_summary['total']} are "
        "GENUINE_TACTICAL_DIVERGENCE -- no matching PLAY/ATTACK pair found in the same real turn."
    )

    output = {
        "primary_n": PRIMARY_N,
        "source_files": sorted(by_file.keys()),
        "method": (
            "For each N=5 ATTACK<->PLAY disagreement, scan V6's real decision "
            "sequence (ordered by decision_num) within the same `turn` value for "
            "the complementary real action (a PLAY before an ATTACK row, or an "
            "ATTACK after a PLAY row). A same-turn match is definitionally zero "
            "opponent turns apart, since this engine's `turn` field only advances "
            "on a turn handoff (empirically confirmed: every row after a real V6 "
            "ATTACK decision has a strictly higher `turn` value)."
        ),
        "by_source_file": {
            fname: {
                "ATTACK_TO_PLAY": summarize(dirs["ATTACK_TO_PLAY"]),
                "PLAY_TO_ATTACK": summarize(dirs["PLAY_TO_ATTACK"]),
            }
            for fname, dirs in by_file.items()
        },
        "combined_summary": {
            "ATTACK_TO_PLAY": summarize(attack_to_play_cases),
            "PLAY_TO_ATTACK": summarize(play_to_attack_cases),
            "ALL": combined_summary,
        },
        "attack_to_play_cases": attack_to_play_cases,
        "play_to_attack_cases": play_to_attack_cases,
    }
    OUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
