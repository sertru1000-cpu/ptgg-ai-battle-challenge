"""Phase 4.7 Section 31: submission smoke test.

Runs against `submission/_staging` (the exact assembled archive contents,
not the dev src/ tree) to catch anything that only breaks once main.py is
isolated from this repo's dev environment. Mirrors what the platform itself
does first ("Your submission will start with a scheduled game vs itself to
ensure everything is working before being entered into the matchmaking
pool" -- "How to Submit to this Competition" page, fetched live this phase):

1. import main (from the staged copy, cwd there)
2. initialize agent
3. load deck
4. receive first observation
5. produce a legal action
6. run a complete local game (self-play, matching the platform's own
   validation-episode check) + one game vs an existing external opponent for
   an extra sanity check beyond pure self-play.

Requires tools/build_submission_v1.py to have been run first (this script
does not build the staging dir itself, only exercises it).
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STAGING = REPO / "submission" / "_staging"

CHECK_SCRIPT = r"""
import sys, json, time
sys.path.insert(0, ".")
import main

# 2. initialize agent / 3. load deck
assert callable(main.agent), "main.agent is not callable"
assert isinstance(main.DECK, list) and len(main.DECK) == 60, "DECK is not a 60-card list"
print("OK: agent initialized, deck loaded (60 cards)")

# 4. receive first observation / 5. produce a legal action
sys.path.insert(0, str(r"{repo}"))
from src.environment.engine_loader import ensure_cg_on_path
ensure_cg_on_path()
import cg.game as g

deck_response = main.agent({{"select": None}})
assert deck_response == main.DECK, "first-call response does not match DECK"
print("OK: first observation (select=None) correctly returns the 60-card deck")

# 6. run a complete local game: self-play first (matches the platform's own
# validation-episode check), then vs an existing external opponent.
def run_game(deck_a, agent_a, deck_b, agent_b, max_steps=2000):
    obs, start = g.battle_start(deck_a, deck_b)
    assert start.errorPlayer == -1, f"deck error: {{start.errorPlayer}} {{start.errorType}}"
    steps = 0
    fns = [agent_a, agent_b]
    try:
        while obs["current"]["result"] < 0 and steps < max_steps:
            obs.pop("search_begin_input", None)
            idx = obs["current"]["yourIndex"]
            action = fns[idx](obs)
            assert isinstance(action, list), f"non-list action: {{action}}"
            opts = obs["select"]["option"]
            mn, mx = obs["select"]["minCount"], obs["select"]["maxCount"]
            assert mn <= len(action) <= mx, f"action length {{len(action)}} not in [{{mn}},{{mx}}]"
            assert len(set(action)) == len(action), f"duplicate indices: {{action}}"
            assert all(0 <= i < len(opts) for i in action), f"out-of-range index in {{action}}"
            obs = g.battle_select(action)
            steps += 1
    finally:
        g.battle_finish()
    assert steps < max_steps, "game did not finish within max_steps (would be a real-match timeout)"
    return obs["current"]["result"], steps

result, steps = run_game(main.DECK, main.agent, main.DECK, main.agent)
print(f"OK: self-play validation episode completed cleanly, result={{result}} steps={{steps}}")

sys.path.insert(0, str(r"{repo}"))
from tools.tournament import load_agent
# Loaded by absolute FILE PATH (not dotted module name): `import main` above
# already cached a `src` / `src.agents` package pointing at THIS staged
# directory's own copy in sys.modules, so a dotted "src.agents.X" import
# here would incorrectly resolve inside the staging dir (which intentionally
# only bundles decks/dragapult_ex.csv, not every local deck). The file-path
# loader gives the opponent module its own independent identity, anchored to
# the real dev repo, purely as an external sanity check beyond the platform's
# own self-play validation above -- not part of what actually ships.
opp_name, opp_fn, opp_deck = load_agent(str(r"{repo}" + r"\src\agents\abomasnow_agent.py"))
result2, steps2 = run_game(main.DECK, main.agent, opp_deck, opp_fn)
print(f"OK: game vs {{opp_name}} completed cleanly, result={{result2}} steps={{steps2}}")

print("SMOKE TEST: PASS")
""".format(repo=str(REPO))


def main() -> None:
    if not STAGING.exists():
        print("FAIL: submission/_staging does not exist -- run tools/build_submission_v1.py first")
        sys.exit(1)

    script_path = STAGING / "_smoke_test_check.py"
    script_path.write_text(CHECK_SCRIPT, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(STAGING),
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        script_path.unlink(missing_ok=True)

    print(result.stdout)
    if result.returncode != 0 or "SMOKE TEST: PASS" not in result.stdout:
        print("FAIL:")
        print(result.stderr)
        sys.exit(1)
    print("Submission smoke test: PASS")


if __name__ == "__main__":
    main()
