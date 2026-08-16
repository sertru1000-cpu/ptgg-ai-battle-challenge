"""Shared parsing/classification core for the Kaggle Replay + Agent Log Forensic
Analysis phase. Read-only: only reads already-pulled replay/log JSON
(data/kaggle_ladder/) plus the `cg` engine's own attack/card data tables
(for an exact, non-guessed knockout-math check) -- never touches main.py,
deck.csv, decks/, src/agents/, or any submission.

Core mechanical facts this module relies on, each verified directly against
the pulled data before being used (see conversation record / report Section
5 methodology note), not assumed:

1. For player P, log entries (agent stdout/stderr/duration, one list per
   Kaggle-recorded call) correspond 1:1, IN ORDER, to the replay's `steps[i]`
   rows where `steps[i][P]['status'] == 'ACTIVE'`. Verified exact-count-match
   across all 47 pulled episodes, 0 mismatches.
2. `steps[i][P]['action']` is P's response to the select/observation most
   recently shown to P, i.e. `steps[i-1][P]['observation']` (NOT
   `steps[i][P]['observation']`, which is the NEW state/question generated
   AFTER applying this action, for the NEXT call). Verified against the
   deck-declare step (select=None at row 0) versus the 60-card action
   appearing at row 1 alongside a fresh IS_FIRST question.
3. Only `observation.current` for OUR OWN player index is ever read for
   decision-relevant state -- this is exactly what `obs_dict` the real agent
   received, so it is VISIBLE_TO_AGENT by construction, not retrospective.
   The replay's separate `visualize` block (spectator/opponent-hidden info)
   is used ONLY for the opponent-archetype tag, explicitly marked
   HIDDEN_FROM_AGENT / DERIVED_FROM_REPLAY, and never mixed into any
   decision-quality judgment.
"""
from __future__ import annotations

import glob
import json
import os

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()
import cg.api as api  # noqa: E402

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
KLADDER = os.path.join(ROOT, "data", "kaggle_ladder")
REPLAY_DIR = os.path.join(KLADDER, "replays")
LOG_DIR = os.path.join(KLADDER, "agent_logs")
TARGET_SUBMISSION_ID = 55437549

SELECT_CONTEXT_NAMES = {int(v): v.name for v in api.SelectContext}
OPTION_TYPE_NAMES = {int(v): v.name for v in api.OptionType}

ATTACKS_BY_ID = {a.attackId: a for a in api.all_attack()}
CARDS_BY_ID = {c.cardId: c for c in api.all_card_data()}

# Context-level category (specific contexts always win over the generic MAIN menu).
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
# For context 0 (MAIN, the per-turn menu), category is driven by the CHOSEN option's type.
CATEGORY_BY_OPTION_TYPE = {
    0: "RESOURCE_MANAGEMENT", 3: "TARGET_SELECTION", 4: "RESOURCE_MANAGEMENT",
    5: "ENERGY_MANAGEMENT", 6: "ENERGY_MANAGEMENT", 7: "RESOURCE_MANAGEMENT",
    8: "ENERGY_MANAGEMENT", 9: "BENCH_MANAGEMENT", 10: "RESOURCE_MANAGEMENT",
    11: "RESOURCE_MANAGEMENT", 12: "RETREAT_SELECTION", 13: "ATTACK_SELECTION",
    14: "TIMING",
}


def categorize(context: int | None, chosen_option_types: list[int]) -> str:
    if context is not None and context != 0 and context in CATEGORY_BY_CONTEXT:
        return CATEGORY_BY_CONTEXT[context]
    if context == 0:
        if not chosen_option_types:
            # MAIN menu, minCount=0, agent submitted an empty selection -- confirmed
            # by direct inspection this is a legal "pass/nothing more to do this
            # phase" choice (offered alongside an explicit END option), functionally
            # a timing decision, not an unclassifiable one.
            return "TIMING"
        for t in chosen_option_types:
            if t in CATEGORY_BY_OPTION_TYPE:
                return CATEGORY_BY_OPTION_TYPE[t]
    return "UNKNOWN"


def our_index(episode_meta: dict) -> int:
    our_agent = next(a for a in episode_meta["agents"] if a["submissionId"] == TARGET_SUBMISSION_ID)
    return our_agent["index"]


def load_episodes():
    with open(os.path.join(KLADDER, "episodes_raw.json"), encoding="utf-8") as f:
        return json.load(f)


def replay_path(eid):
    p = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
    return p if os.path.exists(p) else None


def log_path(eid, idx):
    p = os.path.join(LOG_DIR, f"episode-{eid}-agent-{idx}-logs.json")
    return p if os.path.exists(p) else None


