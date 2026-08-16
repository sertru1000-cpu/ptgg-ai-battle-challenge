"""Native C++ MCTS bridge for V20 (V18 + Block B: B1 learned P(win) eval in
static C++ arrays, B2 PUCT priors, B3 determinization voting -- see
cpp/pwin_trees.hpp, cpp/vectorizer.hpp, mcts.hpp's McTsConfig, and
V17_ROADMAP.md). See README.md for the full architecture
and the call-chain diagram (Python is only ever touched once per real
decision -- see cpp/mcts.hpp's own header for why).

This module:
  1. Compiles cpp/v17_agent.cpp on first import if a cached library isn't
     already present (Objective 3 -- compiled ON the machine that will
     actually run it, since this dev machine has no C++ toolchain at all to
     produce a portable prebuilt binary from; see README.md's "Compilation"
     section for why that's the deliberate choice, not a workaround).
  2. Defines the ctypes mirror of cpp/v17_abi.h, byte-for-byte
     (`_pack_ = 1` on both sides -- see that header's own comment on why).
  3. Flattens a live Observation into that struct, reusing V6's own exact
     bookkeeping (prize-guess / deck-count / pre_turn_log tracking, ported
     here nearly verbatim from dragapult_policy_v6.py's DragapultPolicy
     rather than reimplemented in C++ -- see _Bookkeeping's docstring).
  4. Calls into the native library and reports failure via a plain return
     value (never raises) so the caller (agent.py) can fall back to the
     full pure-Python V6 agent on ANY problem -- library missing, compile
     failure, init failure, or a per-decision native error.
"""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

import cg  # noqa: E402  -- only to locate the native cg.dll/libcg.so path
from cg.api import (  # noqa: E402
    AreaType,
    Log,
    LogType,
    Observation,
    Pokemon,
    to_observation_class,
)

import src.agents.dragapult_policy_v6 as _v6  # noqa: E402 -- DECK + pure-Python fallback agent
from src.agents.dragapult_agent_v22_cpp import opponent_model  # noqa: E402 -- Block A1

DECK = _v6.DECK  # V18 plays V6's exact decklist (same lineage as V17)

# Per-decision wall-clock budget handed to the native MCTS. Raised from the
# original 1200.0 to 800.0 for the "deep search" experiment -- counter-
# intuitively a REDUCTION, not an increase: the original 1200ms budget was
# never actually being spent (see LAST_CALL_STATS/mcts.hpp's out_visits --
# instrumented specifically to check this rather than assume it). 800ms is
# still comfortably inside timeout_shield.PER_DECISION_BUDGET_SECONDS=2.0s
# (the outer hard cap applied by final_candidate_agent_v17.py, identical
# composition to V11's final_candidate_agent_v11.py), leaving >1.2s headroom
# for this module's own flattening/ctypes/compile-check overhead on top of
# the native call itself.
TIME_BUDGET_MS = 1500.0  # 800 -> 1500 (2026-08-14 tuning iteration 2): ~2x simulations per decision;
                          # still leaves ~0.5s headroom under timeout_shield's 2.0s per-decision cap
                          # (searched decisions measured ~0.7s at the 800ms setting, scaling linearly)

_PKG_DIR = Path(__file__).resolve().parent  # .../dragapult_agent_v17_cpp
_CPP_DIR = _PKG_DIR / "cpp"
_BUILD_DIR = _PKG_DIR / "_build"
_SOURCE = _CPP_DIR / "v17_agent.cpp"

# --- ctypes mirror of cpp/v17_abi.h -- keep field-for-field identical to
# that header (same order, same c_int32 width, same array capacities,
# _pack_ = 1 matching its #pragma pack(push, 1)). See that file's own
# comment for why this contract must never drift between the two sides
# without updating both. ---

V17_MAX_ENERGIES = 12
V17_MAX_TOOLS = 4
V17_MAX_PRE_EVO = 3
V17_MAX_BENCH = 8
V17_MAX_HAND = 20
V17_MAX_DISCARD = 64
V17_MAX_DECK_DISTINCT = 60
V17_MAX_PRIZE = 8
V17_MAX_OPTIONS = 200
V17_MAX_SELECT_DECK = 60
V17_MAX_LOOKING = 20
V17_MAX_OPP_POOL = 60
V17_ABI_MAGIC = 0x56323041  # "V20A" -- bumped for the B1-vectorizer fields (Block B)


