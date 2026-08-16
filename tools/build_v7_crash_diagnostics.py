"""Rapid V7 crash-diagnosis pass -- reuses the existing shared ladder-behavior
parser (src/meta_analysis/ladder_behavior_audit.py, same code path already used
for luca/V2/V6) against the freshly pulled V7 real-ladder replays
(data/v7_ladder_audit/replays/, submission 55478172, live score 594.3).

Not a full statistical audit -- a rapid vital-signs check per the user's
explicit request, on whatever real games exist (27 episodes: 1 validation +
26 public).
"""
import json
import os

from src.meta_analysis.ladder_behavior_audit import parse_episode, find_missed_knockouts

ROOT = r"C:\Users\sertru1000\Projects\PokemonGame"
SUBMISSION_ID = 55478172
REPLAY_DIR = os.path.join(ROOT, "data", "v7_ladder_audit", "replays")
EPISODES_FILE = os.path.join(ROOT, "data", "v7_ladder_audit", "v7_episodes_raw.json")

PHANTOM_DIVE_ATTACK_ID = 154

with open(EPISODES_FILE, encoding="utf-8") as f:
    eps_meta = json.load(f)

games = []
for e in eps_meta:
    if e.get("type") == "EPISODE_TYPE_VALIDATION":
        continue
    eid = e["id"]
    # raw statuses check first -- did OUR agent's steps end in ERROR anywhere?
    rp = os.path.join(REPLAY_DIR, f"episode-{eid}-replay.json")
    with open(rp, encoding="utf-8") as rf:
        raw = json.load(rf)
    own_agent = next(a for a in e["agents"] if a["submissionId"] == SUBMISSION_ID)
    idx = own_agent.get("index", 0)
    opp_idx = 1 - idx
    our_statuses = [step[idx]["status"] for step in raw["steps"]]
    opp_statuses = [step[opp_idx]["status"] for step in raw["steps"]]
    our_errors = [s for s in our_statuses if s not in ("ACTIVE", "DONE", "INACTIVE", "TIMEOUT")]
    n_steps_raw = len(raw["steps"])

    parsed = parse_episode(eid, e, REPLAY_DIR, SUBMISSION_ID, "v7")
    if parsed is None:
        print(f"episode {eid}: PARSE FAILED")
        continue
    decs = parsed["decisions"]

    n_attacks = sum(1 for d in decs if d["action_class"] == "ATTACK")
    n_phantom_dive = sum(1 for d in decs if d["action_class"] == "ATTACK"
                          and d["action_detail"].get("attack_id") == PHANTOM_DIVE_ATTACK_ID)
    n_retreats = sum(1 for d in decs if d["action_class"] == "RETREAT")
    n_end = sum(1 for d in decs if d["action_class"] == "END")
    n_other_none = sum(1 for d in decs if d["action_class"] is None)
    n_attach_energy = sum(1 for d in decs if d["action_class"] == "ATTACH_ENERGY")

    prize_points = [(d["state_before"]["prize_n"], d["opp_before"]["prize_n"]) for d in decs
                     if d["state_before"].get("prize_n") is not None]
    our_prizes_taken = max((6 - p[1]) for p in prize_points) if prize_points else None
    final_our_prize_remaining = prize_points[-1][0] if prize_points else None

    row = {
        "episode_id": eid,
        "result": parsed["result"],
        "went_first": parsed["went_first"],
        "n_turns": parsed["n_turns"],
        "n_steps_raw": n_steps_raw,
        "n_decisions": len(decs),
        "n_attacks": n_attacks,
        "n_phantom_dive": n_phantom_dive,
        "n_retreats": n_retreats,
        "n_attach_energy": n_attach_energy,
        "n_end": n_end,
        "n_action_class_none": n_other_none,
        "our_prizes_taken_est": our_prizes_taken,
        "our_status_anomalies": our_errors,
        "opp_status_anomalies": [s for s in opp_statuses if s not in ("ACTIVE", "DONE", "INACTIVE", "TIMEOUT")],
        "deck_own_archetype": parsed["deck_own_archetype"],
        "deck_opp_archetype": parsed["deck_opp_archetype"],
    }
    games.append(row)

print(f"\n=== V7 REAL LADDER VITAL SIGNS (n={len(games)} public games) ===\n")
for g in games:
    print(g)

print("\n=== AGGREGATES ===")
n = len(games)
results = [g["result"] for g in games]
print("Results:", {r: results.count(r) for r in set(results)})
print("Avg attacks/game:", sum(g["n_attacks"] for g in games) / n)
print("Avg phantom dive/game:", sum(g["n_phantom_dive"] for g in games) / n)
print("Games with 0 attacks:", sum(1 for g in games if g["n_attacks"] == 0))
print("Games with 0 phantom dive:", sum(1 for g in games if g["n_phantom_dive"] == 0))
print("Avg retreats/game:", sum(g["n_retreats"] for g in games) / n)
print("Avg END(pass)/game:", sum(g["n_end"] for g in games) / n)
print("Avg decisions/game:", sum(g["n_decisions"] for g in games) / n)
print("Avg n_steps_raw/game:", sum(g["n_steps_raw"] for g in games) / n)
print("Avg prizes taken/game:", sum((g["our_prizes_taken_est"] or 0) for g in games) / n)
print("Games with any status anomaly (ours):", sum(1 for g in games if g["our_status_anomalies"]))
print("Games with any status anomaly (opp):", sum(1 for g in games if g["opp_status_anomalies"]))
print("Games with action_class None > 0 (unclassified actions):", sum(1 for g in games if g["n_action_class_none"] > 0))

with open(os.path.join(ROOT, "results", "v7_crash_diagnostics.json"), "w", encoding="utf-8") as f:
    json.dump(games, f, indent=2, default=str)
print("\nWrote results/v7_crash_diagnostics.json")
