"""Phase: Replay + Agent Log Forensic Analysis v1 -- main build script.

Produces the four required CSVs plus a rich per-analysis JSON (used to write
reports/kaggle_replay_forensic_v1.md accurately). Read-only: no agent/deck/
policy/submission changes. Consumes only already-pulled data in
data/kaggle_ladder/ (see tools/pull_kaggle_ladder_data.py from the prior
phase) and the `cg` engine's own static attack/card tables.
"""
from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict

import pandas as pd

import tools.kaggle_replay_forensic as f

ROOT = f.ROOT
OUT_DIR = os.path.join(ROOT, "results", "agent")
os.makedirs(OUT_DIR, exist_ok=True)

MEANINGFUL_CONTEXTS = {0, 35, 36}  # MAIN, ATTACK, DISABLE_ATTACK -- "real" tactical choices,
# used for "last 5 MEANINGFUL decisions" (Section 8.A), excluding pure bookkeeping
# selects (discard-a-card-from-a-forced-list, damage-counter placement, etc.)
# which are typically single-option or mechanically forced, not tactical choices.


def build_inventory(episodes):
    rows = []
    for e in episodes:
        eid = e["id"]
        idx = f.our_index(e)
        opp_agent = next(a for a in e["agents"] if a is not next(x for x in e["agents"] if x["submissionId"] == f.TARGET_SUBMISSION_ID))
        rp = f.replay_path(eid)
        lp = f.log_path(eid, idx)
        replay_avail = rp is not None
        log_avail = lp is not None
        if replay_avail and log_avail:
            coverage = "BOTH_AVAILABLE"
        elif replay_avail:
            coverage = "REPLAY_AVAILABLE"
        elif log_avail:
            coverage = "LOG_AVAILABLE"
        else:
            coverage = "NEITHER_AVAILABLE"
        reward = None
        result = "NA"
        if replay_avail:
            with open(rp, encoding="utf-8") as fh:
                d = json.load(fh)
            reward = d["rewards"][idx]
            opp_reward = d["rewards"][1 - idx]
            if reward == 1 and opp_reward == -1:
                result = "WIN"
            elif reward == -1 and opp_reward == 1:
                result = "LOSS"
            elif reward == 0 and opp_reward == 0:
                result = "DRAW"
            else:
                result = "ERROR_OR_TIMEOUT"
        rows.append({
            "episode_id": eid,
            "game_id": eid,
            "episode_type": e["type"],
            "timestamp": e["createTime"],
            "result": result,
            "reward": reward if reward is not None else "NA",
            "opponent": opp_agent["teamName"] if e["type"] != "EPISODE_TYPE_VALIDATION" else "SELF (validation)",
            "our_rating": "NA",
            "opponent_rating": "NA",
            "replay_available": replay_avail,
            "log_available": log_avail,
            "replay_path": rp or "NA",
            "log_path": lp or "NA",
            "coverage": coverage,
        })
    return pd.DataFrame(rows)


def visibility_tag(field_name: str) -> str:
    # Every field this pipeline stores comes from `observation.current` for OUR
    # OWN player index (see kaggle_replay_forensic.py module docstring point 3),
    # i.e. exactly what the live agent received -- VISIBLE_TO_AGENT by
    # construction. Opponent archetype/deck tags (built separately, from the
    # prior phase's game-level CSV, not from this trace) are the only
    # DERIVED_FROM_REPLAY / HIDDEN_FROM_AGENT data used anywhere in this phase.
    return "VISIBLE_TO_AGENT"


