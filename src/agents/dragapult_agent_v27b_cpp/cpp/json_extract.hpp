// Narrow, single-pass JSON field extractor -- NOT a general JSON library.
//
// Why this exists at all (see ../README.md "Forward model" section for the
// full architecture): the competition engine's `SearchBegin`/`SearchStep`
// exports only return JSON strings (there is no binary struct ABI available
// -- that's a constraint of the shipped `cg.dll`/`libcg.so`, not a choice
// made here). Those calls happen entirely inside the C++ MCTS loop, native
// engine call after native engine call, with Python never in the loop --
// so *something* in C++ has to read the reply, every single simulated step.
//
// Deliberately NOT a generic recursive-descent-to-heap-tree parser: there is
// no `Value` type, no `std::map`/`std::vector` tree, nothing allocated until
// the caller asks for one specific leaf (an int/bool/string). Every function
// here operates on `std::string_view`s into a buffer the CALLER owns (see
// cg_engine.hpp -- the DLL's transient reply is copied into an owned
// std::string once, immediately; every std::string_view derived from it here
// must not outlive that owning std::string, exactly like any other
// string_view usage). The only real allocations are the final extracted
// leaves (an int has none; a string leaf allocates one std::string, same as
// any normal C++ code reading a value out of a buffer).
//
// Scope: handles the actual JSON this engine emits (objects, arrays,
// strings with the standard backslash escapes + \uXXXX, numbers, true/
// false/null). Not a conformance-tested general parser -- it only needs to
// correctly read well-formed engine output, matching the schema in
// cg/api.py's dataclasses (this project's own ground-truth reference).
#pragma once

#include <cstdlib>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace jx {

inline size_t skip_ws(std::string_view s, size_t pos) {
  while (pos < s.size()) {
    char c = s[pos];
    if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
      ++pos;
    } else {
      break;
    }
  }
  return pos;
}

