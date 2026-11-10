"""Summarize fixed-budget replication without pooling away session differences."""

import csv
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent / "replication"


def interval(values):
    ordered = np.sort(values)
    return [float(ordered[math.ceil(p * len(ordered)) - 1]) for p in (0.025, 0.975)]


def summarize(records, rng):
    strategy_arrays = {}
    result = {}
    for strategy in ("baseline", "constrained"):
        selected = [r for r in records if r["strategy"] == strategy]
        keys = sorted({(r["session"], r["seed"]) for r in selected})
        lookup = {(r["session"], r["seed"], r["mode"]): r for r in selected}
        values = []
        for session, seed in keys:
            (cold, warm) = [lookup[session, seed, mode] for mode in ("cold", "warm")]
            assert cold["status"] == warm["status"]
            assert cold.get("level_content") == warm.get("level_content")
            assert cold.get("softlock_states") == warm.get("softlock_states")
            accepted = cold["status"] == "solved" and cold["softlock_states"] == 0
            if strategy == "constrained" and cold["status"] == "solved":
                assert accepted
            values.append(
                [
                    cold["elapsed_seconds"],
                    warm["elapsed_seconds"],
                    int(accepted),
                    session,
                ]
            )
        array = np.asarray(values)
        strategy_arrays[strategy] = array
        accepted = int(array[:, 2].sum())
        result[strategy] = {
            "attempts": len(array),
            "accepted": accepted,
            "cold_cost": float(array[:, 0].sum() / accepted) if accepted else math.inf,
            "warm_cost": float(array[:, 1].sum() / accepted) if accepted else math.inf,
        }
    (r, g) = (result["baseline"], result["constrained"])
    result["cold_ratio"] = r["cold_cost"] / g["cold_cost"]
    result["warm_ratio"] = r["warm_cost"] / g["warm_cost"]
    boot = {}
    sums = {}
    for strategy, array in strategy_arrays.items():
        totals = np.zeros((10000, 3))
        for session in sorted(set(array[:, 3])):
            block = array[array[:, 3] == session, :3]
            indices = rng.integers(0, len(block), size=(10000, len(block)))
            totals += block[indices].sum(axis=1)
        sums[strategy] = totals[:, :2]
        with np.errstate(divide="ignore", invalid="ignore"):
            boot[strategy] = totals[:, :2] / totals[:, 2, None]
        result[strategy]["zero_acceptance_bootstrap_fraction"] = float(
            np.mean(totals[:, 2] == 0)
        )
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = boot["baseline"] / boot["constrained"]
    result["cold_interval"] = interval(ratios[:, 0])
    result["warm_interval"] = interval(ratios[:, 1])
    (a, b) = (strategy_arrays["baseline"], strategy_arrays["constrained"])
    result["cold_to_warm_ratio_factor"] = float(
        a[:, 0].sum() / a[:, 1].sum() / (b[:, 0].sum() / b[:, 1].sum())
    )
    factor = (
        sums["baseline"][:, 0]
        / sums["baseline"][:, 1]
        / (sums["constrained"][:, 0] / sums["constrained"][:, 1])
    )
    result["factor_interval"] = interval(factor)
    return result


def main():
    records = []
    plan = json.loads((ROOT / "protocol.json").read_text())
    for session in range(1, 4):
        rows = [
            json.loads(line)
            for line in (ROOT / f"session-{session}" / "attempts.jsonl")
            .read_text()
            .splitlines()
        ]
        assert len(rows) == 700
        assert all((r["status"] in ("solved", "unsat") for r in rows))
        records.extend(rows)
    assert len(records) == plan["total_measured_executions"]
    rng = np.random.default_rng(2026110918)
    results = {
        "executions": len(records),
        "paired_draws": len(records) // 2,
        "interval_scope": "Conditional seed resampling within observed sessions; no day/hardware inference",
        "sessions": [],
        "pooled_secondary": [],
    }
    for mechanic in ("driller", "slide"):
        for session in range(1, 4):
            subset = [
                r
                for r in records
                if r["mechanic"] == mechanic and r["session"] == session
            ]
            results["sessions"].append(
                {"mechanic": mechanic, "session": session, **summarize(subset, rng)}
            )
        results["pooled_secondary"].append(
            {
                "mechanic": mechanic,
                **summarize([r for r in records if r["mechanic"] == mechanic], rng),
            }
        )
    (ROOT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    with (ROOT / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "mechanic",
                "session",
                "R_accepted",
                "R_attempts",
                "G_accepted",
                "G_attempts",
                "cold_ratio",
                "warm_ratio",
                "paired_factor",
            ]
        )
        for r in results["sessions"]:
            writer.writerow(
                [
                    r["mechanic"],
                    r["session"],
                    r["baseline"]["accepted"],
                    r["baseline"]["attempts"],
                    r["constrained"]["accepted"],
                    r["constrained"]["attempts"],
                    r["cold_ratio"],
                    r["warm_ratio"],
                    r["cold_to_warm_ratio_factor"],
                ]
            )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