def build_decision_trace(all_parsed):
    rows = []
    for parsed in all_parsed:
        eid = parsed["episode_id"]
        result = parsed["result"]
        for dec in parsed["decisions"]:
            rows.append({
                "episode_id": eid,
                "turn": dec["turn"],
                "step": dec["row_index"],
                "decision_index": dec["decision_index"],
                "state_id": f"{eid}:{dec['row_index'] - 1}",
                "select_context": dec["select_context"],
                "select_context_name": dec["select_context_name"],
                "n_available_actions": dec["n_options"],
                "available_action_types": json.dumps(dec["option_type_counts"], ensure_ascii=False),
                "chosen_action": json.dumps(dec["chosen_action"], ensure_ascii=False),
                "chosen_action_types": ",".join(dec["chosen_option_types"]),
                "category": dec["category"],
                "next_state": f"{eid}:{dec['row_index']}",
                "game_result": result,
                "our_active_id_before": dec["state_before"].get("active_id"),
                "our_active_hp_before": dec["state_before"].get("active_hp"),
                "opp_active_id_before": dec["opp_before"].get("active_id"),
                "opp_active_hp_before": dec["opp_before"].get("active_hp"),
                "our_prize_before": dec["state_before"].get("prize_n"),
                "opp_prize_before": dec["opp_before"].get("prize_n"),
                "log_duration_s": dec["log_duration_s"],
                "log_stdout_nonempty": bool(dec["log_stdout"]),
                "log_stderr_nonempty": bool(dec["log_stderr"]),
                "agent_log_match": dec["agent_log_match"],
                "observation_match": dec["observation_match"],
                "visibility": visibility_tag("state"),
            })
    return pd.DataFrame(rows)


def build_errors(all_parsed):
    rows = []
    pattern_counter = Counter()
    for parsed in all_parsed:
        eid = parsed["episode_id"]
        result = parsed["result"]
        kos = f.find_missed_knockouts(parsed["decisions"])
        for k in kos:
            if k.get("target_removed_via_switch"):
                cat = "TARGET_SWITCHED_AWAY_NOT_AN_ERROR"
            else:
                cat = "ATTACK_SELECTION"
            pattern_key = f"missed_ko__{cat}__{k['evidence_level']}"
            pattern_counter[pattern_key] += 1
            rows.append({
                "episode_id": eid,
                "turn": k["turn"],
                "step": None,
                "result": result,
                "error_category": "ATTACK_SELECTION" if not k.get("target_removed_via_switch") else "TARGET_SELECTION",
                "action_taken": "(see description)",
                "alternative_available": "YES (a legal attack option existed)",
                "evidence_level": k["evidence_level"] if not k.get("target_removed_via_switch") else "AMBIGUOUS",
                "description": k["description"],
                "repeat_pattern_id": pattern_key,
            })
    # manual case study carried over from the prior (ladder-stats) phase, directly
    # hand-inspected there: game 38 / episode 92098917, abrupt unexplained loss
    rows.append({
        "episode_id": 92098917,
        "turn": 6,
        "step": None,
        "result": "LOSS",
        "error_category": "UNKNOWN",
        "action_taken": "(game ended)",
        "alternative_available": "INSUFFICIENT_INFORMATION",
        "evidence_level": "UNKNOWN",
        "description": (
            "Hand-inspected in the prior phase: game ended abruptly at turn ~6 with 0 "
            "prizes taken by either side, our active Pokemon at 10/320 HP (not KO'd), no "
            "status conditions active, episode status DONE. Cause not identifiable from "
            "observation-level fields without full action-effect tracing."
        ),
        "repeat_pattern_id": "abrupt_unexplained_ending",
    })
    return pd.DataFrame(rows), pattern_counter


VALIDATION_EPISODE_ID = 92032692  # platform self-play pre-matchmaking check, both
# agent slots = our own submission -- not a real ladder game, excluded from every
# win/loss-conditioned statistic in this phase (same exclusion the prior ladder-
# stats phase applied).


