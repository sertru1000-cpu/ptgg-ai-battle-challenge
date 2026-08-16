"""Phase 4.7.1: Kaggle exec()-runtime compatibility test.

Reproduces, locally, the exact failure mode Kaggle hit
(`NameError: name '__file__' is not defined` inside main.py) and proves it
no longer occurs, using the ACTUAL staged submission contents rather than
this dev repo's own source tree.

Two fidelity problems a naive local test would have, both handled here:

1. `python main.py` (or a normal `import main`) always has `__file__`
   defined -- that is precisely why the original bug shipped without being
   caught locally. This script instead reads main.py's source as text and
   `exec()`s it in a namespace that deliberately has no `__file__` key, the
   same shape of namespace kaggle_environments' agent runner uses.
2. This dev machine has a global `.pth` file
   (pytools/python312/Lib/site-packages/pokemongame.pth) that makes
   `import src...` resolve to THIS REPO's src/, from any process, any cwd --
   completely independent of whatever main.py's own path-fixing logic does.
   Left in place, a test could pass for a completely wrong reason (silently
   falling back to the dev tree instead of the staged, self-contained
   copy). This script strips that exact path entry out of sys.path before
   running the exec test, so `import src` can only succeed via the staged
   copy's own logic -- a faithful stand-in for "there is no such shortcut
   on the real Kaggle sandbox."

Steps:
  1. Rebuild submission/_staging via tools/build_submission_v1.py (so the
     test exercises the current main.py, not a stale staged copy).
  2. Run the exec()-without-__file__ test against the staged main.py.
  3. Within that same exec'd agent, play a self-play game and one game vs
     an external opponent through the real engine, proving the fix doesn't
     just avoid the NameError but produces a fully working agent.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STAGING = REPO / "submission" / "_staging"

# The exact dev-machine shortcut path to strip -- see module docstring point 2.
_DEV_PTH_SHORTCUT = str(REPO)

_INNER_SCRIPT = r"""
import sys

# --- Fidelity fix: remove this dev machine's global .pth-injected repo-root
# entry so `import src`/`import cg` can ONLY succeed via whatever the staged
# main.py's own logic (or a Kaggle-like implicit sys.path) provides -- never
# via this repo's separate dev-convenience shortcut.
_shortcut = r"{dev_shortcut}"
sys.path = [p for p in sys.path if p != _shortcut]

source = open("main.py", "r", encoding="utf-8").read()

# --- The actual reproduction: exec() with NO __file__ in the namespace,
# matching kaggle_environments' agent-loading model (it reads agent source
# as text and execs it, unlike `python main.py` or a normal `import`, both
# of which always define __file__).
namespace = {{"__name__": "__main__"}}
assert "__file__" not in namespace

try:
    exec(compile(source, "main.py", "exec"), namespace)
except NameError as e:
    if "__file__" in str(e):
        print("REPRO: NameError on __file__ still occurs -- FIX DID NOT WORK")
        print(f"  {{type(e).__name__}}: {{e}}")
        sys.exit(1)
    raise

print("OK: main.py executed via exec() with no __file__ defined, no NameError")

agent = namespace.get("agent")
deck = namespace.get("DECK")
assert callable(agent), "exec'd namespace has no callable `agent`"
assert isinstance(deck, list) and len(deck) == 60, "exec'd namespace has no valid 60-card DECK"
print("OK: agent() and DECK both correctly defined in the exec'd namespace")

deck_response = agent({{"select": None}})
assert deck_response == deck, "first-call response does not match DECK"
print("OK: first observation (select=None) correctly returns the 60-card deck")

# --- Prove `src` resolved via the STAGED copy, not the dev shortcut.
mod = sys.modules.get("src")
assert mod is not None and mod.__file__, "src module has no __file__ (unexpected)"
staged_src = str((__import__("pathlib").Path.cwd() / "src").resolve())
resolved_src_dir = str(__import__("pathlib").Path(mod.__file__).resolve().parent)
assert resolved_src_dir == staged_src, (
    f"`src` resolved from {{resolved_src_dir}}, expected the staged copy at {{staged_src}} "
    "-- the dev .pth shortcut leaked into this test"
)
print(f"OK: `src` resolved from the staged copy ({{resolved_src_dir}}), not the dev repo")

# --- Full game(s) through the real engine, using the exec'd agent.
sys.path.insert(0, r"{repo}")
from src.environment.engine_loader import ensure_cg_on_path  # noqa: E402
ensure_cg_on_path()
import cg.game as g  # noqa: E402


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
            opts = obs["select"]["option"]
            mn, mx = obs["select"]["minCount"], obs["select"]["maxCount"]
            assert isinstance(action, list) and mn <= len(action) <= mx and len(set(action)) == len(action)
            assert all(0 <= i < len(opts) for i in action)
            obs = g.battle_select(action)
            steps += 1
    finally:
        g.battle_finish()
    assert steps < max_steps, "game did not finish within max_steps"
    return obs["current"]["result"], steps

result, steps = run_game(deck, agent, deck, agent)
print(f"OK: self-play game via the exec'd agent completed cleanly, result={{result}} steps={{steps}}")

from tools.tournament import load_agent  # noqa: E402
opp_name, opp_fn, opp_deck = load_agent(str(r"{repo}" + r"\src\agents\abomasnow_agent.py"))
result2, steps2 = run_game(deck, agent, opp_deck, opp_fn)
print(f"OK: game vs {{opp_name}} via the exec'd agent completed cleanly, result={{result2}} steps={{steps2}}")

print("KAGGLE EXEC COMPAT TEST: PASS")
""".format(dev_shortcut=_DEV_PTH_SHORTCUT, repo=str(REPO))


def main() -> None:
    print("--- 1. Rebuild submission/_staging from the current main.py")
    build = subprocess.run([sys.executable, "tools/build_submission_v1.py"], cwd=str(REPO), capture_output=True, text=True)
    print(build.stdout)
    if build.returncode != 0:
        print("FAIL: tools/build_submission_v1.py failed")
        print(build.stderr)
        sys.exit(1)

    print("--- 2-3. Run the exec()-without-__file__ reproduction + full-game test")
    script_path = STAGING / "_kaggle_exec_compat_check.py"
    script_path.write_text(_INNER_SCRIPT, encoding="utf-8")
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
    if result.returncode != 0 or "KAGGLE EXEC COMPAT TEST: PASS" not in result.stdout:
        print("FAIL:")
        print(result.stderr)
        sys.exit(1)
    print("Kaggle exec() compatibility test: PASS")


if __name__ == "__main__":
    main()