def _player_snapshot(cur: dict | None, idx: int) -> dict:
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
        "bench_ids": [b.get("id") for b in bench_raw],
        "bench_n": len(bench_raw),
        "hand_n": pl.get("handCount"),
        "prize_n": len(pl.get("prize") or []),
        "deck_n": pl.get("deckCount"),
        "discard_n": len(pl.get("discard") or []),
        "asleep": pl.get("asleep"), "confused": pl.get("confused"),
        "burned": pl.get("burned"), "poisoned": pl.get("poisoned"),
        "paralyzed": pl.get("paralyzed"),
    }


def parse_episode(eid: int, ep_meta: dict) -> dict | None:
    """Returns a dict with 'decisions' (list) and 'meta', or None if the
    replay is unavailable. Every decision's state fields come exclusively
    from `observation.current` for OUR OWN index -- VISIBLE_TO_AGENT by
    construction (see module docstring point 3)."""
    rp = replay_path(eid)
    if rp is None:
        return None
    with open(rp, encoding="utf-8") as f:
        d = json.load(f)
    idx = our_index(ep_meta)
    opp_idx = 1 - idx
    steps = d["steps"]
    n_steps = len(steps)
    our_reward = d["rewards"][idx]
    opp_reward = d["rewards"][opp_idx]
    if our_reward == 1 and opp_reward == -1:
        result = "WIN"
    elif our_reward == -1 and opp_reward == 1:
        result = "LOSS"
    elif our_reward == 0 and opp_reward == 0:
        result = "DRAW"
    else:
        result = "ERROR_OR_TIMEOUT"

    lp = log_path(eid, idx)
    log = None
    if lp:
        with open(lp, encoding="utf-8") as f:
            log = json.load(f)

    active_rows = [i for i, s in enumerate(steps) if s[idx]["status"] == "ACTIVE"]
    log_matched = log is not None and len(log) == len(active_rows)

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
        chosen_types = []
        chosen_attack_ids = []
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

        log_entry = None
        if log is not None and k < len(log):
            raw = log[k]
            log_entry = raw[0] if isinstance(raw, list) and raw else (raw if isinstance(raw, dict) else None)

        decisions.append({
            "episode_id": eid,
            "decision_index": k,  # 0-based, matches log[k]
            "row_index": row_i,
            "turn": state_before.get("turn"),
            "select_context": context,
            "select_context_name": SELECT_CONTEXT_NAMES.get(context, f"UNKNOWN({context})") if context is not None else None,
            "n_options": len(options),
            "option_type_counts": {OPTION_TYPE_NAMES.get(t, str(t)): c for t, c in option_type_counts.items()},
            "available_attack_ids": available_attack_ids,
            "chosen_action": chosen_action,
            "chosen_option_types": [OPTION_TYPE_NAMES.get(t, str(t)) for t in chosen_types],
            "chosen_attack_ids": chosen_attack_ids,
            "category": category,
            "state_before": state_before,
            "opp_before": opp_before,
            "state_after": state_after,
            "opp_after": opp_after,
            "log_duration_s": log_entry.get("duration") if log_entry else None,
            "log_stdout": log_entry.get("stdout") if log_entry else None,
            "log_stderr": log_entry.get("stderr") if log_entry else None,
            "agent_log_match": "YES" if log_entry is not None else "NO",
            "observation_match": "EXACT" if log_matched else "UNKNOWN",
        })

    return {
        "episode_id": eid,
        "result": result,
        "our_index": idx,
        "n_steps": n_steps,
        "n_active_rows": len(active_rows),
        "log_available": log is not None,
        "log_matched_count": log_matched,
        "decisions": decisions,
    }