class V17PokemonC(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("present", ctypes.c_int32),
        ("faceDown", ctypes.c_int32),
        ("id", ctypes.c_int32),
        ("serial", ctypes.c_int32),
        ("hp", ctypes.c_int32),
        ("maxHp", ctypes.c_int32),
        ("appearThisTurn", ctypes.c_int32),
        ("energiesCount", ctypes.c_int32),
        ("energies", ctypes.c_int32 * V17_MAX_ENERGIES),
        ("energyCardsCount", ctypes.c_int32),
        ("energyCardIds", ctypes.c_int32 * V17_MAX_ENERGIES),
        ("toolsCount", ctypes.c_int32),
        ("toolIds", ctypes.c_int32 * V17_MAX_TOOLS),
        ("preEvoCount", ctypes.c_int32),
        ("preEvoIds", ctypes.c_int32 * V17_MAX_PRE_EVO),
    ]


class V17CardC(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("id", ctypes.c_int32),
        ("serial", ctypes.c_int32),
        ("playerIndex", ctypes.c_int32),
    ]


class V17OptionC(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_int32),
        ("number", ctypes.c_int32),
        ("area", ctypes.c_int32),
        ("index", ctypes.c_int32),
        ("playerIndex", ctypes.c_int32),
        ("toolIndex", ctypes.c_int32),
        ("energyIndex", ctypes.c_int32),
        ("count", ctypes.c_int32),
        ("inPlayArea", ctypes.c_int32),
        ("inPlayIndex", ctypes.c_int32),
        ("attackId", ctypes.c_int32),
        ("cardId", ctypes.c_int32),
        ("serial", ctypes.c_int32),
        ("specialConditionType", ctypes.c_int32),
    ]


class V17RootObservationC(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("abi_magic", ctypes.c_int32),
        ("myIndex", ctypes.c_int32),
        ("turn", ctypes.c_int32),
        ("firstPlayer", ctypes.c_int32),
        ("supporterPlayed", ctypes.c_int32),
        ("stadiumPlayed", ctypes.c_int32),
        ("energyAttached", ctypes.c_int32),
        ("retreated", ctypes.c_int32),
        ("result", ctypes.c_int32),
        ("stadiumCardId", ctypes.c_int32),
        ("selectType", ctypes.c_int32),
        ("context", ctypes.c_int32),
        ("minCount", ctypes.c_int32),
        ("maxCount", ctypes.c_int32),
        ("remainDamageCounter", ctypes.c_int32),
        ("remainEnergyCost", ctypes.c_int32),
        ("contextCardId", ctypes.c_int32),
        ("effectCardId", ctypes.c_int32),
        ("myDeckCount", ctypes.c_int32),
        ("oppDeckCount", ctypes.c_int32),
        ("myPrizeCount", ctypes.c_int32),
        ("oppPrizeCount", ctypes.c_int32),
        ("oppHandCount", ctypes.c_int32),
        ("myPoisoned", ctypes.c_int32),
        ("myBurned", ctypes.c_int32),
        ("myAsleep", ctypes.c_int32),
        ("myParalyzed", ctypes.c_int32),
        ("myConfused", ctypes.c_int32),
        ("preKo", ctypes.c_int32),
        ("noItem", ctypes.c_int32),
        ("myActive", V17PokemonC),
        ("oppActive", V17PokemonC),
        ("myBenchCount", ctypes.c_int32),
        ("myBench", V17PokemonC * V17_MAX_BENCH),
        ("oppBenchCount", ctypes.c_int32),
        ("oppBench", V17PokemonC * V17_MAX_BENCH),
        ("myHandCount", ctypes.c_int32),
        ("myHand", V17CardC * V17_MAX_HAND),
        ("myDiscardCount", ctypes.c_int32),
        ("myDiscard", V17CardC * V17_MAX_DISCARD),
        ("selectDeckCount", ctypes.c_int32),
        ("selectDeck", V17CardC * V17_MAX_SELECT_DECK),
        ("myPrizeCardsCount", ctypes.c_int32),
        ("myPrizeCards", V17CardC * V17_MAX_PRIZE),
        ("lookingCount", ctypes.c_int32),
        ("looking", V17CardC * V17_MAX_LOOKING),
        ("deckDistinctCount", ctypes.c_int32),
        ("deckIds", ctypes.c_int32 * V17_MAX_DECK_DISTINCT),
        ("deckCounts", ctypes.c_int32 * V17_MAX_DECK_DISTINCT),
        ("myPrizeGuessCount", ctypes.c_int32),
        ("myPrizeGuessIds", ctypes.c_int32 * V17_MAX_PRIZE),
        ("optionCount", ctypes.c_int32),
        ("options", V17OptionC * V17_MAX_OPTIONS),
        ("oppHiddenPoolCount", ctypes.c_int32),
        ("oppHiddenPoolIds", ctypes.c_int32 * V17_MAX_OPP_POOL),
        ("turnActionCount", ctypes.c_int32),
        ("oppDiscardCount", ctypes.c_int32),
        ("oppPoisoned", ctypes.c_int32),
        ("oppBurned", ctypes.c_int32),
        ("oppAsleep", ctypes.c_int32),
        ("oppParalyzed", ctypes.c_int32),
        ("oppConfused", ctypes.c_int32),
    ]


