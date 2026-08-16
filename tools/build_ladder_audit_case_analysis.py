"""V2-vs-Luca real-ladder behavioral audit -- Part C: derived metrics, prize-denial case
analysis (Cases A-E), counterfactual assessment, and loss-pattern analysis.

Reads results/ladder_behavior_audit/{label}_{games,decisions}.csv (produced by
tools/build_ladder_behavior_audit.py, IDENTICAL pipeline for both agents) and computes every
number requested for the V2 real-ladder audit report, using the SAME code for both labels.

Never fabricates a value it can't support: any figure that depends on data this pipeline
doesn't have returns None, and the report-writing step is expected to render that as
"NOT IDENTIFIABLE FROM AVAILABLE DATA" rather than a number.
"""
from __future__ import annotations

import csv
import json
import os
import statistics
from collections import Counter, defaultdict

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()
import cg.api as api  # noqa: E402

CARDS_BY_ID = {c.cardId: c for c in api.all_card_data()}

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
IN_DIR = os.path.join(ROOT, "results", "ladder_behavior_audit")
OUT_DIR = IN_DIR
LABELS = ["luca", "v2"]


def _b(v):
    """CSV round-trips booleans as the strings 'True'/'False'/''."""
    if v in ("True", "1", True):
        return True
    if v in ("False", "0", False, ""):
        return False
    return None


