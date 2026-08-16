"""V6 Loss Root-Cause Audit -- turn-by-turn forensic reconstruction of every real V6 ladder loss.

Reuses the existing shared parser (src/meta_analysis/ladder_behavior_audit.py) rather than
building a new one -- same convention as every prior real-ladder audit in this project. Adds
two new signals not computed anywhere before: bench-lock detection (hand contains a Pokemon
card while the bench is already at its 5-slot cap) and a supporter/item hand-economy trace
(hand_n/discard_n delta across every PLAY_SUPPORTER/PLAY_ITEM decision).

Read-only: no agent/deck/weight/submission changes. Writes results/v6_loss_audit/*.
"""
from __future__ import annotations

import csv
import json
import os

from src.meta_analysis.ladder_behavior_audit import (
    parse_episode, find_missed_knockouts, CARDS_BY_ID, ATTACKS_BY_ID,
)

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
SUBMISSION_ID = 55475115
REPLAY_DIR = os.path.join(ROOT, "data", "v6_ladder_audit", "replays")
EPISODES_FILE = os.path.join(ROOT, "data", "v6_ladder_audit", "v6_episodes_raw.json")
OPP_RATINGS_FILE = os.path.join(ROOT, "data", "v6_ladder_audit", "opponent_ratings_raw.json")
OUT_DIR = os.path.join(ROOT, "results", "v6_loss_audit")
os.makedirs(OUT_DIR, exist_ok=True)

PHANTOM_DIVE_ID = 154
BENCH_CAP = 5


def is_basic_pokemon_card(card_id):
    """Only BASIC Pokemon actually require an empty bench slot to enter play. Stage 1/2
    evolution cards evolve IN PLACE onto an already-benched (or active) pre-evolution and
    need zero bench space -- confirmed via cg.api.CardData's own `basic` flag. An earlier
    version of this detector treated any hand Pokemon card as bench-space-gated, which
    produced a false positive on Dragapult ex sitting in hand while 3 Drakloak already sat on
    a full bench (the real, cheap fix there is EVOLVE, not a new bench slot)."""
    cd = CARDS_BY_ID.get(card_id)
    return bool(cd and cd.cardType == 0 and cd.basic)


def load_games():
    with open(EPISODES_FILE, encoding="utf-8") as f:
        eps_meta = json.load(f)
    with open(OPP_RATINGS_FILE, encoding="utf-8") as f:
        opp_ratings = {r["team_id"]: r for r in json.load(f)}
    games = []
    for e in eps_meta:
        if e.get("type") == "EPISODE_TYPE_VALIDATION":
            continue
        parsed = parse_episode(e["id"], e, REPLAY_DIR, SUBMISSION_ID, "v6")
        if parsed is None:
            continue
        opp_info = opp_ratings.get(parsed["opponent_team_id"], {})
        raw_score = opp_info.get("current_public_score")
        parsed["opponent_current_score"] = float(raw_score) if raw_score is not None else None
        games.append(parsed)
    return games


def turn_trajectory(decisions):
    """Per-turn deficit series using the LAST decision observed each turn (deficit = our own
    remaining-prize-count minus opponent's remaining-prize-count; POSITIVE = we are behind,
    since a lower own-prize-count means WE have been securing more KOs -- verified against
    known WIN/LOSS outcomes in v6_games.csv before use, see report Section 2 methodology note).
    """
    by_turn = {}
    for d in decisions:
        t = d["turn"]
        us = d["state_before"].get("prize_n")
        op = d["opp_before"].get("prize_n")
        if t is None or us is None or op is None:
            continue
        by_turn[t] = (us, op)
    turns = sorted(by_turn)
    series = [(t, by_turn[t][0], by_turn[t][1], by_turn[t][0] - by_turn[t][1]) for t in turns]
    return series


def find_decisive_turn(series):
    """First turn after which the deficit never again drops back below 2 ('point of no
    return'), i.e. the earliest turn from which the game is a persistent 2+-prize race deficit
    through to the end. Returns None if the deficit never reaches 2 (game lost some other way,
    e.g. sudden multi-prize swing on the final turn) or oscillates below 2 until the very end."""
    n = len(series)
    for i, (t, us, op, deficit) in enumerate(series):
        if deficit >= 2 and all(s[3] >= 2 for s in series[i:]):
            return t
    return None


def first_turn_deficit_at_least(series, k):
    for t, us, op, deficit in series:
        if deficit >= k:
            return t
    return None


