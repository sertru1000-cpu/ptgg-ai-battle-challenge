"""Optional, switchable decision-point logging for local tournaments/analysis.

Not used by any real Kaggle submission (a submitted main.py never imports
this) -- it exists purely for local research/analysis (Steps 9/12, and later
the Strategy competition). No-op by default so importing/wiring it in adds
zero overhead or risk to anything that doesn't explicitly enable it.

IMPORTANT naming note: this package is `src.logging`, not the stdlib
`logging` module. It must only ever be imported as `src.logging.*` -- never
add a bare `src/` directory to sys.path and do `import logging` expecting
this package, or vice versa.

Never logs anything the acting player couldn't see: state summaries only
read fields the engine already exposes to the deciding player (the engine
itself sets the opponent's `hand` to None, opponent deck/prize contents are
never read at all here).
"""

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.environment.engine_loader import ensure_cg_on_path

ensure_cg_on_path()

from cg.api import AreaType, OptionType, SelectContext  # noqa: E402

# Note: cg.api's to_dataclass() does not coerce raw JSON ints into their
# IntEnum types (verified empirically), so Option.type/area and
# SelectData.context arrive as plain ints on the Observation objects this
# module receives -- wrap them in their enum classes here for readable logs.


def summarize_visible_state(obs) -> dict[str, Any]:
    """Extract a compact, engine-exposed-only snapshot of the current state,
    from the perspective of the player about to act (obs.current.yourIndex).
    """
    state = obs.current
    my_index = state.yourIndex
    my = state.players[my_index]
    opp = state.players[1 - my_index]

    my_active = my.active[0] if my.active else None
    opp_active = opp.active[0] if opp.active else None

    return {
        "turn": state.turn,
        "my_active_id": my_active.id if my_active else None,
        "my_active_hp": my_active.hp if my_active else None,
        "my_bench_count": len(my.bench),
        "my_hand_count": my.handCount,
        "my_prize_count": len(my.prize),
        # opponent's active Pokemon is visible board state once revealed;
        # it is None both when there's genuinely no active Pokemon yet AND
        # when it's face-down during opponent's setup -- either way this is
        # exactly what the engine already shows the acting player.
        "opp_active_id": opp_active.id if opp_active else None,
        "opp_active_hp": opp_active.hp if opp_active else None,
        "opp_bench_count": len(opp.bench),
        "opp_prize_count": len(opp.prize),
    }


def summarize_chosen(select, chosen_indices: list[int]) -> list[dict]:
    """Describe the selected option(s) using only fields already present on
    the Option objects the engine offered (nothing resolved beyond that)."""
    out = []
    for i in chosen_indices:
        o = select.option[i]
        out.append(
            {
                "index": i,
                "type": OptionType(o.type).name,
                "area": AreaType(o.area).name if o.area is not None else None,
                "attackId": o.attackId,
                "cardId": o.cardId,
            }
        )
    return out


class DecisionLogger:
    """Buffers decision records per game_id and only writes them once the
    game's outcome is known (finalize_game), so every persisted record is
    self-contained with its eventual game outcome -- no later join needed.
    """

    def __init__(self, enabled: bool = False, out_path: str | Path | None = None):
        self.enabled = enabled or os.environ.get("PTCG_LOG_DECISIONS") == "1"
        self.out_path = Path(out_path) if out_path else None
        self._buffers: dict[str, list[dict]] = defaultdict(list)

    def log_decision(self, game_id: str, obs, chosen_indices: list[int]) -> None:
        if not self.enabled:
            return
        select = obs.select
        state = obs.current
        record = {
            "game_id": game_id,
            "turn": state.turn,
            "player_index": state.yourIndex,
            "context": SelectContext(select.context).name,
            "option_count": len(select.option),
            "chosen": summarize_chosen(select, chosen_indices),
            "state": summarize_visible_state(obs),
        }
        self._buffers[game_id].append(record)

    def finalize_game(self, game_id: str, outcome: dict) -> None:
        """Stamp `outcome` onto every buffered record for this game and flush
        to out_path (if set). `outcome` is arbitrary small JSON-safe data,
        e.g. {"result": 0, "reason": 1, "winner_agent": "abomasnow_agent"}.
        """
        if not self.enabled:
            return
        records = self._buffers.pop(game_id, [])
        if not records:
            return
        for r in records:
            r["outcome"] = outcome
        if self.out_path:
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.out_path, "a", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
