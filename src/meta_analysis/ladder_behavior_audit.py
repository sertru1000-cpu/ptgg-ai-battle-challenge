"""Shared, agent-agnostic real-ladder replay parser for the V2-vs-Luca behavioral audit.

Built to satisfy an explicit user requirement: Luca and V2 Balanced must be analyzed with
IDENTICAL methodology, on IDENTICAL code paths, so their numbers are honestly comparable. This
module is that single code path. It is applied twice by tools/build_ladder_behavior_audit.py:
once against Luca's already-pulled replays (data/luca_audit/replays/, submission 55447414) and
once against V2 Balanced's real-ladder replays (data/v2_ladder_audit/replays/, submission
55449878) -- both real Kaggle EPISODE_TYPE_PUBLIC ladder games, not local simulation.

Extends the coarser categorization already used in tools/kaggle_replay_forensic.py (session 17)
and the first Luca audit (tools/build_luca_audit_v1.py, session 19) with a card-level action
classifier (PLAY_ITEM/PLAY_SUPPORTER/PLAY_STADIUM/PLAY_TOOL/PLAY_POKEMON/ATTACH_ENERGY/EVOLVE/
ABILITY/RETREAT/ATTACK/END), a prize-value classifier (reusing the EXACT formula from
src/agents/dragapult_policy_v2plus.py's own prize_count(), so "2-prize Pokemon" means what our
own agent's scoring function already means by it, not a new invented definition), and a
best-effort "opponent lethal next turn" threat estimator using the engine's own CardData/Attack
tables (cg.api.all_card_data/all_attack) plus each side's actually-visible attached-energy list.

Every simplifying assumption is stated where it's made. Where a requested signal cannot be
computed reliably, the caller is expected to write "NOT IDENTIFIABLE FROM AVAILABLE DATA"
rather than silently guessing -- this module only ever returns None/False for "couldn't
determine", never fabricates a value.
"""
from __future__ import annotations

from collections import Counter

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()
import cg.api as api  # noqa: E402

from src.meta_analysis.episode_parser import _extract_deck, deck_hash  # noqa: E402
from src.meta_analysis.archetype_signatures import tag_deck  # noqa: E402

SELECT_CONTEXT_NAMES = {int(v): v.name for v in api.SelectContext}
OPTION_TYPE_NAMES = {int(v): v.name for v in api.OptionType}
AREA_TYPE_NAMES = {int(v): v.name for v in api.AreaType}
CARD_TYPE_NAMES = {int(v): v.name for v in api.CardType}
ATTACKS_BY_ID = {a.attackId: a for a in api.all_attack()}
CARDS_BY_ID = {c.cardId: c for c in api.all_card_data()}

# Coarse category taxonomy, reused verbatim from tools/kaggle_replay_forensic.py / the first
# Luca audit -- unchanged so anything computed from it stays comparable to that earlier pass.
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


def prize_value(card_id):
    """EXACT formula reused from src/agents/dragapult_policy_v2plus.py::prize_count(), minus
    the two attack-damage-context-only reductions (Legacy Energy discard, Lillie's Pearl) --
    those only apply to a specific KO-in-progress, not to a static "how many prizes is this
    Pokemon worth" classification, which is all this function is used for here."""
    cd = CARDS_BY_ID.get(card_id)
    if cd is None or cd.cardType != 0:  # not a Pokemon
        return None
    return 3 if cd.megaEx else 2 if cd.ex else 1


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
        "active_energies": list(active0.get("energies") or []) if active0 else [],
        "bench_n": len(bench_raw),
        "bench_ids": [b.get("id") for b in bench_raw],
        "bench_detail": [{"id": b.get("id"), "hp": b.get("hp"), "maxhp": b.get("maxHp"),
                           "energies": list(b.get("energies") or [])} for b in bench_raw],
        "hand": pl.get("hand"),  # only populated/meaningful for OUR OWN index -- see docstring
        "hand_n": pl.get("handCount"),
        "prize_n": len(pl.get("prize") or []),
        "deck_n": pl.get("deckCount"),
        "discard_n": len(pl.get("discard") or []),
    }