# --- build / load ---

_native_lib_cache_checked = False
_native_lib = None  # loaded+initialized ctypes.CDLL, or None if unavailable


def _native_lib_filename() -> str:
    system = platform.system()
    if system == "Windows":
        return "v22_mcts.dll"
    if system == "Darwin":
        return "libv22_mcts.dylib"
    return "libv22_mcts.so"


def _find_vcvars64() -> Optional[Path]:
    """Locates vcvars64.bat via vswhere.exe (the standard, documented way to
    find a Visual Studio install without guessing version-numbered paths).
    Returns None if no VS/Build Tools C++ toolchain is installed -- a normal,
    expected outcome, not an error (most machines, including Kaggle's own
    grading container, won't have this and are meant to use g++ instead)."""
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if not vswhere.exists():
        return None
    try:
        result = subprocess.run(
            [
                str(vswhere), "-latest", "-products", "*", "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath",
            ],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    install_path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not install_path:
        return None
    vcvars = Path(install_path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    return vcvars if vcvars.exists() else None


def _compile_with_msvc(out_path: Path) -> bool:
    """Windows local-testing path (Objective 3's "Smart JIT Wrapper" --
    MSVC on Windows, g++ on Linux): loads the VS Build Tools x64 environment
    via vcvars64.bat and invokes cl.exe in the SAME shell (vcvars64.bat only
    sets up PATH/INCLUDE/LIB env vars for the process that sources it --
    calling cl.exe from a separate subprocess afterward would not see them).

    Runs both steps through a small temporary .bat file rather than a single
    `cmd.exe /c "<quoted path> && ..."` string -- empirically hit cmd.exe's
    well-known nested-quoting pitfall doing it that way (a quoted first
    token inside an already-quoted /c argument gets mis-parsed; cmd reports
    the vcvars64.bat path itself as "not recognized"). A batch file sidesteps
    the ambiguity entirely: `cmd /c <path-to-bat>` has only one argument to
    parse, and `call "path with spaces"` inside the .bat is unambiguous
    standard batch syntax.

    /LD builds a DLL; /EHsc enables standard C++ exception handling (off by
    default under MSVC); NOMINMAX is already handled in cg_engine.hpp itself
    (not here), since <windows.h>'s min/max macros were the actual empirical
    cause of the first compile failure hit during development."""
    vcvars = _find_vcvars64()
    if vcvars is None:
        return False
    bat_path = _BUILD_DIR / "_v17_msvc_build.bat"
    bat_path.write_text(
        "@echo off\r\n"
        f'call "{vcvars}" >nul\r\n'
        "if errorlevel 1 exit /b 1\r\n"
        f'cl.exe /EHsc /std:c++17 /O2 /nologo /LD /Fe:"{out_path}" v17_agent.cpp\r\n'
    )
    try:
        result = subprocess.run(["cmd.exe", "/c", str(bat_path)], cwd=str(_CPP_DIR), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"V17: could not invoke MSVC ({exc!r}).\n")
        return False
    finally:
        try:
            bat_path.unlink()
        except OSError:
            pass
    if result.returncode != 0 or not out_path.exists():
        sys.stderr.write(f"V17: MSVC compilation failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}\n")
        return False
    return True


def _compile_with_gxx(out_path: Path) -> bool:
    """The real deployment path: Kaggle's grading container is Linux (see
    README.md), so this is what actually matters for a real submission --
    the MSVC path above exists purely for local Windows testing convenience."""
    system = platform.system()
    if system == "Windows":
        # g++ on Windows (MinGW) as a fallback if MSVC isn't available either
        # -- untested from this dev machine (which has MSVC, not MinGW), kept
        # for completeness since some Windows dev setups use MinGW instead.
        cmd = ["g++", "-O3", "-shared", "-std=c++17", "-o", str(out_path), "v17_agent.cpp"]
    else:
        cmd = ["g++", "-O3", "-shared", "-fPIC", "-std=c++17", "-o", str(out_path), "v17_agent.cpp", "-ldl"]
    try:
        result = subprocess.run(cmd, cwd=str(_CPP_DIR), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"V17: could not invoke g++ ({exc!r}).\n")
        return False
    if result.returncode != 0 or not out_path.exists():
        sys.stderr.write(
            f"V17: g++ compilation failed:\ncommand: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}\n"
        )
        return False
    return True


def _cg_native_lib_path() -> str:
    """Mirrors cg/sim.py's own platform -> filename logic exactly (that
    module is the ground truth for which binary ships next to cg/api.py)."""
    system = platform.system()
    cg_dir = Path(cg.__file__).resolve().parent
    if system == "Windows":
        name = "cg.dll"
    elif system == "Darwin":
        name = "libcg.dylib"
    elif platform.machine() in ("arm64", "aarch64"):
        name = "libcg-arm64.so"
    else:
        name = "libcg.so"
    return str(cg_dir / name)


def _ensure_native_library_built() -> Optional[Path]:
    """Returns a usable compiled-library path, or None if compilation is
    unavailable/failed -- caller must use the pure-Python fallback. Compiles
    at most once per process; reuses a previously-built file across
    processes sharing the same _build/ directory as long as it is newer than
    the source (a stale build is simply recompiled, never silently reused).

    Compiler selection (Objective 3's "Smart JIT Wrapper"): on Windows
    (`os.name == "nt"`, i.e. local testing -- this dev machine specifically,
    verified working this way, see README.md) try MSVC first via cl.exe,
    since that's what's actually installed here and on most Windows dev
    boxes; fall back to g++ (MinGW) if MSVC isn't found. On every other OS
    (`os.name == "posix"` -- Linux, which is what Kaggle's grading container
    actually runs) go straight to g++, the only realistic option there."""
    try:
        _BUILD_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _BUILD_DIR / _native_lib_filename()

        needs_build = True
        if out_path.exists() and _SOURCE.exists() and out_path.stat().st_mtime >= _SOURCE.stat().st_mtime:
            needs_build = False

        if needs_build:
            built = False
            if os.name == "nt":
                built = _compile_with_msvc(out_path)
                if not built:
                    built = _compile_with_gxx(out_path)
            else:
                built = _compile_with_gxx(out_path)

            if not built:
                sys.stderr.write("V17: native library compilation failed; falling back to pure-Python V6 for the whole match.\n")
                return None

        return out_path
    except Exception as exc:  # noqa: BLE001 -- must never propagate from lazy init
        sys.stderr.write(f"V17: native library build step raised {exc!r}; falling back to pure-Python V6.\n")
        return None


def _load_native_library():
    lib_path = _ensure_native_library_built()
    if lib_path is None:
        return None
    try:
        lib = ctypes.CDLL(str(lib_path))
        lib.v17_init.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32), ctypes.c_int32]
        lib.v17_init.restype = ctypes.c_int32
        lib.v17_choose_action.argtypes = [
            ctypes.POINTER(V17RootObservationC),
            ctypes.c_char_p,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),  # out_eligible
            ctypes.POINTER(ctypes.c_int32),  # out_search_begin_ok
            ctypes.POINTER(ctypes.c_int32),  # out_visits
            ctypes.POINTER(ctypes.c_int32),  # out_greedy_index
            ctypes.POINTER(ctypes.c_int32),  # out_mcts_index
            ctypes.POINTER(ctypes.c_int32),  # out_hit_terminal_reward
            ctypes.POINTER(ctypes.c_int32),  # out_begin_fail_count
            ctypes.POINTER(ctypes.c_int32),  # out_begin_last_error
        ]
        lib.v17_choose_action.restype = ctypes.c_int32

        deck_arr = (ctypes.c_int32 * len(DECK))(*DECK)
        rc = lib.v17_init(_cg_native_lib_path().encode("utf-8"), deck_arr, len(DECK))
        if rc != 0:
            sys.stderr.write(f"V17: v17_init returned error code {rc}; falling back to pure-Python V6.\n")
            return None
        return lib
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"V17: failed to load/initialize native library: {exc!r}\n")
        return None


