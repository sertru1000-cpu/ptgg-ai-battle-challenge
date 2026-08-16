"""V6 vs V2 real-ladder audit -- Part B: aggregate statistics.

Consumes the already-pulled/parsed data (identical methodology for both
agents, see tools/pull_v2_ladder_data.py, tools/pull_v6_ladder_data.py,
tools/build_ladder_behavior_audit.py, tools/build_phantom_dive_forensic*.py)
and computes every Part 2/4/6/7/8/9/10 statistic requested by the audit
prompt, with Wilson 95% CIs where a proportion is reported. Read-only,
writes one JSON file of computed numbers (results/v6_v2_audit/stats.json)
consumed directly when writing the audit report prose -- no number in the
report should be retyped by hand from anywhere else.
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
OUT_DIR = os.path.join(ROOT, "results", "v6_v2_audit")
os.makedirs(OUT_DIR, exist_ok=True)

LADDER_DIR = os.path.join(ROOT, "results", "ladder_behavior_audit")
PD_DIRS = {"v2": os.path.join(ROOT, "results", "phantom_dive_forensic"),
           "v6": os.path.join(ROOT, "results", "phantom_dive_forensic_v6")}
DATA_DIRS = {"v2": os.path.join(ROOT, "data", "v2_ladder_audit"),
             "v6": os.path.join(ROOT, "data", "v6_ladder_audit")}


def wilson_ci(k, n, z=1.959963985):
    if n == 0:
        return (None, None, None)
    p = k / n
    denom = 1 + z ** 2 / n
    center = (p + z ** 2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_games(label):
    rows = read_csv(os.path.join(LADDER_DIR, f"{label}_games.csv"))
    for r in rows:
        for k in ("n_turns", "n_steps", "n_decisions", "retreat_available_decisions",
                  "retreat_chosen", "attack_available_decisions", "attack_chosen_when_available",
                  "turns_with_attack_available", "missed_ko_confirmed", "missed_ko_possible",
                  "max_prize_deficit_faced",
                  "action_count_ATTACK", "action_count_RETREAT"):
            v = r.get(k)
            r[k] = int(v) if v not in (None, "") else None
        v = r.get("opponent_current_score")
        r["opponent_current_score"] = float(v) if v not in (None, "") else None
        fm = r.get("final_prize_margin_positive_means_behind")
        r["final_prize_margin_positive_means_behind"] = int(fm) if fm not in (None, "") else None
        r["went_first"] = {"True": True, "False": False}.get(r.get("went_first"), None)
        r["comeback_from_2plus_deficit"] = r.get("comeback_from_2plus_deficit") == "True"
    return rows


def load_decisions(label):
    return read_csv(os.path.join(LADDER_DIR, f"{label}_decisions.csv"))


def load_pd_events(label):
    rows = read_csv(os.path.join(PD_DIRS[label], "events.csv"))
    return rows


def load_pd_summary(label):
    with open(os.path.join(PD_DIRS[label], "phantom_dive_summary.json"), encoding="utf-8") as f:
        return json.load(f)


def our_kos_and_theirs_per_game(decisions, episode_id):
    """From the decision stream: opp_prize_n falling = we scored a KO (prize taken from
    them); our_prize_n falling = they scored a KO on us. Approximated from first->last
    seen value per episode (monotonic non-increasing in a normal game), which is the
    same approximation basis already used by max_prize_deficit_faced/final_prize_margin
    upstream in ladder_behavior_audit.py."""
    ep_decs = [d for d in decisions if d["episode_id"] == episode_id]
    if not ep_decs:
        return None, None
    opp_prize = [int(d["opp_prize_n"]) for d in ep_decs if d.get("opp_prize_n") not in (None, "")]
    our_prize = [int(d["our_prize_n"]) if False else None for d in ep_decs]  # placeholder, unused
    return opp_prize


def main():
    stats = {}
    for label in ("v2", "v6"):
        games = load_games(label)
        decisions = load_decisions(label)
        pd_summary = load_pd_summary(label)
        pd_events = load_pd_events(label)

        n = len(games)
        wins = [g for g in games if g["result"] == "WIN"]
        losses = [g for g in games if g["result"] == "LOSS"]
        draws_or_other = [g for g in games if g["result"] not in ("WIN", "LOSS")]
        w = len(wins)
        l = len(losses)
        wr, wr_lo, wr_hi = wilson_ci(w, n)

        first_games = [g for g in games if g["went_first"] is True]
        second_games = [g for g in games if g["went_first"] is False]
        unknown_first = [g for g in games if g["went_first"] is None]
        fw = sum(1 for g in first_games if g["result"] == "WIN")
        sw = sum(1 for g in second_games if g["result"] == "WIN")
        fwr, fwr_lo, fwr_hi = wilson_ci(fw, len(first_games))
        swr, swr_lo, swr_hi = wilson_ci(sw, len(second_games))

        opp_scores = [g["opponent_current_score"] for g in games if g["opponent_current_score"] is not None]

        turns_all = [g["n_turns"] for g in games if g["n_turns"] is not None]
        turns_win = [g["n_turns"] for g in wins if g["n_turns"] is not None]
        turns_loss = [g["n_turns"] for g in losses if g["n_turns"] is not None]

        max_deficits = [g["max_prize_deficit_faced"] for g in games if g["max_prize_deficit_faced"] is not None]
        final_margins = [g["final_prize_margin_positive_means_behind"] for g in games if g["final_prize_margin_positive_means_behind"] is not None]
        comebacks = [g for g in games if g["comeback_from_2plus_deficit"]]
        games_behind_at_some_point = [g for g in games if (g["max_prize_deficit_faced"] or 0) >= 1]

        retreat_avail = sum(g["retreat_available_decisions"] or 0 for g in games)
        retreat_chosen = sum(g["retreat_chosen"] or 0 for g in games)
        atk_avail = sum(g["attack_available_decisions"] or 0 for g in games)
        atk_chosen = sum(g["attack_chosen_when_available"] or 0 for g in games)
        atk_count_total = sum(g["action_count_ATTACK"] or 0 for g in games)
        retreat_count_total = sum(g["action_count_RETREAT"] or 0 for g in games)

        # "critical-situation retreat rate": retreat decisions where the opponent's threat
        # assessment (already computed in decisions.csv) says lethal_now == True.
        crit_decs = [d for d in decisions if d.get("retreat_available_this_decision") == "True"
                     and d.get("opp_lethal_now") == "True"]
        crit_retreat_chosen = [d for d in crit_decs if "RETREAT" in (d.get("chosen_option_types") or "")]

        # KOs per game: use opp_prize_n first-seen minus last-seen per episode (we scored),
        # and our_prize_n first-seen minus last-seen (they scored).
        by_ep = {}
        for d in decisions:
            by_ep.setdefault(d["episode_id"], []).append(d)
        we_scored_total, they_scored_total = 0, 0
        for eid, decs in by_ep.items():
            opp_p = [int(x["opp_prize_n"]) for x in decs if x.get("opp_prize_n") not in (None, "")]
            our_p = [int(x["our_prize_n"]) for x in decs if x.get("our_prize_n") not in (None, "")]
            if opp_p:
                we_scored_total += max(0, opp_p[0] - opp_p[-1])
            if our_p:
                they_scored_total += max(0, our_p[0] - our_p[-1])

        # opponent rating bands
        bands = [(0, 650), (650, 750), (750, 850), (850, 10**6)]
        band_stats = []
        for lo, hi in bands:
            band_games = [g for g in games if g["opponent_current_score"] is not None and lo <= g["opponent_current_score"] < hi]
            bw = sum(1 for g in band_games if g["result"] == "WIN")
            bp, blo, bhi = wilson_ci(bw, len(band_games))
            band_stats.append({"band": f"[{lo},{hi})", "n": len(band_games), "wins": bw,
                                "win_rate": bp, "wilson_lo": blo, "wilson_hi": bhi})

        # missed-KO (regular, non-Phantom-Dive-specific) confirmed rate
        missed_ko_confirmed_total = sum(g["missed_ko_confirmed"] or 0 for g in games)
        missed_ko_possible_total = sum(g["missed_ko_possible"] or 0 for g in games)

        pd_conv_p, pd_conv_lo, pd_conv_hi = wilson_ci(
            pd_summary["ko_opportunities_converted_achieved_optimal_prize"],
            pd_summary["phantom_dive_with_at_least_one_ko_opportunity"])

        stats[label] = {
            "n_games": n, "wins": w, "losses": l, "draws_or_other": len(draws_or_other),
            "win_rate": wr, "win_rate_wilson_lo": wr_lo, "win_rate_wilson_hi": wr_hi,
            "n_first": len(first_games), "n_second": len(second_games), "n_first_unknown": len(unknown_first),
            "first_player_wins": fw, "first_player_win_rate": fwr, "first_player_wilson_lo": fwr_lo, "first_player_wilson_hi": fwr_hi,
            "second_player_wins": sw, "second_player_win_rate": swr, "second_player_wilson_lo": swr_lo, "second_player_wilson_hi": swr_hi,
            "opponent_score_mean": statistics.mean(opp_scores) if opp_scores else None,
            "opponent_score_median": statistics.median(opp_scores) if opp_scores else None,
            "opponent_score_stdev": statistics.stdev(opp_scores) if len(opp_scores) > 1 else None,
            "opponent_score_n": len(opp_scores),
            "n_turns_mean_all": statistics.mean(turns_all) if turns_all else None,
            "n_turns_median_all": statistics.median(turns_all) if turns_all else None,
            "n_turns_mean_win": statistics.mean(turns_win) if turns_win else None,
            "n_turns_mean_loss": statistics.mean(turns_loss) if turns_loss else None,
            "max_prize_deficit_mean": statistics.mean(max_deficits) if max_deficits else None,
            "max_prize_deficit_max": max(max_deficits) if max_deficits else None,
            "final_prize_margin_mean": statistics.mean(final_margins) if final_margins else None,
            "n_games_ever_behind": len(games_behind_at_some_point),
            "n_comebacks_from_2plus": len(comebacks),
            "comeback_rate_of_ever_2plus_behind": (len(comebacks) / max(1, sum(1 for g in games if (g["max_prize_deficit_faced"] or 0) >= 2))),
            "retreat_available_decisions_total": retreat_avail,
            "retreat_chosen_total": retreat_chosen,
            "retreat_rate": (retreat_chosen / retreat_avail) if retreat_avail else None,
            "attack_available_decisions_total": atk_avail,
            "attack_chosen_when_available_total": atk_chosen,
            "attack_take_rate": (atk_chosen / atk_avail) if atk_avail else None,
            "action_count_ATTACK_total": atk_count_total,
            "action_count_ATTACK_per_game": (atk_count_total / n) if n else None,
            "action_count_RETREAT_total": retreat_count_total,
            "action_count_RETREAT_per_game": (retreat_count_total / n) if n else None,
            "critical_retreat_opportunities": len(crit_decs),
            "critical_retreat_chosen": len(crit_retreat_chosen),
            "critical_retreat_rate": (len(crit_retreat_chosen) / len(crit_decs)) if crit_decs else None,
            "we_scored_kos_total": we_scored_total,
            "we_scored_kos_per_game": (we_scored_total / n) if n else None,
            "opponent_scored_kos_total": they_scored_total,
            "opponent_scored_kos_per_game": (they_scored_total / n) if n else None,
            "opponent_rating_bands": band_stats,
            "missed_ko_confirmed_total": missed_ko_confirmed_total,
            "missed_ko_possible_total": missed_ko_possible_total,
            "missed_ko_confirmed_per_game": (missed_ko_confirmed_total / n) if n else None,
            "phantom_dive_summary": pd_summary,
            "phantom_dive_conversion_wilson": {"p": pd_conv_p, "lo": pd_conv_lo, "hi": pd_conv_hi},
        }

        # loss-specific: for each loss, did we have a PD lethal opportunity in that game, missed?
        loss_eids = {g["episode_id"] for g in losses}
        loss_pd_events = [e for e in pd_events if e["episode_id"] in loss_eids]
        loss_pd_missed = [e for e in loss_pd_events if e.get("best_prize_achievable") not in (None, "", "0") and e.get("prize_shortfall") not in (None, "", "0")]
        games_lost_with_missed_pd_ko = len({e["episode_id"] for e in loss_pd_missed})
        stats[label]["loss_analysis"] = {
            "n_losses": l,
            "n_losses_with_any_pd_attack": len({e["episode_id"] for e in loss_pd_events}),
            "n_losses_with_missed_pd_ko": games_lost_with_missed_pd_ko,
            "loss_episode_ids": sorted(loss_eids),
        }

    with open(os.path.join(OUT_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