def bench_lock_events(decisions):
    """A decision where our hand (fully visible) contains >=1 Pokemon card, bench is already
    at the 5-slot cap, and the chosen action this decision was NOT playing that Pokemon.
    Cross-references forward: was ANY hand Pokemon from this decision ever actually played
    later that game (by card id, not serial -- an approximation, documented)."""
    events = []
    for k, d in enumerate(decisions):
        if d["select_context"] != 0:
            continue
        hand = d["state_before"].get("hand") or []
        bench_n = d["state_before"].get("bench_n")
        if bench_n is None or bench_n < BENCH_CAP:
            continue
        hand_pokemon_ids = [c.get("id") for c in hand if is_basic_pokemon_card(c.get("id"))]
        if not hand_pokemon_ids:
            continue
        if d["action_class"] == "PLAY_POKEMON":
            continue
        events.append({
            "decision_index": k, "turn": d["turn"],
            "hand_pokemon_ids": hand_pokemon_ids,
            "hand_pokemon_names": [CARDS_BY_ID[i].name for i in hand_pokemon_ids],
            "bench_n": bench_n,
        })
    return events


def bench_lock_ever_resolved(decisions, event):
    """Did any of the flagged hand Pokemon (by card id) get played at any LATER decision in
    the same game? True = eventually resolved (denied only temporarily). False = never played
    (denied for the rest of the game, and is either stuck in hand at game end or discarded)."""
    ids = set(event["hand_pokemon_ids"])
    for d in decisions[event["decision_index"] + 1:]:
        if d["action_class"] == "PLAY_POKEMON":
            cid = (d.get("action_detail") or {}).get("card_id")
            if cid in ids:
                return True
    return False


def supporter_item_trace(decisions):
    """hand_n/discard_n delta across every PLAY_SUPPORTER / PLAY_ITEM decision. Card text is
    not available in cg.api's CardData for trainer cards (verified empty this session), so the
    exact discard MECHANISM of any given supporter cannot be source-verified -- this trace
    reports the empirically OBSERVED hand/discard delta only, never an inferred rule."""
    events = []
    for k, d in enumerate(decisions):
        if d["action_class"] not in ("PLAY_SUPPORTER", "PLAY_ITEM"):
            continue
        cid = (d.get("action_detail") or {}).get("card_id")
        hand_before = d["state_before"].get("hand_n")
        discard_before = d["state_before"].get("discard_n")
        hand_after = d["state_after"].get("hand_n")
        discard_after = d["state_after"].get("discard_n")
        if None in (hand_before, discard_before, hand_after, discard_after):
            continue
        # net cards removed from hand beyond the 1 played-card itself, and cards newly
        # discarded (post-play) beyond the played card landing in the discard pile.
        events.append({
            "decision_index": k, "turn": d["turn"], "action_class": d["action_class"],
            "card_id": cid, "card_name": CARDS_BY_ID[cid].name if cid in CARDS_BY_ID else None,
            "hand_before": hand_before, "hand_after": hand_after,
            "discard_before": discard_before, "discard_after": discard_after,
            "hand_delta": hand_after - hand_before,
            "discard_delta": discard_after - discard_before,
        })
    return events


CRITICAL_SITUATION_FIELDS = ("our_active_prize_value", "our_active_damaged",
                              "retreat_available_this_decision", "bench_target_exists")


def critical_situations(decisions):
    """Reuses the EXACT 'critical situation' definition from session 20's V2_LADDER_AUDIT.md
    (2+-prize active, damaged, opponent lethal now, retreat legal, bench target exists),
    applied here to V6's loss corpus specifically rather than the whole-dataset aggregate."""
    out = []
    for k, d in enumerate(decisions):
        pv = d["our_active_prize_value"]
        threat = d["opp_threat"] or {}
        if (pv is not None and pv >= 2 and d["our_active_damaged"]
                and threat.get("lethal_now") and d["retreat_available_this_decision"]
                and d["bench_target_exists"]):
            retreated = "RETREAT" in d["chosen_option_types"]
            out.append({
                "decision_index": k, "turn": d["turn"], "retreated": retreated,
                "our_active_id": d["state_before"].get("active_id"),
                "our_active_hp": d["state_before"].get("active_hp"),
                "opp_best_attack_damage": threat.get("best_attack_damage"),
                "bench_ready_attackers": d["bench_ready_attackers"],
            })
    return out