def _can_pay(attack, attached_energies):
    """attack.energies is a list of EnergyType costs (0=COLORLESS=wildcard). attached_energies
    is a list of EnergyType values actually attached (directly from the replay -- these are
    already-resolved types, not raw card ids). Colored (non-zero) costs must be matched by the
    SAME type; leftover attached energy of any type pays colorless costs. Does not model
    Rainbow/Team-Rocket special energies providing extra type flexibility -- a documented,
    conservative simplification (may under-count some legal attacks)."""
    attached = Counter(attached_energies)
    colored_cost = Counter(t for t in attack.energies if t != 0)
    colorless_cost = sum(1 for t in attack.energies if t == 0)
    for t, need in colored_cost.items():
        if attached[t] < need:
            return False
        attached[t] -= need
    return sum(attached.values()) >= colorless_cost


def opponent_threat_assessment(opp_active_id, opp_energies, our_active_hp):
    """Best-effort, explicitly approximate. Returns dict with:
      lethal_now: opponent's active already has enough attached energy (by the _can_pay
        approximation above) for >=1 attack whose base damage >= our_active_hp.
      lethal_with_one_more_energy: not lethal_now, but adding exactly one more energy of the
        single most-helpful type would make some attack lethal (a "one turn away" proxy).
      best_attack: (name, damage) of the strongest currently-payable attack, if any.
    Returns None entirely if the opponent's active Pokemon or its card data is unknown (e.g.
    empty active slot) -- caller must treat that as NOT IDENTIFIABLE, not as "no threat"."""
    if opp_active_id is None or our_active_hp is None:
        return None
    cd = CARDS_BY_ID.get(opp_active_id)
    if cd is None:
        return None
    payable = [(ATTACKS_BY_ID[aid]) for aid in cd.attacks if aid in ATTACKS_BY_ID and _can_pay(ATTACKS_BY_ID[aid], opp_energies)]
    lethal_now = any(a.damage >= our_active_hp for a in payable)
    best_attack = max(payable, key=lambda a: a.damage, default=None)
    lethal_with_one_more = False
    if not lethal_now:
        for aid in cd.attacks:
            atk = ATTACKS_BY_ID.get(aid)
            if atk is None or atk.damage < our_active_hp:
                continue
            attached = Counter(opp_energies)
            colored_cost = Counter(t for t in atk.energies if t != 0)
            colorless_cost = sum(1 for t in atk.energies if t == 0)
            shortfall = 0
            for t, need in colored_cost.items():
                shortfall += max(0, need - attached[t])
                attached[t] = max(0, attached[t] - need)
            leftover = sum(attached.values())
            shortfall += max(0, colorless_cost - leftover)
            if shortfall <= 1:
                lethal_with_one_more = True
                break
    return {
        "lethal_now": lethal_now,
        "lethal_with_one_more_energy": lethal_with_one_more,
        "best_attack_name": best_attack.name if best_attack else None,
        "best_attack_damage": best_attack.damage if best_attack else None,
    }


def bench_ready_attacker_count(bench_detail):
    """How many bench Pokemon currently have >=1 attack their own attached energy can already
    pay for (same _can_pay approximation as opponent_threat_assessment). Used only as a
    counterfactual-quality signal (Section 6: "if we had retreated, was there actually a
    ready replacement, or just a warm body"), never as a legality check."""
    ready = 0
    for b in bench_detail or []:
        cd = CARDS_BY_ID.get(b.get("id"))
        if cd is None:
            continue
        if any(_can_pay(ATTACKS_BY_ID[aid], b.get("energies") or []) for aid in cd.attacks if aid in ATTACKS_BY_ID):
            ready += 1
    return ready