def get_native_lib():
    """Builds/loads/inits the native library exactly once per process;
    returns None (cached) forever after on any failure.

    CRITICAL: this is invoked eagerly at module import time (bottom of this
    file), NOT lazily on first use. Compilation alone can take real seconds
    (a from-scratch g++ invocation, possibly the first C++ compile this
    process has ever triggered) -- if that cost landed on the first real
    decision instead, it would run INSIDE
    final_candidate_agent_v17.py's timeout_shield wrapper, which gives each
    decision only PER_DECISION_BUDGET_SECONDS=2.0s on a single-worker
    thread pool. Blowing that budget would not just degrade one decision:
    timeout_shield's single worker stays busy finishing the abandoned
    compile in the background, so every OTHER decision queued behind it
    would ALSO degrade to the crude legal-fallback selector until the
    compile finally finishes -- silently costing several real moves at the
    start of every single match. Running this at import time (before
    kaggle_environments ever calls agent(), and therefore before any
    per-decision clock is running against it) avoids that failure mode
    entirely.
    """
    global _native_lib_cache_checked, _native_lib
    if not _native_lib_cache_checked:
        _native_lib_cache_checked = True
        _native_lib = _load_native_library()
    return _native_lib


get_native_lib()  # eager, at import time -- see docstring above


# --- V6 bookkeeping (verbatim port of the small stateful slice of
# dragapult_policy_v6.py's DragapultPolicy this bridge needs) ---


