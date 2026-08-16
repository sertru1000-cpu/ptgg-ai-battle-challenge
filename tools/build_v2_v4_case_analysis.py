"""V2-vs-V4 real-ladder case analysis -- reuses the IDENTICAL Part-C pipeline already built
and validated for the V2-vs-Luca audit (tools/build_ladder_audit_case_analysis.py), just
pointed at labels ["v2", "v4"] instead of ["luca", "v2"]. No logic duplicated/forked.

Writes v4_stayed_critical_outcomes.csv, v4_loss_analysis.csv, v4_full_summary.json (new) and
re-writes v2_stayed_critical_outcomes.csv / v2_loss_analysis.csv / v2_full_summary.json
(deterministic re-derivation from the same already-pulled v2_games.csv/v2_decisions.csv --
content is expected to be identical to the existing files, not a methodology change).
Writes the combined result to v2_v4_both_summaries.json (a NEW file -- does not overwrite
both_summaries.json, which remains the luca+v2 comparison).
"""
import json
import os

import tools.build_ladder_audit_case_analysis as base

base.LABELS = ["v2", "v4"]


def main():
    all_summaries = {}
    for label in base.LABELS:
        games, decisions = base.load(label)
        gm = base.game_level_metrics(games)
        am = base.action_level_metrics(games, decisions)
        crit, stayed_outcomes = base.critical_situation_analysis(decisions)
        loss_rows, loss_patterns = base.loss_analysis(games, decisions, label)

        import csv
        with open(os.path.join(base.OUT_DIR, f"{label}_stayed_critical_outcomes.csv"), "w", newline="", encoding="utf-8") as f:
            if stayed_outcomes:
                w = csv.DictWriter(f, fieldnames=list(stayed_outcomes[0].keys()))
                w.writeheader()
                w.writerows(stayed_outcomes)
            else:
                f.write("no_critical_stayed_situations_found\n")

        with open(os.path.join(base.OUT_DIR, f"{label}_loss_analysis.csv"), "w", newline="", encoding="utf-8") as f:
            if loss_rows:
                w = csv.DictWriter(f, fieldnames=list(loss_rows[0].keys()))
                w.writeheader()
                w.writerows(loss_rows)
            else:
                f.write("no_losses\n")

        summary = {
            "label": label,
            "game_level": gm,
            "action_level": am,
            "critical_situation_analysis": crit,
            "loss_patterns": loss_patterns,
        }
        all_summaries[label] = summary
        with open(os.path.join(base.OUT_DIR, f"{label}_full_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)

    with open(os.path.join(base.OUT_DIR, "v2_v4_both_summaries.json"), "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, default=str)
    print("done. wrote", os.path.join(base.OUT_DIR, "v2_v4_both_summaries.json"))


if __name__ == "__main__":
    main()
