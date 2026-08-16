// Thin C++ binding to the official competition engine (`cg.dll` / `libcg.so`
// / `libcg.dylib`), loaded dynamically at runtime via the OS loader (LoadLibrary
// / dlopen) rather than link-time linkage against an import library.
//
// Deliberate design choice, not an oversight: this project has the engine's
// full C++ header source under data/official/ptcg_engine/ (see
// ENGINE_CLONE_LOOKAHEAD_AUDIT.md), but that source is licensed
// "competition-use-only, not open source... don't share or republish it"
// (data/official/ptcg_engine/ptcgProgram 22/README.md /
// LICENSES/LicenseRef-PTCG-ABC-Competition-Use-Only.txt). Recompiling that
// source into a new binary we then bundle into a Kaggle submission would be a
// real redistribution/derivative-work question this project has no authority
// to resolve unilaterally. Calling the ALREADY-COMPILED, ALREADY-SHIPPED
// `cg.dll`/`libcg.so` through its public `extern "C"` export table
// (Export.cpp) is exactly what the official Python `cg` package already does
// via ctypes -- this is the same sanctioned client/library boundary, just
// implemented in C++ instead of ctypes, with nothing about the engine itself
// re-linked, recompiled, or redistributed.
//
// Only the subset of exports our agent actually needs is declared: the
// *search sandbox* API (AgentStart/SearchBegin/SearchStep/SearchEnd), plus
// AllCard/AllAttack for static card data, plus GameInitialize. We deliberately
// do NOT bind BattleStart/Select/GetBattleData/BattleFinish -- those drive the
// LIVE match, which only the Kaggle grading harness (or the local `cg.game`
// dev harness) is supposed to touch; our agent only ever advises via the
// disposable search sandbox and returns an index list, exactly like the
// existing Python agents (src/agents/search_lookahead_v2.py) already do.
#pragma once

#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