class _Bookkeeping:
    """Ports exactly the cross-call state dragapult_policy_v6.py's
    DragapultPolicy carries that V6Scorer needs but cannot cheaply
    reconstruct from a single Observation: `self.prize` (an identity guess
    for our own prize cards, fixed once at the deck-declare call and held
    constant after -- see that class's own docstring) and the
    pre_turn_log-derived pre_ko/no_item flags. `card_counts`/`serial_set`
    (`add_card_count`/`set_card_counts` below) are recomputed fresh every
    call, exactly like the original -- not persisted.

    One instance persists for the whole process, matching the one live
    DragapultPolicy instance V6/V11 construct per agent identity.
    """

    def __init__(self) -> None:
        self.prize: list[int] = []
        self.pre_turn_log: list[Log] = []
        self.current_turn_log: list[Log] = []
        self.card_counts: "defaultdict[int, int]" = defaultdict(int)
        self.serial_set: set[int] = set()

    def add_card_count(self, card, my_index: int) -> None:
        if card is None:
            return
        if isinstance(card, Pokemon) or card.playerIndex == my_index:
            if card.serial not in self.serial_set:
                self.card_counts[card.id] -= 1
                self.serial_set.add(card.serial)
        if isinstance(card, Pokemon):
            for c in card.energyCards:
                self.add_card_count(c, my_index)
            for c in card.tools:
                self.add_card_count(c, my_index)
            for c in card.preEvolution:
                self.add_card_count(c, my_index)

    def set_card_counts(self, obs: Observation, my_index: int) -> None:
        self.card_counts.clear()
        self.serial_set.clear()
        for cid in DECK:
            self.card_counts[cid] += 1
        state = obs.current
        my_state = state.players[my_index]
        for card in my_state.hand:
            self.add_card_count(card, my_index)
        for card in my_state.discard:
            self.add_card_count(card, my_index)
        for card in my_state.bench:
            self.add_card_count(card, my_index)
        for card in my_state.active:
            self.add_card_count(card, my_index)
        for card in state.stadium:
            self.add_card_count(card, my_index)
        if state.looking is not None:
            for card in state.looking:
                self.add_card_count(card, my_index)
        self.add_card_count(obs.select.effect, my_index)

    def update(self, obs: Observation, my_index: int) -> None:
        """Call once per real decision, before reading deck_counts()/prize.
        After this returns, self.card_counts IS the deck_counts to hand the
        native struct (mirrors dragapult_policy_v6.py's `agent()` preamble
        exactly, statement for statement)."""
        state = obs.current
        if state.turn == 0:
            self.prize.clear()
            self.pre_turn_log.clear()
            self.current_turn_log.clear()
        else:
            for log in obs.logs:
                self.current_turn_log.append(log)
                if log.type == LogType.TURN_END:
                    self.pre_turn_log = self.current_turn_log
                    self.current_turn_log = []

        if obs.select.deck is not None:
            self.set_card_counts(obs, my_index)
            for card in obs.select.deck:
                self.card_counts[card.id] -= 1
            self.prize.clear()
            for cid in self.card_counts:
                for _ in range(self.card_counts[cid]):
                    self.prize.append(cid)

        self.set_card_counts(obs, my_index)
        for cid in self.prize:
            self.card_counts[cid] -= 1

    def pre_ko_and_no_item(self, my_index: int) -> tuple[bool, bool]:
        pre_ko = False
        no_item = False
        for log in self.pre_turn_log:
            if log.type == LogType.ATTACK:
                if log.attackId == 323:  # Itchy Pollen
                    no_item = True
            elif log.type == LogType.MOVE_CARD:
                if (
                    log.playerIndex == my_index
                    and (log.fromArea == AreaType.BENCH or log.fromArea == AreaType.ACTIVE)
                    and log.toArea == AreaType.DISCARD
                ):
                    pre_ko = True
        return pre_ko, no_item


# --- flattening: Observation -> V17RootObservationC ---


# Cumulative per-process classification tally (family label -> decision
# count), for local diagnostics only (tools/meta_gauntlet_v18.py reads and
# resets it per game to verify the classifier actually fires against each
# gauntlet deck). Never read on the Kaggle path.
CLASSIFICATION_COUNTS: dict = {}


def _opponent_visible_counter(state, my_index: int) -> Counter:
    """Multiset of every opponent card id we can legitimately see: their
    active/bench Pokemon with attached energies/tools/pre-evolutions, their
    discard pile (public zone -- the half of Block A1 V17 never used), and
    their stadium if one of theirs is in play. Opponent hand/deck/prizes are
    hidden and never touched (only their counts are, elsewhere)."""
    opp_index = 1 - my_index
    opp_state = state.players[opp_index]
    vis: Counter = Counter()

    def add_pokemon(p) -> None:
        if p is None:  # face-down active slot
            return
        vis[p.id] += 1
        for card in p.energyCards:
            vis[card.id] += 1
        for card in p.tools:
            vis[card.id] += 1
        for card in p.preEvolution:
            vis[card.id] += 1

    for p in opp_state.active:
        add_pokemon(p)
    for p in opp_state.bench:
        add_pokemon(p)
    for card in opp_state.discard:
        vis[card.id] += 1
    for card in state.stadium:
        if card.playerIndex == opp_index:
            vis[card.id] += 1
    return vis


