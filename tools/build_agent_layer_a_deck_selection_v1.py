"""Phase 4.7 Layer A: deck-selection recommendation.

Mechanically applies the FROZEN Phase 4.6 policy
(`results/meta/final_deck_selection_policy.csv`) to the actual set of decks
we can submit -- i.e. decks with both (a) a real, validated 60-card deck.csv
and (b) a competitive gameplay policy (Layer B agent) to pilot it, which is a
strictly smaller set than "every archetype in the meta". This distinction --
meta-evidence quality vs. gameplay-execution quality -- is exactly what
session 13 (interrupted mid-Phase-4.7) flagged as an unresolved tension
between Team Rocket's Mewtwo ex (best meta evidence, no tested policy) and
Dragapult ex (proven policy, merely decent meta evidence). This script
resolves it by computing both axes side by side instead of picking one
axis first.

Does NOT re-run any Phase 4.1-4.6 statistics -- reads their frozen outputs
verbatim (`current_deck_recommendation.csv`, `final_validated_counters.csv`,
`meta_prior.csv`) and adds only: (1) restriction to our real candidate pool,
(2) a `has_tested_hand_tuned_policy` column sourced from local ablation
results (results/agent/ablation/leaderboard.csv, reports/competitive_v2.md),
(3) Wilson-CI overlap check between the top two candidates so a close
point-estimate gap isn't silently treated as a decisive win.
"""

import csv
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
META = REPO / "results" / "meta"
OUT = REPO / "results" / "agent" / "final_agent_policy.csv"

# Our actual candidate pool: archetype name -> (deck.csv path, has a tested
# hand-tuned Layer B policy, policy quality note).
CANDIDATES = {
    "Dragapult ex": {
        "deck_csv": "decks/dragapult_ex.csv",
        "policy_module": "src.agents.dragapult_agent_always_first",
        "has_tested_hand_tuned_policy": True,
        "policy_note": (
            "751-line hand-tuned port of the official notebook agent "
            "(src.agents.dragapult_agent), with the already-validated "
            "'dragapult_fix_v1' single-decision override promoted in an "
            "earlier session (results/dragapult_first_second_analysis.md + "
            "experiments/dragapult_first_variant.md): always elect to go "
            "first instead of the notebook's unconditional 'always second' "
            "(1000 games/condition controlled experiment, significant "
            "+10.8pp vs Abomasnow z=-4.97, never significantly worse "
            "vs any opponent tested). This IS the historical BEST_AGENT "
            "reference, not a new change this phase -- reused here since "
            "session 13's final_candidate_agent.py had regressed to "
            "wrapping the plain never-promoted dragapult_agent instead."
        ),
    },
    "Mega Lucario ex": {
        "deck_csv": "decks/lucario_ex.csv",
        "policy_module": "src.agents.lucario_ex_agent",
        "has_tested_hand_tuned_policy": True,
        "policy_note": (
            "466-line hand-tuned port of the official notebook agent; "
            "statistically TIED with Dragapult ex head-to-head in Search "
            "V2 ablation (reports/competitive_v2.md) -- also a credible "
            "policy, not a fallback choice."
        ),
    },
    "Team Rocket's Mewtwo ex": {
        "deck_csv": "decks/team_rockets_mewtwo_ex.csv",
        "policy_module": "src.agents.generic_mewtwo_agent",
        "has_tested_hand_tuned_policy": False,
        "policy_note": (
            "Only a deck-agnostic generic policy exists (no card-specific "
            "hand-tuning). Local ablation (results/agent/ablation/"
            "leaderboard.csv): 3/25 (12%) vs abomasnow_agent, a sparring "
            "opponent the hand-tuned Dragapult agent beats 64% of the "
            "time -- and 2/20 (10%) in a direct head-to-head vs the "
            "existing hand-tuned agent. Dramatically weaker execution."
        ),
    },
    "Mega Abomasnow ex": {
        "deck_csv": "decks/abomasnow_ex_corrected_v1.csv",
        "policy_module": "src.agents.abomasnow_agent",
        "has_tested_hand_tuned_policy": True,
        "policy_note": "Hand-tuned notebook port, but 0 real-ladder games (see meta_prior.csv) -- essentially absent from the actual competitive meta.",
    },
    "Iono's (Bellibolt/Voltorb)": {
        "deck_csv": "decks/iono.csv",
        "policy_module": "src.agents.iono_agent",
        "has_tested_hand_tuned_policy": True,
        "policy_note": "Hand-tuned notebook port, but 0 real-ladder games (see meta_prior.csv) -- essentially absent from the actual competitive meta.",
    },
}


def wilson(p: float, n: int, z: float = 1.959963985) -> tuple[float, float, float]:
    if n == 0:
        return (0.0, 0.0, 0.0)
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((center - half) / denom, p, (center + half) / denom)


