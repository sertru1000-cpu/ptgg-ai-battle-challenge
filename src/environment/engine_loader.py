"""Makes the `cg` engine package importable, in either of two environments:

1. The real Kaggle submission: main.py ships with its own bundled cg/
   directory at the submission archive's top level (see the packaging cells
   in the official sample notebooks, and tools/build_submission_v1.py). In
   the grading sandbox `cg` is importable directly once the submission's own
   directory is on sys.path (main.py adds it) -- no dev-only path exists
   there at all, so this loader must NOT assume data/official/ is present.
2. Local dev: this repo's git-ignored data/official/ copy (competition-use-
   only licensed, never bundled into a public repo) is used instead, purely
   so local tooling (agents run outside a submission, tools/tournament.py,
   analysis scripts) can `import cg...`.

ensure_cg_on_path() tries a plain `import cg` first (path 1) and only falls
back to the dev-only data/official/ path (path 2) if that fails -- this
single function is shared by every agent module in both environments, so it
must work correctly in both rather than hard-assuming dev-only.
"""

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CG_PARENT = _REPO_ROOT / "data" / "official" / "sample_submission" / "sample_submission"


def ensure_cg_on_path() -> None:
    """Idempotently ensure `import cg` will succeed.

    Call this before any `import cg...` / `from cg...` statement.
    """
    if importlib.util.find_spec("cg") is not None:
        return  # already importable (real submission: bundled cg/ alongside main.py)

    if not (_CG_PARENT / "cg").is_dir():
        raise FileNotFoundError(
            f"cg engine package not importable, and no dev-only copy found at "
            f"{_CG_PARENT}. Either this should be running inside a submission "
            "archive that bundles its own cg/ directory, or (local dev) "
            "download the official competition assets from the Kaggle Data "
            "tab first (see docs/environment.md, section 5)."
        )
    p = str(_CG_PARENT)
    if p not in sys.path:
        sys.path.insert(0, p)