def _fill_pokemon_c(dst: "V17PokemonC", pokemon) -> None:
    """`pokemon` must already be None-collapsed by the caller (i.e.
    `active[0] if active else None`) -- V6 never distinguishes "no active"
    from "active but face-down" (both come out of cg.api as the same
    `None`), so this never sets faceDown=1 from the Python side; the
    distinction only exists on the C++ side for nodes built from the
    engine's own SearchStep JSON during rollout (see observation.hpp)."""
    if pokemon is None:
        dst.present = 0
        dst.faceDown = 0
        return
    dst.present = 1
    dst.faceDown = 0
    dst.id = pokemon.id
    dst.serial = pokemon.serial
    dst.hp = pokemon.hp
    dst.maxHp = pokemon.maxHp
    dst.appearThisTurn = 1 if pokemon.appearThisTurn else 0
    n = min(len(pokemon.energies), V17_MAX_ENERGIES)
    dst.energiesCount = n
    for i in range(n):
        dst.energies[i] = int(pokemon.energies[i])
    n = min(len(pokemon.energyCards), V17_MAX_ENERGIES)
    dst.energyCardsCount = n
    for i in range(n):
        dst.energyCardIds[i] = pokemon.energyCards[i].id
    n = min(len(pokemon.tools), V17_MAX_TOOLS)
    dst.toolsCount = n
    for i in range(n):
        dst.toolIds[i] = pokemon.tools[i].id
    n = min(len(pokemon.preEvolution), V17_MAX_PRE_EVO)
    dst.preEvoCount = n
    for i in range(n):
        dst.preEvoIds[i] = pokemon.preEvolution[i].id


