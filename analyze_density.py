"""Analyze the fixed density extension together with the separate 50% reference."""

import csv
import json
import numpy as np
from analyze_followup import attempt_arrays, interval, resample_cost
from run_pilot import ROOT
from summarize import wilson


def main():
    rng = np.random.default_rng(91109)
    repetitions = 10000
    summaries = []
    raw = {}
    for walls, folder in [(40, "density-40"), (50, "followup"), (60, "density-60")]:
        rows = [
            json.loads(line)
            for line in (ROOT / folder / "attempts.jsonl").read_text().splitlines()
        ]
        raw[walls] = rows
        cost_samples = {}
        result = {"walls": walls, "series": folder}
        for strategy, expected in [("baseline", 100), ("constrained", 20)]:
            group = [row for row in rows if row["strategy"] == strategy]
            assert len(group) == expected
            (elapsed, accepted) = attempt_arrays(group)
            solved = [row for row in group if row["status"] == "solved"]
            stuck = sum((row["softlock_states"] > 0 for row in solved))
            (costs, zero_success_samples) = resample_cost(
                elapsed, accepted, rng, repetitions
            )
            cost_samples[strategy] = costs
            result[strategy] = {
                "attempts": len(group),
                "solved": len(solved),
                "accepted": int(accepted.sum()),
                "softlocked": stuck,
                "prevalence": stuck / len(solved) if solved else None,
                "prevalence_wilson_95": wilson(stuck, len(solved)),
                "total_seconds": float(elapsed.sum()),
                "seconds_per_accepted": (
                    float(elapsed.sum() / accepted.sum()) if accepted.sum() else None
                ),
                "cost_bootstrap_95": interval(costs),
                "zero_acceptance_bootstrap_samples": zero_success_samples,
                "timeouts": sum((row["status"] == "timeout" for row in group)),
                "unique_levels": len({row["level_content"] for row in solved}),
                "terminal_goal_softlocked": sum(
                    (row["terminal_goal_softlocks"] > 0 for row in solved)
                ),
                "median_shortest_path": (
                    float(np.median([row["shortest_path"] for row in solved]))
                    if solved
                    else None
                ),
            }
        (base, constrained) = (result["baseline"], result["constrained"])
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio_samples = cost_samples["baseline"] / cost_samples["constrained"]
        result["cost_ratio"] = (
            base["seconds_per_accepted"] / constrained["seconds_per_accepted"]
            if base["seconds_per_accepted"] and constrained["seconds_per_accepted"]
            else None
        )
        result["cost_ratio_pointwise_95"] = (
            interval(ratio_samples) if not np.isnan(ratio_samples).any() else None
        )
        summaries.append(result)
    prevalence_samples = {}
    for walls in (40, 60):
        group = [row for row in raw[walls] if row["strategy"] == "baseline"]
        solved = np.array([row["status"] == "solved" for row in group], dtype=int)
        stuck = np.array(
            [row["status"] == "solved" and row["softlock_states"] > 0 for row in group],
            dtype=int,
        )
        indices = rng.integers(0, len(group), (repetitions, len(group)))
        prevalence_samples[walls] = stuck[indices].sum(axis=1) / solved[indices].sum(
            axis=1
        )
    contrast = prevalence_samples[40] - prevalence_samples[60]
    result = {
        "density_results": summaries,
        "primary_prevalence_difference_40_minus_60": summaries[0]["baseline"][
            "prevalence"
        ]
        - summaries[2]["baseline"]["prevalence"],
        "primary_difference_bootstrap_95": interval(contrast),
        "bootstrap_repetitions": repetitions,
        "bootstrap_seed": 91109,
        "interpretation_limits": "Prevalence is conditional on successful generation. Cost intervals are pointwise exploratory; 50% was measured in an earlier execution batch. Zero acceptance means no finite empirical cost, not proof of infinite expected cost. No uniform sampling assumption is justified.",
    }
    (ROOT / "density_results.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    flat = []
    for row in summaries:
        for strategy in ("baseline", "constrained"):
            flat.append({"walls": row["walls"], "strategy": strategy, **row[strategy]})
    with (ROOT / "density_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.DictWriter(output, fieldnames=flat[0].keys())
        writer.writeheader()
        writer.writerows(flat)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
