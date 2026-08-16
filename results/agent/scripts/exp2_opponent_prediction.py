"""Experiment 2: Bayesian opponent-archetype posterior model + temporal OOS validation.

Research-only script. Reads:
  - data/episode_pilot/<date>/<episode_id>.json  (raw kaggle_environments replay JSON,
    1503 files spanning all 56 dates 2026-06-16..2026-08-10 -- a REDUCED sample of the
    full 3499-episode dataset, not the full thing)
  - results/meta/deck_to_archetype.csv  (exact_deck_hash -> archetype_id/name mapping,
    reused as-is from the Phase 4.1 pipeline, not re-derived)
  - results/meta/meta_prior.csv  (RECENT-period archetype shares, prior_filtered column)

Writes ONLY to:
  - results/agent/opponent_prediction_metrics.csv
  - results/agent/opponent_prediction_raw_predictions.csv

Evidence signal used (explicitly scoped, per task instructions): opponent Pokemon card
ids revealed to the acting player's own observation stream, cumulative through a given
turn cutoff. A Pokemon "reveals" itself the moment it appears in
observation.current.players[opponent_index].active/.bench for that player's OWN
observation object (never .visualize.*, which is spectator/hidden-info only and
forbidden). We also fold in each such Pokemon's `preEvolution` id list -- this is
part of the same visible Pokemon object (not extra hidden info) and recovers cards
whose earlier evolution stage was never separately observed by this particular
acting player. Non-Pokemon (Trainer/Item/Supporter) revealed cards are NOT extracted
-- the per-step schema does not expose a clean "cards visibly played by opponent"
field distinct from the active/bench Pokemon array without much deeper log-parsing,
so this experiment is explicitly scoped to "revealed opponent Pokemon" only, per the
task's documented fallback.

Turn-cutoff semantics: each engine env-step has an entry for BOTH players, but only
the player whose decision the step corresponds to receives a freshly updated
`observation.current` (confirmed empirically: a player's own `current.turn` sequence
only advances at their own turn boundaries, e.g. player 0 who goes first sees
turn in {0,1,3,5,...}, never 2/4/6). So for turn cutoff T, "what does this player
know" = the cumulative revealed set as of the LAST of their own snapshots with
turn <= T; if they have no such snapshot yet (their own next decision point hasn't
happened), evidence is empty and coverage=False for that cutoff. This is an honest
reflection of what is actually visible to that seat at that point in the game, not
an artifact -- documented explicitly here and in the notes file.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.meta_analysis.episode_parser import deck_hash, _extract_deck

REPO_ROOT = Path(__file__).resolve().parents[3]
PILOT_DIR = REPO_ROOT / "data" / "episode_pilot"
DECK_MAP_PATH = REPO_ROOT / "results" / "meta" / "deck_to_archetype.csv"
PRIOR_PATH = REPO_ROOT / "results" / "meta" / "meta_prior.csv"
OUT_METRICS = REPO_ROOT / "results" / "agent" / "opponent_prediction_metrics.csv"
OUT_RAW = REPO_ROOT / "results" / "agent" / "opponent_prediction_raw_predictions.csv"

CUTOFFS = [1, 2, 3, "full"]
TEST_DATE_FRACTION = 0.20  # last ~20% of dates by chronological order
LAPLACE_ALPHA = 1.0        # add-one (Laplace) smoothing, see notes for justification
PRIOR_FLOOR = 1e-3         # floor applied to any archetype with prior_filtered == 0
LOGLOSS_EPS = 1e-12
TIER_BOUNDS = [("HIGH", 0.80, 1.0 + 1e-9), ("MEDIUM", 0.60, 0.80), ("LOW", 0.0, 0.60)]


def confidence_tier(p: float) -> str:
    if p >= 0.80:
        return "HIGH"
    if p >= 0.60:
        return "MEDIUM"
    return "LOW"


def load_archetype_map() -> dict:
    df = pd.read_csv(DECK_MAP_PATH)
    m = {}
    for _, r in df.iterrows():
        aid = r["archetype_id"]
        if isinstance(aid, str) and not aid.startswith("UNLABELED_CLUSTER"):
            m[r["exact_deck_hash"]] = aid
    return m


def load_prior() -> dict:
    df = pd.read_csv(PRIOR_PATH)
    return dict(zip(df["archetype_id"], df["prior_filtered"]))


def revealed_ids_from_playerstate(ps: dict) -> set:
    ids = set()
    for zone in ("active", "bench"):
        for mon in (ps.get(zone) or []):
            if not mon:
                continue
            ids.add(mon["id"])
            for pre in (mon.get("preEvolution") or []):
                ids.add(pre["id"])
    return ids


def extract_episode_examples(path: Path, date: str, archetype_map: dict) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    steps = data["steps"]
    rewards = data.get("rewards", [None, None])
    r0, r1 = rewards[0], rewards[1]
    if r0 == 1 and r1 == -1:
        outcome_type = "DECISIVE"
    elif r1 == 1 and r0 == -1:
        outcome_type = "DECISIVE"
    elif r0 == 0 and r1 == 0:
        outcome_type = "DRAW"
    else:
        outcome_type = "ERROR_OR_TIMEOUT"
    if outcome_type != "DECISIVE":
        return []

    deck0, _src0 = _extract_deck(steps, 0)
    deck1, _src1 = _extract_deck(steps, 1)
    arche0 = archetype_map.get(deck_hash(deck0))
    arche1 = archetype_map.get(deck_hash(deck1))

    episode_id = str(data["info"].get("EpisodeId", data.get("id")))

    examples = []
    for p in (0, 1):
        opp_idx = 1 - p
        opp_archetype = arche1 if p == 0 else arche0
        if opp_archetype is None:
            continue  # opponent's exact deck did not map to a NAMED archetype -- unusable
        snapshots = []  # list of (turn, cumulative_revealed_frozenset), in step order
        cumulative = set()
        for step in steps:
            cur = step[p]["observation"].get("current")
            if not cur:
                continue
            turn = cur.get("turn")
            opp_ps = cur["players"][opp_idx]
            cumulative = cumulative | revealed_ids_from_playerstate(opp_ps)
            snapshots.append((turn, frozenset(cumulative)))
        if not snapshots:
            continue
        for cutoff in CUTOFFS:
            if cutoff == "full":
                evidence = snapshots[-1][1]
            else:
                candidates = [s for (t, s) in snapshots if t is not None and t <= cutoff]
                evidence = candidates[-1] if candidates else frozenset()
            examples.append({
                "episode_id": episode_id,
                "date": date,
                "side": p,
                "turn_cutoff": cutoff,
                "true_archetype": opp_archetype,
                "evidence": evidence,
            })
    return examples


def main():
    archetype_map = load_archetype_map()
    prior_filtered = load_prior()

    files = sorted(PILOT_DIR.glob("*/*.json"))
    print("Pilot episode files found:", len(files))

    all_examples = []
    n_parse_err = 0
    for path in files:
        date = path.parent.name
        try:
            all_examples.extend(extract_episode_examples(path, date, archetype_map))
        except Exception as e:
            n_parse_err += 1
            if n_parse_err <= 5:
                print("parse error on", path.name, ":", repr(e))
    print("Parse errors:", n_parse_err, "/", len(files))
    print("Total (episode, side, cutoff) examples extracted:", len(all_examples))

    n_perspectives = len(all_examples) // len(CUTOFFS)
    print("Usable (episode, side) perspectives (named-archetype opponent):", n_perspectives)

    # --- temporal split ---
    dates = sorted({e["date"] for e in all_examples})
    n_dates = len(dates)
    n_test_dates = max(1, round(TEST_DATE_FRACTION * n_dates))
    train_dates = dates[: n_dates - n_test_dates]
    test_dates = dates[n_dates - n_test_dates:]
    cutoff_date = test_dates[0]
    assert max(train_dates) < min(test_dates), "temporal leakage: train/test date overlap"
    print(f"VERIFIED FACT (temporal split): {len(train_dates)} train dates "
          f"({train_dates[0]}..{train_dates[-1]}), {len(test_dates)} test dates "
          f"({test_dates[0]}..{test_dates[-1]}), cutoff={cutoff_date}, "
          f"max(train_date) < min(test_date) = {max(train_dates) < min(test_dates)}")

    train_date_set = set(train_dates)
    test_date_set = set(test_dates)
    train_examples = [e for e in all_examples if e["date"] in train_date_set]
    test_examples = [e for e in all_examples if e["date"] in test_date_set]
    print("Train examples (all cutoffs):", len(train_examples), " Test examples (all cutoffs):", len(test_examples))

    # --- known-class universe: archetypes with >=1 training example ---
    known_archetypes = sorted({e["true_archetype"] for e in train_examples})
    print("Known archetypes (>=1 training example):", known_archetypes)

    # per-archetype training example count (constant across cutoffs by construction --
    # verify that explicitly)
    n_a = {}
    for a in known_archetypes:
        counts_per_cutoff = {
            c: sum(1 for e in train_examples if e["true_archetype"] == a and e["turn_cutoff"] == c)
            for c in CUTOFFS
        }
        assert len(set(counts_per_cutoff.values())) == 1, f"denom mismatch across cutoffs for {a}: {counts_per_cutoff}"
        n_a[a] = counts_per_cutoff[CUTOFFS[0]]
    print("Training example counts per known archetype (perspectives, not cutoff-multiplied):")
    for a in known_archetypes:
        print("  ", a.encode("ascii", "replace").decode("ascii"), "=", n_a[a])

    # --- prior, restricted + floored + renormalized over known_archetypes ---
    floored_archetypes = []
    prior_raw = {}
    for a in known_archetypes:
        v = float(prior_filtered.get(a, 0.0))
        if v <= 0.0:
            floored_archetypes.append(a)
            v = PRIOR_FLOOR
        prior_raw[a] = v
    total = sum(prior_raw.values())
    prior = {a: v / total for a, v in prior_raw.items()}
    print("Archetypes floored to", PRIOR_FLOOR, "before renormalization (had prior_filtered==0):",
          [a.encode("ascii", "replace").decode("ascii") for a in floored_archetypes])
    print("Renormalized prior over known archetypes (sums to 1):")
    for a in known_archetypes:
        print("  ", a.encode("ascii", "replace").decode("ascii"), "=", round(prior[a], 5))

    archetypes_list = known_archetypes  # fixed order
    n_classes = len(archetypes_list)
    a_index = {a: i for i, a in enumerate(archetypes_list)}
    prior_vec = np.array([prior[a] for a in archetypes_list])

    # --- vocabulary: union of revealed ids across FULL-GAME train examples ---
    vocab = sorted({cid for e in train_examples if e["turn_cutoff"] == "full" for cid in e["evidence"]})
    v_index = {cid: i for i, cid in enumerate(vocab)}
    n_vocab = len(vocab)
    print("Vocabulary size (unique opponent Pokemon ids ever revealed in training, full-game):", n_vocab)

    # --- per-cutoff likelihood tables: P(card X revealed by cutoff | archetype), Laplace-smoothed ---
    log_p = {}      # cutoff -> (n_classes, n_vocab) log P(revealed | archetype)
    log_1mp = {}    # cutoff -> (n_classes, n_vocab) log (1 - P(revealed | archetype))
    for cutoff in CUTOFFS:
        k = np.zeros((n_classes, n_vocab))
        for e in train_examples:
            if e["turn_cutoff"] != cutoff:
                continue
            ai = a_index[e["true_archetype"]]
            for cid in e["evidence"]:
                vi = v_index.get(cid)
                if vi is not None:
                    k[ai, vi] += 1
        n_arr = np.array([n_a[a] for a in archetypes_list]).reshape(-1, 1)
        p_hat = (k + LAPLACE_ALPHA) / (n_arr + 2 * LAPLACE_ALPHA)
        p_hat = np.clip(p_hat, 1e-9, 1 - 1e-9)
        log_p[cutoff] = np.log(p_hat)
        log_1mp[cutoff] = np.log(1 - p_hat)

    def bayesian_posterior(evidence: frozenset, cutoff) -> np.ndarray:
        evi_vec = np.zeros(n_vocab, dtype=bool)
        for cid in evidence:
            vi = v_index.get(cid)
            if vi is not None:
                evi_vec[vi] = True
        lp = log_p[cutoff]
        l1mp = log_1mp[cutoff]
        log_post = np.log(prior_vec) + (lp[:, evi_vec].sum(axis=1) if evi_vec.any() else 0.0) \
                   + l1mp[:, ~evi_vec].sum(axis=1)
        log_post = log_post - log_post.max()
        post = np.exp(log_post)
        post = post / post.sum()
        return post

    most_popular_idx = int(np.argmax(prior_vec))
    most_popular_vec = np.full(n_classes, 1e-9)
    most_popular_vec[most_popular_idx] = 1.0
    most_popular_vec = most_popular_vec / most_popular_vec.sum()

    def evaluate_posteriors(records, name):
        """records: list of dict(true_archetype, posterior(np.array), coverage(bool), evidence_n(int))
        Returns a list of per-example dicts with computed metrics fields (top1/top2/logloss/brier)."""
        out = []
        for r in records:
            true_a = r["true_archetype"]
            oov = true_a not in a_index
            post = r["posterior"]
            top1_i = int(np.argmax(post))
            top1_a = archetypes_list[top1_i]
            top1_p = float(post[top1_i])
            order = np.argsort(-post)
            top2_as = {archetypes_list[order[0]], archetypes_list[order[1]]} if n_classes > 1 else {archetypes_list[order[0]]}
            ent = float(-np.sum(post * np.log(np.clip(post, 1e-12, 1.0))))
            tier = confidence_tier(top1_p)
            if not oov:
                ti = a_index[true_a]
                p_true = max(post[ti], LOGLOSS_EPS)
                logloss = -math.log(p_true)
                brier = float(np.sum((post - np.eye(n_classes)[ti]) ** 2))
                top1_correct = (top1_a == true_a)
                top2_correct = (true_a in top2_as)
            else:
                logloss = np.nan
                brier = np.nan
                top1_correct = False
                top2_correct = False
            out.append({
                **r,
                "oov_true_archetype": oov,
                "predicted_archetype": top1_a,
                "posterior_top1": top1_p,
                "posterior_entropy": ent,
                "confidence_tier": tier,
                "top1_correct": top1_correct,
                "top2_correct": top2_correct,
                "logloss": logloss,
                "brier": brier,
            })
        return out

    # --- score every test example under all 3 models, per cutoff ---
    bayesian_scored = {c: [] for c in CUTOFFS}
    recent_prior_scored = {c: [] for c in CUTOFFS}
    most_popular_scored = {c: [] for c in CUTOFFS}

    for e in test_examples:
        c = e["turn_cutoff"]
        evidence = e["evidence"]
        coverage = len(evidence) > 0
        post_bayes = bayesian_posterior(evidence, c)
        bayesian_scored[c].append({
            "episode_id": e["episode_id"], "side": e["side"], "turn_cutoff": c,
            "true_archetype": e["true_archetype"], "posterior": post_bayes,
            "coverage": coverage, "evidence_n": len(evidence),
        })
        recent_prior_scored[c].append({
            "episode_id": e["episode_id"], "side": e["side"], "turn_cutoff": c,
            "true_archetype": e["true_archetype"], "posterior": prior_vec,
            "coverage": False, "evidence_n": len(evidence),
        })
        most_popular_scored[c].append({
            "episode_id": e["episode_id"], "side": e["side"], "turn_cutoff": c,
            "true_archetype": e["true_archetype"], "posterior": most_popular_vec,
            "coverage": False, "evidence_n": len(evidence),
        })

    models_scored = {
        "bayesian": bayesian_scored,
        "recent_prior": recent_prior_scored,
        "most_popular": most_popular_scored,
    }

    metrics_rows = []
    raw_rows = []  # bayesian only, per spec

    def summarize(records_eval, model_name, cutoff, tier_or_overall):
        in_universe = [r for r in records_eval if not r["oov_true_archetype"]]
        n_test = len(in_universe)
        if n_test == 0:
            return {
                "model": model_name, "turn_cutoff": cutoff, "tier_or_overall": tier_or_overall,
                "n_test": 0, "n_oov_excluded": sum(1 for r in records_eval if r["oov_true_archetype"]),
                "top1_acc": np.nan, "top2_acc": np.nan, "logloss": np.nan, "brier": np.nan,
                "coverage": np.nan, "tier_fraction": np.nan,
            }
        top1_acc = np.mean([r["top1_correct"] for r in in_universe])
        top2_acc = np.mean([r["top2_correct"] for r in in_universe])
        logloss = np.mean([r["logloss"] for r in in_universe])
        brier = np.mean([r["brier"] for r in in_universe])
        coverage = np.mean([r["coverage"] for r in in_universe])
        return {
            "model": model_name, "turn_cutoff": cutoff, "tier_or_overall": tier_or_overall,
            "n_test": n_test, "n_oov_excluded": sum(1 for r in records_eval if r["oov_true_archetype"]),
            "top1_acc": top1_acc, "top2_acc": top2_acc, "logloss": logloss, "brier": brier,
            "coverage": coverage,
            "tier_fraction": None,
        }

    for model_name, scored_by_cutoff in models_scored.items():
        for cutoff in CUTOFFS:
            evaluated = evaluate_posteriors(scored_by_cutoff[cutoff], model_name)
            total_n = len(evaluated)
            overall = summarize(evaluated, model_name, cutoff, "OVERALL")
            metrics_rows.append(overall)
            for tier_name, _lo, _hi in TIER_BOUNDS:
                subset = [r for r in evaluated if r["confidence_tier"] == tier_name]
                row = summarize(subset, model_name, cutoff, tier_name)
                row["tier_fraction"] = (len(subset) / total_n) if total_n else np.nan
                metrics_rows.append(row)
            if model_name == "bayesian":
                for r in evaluated:
                    raw_rows.append({
                        "episode_id": r["episode_id"],
                        "side": r["side"],
                        "turn_cutoff": r["turn_cutoff"],
                        "true_archetype": r["true_archetype"],
                        "predicted_archetype": r["predicted_archetype"],
                        "posterior_top1": r["posterior_top1"],
                        "posterior_entropy": r["posterior_entropy"],
                        "confidence_tier": r["confidence_tier"],
                        "oov_true_archetype": r["oov_true_archetype"],
                        "coverage": r["coverage"],
                        "evidence_n": r["evidence_n"],
                        "top1_correct": r["top1_correct"],
                        "model": "bayesian",
                    })

    metrics_df = pd.DataFrame(metrics_rows)
    raw_df = pd.DataFrame(raw_rows)

    OUT_METRICS.parent.mkdir(parents=True, exist_ok=True)
    metrics_df.to_csv(OUT_METRICS, index=False, encoding="utf-8")
    raw_df.to_csv(OUT_RAW, index=False, encoding="utf-8")
    print("Wrote", OUT_METRICS, "rows=", len(metrics_df))
    print("Wrote", OUT_RAW, "rows=", len(raw_df))

    # console summary (ASCII-safe)
    print("\n--- OVERALL metrics by model x cutoff ---")
    overall_only = metrics_df[metrics_df["tier_or_overall"] == "OVERALL"]
    for _, r in overall_only.iterrows():
        print(f"{r['model']:14s} cutoff={str(r['turn_cutoff']):5s} n={r['n_test']:5d} "
              f"top1={r['top1_acc']:.4f} top2={r['top2_acc']:.4f} "
              f"logloss={r['logloss']:.4f} brier={r['brier']:.4f} coverage={r['coverage']:.4f}")


if __name__ == "__main__":
    main()
