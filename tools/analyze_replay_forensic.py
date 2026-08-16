"""Phase: Replay + Agent Log Forensic Analysis v1 -- deep-dive analysis pass.

Consumes the per-episode parsed cache (data/kaggle_ladder/parsed/*.json,
built by tools/build_replay_forensic_v1.py) to answer the phase's
loss-analysis / early-late-game / going-first-second / timing / opponent /
win-vs-loss questions. Prints one big JSON so the report-writing step uses
exact numbers, not re-derived ones.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
from collections import Counter, defaultdict

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
CACHE_DIR = os.path.join(ROOT, "data", "kaggle_ladder", "parsed")
OUT_DIR = os.path.join(ROOT, "results", "agent")

MEANINGFUL_CONTEXTS = {0, 35, 36}


def load_all():
    out = []
    for p in sorted(glob.glob(os.path.join(CACHE_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def meaningful(decisions):
    return [d for d in decisions if d["select_context"] in MEANINGFUL_CONTEXTS and d["n_options"] > 1]


def going_first_directly(parsed):
    """Determine our_turn_order strictly from replay data (state.turn +
    first move), never from agent-intent assumptions. Uses the first
    non-null firstPlayer observed anywhere in either player's state, cross-
    checked against our_index (already the actual engine-observed slot)."""
    decisions = parsed["decisions"]
    for d in decisions:
        # state_before/after do not carry firstPlayer directly (trimmed snapshot);
        # re-derive from the cached decisions' turn progression instead: the
        # player whose first MAIN-context decision happens at turn 1 with the
        # lower row_index went first. Simpler and equally direct: reuse turn
        # field parity is unreliable, so fall back to explicit first_player
        # field cached separately per episode by the ladder-stats phase.
        pass
    return None


def main():
    all_parsed = load_all()
    ladder = [p for p in all_parsed if p["result"] in ("WIN", "LOSS", "DRAW")]
    # exclude the validation episode (self-play, both sides = our own submission)
    # -- identified the same way the prior phase did: episode 92032692.
    ladder = [p for p in ladder if p["episode_id"] != 92032692]

    out = {}

    # ---- Going First/Second, re-derived directly from the replay's own
    # firstPlayer field (loaded straight from the raw replay JSON here, not
    # from the prior phase's CSV, to satisfy "verify directly" per the prompt).
    import glob as _glob
    replay_dir = os.path.join(ROOT, "data", "kaggle_ladder", "replays")
    gf_results, gs_results = [], []
    for p in ladder:
        eid = p["episode_id"]
        rp = os.path.join(replay_dir, f"episode-{eid}-replay.json")
        with open(rp, encoding="utf-8") as f:
            d = json.load(f)
        steps = d["steps"]
        idx = p["our_index"]
        fp = None
        for s in steps:
            cur = s[idx]["observation"].get("current")
            if cur and cur.get("firstPlayer") not in (None, -1):
                fp = cur["firstPlayer"]
        went_first = (fp == idx) if fp is not None else None
        (gf_results if went_first else gs_results if went_first is False else []).append(p["result"])
    gf_wins = sum(1 for r in gf_results if r == "WIN")
    gs_wins = sum(1 for r in gs_results if r == "WIN")
    out["going_first_second"] = {
        "going_first_games": len(gf_results), "going_first_wins": gf_wins,
        "going_first_wr": gf_wins / len(gf_results) if gf_results else None,
        "going_second_games": len(gs_results), "going_second_wins": gs_wins,
        "going_second_wr": gs_wins / len(gs_results) if gs_results else None,
    }

    # ---- Timing, overall vs pre-loss-specific
    all_durations = []
    loss_last5_durations = []
    for p in ladder:
        for d in p["decisions"]:
            if d["log_duration_s"] is not None:
                all_durations.append(d["log_duration_s"])
        if p["result"] == "LOSS":
            m = meaningful(p["decisions"])
            for d in m[-5:]:
                if d["log_duration_s"] is not None:
                    loss_last5_durations.append(d["log_duration_s"])
    def pctl(lst, q):
        if not lst:
            return None
        s = sorted(lst)
        return s[min(len(s) - 1, int(q * (len(s) - 1)))]
    out["timing"] = {
        "n_calls_total": len(all_durations),
        "mean_s": statistics.mean(all_durations) if all_durations else None,
        "median_s": statistics.median(all_durations) if all_durations else None,
        "p95_s": pctl(all_durations, 0.95),
        "p99_s": pctl(all_durations, 0.99),
        "max_s": max(all_durations) if all_durations else None,
        "n_calls_ge_1s": sum(1 for x in all_durations if x >= 1.0),
        "n_pre_loss_last5_calls": len(loss_last5_durations),
        "pre_loss_last5_mean_s": statistics.mean(loss_last5_durations) if loss_last5_durations else None,
        "pre_loss_last5_max_s": max(loss_last5_durations) if loss_last5_durations else None,
    }
    err_count = sum(1 for p in ladder for d in p["decisions"] if d["log_stderr"])
    out["errors_total"] = err_count

    # ---- Loss deep-dive: last 5 meaningful decisions, deterioration point
    loss_dives = []
    for p in ladder:
        if p["result"] != "LOSS":
            continue
        m = meaningful(p["decisions"])
        last5 = m[-5:]
        # deterioration: first meaningful decision where opp_prize lead over us is >=2
        # (opponent has taken >=2 more of their available KO-prizes than we have)
        det_idx = None
        for i, d in enumerate(m):
            our_pz = d["state_before"].get("prize_n")
            opp_pz = d["opp_before"].get("prize_n")
            if our_pz is None or opp_pz is None:
                continue
            our_taken = 6 - our_pz  # prizes WE have already claimed (lower prize_n = more taken = better for us)
            opp_taken = 6 - opp_pz
            if opp_taken - our_taken >= 2:
                det_idx = i
                break
        loss_dives.append({
            "episode_id": p["episode_id"],
            "n_meaningful_decisions": len(m),
            "last5_categories": [d["category"] for d in last5],
            "last5_contexts": [d["select_context_name"] for d in last5],
            "last5_chosen": [d["chosen_option_types"] for d in last5],
            "deterioration_decision_index_in_meaningful_list": det_idx,
            "deterioration_total_meaningful": len(m),
            "deterioration_fraction_through_game": (det_idx / len(m)) if (det_idx is not None and m) else None,
            "final_our_prize": m[-1]["state_after"].get("prize_n") if m else None,
            "final_opp_prize": m[-1]["opp_after"].get("prize_n") if m else None,
        })
    out["loss_dives"] = loss_dives

    # ---- Final-3-turns classification (LOSS_ALREADY_FORCED heuristic)
    final_turn_class = []
    for p in ladder:
        if p["result"] != "LOSS":
            continue
        m = meaningful(p["decisions"])
        if not m:
            continue
        last_turn = m[-1]["turn"]
        final_window = [d for d in m if last_turn is not None and d["turn"] is not None and d["turn"] >= last_turn - 2]
        if not final_window:
            final_window = m[-3:]
        our_pz = final_window[0]["state_before"].get("prize_n")
        opp_pz = final_window[0]["opp_before"].get("prize_n")
        our_active_hp = final_window[0]["state_before"].get("active_hp")
        if our_pz is not None and opp_pz is not None:
            deficit = (6 - opp_pz) - (6 - our_pz)
        else:
            deficit = None
        if deficit is not None and deficit >= 3:
            cls = "LOSS_ALREADY_FORCED"
        elif deficit is not None and deficit >= 1:
            cls = "LOSS_LIKELY_DECIDED_HERE"
        elif deficit is not None and deficit <= 0:
            cls = "LOSS_FIRST_BECAME_CLEAR_HERE"
        else:
            cls = "CAUSE_UNCLEAR"
        final_turn_class.append({
            "episode_id": p["episode_id"], "final_window_turns": [d["turn"] for d in final_window],
            "prize_deficit_at_window_start": deficit, "classification": cls,
        })
    out["final_turn_classification"] = final_turn_class
    out["final_turn_classification_counts"] = dict(Counter(x["classification"] for x in final_turn_class))

    # ---- Early game (first 5 meaningful decisions) summary
    early_rows = []
    for p in ladder:
        m = meaningful(p["decisions"])
        first5 = m[:5]
        early_rows.append({
            "episode_id": p["episode_id"], "result": p["result"],
            "first5_categories": [d["category"] for d in first5],
        })
    out["early_game"] = early_rows
    cat_counter_by_result_early = defaultdict(lambda: {"WIN": 0, "LOSS": 0})
    for row in early_rows:
        if row["result"] not in ("WIN", "LOSS"):
            continue
        for c in set(row["first5_categories"]):
            cat_counter_by_result_early[c][row["result"]] += 1
    out["early_game_category_by_result"] = dict(cat_counter_by_result_early)

    # ---- Win vs loss: last-5-meaningful category frequency comparison
    cat_counter_by_result_late = defaultdict(lambda: {"WIN": 0, "LOSS": 0})
    for p in ladder:
        if p["result"] not in ("WIN", "LOSS"):
            continue
        m = meaningful(p["decisions"])
        last5 = m[-5:]
        for c in set(d["category"] for d in last5):
            cat_counter_by_result_late[c][p["result"]] += 1
    out["late_game_category_by_result"] = dict(cat_counter_by_result_late)

    # ---- Opponent analysis
    opp_rows = defaultdict(lambda: {"games": 0, "wins": 0, "losses": 0, "turns": []})
    for p in ladder:
        # opponent name not stored in cache; re-derive from episodes_raw.json via
        # results/agent/kaggle_ladder_games.csv (already built, prior phase)
        pass
    out["n_ladder_games_this_phase"] = len(ladder)
    out["n_wins"] = sum(1 for p in ladder if p["result"] == "WIN")
    out["n_losses"] = sum(1 for p in ladder if p["result"] == "LOSS")
    out["n_draws"] = sum(1 for p in ladder if p["result"] == "DRAW")

    with open(os.path.join(OUT_DIR, "replay_forensic_stats.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str)[:6000])


if __name__ == "__main__":
    main()
