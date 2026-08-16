"""Package a V2..V10 challenger into its own Kaggle submission archive
(Prompt #5, Part 7: "prepare everything so I can explicitly choose which
version to submit"). Never touches submission/_staging or
submission/final_submission.tar.gz (V1/BASELINE's own staging dir and
archive, built by tools/build_submission_v1.py) -- each challenger gets its
own staging directory and its own timestamped archive, so V1's archive is
never at risk of being overwritten by running this tool.

Same validation steps as tools/build_submission_v1.py (main.py imports
cleanly, deck.csv passes real battle_start legality, staged copy runs fully
standalone, archive structure/size sanity-checked) -- just parameterized
over which version's main.py to package. Deliberately does NOT call `kaggle
competitions submit` or anything else that would upload to Kaggle: building
the archive is a fully local, reversible step; uploading it is a separate,
explicit action left to the user.

DECK SOURCE (added for v9, see V9_IMPLEMENTATION_REPORT.md section 4.3):
V2-V8 all play the same Dragapult ex decklist, which happens to live in two
byte-identical places -- the shared repo-root `deck.csv` and
`decks/dragapult_ex.csv` -- so earlier versions of this script just copied
the shared root file. V9 plays a DIFFERENT decklist (Mega Lucario ex) and
must NOT be packaged with the shared root `deck.csv` (that file holds
Dragapult ex's list, and always will as long as V2-V8 depend on it for their
own local testing/staging -- packaging V9 with it would declare the wrong
60 cards while the agent internally tries to play Lucario cards it doesn't
have, the exact bug already avoided once in main_v9.py's own docstring).
`DECK_SOURCE` below is the single per-version source of truth this script
now reads from instead: `decks/<archetype>.csv` directly, never the shared
root file, for every version -- functionally identical output for v2-v8
(decks/dragapult_ex.csv IS the same bytes as root deck.csv, confirmed via
diff) and correct-by-construction for v9.

v10 (see V10_IMPLEMENTATION_REPORT.md) is the same situation as v9: it plays
its own modernized Dragapult ex decklist (`decks/dragapult_ex_v10.csv`), not
the shared root `deck.csv` (still V1-V8's older Dragapult ex list) -- same
`DECK_SOURCE`-driven fix applies. Per V10's own governing task, building this
local archive is explicitly allowed (a fully local, reversible packaging
step); this script still never calls `kaggle competitions submit` or
anything else that would actually upload v10 (or any version) to Kaggle.

v11 (see V11_IMPLEMENTATION_REPORT.md) is back to V6/V2-V8's exact decklist
(`decks/dragapult_ex.csv`) -- it forks V6's policy/greedy logic, not V10's
deck or setup logic, per its own governing task's explicit instruction. Same
"build the archive but do not submit" rule as v9/v10.

v12 (see V12_IMPLEMENTATION_REPORT.md) is also V6's exact decklist
(`decks/dragapult_ex.csv`) -- it forks V6's policy/greedy logic (not V10's
deck/policy) and adds opponent-archetype detection + dynamic weight
shifting, with no lookahead/search (that's v11's job) and no V8/V9
survival/defensive-retreat heuristics. Same "build the archive but do not
submit" rule.

v13 (see V13_IMPLEMENTATION_REPORT.md) forks V6's exact policy/greedy logic
(not V10's), with no lookahead/search and no V8/V9 survival/defensive-retreat
heuristics, but plays its own new "turbo consistency" decklist
(`decks/dragapult_v13_turbo.csv`, NOT `decks/dragapult_ex.csv`) -- a
deck-selection experiment, same DECK_SOURCE-driven situation as v9/v10. Same
"build the archive but do not submit" rule.

v14 (see V14_IMPLEMENTATION_REPORT.md) is also V6's exact decklist
(`decks/dragapult_ex.csv`) -- it forks V6's policy/greedy logic (not V10's)
and adds game-phase detection (EARLY/MID/LATE, from both players' own
remaining prize counts) + dynamic weight modulation by phase, with no
lookahead/search (that's v11's job) and no V8/V9 survival/defensive-retreat
heuristics. Same "build the archive but do not submit" rule.

v15 (see V15_IMPLEMENTATION_REPORT.md, if present) is also V6's exact
decklist (`decks/dragapult_ex.csv`) -- it is a strict fork of V6's engine
(src/agents/dragapult_policy_v15.py, byte-identical logic to
dragapult_policy_v6.py, including both Phantom Dive fixes) with V4's
DEFENSIVE weight profile substituted for V6's BALANCED profile in
src/agents/dragapult_agent_v15.py. No new logic, no lookahead/search, no
opponent modeling. Same "build the archive but do not submit" rule.

v16 (feature/xgboost-rd branch, R&D) is also V6's exact decklist
(`decks/dragapult_ex.csv`) -- it forks V6's policy/greedy logic and adds a
per-decision win-probability signal from a trained XGBoost model
(src/agents/xgb_model.json, produced by src/ml/train_xgboost.py) blended into
V5's existing AGGRESSIVE<->DEFENSIVE weight interpolation. Two things no
earlier version needed: (1) `src/agents/xgb_model.json` must be staged --
already covered by the existing `shutil.copytree(REPO / "src", ...)` step
below since that file lives inside `src/agents/`, verified explicitly in step
5 below rather than assumed; (2) the `xgboost` PyPI package is a genuinely new
runtime dependency (every prior version only needs the bundled `cg` package)
-- a `requirements.txt` is staged as a best-effort artifact, but whether
Kaggle's actual "cabt" grading sandbox has xgboost pre-installed (or installs
from a bundled requirements.txt at all) is UNVERIFIED; this is a real risk to
resolve before any actual v16 submission, not before this local
build-only step. Same "build the archive but do not submit" rule.

v17 (C++ MCTS Edition, src/agents/dragapult_agent_v17_cpp/) is also V6's exact
decklist (`decks/dragapult_ex.csv`) -- it forks V6's own scoring math
(ported line-for-line to C++, not reimplemented) for both the MCTS
rollout/default policy and the leaf/backup evaluation, with a native
Monte Carlo Tree Search calling the engine's SearchBegin/SearchStep/SearchEnd
C ABI directly from C++ (bypassing Python for every simulated branch -- see
that package's README.md for the full architecture and its explicitly
documented caveats). Nothing extra needs staging beyond what
`shutil.copytree(REPO / "src", ...)` already does -- the C++ source
(`cpp/*.hpp`/`.cpp`), `compile.sh`, and `CMakeLists.txt` all live inside
`src/agents/dragapult_agent_v17_cpp/` and are copied automatically, same as
v16's `xgb_model.json`. UNLIKE every other version, v17 ships NO precompiled
native library: `main.py` compiles `cpp/v17_agent.cpp` with `g++` the first
time it is imported (see native_bridge.py's `_ensure_native_library_built`),
falling back to the pure-Python V6 agent if no compiler is available -- this
dev machine has no C++ toolchain at all (checked directly: no
cl.exe/g++/clang++/cmake, no WSL distro, no Docker), so the native path has
never actually been compiled or execution-tested, only reviewed by hand and
smoke-tested at the Python-flattening layer against a real live engine game
(zero errors across ~670 real decisions, 15 distinct SelectContext values).
Whether Kaggle's grading container has `g++` available is UNVERIFIED from
here -- if it doesn't, this version silently (but safely) runs as pure-Python
V6 for the whole match. Same "build the archive but do not submit" rule --
and for v17 specifically, do not submit without first compiling and
execution-testing on a machine that actually has a C++ toolchain (see that
package's README.md, "How to actually build and test this").

Usage:
    python tools/build_submission_challenger.py --version v2
    python tools/build_submission_challenger.py --version v3
    python tools/build_submission_challenger.py --version v4
    python tools/build_submission_challenger.py --version v5
    python tools/build_submission_challenger.py --version v6
    python tools/build_submission_challenger.py --version v7
    python tools/build_submission_challenger.py --version v8
    python tools/build_submission_challenger.py --version v9
    python tools/build_submission_challenger.py --version v10
    python tools/build_submission_challenger.py --version v11
    python tools/build_submission_challenger.py --version v12
    python tools/build_submission_challenger.py --version v13
    python tools/build_submission_challenger.py --version v14
    python tools/build_submission_challenger.py --version v15
    python tools/build_submission_challenger.py --version v16
    python tools/build_submission_challenger.py --version v17
"""