def flatten_observation(obs: Observation, bookkeeping: _Bookkeeping) -> "V17RootObservationC":
    """Requires obs.select is not None (deck-declare is handled by the
    caller before this is ever invoked -- see agent.py)."""
    state = obs.current
    select = obs.select
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    bookkeeping.update(obs, my_index)
    pre_ko, no_item = bookkeeping.pre_ko_and_no_item(my_index)

    c = V17RootObservationC()
    ctypes.memset(ctypes.byref(c), 0, ctypes.sizeof(c))
    c.abi_magic = V17_ABI_MAGIC

    c.myIndex = my_index
    c.turn = state.turn
    c.firstPlayer = state.firstPlayer
    c.supporterPlayed = 1 if state.supporterPlayed else 0
    c.stadiumPlayed = 1 if state.stadiumPlayed else 0
    c.energyAttached = 1 if state.energyAttached else 0
    c.retreated = 1 if state.retreated else 0
    c.result = state.result if state.result is not None else -1
    c.stadiumCardId = state.stadium[0].id if state.stadium else 0

    c.selectType = int(select.type)
    c.context = int(select.context)
    c.minCount = select.minCount
    c.maxCount = select.maxCount
    c.remainDamageCounter = select.remainDamageCounter
    c.remainEnergyCost = select.remainEnergyCost
    c.contextCardId = select.contextCard.id if select.contextCard is not None else 0
    c.effectCardId = select.effect.id if select.effect is not None else 0

    c.myDeckCount = my_state.deckCount
    c.oppDeckCount = op_state.deckCount
    c.myPrizeCount = len(my_state.prize)
    c.oppPrizeCount = len(op_state.prize)
    c.oppHandCount = op_state.handCount

    c.myPoisoned = 1 if my_state.poisoned else 0
    c.myBurned = 1 if my_state.burned else 0
    c.myAsleep = 1 if my_state.asleep else 0
    c.myParalyzed = 1 if my_state.paralyzed else 0
    c.myConfused = 1 if my_state.confused else 0

    c.preKo = 1 if pre_ko else 0
    c.noItem = 1 if no_item else 0

    # V20 (B1 vectorizer fields)
    c.turnActionCount = state.turnActionCount
    c.oppDiscardCount = len(op_state.discard)
    c.oppPoisoned = 1 if op_state.poisoned else 0
    c.oppBurned = 1 if op_state.burned else 0
    c.oppAsleep = 1 if op_state.asleep else 0
    c.oppParalyzed = 1 if op_state.paralyzed else 0
    c.oppConfused = 1 if op_state.confused else 0

    _fill_pokemon_c(c.myActive, my_state.active[0] if my_state.active else None)
    _fill_pokemon_c(c.oppActive, op_state.active[0] if op_state.active else None)

    n = min(len(my_state.bench), V17_MAX_BENCH)
    c.myBenchCount = n
    for i in range(n):
        _fill_pokemon_c(c.myBench[i], my_state.bench[i])
    n = min(len(op_state.bench), V17_MAX_BENCH)
    c.oppBenchCount = n
    for i in range(n):
        _fill_pokemon_c(c.oppBench[i], op_state.bench[i])

    hand = my_state.hand or []
    n = min(len(hand), V17_MAX_HAND)
    c.myHandCount = n
    for i in range(n):
        c.myHand[i].id = hand[i].id
        c.myHand[i].serial = hand[i].serial
        c.myHand[i].playerIndex = hand[i].playerIndex

    n = min(len(my_state.discard), V17_MAX_DISCARD)
    c.myDiscardCount = n
    for i in range(n):
        c.myDiscard[i].id = my_state.discard[i].id
        c.myDiscard[i].serial = my_state.discard[i].serial
        c.myDiscard[i].playerIndex = my_state.discard[i].playerIndex

    select_deck = select.deck or []
    n = min(len(select_deck), V17_MAX_SELECT_DECK)
    c.selectDeckCount = n
    for i in range(n):
        c.selectDeck[i].id = select_deck[i].id
        c.selectDeck[i].serial = select_deck[i].serial
        c.selectDeck[i].playerIndex = select_deck[i].playerIndex

    # my_state.prize / state.looking are `list[Card | None]` -- a None entry
    # (face-down/unrevealed) is encoded as id=0 at its ORIGINAL index
    # (never skipped/compacted: Option.index must keep referring to the same
    # position cg.api itself uses).
    n = min(len(my_state.prize), V17_MAX_PRIZE)
    c.myPrizeCardsCount = n
    for i in range(n):
        card = my_state.prize[i]
        if card is not None:
            c.myPrizeCards[i].id = card.id
            c.myPrizeCards[i].serial = card.serial
            c.myPrizeCards[i].playerIndex = card.playerIndex

    looking = state.looking or []
    n = min(len(looking), V17_MAX_LOOKING)
    c.lookingCount = n
    for i in range(n):
        card = looking[i]
        if card is not None:
            c.looking[i].id = card.id
            c.looking[i].serial = card.serial
            c.looking[i].playerIndex = card.playerIndex

    deck_items = [(cid, cnt) for cid, cnt in bookkeeping.card_counts.items()]
    n = min(len(deck_items), V17_MAX_DECK_DISTINCT)
    c.deckDistinctCount = n
    for i in range(n):
        c.deckIds[i] = deck_items[i][0]
        c.deckCounts[i] = deck_items[i][1]

    n = min(len(bookkeeping.prize), V17_MAX_PRIZE)
    c.myPrizeGuessCount = n
    for i in range(n):
        c.myPrizeGuessIds[i] = bookkeeping.prize[i]

    # Block A1: archetype-conditioned opponent hidden-zone pool (canonical 60
    # of the classified archetype -- or our own DECK on fallback -- minus
    # everything of theirs visible, including their discard).
    visible = _opponent_visible_counter(state, my_index)
    pool, family, variant = opponent_model.build_hidden_pool(visible, DECK)
    n = min(len(pool), V17_MAX_OPP_POOL)
    c.oppHiddenPoolCount = n
    for i in range(n):
        c.oppHiddenPoolIds[i] = pool[i]
    LAST_CALL_STATS["opp_archetype"] = family
    LAST_CALL_STATS["opp_archetype_variant"] = variant
    CLASSIFICATION_COUNTS[family] = CLASSIFICATION_COUNTS.get(family, 0) + 1

    n = min(len(select.option), V17_MAX_OPTIONS)
    c.optionCount = n
    for i in range(n):
        o = select.option[i]
        dst = c.options[i]
        dst.type = int(o.type)
        dst.number = o.number if o.number is not None else -1
        dst.area = int(o.area) if o.area is not None else -1
        dst.index = o.index if o.index is not None else -1
        dst.playerIndex = o.playerIndex if o.playerIndex is not None else -1
        dst.toolIndex = o.toolIndex if o.toolIndex is not None else -1
        dst.energyIndex = o.energyIndex if o.energyIndex is not None else -1
        dst.count = o.count if o.count is not None else -1
        dst.inPlayArea = int(o.inPlayArea) if o.inPlayArea is not None else -1
        dst.inPlayIndex = o.inPlayIndex if o.inPlayIndex is not None else -1
        dst.attackId = o.attackId if o.attackId is not None else -1
        dst.cardId = o.cardId if o.cardId is not None else -1
        dst.serial = o.serial if o.serial is not None else -1
        dst.specialConditionType = int(o.specialConditionType) if o.specialConditionType is not None else -1

    return c


_bookkeeping = _Bookkeeping()