def load_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    recs = {r["archetype"]: r for r in load_csv(META / "current_deck_recommendation.csv")}
    counters = load_csv(META / "final_validated_counters.csv")
    oos_confirmed = [c for c in counters if c["status"] == "OOS_CONFIRMED"]

    rows = []
    for archetype, meta_info in CANDIDATES.items():
        rec = recs.get(archetype)
        if rec is None or int(rec.get("recent_games", 0)) == 0:
            recent_games = 0
            recent_wr = None
            wilson_lo = wilson_hi = None
            expected_wr = None
        else:
            recent_games = int(rec["recent_games"])
            recent_wr = float(rec["recent_win_rate"])
            wilson_lo, _, wilson_hi = wilson(recent_wr, recent_games)
            expected_wr = float(rec["expected_win_rate_vs_current_meta"])

        applicable_confirmed_counters = [c for c in oos_confirmed if c["counter_archetype"] == archetype]
        counter_note = (
            "; ".join(
                f"{c['counter_archetype']} > {c['target_archetype']} "
                f"(OOS {float(c['oos_primary_win_rate']):.1%}, n={c['oos_primary_games']}, "
                f"target currently {float(c['current_target_meta_share']):.1%} of meta)"
                for c in applicable_confirmed_counters
            )
            or "none"
        )

        rows.append(
            {
                "archetype": archetype,
                "deck_csv": meta_info["deck_csv"],
                "policy_module": meta_info["policy_module"],
                "has_tested_hand_tuned_policy": meta_info["has_tested_hand_tuned_policy"],
                "policy_note": meta_info["policy_note"],
                "real_ladder_recent_games_14d_snapshot": recent_games,
                "real_ladder_recent_win_rate": recent_wr,
                "wilson_lo": wilson_lo,
                "wilson_hi": wilson_hi,
                "expected_win_rate_vs_current_meta": expected_wr,
                "oos_confirmed_counters_this_deck_has": counter_note,
            }
        )

    # Selection logic == frozen policy step 2 (rank candidates by Recent WR)
    # restricted to candidates with real ladder data AND a tested hand-tuned
    # policy (Section 16 step 7: "if uncertainty is high, prefer the robust
    # baseline" -- a deck with no competitive Layer B policy is not a robust
    # candidate regardless of its meta evidence).
    eligible = [r for r in rows if r["real_ladder_recent_games_14d_snapshot"] > 0 and r["has_tested_hand_tuned_policy"]]
    eligible.sort(key=lambda r: r["real_ladder_recent_win_rate"], reverse=True)

    for r in rows:
        r["eligible_for_selection"] = r in eligible
        r["selected"] = False

    if not eligible:
        note = "No eligible candidate (no archetype has both real ladder data and a tested policy)."
    else:
        by_point_estimate = eligible[0]
        final_pick = by_point_estimate
        if len(eligible) > 1:
            runner_up = eligible[1]
            overlap = not (
                by_point_estimate["wilson_lo"] > runner_up["wilson_hi"]
                or runner_up["wilson_lo"] > by_point_estimate["wilson_hi"]
            )
            if overlap:
                # Section 16 step 7: "if uncertainty is high, prefer the
                # robust baseline." A point-estimate ranking whose Wilson 95%
                # CIs overlap is NOT a credible gap (standing project rule:
                # never call a small-sample gap decisive) -- tie-break by
                # sample size/precision (more real-ladder games = a more
                # reliable estimate of true win rate) rather than the raw
                # point estimate.
                final_pick = max(eligible[:2], key=lambda r: r["real_ladder_recent_games_14d_snapshot"])
                note = (
                    f"By raw point estimate, '{by_point_estimate['archetype']}' "
                    f"({by_point_estimate['real_ladder_recent_win_rate']:.2%}, "
                    f"n={by_point_estimate['real_ladder_recent_games_14d_snapshot']}) ranks above "
                    f"'{runner_up['archetype']}' ({runner_up['real_ladder_recent_win_rate']:.2%}, "
                    f"n={runner_up['real_ladder_recent_games_14d_snapshot']}), but their Wilson 95% CIs "
                    f"OVERLAP (gap not statistically credible) -- tie-broken by sample size/precision "
                    f"in favor of '{final_pick['archetype']}' (n={final_pick['real_ladder_recent_games_14d_snapshot']}) "
                    f"rather than treating the smaller-n point estimate as a real win."
                )
            else:
                note = (
                    f"Top pick '{final_pick['archetype']}' ({final_pick['real_ladder_recent_win_rate']:.2%}, "
                    f"n={final_pick['real_ladder_recent_games_14d_snapshot']}) beats runner-up "
                    f"'{runner_up['archetype']}' with a statistically credible (non-overlapping Wilson 95% CI) gap."
                )
        else:
            note = f"Top pick '{final_pick['archetype']}' is the only eligible candidate."

        final_idx = rows.index(final_pick)
        rows[final_idx]["selected"] = True

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {OUT} ({len(rows)} candidate rows)")
    print(note)
    selected = next((r for r in rows if r["selected"]), None)
    if selected:
        print(f"SELECTED: {selected['archetype']}")


if __name__ == "__main__":
    main()