def _f(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _i(v):
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def load(label):
    with open(os.path.join(IN_DIR, f"{label}_games.csv"), encoding="utf-8") as f:
        games = list(csv.DictReader(f))
    with open(os.path.join(IN_DIR, f"{label}_decisions.csv"), encoding="utf-8") as f:
        decisions = list(csv.DictReader(f))
    return games, decisions


# ---------------------------------------------------------------------------
# Section 3: game-level metrics
# ---------------------------------------------------------------------------
def game_level_metrics(games):
    n = len(games)
    decisive = [g for g in games if g["result"] in ("WIN", "LOSS")]
    wins = [g for g in games if g["result"] == "WIN"]
    losses = [g for g in games if g["result"] == "LOSS"]
    lengths = [_i(g["n_turns"]) for g in games if _i(g["n_turns"]) is not None]
    first = [g for g in games if _b(g["went_first"]) is True]
    second = [g for g in games if _b(g["went_first"]) is False]

    def wr(gs):
        d = [g for g in gs if g["result"] in ("WIN", "LOSS")]
        return (sum(1 for g in d if g["result"] == "WIN") / len(d)) if d else None

    deficits = [_i(g["max_prize_deficit_faced"]) for g in games if _i(g["max_prize_deficit_faced"]) is not None]
    games_2plus = [g for g in games if (_i(g["max_prize_deficit_faced"]) or 0) >= 2]
    comebacks = sum(1 for g in games if _b(g["comeback_from_2plus_deficit"]))
    final_margins_win = [_f(g["final_prize_margin_positive_means_behind"]) for g in wins if _f(g["final_prize_margin_positive_means_behind"]) is not None]
    final_margins_loss = [_f(g["final_prize_margin_positive_means_behind"]) for g in losses if _f(g["final_prize_margin_positive_means_behind"]) is not None]

    return {
        "games_total": n,
        "wins": len(wins), "losses": len(losses),
        "draws": sum(1 for g in games if g["result"] == "DRAW"),
        "errors_or_timeouts": sum(1 for g in games if g["result"] == "ERROR_OR_TIMEOUT"),
        "win_rate": (len(wins) / len(decisive)) if decisive else None,
        "avg_game_length_turns": statistics.mean(lengths) if lengths else None,
        "median_game_length_turns": statistics.median(lengths) if lengths else None,
        "n_going_first": len(first), "win_rate_going_first": wr(first),
        "n_going_second": len(second), "win_rate_going_second": wr(second),
        "games_with_2plus_prize_deficit": len(games_2plus),
        "frequency_2plus_prize_deficit": len(games_2plus) / n if n else None,
        "comeback_rate_when_2plus_behind": (comebacks / len(games_2plus)) if games_2plus else None,
        "comebacks_from_2plus_deficit": comebacks,
        "avg_max_deficit_faced": statistics.mean(deficits) if deficits else None,
        "avg_final_prize_margin_wins_positive_means_behind": statistics.mean(final_margins_win) if final_margins_win else None,
        "avg_final_prize_margin_losses_positive_means_behind": statistics.mean(final_margins_loss) if final_margins_loss else None,
    }


# ---------------------------------------------------------------------------
# Section 4: action-level metrics + retreat sub-categories
# ---------------------------------------------------------------------------
def action_level_metrics(games, decisions):
    n_decisions = len(decisions)
    action_counts = Counter(d["action_class"] for d in decisions if d["action_class"])
    n_games = len(games)

    turn_attack_rates = [_f(g["turn_attack_rate"]) for g in games if _f(g["turn_attack_rate"]) is not None]
    turns_avail = [_i(g["turns_with_attack_available"]) for g in games]
    weighted_attack = None
    pairs = [(r, t) for r, t in zip(turn_attack_rates, turns_avail) if r is not None and t]
    if pairs:
        weighted_attack = sum(r * t for r, t in pairs) / sum(t for _, t in pairs)

    retreat_avail = sum(_i(g["retreat_available_decisions"]) or 0 for g in games)
    retreat_chosen = sum(_i(g["retreat_chosen"]) or 0 for g in games)

    attacks = [d for d in decisions if d["action_class"] == "ATTACK"]
    successful_kos = [
        d for d in attacks
        if (_i(d.get("opp_active_hp_after")) == 0 or d.get("opp_active_id_after") in (None, ""))
        and _i(d.get("opp_active_id")) is not None
    ]

    ret_all = [d for d in decisions if d["action_class"] == "RETREAT"]
    ret_2prize = [d for d in ret_all if _f(d["our_active_prize_value"]) is not None and _f(d["our_active_prize_value"]) >= 2]
    ret_damaged = [d for d in ret_all if _b(d["our_active_damaged"])]
    ret_lethal_now = [d for d in ret_all if _b(d["opp_lethal_now"])]
    ret_lethal_soon = [d for d in ret_all if _b(d["opp_lethal_now"]) or _b(d["opp_lethal_with_one_more_energy"])]
    ret_bench_target = [d for d in ret_all if _b(d["bench_target_exists"])]

    cond_2prize = [d for d in decisions if _f(d["our_active_prize_value"]) is not None and _f(d["our_active_prize_value"]) >= 2]
    cond_damaged = [d for d in decisions if _b(d["our_active_damaged"])]
    cond_lethal_now = [d for d in decisions if _b(d["opp_lethal_now"])]
    cond_bench_target = [d for d in decisions if _b(d["bench_target_exists"])]
    cond_retreat_avail = [d for d in decisions if _b(d["retreat_available_this_decision"])]

    def rate(sub_list, cond_list):
        return (len(sub_list) / len(cond_list)) if cond_list else None

    return {
        "n_decisions": n_decisions, "n_games": n_games,
        "action_counts_total": dict(action_counts),
        "action_rate_per_game": {k: v / n_games for k, v in action_counts.items()} if n_games else {},
        "attack_rate_per_turn_weighted": weighted_attack,
        "retreat_rate_per_decision": retreat_chosen / n_decisions if n_decisions else None,
        "retreat_rate_when_available": retreat_chosen / retreat_avail if retreat_avail else None,
        "ko_attempts_total": len(attacks),
        "successful_kos_total": len(successful_kos),
        "ko_success_rate_per_attack": (len(successful_kos) / len(attacks)) if attacks else None,
        "missed_ko_confirmed_total": sum(_i(g["missed_ko_confirmed"]) or 0 for g in games),
        "missed_ko_possible_total": sum(_i(g["missed_ko_possible"]) or 0 for g in games),
        "retreat_categories": {
            "1_all_retreats": {"count": len(ret_all), "rate_per_decision": len(ret_all) / n_decisions if n_decisions else None},
            "2_retreat_when_available": {"count": len(ret_all), "denominator_decisions_retreat_legal": len(cond_retreat_avail), "rate": rate(ret_all, cond_retreat_avail)},
            "3_retreat_of_2plus_prize_pokemon": {"count": len(ret_2prize), "denominator_decisions_active_is_2plus_prize": len(cond_2prize), "rate": rate(ret_2prize, cond_2prize)},
            "4_retreat_of_damaged_pokemon": {"count": len(ret_damaged), "denominator_decisions_active_damaged": len(cond_damaged), "rate": rate(ret_damaged, cond_damaged)},
            "5_retreat_when_opp_lethal_now": {"count": len(ret_lethal_now), "denominator_decisions_opp_lethal_now": len(cond_lethal_now), "rate": rate(ret_lethal_now, cond_lethal_now)},
            "5b_retreat_when_opp_lethal_now_or_one_energy_away": {"count": len(ret_lethal_soon)},
            "6_retreat_when_bench_target_exists": {"count": len(ret_bench_target), "denominator_decisions_bench_target_exists": len(cond_bench_target), "rate": rate(ret_bench_target, cond_bench_target)},
        },
        "conjunctive_condition_counts_marginal": {
            "A_active_is_2plus_prize": len(cond_2prize),
            "B_active_damaged": len(cond_damaged),
            "C_opp_lethal_now": len(cond_lethal_now),
            "D_retreat_legal": len(cond_retreat_avail),
            "E_bench_target_exists": len(cond_bench_target),
        },
    }


# ---------------------------------------------------------------------------
# Section 5 + 6: prize-denial critical-situation case analysis + counterfactual
# ---------------------------------------------------------------------------
def critical_situation_analysis(decisions):
    by_episode = defaultdict(list)
    for d in decisions:
        by_episode[d["episode_id"]].append(d)
    for eid in by_episode:
        by_episode[eid].sort(key=lambda d: _i(d["decision_index"]))

    critical = []
    for d in decisions:
        cond = (
            _f(d["our_active_prize_value"]) is not None and _f(d["our_active_prize_value"]) >= 2
            and _b(d["our_active_damaged"])
            and _b(d["opp_lethal_now"])
            and _b(d["retreat_available_this_decision"])
            and _b(d["bench_target_exists"])
        )
        if cond:
            critical.append(d)

    retreated = [d for d in critical if d["action_class"] == "RETREAT" or "RETREAT" in (d.get("chosen_option_types") or "")]
    stayed = [d for d in critical if d not in retreated]

    stayed_outcomes = []
    for d in stayed:
        eid = d["episode_id"]
        seq = by_episode[eid]
        idx_in_seq = next((i for i, x in enumerate(seq) if x["decision_index"] == d["decision_index"]), None)
        outcome = "UNKNOWN"
        if idx_in_seq is not None and idx_in_seq + 1 < len(seq):
            nxt = seq[idx_in_seq + 1]
            active_changed = _i(nxt["our_active_id"]) != _i(d["our_active_id"])
            opp_prize_dropped = (_i(nxt["opp_prize_n"]) is not None and _i(d["opp_prize_n"]) is not None
                                  and _i(nxt["opp_prize_n"]) < _i(d["opp_prize_n"]))
            if active_changed and opp_prize_dropped:
                outcome = "CONFIRMED_KO_NEXT_DECISION"
            elif active_changed:
                outcome = "ACTIVE_CHANGED_NO_PRIZE_DROP (not a KO -- other switch)"
            else:
                outcome = "SURVIVED_TO_NEXT_DECISION"
        else:
            outcome = "GAME_ENDED_HERE (result=" + d["result"] + ", not directly confirmable as this Pokemon's KO)"
        stayed_outcomes.append({
            "episode_id": eid, "decision_index": d["decision_index"], "turn": d["turn"],
            "result": d["result"], "outcome": outcome,
            "our_active_id": d["our_active_id"], "our_active_hp": d["our_active_hp"],
            "our_active_retreat_cost": d["our_active_retreat_cost"],
            "our_active_energy_loss_if_retreated": d["our_active_energy_loss_if_retreated"],
            "bench_ready_attackers": d["bench_ready_attackers"],
            "opp_best_attack_damage": d["opp_best_attack_damage"],
        })

    confirmed_ko_after_stay = [o for o in stayed_outcomes if o["outcome"] == "CONFIRMED_KO_NEXT_DECISION"]

    def mean_or_none(vals):
        vals = [v for v in vals if v is not None]
        return statistics.mean(vals) if vals else None

    counterfactual = {
        "n_confirmed_ko_after_staying": len(confirmed_ko_after_stay),
        "avg_retreat_cost": mean_or_none([_f(o["our_active_retreat_cost"]) for o in confirmed_ko_after_stay]),
        "avg_energy_loss_if_had_retreated": mean_or_none([_f(o["our_active_energy_loss_if_retreated"]) for o in confirmed_ko_after_stay]),
        "n_with_zero_ready_bench_attacker": sum(1 for o in confirmed_ko_after_stay if _i(o["bench_ready_attackers"]) == 0),
        "n_with_ready_bench_attacker": sum(1 for o in confirmed_ko_after_stay if (_i(o["bench_ready_attackers"]) or 0) > 0),
        "avg_opp_best_attack_damage": mean_or_none([_f(o["opp_best_attack_damage"]) for o in confirmed_ko_after_stay]),
        "game_results_after_these_events": dict(Counter(o["result"] for o in confirmed_ko_after_stay)),
    }

    return {
        "n_critical_situations": len(critical),
        "n_retreated": len(retreated),
        "n_stayed": len(stayed),
        "retreat_rate_in_critical_situations": (len(retreated) / len(critical)) if critical else None,
        "stayed_outcomes_breakdown": dict(Counter(o["outcome"].split(" (")[0] for o in stayed_outcomes)),
        "counterfactual": counterfactual,
    }, stayed_outcomes


# ---------------------------------------------------------------------------
# Section 7: loss analysis
# ---------------------------------------------------------------------------
def loss_analysis(games, decisions, label):
    by_episode = defaultdict(list)
    for d in decisions:
        by_episode[d["episode_id"]].append(d)
    for eid in by_episode:
        by_episode[eid].sort(key=lambda d: _i(d["decision_index"]))

    loss_games = [g for g in games if g["result"] == "LOSS"]
    rows = []
    for g in loss_games:
        eid = g["episode_id"]
        seq = by_episode.get(eid, [])
        first_2plus_turn = None
        for d in seq:
            us = _i(d.get("our_prize_n"))
            op = _i(d.get("opp_prize_n"))
            if us is not None and op is not None and (us - op) >= 2:
                first_2plus_turn = _i(d["turn"])
                break
        last3 = seq[-3:] if len(seq) >= 3 else seq
        last3_actions = [d["action_class"] for d in last3]
        retreat_possible_late = any(_b(d["retreat_available_this_decision"]) for d in last3)
        bench_target_late = any(_b(d["bench_target_exists"]) for d in last3)
        lost_2prize_attacker = any(
            (d["action_class"] != "RETREAT")
            and _f(d["our_active_prize_value"]) is not None and _f(d["our_active_prize_value"]) >= 2
            and i + 1 < len(seq) and _i(seq[i + 1]["our_active_id"]) != _i(d["our_active_id"])
            for i, d in enumerate(seq)
        )
        n_missed_ko = int(_f(g["missed_ko_confirmed"]) or 0) + int(_f(g["missed_ko_possible"]) or 0)
        n_energy_attach = sum(1 for d in seq if d["action_class"] == "ATTACH_ENERGY")
        n_turns = _i(g["n_turns"]) or 1
        energy_attach_rate = n_energy_attach / n_turns if n_turns else None

        rows.append({
            "episode_id": eid, "label": label,
            "n_turns": g["n_turns"], "went_first": g["went_first"],
            "final_prize_margin_positive_means_behind": g["final_prize_margin_positive_means_behind"],
            "max_prize_deficit_faced": g["max_prize_deficit_faced"],
            "last3_own_decisions_action_classes": ";".join(a or "?" for a in last3_actions),
            "retreat_available_in_last3_decisions": retreat_possible_late,
            "bench_target_available_in_last3_decisions": bench_target_late,
            "lost_a_2plus_prize_attacker_this_game": lost_2prize_attacker,
            "missed_ko_events_this_game": n_missed_ko,
            "energy_attach_per_turn": energy_attach_rate,
        })

    patterns = {
        "n_losses": len(loss_games),
        "losses_going_first": sum(1 for r in rows if _b(r["went_first"]) is True),
        "losses_going_second": sum(1 for r in rows if _b(r["went_first"]) is False),
        "losses_with_2plus_deficit": sum(1 for r in rows if (_i(r["max_prize_deficit_faced"]) or 0) >= 2),
        "losses_where_retreat_was_available_late": sum(1 for r in rows if r["retreat_available_in_last3_decisions"]),
        "losses_where_bench_target_available_late": sum(1 for r in rows if r["bench_target_available_in_last3_decisions"]),
        "losses_that_lost_a_2plus_prize_attacker": sum(1 for r in rows if r["lost_a_2plus_prize_attacker_this_game"]),
        "losses_with_any_missed_ko_event": sum(1 for r in rows if r["missed_ko_events_this_game"] > 0),
        "avg_final_prize_margin": statistics.mean([_f(r["final_prize_margin_positive_means_behind"]) for r in rows if _f(r["final_prize_margin_positive_means_behind"]) is not None]) if rows else None,
        "avg_energy_attach_per_turn": statistics.mean([r["energy_attach_per_turn"] for r in rows if r["energy_attach_per_turn"] is not None]) if rows else None,
    }
    return rows, patterns


def main():
    all_summaries = {}
    for label in LABELS:
        games, decisions = load(label)
        gm = game_level_metrics(games)
        am = action_level_metrics(games, decisions)
        crit, stayed_outcomes = critical_situation_analysis(decisions)
        loss_rows, loss_patterns = loss_analysis(games, decisions, label)

        with open(os.path.join(OUT_DIR, f"{label}_stayed_critical_outcomes.csv"), "w", newline="", encoding="utf-8") as f:
            if stayed_outcomes:
                w = csv.DictWriter(f, fieldnames=list(stayed_outcomes[0].keys()))
                w.writeheader()
                w.writerows(stayed_outcomes)
            else:
                f.write("no_critical_stayed_situations_found\n")

        with open(os.path.join(OUT_DIR, f"{label}_loss_analysis.csv"), "w", newline="", encoding="utf-8") as f:
            if loss_rows:
                w = csv.DictWriter(f, fieldnames=list(loss_rows[0].keys()))
                w.writeheader()
                w.writerows(loss_rows)
            else:
                f.write("no_losses\n")

        summary = {
            "label": label,
            "game_level": gm,
            "action_level": am,
            "critical_situation_analysis": crit,
            "loss_patterns": loss_patterns,
        }
        all_summaries[label] = summary
        with open(os.path.join(OUT_DIR, f"{label}_full_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"=== {label} ===")
        print(json.dumps(summary, indent=2, default=str))

    with open(os.path.join(OUT_DIR, "both_summaries.json"), "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, default=str)


if __name__ == "__main__":
    main()
