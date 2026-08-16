"""Ad hoc local validation for V9: real games through the actual compiled
engine (not the synthetic fixtures in verify_v9_survival_retreat.py),
mirroring tools/verify_v8_real_game_smoke_test.py's harness. Confirms V9
produces only legal actions across full real games (self-play, vs the old
lucario_ex_agent baseline, vs V8 head to head, vs abomasnow/mewtwo/iono's),
that it never gets stuck retreating in a loop, and reports whether:
  - the (now 1-Prize/megaEx-expanded) survival-retreat hook fired for real,
    split by one_prize_path vs the ex/megaEx path;
  - DAMAGE_COUNTER_ANY was ever actually reached (expected: never -- see
    lucario_policy_v9.py's module docstring, this deck's kit has no
    damage-counter-placement attack; a nonzero count here would mean that
    claim was wrong and needs to be revisited before shipping).
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402

ensure_cg_on_path()

import cg.game as g  # noqa: E402
from cg.api import to_observation_class, OptionType, SelectContext  # noqa: E402

from src.agents.lucario_agent_v9 import agent as v9_agent, DECK as V9_DECK  # noqa: E402
from src.agents.dragapult_agent_v8 import agent as v8_agent, DECK as V8_DECK  # noqa: E402
from src.agents.abomasnow_agent import agent as abomasnow_agent, DECK as ABOMASNOW_DECK  # noqa: E402
from src.agents.lucario_ex_agent import agent as lucario_baseline_agent, DECK as LUCARIO_BASELINE_DECK  # noqa: E402
from src.agents.generic_mewtwo_agent import agent as mewtwo_agent, DECK as MEWTWO_DECK  # noqa: E402
from src.agents.iono_agent import agent as iono_agent, DECK as IONO_DECK  # noqa: E402


def run_game(deck0, agent0, deck1, agent1, max_steps=2000):
    obs, start = g.battle_start(deck0, deck1)
    if start.errorPlayer != -1:
        raise RuntimeError(f"deck error: player {start.errorPlayer} errorType {start.errorType}")
    fns = [agent0, agent1]
    steps = 0
    retreats_slot0 = 0
    damage_counter_any_selects = 0
    try:
        while obs["current"]["result"] < 0 and steps < max_steps:
            obs.pop("search_begin_input", None)
            idx = obs["current"]["yourIndex"]
            o = to_observation_class(obs)
            if idx == 0 and o.select is not None and o.select.context == SelectContext.DAMAGE_COUNTER_ANY:
                damage_counter_any_selects += 1
            action = fns[idx](obs)
            assert isinstance(action, list), f"non-list action: {action}"
            opts = obs["select"]["option"]
            mn, mx = obs["select"]["minCount"], obs["select"]["maxCount"]
            assert mn <= len(action) <= mx, f"action length {len(action)} not in [{mn},{mx}]"
            assert len(set(action)) == len(action), f"duplicate indices: {action}"
            assert all(0 <= i < len(opts) for i in action), f"out-of-range index in {action}"
            if idx == 0 and o.select is not None and o.select.context == SelectContext.MAIN:
                for i in action:
                    if opts[i].get("type") == int(OptionType.RETREAT):
                        retreats_slot0 += 1
            obs = g.battle_select(action)
            steps += 1
    finally:
        g.battle_finish()
    assert steps < max_steps, "game did not finish within max_steps (possible infinite loop)"
    return obs["current"]["result"], steps, retreats_slot0, damage_counter_any_selects


def report(label, deck0, agent0, deck1, agent1, policy):
    result, steps, retreats, dca = run_game(deck0, agent0, deck1, agent1)
    print(f"{label}")
    print(f"  OK: result={result} steps={steps} retreats(slot0)={retreats} DAMAGE_COUNTER_ANY_selects(slot0)={dca}")
    n_before = len(policy.survival_retreat_log)
    return result, steps, retreats, dca, n_before


def main() -> int:
    v9_policy = v9_agent.policy  # type: ignore[attr-defined]
    total_dca = 0

    print("Game 1: V9 (slot0) self-play vs V9 (slot1)")
    _, _, _, dca, _ = report("", V9_DECK, v9_agent, V9_DECK, v9_agent, v9_policy)
    total_dca += dca
    print(f"  survival_retreat_log so far (slot0 instance): {len(v9_policy.survival_retreat_log)} entries")

    print("Game 2: V9 (slot0) vs abomasnow_agent (slot1)")
    _, _, _, dca, _ = report("", V9_DECK, v9_agent, ABOMASNOW_DECK, abomasnow_agent, v9_policy)
    total_dca += dca
    print(f"  survival_retreat_log so far (slot0 instance): {len(v9_policy.survival_retreat_log)} entries")

    print("Game 3: V9 (slot0) vs V8/Dragapult ex (slot1) -- cross-deck sanity check")
    _, _, _, dca, _ = report("", V9_DECK, v9_agent, V8_DECK, v8_agent, v9_policy)
    total_dca += dca
    print(f"  survival_retreat_log so far (slot0 instance): {len(v9_policy.survival_retreat_log)} entries")

    print("Game 4: V9 (slot0) vs the OLD lucario_ex_agent baseline (slot1) -- same deck/archetype, different policy")
    _, _, _, dca, _ = report("", V9_DECK, v9_agent, LUCARIO_BASELINE_DECK, lucario_baseline_agent, v9_policy)
    total_dca += dca
    print(f"  survival_retreat_log so far (slot0 instance): {len(v9_policy.survival_retreat_log)} entries")

    print("Game 5: V9 (slot0) vs generic Mewtwo ex agent (slot1)")
    _, _, _, dca, _ = report("", V9_DECK, v9_agent, MEWTWO_DECK, mewtwo_agent, v9_policy)
    total_dca += dca
    print(f"  survival_retreat_log so far (slot0 instance): {len(v9_policy.survival_retreat_log)} entries")

    print("Game 6: V9 (slot0) vs Iono's agent (slot1) -- a hard-hitting matchup, best real-game chance of a guaranteed lethal on our Active")
    _, _, _, dca, _ = report("", V9_DECK, v9_agent, IONO_DECK, iono_agent, v9_policy)
    total_dca += dca
    print(f"  survival_retreat_log so far (slot0 instance): {len(v9_policy.survival_retreat_log)} entries")

    n_total = len(v9_policy.survival_retreat_log)
    n_one_prize = sum(1 for e in v9_policy.survival_retreat_log if e.get("one_prize_path"))
    n_ex_mega = n_total - n_one_prize
    print(f"\nTotal survival-retreat activations across all 6 games (slot0 V9 instance, cumulative): {n_total}")
    print(f"  one_prize_path=True (Objective 2 new eligibility): {n_one_prize}")
    print(f"  one_prize_path=False (ex/megaEx path): {n_ex_mega}")
    for entry in v9_policy.survival_retreat_log:
        print(f"    {entry}")

    print(f"\nTotal DAMAGE_COUNTER_ANY selects across all 6 games (slot0 V9 instance): {total_dca} (expected 0 -- see module docstring)")

    if total_dca != 0:
        print("\nSMOKE TEST: FAIL -- DAMAGE_COUNTER_ANY was reached; the 'verified-inert for this deck' claim in lucario_policy_v9.py's docstring needs to be revisited.")
        return 1

    print("\nSMOKE TEST: PASS -- V9 produced only legal actions across all 6 games, no infinite loops, DAMAGE_COUNTER_ANY confirmed inert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
