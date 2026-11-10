"""Frozen predictions and conditional analyses for the prospective stress test."""

import argparse
import json
import math
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "prospective"
DELAYS = [0, 5, 25]


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def interval(values):
    values = np.sort(values)
    return [float(values[math.ceil(p * len(values)) - 1]) for p in (0.025, 0.975)]


def choice(bounds):
    return "R" if bounds[1] < 1 else "G" if bounds[0] > 1 else "abstain"


def arrays(rows, observed):
    """One row per seed; keep all three delay measurements in each resample."""
    result = {}
    for strategy in ("baseline", "constrained"):
        selected = [r for r in rows if r["strategy"] == strategy]
        keys = sorted({(r["session"], r["seed"]) for r in selected})
        lookup = {(r["session"], r["seed"], r.get("delay_ms", 0)): r for r in selected}
        data = []
        for session, seed in keys:
            first = lookup[session, seed, 0]
            accepted = int(
                first["status"] == "solved" and first["softlock_states"] == 0
            )
            times = []
            for delay in DELAYS:
                if observed:
                    row = lookup[session, seed, delay]
                    assert row.get("level_content") == first.get("level_content")
                    assert row["status"] == first["status"]
                    assert row.get("softlock_states") == first.get("softlock_states")
                    times.append(row["elapsed_seconds"])
                else:
                    times.append(first["elapsed_seconds"] + delay / 1000)
            data.append(times + [accepted, session])
        result[strategy] = np.array(data)
    return result


def estimate(rows, observed, rng):
    data = arrays(rows, observed)
    (costs, samples, counts) = ({}, {}, {})
    for strategy, values in data.items():
        accepted = values[:, 3].sum()
        counts[strategy] = {"attempts": len(values), "accepted": int(accepted)}
        costs[strategy] = (
            values[:, :3].sum(axis=0) / accepted if accepted else np.full(3, np.inf)
        )
        totals = np.zeros((10000, 4))
        for session in sorted(set(values[:, 4])):
            block = values[values[:, 4] == session, :4]
            indices = rng.integers(len(block), size=(10000, len(block)))
            totals += block[indices].sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            samples[strategy] = totals[:, :3] / totals[:, 3, None]
    results = []
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = samples["baseline"] / samples["constrained"]
    for index, delay in enumerate(DELAYS):
        bounds = interval(ratios[:, index])
        selected = (
            choice(bounds)
            if all((c["accepted"] for c in counts.values()))
            else "abstain"
        )
        results.append(
            {
                "delay_ms": delay,
                "ratio": float(costs["baseline"][index] / costs["constrained"][index]),
                "interval": bounds,
                "choice": selected,
                "counts": counts,
                "R_cost": float(costs["baseline"][index]),
                "G_cost": float(costs["constrained"][index]),
                "zero_acceptance_fraction_R": float(
                    np.mean(np.isinf(samples["baseline"][:, index]))
                ),
            }
        )
    return (results, samples)