def check_missed_knockout(decision):
    """Verbatim from tools/build_luca_audit_v1.py / tools/kaggle_replay_forensic.py."""
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
        return {"evidence_level": "CONFIRMED", "description": f"{lethal_certain} not chosen"}
    return {"evidence_level": "POSSIBLE", "description": f"{lethal_uncertain} not chosen (uncertain)"}


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
            if d2["opp_before"].get("active_id") == opp_id and (d2["opp_before"].get("active_hp") or -1) == 0:
                resolved = True
                break
            if d2["opp_after"].get("active_id") == opp_id and (d2["opp_after"].get("active_hp") or -1) == 0:
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


def classify_action(context, chosen_action, options, hand_before):
    """Returns (action_class, detail_dict). action_class is one of: ATTACK, RETREAT,
    ATTACH_ENERGY, EVOLVE, ABILITY, PLAY_POKEMON, PLAY_ITEM, PLAY_SUPPORTER, PLAY_STADIUM,
    PLAY_TOOL, PLAY_ENERGY_AS_CARD, END, OTHER, or None (context isn't a MAIN action menu)."""
    if context != 0 or not isinstance(chosen_action, list):
        return None, {}
    chosen_opts = [options[c] for c in chosen_action if isinstance(c, int) and 0 <= c < len(options) and isinstance(options[c], dict)]
    if not chosen_opts:
        return None, {}
    o = chosen_opts[0]
    t = o.get("type")
    if t == 13:  # ATTACK
        return "ATTACK", {"attack_id": o.get("attackId")}
    if t == 12:  # RETREAT
        return "RETREAT", {}
    if t == 14:  # END
        return "END", {}
    if t == 10:  # ABILITY
        return "ABILITY", {"area": o.get("area"), "index": o.get("index")}
    if t == 9:  # EVOLVE
        return "EVOLVE", {}
    if t == 8:  # ATTACH (energy)
        return "ATTACH_ENERGY", {}
    if t == 7:  # PLAY (a hand card, non-energy: pokemon/item/supporter/stadium/tool)
        idx = o.get("index")
        card_id = None
        if hand_before and isinstance(idx, int) and 0 <= idx < len(hand_before):
            card_id = hand_before[idx].get("id")
        cd = CARDS_BY_ID.get(card_id) if card_id is not None else None
        if cd is None:
            return "PLAY_UNKNOWN", {"card_id": card_id}
        if cd.cardType == 0:  # POKEMON
            return "PLAY_POKEMON", {"card_id": card_id}
        if cd.cardType == 1:
            return "PLAY_ITEM", {"card_id": card_id}
        if cd.cardType == 2:
            return "PLAY_TOOL", {"card_id": card_id}
        if cd.cardType == 3:
            return "PLAY_SUPPORTER", {"card_id": card_id}
        if cd.cardType == 4:
            return "PLAY_STADIUM", {"card_id": card_id}
        return "PLAY_OTHER", {"card_id": card_id, "card_type": cd.cardType}
    return "OTHER", {"raw_type": t}


