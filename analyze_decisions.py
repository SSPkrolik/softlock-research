"""Retrospective decision boundaries, holdout costs, and robustness checks.

No generator is run. Common added overhead is a hypothetical per-attempt cost;
varying acceptance in the map holds attempt times fixed and is not a new level
distribution. All uncertainty is conditional on observed sessions and samples.
"""

import csv
import json
import math
from pathlib import Path
import numpy as np
from analyze_replication import summarize

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "decision_analysis"
REPS = 10000


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def ci(values):
    return np.quantile(values, [0.025, 0.975], method="inverted_cdf").tolist()


def binomial_cdf(k, n, p):
    if p <= 0:
        return 1.0
    if p >= 1:
        return float(k >= n)
    logs = [
        math.lgamma(n + 1)
        - math.lgamma(j + 1)
        - math.lgamma(n - j + 1)
        + j * math.log(p)
        + (n - j) * math.log1p(-p)
        for j in range(k + 1)
    ]
    top = max(logs)
    return min(1.0, math.exp(top) * sum((math.exp(x - top) for x in logs)))


def exact_interval(k, n, alpha=0.025):

    def solve(count, target):
        (lo, hi) = (0.0, 1.0)
        for _ in range(65):
            mid = (lo + hi) / 2
            if binomial_cdf(count, n, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    return [
        0.0 if k == 0 else solve(k - 1, 1 - alpha / 2),
        1.0 if k == n else solve(k, alpha / 2),
    ]


def paired_arrays(records, strategy):
    lookup = {
        (r["session"], r["seed"], r["mode"]): r
        for r in records
        if r["strategy"] == strategy
    }
    rows = []
    for session, seed in sorted({(s, seed) for (s, seed, mode) in lookup}):
        (cold, warm) = [lookup[session, seed, mode] for mode in ("cold", "warm")]
        assert cold["level_content"] == warm["level_content"]
        rows.append(
            [
                cold["elapsed_seconds"],
                warm["elapsed_seconds"],
                int(cold["status"] == "solved" and cold["softlock_states"] == 0),
                session,
            ]
        )
    return np.array(rows)


def draw_stats(array, rng):
    totals = np.zeros((REPS, 3))
    for session in np.unique(array[:, 3]):
        block = array[array[:, 3] == session, :3]
        indices = rng.integers(0, len(block), (REPS, len(block)))
        totals += block[indices].sum(axis=1)
    return totals / len(array)


def main():
    OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(20261110)
    records = sum(
        [
            read(ROOT / "replication" / f"session-{s}" / "attempts.jsonl")
            for s in (1, 2, 3)
        ],
        [],
    )
    report = {
        "status": "Retrospective exploratory analysis; no new generation or prospective validation",
        "bootstrap_replicates": REPS,
        "conditions": {},
        "holdout_costs": {},
    }
    maps = []
    for mechanic in ("driller", "slide"):
        group = [r for r in records if r["mechanic"] == mechanic]
        (a, b) = [paired_arrays(group, s) for s in ("baseline", "constrained")]
        (ar, br) = (draw_stats(a, rng), draw_stats(b, rng))
        (am, bm) = (a[:, :3].mean(axis=0), b[:, :3].mean(axis=0))
        result = {
            "accepted": [int(a[:, 2].sum()), int(b[:, 2].sum())],
            "attempts": [len(a), len(b)],
            "mean_attempt_times_cold_warm": [am[:2].tolist(), bm[:2].tolist()],
            "acceptance_exact_97_5": [
                exact_interval(int(a[:, 2].sum()), len(a)),
                exact_interval(int(b[:, 2].sum()), len(b)),
            ],
        }
        cross = (ar[:, 2] * br[:, 1] - br[:, 2] * ar[:, 1]) / (br[:, 2] - ar[:, 2])
        result["common_added_overhead_crossing_seconds"] = float(
            (am[2] * bm[1] - bm[2] * am[1]) / (bm[2] - am[2])
        )
        result["crossing_interval"] = ci(cross)
        for h in np.linspace(0, 0.25, 101):
            boundary = (ar[:, 1] + h) * br[:, 2] / (br[:, 1] + h)
            (low, high) = ci(boundary)
            maps.append(
                [
                    mechanic,
                    float(h),
                    float((am[1] + h) * bm[2] / (bm[1] + h)),
                    low,
                    high,
                ]
            )
        result["warm_boundary_at_zero"] = ci(ar[:, 1] * br[:, 2] / br[:, 1])
        result["uncertainty_decomposition"] = {}
        result["acceptance_only_ratio_bands"] = {}
        for mode, col in (("cold", 0), ("warm", 1)):
            valid = (ar[:, 2] > 0) & (br[:, 2] > 0)
            time_part = np.log(ar[valid, col] / br[valid, col])
            acceptance_part = np.log(br[valid, 2] / ar[valid, 2])
            total_var = np.var(time_part + acceptance_part, ddof=1)
            components = [
                np.var(time_part, ddof=1),
                np.var(acceptance_part, ddof=1),
                2 * np.cov(time_part, acceptance_part, ddof=1)[0, 1],
            ]
            assert np.isclose(sum(components), total_var)
            result["uncertainty_decomposition"][mode] = {
                "log_ratio_variance": float(total_var),
                "timing_acceptance_covariance_shares": (
                    np.array(components) / total_var
                ).tolist(),
                "finite_bootstrap_fraction": float(valid.mean()),
                "interpretation": "Algebraic decomposition of conditional bootstrap variance, not causal attribution",
            }
            (qa, qb) = result["acceptance_exact_97_5"]
            result["acceptance_only_ratio_bands"][mode] = [
                float(am[col] / bm[col] * qb[0] / qa[1]),
                float(am[col] / bm[col] * qb[1] / qa[0]),
            ]
        result["leave_one_session_out"] = []
        for dropped in (1, 2, 3):
            r = summarize([row for row in group if row["session"] != dropped], rng)
            result["leave_one_session_out"].append({"dropped_session": dropped, **r})
        capped = [dict(r) for r in group]
        cap_audit = []
        for session in (1, 2, 3):
            for strategy in ("baseline", "constrained"):
                for mode in ("cold", "warm"):
                    subset = [
                        r
                        for r in capped
                        if (r["session"], r["strategy"], r["mode"])
                        == (session, strategy, mode)
                    ]
                    cap = float(
                        np.quantile([r["elapsed_seconds"] for r in subset], 0.99)
                    )
                    cap_audit.append(
                        {
                            "session": session,
                            "strategy": strategy,
                            "mode": mode,
                            "cap": cap,
                            "modified": sum(
                                (r["elapsed_seconds"] > cap for r in subset)
                            ),
                        }
                    )
                    for r in subset:
                        r["elapsed_seconds"] = min(r["elapsed_seconds"], cap)
        result["winsorized_99_sensitivity"] = summarize(capped, rng)
        result["winsorization_audit"] = cap_audit
        result["tail_note"] = (
            "Diagnostic modified-time estimand only; raw uncapped costs remain the primary result; acceptance and all records retained"
        )
        report["conditions"][mechanic] = result
    with (OUT / "boundary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "mechanic",
                "added_seconds_per_attempt",
                "q_threshold",
                "q_threshold_low",
                "q_threshold_high",
            ]
        )
        w.writerows(maps)
    frozen = json.loads((ROOT / "extension/predictions.json").read_text())
    old = json.loads((ROOT / "extension/results.json").read_text())
    evaluation = read(ROOT / "extension/evaluation/attempts.jsonl")
    for walls in (40, 60):
        chosen = frozen["cells"][str(walls)]["recommendation"]
        assert chosen in ("baseline", "constrained")
        samples = {}
        points = {}
        for strategy in ("baseline", "constrained"):
            group = [
                r
                for r in evaluation
                if r["walls"] == walls and r["strategy"] == strategy
            ]
            t = np.array([r["elapsed_seconds"] for r in group])
            ok = np.array(
                [r["status"] == "solved" and r["softlock_states"] == 0 for r in group]
            )
            indices = rng.integers(0, len(t), (REPS, len(t)))
            denom = ok[indices].sum(axis=1)
            costs = np.full(REPS, np.inf)
            np.divide(t[indices].sum(axis=1), denom, out=costs, where=denom > 0)
            samples[strategy] = costs
            points[strategy] = float(t.sum() / ok.sum())
        k = old["transfer"][str(walls)]["calibration_seconds_including_setup"]
        costrows = []
        for h in (1, 5, 10, 20, 25, 50, 100, 250, 1000):
            policy = k + h * samples[chosen]
            best = h * np.minimum(samples["baseline"], samples["constrained"])
            row = {
                "outputs": h,
                "policy_projected_seconds": k + h * points[chosen],
                "excess_over_empirical_best_fixed": k
                + h * points[chosen]
                - h * min(points.values()),
                "excess_interval": ci(policy - best),
            }
            for strategy in ("baseline", "constrained"):
                row["difference_vs_" + strategy] = k + h * (
                    points[chosen] - points[strategy]
                )
                row["difference_interval_vs_" + strategy] = ci(
                    policy - h * samples[strategy]
                )
            costrows.append(row)
        saving = samples["constrained"] - samples[chosen]
        payback = np.full(REPS, np.inf)
        good = saving > 0
        payback[good] = np.floor(k / saving[good]) + 1
        report["holdout_costs"][str(walls)] = {
            "frozen_choice": chosen,
            "fixed_measured_calibration_seconds": k,
            "point_costs": points,
            "horizons": costrows,
            "payback_vs_constraints_interval": ci(payback),
            "nonpositive_saving_fraction": float((~good).mean()),
            "note": "Projection from already-used holdout, not new production batches; K held fixed; empirical best fixed is estimated, not a known oracle; no credit for calibration outputs",
        }
    (OUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "Completed decision map, frozen-choice holdout projections and robustness analyses"
    )


if __name__ == "__main__":
    main()