def predict(source):
    target = DEST / f"{source}_predictions.json"
    assert not target.exists(), "Never overwrite frozen predictions"
    start = time.perf_counter()
    if source == "historical":
        rows = []
        for session in range(1, 4):
            rows.extend(
                (
                    r
                    for r in read(
                        ROOT / f"replication/session-{session}/attempts.jsonl"
                    )
                    if r["mode"] == "warm"
                )
            )
    else:
        rows = read(DEST / "calibration/attempts.jsonl")
    rng = np.random.default_rng(2026111022)
    results = {"conditions": []}
    for mechanic in ("driller", "slide"):
        subset = [r for r in rows if r["mechanic"] == mechanic]
        (estimates, _) = estimate(subset, False, rng)
        for entry in estimates:
            results["conditions"].append({"mechanic": mechanic, **entry})
    results["computation_seconds"] = time.perf_counter() - start
    results["frozen_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if source == "calibration":
        startup = json.loads((DEST / "calibration/environment.json").read_text())[
            "worker_startup_seconds"
        ]
        results["K_by_mechanic"] = {
            m: sum((r["elapsed_seconds"] for r in rows if r["mechanic"] == m))
            + startup
            + results["computation_seconds"]
            for m in ("driller", "slide")
        }
    target.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


def analyze():
    rows = read(DEST / "session-1/attempts.jsonl") + read(
        DEST / "session-2/attempts.jsonl"
    )
    old = json.loads((DEST / "historical_predictions.json").read_text())
    calibration = json.loads((DEST / "calibration_predictions.json").read_text())
    lookup = {(r["mechanic"], r["delay_ms"]): r for r in old["conditions"]}
    local = {(r["mechanic"], r["delay_ms"]): r for r in calibration["conditions"]}
    rng = np.random.default_rng(2026111023)
    output = {"sessions": [], "pooled": [], "costs": [], "delay_diagnostics": []}
    for mechanic in ("driller", "slide"):
        for session in (1, 2):
            subset = [
                r for r in rows if r["mechanic"] == mechanic and r["session"] == session
            ]
            (estimates, _) = estimate(subset, True, rng)
            output["sessions"].extend(
                ({"mechanic": mechanic, "session": session, **r} for r in estimates)
            )
        subset = [r for r in rows if r["mechanic"] == mechanic]
        (estimates, boot) = estimate(subset, True, rng)
        for index, entry in enumerate(estimates):
            key = (mechanic, entry["delay_ms"])
            (predicted, observed) = (lookup[key]["choice"], entry["choice"])
            agreement = (
                "abstained"
                if predicted == "abstain"
                else (
                    "unresolved"
                    if observed == "abstain"
                    else "supported" if predicted == observed else "contradicted"
                )
            )
            output["pooled"].append(
                {
                    "mechanic": mechanic,
                    "historical_choice": predicted,
                    "historical_assessment": agreement,
                    **entry,
                }
            )
            chosen = local[key]["choice"]
            action = "R" if chosen == "abstain" else chosen
            k = calibration["K_by_mechanic"][mechanic]
            for horizon in (25, 100, 1000):
                (r, g) = (entry["R_cost"], entry["G_cost"])
                (rb, gb) = (boot["baseline"][:, index], boot["constrained"][:, index])
                cost = k + horizon * (r if action == "R" else g)
                samples = k + horizon * (rb if action == "R" else gb)
                output["costs"].append(
                    {
                        "mechanic": mechanic,
                        "delay_ms": entry["delay_ms"],
                        "horizon": horizon,
                        "calibration_choice": chosen,
                        "action": action,
                        "K": k,
                        "policy_cost": cost,
                        "excess_vs_R": cost - horizon * r,
                        "excess_vs_G": cost - horizon * g,
                        "excess_vs_best": cost - horizon * min(r, g),
                        "excess_vs_best_interval": interval(
                            samples - horizon * np.minimum(rb, gb)
                        ),
                        "excess_vs_R_interval": (
                            [k, k]
                            if action == "R"
                            else interval(samples - horizon * rb)
                        ),
                        "excess_vs_G_interval": (
                            [k, k]
                            if action == "G"
                            else interval(samples - horizon * gb)
                        ),
                    }
                )
        for delay in DELAYS:
            block = [r for r in subset if r["delay_ms"] == delay]
            output["delay_diagnostics"].append(
                {
                    "mechanic": mechanic,
                    "delay_ms": delay,
                    "mean_actual_ms": 1000
                    * sum((r["measured_delay_seconds"] for r in block))
                    / len(block),
                    "max_actual_ms": 1000
                    * max((r["measured_delay_seconds"] for r in block)),
                }
            )
    (DEST / "results.json").write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("historical", "calibration", "analyze"))
    action = parser.parse_args().action
    analyze() if action == "analyze" else predict(action)
