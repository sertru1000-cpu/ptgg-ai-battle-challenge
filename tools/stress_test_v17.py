"""1000-game brutal stress test: V17 (native C++ MCTS, real submission
composition) vs V6 (pure-Python heuristic, real submission composition).

Plays through `src.agents.final_candidate_agent_v17` / `final_candidate_agent_v6`
-- the SAME safety_wrapper -> timeout_shield -> policy composition Kaggle
would actually invoke (see those two modules) -- not the bare policy
functions, so the "Kaggle turn-time limits" enforcement (timeout_shield:
PER_DECISION_BUDGET_SECONDS=2.0s, MATCH_BUDGET_SECONDS=600s per match; see
src/agents/timeout_shield.py's own docstring for where those numbers come
from) is genuinely exercised, and a decision that blows its budget is
recorded as a real timeout (via that module's own `stats` counters) rather
than just hoped to be fast.

Orchestrator/worker split for genuine crash isolation (this is a real
concern, not a hypothetical: a native access violation inside v17_mcts.dll
crashes the WHOLE Python process instantly -- no Python try/except can catch
it, only OS-level process isolation can). This script's top-level process
never imports cg or the native library itself; it only spawns a worker
subprocess (`--worker START END --games N`) that plays games [START, END).
Any abnormal worker exit is treated as a crash: the orchestrator reads
worker_heartbeat.json (rewritten before every single real decision inside
the worker, so it always points at the game/turn/decision in flight) to
recover the exact point of failure, records a synthetic aborted GameResult
for that one game, and respawns a fresh worker to continue from the next
game index. Raw per-game results and raw per-decision V17 timings are
appended to disk immediately after each game completes, so a crash never
loses more than the one in-flight game -- never discard raw data, per this
project's standing rule (feedback_ptcg_process.md point 1).

Cross-game state isolation: final_candidate_agent_v17/v6's timeout_shield
wrapper is built ONCE per worker process and reused across every game that
worker plays (matches this repo's existing tools/run_local_tournament.py
pattern of reusing one agent instance across many local games -- rebuilding
the native-backed agent per game would be needlessly expensive). But
timeout_shield's own MATCH_BUDGET_SECONDS/`degraded` latch has no per-game
reset built in (it is designed around "one process = one real Kaggle match"),
so left alone it would silently accumulate elapsed time and could eventually
latch V17 into permanent-fallback-only for the rest of a worker's games,
without that ever showing up as a crash. This script resets the exposed
`_timeout_shielded_agent.stats["cumulative_elapsed_seconds"]` counter to 0
after every game (the one piece of that internal state the module exposes)
so each game gets a fresh 600s budget, matching real per-match semantics,
without needing to rebuild the (expensive) native-backed agent itself.

Usage:
    python tools/stress_test_v17.py                    # full 1000-game run (resumable)
    python tools/stress_test_v17.py --games 20          # smaller pilot run
    python tools/stress_test_v17.py --worker 0 20 --games 20   # internal, do not call directly
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "results" / "v17_vs_v6_stress"
RAW_GAMES_PATH = OUT_DIR / "raw_games.jsonl"
TIMINGS_PATH = OUT_DIR / "v17_decision_times.csv"
HEARTBEAT_PATH = OUT_DIR / "worker_heartbeat.json"
CRASHES_PATH = OUT_DIR / "crashes.jsonl"
REPORT_PATH = OUT_DIR / "report.md"

MAX_STEPS = 2000
MAX_CRASH_RETRIES = 30

WIN_REASON_LABELS = {1: "All Prizes Taken", 2: "Deck Out", 3: "No Active Pokemon", 4: "Card Effect"}


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------


def _play_one_game_keep_search_input(
    run_id, game_index, agent_a_name, agent_a_fn, deck_a, agent_b_name, agent_b_fn, deck_b, a_slot0, max_steps
):
    """Same as tools.tournament.play_one_game, EXCEPT it does NOT
    `obs.pop("search_begin_input", None)` before calling the agent.

    This is the actual root cause behind V17 never engaging its native MCTS
    in any earlier local test that used tools.tournament.play_one_game
    (including this project's first 1000-game stress-test run): that field
    is required for the C++ side's `search_begin()` call to succeed at all
    (see docs/search_api.md -- "search_begin raises ValueError('Not agent
    observation.') if this is None"); v17_agent.cpp's `eligible_for_search`
    gate also requires `search_begin_input_len > 0`, so stripping it made
    every single decision silently fall through to the plain V6-greedy
    fallback, indistinguishable from a real "no crash, sensible moves"
    result. tools/search_ablation_experiment.py already established this
    exact pattern (a separate non-stripping play-one-game function) for the
    same reason with a different search implementation -- kept local here
    rather than importing that module since it also pulls in unrelated
    Phase 12/13 agent dependencies this script has no other use for.

    The strip in tools.tournament.play_one_game is NOT present in the real
    Kaggle path: `search_begin_input` is populated by cg.game's own
    `_get_battle_data()` (the same official engine wrapper Kaggle's grading
    container uses), and main_v17.py's `agent(obs_dict)` has the identical
    signature/contract the real harness calls -- this stripping is a
    tools.tournament.py-local-harness-only artifact.
    """
    import cg.game as g
    from cg.api import LogType, to_observation_class
    from tools.tournament import GameResult

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


def _write_heartbeat(game_index: int, decision_index: int, turn, acting: str) -> None:
    try:
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {"game_index": game_index, "decision_index": decision_index, "turn": turn, "acting": acting, "ts": time.time()},
                f,
            )
    except OSError:
        pass  # heartbeat is best-effort diagnostics, never allowed to break the actual game


def run_worker(start: int, end: int, n_games: int) -> None:
    from tools.tournament import load_agent

    import src.agents.final_candidate_agent_v17 as v17_mod
    import src.agents.final_candidate_agent_v6 as v6_mod
    from src.agents.dragapult_agent_v17_cpp import native_bridge

    v17_name, v17_fn, v17_deck = load_agent("src.agents.final_candidate_agent_v17", name_override="v17_cpp_mcts")
    v6_name, v6_fn, v6_deck = load_agent("src.agents.final_candidate_agent_v6", name_override="v6_heuristic")

    half = n_games // 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    games_f = open(RAW_GAMES_PATH, "a", encoding="utf-8")
    timings_f = open(TIMINGS_PATH, "a", encoding="utf-8")
    if TIMINGS_PATH.stat().st_size == 0:
        timings_f.write("game_index,decision_index,elapsed_ms,eligible,search_begin_ok,visits\n")

    for i in range(start, end):
        v17_slot0 = i < half  # first half of the WHOLE run: V17 occupies engine slot 0 (goes first)
        _write_heartbeat(i, 0, None, "pre-start")

        decision_index = [0]
        v17_call_ms: list[float] = []
        v17_search_stats: list[tuple[bool, bool, int]] = []  # (eligible, search_begin_ok, visits)

        def timed_v17(obs_dict, _i=i):
            turn = obs_dict.get("current", {}).get("turn") if isinstance(obs_dict, dict) else None
            _write_heartbeat(_i, decision_index[0], turn, "v17")

            # native_bridge.LAST_CALL_STATS is a plain shared module global,
            # only written by native_choose_action() -- but
            # dragapult_agent_v17_cpp/agent.py short-circuits BEFORE ever
            # calling native_choose_action on two call types: the deck-declare
            # call (select is None) and the once-per-game IS_FIRST coin-toss
            # decision. On those calls LAST_CALL_STATS is never touched, so a
            # naive read-after-return would silently report STALE data left
            # over from the most recent call that DID reach
            # native_choose_action (possibly from the previous game). Reset
            # it to the "nothing ran" defaults ourselves before every call so
            # a short-circuited call correctly reads back as "no search ran"
            # rather than carrying over someone else's numbers.
            native_bridge.LAST_CALL_STATS["eligible"] = False
            native_bridge.LAST_CALL_STATS["search_begin_ok"] = False
            native_bridge.LAST_CALL_STATS["visits"] = 0

            # Separate, defense-in-depth concern: LAST_CALL_STATS is also
            # written from timeout_shield's background worker thread. If THIS
            # call's future times out (timeout_shield abandons it and returns
            # a safe default immediately without waiting), the abandoned
            # inner call can still finish later on that worker thread and
            # write LAST_CALL_STATS asynchronously, racing with a LATER
            # decision's read. Detect that via the timeouts counter and record
            # "unknown" for this decision rather than trusting a read that
            # might reflect a different call entirely.
            pre_timeouts = v17_mod._timeout_shielded_agent.stats["timeouts"]
            t0 = time.perf_counter()
            result = v17_fn(obs_dict)
            elapsed = (time.perf_counter() - t0) * 1000.0
            v17_call_ms.append(elapsed)
            if v17_mod._timeout_shielded_agent.stats["timeouts"] > pre_timeouts:
                v17_search_stats.append((False, False, -1))  # -1 sentinel: unknown (timed out), not "not eligible"
            else:
                s = native_bridge.LAST_CALL_STATS
                v17_search_stats.append((bool(s["eligible"]), bool(s["search_begin_ok"]), int(s["visits"])))
            decision_index[0] += 1
            return result

        def heartbeat_v6(obs_dict, _i=i):
            turn = obs_dict.get("current", {}).get("turn") if isinstance(obs_dict, dict) else None
            _write_heartbeat(_i, decision_index[0], turn, "v6")
            result = v6_fn(obs_dict)
            decision_index[0] += 1
            return result

        prev_v17_ts = dict(v17_mod._timeout_shielded_agent.stats)
        prev_v17_sw = dict(v17_mod.agent.stats)

        try:
            result = _play_one_game_keep_search_input(
                run_id="v17_vs_v6_stress",
                game_index=i,
                agent_a_name=v17_name,
                agent_a_fn=timed_v17,
                deck_a=v17_deck,
                agent_b_name=v6_name,
                agent_b_fn=heartbeat_v6,
                deck_b=v6_deck,
                a_slot0=v17_slot0,
                max_steps=MAX_STEPS,
            )

            cur_v17_ts = v17_mod._timeout_shielded_agent.stats
            cur_v17_sw = v17_mod.agent.stats

            unknown_stats = [s for s in v17_search_stats if s[2] == -1]  # decision's own future timed out; stats unreadable, not "ineligible"
            eligible_stats = [s for s in v17_search_stats if s[0]]
            searched_stats = [s for s in eligible_stats if s[1]]  # eligible AND search_begin succeeded
            visits_list = [s[2] for s in searched_stats]

            row = {
                "game_index": i,
                "v17_slot0": v17_slot0,
                "winner_agent": result.winner_agent,
                "win_reason": result.win_reason,
                "first_player_slot": result.first_player_slot,
                "turns": result.turns,
                "steps": result.steps,
                "aborted": result.aborted,
                "error": result.error,
                "crashed": False,
                "v17_decisions": len(v17_call_ms),
                "v17_ms_mean": (sum(v17_call_ms) / len(v17_call_ms)) if v17_call_ms else None,
                "v17_ms_min": min(v17_call_ms) if v17_call_ms else None,
                "v17_ms_max": max(v17_call_ms) if v17_call_ms else None,
                "v17_timeouts": cur_v17_ts["timeouts"] - prev_v17_ts["timeouts"],
                "v17_inner_exceptions": cur_v17_ts["inner_exceptions"] - prev_v17_ts["inner_exceptions"],
                "v17_degraded_activations": cur_v17_ts["degraded_mode_activations"] - prev_v17_ts["degraded_mode_activations"],
                "v17_safety_fallback_used": cur_v17_sw["fallback_used"] - prev_v17_sw["fallback_used"],
                "v17_safety_exceptions": cur_v17_sw["exceptions"] - prev_v17_sw["exceptions"],
                "v17_eligible_decisions": len(eligible_stats),
                "v17_search_begin_ok_decisions": len(searched_stats),
                "v17_visits_mean": (sum(visits_list) / len(visits_list)) if visits_list else None,
                "v17_visits_min": min(visits_list) if visits_list else None,
                "v17_visits_max": max(visits_list) if visits_list else None,
                "v17_unknown_stats_decisions": len(unknown_stats),
            }

            # Per-match budget reset (see module docstring) -- must happen
            # regardless of outcome, so do it right after reading stats above.
            v17_mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0
            v6_mod._timeout_shielded_agent.stats["cumulative_elapsed_seconds"] = 0.0

            games_f.write(json.dumps(row) + "\n")
            games_f.flush()
            os.fsync(games_f.fileno())

            for di, (ms, (elig, begin_ok, visits)) in enumerate(zip(v17_call_ms, v17_search_stats)):
                timings_f.write(f"{i},{di},{ms:.4f},{int(elig)},{int(begin_ok)},{visits}\n")
            timings_f.flush()

            status = "ABORTED: " + str(result.error) if result.aborted else f"winner={result.winner_agent}"
            print(
                f"[{i + 1}/{n_games}] v17_slot0={v17_slot0} steps={result.steps} turns={result.turns} "
                f"v17_decisions={len(v17_call_ms)} searched={len(searched_stats)} {status}",
                flush=True,
            )

        except Exception as exc:  # noqa: BLE001 -- a bug in THIS script's own bookkeeping must not be
            # misreported as a native crash (those never raise a Python
            # exception at all -- they kill the process outright). Log and
            # keep going so one harness bug doesn't lose the rest of the run.
            row = {
                "game_index": i,
                "v17_slot0": v17_slot0,
                "winner_agent": None,
                "win_reason": None,
                "first_player_slot": None,
                "turns": 0,
                "steps": 0,
                "aborted": True,
                "error": f"harness exception: {type(exc).__name__}: {exc}",
                "crashed": False,
                "v17_decisions": len(v17_call_ms),
                "v17_ms_mean": None,
                "v17_ms_min": None,
                "v17_ms_max": None,
                "v17_timeouts": None,
                "v17_inner_exceptions": None,
                "v17_degraded_activations": None,
                "v17_safety_fallback_used": None,
                "v17_safety_exceptions": None,
                "v17_eligible_decisions": None,
                "v17_search_begin_ok_decisions": None,
                "v17_visits_mean": None,
                "v17_visits_min": None,
                "v17_visits_max": None,
                "v17_unknown_stats_decisions": None,
            }
            games_f.write(json.dumps(row) + "\n")
            games_f.flush()
            print(f"[{i + 1}/{n_games}] HARNESS EXCEPTION: {exc!r}", flush=True)

    games_f.close()
    timings_f.close()
    _write_heartbeat(end, 0, None, "worker-finished-cleanly")


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------


def _count_completed() -> int:
    if not RAW_GAMES_PATH.exists():
        return 0
    n = 0
    with open(RAW_GAMES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _read_heartbeat() -> dict:
    try:
        with open(HEARTBEAT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def run_orchestrator(n_games: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"V17 vs V6 stress test: target {n_games} games. Output: {OUT_DIR}")

    crash_count = 0
    while True:
        completed = _count_completed()
        if completed >= n_games:
            print(f"All {n_games} games accounted for in {RAW_GAMES_PATH}.")
            break

        start = completed
        print(f"Spawning worker for games [{start}, {n_games}) (resume point: {start} already done)...")

        # Seed a placeholder heartbeat pointing at the intended start index,
        # so a crash before the worker's own first real heartbeat write
        # (e.g. during import) still attributes correctly.
        try:
            with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
                json.dump({"game_index": start, "decision_index": 0, "turn": None, "acting": "pre-spawn", "ts": time.time()}, f)
        except OSError:
            pass

        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(start), str(n_games), "--games", str(n_games)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        tail: deque[str] = deque(maxlen=60)
        for line in proc.stdout:  # type: ignore[union-attr]
            print(line, end="")
            tail.append(line)
        retcode = proc.wait()

        completed_after = _count_completed()
        if retcode == 0 and completed_after >= n_games:
            print("Worker finished its full range cleanly.")
            break

        # Nonzero exit (or, defensively, a clean-looking exit that still left
        # games missing) -- treat as a crash: a genuine native access
        # violation never raises a Python exception, so it can only ever
        # show up here as an abnormal process exit, not as a caught error.
        crash_count += 1
        heartbeat = _read_heartbeat()
        crashed_game_index = heartbeat.get("game_index", completed_after)
        print(f"*** WORKER CRASHED (exit code {retcode}). Heartbeat at time of death: {heartbeat} ***")

        crash_record = {
            "crash_number": crash_count,
            "worker_start": start,
            "worker_exit_code": retcode,
            "heartbeat_at_death": heartbeat,
            "stdout_tail": "".join(tail),
            "ts": time.time(),
        }
        CRASHES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CRASHES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(crash_record) + "\n")

        # Ensure the in-flight game gets a dense, accounted-for row so
        # raw_games.jsonl stays a complete 0..N-1 sequence (no silent gaps).
        if completed_after <= crashed_game_index:
            synthetic_row = {
                "game_index": crashed_game_index,
                "v17_slot0": crashed_game_index < (n_games // 2),
                "winner_agent": None,
                "win_reason": None,
                "first_player_slot": None,
                "turns": 0,
                "steps": 0,
                "aborted": True,
                "error": f"WORKER PROCESS CRASH (exit code {retcode}) during decision_index={heartbeat.get('decision_index')} turn={heartbeat.get('turn')} acting={heartbeat.get('acting')}",
                "crashed": True,
                "v17_decisions": None,
                "v17_ms_mean": None,
                "v17_ms_min": None,
                "v17_ms_max": None,
                "v17_timeouts": None,
                "v17_inner_exceptions": None,
                "v17_degraded_activations": None,
                "v17_safety_fallback_used": None,
                "v17_safety_exceptions": None,
                "v17_eligible_decisions": None,
                "v17_search_begin_ok_decisions": None,
                "v17_visits_mean": None,
                "v17_visits_min": None,
                "v17_visits_max": None,
                "v17_unknown_stats_decisions": None,
            }
            with open(RAW_GAMES_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(synthetic_row) + "\n")

        if crash_count > MAX_CRASH_RETRIES:
            print(f"*** {crash_count} crashes exceeds MAX_CRASH_RETRIES={MAX_CRASH_RETRIES}. Stopping early. ***")
            break

    build_and_write_report(n_games, crash_count)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def build_and_write_report(n_games: int, crash_count: int) -> None:
    rows = []
    with open(RAW_GAMES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["game_index"])

    aborted = [r for r in rows if r["aborted"]]
    crashed = [r for r in rows if r.get("crashed")]
    decided = [r for r in rows if not r["aborted"] and r["winner_agent"] not in (None, "draw")]
    draws = [r for r in rows if not r["aborted"] and r["winner_agent"] == "draw"]

    v17_wins = [r for r in decided if r["winner_agent"] == "v17_cpp_mcts"]
    v6_wins = [r for r in decided if r["winner_agent"] == "v6_heuristic"]
    n_decided = len(decided)
    v17_rate = len(v17_wins) / n_decided if n_decided else float("nan")
    v6_rate = len(v6_wins) / n_decided if n_decided else float("nan")

    # Positional split -- cross-checked against the REAL engine-reported
    # first_player_slot, not just the intended v17_slot0 assignment (per
    # feedback_ptcg_process.md point 2: verify the actual split, don't
    # assume alternation/assignment achieved it).
    v17_as_p1_intended = [r for r in decided if r["v17_slot0"]]
    v17_as_p2_intended = [r for r in decided if not r["v17_slot0"]]
    v17_wins_as_p1 = sum(1 for r in v17_as_p1_intended if r["winner_agent"] == "v17_cpp_mcts")
    v17_wins_as_p2 = sum(1 for r in v17_as_p2_intended if r["winner_agent"] == "v17_cpp_mcts")
    v17_p1_rate = v17_wins_as_p1 / len(v17_as_p1_intended) if v17_as_p1_intended else float("nan")
    v17_p2_rate = v17_wins_as_p2 / len(v17_as_p2_intended) if v17_as_p2_intended else float("nan")

    # Verify (not assume) that engine slot 0 -- the only slot ever asked
    # "go first?" -- actually went first in every game, since both agents
    # answer that question identically (always_first=True on both sides).
    # If this ever comes back < 100%, the "intended split == actual split"
    # assumption below is wrong and the whole positional table is suspect.
    checkable = [r for r in rows if r.get("first_player_slot") is not None]
    slot0_went_first = sum(1 for r in checkable if r["first_player_slot"] == 0)
    slot0_mismatch = len(checkable) - slot0_went_first

    intended_v17_first = sum(1 for r in rows if r["v17_slot0"])
    intended_v6_first = sum(1 for r in rows if not r["v17_slot0"])
    actual_v17_first = sum(1 for r in checkable if r["v17_slot0"] == (r["first_player_slot"] == 0))

    # Execution metrics -- pooled across every V17 decision in every
    # non-crashed game (raw per-decision data also lives in
    # v17_decision_times.csv untouched, per the never-discard-raw-data rule).
    all_v17_ms: list[float] = []
    all_v17_ms_searched: list[float] = []  # subset: eligible AND search_begin succeeded
    all_visits: list[int] = []
    n_eligible_total = 0
    n_searched_total = 0
    n_decisions_total = 0
    n_unknown_stats_total = 0  # decision's own future timed out (see timed_v17's docstring) -- stats unreadable, not "ineligible"
    if TIMINGS_PATH.exists():
        with open(TIMINGS_PATH, "r", encoding="utf-8") as f:
            next(f, None)  # header
            for line in f:
                parts = line.strip().split(",")
                if len(parts) != 6:
                    continue
                try:
                    ms = float(parts[2])
                    eligible = bool(int(parts[3]))
                    begin_ok = bool(int(parts[4]))
                    visits = int(parts[5])
                except ValueError:
                    continue
                n_decisions_total += 1
                all_v17_ms.append(ms)
                if visits == -1:
                    n_unknown_stats_total += 1
                    continue
                if eligible:
                    n_eligible_total += 1
                if eligible and begin_ok:
                    n_searched_total += 1
                    all_v17_ms_searched.append(ms)
                    all_visits.append(visits)

    total_v17_timeouts = sum(r["v17_timeouts"] for r in rows if r.get("v17_timeouts") is not None)
    total_v17_inner_exc = sum(r["v17_inner_exceptions"] for r in rows if r.get("v17_inner_exceptions") is not None)
    total_v17_degraded = sum(r["v17_degraded_activations"] for r in rows if r.get("v17_degraded_activations") is not None)
    total_v17_safety_fallback = sum(r["v17_safety_fallback_used"] for r in rows if r.get("v17_safety_fallback_used") is not None)

    def avg_turns(rs):
        return sum(r["turns"] for r in rs) / len(rs) if rs else float("nan")

    reason_counts = {label: 0 for label in WIN_REASON_LABELS.values()}
    reason_counts["Unknown"] = 0
    for r in decided:
        label = WIN_REASON_LABELS.get(r["win_reason"], "Unknown")
        reason_counts[label] += 1

    lines = []
    lines.append("# V17 (C++ MCTS) vs V6 (Python Heuristic) -- Local Stress Test Report")
    lines.append("")
    lines.append("**Claim key**: F = verified fact (directly measured this run), H = hypothesis/interpretation.")
    lines.append("")
    lines.append(f"- [F] Games requested: {n_games}. Games accounted for: {len(rows)}. Decided: {n_decided}. Draws: {len(draws)}. Aborted (non-crash): {len(aborted) - len(crashed)}. Worker crashes: {len(crashed)}.")
    lines.append(f"- [F] Both agents run through the real submission composition (`final_candidate_agent_v17`/`v6`: safety_wrapper -> timeout_shield -> policy), the same one Kaggle would invoke -- not the bare policy functions.")
    lines.append(f"- [H] This is a single {n_games}-game local run against each other, not the Kaggle ladder meta -- see feedback_ptcg_process.md point 3. Do not read this as a ladder-strength claim, only as a same-deck architecture A/B result.")
    lines.append("")

    lines.append("## Overall Win Rate")
    lines.append("")
    lines.append("| Agent | Wins | Win Rate (of decided games) |")
    lines.append("|---|---|---|")
    lines.append(f"| V17 (C++ MCTS) | {len(v17_wins)} | {v17_rate:.1%} |")
    lines.append(f"| V6 (Python Heuristic) | {len(v6_wins)} | {v6_rate:.1%} |")
    lines.append("")

    lines.append("## Coin-Toss / Positional Control")
    lines.append("")
    lines.append(f"- [F] Intended split: V17 assigned engine slot 0 (goes first) in {intended_v17_first} games; V6 in {intended_v6_first} games.")
    lines.append(f"- [F] Verified against the engine's own reported `first_player_slot` (not assumed, per feedback_ptcg_process.md point 2): of {len(checkable)} games with a recorded result, engine slot 0 actually went first in {slot0_went_first} of them ({slot0_mismatch} where a slot other than 0 went first -- would indicate the always-answer-yes assumption broke for one agent).")
    lines.append(f"- [F] V17 therefore actually went first in {actual_v17_first} games (intended: {intended_v17_first}).")
    lines.append("")
    lines.append("| | V17 win rate as Player 1 (went first) | V17 win rate as Player 2 (went second) |")
    lines.append("|---|---|---|")
    lines.append(f"| V17 | {v17_wins_as_p1}/{len(v17_as_p1_intended)} ({v17_p1_rate:.1%}) | {v17_wins_as_p2}/{len(v17_as_p2_intended)} ({v17_p2_rate:.1%}) |")
    lines.append("")

    lines.append("## Average Game Length (turns, wins only)")
    lines.append("")
    lines.append("| Agent | Avg turns in its own wins |")
    lines.append("|---|---|")
    lines.append(f"| V17 | {avg_turns(v17_wins):.1f} |")
    lines.append(f"| V6 | {avg_turns(v6_wins):.1f} |")
    lines.append("")

    lines.append("## Win Conditions (decided games)")
    lines.append("")
    lines.append("| Condition | Count |")
    lines.append("|---|---|")
    for label, count in reason_counts.items():
        lines.append(f"| {label} | {count} |")
    lines.append("")

    lines.append("## Search Engagement (is MCTS actually running?)")
    lines.append("")
    lines.append(
        "Added after discovering the original 1000-game run's test harness stripped "
        "`search_begin_input` before every agent call (a tools/tournament.py-local artifact, "
        "not present on the real Kaggle path -- see tools/stress_test_v17.py's "
        "`_play_one_game_keep_search_input` docstring), which silently made every decision "
        "fall through to the plain V6-greedy fallback with 0% search eligibility. Fixed for this run."
    )
    lines.append("")
    pct_eligible = (n_eligible_total / n_decisions_total * 100.0) if n_decisions_total else float("nan")
    pct_searched = (n_searched_total / n_eligible_total * 100.0) if n_eligible_total else float("nan")
    lines.append(f"- [F] Total V17 decisions: {n_decisions_total}")
    lines.append(f"- [F] Eligible for search (`context==MAIN`, `maxCount==1`, `options>=2`): {n_eligible_total} ({pct_eligible:.1f}%)")
    lines.append(f"- [F] Eligible AND `search_begin` succeeded (a real MCTS search actually ran): {n_searched_total} ({pct_searched:.1f}% of eligible)")
    lines.append(f"- [F] Decisions where `timeout_shield`'s own future timed out on this exact call (see `timed_v17`'s docstring in the script -- the shared `LAST_CALL_STATS` read would otherwise risk pairing this decision's fast fallback time with a different, still-finishing call's stats): {n_unknown_stats_total} (excluded from eligible/searched counts and from the timing/visits stats below, not counted as ineligible)")
    lines.append("")
    if all_visits:
        srt_v = sorted(all_visits)
        nv = len(srt_v)
        lines.append(f"- [F] Rollouts/simulations completed per searched decision: mean={sum(all_visits) / nv:.1f}, min={min(all_visits)}, max={max(all_visits)}, p50={srt_v[nv // 2]}, p95={srt_v[min(nv - 1, int(nv * 0.95))]}")
    else:
        lines.append("- [F] No decision ever reached a real MCTS search (0 rollouts observed) -- see above; the win-rate numbers in this report do not reflect a working search, only the V6 fallback vs itself.")
    lines.append("")

    lines.append("## V17 Execution Metrics (per-decision wall-clock time, full submission-wrapped call)")
    lines.append("")
    if all_v17_ms:
        srt = sorted(all_v17_ms)
        n = len(srt)
        p50 = srt[n // 2]
        p95 = srt[min(n - 1, int(n * 0.95))]
        p99 = srt[min(n - 1, int(n * 0.99))]
        lines.append(f"- [F] All V17 decisions (including instant non-eligible ones): mean={sum(all_v17_ms) / n:.2f} ms, min={min(all_v17_ms):.2f} ms, max={max(all_v17_ms):.2f} ms, p50={p50:.2f} ms, p95={p95:.2f} ms, p99={p99:.2f} ms")
        if all_v17_ms_searched:
            srt2 = sorted(all_v17_ms_searched)
            n2 = len(srt2)
            lines.append(f"- [F] Decisions where a real search ran only: mean={sum(all_v17_ms_searched) / n2:.2f} ms, min={min(all_v17_ms_searched):.2f} ms, max={max(all_v17_ms_searched):.2f} ms, p50={srt2[n2 // 2]:.2f} ms")
        lines.append(f"- [F] Per-decision Kaggle-equivalent budget: 2.0s (`timeout_shield.PER_DECISION_BUDGET_SECONDS`). Max observed ({max(all_v17_ms):.2f} ms) is {'WITHIN' if max(all_v17_ms) < 2000 else 'OVER'} budget.")
    else:
        lines.append("- No V17 decision timing data was captured (see raw files / crash log below).")
    lines.append("")
    lines.append(f"- Raw per-decision timings (never aggregated-away): `{TIMINGS_PATH.relative_to(REPO_ROOT)}`")
    lines.append("")

    lines.append("## Stability Audit")
    lines.append("")
    lines.append(f"- [F] Worker process crashes (native access violation / process death -- caught at the process boundary, see `{CRASHES_PATH.relative_to(REPO_ROOT)}`): **{crash_count}**")
    lines.append(f"- [F] Games lost/aborted directly due to a crash: {len(crashed)}")
    lines.append(f"- [F] Games aborted for a non-crash reason (Python exception caught by the game loop's own try/except, or `max_steps` exceeded): {len(aborted) - len(crashed)}")
    lines.append(f"- [F] V17 `timeout_shield` timeouts (a single decision exceeded its {2.0}s budget and was force-defaulted): {total_v17_timeouts}")
    lines.append(f"- [F] V17 `timeout_shield` inner exceptions (the wrapped agent itself raised, caught and defaulted): {total_v17_inner_exc}")
    lines.append(f"- [F] V17 `timeout_shield` permanent-degrade-mode activations (would indicate a match-budget exhaustion; per-game budget reset applied after every game, see script docstring): {total_v17_degraded}")
    lines.append(f"- [F] V17 `safety_wrapper` fallback-used count (final backstop: illegal/invalid selection from the inner agent, replaced with a safe legal default): {total_v17_safety_fallback}")
    lines.append("")
    if crash_count:
        lines.append("### Crash Detail")
        lines.append("")
        with open(CRASHES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                c = json.loads(line)
                hb = c.get("heartbeat_at_death", {})
                lines.append(
                    f"- Crash #{c['crash_number']}: worker exit code {c['worker_exit_code']}, "
                    f"game_index={hb.get('game_index')}, decision_index={hb.get('decision_index')}, "
                    f"turn={hb.get('turn')}, acting={hb.get('acting')}"
                )
        lines.append("")

    lines.append("## Raw Data")
    lines.append("")
    lines.append(f"- Per-game results (one JSON object per line, dense over game_index 0..{n_games - 1}): `{RAW_GAMES_PATH.relative_to(REPO_ROOT)}`")
    lines.append(f"- Per-decision V17 timings: `{TIMINGS_PATH.relative_to(REPO_ROOT)}`")
    lines.append(f"- Crash log: `{CRASHES_PATH.relative_to(REPO_ROOT)}`" if crash_count else "- Crash log: none written (zero crashes)")
    lines.append("")
    lines.append("Per project convention (feedback_ptcg_process.md point 1), this is preliminary/first-run data: raw per-game data is preserved above for any larger follow-up evaluation, and this report should not be treated as final statistical proof beyond what N=" + str(n_games) + " decided games actually supports.")

    report = "\n".join(lines)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nReport written to {REPORT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", nargs=2, type=int, metavar=("START", "END"), default=None)
    parser.add_argument("--games", type=int, default=1000)
    args = parser.parse_args()

    if args.worker is not None:
        start, end = args.worker
        run_worker(start, end, args.games)
    else:
        run_orchestrator(args.games)


if __name__ == "__main__":
    main()
