"""Interleave both new densities so timing is not confounded with their order."""

import json
import os
import platform
import random
import subprocess
import sys
from run_pilot import ROOT, UPSTREAM, run_attempt


def main():
    plan = json.loads((ROOT / "density_plan.json").read_text())
    folders = {walls: ROOT / f"density-{walls}" for walls in plan["wall_counts"]}
    for walls, folder in folders.items():
        folder.mkdir(exist_ok=False)
        environment = {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=UPSTREAM, text=True
            ).strip(),
            "packages": subprocess.check_output(
                [sys.executable, "-m", "pip", "freeze"], text=True
            ),
            "walls": walls,
            "layers": 101,
            "pattern": "nbr-plus",
            "plan": plan,
        }
        (folder / "environment.json").write_text(
            json.dumps(environment, indent=2), encoding="utf-8"
        )
    jobs = []
    for walls in folders:
        for strategy in ("baseline", "constrained"):
            (low, high) = plan["seed_ranges"][f"{walls}_{strategy}"]
            jobs.extend(((walls, strategy, seed) for seed in range(low, high + 1)))
    random.Random(plan["order_seed"]).shuffle(jobs)
    for index, (walls, strategy, seed) in enumerate(jobs, 1):
        output = folders[walls] / f"driller-{strategy}-{seed}"
        record = run_attempt(
            "driller", strategy, seed, output, plan["timeout_seconds"], walls
        )
        record["execution_order"] = index
        with (folders[walls] / "attempts.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")
        print(
            f"{index}/240 walls={walls} {strategy}: {record['status']}, {record['generation_seconds']:.3f}s, softlocks={record.get('softlock_states', '?')}",
            flush=True,
        )
        if record["status"] in ("invalid", "error"):
            raise RuntimeError(f"Stopped: {output}")


if __name__ == "__main__":
    main()