# Diagnostics from the most recent native_choose_action() call -- added for
# the deep-search-budget experiment so callers (e.g. tools/stress_test_v17.py)
# can report real per-decision search behavior (was this decision even
# eligible for search, did search_begin succeed, how many UCB1
# simulations/rollouts actually ran) without changing native_choose_action's
# own return contract. Same "expose a plain mutable dict" convention as
# safety_wrapper.py/timeout_shield.py's `.stats`. Overwritten every call
# (including calls that never reach the native path at all, e.g. lib is
# None, or the IS_FIRST short-circuit in agent.py which never calls this
# function) -- reset to the "nothing ran" defaults at the top of every call
# that does reach here so a stale prior value is never misread.
LAST_CALL_STATS: dict = {
    "eligible": False,
    "search_begin_ok": False,
    "visits": 0,
    "greedy_index": -1,
    "mcts_index": -1,
    "hit_terminal_reward": False,
    "opp_archetype": None,          # Block A1: family label, or "MIRROR_FALLBACK"
    "opp_archetype_variant": None,  # Block A1: which canonical variant matched
    "begin_fail_count": 0,          # search_begin failures across determinizations this call
    "begin_last_error": 0,          # engine error code from the most recent failure
}


def native_choose_action(obs_dict: dict) -> Optional[list[int]]:
    """Returns the chosen option indices, or None if the native path is
    unavailable/failed for this call (caller must fall back to pure-Python
    V6). `obs_dict.get("select")` must not be None (deck-declare is handled
    entirely by the caller, see agent.py)."""
    lib = get_native_lib()
    LAST_CALL_STATS["eligible"] = False
    LAST_CALL_STATS["search_begin_ok"] = False
    LAST_CALL_STATS["visits"] = 0
    LAST_CALL_STATS["greedy_index"] = -1
    LAST_CALL_STATS["mcts_index"] = -1
    LAST_CALL_STATS["hit_terminal_reward"] = False
    LAST_CALL_STATS["opp_archetype"] = None
    LAST_CALL_STATS["opp_archetype_variant"] = None
    LAST_CALL_STATS["begin_fail_count"] = 0
    LAST_CALL_STATS["begin_last_error"] = 0
    if lib is None:
        return None

    try:
        obs = to_observation_class(obs_dict)
        c_obs = flatten_observation(obs, _bookkeeping)

        sbi = obs.search_begin_input
        sbi_bytes = sbi.encode("ascii") if sbi else b""

        out_indices = (ctypes.c_int32 * 16)()
        out_count = ctypes.c_int32(0)
        out_eligible = ctypes.c_int32(0)
        out_search_begin_ok = ctypes.c_int32(0)
        out_visits = ctypes.c_int32(0)
        out_greedy_index = ctypes.c_int32(-1)
        out_mcts_index = ctypes.c_int32(-1)
        out_hit_terminal_reward = ctypes.c_int32(0)
        out_begin_fail_count = ctypes.c_int32(0)
        out_begin_last_error = ctypes.c_int32(0)

        rc = lib.v17_choose_action(
            ctypes.byref(c_obs),
            sbi_bytes,
            len(sbi_bytes),
            ctypes.c_double(TIME_BUDGET_MS),
            out_indices,
            len(out_indices),
            ctypes.byref(out_count),
            ctypes.byref(out_eligible),
            ctypes.byref(out_search_begin_ok),
            ctypes.byref(out_visits),
            ctypes.byref(out_greedy_index),
            ctypes.byref(out_mcts_index),
            ctypes.byref(out_hit_terminal_reward),
            ctypes.byref(out_begin_fail_count),
            ctypes.byref(out_begin_last_error),
        )
        LAST_CALL_STATS["eligible"] = bool(out_eligible.value)
        LAST_CALL_STATS["search_begin_ok"] = bool(out_search_begin_ok.value)
        LAST_CALL_STATS["visits"] = int(out_visits.value)
        LAST_CALL_STATS["greedy_index"] = int(out_greedy_index.value)
        LAST_CALL_STATS["mcts_index"] = int(out_mcts_index.value)
        LAST_CALL_STATS["hit_terminal_reward"] = bool(out_hit_terminal_reward.value)
        LAST_CALL_STATS["begin_fail_count"] = int(out_begin_fail_count.value)
        LAST_CALL_STATS["begin_last_error"] = int(out_begin_last_error.value)
        if rc != 0:
            sys.stderr.write(f"V17: v17_choose_action returned error code {rc}; falling back to pure-Python V6 for this decision.\n")
            return None
        return [int(out_indices[i]) for i in range(out_count.value)]
    except Exception as exc:  # noqa: BLE001 -- must never propagate: caller needs a clean None to fall back on
        sys.stderr.write(f"V17: native_choose_action raised {exc!r}; falling back to pure-Python V6 for this decision.\n")
        return None
