"""Phase 4.7 Section 30-31: build + validate the final Kaggle submission archive.

Assembles a staging directory matching the official required layout
(main.py at the top level, deck.csv, a bundled cg/ package) plus this
project's own src/ package and the decks/ directory main.py's import chain
needs, then tars it exactly per the official instructions
("How to Submit to this Competition" page, fetched live this phase):
`tar -czvf submission.tar.gz *` from inside the staging directory (so main.py
ends up at the archive's top level, not nested).

Steps (Section 30):
1. validate main.py (imports cleanly, defines `agent`)
2. validate deck.csv (60 lines, passes tools/deck_validator.py's real
   battle_start legality check)
3. validate imports (everything main.py transitively needs is bundled)
4. validate required files present
5. validate archive structure (main.py at top level, not nested)
6. validate archive size
7. create final .tar.gz
8. inspect the resulting archive

Never overwrites a previous archive -- each run gets its own timestamped
filename under submission/.
"""

import datetime
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STAGING = REPO / "submission" / "_staging"
SUBMISSION_DIR = REPO / "submission"
CG_SRC = REPO / "data" / "official" / "sample_submission" / "sample_submission" / "cg"

# Kaggle's own stated size limit could not be resolved to a concrete number
# this phase (the "How to Submit" API page returns an unresolved
# ${competition.SubmissionSizeLimit} template placeholder server-side, and
# the open-source kaggle_environments cabt.json env spec doesn't carry
# per-competition resource limits either -- see reports/final_agent_v1.md
# "Competition Constraints" section for the full account). This constant is
# a conservative sanity ceiling, not an authoritative Kaggle limit -- if the
# real archive approaches it, treat that as a signal to investigate, not as
# proof of passing/failing the actual platform check.
SANITY_SIZE_CEILING_MB = 200


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def step(msg: str) -> None:
    print(f"--- {msg}")


def main() -> None:
    step("1. Validate main.py imports cleanly and defines agent()")
    result = subprocess.run(
        [sys.executable, "-c", "import main; assert callable(main.agent); assert len(main.DECK) == 60"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"main.py failed to import cleanly:\n{result.stdout}\n{result.stderr}")
    print("    OK: main.py imports cleanly, agent() defined, DECK has 60 cards")

    step("2. Validate deck.csv (60 lines, real battle_start legality check)")
    result = subprocess.run(
        [sys.executable, "tools/deck_validator.py", "deck.csv"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    print("   ", result.stdout.strip())
    if result.returncode != 0 or "illegal" in result.stdout.lower():
        fail(f"deck.csv failed legality validation:\n{result.stdout}\n{result.stderr}")
    print("    OK: deck.csv is legal")

    step("3-4. Assemble staging directory (validates required files by construction)")
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True)

    shutil.copy2(REPO / "main.py", STAGING / "main.py")
    shutil.copy2(REPO / "deck.csv", STAGING / "deck.csv")

    if not CG_SRC.is_dir():
        fail(f"cg engine package not found at {CG_SRC} -- cannot bundle it")
    shutil.copytree(CG_SRC, STAGING / "cg", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    shutil.copytree(REPO / "src", STAGING / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    decks_dst = STAGING / "decks"
    decks_dst.mkdir()
    shutil.copy2(REPO / "decks" / "dragapult_ex.csv", decks_dst / "dragapult_ex.csv")

    required = ["main.py", "deck.csv", "cg/api.py", "cg/game.py", "src/agents/final_candidate_agent.py", "decks/dragapult_ex.csv"]
    for rel in required:
        if not (STAGING / rel).exists():
            fail(f"required staged file missing: {rel}")
    print(f"    OK: staged {sum(1 for _ in STAGING.rglob('*') if _.is_file())} files under {STAGING}")

    step("3b. Validate imports: run the assembled staging dir as if it were the submission root")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '.'); import main; "
            "assert callable(main.agent); "
            "r = main.agent({'select': None}); assert isinstance(r, list) and len(r) == 60, r",
        ],
        cwd=str(STAGING),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"staged main.py failed to run standalone (import isolation check):\n{result.stdout}\n{result.stderr}")
    print("    OK: staged submission runs standalone (no dependency on data/official/ dev path)")

    step("5. Validate archive structure (main.py must be at the archive top level)")
    # (verified below by inspecting the actual tar members after creation)

    step("6-7. Create the .tar.gz")
    # Step 3b's standalone-import check runs `python` with cwd=STAGING, which
    # writes its own __pycache__/*.pyc directly into STAGING as a side
    # effect -- strip it (and any other __pycache__ that snuck in) before
    # archiving so the tar only contains intentionally-staged files.
    for pycache in STAGING.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)

    SUBMISSION_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = SUBMISSION_DIR / f"submission_{timestamp}.tar.gz"

    def _exclude_pycache(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
        if "__pycache__" in tarinfo.name or tarinfo.name.endswith(".pyc"):
            return None
        return tarinfo

    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(STAGING.iterdir()):
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
        unexpected = top_level_names - expected_top_level
        if unexpected:
            fail(f"unexpected top-level archive entries: {unexpected}")
        print(f"    {len(names)} archive members, top-level entries: {sorted(top_level_names)}")

    print(f"\nPASS. Archive: {archive_path} ({size_mb:.2f} MB)")
    print(f"Staging dir preserved at {STAGING} for inspection (not committed, not archived twice).")


if __name__ == "__main__":
    main()
