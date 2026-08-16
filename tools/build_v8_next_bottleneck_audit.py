"""V8 Next-Bottleneck Audit (Session 29, Prompt "V8 NEXT BOTTLENECK AUDIT").

Read-only forensic analysis of V8's real Kaggle ladder replays. No code, weight,
deck, or submission changes; no V9. Builds on top of the already-pulled V7/V8
replay data (data/{v7,v8}_ladder_audit/) and the already-validated shared parser
(src/meta_analysis/ladder_behavior_audit.py::parse_episode) -- reused unchanged,
not reimplemented, so results stay comparable to session 28's audit.

New analysis this session (not covered by any prior tool):
  1. Per-turn Board-State-Value-Delta trajectory (sum of our own Active+Bench HP
     minus the opponent's, computed only from fields the acting player can see)
     and a "decisive turn" detector -- the first turn after which the delta never
     returns to >=0 for the rest of the game. This is the Part-10-mandated
     ALTERNATIVE tempo metric, built specifically BECAUSE the full-replay-trace
     prize-economy tool was found broken in session 28 and must not be reused as
     ground truth here.
  2. Serial-tracked (cg.api's own per-Pokemon `serial` field, stable across
     evolution and the whole game) evolution-pipeline and energy-stranding
     analysis for the Dreepy(119)->Drakloak(120)->Dragapult ex(121) line.
  3. Loss taxonomy (categories A-M) driven by the decisive-turn detector plus
     the decision-level signals parse_episode already computes (missed-KO flags,
     opponent lethal-threat flags, bench-ready-attacker counts, action classes).
  4. Matchup and opponent-rating-band tables (aggregated from the already-pulled
     per-game data, v8_games.csv-equivalent fields recomputed here to stay
     self-contained).

Every derived claim is FACT (directly measured) or HYPOTHESIS (plausible
inference); ambiguous/undeterminable cases are left UNCLASSIFIED rather than
forced into a category, per standing project process rules.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict

from src.meta_analysis.ladder_behavior_audit import (
    parse_episode, CARDS_BY_ID, ATTACKS_BY_ID, _can_pay,
)

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
OUT_DIR = os.path.join(ROOT, "results", "v8_next_bottleneck_audit")
os.makedirs(OUT_DIR, exist_ok=True)

PHANTOM_DIVE_ID = 154
DREEPY_ID, DRAKLOAK_ID, DRAGAPULT_EX_ID = 119, 120, 121

TARGETS = {
    "v7": {"submission_id": 55478172,
           "replay_dir": os.path.join(ROOT, "data", "v7_ladder_audit", "replays"),
           "episodes_file": os.path.join(ROOT, "data", "v7_ladder_audit", "v7_episodes_raw.json")},
    "v8": {"submission_id": 55482268,
           "replay_dir": os.path.join(ROOT, "data", "v8_ladder_audit", "replays"),
           "episodes_file": os.path.join(ROOT, "data", "v8_ladder_audit", "v8_episodes_raw.json")},
}


def load_parsed(label):
    cfg = TARGETS[label]
    with open(cfg["episodes_file"], encoding="utf-8") as f:
        eps_meta = json.load(f)
    ratings_path = os.path.join(os.path.dirname(cfg["episodes_file"]), "opponent_ratings_raw.json")
    rating_by_team = {}
    if os.path.exists(ratings_path):
        with open(ratings_path, encoding="utf-8") as f:
            for r in json.load(f):
                try:
                    rating_by_team[r["team_id"]] = float(r["current_public_score"])
                except (TypeError, ValueError, KeyError):
                    pass
    parsed = []
    for e in eps_meta:
        if e.get("type") == "EPISODE_TYPE_VALIDATION":
            continue
        eid = e["id"]
        p = parse_episode(eid, e, cfg["replay_dir"], cfg["submission_id"], label)
        if p is None:
            continue
        p["opponent_current_score"] = rating_by_team.get(p.get("opponent_team_id"))
        parsed.append(p)
    return parsed


# ---------------------------------------------------------------------------
# 1. Serial-level raw extraction (adds `serial` + `preEvolution`, which the
#    shared parser's _player_snapshot does not capture) -- needed for the
#    evolution-pipeline and energy-stranding analysis.
# ---------------------------------------------------------------------------

def extended_own_timeline(eid, replay_dir, idx):
    rp = os.path.join(replay_dir, f"episode-{eid}-replay.json")
    with open(rp, encoding="utf-8") as f:
        d = json.load(f)
    steps = d["steps"]
    active_rows = [i for i, s in enumerate(steps) if s[idx]["status"] == "ACTIVE"]
    timeline = []
    for row_i in active_rows:
        obs = steps[row_i][idx]["observation"]
        cur = obs.get("current")
        if not cur:
            continue
        pl = cur["players"][idx]
        turn = cur.get("turn")
        active_raw = pl.get("active") or []
        active0 = active_raw[0] if active_raw and active_raw[0] is not None else None
        bench_raw = [b for b in (pl.get("bench") or []) if b is not None]
        pieces = []
        if active0:
            pieces.append({"serial": active0.get("serial"), "id": active0.get("id"),
                            "hp": active0.get("hp"), "energies": list(active0.get("energies") or []),
                            "preEvolution": list(active0.get("preEvolution") or []), "zone": "active"})
        for b in bench_raw:
            pieces.append({"serial": b.get("serial"), "id": b.get("id"),
                            "hp": b.get("hp"), "energies": list(b.get("energies") or []),
                            "preEvolution": list(b.get("preEvolution") or []), "zone": "bench"})
        timeline.append({"turn": turn, "row_index": row_i, "pieces": pieces})
    return timeline


def analyze_evolution_and_energy(eid, replay_dir, idx):
    """Serial-indexed: for every physical Pokemon that was ever Dreepy/Drakloak,
    find its full turn-by-turn id/energy history, whether it ever reached
    Dragapult ex, and whether it disappeared (KO'd/discarded) while still
    holding attached energy and not yet at ex stage."""
    timeline = extended_own_timeline(eid, replay_dir, idx)
    by_serial = defaultdict(list)  # serial -> list of (turn, id, hp, energy_count)
    last_turn_seen_serial = {}
    for row in timeline:
        seen_this_row = set()
        for p in row["pieces"]:
            s = p["serial"]
            if s is None:
                continue
            by_serial[s].append((row["turn"], p["id"], p["hp"], len(p["energies"])))
            seen_this_row.add(s)
        last_turn_seen_serial[row["turn"]] = seen_this_row

    all_turns_sorted = sorted(set(row["turn"] for row in timeline if row["turn"] is not None))
    last_game_turn = all_turns_sorted[-1] if all_turns_sorted else None

    lines = []
    first_dragapult_ex_turn = None
    for serial, hist in by_serial.items():
        ids_seen = [h[1] for h in hist]
        if DREEPY_ID not in ids_seen and DRAKLOAK_ID not in ids_seen and DRAGAPULT_EX_ID not in ids_seen:
            continue  # not part of the Dreepy line at all
        first_turn = hist[0][0]
        first_energy_turn = next((h[0] for h in hist if h[3] > 0), None)
        reached_ex = DRAGAPULT_EX_ID in ids_seen
        reached_drakloak = DRAKLOAK_ID in ids_seen
        last_turn, last_id, last_hp, last_energy = hist[-1]
        # "disappeared" = this serial is absent from every subsequent active-row's
        # piece set, and the game continued past its last-seen turn (i.e. it did
        # not simply persist to game end).
        disappeared_early = (last_turn != last_game_turn) and last_hp is not None and last_hp <= 0
        # (hp<=0 is the direct engine signal for a KO'd piece still visible on the
        # KO'ing row, consistent with session 23's finding that KOs are visible
        # in-place before removal; if the last recorded hp is >0 but the serial
        # simply stops appearing before game end, treat as UNCLEAR, not KO'd.)
        vanished_unclear = (last_turn != last_game_turn) and not (last_hp is not None and last_hp <= 0)
        energy_stranded = (not reached_ex) and first_energy_turn is not None and (disappeared_early or vanished_unclear)
        if reached_ex and first_dragapult_ex_turn is None:
            first_dragapult_ex_turn = first_turn if ids_seen[0] == DRAGAPULT_EX_ID else next(
                h[0] for h in hist if h[1] == DRAGAPULT_EX_ID)
        lines.append({
            "episode_id": eid, "serial": serial, "first_turn": first_turn,
            "first_energy_turn": first_energy_turn, "reached_drakloak": reached_drakloak,
            "reached_dragapult_ex": reached_ex, "last_turn_seen": last_turn,
            "last_id_seen": last_id, "last_hp_seen": last_hp,
            "disappeared_early_ko": disappeared_early,
            "vanished_unclear": vanished_unclear,
            "energy_stranded_pre_ex": energy_stranded,
        })
    return lines, first_dragapult_ex_turn


# ---------------------------------------------------------------------------
# 2. Board-State-Value-Delta trajectory + decisive-turn detector
# ---------------------------------------------------------------------------

def board_value(snapshot):
    hp = snapshot.get("active_hp") or 0
    bench_hp = sum((b.get("hp") or 0) for b in (snapshot.get("bench_detail") or []))
    return hp + bench_hp


def decisive_turn_from_board_delta(decisions):
    """Returns (decisive_turn, trajectory) where decisive_turn is the turn of
    the first decision after which board_delta (ours - opponent's) never
    returns to >=0 for the remainder of the game. None if it never goes
    decisively/permanently negative (close game or we stayed ahead)."""
    traj = []
    for d in decisions:
        if d["turn"] is None:
            continue
        delta = board_value(d["state_before"]) - board_value(d["opp_before"])
        traj.append((d["turn"], d["decision_index"], delta))
    if not traj:
        return None, traj
    decisive_turn = None
    for i, (turn, idx_, delta) in enumerate(traj):
        if delta < 0:
            rest = [t[2] for t in traj[i:]]
            if all(v < 0 for v in rest):
                decisive_turn = turn
                break
    return decisive_turn, traj


def decisive_turn_from_prize_margin(decisions):
    """Same 'never recovers' logic applied to the decision-snapshot prize
    trajectory (our_prize_n - opp_prize_n; positive = we are BEHIND, matching
    the sign convention of the already-existing 'final_prize_margin_positive_
    means_behind' field). Labeled a lower-bound/directional signal per session
    28's finding about the prize-tracking tool family -- decision-snapshot
    (this one) was NOT the broken one, the full-replay-trace blend was."""
    traj = []
    for d in decisions:
        if d["turn"] is None:
            continue
        ours = d["state_before"].get("prize_n")
        opp = d["opp_before"].get("prize_n")
        if ours is None or opp is None:
            continue
        traj.append((d["turn"], ours - opp))
    if not traj:
        return None, traj
    decisive_turn = None
    for i, (turn, margin) in enumerate(traj):
        if margin > 0:
            rest = [t[1] for t in traj[i:]]
            if all(v > 0 for v in rest):
                decisive_turn = turn
                break
    return decisive_turn, traj


# ---------------------------------------------------------------------------
# 3. Loss taxonomy classifier
#
# Redesigned after an initial pass over-flagged nearly every loss into nearly
# every category (documented, not hidden, in the report's methodology
# section): the bug was per-DECISION scanning across the WHOLE game, which
# treats normal turn-1/2 "haven't attached energy yet" as "active stranded"
# and double-counts multi-decision turns where an earlier MAIN sub-decision
# in a turn precedes the turn's real terminal choice. Fixed by (a) collapsing
# to one TERMINAL decision per turn (last MAIN decision with that turn
# number), and (b) requiring temporal proximity to the decisive turn (the
# earliest point after which the game was never again winnable, per the
# board-value/prize trajectories) rather than flagging any occurrence
# anywhere in a 8-24 turn game. This directly follows the phase prompt's own
# Part 1 instruction: "find the earliest repeatable decision pattern," not
# "find every occurrence of every pattern."
# ---------------------------------------------------------------------------

CATEGORY_LABELS = {
    "A": "Failed attack / wrong attack",
    "B": "Failed KO despite available lethal",
    "C": "Bad target selection",
    "D": "Failed retreat (declined available beneficial retreat)",
    "E": "Unnecessary retreat",
    "F": "Energy starvation",
    "G": "Active stranded / no attacker",
    "H": "Bench/evolution development failure (Dragapult ex never came online)",
    "I": "Opponent threat not answered (threat unaddressed AND active subsequently lost)",
    "J": "Prize-race mistake",
    "K": "Matchup-specific structural weakness / total shutout, no single flagged decision",
    "L": "Random / unclear",
    "M": "Other",
}


def terminal_decisions_by_turn(decisions):
    by_turn = {}
    for d in decisions:
        if d["select_context_name"] != "MAIN" or d["turn"] is None:
            continue
        by_turn[d["turn"]] = d  # last one wins -- decisions are chronological
    return by_turn


def classify_loss(game, decisions, board_traj, board_decisive_turn, prize_decisive_turn,
                   evo_lines, first_ex_turn, missed_kos):
    """Returns (primary_tags, detail). Looks specifically at/near the decisive
    turn (board-value delta going permanently negative, cross-checked against
    the prize-margin trajectory) rather than scanning the whole game, so at
    most a small ordered set of tags results per loss -- the earliest
    repeatable pattern, not every pattern present anywhere in the replay."""
    n_turns = game.get("n_turns") or 0
    by_turn = terminal_decisions_by_turn(decisions)
    decisive_turn = board_decisive_turn if board_decisive_turn is not None else prize_decisive_turn
    # window: the decisive turn itself and the turn immediately before it (the
    # decision that plausibly caused the slip), or the last 3 turns if no
    # decisive turn could be pinned down at all.
    if decisive_turn is not None:
        window_turns = [t for t in (decisive_turn - 1, decisive_turn) if t in by_turn]
    else:
        all_t = sorted(by_turn.keys())
        window_turns = all_t[-3:] if all_t else []

    tags = []

    confirmed_misses = [m for m in missed_kos
                         if m["evidence_level"] == "CONFIRMED" and
                         (decisive_turn is None or int(m["turn"]) <= decisive_turn)]
    if confirmed_misses:
        tags.append(("B", "HIGH", f"CONFIRMED missed-KO at/before the decisive turn "
                                   f"(turn {confirmed_misses[0]['turn']})"))

    if first_ex_turn is None:
        tags.append(("H", "HIGH", f"Dragapult ex never appeared on board this game "
                                   f"({n_turns}-turn game)"))
    elif decisive_turn is not None and first_ex_turn > decisive_turn:
        tags.append(("H", "MEDIUM", f"Dragapult ex first appeared turn {first_ex_turn}, "
                                     f"AFTER the game had already decisively slipped (turn {decisive_turn})"))

    for t in window_turns:
        d = by_turn[t]
        threat = d.get("opp_threat") or {}
        has_attack = bool(d["available_attack_ids"])
        retreated = "RETREAT" in (d["chosen_option_types"] or [])
        attacked = bool(d["chosen_attack_ids"])
        if not has_attack and d["bench_ready_attackers"] == 0 and d["state_before"].get("active_id") is not None:
            tags.append(("G", "MEDIUM", f"turn {t}: no legal attack and no energy-ready bench "
                                         "attacker at/near the decisive turn"))
        if threat.get("lethal_now") and d["retreat_available_this_decision"] and \
                d["bench_ready_attackers"] > 0 and not retreated and not attacked:
            tags.append(("D", "MEDIUM", f"turn {t}: confirmed lethal threat + ready bench + retreat "
                                         "legal, but neither retreat nor a winning attack was taken"))
        if threat.get("lethal_now") and not retreated and not attacked:
            # our active subsequently lost? check next own decision's active_id/hp
            idx_in_list = decisions.index(d)
            lost_active = False
            for later in decisions[idx_in_list + 1:]:
                if later["turn"] is not None and later["turn"] > t + 1:
                    break
                if later["state_before"].get("active_hp") == 0 or \
                        (later["state_before"].get("active_id") != d["state_before"].get("active_id")
                         and later["our_active_changed_since_prev_own_decision"]):
                    lost_active = True
                    break
            if lost_active:
                tags.append(("I", "MEDIUM", f"turn {t}: confirmed lethal threat left unaddressed, "
                                             "active Pokemon lost by the following turn"))

    seen = set()
    dedup_tags = []
    for tag in tags:
        if tag[0] not in seen:
            dedup_tags.append(tag)
            seen.add(tag[0])

    if not dedup_tags:
        early_slip = decisive_turn is not None and n_turns and decisive_turn <= max(4, n_turns // 3)
        if early_slip:
            dedup_tags.append(("K", "MEDIUM", f"board-value delta went permanently negative by turn "
                                               f"{decisive_turn} (game length {n_turns} turns) with no "
                                               "single flagged decision at that point"))
        elif decisive_turn is None:
            dedup_tags.append(("L", "LOW", "no clear decisive turn found (board value / prize margin "
                                            "never permanently tipped, or data insufficient) and no "
                                            "single flagged decision"))
        else:
            dedup_tags.append(("K", "LOW", f"decisive turn {decisive_turn} identified but no specific "
                                            "decision-level defect found there -- read as matchup/tempo"))

    return dedup_tags, {
        "board_decisive_turn": board_decisive_turn,
        "prize_decisive_turn": prize_decisive_turn,
        "decisive_turn_used": decisive_turn,
        "confirmed_missed_kos_total": len([m for m in missed_kos if m["evidence_level"] == "CONFIRMED"]),
        "evolution_lines": len(evo_lines),
        "first_dragapult_ex_turn": first_ex_turn,
        "energy_stranded_lines": sum(1 for l in evo_lines if l["energy_stranded_pre_ex"]),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    v8 = load_parsed("v8")
    v7 = load_parsed("v7")

    v8_missed = defaultdict(list)
    with open(os.path.join(ROOT, "results", "ladder_behavior_audit", "v8_missed_knockouts.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v8_missed[int(row["episode_id"])].append({"turn": row["turn"], "evidence_level": row["evidence_level"]})

    per_game_rows = []
    loss_tag_counter = Counter()
    loss_tag_examples = defaultdict(list)
    all_evo_lines = []
    energy_summary_rows = []
    n_wasted_lines_by_game = {}

    for game in v8:
        eid = game["episode_id"]
        decisions = game["decisions"]
        idx = game["own_index"]
        board_decisive_turn, board_traj = decisive_turn_from_board_delta(decisions)
        prize_decisive_turn, prize_traj = decisive_turn_from_prize_margin(decisions)
        evo_lines, first_ex_turn = analyze_evolution_and_energy(eid, TARGETS["v8"]["replay_dir"], idx)
        all_evo_lines.extend(evo_lines)
        n_wasted_lines_by_game[eid] = sum(1 for l in evo_lines if l["energy_stranded_pre_ex"])

        main_decisions = [d for d in decisions if d["select_context_name"] == "MAIN"]
        attach_energy_actions = sum(1 for d in decisions if d["action_class"] == "ATTACH_ENERGY")
        row = {
            "episode_id": eid, "result": game["result"], "n_turns": game["n_turns"],
            "opponent_archetype": game["deck_opp_archetype"],
            "opponent_current_score": game.get("opponent_current_score"),
            "board_decisive_turn": board_decisive_turn,
            "prize_decisive_turn": prize_decisive_turn,
            "first_dragapult_ex_turn": first_ex_turn,
            "n_evolution_lines": len(evo_lines),
            "n_energy_stranded_lines": n_wasted_lines_by_game[eid],
            "attach_energy_actions": attach_energy_actions,
            "main_decisions_no_attack_available": sum(1 for d in main_decisions if not d["available_attack_ids"]),
            "main_decisions_total": len(main_decisions),
        }
        per_game_rows.append(row)

        if game["result"] == "LOSS":
            tags, detail = classify_loss(game, decisions, board_traj, board_decisive_turn,
                                          prize_decisive_turn, evo_lines, first_ex_turn,
                                          v8_missed.get(eid, []))
            for letter, conf, rationale in tags:
                loss_tag_counter[letter] += 1
                loss_tag_examples[letter].append({"episode_id": eid, "confidence": conf, "rationale": rationale})
            row["loss_tags"] = ";".join(t[0] for t in tags)
            row["loss_tag_detail"] = detail

    n_losses = sum(1 for g in v8 if g["result"] == "LOSS")

    # matchup table
    matchup = defaultdict(lambda: {"games": 0, "wins": 0, "losses": 0, "draws": 0})
    for game in v8:
        arch = game["deck_opp_archetype"]
        matchup[arch]["games"] += 1
        if game["result"] == "WIN":
            matchup[arch]["wins"] += 1
        elif game["result"] == "LOSS":
            matchup[arch]["losses"] += 1
        else:
            matchup[arch]["draws"] += 1
    matchup_rows = []
    for arch, s in sorted(matchup.items(), key=lambda kv: -kv[1]["games"]):
        wr = s["wins"] / s["games"] if s["games"] else None
        matchup_rows.append({"archetype": arch, **s, "win_rate": wr})

    # opponent-rating bins
    bins = [(0, 600), (600, 650), (650, 700), (700, 750), (750, 10000)]
    bin_rows = []
    for lo, hi in bins:
        games_in_bin = [g for g in v8 if g.get("opponent_current_score") is not None and lo <= g["opponent_current_score"] < hi]
        wins = sum(1 for g in games_in_bin if g["result"] == "WIN")
        bin_rows.append({"bin": f"{lo}-{hi}", "games": len(games_in_bin), "wins": wins,
                          "win_rate": (wins / len(games_in_bin)) if games_in_bin else None})

    # write outputs
    with open(os.path.join(OUT_DIR, "per_game.json"), "w", encoding="utf-8") as f:
        json.dump(per_game_rows, f, indent=2, default=str)

    with open(os.path.join(OUT_DIR, "loss_taxonomy.json"), "w", encoding="utf-8") as f:
        json.dump({
            "n_losses": n_losses,
            "category_counts": dict(loss_tag_counter),
            "category_pct_of_losses": {k: round(100 * v / n_losses, 1) for k, v in loss_tag_counter.items()},
            "examples": {k: v for k, v in loss_tag_examples.items()},
            "labels": CATEGORY_LABELS,
        }, f, indent=2, default=str)

    with open(os.path.join(OUT_DIR, "matchup_table.json"), "w", encoding="utf-8") as f:
        json.dump(matchup_rows, f, indent=2, default=str)

    with open(os.path.join(OUT_DIR, "opponent_rating_bins.json"), "w", encoding="utf-8") as f:
        json.dump(bin_rows, f, indent=2, default=str)

    with open(os.path.join(OUT_DIR, "evolution_lines.csv"), "w", newline="", encoding="utf-8") as f:
        fieldnames = ["episode_id", "serial", "first_turn", "first_energy_turn", "reached_drakloak",
                      "reached_dragapult_ex", "last_turn_seen", "last_id_seen", "last_hp_seen",
                      "disappeared_early_ko", "vanished_unclear", "energy_stranded_pre_ex"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_evo_lines)

    print("=== LOSS TAXONOMY (n_losses=%d) ===" % n_losses)
    for k, v in sorted(loss_tag_counter.items(), key=lambda kv: -kv[1]):
        print(f"  {k} ({CATEGORY_LABELS[k]}): {v} ({100*v/n_losses:.1f}%)")
    print("\n=== MATCHUP TABLE ===")
    for r in matchup_rows:
        print(f"  {r['archetype']}: {r['wins']}-{r['losses']} ({r['win_rate']*100:.1f}% WR, n={r['games']})" if r["win_rate"] is not None else r)
    print("\n=== OPPONENT RATING BINS ===")
    for r in bin_rows:
        print(f"  {r['bin']}: n={r['games']} wins={r['wins']} wr={r['win_rate']}")
    print("\nFirst-Dragapult-ex-on-board turn, mean:",
          sum(r["first_dragapult_ex_turn"] for r in per_game_rows if r["first_dragapult_ex_turn"]) /
          max(1, sum(1 for r in per_game_rows if r["first_dragapult_ex_turn"])))
    print("Games where Dragapult ex NEVER appeared:",
          sum(1 for r in per_game_rows if r["first_dragapult_ex_turn"] is None), "/", len(per_game_rows))
    print("Total energy-stranded Dreepy/Drakloak lines across all V8 games:",
          sum(r["n_energy_stranded_lines"] for r in per_game_rows))
    print("\nWrote outputs to", OUT_DIR)


if __name__ == "__main__":
    main()
