"""Leader deck diff (breakthrough track, step 1): compare the exact 60-card
Dragapult decklists of the top-100 ladder's Dragapult teams (already
downloaded in data/top100_audit/replays/ by tools/pull_top100_ladder_audit.py)
against OUR deck (decks/dragapult_ex.csv = V6/V17/V18's DECK).

Question this answers: the #2/#3 ladder teams play "our" archetype at rating
~1200 vs our ~680 -- is any of that gap in the LIST (cards we're missing /
extras we shouldn't run), before even looking at play-decision differences?

Output: per-team diff + a consensus table (how many of the top Dragapult
teams run each card we don't, and vice versa), card names resolved via the
official card CSV. Read-only, no downloads, no agent changes.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import csv

from src.agents.dragapult_policy_v6 import DECK as OUR_DECK  # noqa: E402
from src.meta_analysis.card_lookup import load_card_data  # noqa: E402

REPLAYS_DIR = REPO_ROOT / "data" / "top100_audit" / "replays"
LEADERBOARD_CSV = REPO_ROOT / "results" / "top100_audit" / "leaderboard_decks.csv"
OUT_PATH = REPO_ROOT / "results" / "leader_diff" / "deck_diff.md"


def _extract_decks(replay_path: Path):
    """Returns (team_names, decks) where decks[i] is the 60-card list player i
    declared (first non-empty action -- the validated exact method)."""
    with open(replay_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    team_names = data["info"].get("TeamNames", [None, None])
    decks = [None, None]
    for step in data["steps"]:
        for pi in (0, 1):
            if decks[pi] is None:
                action = step[pi].get("action")
                if action and isinstance(action, list) and len(action) == 60:
                    decks[pi] = list(action)
        if decks[0] is not None and decks[1] is not None:
            break
    return team_names, decks


def main() -> None:
    table = load_card_data()

    def name(cid: int) -> str:
        row = table.get(cid)
        return row["Card Name"] if row else f"?id={cid}"

    rows = list(csv.DictReader(open(LEADERBOARD_CSV, encoding="utf-8")))
    drag_teams = {r["team_name"]: r for r in rows if "Dragapult" in r.get("archetype", "")}
    print(f"Top-100 Dragapult teams: {len(drag_teams)}")

    # team_name -> Counter(deck) (first consistent deck seen; deck_consistent
    # was True for all 99 extracted teams in the audit)
    team_decks: dict[str, Counter] = {}
    scanned = 0
    for path in sorted(REPLAYS_DIR.glob("episode-*-replay.json")):
        scanned += 1
        try:
            team_names, decks = _extract_decks(path)
        except (json.JSONDecodeError, KeyError, OSError):
            continue
        for pi, tn in enumerate(team_names):
            if tn in drag_teams and tn not in team_decks and decks[pi] is not None:
                team_decks[tn] = Counter(decks[pi])
        if len(team_decks) == len(drag_teams):
            break
    print(f"Scanned {scanned} replays; recovered decks for {len(team_decks)}/{len(drag_teams)} Dragapult teams")

    ours = Counter(OUR_DECK)
    lines = ["# Top-100 Dragapult decklists vs our deck", ""]
    lines.append(f"Recovered {len(team_decks)} of {len(drag_teams)} top-100 Dragapult teams' exact lists.")
    lines.append("")

    # Consensus: for every card, in how many leader decks does it appear (and
    # at what typical count) vs our count?
    they_have_we_dont: Counter = Counter()
    count_diffs: dict[int, list[int]] = {}
    for tn, deck in team_decks.items():
        for cid, n in deck.items():
            if ours.get(cid, 0) == 0:
                they_have_we_dont[cid] += 1
            elif ours[cid] != n:
                count_diffs.setdefault(cid, []).append(n - ours[cid])
    we_have_they_dont: Counter = Counter()
    for cid in ours:
        missing_in = sum(1 for deck in team_decks.values() if deck.get(cid, 0) == 0)
        if missing_in > 0:
            we_have_they_dont[cid] = missing_in

    n_teams = max(1, len(team_decks))
    lines.append("## Cards leaders run that we DON'T (teams running it / total)")
    for cid, cnt in they_have_we_dont.most_common():
        counts = [d.get(cid, 0) for d in team_decks.values() if d.get(cid, 0) > 0]
        lines.append(f"- {name(cid)} (id {cid}): {cnt}/{n_teams} teams, typical copies {sorted(set(counts))}")
    lines.append("")
    lines.append("## Cards WE run that some leaders don't (teams NOT running it / total)")
    for cid, cnt in we_have_they_dont.most_common():
        lines.append(f"- {name(cid)} (id {cid}) x{ours[cid]} in ours: absent in {cnt}/{n_teams} leader decks")
    lines.append("")
    lines.append("## Copy-count differences on shared cards (leader count minus ours)")
    for cid, diffs in sorted(count_diffs.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- {name(cid)} (id {cid}, ours x{ours[cid]}): diffs {sorted(diffs)}")
    lines.append("")

    lines.append("## Per-team exact diff vs ours")
    ranked = sorted(team_decks.items(), key=lambda kv: int(drag_teams[kv[0]]["rank"]))
    for tn, deck in ranked:
        meta = drag_teams[tn]
        plus = {cid: n - ours.get(cid, 0) for cid, n in deck.items() if n > ours.get(cid, 0)}
        minus = {cid: ours[cid] - deck.get(cid, 0) for cid in ours if ours[cid] > deck.get(cid, 0)}
        same = not plus and not minus
        lines.append(f"### rank {meta['rank']} — {tn} (rating {meta['rating']})")
        if same:
            lines.append("- IDENTICAL to our deck")
        else:
            for cid, n in sorted(plus.items(), key=lambda kv: -kv[1]):
                lines.append(f"- +{n} {name(cid)} (id {cid})")
            for cid, n in sorted(minus.items(), key=lambda kv: -kv[1]):
                lines.append(f"- -{n} {name(cid)} (id {cid})")
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
