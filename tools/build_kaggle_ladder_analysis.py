"""Phase: Kaggle Ladder ~50 Games Deep Analysis -- read-only forensic build.

Parses the already-downloaded episode replays + our-agent logs for the
current production submission (data/kaggle_ladder/) into the required
game-level / rating-trajectory / loss / behavior-summary CSVs. Read-only:
does not touch main.py, deck.csv, decks/, src/agents/, or any submission.
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
from collections import Counter

import pandas as pd

from src.meta_analysis.archetype_signatures import tag_deck
from src.meta_analysis.deck_clustering import deck_signature
from src.meta_analysis.episode_parser import _extract_deck, deck_hash

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
KLADDER = os.path.join(ROOT, "data", "kaggle_ladder")
REPLAY_DIR = os.path.join(KLADDER, "replays")
LOG_DIR = os.path.join(KLADDER, "agent_logs")
OUT_DIR = os.path.join(ROOT, "results", "agent")
os.makedirs(OUT_DIR, exist_ok=True)

STARTING_RATING = 600.0  # documented competition default (mu0), verified via Kaggle API metadata (session 3)
CURRENT_PUBLIC_SCORE = None  # filled from submissions_raw.json below

TARGET_SUBMISSION_ID = 55437549  # resolved live from competition_submissions (see pull script output)


def load_episodes():
    with open(os.path.join(KLADDER, "episodes_raw.json"), encoding="utf-8") as f:
        return json.load(f)


def load_submission_score():
    with open(os.path.join(KLADDER, "submissions_raw.json"), encoding="utf-8") as f:
        subs = json.load(f)
    for s in subs:
        if s.get("ref") == TARGET_SUBMISSION_ID:
            return float(s["publicScore"]), s
    raise RuntimeError("target submission not found in submissions_raw.json")


def replay_path_for(eid):
    p = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    return p


def log_path_for(eid, our_idx):
    p = os.path.join(LOG_DIR, f"episode-{eid}-agent-{our_idx}-logs.json")
    return p if os.path.exists(p) else None


def _final_turn(steps, idx):
    turn = None
    for step in steps:
        cur = step[idx]["observation"].get("current")
        if cur and cur.get("turn") is not None:
            turn = cur["turn"]
    return turn


def _first_player(steps):
    fp = None
    for step in steps:
        for p in (0, 1):
            cur = step[p]["observation"].get("current")
            if cur and cur.get("firstPlayer") is not None and cur["firstPlayer"] != -1:
                fp = cur["firstPlayer"]
    return fp


def build_game_row(ep_meta):
    eid = ep_meta["id"]
    ep_type = ep_meta["type"]
    our_agent = next(a for a in ep_meta["agents"] if a["submissionId"] == TARGET_SUBMISSION_ID)
    our_idx = our_agent["index"]
    opp_agent = next(a for a in ep_meta["agents"] if a is not our_agent)
    opp_submission_id = opp_agent["submissionId"]

    with open(replay_path_for(eid), encoding="utf-8") as f:
        d = json.load(f)
    steps = d["steps"]
    team_names = d["info"].get("TeamNames", [None, None])
    is_self_play = ep_type == "EPISODE_TYPE_VALIDATION"

    our_reward = d["rewards"][our_idx]
    opp_reward = d["rewards"][1 - our_idx]
    if our_reward == 1 and opp_reward == -1:
        result = "WIN"
    elif our_reward == -1 and opp_reward == 1:
        result = "LOSS"
    elif our_reward == 0 and opp_reward == 0:
        result = "DRAW"
    else:
        result = "ERROR_OR_TIMEOUT"

    first_player = _first_player(steps)
    going_first = (first_player == our_idx) if first_player is not None else None

    turns_ours = _final_turn(steps, our_idx)
    turns_opp = _final_turn(steps, 1 - our_idx)
    n_steps = len(steps)

    opp_deck, opp_deck_src = _extract_deck(steps, 1 - our_idx)
    opp_archetype, opp_matched, opp_evidence = tag_deck(opp_deck) if opp_deck else ("NA", 0, [])
    opp_deck_hash = deck_hash(opp_deck) if opp_deck else "NA"
    opp_headline_sig = ", ".join(deck_signature(opp_deck)) if opp_deck else "NA"
    # refined matchup key: known-archetype label where matched, else the deterministic
    # headline-Pokemon signature (same method as the Phase 4.1 deck_clustering.py, applied
    # per-deck rather than needing a multi-game registry since this sample is small)
    opp_matchup_key = opp_archetype if opp_archetype != "UNLABELED" else f"UNLABELED[{opp_headline_sig}]"

    log_path = log_path_for(eid, our_idx)
    decision_count = None
    errors = 0
    stdout_nonempty = 0
    durations = []
    if log_path:
        with open(log_path, encoding="utf-8") as f:
            log = json.load(f)
        decision_count = len(log)
        for entry in log:
            if isinstance(entry, list) and entry:
                rec = entry[0]
            elif isinstance(entry, dict):
                rec = entry
            else:
                continue
            dur = rec.get("duration")
            if dur is not None:
                durations.append(dur)
            if rec.get("stderr"):
                errors += 1
            if rec.get("stdout"):
                stdout_nonempty += 1

    near_budget_calls = sum(1 for x in durations if x >= 1.8)  # proxy: near the 2.0s per-decision cap
    over_1s_calls = sum(1 for x in durations if x >= 1.0)

    return {
        "game_id": eid,
        "episode_type": ep_type,
        "is_self_play_validation": is_self_play,
        "timestamp": ep_meta["createTime"],
        "end_timestamp": ep_meta["endTime"],
        "result": result,
        "reward": our_reward,
        "our_rating_before": None,  # not exposed per-game by the Kaggle API (see report Limitations)
        "our_rating_after": None,
        "opponent_name": team_names[1 - our_idx] if not is_self_play else "SELF (validation)",
        "opponent_submission_id": opp_submission_id,
        "opponent_team_id": opp_agent["teamId"],
        "opponent_rating": None,  # not exposed by this API surface
        "opponent_deck_hash": opp_deck_hash,
        "opponent_deck_ncards": sum(opp_deck.values()) if opp_deck else 0,
        "opponent_deck_source": opp_deck_src,
        "opponent_archetype": opp_archetype,
        "opponent_archetype_matched_cards": opp_matched,
        "opponent_headline_signature": opp_headline_sig,
        "opponent_matchup_key": opp_matchup_key,
        "going_first": going_first,
        "first_player_index": first_player,
        "our_index": our_idx,
        "turns_ours": turns_ours,
        "turns_opp": turns_opp,
        "turns": max(t for t in (turns_ours, turns_opp) if t is not None) + 1 if (turns_ours is not None or turns_opp is not None) else None,
        "steps": n_steps,
        "decision_count": decision_count,
        "invalid_actions": "NA",  # in-memory-only counter in safety_wrapper, never logged (see report)
        "timeouts": "NA",  # in-memory-only counter in timeout_shield, never logged (see report)
        "near_decision_budget_calls_ge_1.8s": near_budget_calls,
        "calls_ge_1.0s": over_1s_calls,
        "errors_stderr_nonempty": errors,
        "stdout_nonempty_calls": stdout_nonempty,
        "fallback_count": "NA",
        "safety_interventions": "NA",
        "decision_duration_mean_s": statistics.mean(durations) if durations else None,
        "decision_duration_median_s": statistics.median(durations) if durations else None,
        "decision_duration_max_s": max(durations) if durations else None,
        "decision_duration_p95_s": (sorted(durations)[int(0.95 * (len(durations) - 1))] if durations else None),
        "decision_duration_p99_s": (sorted(durations)[int(0.99 * (len(durations) - 1))] if durations else None),
    }


def main():
    global CURRENT_PUBLIC_SCORE
    CURRENT_PUBLIC_SCORE, sub_meta = load_submission_score()
    episodes = load_episodes()

    rows = [build_game_row(e) for e in episodes]
    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)

    ladder_df = df[~df["is_self_play_validation"]].reset_index(drop=True)
    ladder_df.insert(0, "game_number", range(1, len(ladder_df) + 1))

    ladder_df.to_csv(os.path.join(OUT_DIR, "kaggle_ladder_games.csv"), index=False)

    # Rating trajectory: only start (600, documented default) and end (current public score,
    # live-API fact) are real data points; every intermediate per-game rating is genuinely
    # unavailable from this API surface -- NA, not interpolated/estimated.
    traj_rows = []
    for i, row in ladder_df.iterrows():
        traj_rows.append({
            "game_number": row["game_number"],
            "game_id": row["game_id"],
            "timestamp": row["timestamp"],
            "result": row["result"],
            "rating_before": STARTING_RATING if row["game_number"] == 1 else None,
            "rating_after": CURRENT_PUBLIC_SCORE if row["game_number"] == len(ladder_df) else None,
            "rating_delta": None,
            "opponent_rating": None,
        })
    traj_df = pd.DataFrame(traj_rows)
    traj_df.to_csv(os.path.join(OUT_DIR, "kaggle_rating_trajectory.csv"), index=False)

    # Losses. Default category is LOG_INSUFFICIENT (full turn-by-turn causal tracing was
    # not performed for every loss, only illustrative case studies -- see report). Games
    # directly hand-inspected this phase get their evidence-based category below instead
    # of the default, per the phase prompt's "don't force a classification" instruction.
    manual_loss_findings = {
        92098917: (
            "RANDOMNESS_UNCLEAR",
            "Hand-inspected (game_number 38, vs Dragapult ex mirror): ended abruptly at "
            "turn ~6/7 with 0 prizes taken by either side, our active Pokemon at 10/320 HP "
            "(not yet KO'd), no status conditions (poison/burn/etc.) active at the final "
            "observed step, episode status DONE (not ERROR/TIMEOUT). Cause not identifiable "
            "from available observation fields without full action-effect replay tracing, "
            "which was out of scope this phase.",
        ),
    }

    losses = ladder_df[ladder_df["result"] == "LOSS"].copy()
    loss_rows = []
    for _, row in losses.iterrows():
        loss_rows.append({
            "game_number": row["game_number"],
            "game_id": row["game_id"],
            "timestamp": row["timestamp"],
            "opponent_name": row["opponent_name"],
            "opponent_archetype": row["opponent_matchup_key"],
            "going_first": row["going_first"],
            "turns": row["turns"],
            "steps": row["steps"],
            "decision_count": row["decision_count"],
            "errors_stderr_nonempty": row["errors_stderr_nonempty"],
            "near_decision_budget_calls_ge_1.8s": row["near_decision_budget_calls_ge_1.8s"],
            "decision_duration_max_s": row["decision_duration_max_s"],
            "safety_or_fallback_involved": "UNKNOWN (not logged, see Limitations)",
            "category": manual_loss_findings.get(row["game_id"], ("LOG_INSUFFICIENT", ""))[0],
            "notes": manual_loss_findings.get(row["game_id"], ("", ""))[1],
        })
    loss_df = pd.DataFrame(loss_rows)
    loss_df.to_csv(os.path.join(OUT_DIR, "kaggle_losses.csv"), index=False)

    # Behavior summary (one row per metric)
    n = len(ladder_df)
    all_durations = []
    for _, row in ladder_df.iterrows():
        pass
    behavior_rows = [
        {"metric": "games_analyzed", "value": n},
        {"metric": "self_play_validation_episodes_excluded", "value": int(df["is_self_play_validation"].sum())},
        {"metric": "wins", "value": int((ladder_df["result"] == "WIN").sum())},
        {"metric": "losses", "value": int((ladder_df["result"] == "LOSS").sum())},
        {"metric": "draws", "value": int((ladder_df["result"] == "DRAW").sum())},
        {"metric": "error_or_timeout_results", "value": int((ladder_df["result"] == "ERROR_OR_TIMEOUT").sum())},
        {"metric": "going_first_games", "value": int((ladder_df["going_first"] == True).sum())},
        {"metric": "going_second_games", "value": int((ladder_df["going_first"] == False).sum())},
        {"metric": "going_first_unknown", "value": int(ladder_df["going_first"].isna().sum())},
        {"metric": "total_decision_calls_logged", "value": int(ladder_df["decision_count"].sum())},
        {"metric": "calls_with_nonempty_stderr", "value": int(ladder_df["errors_stderr_nonempty"].sum())},
        {"metric": "calls_with_nonempty_stdout", "value": int(ladder_df["stdout_nonempty_calls"].sum())},
        {"metric": "calls_ge_1.0s_duration", "value": int(ladder_df["calls_ge_1.0s"].sum())},
        {"metric": "calls_ge_1.8s_duration_near_2s_cap", "value": int(ladder_df["near_decision_budget_calls_ge_1.8s"].sum())},
        {"metric": "decision_duration_mean_s_pooled", "value": ladder_df["decision_duration_mean_s"].mean()},
        {"metric": "decision_duration_max_s_overall", "value": ladder_df["decision_duration_max_s"].max()},
        {"metric": "invalid_actions_directly_observable", "value": "NO (in-memory counter, never logged)"},
        {"metric": "timeouts_directly_observable", "value": "NO (in-memory counter, never logged)"},
        {"metric": "fallback_count_directly_observable", "value": "NO (in-memory counter, never logged)"},
        {"metric": "safety_interventions_directly_observable", "value": "NO (in-memory counter, never logged)"},
        {"metric": "current_public_score", "value": CURRENT_PUBLIC_SCORE},
        {"metric": "starting_rating_documented", "value": STARTING_RATING},
    ]
    behavior_df = pd.DataFrame(behavior_rows)
    behavior_df.to_csv(os.path.join(OUT_DIR, "kaggle_behavior_summary.csv"), index=False)

    print("games:", n)
    print("wins/losses/draws:", (ladder_df["result"] == "WIN").sum(), (ladder_df["result"] == "LOSS").sum(), (ladder_df["result"] == "DRAW").sum())
    print("current public score:", CURRENT_PUBLIC_SCORE)
    print("Saved CSVs to", OUT_DIR)


if __name__ == "__main__":
    main()
