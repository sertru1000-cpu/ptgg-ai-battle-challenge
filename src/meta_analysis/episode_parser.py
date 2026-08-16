"""Parse a single Kaggle PTCG episode replay JSON into a structured, offline-only record.

This module is for OFFLINE analysis of episode data (Part 1-3 of the meta-analysis phase).
It reads the `visualize`/full-decklist fields that are explicitly NOT visible to a live
agent -- do not reuse any of this against real game state during actual play.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class EpisodeRecord:
    episode_id: str
    date: str
    team_names: list          # [name0, name1]
    reward0: int              # -1/0/1
    reward1: int
    winner: int | None        # 0, 1, or None (draw / error / timeout)
    outcome_type: str         # "DECISIVE" | "DRAW" | "ERROR_OR_TIMEOUT"
    first_player: int | None  # engine current.firstPlayer, last-observed value
    n_steps: int
    final_turn_p0: int | None
    final_turn_p1: int | None
    deck0: Counter            # card_id -> count, exact, from deck-declare action
    deck1: Counter
    deck0_hash: str
    deck1_hash: str
    deck0_source: str         # "action" | "visualize" | "missing"
    deck1_source: str


def deck_hash(deck: Counter) -> str:
    """Stable hash of a deck's exact composition, order-independent."""
    canonical = tuple(sorted(deck.items()))
    return hashlib.sha256(repr(canonical).encode("utf-8")).hexdigest()[:16]


def _extract_deck(steps, player_idx) -> tuple[Counter, str]:
    """First non-empty 60-card action for this player is their submitted deck.
    Falls back to visualize.current.players[player_idx].deck if the action-based
    path is ever absent (should not happen per Part 0 findings, but don't assume)."""
    for step in steps:
        entry = step[player_idx]
        action = entry.get("action")
        if isinstance(action, list) and len(action) == 60:
            return Counter(action), "action"
    for step in steps:
        vis = step[player_idx].get("visualize")
        if vis:
            cur = vis[0].get("current") if isinstance(vis, list) else vis.get("current")
            if cur:
                d = cur["players"][player_idx].get("deck")
                if d and len(d) == 60:
                    return Counter(c["id"] for c in d), "visualize"
    return Counter(), "missing"


def _final_turn(steps, player_idx):
    turn = None
    for step in steps:
        cur = step[player_idx]["observation"].get("current")
        if cur and cur.get("turn") is not None:
            turn = cur["turn"]
    return turn


def _first_player(steps):
    fp = None
    for step in steps:
        for p in (0, 1):
            cur = step[p]["observation"].get("current")
            if cur and cur.get("firstPlayer") is not None and cur["firstPlayer"] != -1:
                fp = cur["firstPlayer"]
    return fp


def parse_episode_file(path: str, date: str) -> EpisodeRecord:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    episode_id = str(data["info"].get("EpisodeId", data.get("id")))
    team_names = data["info"].get("TeamNames", [None, None])
    rewards = data["rewards"]
    statuses = data.get("statuses", [None, None])
    r0, r1 = rewards[0], rewards[1]
    if r0 == 1 and r1 == -1:
        winner, outcome_type = 0, "DECISIVE"
    elif r1 == 1 and r0 == -1:
        winner, outcome_type = 1, "DECISIVE"
    elif r0 == 0 and r1 == 0:
        winner, outcome_type = None, "DRAW"
    else:
        # asymmetric/None reward paired with an ERROR or TIMEOUT status -- one side's
        # agent crashed or exceeded the wall-clock budget, not a real contested draw.
        # (Verified empirically: every non-DECISIVE/non-(0,0) case in the pilot sample
        # has statuses containing "ERROR" or "TIMEOUT".)
        winner = 0 if r0 == 1 else (1 if r1 == 1 else None)
        outcome_type = "ERROR_OR_TIMEOUT"

    steps = data["steps"]
    deck0, src0 = _extract_deck(steps, 0)
    deck1, src1 = _extract_deck(steps, 1)

    return EpisodeRecord(
        episode_id=episode_id,
        date=date,
        team_names=team_names,
        reward0=r0,
        reward1=r1,
        winner=winner,
        outcome_type=outcome_type,
        first_player=_first_player(steps),
        n_steps=len(steps),
        final_turn_p0=_final_turn(steps, 0),
        final_turn_p1=_final_turn(steps, 1),
        deck0=deck0,
        deck1=deck1,
        deck0_hash=deck_hash(deck0),
        deck1_hash=deck_hash(deck1),
        deck0_source=src0,
        deck1_source=src1,
    )


def record_to_row(rec: EpisodeRecord) -> dict:
    """Flatten to a CSV-friendly dict. Deck composition itself is stored separately
    (see tools/build_pilot_dataset.py) since it's variable-length."""
    return {
        "episode_id": rec.episode_id,
        "date": rec.date,
        "team0": rec.team_names[0] if rec.team_names else None,
        "team1": rec.team_names[1] if len(rec.team_names or []) > 1 else None,
        "winner": rec.winner,
        "outcome_type": rec.outcome_type,
        "first_player": rec.first_player,
        "n_steps": rec.n_steps,
        "final_turn_p0": rec.final_turn_p0,
        "final_turn_p1": rec.final_turn_p1,
        "deck0_hash": rec.deck0_hash,
        "deck1_hash": rec.deck1_hash,
        "deck0_ncards": sum(rec.deck0.values()),
        "deck1_ncards": sum(rec.deck1.values()),
        "deck0_source": rec.deck0_source,
        "deck1_source": rec.deck1_source,
    }