def check_missed_knockout(decision: dict) -> dict | None:
    """Exact-math knockout check using the real engine's attack damage table
    (cg.api.all_attack()) and card weakness/resistance table
    (cg.api.all_card_data()) -- not a guessed/approximate figure. Only
    called on MAIN-context (0) decisions with >=1 legal ATTACK option.

    Conservative by construction: an attack is only flagged CONFIRMED-lethal
    if its base damage alone (i.e. ignoring any weakness bonus, which could
    only add more damage) already meets or exceeds the opponent active's
    current HP, AND the opponent's card has no listed resistance to our
    attacking Pokemon's own energy type (resistance is the only factor that
    could reduce damage below lethal; weakness only increases it, so
    ignoring weakness here is a deliberately conservative simplification,
    not a source of false positives)."""
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

    # Ability/skill text or non-standard attack text (bench-targeting, coin flips,
    # conditional/variable damage) both invalidate the "attack.damage applies fully
    # and directly to the opponent's active Pokemon" assumption -- confirmed
    # empirically this phase: Crustle's "Mysterious Rock Inn" skill ("Prevent all
    # damage done to this Pokemon by attacks from your opponent's Pokemon {ex}")
    # produced a 21-flag false-positive streak in one episode before this guard was
    # added, and Phantom Dive's own text ("Put 6 damage counters on your opponent's
    # Benched Pokemon in any way you like") turned out to not even target the active
    # Pokemon by default. Any such case is downgraded, never reported as CONFIRMED.
    opp_has_ability = bool(opp_card and opp_card.skills)
    _NONSTANDARD_KEYWORDS = ("bench", "coin", "flip", "counter", "instead", "unless",
                              "for each", "any way you like", "prevent", "discard")

    lethal_certain = []
    lethal_uncertain = []
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
        return None  # agent took the knockout -- not an error

    if lethal_certain:
        return {
            "evidence_level": "CONFIRMED",
            "description": (
                f"Legal, non-resisted, ability-free, standard-direct-damage attack(s) available "
                f"({', '.join(f'{n} (id {i}, {d} dmg) vs opp HP {opp_hp}' for i, n, d in lethal_certain)}) "
                f"but a different action was chosen: {decision['chosen_option_types']}."
            ),
        }
    reasons = []
    if opp_has_ability:
        reasons.append(f"opponent's card (id {opp_id}) has a listed ability/skill that may block or alter damage")
    reasons.append("resistance and/or non-standard attack text (bench-targeting, coin-flip, conditional, etc.) may mean the base damage value does not apply directly/fully to the active Pokemon")
    return {
        "evidence_level": "POSSIBLE",
        "description": (
            f"Legal, lethal-BY-BASE-DAMAGE-ONLY attack(s) available but not chosen -- NOT elevated to "
            f"CONFIRMED because {'; '.join(reasons)}: "
            f"{', '.join(f'{n} (id {i}, {d} dmg) vs opp HP {opp_hp}' for i, n, d in lethal_uncertain)}."
        ),
    }


def find_missed_knockouts(decisions: list[dict]) -> list[dict]:
    """Turn-aware version of the knockout check. A naive per-decision check
    produces false positives whenever the agent revisits the MAIN menu
    multiple times in one turn (e.g. play a card, THEN attack) -- confirmed
    empirically: a raw per-decision flag on one real episode turned out to
    be followed one decision later, same turn, by the agent actually taking
    that exact attack and landing the KO. This function instead looks
    forward within the same turn (same `turn` value, same opponent active
    card id) and only reports a miss if the opponent's active Pokemon is
    NEVER knocked out (hp drops to 0) and the flagged attack is NEVER taken
    before the turn value changes."""
    results = []
    n = len(decisions)
    for k, dec in enumerate(decisions):
        ko = check_missed_knockout(dec)
        if ko is None:
            continue
        opp_id = dec["opp_before"].get("active_id")
        opp_hp0 = dec["opp_before"].get("active_hp")
        turn0 = dec["turn"]
        resolved = False
        target_removed_via_switch = False
        j = k

        def _hp_zero(hp):
            return hp is not None and hp <= 0

        while j < n and decisions[j]["turn"] == turn0:
            d2 = decisions[j]
            if d2["opp_before"].get("active_id") == opp_id and _hp_zero(d2["opp_before"].get("active_hp")):
                resolved = True
                break
            if d2["opp_after"].get("active_id") == opp_id and _hp_zero(d2["opp_after"].get("active_hp")):
                resolved = True
                break
            # Confirmed empirically: this engine clears the active slot to `None`
            # (empty, awaiting a replacement pick) immediately after a knockout,
            # rather than leaving the same card id with hp=0 -- so an empty active
            # slot right after the original target was there is itself the KO
            # signal, not just a hp==0 reading under the same id.
            if d2["opp_after"].get("active_id") is None and d2["opp_before"].get("active_id") in (opp_id, None):
                resolved = True
                break
            if d2["opp_after"].get("active_id") not in (None, opp_id):
                target_removed_via_switch = True  # original target left the active spot (switch/forced-switch)
                break
            if j > k and d2["opp_before"].get("active_id") not in (None, opp_id):
                target_removed_via_switch = True
                break
            j += 1
        if not resolved:
            note = (
                " (checked forward through end of turn: the ORIGINAL target Pokemon was switched "
                "out of the active spot before it could be re-attacked -- this is a materially "
                "different, more benign situation than a target that simply sat there unattacked; "
                "not counted toward the headline CONFIRMED total, see report methodology)"
                if target_removed_via_switch else
                " (checked forward through end of turn: opponent's active Pokemon was never knocked "
                "out and this attack was never subsequently taken that turn)"
            )
            results.append({
                "episode_id": dec["episode_id"],
                "decision_index": dec["decision_index"],
                "turn": turn0,
                "evidence_level": ko["evidence_level"] if not target_removed_via_switch else "POSSIBLE",
                "target_removed_via_switch": target_removed_via_switch,
                "description": ko["description"] + note,
            })
    return results


def all_episode_dirs():
    return sorted(glob.glob(os.path.join(REPLAY_DIR, "episode-*-replay.json")))