// Returns the raw span of exactly one JSON value starting at `pos` (after
// skipping leading whitespace), plus the index just past it. Balances
// {}/[]/quoted-strings (including escaped quotes/braces inside strings, so a
// card name or log text containing a literal '"' or '{' never desyncs the
// scan). Returns nullopt only on truncated/malformed input.
inline std::optional<std::pair<std::string_view, size_t>> read_value(std::string_view s, size_t pos) {
  pos = skip_ws(s, pos);
  if (pos >= s.size()) return std::nullopt;
  size_t start = pos;
  char c = s[pos];

  if (c == '{' || c == '[') {
    char open = c;
    char close = (c == '{') ? '}' : ']';
    int depth = 0;
    bool in_str = false;
    bool esc = false;
    for (; pos < s.size(); ++pos) {
      char ch = s[pos];
      if (in_str) {
        if (esc) {
          esc = false;
        } else if (ch == '\\') {
          esc = true;
        } else if (ch == '"') {
          in_str = false;
        }
        continue;
      }
      if (ch == '"') {
        in_str = true;
        continue;
      }
      if (ch == open) {
        ++depth;
      } else if (ch == close) {
        --depth;
        if (depth == 0) {
          ++pos;
          break;
        }
      }
    }
    if (depth != 0) return std::nullopt;  // truncated
    return std::make_pair(s.substr(start, pos - start), pos);
  }

  if (c == '"') {
    bool esc = false;
    ++pos;
    bool closed = false;
    for (; pos < s.size(); ++pos) {
      char ch = s[pos];
      if (esc) {
        esc = false;
        continue;
      }
      if (ch == '\\') {
        esc = true;
        continue;
      }
      if (ch == '"') {
        ++pos;
        closed = true;
        break;
      }
    }
    if (!closed) return std::nullopt;
    return std::make_pair(s.substr(start, pos - start), pos);
  }

  // number / true / false / null: run until a structural delimiter.
  while (pos < s.size()) {
    char ch = s[pos];
    if (ch == ',' || ch == '}' || ch == ']' || ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r') break;
    ++pos;
  }
  if (pos == start) return std::nullopt;
  return std::make_pair(s.substr(start, pos - start), pos);
}

// `obj` must be a JSON object span (as returned by read_value, e.g. from a
// prior object_member/array_items call). Returns the raw value span for
// `key`, or nullopt if absent/null/not an object -- callers treat "absent"
// and "null" identically throughout this project (matching the engine's own
// documented "new fields may be appended" schema-evolution note).
inline std::optional<std::string_view> object_member(std::string_view obj, std::string_view key) {
  size_t pos = skip_ws(obj, 0);
  if (pos >= obj.size() || obj[pos] != '{') return std::nullopt;
  ++pos;
  pos = skip_ws(obj, pos);
  if (pos < obj.size() && obj[pos] == '}') return std::nullopt;  // empty object

  while (pos < obj.size()) {
    pos = skip_ws(obj, pos);
    if (pos >= obj.size() || obj[pos] != '"') return std::nullopt;  // malformed
    auto key_res = read_value(obj, pos);
    if (!key_res) return std::nullopt;
    std::string_view raw_key = key_res->first;
    pos = key_res->second;

    pos = skip_ws(obj, pos);
    if (pos >= obj.size() || obj[pos] != ':') return std::nullopt;
    ++pos;

    auto val_res = read_value(obj, pos);
    if (!val_res) return std::nullopt;
    std::string_view raw_val = val_res->first;
    pos = val_res->second;

    // Strip the surrounding quotes from the key. Every key in this schema is
    // a plain ASCII identifier (field name) -- never escaped -- so no
    // unescaping is needed here (unlike string VALUES, see unescape_string).
    std::string_view unquoted_key = (raw_key.size() >= 2) ? raw_key.substr(1, raw_key.size() - 2) : raw_key;
    if (unquoted_key == key) {
      if (raw_val == "null") return std::nullopt;
      return raw_val;
    }

    pos = skip_ws(obj, pos);
    if (pos < obj.size() && obj[pos] == ',') {
      ++pos;
      continue;
    }
    break;  // '}' or end of buffer
  }
  return std::nullopt;
}

// `arr` must be a JSON array span. Returns the raw value span of each
// top-level element, in order.
inline std::vector<std::string_view> array_items(std::string_view arr) {
  std::vector<std::string_view> out;
  size_t pos = skip_ws(arr, 0);
  if (pos >= arr.size() || arr[pos] != '[') return out;
  ++pos;
  pos = skip_ws(arr, pos);
  if (pos < arr.size() && arr[pos] == ']') return out;

  while (pos < arr.size()) {
    auto v = read_value(arr, pos);
    if (!v) break;
    out.push_back(v->first);
    pos = skip_ws(arr, v->second);
    if (pos < arr.size() && arr[pos] == ',') {
      ++pos;
      continue;
    }
    break;
  }
  return out;
}

inline bool is_null_or_absent(const std::optional<std::string_view>& v) {
  return !v.has_value() || *v == "null";
}

inline int to_int(const std::optional<std::string_view>& v, int default_value = 0) {
  if (is_null_or_absent(v)) return default_value;
  // std::string_view is not guaranteed NUL-terminated; std::stoi needs a
  // std::string. These leaves are short (a handful of digits), so the copy
  // is cheap and this stays portable across standard library versions that
  // don't yet have full <charconv> floating support (see long_double/double
  // note below) rather than reaching for std::from_chars everywhere.
  try {
    return std::stoi(std::string(*v));
  } catch (...) {
    return default_value;
  }
}

inline long long to_int64(const std::optional<std::string_view>& v, long long default_value = 0) {
  if (is_null_or_absent(v)) return default_value;
  try {
    return std::stoll(std::string(*v));
  } catch (...) {
    return default_value;
  }
}

inline double to_double(const std::optional<std::string_view>& v, double default_value = 0.0) {
  if (is_null_or_absent(v)) return default_value;
  try {
    return std::stod(std::string(*v));
  } catch (...) {
    return default_value;
  }
}

inline bool to_bool(const std::optional<std::string_view>& v, bool default_value = false) {
  if (is_null_or_absent(v)) return default_value;
  if (*v == "true") return true;
  if (*v == "false") return false;
  return default_value;
}

// `v` includes the surrounding quotes (a raw string-value span from
// read_value/object_member). Strips them and resolves backslash escapes.
inline std::string to_unescaped_string(const std::optional<std::string_view>& v, const std::string& default_value = "") {
  if (is_null_or_absent(v)) return default_value;
  std::string_view s = *v;
  if (s.size() < 2 || s.front() != '"' || s.back() != '"') return default_value;
  s = s.substr(1, s.size() - 2);

  std::string out;
  out.reserve(s.size());
  for (size_t i = 0; i < s.size(); ++i) {
    char c = s[i];
    if (c != '\\' || i + 1 >= s.size()) {
      out.push_back(c);
      continue;
    }
    char esc = s[++i];
    switch (esc) {
      case '"': out.push_back('"'); break;
      case '\\': out.push_back('\\'); break;
      case '/': out.push_back('/'); break;
      case 'b': out.push_back('\b'); break;
      case 'f': out.push_back('\f'); break;
      case 'n': out.push_back('\n'); break;
      case 'r': out.push_back('\r'); break;
      case 't': out.push_back('\t'); break;
      case 'u': {
        if (i + 4 >= s.size()) break;
        unsigned code = 0;
        for (int k = 0; k < 4; ++k) {
          char h = s[i + 1 + k];
          code <<= 4;
          if (h >= '0' && h <= '9') code |= static_cast<unsigned>(h - '0');
          else if (h >= 'a' && h <= 'f') code |= static_cast<unsigned>(h - 'a' + 10);
          else if (h >= 'A' && h <= 'F') code |= static_cast<unsigned>(h - 'A' + 10);
        }
        i += 4;
        if (code < 0x80) {
          out.push_back(static_cast<char>(code));
        } else if (code < 0x800) {
          out.push_back(static_cast<char>(0xC0 | (code >> 6)));
          out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
        } else {
          out.push_back(static_cast<char>(0xE0 | (code >> 12)));
          out.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
          out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
        }
        break;
      }
      default:
        out.push_back(esc);
    }
  }
  return out;
}

}  // namespace jx