import argparse
import datetime
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUBMISSION_DIR = REPO / "submission"
CG_SRC = REPO / "data" / "official" / "sample_submission" / "sample_submission" / "cg"
SANITY_SIZE_CEILING_MB = 200

VALID_VERSIONS = {"v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15", "v16", "v17", "v18", "v19", "v20", "v21", "v22", "v23", "v24", "v25", "v26"}

DECK_SOURCE = {
    "v2": "dragapult_ex.csv", "v3": "dragapult_ex.csv", "v4": "dragapult_ex.csv",
    "v5": "dragapult_ex.csv", "v6": "dragapult_ex.csv", "v7": "dragapult_ex.csv",
    "v8": "dragapult_ex.csv", "v9": "lucario_ex.csv", "v10": "dragapult_ex_v10.csv",
    "v11": "dragapult_ex.csv", "v12": "dragapult_ex.csv", "v13": "dragapult_v13_turbo.csv",
    "v14": "dragapult_ex.csv", "v15": "dragapult_ex.csv", "v16": "dragapult_ex.csv",
    "v17": "dragapult_ex.csv",
    "v18": "dragapult_ex.csv",
    "v19": "dragapult_ex_v19.csv",
    "v20": "dragapult_ex.csv",
    "v21": "dragapult_ex_v19.csv",
    "v22": "dragapult_ex.csv",
    "v23": "dragapult_ex.csv",
    "v24": "dragapult_ex.csv",
    "v25": "dragapult_ex_v19.csv",
    "v26": "dragapult_ex_v19.csv",
}