def phantom_dive_usage(decisions):
    used_turns, available_turns = set(), set()
    for d in decisions:
        if PHANTOM_DIVE_ID in (d["available_attack_ids"] or []):
            available_turns.add(d["turn"])
        if PHANTOM_DIVE_ID in (d["chosen_attack_ids"] or []):
            used_turns.add(d["turn"])
    return sorted(available_turns), sorted(used_turns)


def main():
    games = load_games()
    losses = [g for g in games if g["result"] == "LOSS"]
    wins = [g for g in games if g["result"] == "WIN"]
    print(f"Loaded {len(games)} games: {len(wins)} wins, {len(losses)} losses")

    pd_missed_by_episode = {}
    pd_path = os.path.join(ROOT, "results", "phantom_dive_forensic_v6", "missed_ko_examples.csv")
    if os.path.exists(pd_path):
        with open(pd_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pd_missed_by_episode.setdefault(int(r["episode_id"]), []).append(r)

    loss_reports = []
    for g in losses:
        decs = g["decisions"]
        series = turn_trajectory(decs)
        decisive_turn = find_decisive_turn(series)
        first_behind = first_turn_deficit_at_least(series, 1)
        first_2plus = first_turn_deficit_at_least(series, 2)
        final_deficit = series[-1][3] if series else None

        mko = find_missed_knockouts(decs)
        confirmed_mko = [m for m in mko if m["evidence_level"] == "CONFIRMED"]

        pd_avail_turns, pd_used_turns = phantom_dive_usage(decs)
        pd_missed = pd_missed_by_episode.get(g["episode_id"], [])

        bl_events = bench_lock_events(decs)
        bl_events_annotated = [
            {**e, "eventually_played": bench_lock_ever_resolved(decs, e)} for e in bl_events
        ]
        bl_never_resolved = [e for e in bl_events_annotated if not e["eventually_played"]]

        sup_events = supporter_item_trace(decs)

        crit = critical_situations(decs)
        crit_stayed = [c for c in crit if not c["retreated"]]

        # Candidate "first bad decision" events, each tagged with (turn, decision_index,
        # category, description) -- earliest by (turn, decision_index) wins.
        candidates = []
        for m in confirmed_mko:
            candidates.append((m["turn"], m["decision_index"], "D_ACTIVE_SELECTION_MISSED_KO",
                                f"Confirmed missed active-Pokemon knockout: {m['description']}"))
        for pm in pd_missed:
            candidates.append((int(pm["turn"]), None, "B_PHANTOM_DIVE_ALLOCATION",
                                f"Phantom Dive misallocated 6 counters: actual={pm['v6_actual_allocation_by_slot']} "
                                f"(kos={pm['v6_actual_kos']}) vs optimal={pm['optimal_allocation_by_slot']} "
                                f"(kos={pm['optimal_kos']}, +{pm['prize_difference']} prize)"))
        for c in crit_stayed:
            candidates.append((c["turn"], c["decision_index"], "E_RETREAT_SURVIVAL",
                                f"Stayed active at {c['our_active_hp']}hp facing a lethal "
                                f"{c['opp_best_attack_damage']}dmg attack with retreat legal and "
                                f"{c['bench_ready_attackers']} ready bench attacker(s) available"))
        for e in bl_never_resolved:
            candidates.append((e["turn"], e["decision_index"], "L_BENCH_SPACE",
                                f"Bench at cap (5/5) while holding {e['hand_pokemon_names']} in "
                                f"hand; never played this game"))
        candidates.sort(key=lambda c: (c[0] if c[0] is not None else 999, c[1] if c[1] is not None else 999))
        first_bad = candidates[0] if candidates else None

        loss_reports.append({
            "episode_id": g["episode_id"],
            "opponent_archetype": g["deck_opp_archetype"],
            "opponent_score": g.get("opponent_current_score"),
            "went_first": g["went_first"],
            "n_turns": g["n_turns"],
            "turn_trajectory": series,
            "first_behind_turn": first_behind,
            "first_2plus_deficit_turn": first_2plus,
            "decisive_turn": decisive_turn,
            "final_deficit": final_deficit,
            "phantom_dive_available_turns": pd_avail_turns,
            "phantom_dive_used_turns": pd_used_turns,
            "confirmed_missed_kos": confirmed_mko,
            "phantom_dive_missed_events": pd_missed,
            "bench_lock_events": bl_events_annotated,
            "bench_lock_never_resolved": bl_never_resolved,
            "supporter_item_events": sup_events,
            "critical_situations": crit,
            "critical_situations_stayed": crit_stayed,
            "first_bad_decision": {
                "turn": first_bad[0], "decision_index": first_bad[1],
                "category": first_bad[2], "description": first_bad[3],
            } if first_bad else None,
            "all_candidate_bad_decisions": [
                {"turn": c[0], "decision_index": c[1], "category": c[2], "description": c[3]}
                for c in candidates
            ],
        })

    with open(os.path.join(OUT_DIR, "loss_reports.json"), "w", encoding="utf-8") as f:
        json.dump(loss_reports, f, indent=2, default=str)

    # -- Win vs loss aggregate behavioral comparison (Part 10) --
    def agg(gs, key_fn):
        vals = [key_fn(g) for g in gs]
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals)) if vals else None

    def game_attack_rate(g):
        decs = g["decisions"]
        avail = set(d["turn"] for d in decs if d["available_attack_ids"])
        chosen = set(d["turn"] for d in decs if d["chosen_attack_ids"])
        return (len(avail & chosen) / len(avail)) if avail else None

    def game_retreat_rate(g):
        decs = g["decisions"]
        avail = [d for d in decs if d["retreat_available_this_decision"]]
        chosen = [d for d in avail if "RETREAT" in d["chosen_option_types"]]
        return (len(chosen) / len(avail)) if avail else None

    def game_pd_conversion(g):
        eid = g["episode_id"]
        missed = pd_missed_by_episode.get(eid, [])
        avail_turns, used_turns = phantom_dive_usage(g["decisions"])
        return len(used_turns), len(missed)

    comparison = {}
    for label, gs in (("wins", wins), ("losses", losses)):
        pd_used_total = sum(game_pd_conversion(g)[0] for g in gs)
        pd_missed_total = sum(game_pd_conversion(g)[1] for g in gs)
        comparison[label] = {
            "n_games": len(gs),
            "mean_n_turns": agg(gs, lambda g: g["n_turns"]),
            "mean_n_decisions": agg(gs, lambda g: g["n_decisions"]),
            "mean_turn_attack_rate": agg(gs, game_attack_rate),
            "mean_retreat_rate_when_available": agg(gs, game_retreat_rate),
            "pct_went_first": agg(gs, lambda g: 1.0 if g["went_first"] else (0.0 if g["went_first"] is not None else None)),
            "phantom_dive_attacks_used_total": pd_used_total,
            "phantom_dive_missed_value_events_total": pd_missed_total,
            "mean_opponent_score": agg(gs, lambda g: g.get("opponent_current_score")),
            "mean_bench_lock_events": agg(gs, lambda g: len(bench_lock_events(g["decisions"]))),
            "mean_supporter_plays": agg(gs, lambda g: sum(1 for d in g["decisions"] if d["action_class"] == "PLAY_SUPPORTER")),
            "mean_item_plays": agg(gs, lambda g: sum(1 for d in g["decisions"] if d["action_class"] == "PLAY_ITEM")),
            "mean_energy_attach_plays": agg(gs, lambda g: sum(1 for d in g["decisions"] if d["action_class"] == "ATTACH_ENERGY")),
        }

    with open(os.path.join(OUT_DIR, "win_vs_loss_comparison.json"), "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, default=str)

    # -- Opponent-rating-banded loss breakdown (Part 11) --
    bands = [(0, 650), (650, 750), (750, 850), (850, 99999)]
    band_report = []
    for lo, hi in bands:
        in_band = [g for g in losses if g.get("opponent_current_score") is not None and lo <= g["opponent_current_score"] < hi]
        band_report.append({"band": f"{lo}-{hi}", "n_losses": len(in_band),
                             "episode_ids": [g["episode_id"] for g in in_band]})
    with open(os.path.join(OUT_DIR, "opponent_band_losses.json"), "w", encoding="utf-8") as f:
        json.dump(band_report, f, indent=2)

    print("Done. Wrote loss_reports.json, win_vs_loss_comparison.json, opponent_band_losses.json")
    for lr in loss_reports:
        print(lr["episode_id"], "decisive_turn=", lr["decisive_turn"], "first_bad=",
              lr["first_bad_decision"]["category"] if lr["first_bad_decision"] else None)


if __name__ == "__main__":
    main()
