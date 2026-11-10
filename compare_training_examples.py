"""Compare fixed training examples using existing measured records."""

import json
import numpy as np
from analyze_followup import attempt_arrays, interval, resample_cost
from run_pilot import ROOT
from summarize import wilson


def main():
    rng = np.random.default_rng(121109)
    repetitions = 10000
    summary = []
    prevalence_samples = {}
    for label, prefix in [("A", "density"), ("B", "training-b")]:
        for walls in (40, 60):
            folder = ROOT / f"{prefix}-{walls}"
            records = [
                json.loads(line)
                for line in (folder / "attempts.jsonl").read_text().splitlines()
            ]
            output = {"example": label, "walls": walls}
            cost_samples = {}
            for strategy, expected in [("baseline", 100), ("constrained", 20)]:
                group = [row for row in records if row["strategy"] == strategy]
                assert len(group) == expected and all(
                    (row["status"] == "solved" for row in group)
                )
                (elapsed, accepted) = attempt_arrays(group)
                (cost_samples[strategy], empty) = resample_cost(
                    elapsed, accepted, rng, repetitions
                )
                output[strategy] = {
                    "attempts": len(group),
                    "accepted": int(accepted.sum()),
                    "softlocked": int(len(group) - accepted.sum()),
                    "prevalence_wilson_95": wilson(
                        int(len(group) - accepted.sum()), len(group)
                    ),
                    "seconds_per_accepted": float(elapsed.sum() / accepted.sum()),
                    "cost_pointwise_95": interval(cost_samples[strategy]),
                    "zero_success_bootstrap_samples": empty,
                }
                if strategy == "baseline":
                    indices = rng.integers(0, len(group), (repetitions, len(group)))
                    prevalence_samples[label, walls] = 1 - accepted[indices].mean(
                        axis=1
                    )
            output["cost_ratio_baseline_over_constrained"] = (
                output["baseline"]["seconds_per_accepted"]
                / output["constrained"]["seconds_per_accepted"]
            )
            output["ratio_pointwise_95"] = interval(
                cost_samples["baseline"] / cost_samples["constrained"]
            )
            summary.append(output)
    a_effect = prevalence_samples["A", 40] - prevalence_samples["A", 60]
    b_effect = prevalence_samples["B", 40] - prevalence_samples["B", 60]
    b = [row for row in summary if row["example"] == "B"]
    result = {
        "conditions": summary,
        "B_prevalence_40_minus_60": (
            b[0]["baseline"]["softlocked"] - b[1]["baseline"]["softlocked"]
        )
        / 100,
        "B_prevalence_difference_pointwise_95": interval(b_effect),
        "A_minus_B_at_40_pointwise_95": interval(
            prevalence_samples["A", 40] - prevalence_samples["B", 40]
        ),
        "A_minus_B_at_60_pointwise_95": interval(
            prevalence_samples["A", 60] - prevalence_samples["B", 60]
        ),
        "difference_of_density_differences_pointwise_95": interval(a_effect - b_effect),
        "bootstrap_seed": 121109,
        "repetitions": repetitions,
        "interpretation": "Pointwise exploratory comparisons; separate execution batches; B is a designed sensitivity case, not an external benchmark.",
    }
    (ROOT / "training_comparison.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