#include "json_extract.hpp"

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
// Without NOMINMAX, <windows.h> #defines min/max as function-like macros,
// which silently rewrites every std::max(...)/std::min(...) call anywhere
// else in this project's headers into nonsense and fails to compile with a
// misleading "illegal token on right side of '::'" (MSVC C2589) far from
// this file. Confirmed by hitting exactly that error empirically before
// adding this.
#define NOMINMAX
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace cg {

// Mirrors cg/api.py's ApiResult -> SearchState -> Observation JSON shape at
// the raw-string level; parsing into typed structs happens in observation.hpp.
// Every SearchBegin/SearchStep call returns one JSON string of this shape:
//   {"state": {"observation": {...}, "searchId": N} | null, "error": E}
struct RawSearchResult {
  bool ok = false;
  int error = 0;
  std::string observation_json;  // only valid if ok
  long long search_id = 0;       // only valid if ok
};

class EngineLoadError : public std::runtime_error {
 public:
  explicit EngineLoadError(const std::string& msg) : std::runtime_error(msg) {}
};

// Loads and exposes the native library. One instance should live for the
// whole process lifetime (mirrors the Python `cg` package's own module-level
// `lib` and the sanctioned "AgentStart once per process, never destroy"
// usage documented in ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 3 -- there is no
// exported "destroy agent sandbox" function, so we never attempt one either).
class Engine {
 public:
  explicit Engine(const std::string& lib_path) {
#if defined(_WIN32)
    handle_ = reinterpret_cast<void*>(LoadLibraryA(lib_path.c_str()));
#else
    handle_ = dlopen(lib_path.c_str(), RTLD_NOW | RTLD_LOCAL);
#endif
    if (!handle_) {
      throw EngineLoadError("failed to load native engine library at: " + lib_path);
    }

    agent_start_ = resolve<AgentStartFn>("AgentStart");
    search_begin_ = resolve<SearchBeginFn>("SearchBegin");
    search_step_ = resolve<SearchStepFn>("SearchStep");
    search_end_ = resolve<SearchEndFn>("SearchEnd");
    search_release_ = resolve<SearchReleaseFn>("SearchRelease");
    all_card_ = resolve<AllCardFn>("AllCard");
    all_attack_ = resolve<AllAttackFn>("AllAttack");

    // Deliberately NOT calling GameInitialize() here, even though it's a
    // real exported function -- confirmed by hitting this empirically (a
    // "buffer full, capacity:7" native-side failure) while compiling and
    // smoke-testing this against a real VS Build Tools install: `lib_path`
    // here always resolves to the SAME physical cg.dll/libcg.so file the
    // Python `cg` package already loaded (native_bridge.py's own top-level
    // `import cg` runs before this constructor is ever reached -- see that
    // module's docstring), and the OS loader gives a second LoadLibrary/
    // dlopen call on an already-loaded module a handle to the SAME image,
    // sharing all static/global state. cg/sim.py already calls
    // GameInitialize() exactly once at that import; calling it again here
    // re-runs whatever one-time global setup it does against
    // already-initialized state and corrupts it. This makes GameInitialize
    // itself effectively load-order-coupled to Python -- documented here
    // rather than silently relied upon, since it's the one place this
    // binding is NOT fully independent of the Python side already having
    // run.
    agent_ptr_ = agent_start_();
    if (!agent_ptr_) {
      throw EngineLoadError("AgentStart() returned null -- native engine failed to allocate a search sandbox");
    }
  }

  Engine(const Engine&) = delete;
  Engine& operator=(const Engine&) = delete;

  ~Engine() {
    // No AgentFinish export exists (confirmed by source trace,
    // ENGINE_CLONE_LOOKAHEAD_AUDIT.md Part 3) -- there is nothing to release
    // here beyond unloading the library itself, which we deliberately also
    // skip: this Engine is meant to live for the whole process, and freeing
    // the library at static-destructor time on process exit is unnecessary
    // risk (destructor ordering vs. any OS-level atexit cleanup the DLL
    // itself may have registered) for zero benefit.
  }

  std::string all_card_json() {
    const char* p = all_card_();
    return p ? std::string(p) : std::string("[]");
  }

  std::string all_attack_json() {
    const char* p = all_attack_();
    return p ? std::string(p) : std::string("[]");
  }

  // `serialized`/`count` is the opaque `search_begin_input` token from the
  // live Observation (docs/search_api.md §1) -- NOT JSON, a raw byte buffer
  // the engine itself minted. The four "predicted" id lists are our
  // determinization guess for hidden zones (V6Heuristic::determinize_* ports
  // the same deck/prize bookkeeping V6/V11 already do in Python).
  RawSearchResult search_begin(const std::string& serialized,
                                const std::vector<int>& my_deck,
                                const std::vector<int>& my_prize,
                                const std::vector<int>& enemy_deck,
                                const std::vector<int>& enemy_prize,
                                const std::vector<int>& enemy_hand,
                                const std::vector<int>& enemy_active,
                                bool manual_coin) {
    const char* raw = search_begin_(
        agent_ptr_, serialized.data(), static_cast<int>(serialized.size()),
        const_cast<int*>(my_deck.data()), const_cast<int*>(my_prize.data()),
        const_cast<int*>(enemy_deck.data()), const_cast<int*>(enemy_prize.data()),
        const_cast<int*>(enemy_hand.data()), const_cast<int*>(enemy_active.data()),
        manual_coin ? 1 : 0);
    // `raw` points into the engine's own persistent per-ApiData JsonBuilder
    // buffer (Export.cpp: `data->jsonBuilder.buf.c_str()`) -- it is
    // overwritten by the NEXT call into this same agent_ptr_, never owned by
    // us and never to be freed here. Copy immediately into a std::string.
    return parse_raw_result(raw ? std::string(raw) : std::string());
  }

  RawSearchResult search_step(long long search_id, const std::vector<int>& select) {
    const char* raw = search_step_(agent_ptr_, search_id, const_cast<int*>(select.data()),
                                    static_cast<int>(select.size()));
    return parse_raw_result(raw ? std::string(raw) : std::string());
  }

  void search_end() { search_end_(agent_ptr_); }

  void search_release(long long search_id) { search_release_(agent_ptr_, search_id); }

 private:
  using AgentStartFn = void* (*)();
  using SearchBeginFn = const char* (*)(void*, const char*, int, int*, int*, int*, int*, int*, int*, int);
  using SearchStepFn = const char* (*)(void*, long long, int*, int);
  using SearchEndFn = void (*)(void*);
  using SearchReleaseFn = void (*)(void*, long long);
  using AllCardFn = const char* (*)();
  using AllAttackFn = const char* (*)();

  template <typename FnPtr>
  FnPtr resolve(const char* symbol) {
#if defined(_WIN32)
    void* addr = reinterpret_cast<void*>(GetProcAddress(reinterpret_cast<HMODULE>(handle_), symbol));
#else
    void* addr = dlsym(handle_, symbol);
#endif
    if (!addr) {
      throw EngineLoadError(std::string("native engine library missing expected export: ") + symbol);
    }
    return reinterpret_cast<FnPtr>(addr);
  }

  // Parses the fixed ApiResult envelope ({"state": {...}|null, "error": E})
  // using the narrow jx:: extractor (see json_extract.hpp) -- two top-level
  // fields plus one nested lookup, no tree allocation. The *inner*
  // observation substring is copied out into its own owned std::string here
  // (required: it points into `raw`, which is a local about to go out of
  // scope) and handed to observation.hpp's from_search_json only when/if the
  // caller actually needs typed fields -- MCTS's cheap tree-policy checks
  // (e.g. "did the turn end") often only need `error`/`search_id`.
  static RawSearchResult parse_raw_result(const std::string& raw) {
    RawSearchResult r;
    if (raw.empty()) {
      r.ok = false;
      r.error = -1;
      return r;
    }
    r.error = jx::to_int(jx::object_member(raw, "error"), 0);
    auto state = jx::object_member(raw, "state");
    if (r.error != 0 || !state.has_value()) {
      r.ok = false;
      return r;
    }
    r.search_id = jx::to_int64(jx::object_member(*state, "searchId"), 0);
    auto obs = jx::object_member(*state, "observation");
    if (!obs.has_value()) {
      r.ok = false;
      r.error = -2;  // malformed reply: "state" present but no "observation" -- treat as a hard failure, never guess
      return r;
    }
    r.ok = true;
    r.observation_json = std::string(*obs);  // owned copy -- `raw` (and thus `*obs`'s backing memory) goes out of scope on return
    return r;
  }

  void* handle_ = nullptr;
  void* agent_ptr_ = nullptr;

  AgentStartFn agent_start_ = nullptr;
  SearchBeginFn search_begin_ = nullptr;
  SearchStepFn search_step_ = nullptr;
  SearchEndFn search_end_ = nullptr;
  SearchReleaseFn search_release_ = nullptr;
  AllCardFn all_card_ = nullptr;
  AllAttackFn all_attack_ = nullptr;
};

}  // namespace cg
