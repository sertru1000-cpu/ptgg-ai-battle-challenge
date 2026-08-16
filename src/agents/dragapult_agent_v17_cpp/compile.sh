#!/usr/bin/env bash
# Manual/reference g++/Linux build script -- NOT what actually runs on
# Kaggle, and not what this dev machine's own automated tests used either
# (this machine has MSVC via VS Build Tools, not g++; native_bridge.py's
# compiler selection uses MSVC here and g++ on Linux, see README.md's
# "What compiling and testing actually found" -- the g++ path below is
# believed correct but has not itself been run anywhere yet).
#
# The real submission compiles this on first import instead (see
# main_v17.py -> native_bridge.py's `_ensure_native_library_built()`),
# because Kaggle's grading container's architecture/libc/compiler are
# unverified from here, and no binary built on this dev machine would be the
# right target platform (Linux) anyway. Shipping a locally-built .so would be
# a pure guess at ABI compatibility; compiling on the actual target machine
# removes that guess entirely, at the cost of depending on g++ being present
# there (unverified -- see README.md).
#
# This script exists so a human with a real g++/Linux toolchain (a scratch
# Kaggle notebook cell, a Linux CI runner) can build and smoke-test the
# library exactly the way native_bridge.py's g++ path does, with the exact
# same flags, kept in sync by hand (both are short enough that drift would
# be obvious in review).
set -euo pipefail
cd "$(dirname "$0")/cpp"

OUT="${1:-libv17_mcts.so}"
g++ -O3 -shared -fPIC -std=c++17 -o "$OUT" v17_agent.cpp -ldl
echo "Built $OUT"
