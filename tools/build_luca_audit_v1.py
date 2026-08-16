"""Luca Episode Data Audit -- Part B: parse + analyze.

Reads the 70 already-pulled replay JSONs for Luca's current live submission
(55447414, score 1232.4 as of 2026-08-12, #1 on the pokemon-tcg-ai-battle
leaderboard) from data/luca_audit/replays/ and produces:
  - results/luca_audit/luca_games.csv          (one row per game, raw+derived)
  - results/luca_audit/luca_decisions.csv      (one row per Luca decision, RAW -- never discard)
  - results/luca_audit/luca_missed_knockouts.csv
  - results/luca_audit/luca_behavior_summary.json

Reuses, not reinvents: `categorize`/`_player_snapshot`/`check_missed_knockout`/
`find_missed_knockouts` ported verbatim from tools/kaggle_replay_forensic.py
(same engine-grounded logic already validated across 46 of our own ladder
games in session 17 -- 3 real bugs already caught and fixed there). Deck
extraction and archetype tagging reuse src/meta_analysis/episode_parser.py
and src/meta_analysis/archetype_signatures.py verbatim (same code that
labeled the 3,499-episode historical dataset).

Read-only: no agent/deck/submission changes.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()
import cg.api as api  # noqa: E402

from src.meta_analysis.episode_parser import _extract_deck, deck_hash  # noqa: E402
from src.meta_analysis.archetype_signatures import tag_deck  # noqa: E402

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
IN_DIR = os.path.join(ROOT, "data", "luca_audit")
REPLAY_DIR = os.path.join(IN_DIR, "replays")
OUT_DIR = os.path.join(ROOT, "results", "luca_audit")
os.makedirs(OUT_DIR, exist_ok=True)

LUCA_SUBMISSION_ID = 55447414

SELECT_CONTEXT_NAMES = {int(v): v.name for v in api.SelectContext}
OPTION_TYPE_NAMES = {int(v): v.name for v in api.OptionType}
ATTACKS_BY_ID = {a.attackId: a for a in api.all_attack()}
CARDS_BY_ID = {c.cardId: c for c in api.all_card_data()}

CATEGORY_BY_CONTEXT = {
    1: "EARLY_GAME_SETUP", 2: "BENCH_MANAGEMENT", 3: "ACTIVE_POKEMON_SELECTION",
    4: "ACTIVE_POKEMON_SELECTION", 5: "BENCH_MANAGEMENT", 6: "BENCH_MANAGEMENT",
    7: "RESOURCE_MANAGEMENT", 8: "RESOURCE_MANAGEMENT", 9: "RESOURCE_MANAGEMENT",
    10: "RESOURCE_MANAGEMENT", 11: "PRIZE_RACE", 12: "RESOURCE_MANAGEMENT",
    13: "TARGET_SELECTION", 14: "TARGET_SELECTION", 15: "TARGET_SELECTION",
    16: "RESOURCE_MANAGEMENT", 17: "RESOURCE_MANAGEMENT", 18: "BENCH_MANAGEMENT",
    19: "BENCH_MANAGEMENT", 20: "BENCH_MANAGEMENT", 21: "ENERGY_MANAGEMENT",
    22: "ENERGY_MANAGEMENT", 23: "ENERGY_MANAGEMENT", 24: "SEARCH_DECISION",
    25: "TARGET_SELECTION", 26: "ENERGY_MANAGEMENT", 27: "RESOURCE_MANAGEMENT",
    28: "ENERGY_MANAGEMENT", 29: "RESOURCE_MANAGEMENT", 30: "ENERGY_MANAGEMENT",
    31: "ENERGY_MANAGEMENT", 32: "ENERGY_MANAGEMENT", 33: "ENERGY_MANAGEMENT",
    34: "TIMING", 35: "ATTACK_SELECTION", 36: "ATTACK_SELECTION",
    37: "BENCH_MANAGEMENT", 38: "SEARCH_DECISION", 39: "TARGET_SELECTION",
    40: "TARGET_SELECTION", 41: "GOING_FIRST_SECOND", 42: "EARLY_GAME_SETUP",
    43: "RESOURCE_MANAGEMENT", 44: "RESOURCE_MANAGEMENT", 45: "RESOURCE_MANAGEMENT",
    46: "TIMING", 47: "RESOURCE_MANAGEMENT", 48: "RESOURCE_MANAGEMENT",
}
CATEGORY_BY_OPTION_TYPE = {
    0: "RESOURCE_MANAGEMENT", 3: "TARGET_SELECTION", 4: "RESOURCE_MANAGEMENT",
    5: "ENERGY_MANAGEMENT", 6: "ENERGY_MANAGEMENT", 7: "RESOURCE_MANAGEMENT",
    8: "ENERGY_MANAGEMENT", 9: "BENCH_MANAGEMENT", 10: "RESOURCE_MANAGEMENT",
    11: "RESOURCE_MANAGEMENT", 12: "RETREAT_SELECTION", 13: "ATTACK_SELECTION",
    14: "TIMING",
}


def categorize(context, chosen_option_types):
    if context is not None and context != 0 and context in CATEGORY_BY_CONTEXT:
        return CATEGORY_BY_CONTEXT[context]
    if context == 0:
        if not chosen_option_types:
            return "TIMING"
        for t in chosen_option_types:
            if t in CATEGORY_BY_OPTION_TYPE:
                return CATEGORY_BY_OPTION_TYPE[t]
    return "UNKNOWN"


def _player_snapshot(cur, idx):
    if not cur:
        return {}
    pl = cur["players"][idx]
    active_raw = pl.get("active") or []
    active0 = active_raw[0] if active_raw and active_raw[0] is not None else None
    bench_raw = [b for b in (pl.get("bench") or []) if b is not None]
    return {
        "turn": cur.get("turn"),
        "active_id": active0.get("id") if active0 else None,
        "active_hp": active0.get("hp") if active0 else None,
        "active_maxhp": active0.get("maxHp") if active0 else None,
        "active_energy_n": len(active0.get("energies") or []) if active0 else 0,
        "bench_n": len([b for b in bench_raw]),
        "hand_n": pl.get("handCount"),
        "prize_n": len(pl.get("prize") or []),
        "deck_n": pl.get("deckCount"),
        "discard_n": len(pl.get("discard") or []),
    }


def check_missed_knockout(decision):
    if decision["select_context"] != 0 or not decision["available_attack_ids"]:
        return None
    opp = decision["opp_before"]
    opp_hp = opp.get("active_hp")
    opp_id = opp.get("active_id")
    if opp_hp is None or opp_id is None or opp_hp <= 0:
        return None
    opp_card = CARDS_BY_ID.get(opp_id)
    our_active_id = decision["state_before"].get("active_id")
    our_card = CARDS_BY_ID.get(our_active_id) if our_active_id else None
    our_energy_type = our_card.energyType if our_card else None
    opp_has_ability = bool(opp_card and opp_card.skills)
    _NONSTANDARD_KEYWORDS = ("bench", "coin", "flip", "counter", "instead", "unless",
                              "for each", "any way you like", "prevent", "discard")
    lethal_certain, lethal_uncertain = [], []
    for aid in decision["available_attack_ids"]:
        atk = ATTACKS_BY_ID.get(aid)
        if atk is None:
            continue
        dmg = atk.damage
        if dmg <= 0 or dmg < opp_hp:
            continue
        resisted = bool(opp_card and opp_card.resistance is not None and opp_card.resistance == our_energy_type)
        nonstandard_text = any(kw in (atk.text or "").lower() for kw in _NONSTANDARD_KEYWORDS)
        if resisted or opp_has_ability or nonstandard_text:
            lethal_uncertain.append((aid, atk.name, dmg))
        else:
            lethal_certain.append((aid, atk.name, dmg))
    if not lethal_certain and not lethal_uncertain:
        return None
    chosen_lethal = any(aid in [x[0] for x in lethal_certain] for aid in decision["chosen_attack_ids"])
    if chosen_lethal:
        return None
    if lethal_certain:
        return {"evidence_level": "CONFIRMED",
                "description": f"Non-resisted lethal attack(s) available ({lethal_certain}) but not chosen: {decision['chosen_option_types']}"}
    return {"evidence_level": "POSSIBLE",
            "description": f"Lethal-by-base-damage attack(s) available but uncertain (ability/resist/nonstandard text) and not chosen: {lethal_uncertain}"}


def find_missed_knockouts(decisions):
    results = []
    n = len(decisions)
    for k, dec in enumerate(decisions):
        ko = check_missed_knockout(dec)
        if ko is None:
            continue
        opp_id = dec["opp_before"].get("active_id")
        turn0 = dec["turn"]
        resolved, target_removed = False, False
        j = k
        while j < n and decisions[j]["turn"] == turn0:
            d2 = decisions[j]
            if d2["opp_before"].get("active_id") == opp_id and (d2["opp_before"].get("active_hp") or 0) <= 0 and d2["opp_before"].get("active_hp") is not None:
                resolved = True
                break
            if d2["opp_after"].get("active_id") == opp_id and (d2["opp_after"].get("active_hp") or 0) <= 0 and d2["opp_after"].get("active_hp") is not None:
                resolved = True
                break
            if d2["opp_after"].get("active_id") is None and d2["opp_before"].get("active_id") in (opp_id, None):
                resolved = True
                break
            if d2["opp_after"].get("active_id") not in (None, opp_id):
                target_removed = True
                break
            if j > k and d2["opp_before"].get("active_id") not in (None, opp_id):
                target_removed = True
                break
            j += 1
        if not resolved:
            results.append({
                "episode_id": dec["episode_id"], "decision_index": dec["decision_index"], "turn": turn0,
                "evidence_level": ko["evidence_level"] if not target_removed else "POSSIBLE",
                "target_removed_via_switch": target_removed, "description": ko["description"],
            })
    return results


def parse_episode(eid, ep_meta):
    rp = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
    if not os.path.exists(rp):
        return None
    with open(rp, encoding="utf-8") as f:
        d = json.load(f)

    luca_agent = next(a for a in ep_meta["agents"] if a["submissionId"] == LUCA_SUBMISSION_ID)
    opp_agent = next(a for a in ep_meta["agents"] if a["submissionId"] != LUCA_SUBMISSION_ID)
    idx = luca_agent.get("index", 0)
    opp_idx = 1 - idx
    steps = d["steps"]
    rewards = d["rewards"]
    our_r, opp_r = rewards[idx], rewards[opp_idx]
    statuses = d.get("statuses", [None, None])
    if our_r == 1 and opp_r == -1:
        result = "WIN"
    elif our_r == -1 and opp_r == 1:
        result = "LOSS"
    elif our_r == 0 and opp_r == 0:
        result = "DRAW"
    else:
        result = "ERROR_OR_TIMEOUT"

    deck_luca, src_luca = _extract_deck(steps, idx)
    deck_opp, src_opp = _extract_deck(steps, opp_idx)
    arch_luca, _, _ = tag_deck(deck_luca) if deck_luca else ("MISSING", 0, [])
    arch_opp, _, _ = tag_deck(deck_opp) if deck_opp else ("MISSING", 0, [])

    first_player = None
    for step in steps:
        for p in (0, 1):
            cur = step[p]["observation"].get("current")
            if cur and cur.get("firstPlayer") not in (None, -1):
                first_player = cur["firstPlayer"]

    active_rows = [i for i, s in enumerate(steps) if s[idx]["status"] == "ACTIVE"]
    decisions = []
    for k, row_i in enumerate(active_rows):
        prev_obs = steps[row_i - 1][idx]["observation"] if row_i - 1 >= 0 else steps[row_i][idx]["observation"]
        cur_obs = steps[row_i][idx]["observation"]
        select = prev_obs.get("select")
        chosen_action = steps[row_i][idx]["action"]
        state_before = _player_snapshot(prev_obs.get("current"), idx)
        opp_before = _player_snapshot(prev_obs.get("current"), opp_idx)
        state_after = _player_snapshot(cur_obs.get("current"), idx)
        opp_after = _player_snapshot(cur_obs.get("current"), opp_idx)
        options = select.get("option", []) if select else []
        context = select.get("context") if select else None
        chosen_types, chosen_attack_ids = [], []
        if isinstance(chosen_action, list):
            for ci in chosen_action:
                if isinstance(ci, int) and 0 <= ci < len(options):
                    o = options[ci]
                    if isinstance(o, dict):
                        chosen_types.append(o.get("type"))
                        if o.get("type") == 13 and o.get("attackId") is not None:
                            chosen_attack_ids.append(o["attackId"])
        category = categorize(context, chosen_types)
        option_type_counts = {}
        available_attack_ids = []
        for o in options:
            if not isinstance(o, dict):
                continue
            t = o.get("type")
            option_type_counts[t] = option_type_counts.get(t, 0) + 1
            if t == 13 and o.get("attackId") is not None:
                available_attack_ids.append(o["attackId"])
        decisions.append({
            "episode_id": eid, "decision_index": k, "row_index": row_i,
            "turn": state_before.get("turn"),
            "select_context": context,
            "select_context_name": SELECT_CONTEXT_NAMES.get(context, f"UNKNOWN({context})") if context is not None else None,
            "n_options": len(options),
            "option_type_counts": option_type_counts,
            "available_attack_ids": available_attack_ids,
            "chosen_action": chosen_action,
            "chosen_option_types": [OPTION_TYPE_NAMES.get(t, str(t)) for t in chosen_types],
            "chosen_attack_ids": chosen_attack_ids,
            "category": category,
            "state_before": state_before, "opp_before": opp_before,
            "state_after": state_after, "opp_after": opp_after,
        })

    return {
        "episode_id": eid,
        "create_time": ep_meta.get("createTime"),
        "opponent_team_id": opp_agent["teamId"],
        "opponent_team_name": opp_agent["teamName"],
        "result": result,
        "luca_index": idx,
        "went_first": (first_player == idx) if first_player is not None else None,
        "n_steps": len(steps),
        "n_turns": max((s[idx]["observation"].get("current") or {}).get("turn", 0) for s in steps if s[idx]["observation"].get("current")) if any(s[idx]["observation"].get("current") for s in steps) else None,
        "deck_luca_hash": deck_hash(deck_luca) if deck_luca else None,
        "deck_luca_archetype": arch_luca,
        "deck_luca_source": src_luca,
        "deck_opp_hash": deck_hash(deck_opp) if deck_opp else None,
        "deck_opp_archetype": arch_opp,
        "deck_opp_source": src_opp,
        "n_decisions": len(decisions),
        "decisions": decisions,
    }


def main():
    with open(os.path.join(IN_DIR, "luca_episodes_raw.json"), encoding="utf-8") as f:
        eps_meta = json.load(f)
    with open(os.path.join(IN_DIR, "opponent_ratings_raw.json"), encoding="utf-8") as f:
        opp_ratings = {r["team_id"]: r for r in json.load(f)}

    games = []
    all_decisions = []
    all_missed_ko = []
    n_validation_excluded = 0
    for e in eps_meta:
        eid = e["id"]
        if e.get("type") == "EPISODE_TYPE_VALIDATION":
            # Kaggle's own pre-matchmaking self-play check (both slots = Luca's own
            # submission) -- confirmed by direct inspection, same pattern found for our
            # own submission in session 16. Not a real ladder game, excluded from stats.
            n_validation_excluded += 1
            continue
        parsed = parse_episode(eid, e)
        if parsed is None:
            continue
        mko = find_missed_knockouts(parsed["decisions"])
        all_missed_ko.extend(mko)
        parsed["missed_ko_confirmed"] = sum(1 for m in mko if m["evidence_level"] == "CONFIRMED")
        parsed["missed_ko_possible"] = sum(1 for m in mko if m["evidence_level"] == "POSSIBLE")

        decs = parsed["decisions"]
        retreat_avail = sum(1 for d in decs if d["category"] == "RETREAT_SELECTION" or (d["select_context_name"] in ("SWITCH",) ))
        retreat_chosen = sum(1 for d in decs if "RETREAT" in d["chosen_option_types"])
        attack_avail_decisions = [d for d in decs if d["available_attack_ids"]]
        attack_chosen = sum(1 for d in attack_avail_decisions if d["chosen_attack_ids"])
        # Per-TURN attack rate (cleaner than per-decision: a turn often revisits MAIN
        # multiple times -- play energy/trainer first, THEN attack -- so per-decision
        # conversion understates true aggression by counting each pre-attack visit as
        # a separate "declined" instance; per-turn asks "did an attack happen at all
        # this turn, given one was legal at some point this turn").
        turns_with_attack_avail = set(d["turn"] for d in attack_avail_decisions)
        turns_with_attack_chosen = set(d["turn"] for d in decs if d["chosen_attack_ids"])
        turn_attack_rate = (len(turns_with_attack_avail & turns_with_attack_chosen) / len(turns_with_attack_avail)) if turns_with_attack_avail else None
        # prize-race trajectory: (our_prize, opp_prize) remaining-unclaimed counts at
        # each MAIN decision. LOWER remaining count = closer to winning (you've taken
        # more prizes), so "deficit" (being behind) = our_remaining - opp_remaining > 0,
        # NOT opp - our (verified against the sign of avg_final_prize_margin_wins/losses
        # below during dev -- an earlier version of this script had this backwards).
        prize_points = [(d["state_before"]["prize_n"], d["opp_before"]["prize_n"]) for d in decs if d["state_before"].get("prize_n") is not None]
        max_deficit = max((us - op for us, op in prize_points), default=0)
        final_margin = (prize_points[-1][0] - prize_points[-1][1]) if prize_points else None
        comeback = bool(prize_points) and max_deficit >= 2 and parsed["result"] == "WIN"

        opp_rating_info = opp_ratings.get(parsed["opponent_team_id"], {})
        row = {
            "episode_id": eid,
            "create_time": parsed["create_time"],
            "opponent_team_id": parsed["opponent_team_id"],
            "opponent_team_name": parsed["opponent_team_name"],
            "opponent_current_score": opp_rating_info.get("current_public_score"),
            "result": parsed["result"],
            "went_first": parsed["went_first"],
            "n_turns": parsed["n_turns"],
            "n_steps": parsed["n_steps"],
            "n_decisions": parsed["n_decisions"],
            "deck_luca_hash": parsed["deck_luca_hash"],
            "deck_luca_archetype": parsed["deck_luca_archetype"],
            "deck_opp_hash": parsed["deck_opp_hash"],
            "deck_opp_archetype": parsed["deck_opp_archetype"],
            "retreat_available_decisions": retreat_avail,
            "retreat_chosen": retreat_chosen,
            "attack_available_decisions": len(attack_avail_decisions),
            "attack_chosen_when_available": attack_chosen,
            "turns_with_attack_available": len(turns_with_attack_avail),
            "turn_attack_rate": turn_attack_rate,
            "missed_ko_confirmed": parsed["missed_ko_confirmed"],
            "missed_ko_possible": parsed["missed_ko_possible"],
            "max_prize_deficit_faced": max_deficit,
            "final_prize_margin": final_margin,
            "comeback_from_2plus_deficit": comeback,
        }
        games.append(row)
        for d in decs:
            all_decisions.append({
                "episode_id": eid, "decision_index": d["decision_index"], "turn": d["turn"],
                "select_context_name": d["select_context_name"], "n_options": d["n_options"],
                "category": d["category"],
                "chosen_option_types": ";".join(d["chosen_option_types"]),
                "n_available_attacks": len(d["available_attack_ids"]),
                "n_chosen_attacks": len(d["chosen_attack_ids"]),
                "our_active_id": d["state_before"].get("active_id"),
                "our_active_hp": d["state_before"].get("active_hp"),
                "our_active_maxhp": d["state_before"].get("active_maxhp"),
                "our_bench_n": d["state_before"].get("bench_n"),
                "our_prize_n": d["state_before"].get("prize_n"),
                "opp_active_id": d["opp_before"].get("active_id"),
                "opp_active_hp": d["opp_before"].get("active_hp"),
                "opp_prize_n": d["opp_before"].get("prize_n"),
                "result": parsed["result"],
            })

    # --- write raw, per-decision CSV (never discard) ---
    with open(os.path.join(OUT_DIR, "luca_decisions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_decisions[0].keys()))
        w.writeheader()
        w.writerows(all_decisions)

    with open(os.path.join(OUT_DIR, "luca_games.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(games[0].keys()))
        w.writeheader()
        w.writerows(games)

    with open(os.path.join(OUT_DIR, "luca_missed_knockouts.csv"), "w", newline="", encoding="utf-8") as f:
        if all_missed_ko:
            w = csv.DictWriter(f, fieldnames=list(all_missed_ko[0].keys()))
            w.writeheader()
            w.writerows(all_missed_ko)
        else:
            f.write("no_missed_knockouts_found\n")

    # --- aggregate summary ---
    n = len(games)
    wins = sum(1 for g in games if g["result"] == "WIN")
    losses = sum(1 for g in games if g["result"] == "LOSS")
    draws = sum(1 for g in games if g["result"] == "DRAW")
    errs = sum(1 for g in games if g["result"] == "ERROR_OR_TIMEOUT")
    first_games = [g for g in games if g["went_first"] is True]
    second_games = [g for g in games if g["went_first"] is False]

    def wr(gs):
        decisive = [g for g in gs if g["result"] in ("WIN", "LOSS")]
        return (sum(1 for g in decisive if g["result"] == "WIN") / len(decisive)) if decisive else None

    arch_counter = Counter(g["deck_luca_archetype"] for g in games)
    opp_arch_counter = Counter(g["deck_opp_archetype"] for g in games)
    opp_arch_wr = {}
    for a in opp_arch_counter:
        gs = [g for g in games if g["deck_opp_archetype"] == a and g["result"] in ("WIN", "LOSS")]
        if gs:
            opp_arch_wr[a] = {"n": len(gs), "luca_win_rate": sum(1 for g in gs if g["result"] == "WIN") / len(gs)}

    total_retreat_avail = sum(g["retreat_available_decisions"] for g in games)
    total_retreat_chosen = sum(g["retreat_chosen"] for g in games)
    total_attack_avail = sum(g["attack_available_decisions"] for g in games)
    total_attack_chosen = sum(g["attack_chosen_when_available"] for g in games)
    total_decisions = len(all_decisions)

    losses_games = [g for g in games if g["result"] == "LOSS"]
    wins_games = [g for g in games if g["result"] == "WIN"]

    summary = {
        "target_submission_id": LUCA_SUBMISSION_ID,
        "leaderboard_score_at_pull_time": 1232.4,
        "validation_episodes_excluded": n_validation_excluded,
        "games_total": n,
        "wins": wins, "losses": losses, "draws": draws, "errors_or_timeouts": errs,
        "win_rate_decisive": wr(games),
        "win_rate_going_first": wr(first_games), "n_going_first": len(first_games),
        "win_rate_going_second": wr(second_games), "n_going_second": len(second_games),
        "deck_archetypes_played": dict(arch_counter),
        "opponent_archetype_distribution": dict(opp_arch_counter),
        "win_rate_by_opponent_archetype": opp_arch_wr,
        "retreat_rate_per_decision": total_retreat_chosen / total_decisions if total_decisions else None,
        "retreat_rate_when_available": total_retreat_chosen / total_retreat_avail if total_retreat_avail else None,
        "attack_conversion_rate_per_decision": total_attack_chosen / total_attack_avail if total_attack_avail else None,
        "attack_conversion_rate_per_turn": (sum(g["turn_attack_rate"] * g["turns_with_attack_available"] for g in games if g["turn_attack_rate"] is not None) / sum(g["turns_with_attack_available"] for g in games if g["turn_attack_rate"] is not None)) if any(g["turn_attack_rate"] is not None for g in games) else None,
        "missed_ko_confirmed_total": sum(g["missed_ko_confirmed"] for g in games),
        "missed_ko_possible_total": sum(g["missed_ko_possible"] for g in games),
        "avg_turns_all": sum(g["n_turns"] or 0 for g in games) / n if n else None,
        "avg_turns_wins": sum(g["n_turns"] or 0 for g in wins_games) / len(wins_games) if wins_games else None,
        "avg_turns_losses": sum(g["n_turns"] or 0 for g in losses_games) / len(losses_games) if losses_games else None,
        # NOTE on sign convention: prize_n = UNCLAIMED prizes remaining (lower = closer to
        # winning). "deficit"/"margin" below = our_remaining - opp_remaining, so POSITIVE
        # means Luca was BEHIND (had more prizes left to take than the opponent) and
        # NEGATIVE means Luca was AHEAD.
        "comebacks_from_2plus_prize_deficit": sum(1 for g in games if g["comeback_from_2plus_deficit"]),
        "games_where_luca_faced_2plus_prize_deficit": sum(1 for g in games if g["max_prize_deficit_faced"] >= 2),
        "avg_max_prize_deficit_faced_wins": sum(g["max_prize_deficit_faced"] for g in wins_games) / len(wins_games) if wins_games else None,
        "avg_max_prize_deficit_faced_losses": sum(g["max_prize_deficit_faced"] for g in losses_games) / len(losses_games) if losses_games else None,
        "avg_final_prize_margin_wins_positive_means_behind": sum(g["final_prize_margin"] or 0 for g in wins_games) / len(wins_games) if wins_games else None,
        "avg_final_prize_margin_losses_positive_means_behind": sum(g["final_prize_margin"] or 0 for g in losses_games) / len(losses_games) if losses_games else None,
        "unique_opponents_faced": len(set(g["opponent_team_id"] for g in games)),
        "n_games_analyzed_for_opponent_rating": sum(1 for g in games if g["opponent_current_score"] not in (None, "")),
    }
    with open(os.path.join(OUT_DIR, "luca_behavior_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
