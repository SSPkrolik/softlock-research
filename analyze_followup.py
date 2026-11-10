"""Estimate cost uncertainty by resampling complete attempts, including rejections."""

import json
import math
import sys
from pathlib import Path
import numpy as np
from summarize import wilson

ROOT = Path(__file__).resolve().parent


def attempt_arrays(records):
    elapsed = np.array(
        [
            row["generation_seconds"] + row.get("validation_seconds", 0)
            for row in records
        ]
    )
    accepted = np.array(
        [row["status"] == "solved" and row["softlock_states"] == 0 for row in records],
        dtype=int,
    )
    return (elapsed, accepted)


def resample_cost(elapsed, accepted, random, repetitions):
    indices = random.integers(0, len(elapsed), size=(repetitions, len(elapsed)))
    total_time = elapsed[indices].sum(axis=1)
    successes = accepted[indices].sum(axis=1)
    costs = np.full(repetitions, np.inf)
    np.divide(total_time, successes, out=costs, where=successes > 0)
    return (costs, int(np.sum(successes == 0)))


def interval(values):
    bounds = np.quantile(values, [0.025, 0.975], method="inverted_cdf")
    return [float(value) if math.isfinite(value) else "infinite" for value in bounds]


def main():
    folder = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "followup")
    records = [
        json.loads(line)
        for line in (folder / "attempts.jsonl").read_text().splitlines()
    ]
    plan = json.loads((ROOT / "followup_plan.json").read_text())
    random = np.random.default_rng(71109)
    repetitions = 10000
    result = {"bootstrap_repetitions": repetitions, "bootstrap_seed": 71109}
    bootstraps = {}
    for strategy in ("baseline", "constrained"):
        group = [row for row in records if row["strategy"] == strategy]
        assert len(group) == plan[f"{strategy}_attempts"]
        assert all(
            (row["status"] == "solved" for row in group)
        ), "Inspect failures before interpreting inference."
        (elapsed, accepted) = attempt_arrays(group)
        (bootstraps[strategy], empty) = resample_cost(
            elapsed, accepted, random, repetitions
        )
        result[strategy] = {
            "attempts": len(group),
            "accepted": int(accepted.sum()),
            "softlocked": int(len(group) - accepted.sum()),
            "prevalence_wilson_95": wilson(
                int(len(group) - accepted.sum()), len(group)
            ),
            "seconds_per_accepted": float(elapsed.sum() / accepted.sum()),
            "cost_bootstrap_95": interval(bootstraps[strategy]),
            "bootstrap_zero_acceptance_samples": empty,
            "unique_levels": len({row["level_content"] for row in group}),
            "terminal_goal_classification_changes": sum(
                (
                    (row["softlock_states"] > 0) != (row["terminal_goal_softlocks"] > 0)
                    for row in group
                )
            ),
        }
    ratio = bootstraps["baseline"] / bootstraps["constrained"]
    result["cost_ratio_baseline_over_constrained"] = (
        result["baseline"]["seconds_per_accepted"]
        / result["constrained"]["seconds_per_accepted"]
    )
    result["cost_ratio_bootstrap_95"] = interval(ratio)
    result["constrained_advantage_supported"] = bool(
        np.quantile(ratio, 0.025, method="inverted_cdf") > 1
    )
    result["limitations"] = (
        "Nominal percentile bootstrap under independent-attempt, stable-runtime assumptions; one randomized execution series, one generator configuration; no general performance claim. The constrained run has no observed failures, so its empirical bootstrap cannot model unseen failures."
    )
    (folder / "inference.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
