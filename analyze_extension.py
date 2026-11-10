"""Freeze decisions before holdout, then report costs and calibration overhead."""

import argparse
import csv
import json
import math
from pathlib import Path
import numpy as np
from run_pilot import ROOT
from summarize import wilson

EXT = ROOT / "extension"


def read_records(phase):
    return [
        json.loads(line)
        for line in (EXT / phase / "attempts.jsonl").read_text().splitlines()
    ]


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


def finite(value):
    return float(value) if math.isfinite(value) else "infinite"


def arrays(records):
    elapsed = np.array([r["elapsed_seconds"] for r in records])
    accepted = np.array(
        [r["status"] == "solved" and r["softlock_states"] == 0 for r in records],
        dtype=int,
    )
    return (elapsed, accepted)


def bootstrap(elapsed, accepted, rng, count):
    indices = rng.integers(0, len(elapsed), (count, len(elapsed)))
    successes = accepted[indices].sum(axis=1)
    costs = np.full(count, np.inf)
    np.divide(elapsed[indices].sum(axis=1), successes, out=costs, where=successes > 0)
    return costs


def compare(records, rng, count=10000):
    (result, samples) = ({}, {})
    for strategy in ("baseline", "constrained"):
        group = [r for r in records if r["strategy"] == strategy]
        assert group
        (elapsed, accepted) = arrays(group)
        successes = int(accepted.sum())
        samples[strategy] = bootstrap(elapsed, accepted, rng, count)
        result[strategy] = {
            "attempts": len(group),
            "accepted": successes,
            "q": successes / len(group),
            "q_wilson_95": wilson(successes, len(group)),
            "mean_attempt_seconds": float(elapsed.mean()),
            "total_seconds": float(elapsed.sum()),
            "seconds_per_accepted": (
                finite(elapsed.sum() / successes) if successes else "infinite"
            ),
            "cost_bootstrap_95": [
                finite(v)
                for v in np.quantile(
                    samples[strategy], [0.025, 0.975], method="inverted_cdf"
                )
            ],
            "zero_acceptance_bootstraps": int(np.isinf(samples[strategy]).sum()),
            "unique_levels": len(
                {r.get("level_content") for r in group if r["status"] == "solved"}
            ),
            "statuses": {
                s: sum((r["status"] == s for r in group))
                for s in sorted({r["status"] for r in group})
            },
            "terminal_goal_changed": sum(
                (
                    r["status"] == "solved"
                    and (r["softlock_states"] > 0) != (r["terminal_goal_softlocks"] > 0)
                    for r in group
                )
            ),
        }
    if not all((result[s]["accepted"] > 0 for s in result)):
        result.update(
            {"recommendation": "abstain", "ratio": None, "ratio_bootstrap_95": None}
        )
        return result
    ratio = samples["baseline"] / samples["constrained"]
    (lo, hi) = np.quantile(ratio, [0.025, 0.975], method="inverted_cdf")
    result["ratio"] = (
        result["baseline"]["seconds_per_accepted"]
        / result["constrained"]["seconds_per_accepted"]
    )
    result["ratio_bootstrap_95"] = [finite(lo), finite(hi)]
    result["recommendation"] = (
        "constrained" if lo > 1 else "baseline" if hi < 1 else "abstain"
    )
    result["q_threshold"] = (
        result["baseline"]["mean_attempt_seconds"]
        / result["constrained"]["seconds_per_accepted"]
    )
    return result


def freeze():
    assert not (
        EXT / "evaluation"
    ).exists(), "Evaluation must follow frozen predictions"
    target = EXT / "predictions.json"
    assert not target.exists(), "Do not replace frozen predictions"
    plan = json.loads((EXT / "plan.json").read_text())
    records = read_records("calibration")
    assert len(records) == 160
    rng = np.random.default_rng(plan["bootstrap_seed"])
    predictions = {"cells": {}}
    for walls in plan["transfer"]["walls"]:
        predictions["cells"][str(walls)] = compare(
            [r for r in records if r["walls"] == walls], rng
        )
    write_json(target, predictions)
    print(json.dumps(predictions, indent=2))