def parse_episode(eid, ep_meta, replay_dir, own_submission_id, own_label):
    import json
    import os
    rp = os.path.join(replay_dir, f"episode-{eid}-replay.json")
    if not os.path.exists(rp):
        return None
    with open(rp, encoding="utf-8") as f:
        d = json.load(f)

    own_agent = next(a for a in ep_meta["agents"] if a["submissionId"] == own_submission_id)
    opp_agent = next(a for a in ep_meta["agents"] if a["submissionId"] != own_submission_id)
    idx = own_agent.get("index", 0)
    opp_idx = 1 - idx
    steps = d["steps"]
    rewards = d["rewards"]
    our_r, opp_r = rewards[idx], rewards[opp_idx]
    if our_r == 1 and opp_r == -1:
        result = "WIN"
    elif our_r == -1 and opp_r == 1:
        result = "LOSS"
    elif our_r == 0 and opp_r == 0:
        result = "DRAW"
    else:
        result = "ERROR_OR_TIMEOUT"

    deck_own, src_own = _extract_deck(steps, idx)
    deck_opp, src_opp = _extract_deck(steps, opp_idx)
    arch_own, _, _ = tag_deck(deck_own) if deck_own else ("MISSING", 0, [])
    arch_opp, _, _ = tag_deck(deck_opp) if deck_opp else ("MISSING", 0, [])

    first_player = None
    for step in steps:
        for p in (0, 1):
            cur = step[p]["observation"].get("current")
            if cur and cur.get("firstPlayer") not in (None, -1):
                first_player = cur["firstPlayer"]

    active_rows = [i for i, s in enumerate(steps) if s[idx]["status"] == "ACTIVE"]
    decisions = []
    prev_our_active_id = None
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
        action_class, action_detail = classify_action(context, chosen_action, options, state_before.get("hand"))

        our_active_id = state_before.get("active_id")
        our_active_hp = state_before.get("active_hp")
        our_active_maxhp = state_before.get("active_maxhp")
        prize_val = prize_value(our_active_id) if our_active_id is not None else None
        damaged = (our_active_hp is not None and our_active_maxhp is not None and our_active_hp < our_active_maxhp)
        retreat_available = 12 in option_type_counts
        bench_target_exists = state_before.get("bench_n", 0) > 0
        threat = opponent_threat_assessment(opp_before.get("active_id"), opp_before.get("active_energies", []), our_active_hp)
        our_active_cd = CARDS_BY_ID.get(our_active_id) if our_active_id is not None else None
        our_active_retreat_cost = our_active_cd.retreatCost if our_active_cd else None
        our_active_n_energy = len(state_before.get("active_energies") or [])
        energy_loss_if_retreated = (min(our_active_retreat_cost, our_active_n_energy)
                                     if our_active_retreat_cost is not None else None)
        bench_ready = bench_ready_attacker_count(state_before.get("bench_detail"))

        decisions.append({
            "episode_id": eid, "decision_index": k, "row_index": row_i,
            "turn": state_before.get("turn"),
            "select_context": context,
            "select_context_name": SELECT_CONTEXT_NAMES.get(context, f"UNKNOWN({context})") if context is not None else None,
            "n_options": len(options),
            "available_attack_ids": available_attack_ids,
            "chosen_action": chosen_action,
            "chosen_option_types": [OPTION_TYPE_NAMES.get(t, str(t)) for t in chosen_types],
            "chosen_attack_ids": chosen_attack_ids,
            "category": category,
            "action_class": action_class,
            "action_detail": action_detail,
            "state_before": state_before, "opp_before": opp_before,
            "state_after": state_after, "opp_after": opp_after,
            "our_active_prize_value": prize_val,
            "our_active_damaged": damaged,
            "retreat_available_this_decision": retreat_available,
            "bench_target_exists": bench_target_exists,
            "our_active_retreat_cost": our_active_retreat_cost,
            "our_active_energy_loss_if_retreated": energy_loss_if_retreated,
            "bench_ready_attackers": bench_ready,
            "opp_threat": threat,
            "our_active_changed_since_prev_own_decision": (prev_our_active_id is not None and our_active_id != prev_our_active_id),
        })
        prev_our_active_id = state_before.get("active_id")

    return {
        "episode_id": eid,
        "label": own_label,
        "create_time": ep_meta.get("createTime"),
        "opponent_team_id": opp_agent["teamId"],
        "opponent_team_name": opp_agent["teamName"],
        "result": result,
        "own_index": idx,
        "went_first": (first_player == idx) if first_player is not None else None,
        "n_steps": len(steps),
        "n_turns": max((s[idx]["observation"].get("current") or {}).get("turn", 0) for s in steps if s[idx]["observation"].get("current")) if any(s[idx]["observation"].get("current") for s in steps) else None,
        "deck_own_hash": deck_hash(deck_own) if deck_own else None,
        "deck_own_archetype": arch_own,
        "deck_own_source": src_own,
        "deck_opp_hash": deck_hash(deck_opp) if deck_opp else None,
        "deck_opp_archetype": arch_opp,
        "deck_opp_source": src_opp,
        "n_decisions": len(decisions),
        "decisions": decisions,
    }