def build_patterns(all_parsed, error_pattern_counter):
    # Pattern 1: category sequence in the last-5-meaningful-decisions window, per game.
    last5_by_game = {}
    first5_by_game = {}
    for parsed in all_parsed:
        if parsed["result"] not in ("WIN", "LOSS") or parsed["episode_id"] == VALIDATION_EPISODE_ID:
            continue
        meaningful = [d for d in parsed["decisions"] if d["select_context"] in MEANINGFUL_CONTEXTS and d["n_options"] > 1]
        last5_by_game[parsed["episode_id"]] = meaningful[-5:]
        first5_by_game[parsed["episode_id"]] = meaningful[:5]

    def pattern_stats(window_by_game, label):
        cat_seq_counter = Counter()
        cat_game_result = defaultdict(lambda: {"WIN": 0, "LOSS": 0})
        first_seen = {}
        last_seen = {}
        for eid, decs in window_by_game.items():
            parsed = next(p for p in all_parsed if p["episode_id"] == eid)
            result = parsed["result"]
            cats = tuple(d["category"] for d in decs)
            if not cats:
                continue
            cat_seq_counter[cats] += 1
            for c in set(cats):
                cat_game_result[c][result] += 1
                first_seen.setdefault(c, eid)
                last_seen[c] = eid
        rows = []
        pid = 0
        for cat, res in cat_game_result.items():
            games = res["WIN"] + res["LOSS"]
            if games < 2:
                continue
            wr = res["WIN"] / games
            evidence = "OBSERVED_ONLY_SMALL_N" if games < 10 else "USABLE"
            rows.append({
                "pattern_id": f"{label}_category_{cat}_{pid}",
                "pattern_type": f"{label}_window_category_presence",
                "description": f"Category '{cat}' appears at least once in the {label} window",
                "games": games, "wins": res["WIN"], "losses": res["LOSS"],
                "win_rate": wr,
                "first_seen_episode": first_seen.get(cat),
                "last_seen_episode": last_seen.get(cat),
                "evidence_level": evidence,
            })
            pid += 1
        return rows

    rows = []
    rows += pattern_stats(last5_by_game, "last5")
    rows += pattern_stats(first5_by_game, "first5")

    for pattern_key, count in error_pattern_counter.items():
        rows.append({
            "pattern_id": pattern_key,
            "pattern_type": "tactical_error_repeat",
            "description": pattern_key.replace("__", " / "),
            "games": "NA", "wins": "NA", "losses": "NA", "win_rate": "NA",
            "first_seen_episode": "NA", "last_seen_episode": "NA",
            "evidence_level": "SEE_kaggle_replay_errors.csv" if count > 1 else "SINGLE_OCCURRENCE_NOT_A_PATTERN",
        })
    return pd.DataFrame(rows)


def main():
    episodes = f.load_episodes()
    inv_df = build_inventory(episodes)
    inv_df.to_csv(os.path.join(OUT_DIR, "kaggle_replay_inventory.csv"), index=False)
    print("Inventory:", len(inv_df), "episodes;", (inv_df["coverage"] == "BOTH_AVAILABLE").sum(), "BOTH_AVAILABLE")

    all_parsed = []
    for e in episodes:
        p = f.parse_episode(e["id"], e)
        if p is not None:
            all_parsed.append(p)
    print("Parsed:", len(all_parsed), "episodes")

    trace_df = build_decision_trace(all_parsed)
    trace_df.to_csv(os.path.join(OUT_DIR, "replay_decision_trace.csv"), index=False)
    n_dec = len(trace_df)
    n_matched = (trace_df["agent_log_match"] == "YES").sum()
    print(f"Decision trace: {n_dec} rows, {n_matched} matched ({100*n_matched/n_dec:.1f}%)")

    err_df, pattern_counter = build_errors(all_parsed)
    err_df.to_csv(os.path.join(OUT_DIR, "kaggle_replay_errors.csv"), index=False)
    print("Errors:", len(err_df), "rows;", (err_df["evidence_level"] == "CONFIRMED").sum(), "CONFIRMED")

    pat_df = build_patterns(all_parsed, pattern_counter)
    pat_df.to_csv(os.path.join(OUT_DIR, "kaggle_decision_patterns.csv"), index=False)
    print("Patterns:", len(pat_df), "rows")

    # Cache full per-episode decision lists (with knockout-check annotations) for
    # the report-writing pass -- not a required deliverable, kept for traceability.
    cache_dir = os.path.join(ROOT, "data", "kaggle_ladder", "parsed")
    os.makedirs(cache_dir, exist_ok=True)
    for parsed in all_parsed:
        out = dict(parsed)
        # decisions already JSON-safe (plain dicts/lists/primitives)
        with open(os.path.join(cache_dir, f"{parsed['episode_id']}.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=str)

    print("Done.")


if __name__ == "__main__":
    main()