def summarize():
    plan = json.loads((EXT / "plan.json").read_text())
    frozen = json.loads((EXT / "predictions.json").read_text())
    audit = json.loads((EXT / "source_audit.json").read_text())
    (timing, evaluation) = (read_records("timing"), read_records("evaluation"))
    assert len(timing) == 480 and len(evaluation) == 240
    environment = json.loads((EXT / "evaluation/environment.json").read_text())
    calibration = read_records("calibration")
    assert not {r["seed"] for r in calibration} & {r["seed"] for r in evaluation}
    rng = np.random.default_rng(plan["bootstrap_seed"] + 1)
    results = {
        "new_measured_attempts": len(timing) + len(calibration) + len(evaluation),
        "timing": {},
        "transfer": {},
        "paired_timing": {},
    }
    timing_startup = json.loads((EXT / "timing/environment.json").read_text())[
        "worker_startup_seconds"
    ]
    for example in ("A", "B"):
        for mode in ("cold", "warm"):
            group = [r for r in timing if r["example"] == example and r["mode"] == mode]
            summary = compare(group, rng)
            summary["startup_seconds"] = timing_startup if mode == "warm" else 0
            for strategy in ("baseline", "constrained"):
                summary[strategy]["standalone_sample_cost_with_startup"] = (
                    (summary[strategy]["total_seconds"] + summary["startup_seconds"])
                    / summary[strategy]["accepted"]
                    if summary[strategy]["accepted"]
                    else "infinite"
                )
            results["timing"][f"{example}40_{mode}"] = summary
        for strategy in ("baseline", "constrained"):
            cold = {
                r["seed"]: r
                for r in timing
                if r["example"] == example
                and r["strategy"] == strategy
                and (r["mode"] == "cold")
            }
            warm = {
                r["seed"]: r
                for r in timing
                if r["example"] == example
                and r["strategy"] == strategy
                and (r["mode"] == "warm")
            }
            assert cold.keys() == warm.keys()
            assert all(
                (cold[s]["level_content"] == warm[s]["level_content"] for s in cold)
            )
            differences = np.array(
                [
                    cold[s]["elapsed_seconds"] - warm[s]["elapsed_seconds"]
                    for s in sorted(cold)
                ]
            )
            indices = rng.integers(0, len(differences), (10000, len(differences)))
            results["paired_timing"][f"{example}40_{strategy}"] = {
                "identical_level_pairs": len(cold),
                "mean_cold_minus_warm_seconds": float(differences.mean()),
                "paired_bootstrap_95": np.quantile(
                    differences[indices].mean(axis=1), [0.025, 0.975]
                ).tolist(),
            }
    calibration_startup = json.loads(
        (EXT / "calibration/environment.json").read_text()
    )["worker_startup_seconds"]
    setup = (
        audit["preparation_seconds"]
        + plan["amendment"]["additional_preparation_seconds"]
    )
    for walls in (40, 60):
        summary = compare([r for r in evaluation if r["walls"] == walls], rng)
        decision = frozen["cells"][str(walls)]["recommendation"]
        summary["frozen_recommendation"] = decision
        summary["calibration_seconds_including_setup"] = (
            sum((r["elapsed_seconds"] for r in calibration if r["walls"] == walls))
            + calibration_startup
            + setup
        )
        if decision != "abstain" and all(
            (
                isinstance(summary[s]["seconds_per_accepted"], float)
                for s in ("baseline", "constrained")
            )
        ):
            other = "baseline" if decision == "constrained" else "constrained"
            chosen_cost = summary[decision]["seconds_per_accepted"]
            other_cost = summary[other]["seconds_per_accepted"]
            overhead = summary["calibration_seconds_including_setup"]
            savings = other_cost - chosen_cost
            summary["point_estimate_choice_correct"] = savings > 0
            summary["holdout_interval_supports_choice"] = (
                summary["recommendation"] == decision
            )
            summary["break_even_outputs_point_estimate"] = (
                math.floor(overhead / savings) + 1 if savings > 0 else None
            )
            horizon = plan["batch_horizon"]
            summary["cost_at_fixed_horizon"] = {
                "outputs": horizon,
                "calibrate_then_chosen": overhead + horizon * chosen_cost,
                "always_baseline": horizon
                * summary["baseline"]["seconds_per_accepted"],
                "always_constrained": horizon
                * summary["constrained"]["seconds_per_accepted"],
                "note": "Projected from holdout empirical means, not an observed production batch. Common future startup omitted from all arms. All calibration/setup costs conservatively charged; no credit for calibration outputs.",
            }
            group = [r for r in evaluation if r["walls"] == walls]
            bs = {}
            for strategy in ("baseline", "constrained"):
                bs[strategy] = bootstrap(
                    *arrays([r for r in group if r["strategy"] == strategy]), rng, 10000
                )
            difference = bs[other] - bs[decision]
            horizon_samples = np.full(10000, np.inf)
            positive = difference > 0
            horizon_samples[positive] = np.floor(overhead / difference[positive]) + 1
            summary["break_even_outputs_bootstrap_95"] = [
                finite(v)
                for v in np.quantile(
                    horizon_samples, [0.025, 0.975], method="inverted_cdf"
                )
            ]
        results["transfer"][str(walls)] = summary
    results["limitations"] = [
        "One machine, one randomized execution series; attempt bootstrap does not establish across-session timing variability.",
        "Cold/warm equality establishes same generated outputs for measured pairs; imported modules reused, not constraints.",
        "External geometry and pattern both change; source-specific causal attribution is not identifiable.",
        "Calibration/holdout split tests new seeds in two local configurations, not unseen games without calibration.",
        "Cost rule is elementary; contribution is empirical validation, including abstention and calibration overhead.",
        "Bootstrap intervals are nominal pointwise exploratory intervals; zero failures in constrained samples do not prove reliability beyond the formal finite model.",
    ]
    write_json(EXT / "results.json", results)
    with (EXT / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "series",
                "cell",
                "strategy",
                "attempts",
                "accepted",
                "seconds_per_accepted",
            ]
        )
        for series in ("timing", "transfer"):
            for cell, summary in results[series].items():
                for strategy in ("baseline", "constrained"):
                    s = summary[strategy]
                    writer.writerow(
                        [
                            series,
                            cell,
                            strategy,
                            s["attempts"],
                            s["accepted"],
                            s["seconds_per_accepted"],
                        ]
                    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "summarize"])
    action = parser.parse_args().action
    freeze() if action == "freeze" else summarize()