# Versions with a genuine extra PyPI runtime dependency beyond the bundled cg
# package -- a requirements.txt is staged for these (see module docstring's
# v16 note: whether Kaggle's grading sandbox actually installs from it is
# unverified, this is a best-effort artifact, not a confirmed fix).
EXTRA_REQUIREMENTS = {
    "v16": ["xgboost==3.4.0"],
}

# Versions whose staged src/ tree must contain specific extra files beyond
# the standard required set (e.g. a trained model artifact) -- checked
# explicitly in step 3-4 rather than only relying on the copytree succeeding.
EXTRA_REQUIRED_FILES = {
    "v16": ["src/agents/xgb_model.json", "src/ml/vectorizer.py"],
    "v17": [
        "src/agents/dragapult_agent_v17_cpp/cpp/v17_agent.cpp",
        "src/agents/dragapult_agent_v17_cpp/cpp/mcts.hpp",
        "src/agents/dragapult_agent_v17_cpp/cpp/v6_heuristic_scores.hpp",
        "src/agents/dragapult_agent_v17_cpp/native_bridge.py",
        "src/agents/dragapult_agent_v17_cpp/compile.sh",
    ],
    "v18": [
        "src/agents/dragapult_agent_v18_cpp/cpp/v17_agent.cpp",
        "src/agents/dragapult_agent_v18_cpp/cpp/mcts.hpp",
        "src/agents/dragapult_agent_v18_cpp/cpp/v6_heuristic_scores.hpp",
        "src/agents/dragapult_agent_v18_cpp/native_bridge.py",
        "src/agents/dragapult_agent_v18_cpp/opponent_model.py",
        "src/agents/dragapult_agent_v18_cpp/archetype_decks.py",
        "src/agents/dragapult_agent_v18_cpp/compile.sh",
    ],
    "v20": [
        "src/agents/dragapult_agent_v20_cpp/cpp/v17_agent.cpp",
        "src/agents/dragapult_agent_v20_cpp/cpp/mcts.hpp",
        "src/agents/dragapult_agent_v20_cpp/cpp/pwin_trees.hpp",
        "src/agents/dragapult_agent_v20_cpp/cpp/vectorizer.hpp",
        "src/agents/dragapult_agent_v20_cpp/native_bridge.py",
        "src/agents/dragapult_agent_v20_cpp/opponent_model.py",
        "src/agents/dragapult_agent_v20_cpp/archetype_decks.py",
        "src/agents/dragapult_agent_v20_cpp/compile.sh",
    ],
    "v21": [
        "src/ml/bc_trees.py",
        "src/ml/bc_features.py",
        "src/ml/vectorizer.py",
        "src/agents/dragapult_policy_v21.py",
        "src/agents/dragapult_policy_v19.py",
    ],
    "v22": [
        "src/agents/dragapult_agent_v22_cpp/cpp/v17_agent.cpp",
        "src/agents/dragapult_agent_v22_cpp/cpp/mcts.hpp",
        "src/agents/dragapult_agent_v22_cpp/cpp/pwin_trees.hpp",
        "src/agents/dragapult_agent_v22_cpp/cpp/vectorizer.hpp",
        "src/agents/dragapult_agent_v22_cpp/native_bridge.py",
        "src/agents/dragapult_agent_v22_cpp/opponent_model.py",
        "src/agents/dragapult_agent_v22_cpp/archetype_decks.py",
        "src/agents/dragapult_agent_v22_cpp/compile.sh",
    ],
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def step(msg: str) -> None:
    print(f"--- {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, choices=sorted(VALID_VERSIONS))
    args = parser.parse_args()
    version = args.version
    main_py = REPO / f"main_{version}.py"
    staging = SUBMISSION_DIR / f"_staging_{version}"
    final_candidate_module = f"src/agents/final_candidate_agent_{version}.py"
    deck_filename = DECK_SOURCE[version]
    deck_source_path = REPO / "decks" / deck_filename

    if not main_py.exists():
        fail(f"{main_py} not found")

    step(f"1. Validate {main_py.name} imports cleanly and defines agent()")
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib.util as u; spec=u.spec_from_file_location('m', r'{main_py}'); m=u.module_from_spec(spec); spec.loader.exec_module(m); assert callable(m.agent); assert len(m.DECK) == 60"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"{main_py.name} failed to import cleanly:\n{result.stdout}\n{result.stderr}")
    print(f"    OK: {main_py.name} imports cleanly, agent() defined, DECK has 60 cards")

    step(f"2. Validate decks/{deck_filename} (60 lines, real battle_start legality check)")
    result = subprocess.run(
        [sys.executable, "tools/deck_validator.py", f"decks/{deck_filename}"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    print("   ", result.stdout.strip())
    if result.returncode != 0 or "illegal" in result.stdout.lower():
        fail(f"decks/{deck_filename} failed legality validation:\n{result.stdout}\n{result.stderr}")
    print(f"    OK: decks/{deck_filename} is legal")

    step("3-4. Assemble staging directory (validates required files by construction)")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    shutil.copy2(main_py, staging / "main.py")
    shutil.copy2(deck_source_path, staging / "deck.csv")

    if not CG_SRC.is_dir():
        fail(f"cg engine package not found at {CG_SRC} -- cannot bundle it")
    shutil.copytree(CG_SRC, staging / "cg", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(REPO / "src", staging / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    decks_dst = staging / "decks"
    decks_dst.mkdir()
    shutil.copy2(deck_source_path, decks_dst / deck_filename)

    if version in EXTRA_REQUIREMENTS:
        (staging / "requirements.txt").write_text("\n".join(EXTRA_REQUIREMENTS[version]) + "\n")
        print(f"    staged requirements.txt: {EXTRA_REQUIREMENTS[version]}")

    required = ["main.py", "deck.csv", "cg/api.py", "cg/game.py", final_candidate_module, f"decks/{deck_filename}"]
    required += EXTRA_REQUIRED_FILES.get(version, [])
    for rel in required:
        if not (staging / rel).exists():
            fail(f"required staged file missing: {rel}")
    print(f"    OK: staged {sum(1 for _ in staging.rglob('*') if _.is_file())} files under {staging}")

    step("3b. Validate imports: run the assembled staging dir as if it were the submission root")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '.'); import main; "
            "assert callable(main.agent); "
            "r = main.agent({'select': None}); assert isinstance(r, list) and len(r) == 60, r",
        ],
        cwd=str(staging),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"staged main.py failed to run standalone (import isolation check):\n{result.stdout}\n{result.stderr}")
    print("    OK: staged submission runs standalone (no dependency on data/official/ dev path)")

    step("6-7. Create the .tar.gz")
    for pycache in staging.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)

    # Step 3b's import-isolation check runs `main.py` for real, which for a
    # version with a self-compiling native extension (v17: native_bridge.py
    # JIT-compiles cpp/v17_agent.cpp at import time -- see that module's own
    # docstring) triggers a REAL local compile as a side effect, leaving a
    # platform-specific build directory/object file inside staging. That
    # binary is for THIS machine's OS/architecture, never Kaggle's grading
    # container, so shipping it would be dead weight at best -- strip any
    # such residue before creating the archive, mirroring the pycache
    # cleanup immediately above (same "build artifact, not source" logic,
    # generic across any future version with a similar native-compile step).
    # Scoped narrowly and deliberately: `_build/` is the one directory
    # name native_bridge.py's own compiler steps ever write into, and
    # `.obj`/`.pdb` are unambiguous MSVC compiler intermediates that are
    # never legitimately part of a shipped submission -- NOT a blanket
    # `.dll`/`.so` sweep, which would also delete the REQUIRED official
    # engine binary (`cg/cg.dll` / `cg/libcg.so`) bundled from CG_SRC above.
    for build_dir in staging.rglob("_build"):
        if build_dir.is_dir():
            shutil.rmtree(build_dir, ignore_errors=True)
    for ext in (".obj", ".o", ".pdb"):
        for artifact in staging.rglob(f"*{ext}"):
            if artifact.is_file():
                artifact.unlink()

    SUBMISSION_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = SUBMISSION_DIR / f"challenger_{version}_{timestamp}.tar.gz"

    def _exclude_pycache(tarinfo: tarfile.TarInfo):
        if "__pycache__" in tarinfo.name or tarinfo.name.endswith(".pyc"):
            return None
        return tarinfo

    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(staging.iterdir()):
            tar.add(item, arcname=item.name, filter=_exclude_pycache)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"    Created {archive_path} ({size_mb:.2f} MB)")
    if size_mb > SANITY_SIZE_CEILING_MB:
        fail(f"archive size {size_mb:.2f} MB exceeds the {SANITY_SIZE_CEILING_MB} MB sanity ceiling")

    step("8. Inspect the resulting archive")
    with tarfile.open(archive_path, "r:gz") as tar:
        names = tar.getnames()
        top_level_names = {n.split("/")[0] for n in names}
        nested_main = [n for n in names if n.endswith("main.py") and n != "main.py"]
        if "main.py" not in names:
            fail("main.py is not present at the archive's top level")
        if nested_main:
            fail(f"main.py also exists nested (would confuse the grader): {nested_main}")
        expected_top_level = {"main.py", "deck.csv", "cg", "src", "decks"}
        if version in EXTRA_REQUIREMENTS:
            expected_top_level.add("requirements.txt")
        unexpected = top_level_names - expected_top_level
        if unexpected:
            fail(f"unexpected top-level archive entries: {unexpected}")
        for rel in EXTRA_REQUIRED_FILES.get(version, []):
            if rel not in names:
                fail(f"required file missing from final archive: {rel}")
        print(f"    OK: all EXTRA_REQUIRED_FILES present in archive: {EXTRA_REQUIRED_FILES.get(version, [])}")
        print(f"    {len(names)} archive members, top-level entries: {sorted(top_level_names)}")

    print(f"\nPASS. Archive: {archive_path} ({size_mb:.2f} MB)")
    print("NOT uploaded to Kaggle -- this tool only builds the local archive.")
    print(f"Staging dir preserved at {staging} for inspection.")


if __name__ == "__main__":
    main()
