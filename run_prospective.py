"""Prospective, fixed-budget stress test of previously estimated decision maps.

Injected sleeps are synthetic request delays, not measured deployment overhead.
Generation, validation, and all measured delays stay in the request cost.
"""

import argparse
import json
import platform
import random
import sys
import time
from pathlib import Path
from run_extension import Worker
from run_pilot import ROOT

DEST = ROOT / "prospective"


def run(phase):
    plan = json.loads((DEST / "protocol.json").read_text())
    if phase.startswith("session"):
        assert (DEST / "calibration_predictions.json").exists()
    folder = DEST / phase
    folder.mkdir(exist_ok=False)
    session = int(phase[-1]) if phase.startswith("session") else 0
    jobs = []
    for index, condition in enumerate(plan["conditions"]):
        counts = condition["calibration" if phase == "calibration" else "validation"]
        delays = [0] if phase in ("calibration", "smoke") else plan["delay_ms"]
        for strategy_index, strategy in enumerate(("baseline", "constrained")):
            count = 1 if phase == "smoke" else counts[strategy]
            for draw in range(count):
                seed = (
                    12000000
                    + session * 100000
                    + index * 20000
                    + strategy_index * 10000
                    + draw
                )
                if phase == "smoke":
                    seed += 900000
                for delay in delays:
                    jobs.append(
                        {
                            "mechanic": condition["mechanic"],
                            "strategy": strategy,
                            "seed": seed,
                            "session": session,
                            "delay_ms": delay,
                            "walls": 40,
                            "mode": "warm",
                            "scheme": str(ROOT / condition["scheme"]),
                        }
                    )
    random.Random(plan["order_seed"] + session).shuffle(jobs)
    worker = Worker(plan["timeout_seconds"])
    metadata = {
        "worker_startup_seconds": worker.startup_seconds,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "platform": platform.platform(),
        "jobs": len(jobs),
    }
    (folder / "environment.json").write_text(json.dumps(metadata, indent=2))
    try:
        with (folder / "attempts.jsonl").open("w", encoding="utf-8") as stream:
            for order, job in enumerate(jobs, 1):
                job["output"] = str(
                    folder
                    / f"{job['mechanic']}-{job['strategy']}-{job['seed']}-{job['delay_ms']}"
                )
                start = time.perf_counter()
                result = worker.run(job)
                base_seconds = result["elapsed_seconds"]
                delay_start = time.perf_counter()
                if job["delay_ms"]:
                    time.sleep(job["delay_ms"] / 1000)
                delay_seconds = time.perf_counter() - delay_start
                elapsed = time.perf_counter() - start
                result.update(job)
                result.update(
                    base_request_seconds=base_seconds,
                    measured_delay_seconds=delay_seconds,
                    elapsed_seconds=elapsed,
                    execution_order=order,
                )
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                if order % 50 == 0 or phase == "smoke":
                    print(f"{phase}: {order}/{len(jobs)}", flush=True)
                if result["status"] in ("invalid", "error", "timeout"):
                    raise RuntimeError(
                        "Failed attempt retained; no replacement or budget increase"
                    )
    finally:
        worker.close()
    metadata["completed_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (folder / "environment.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("smoke", "calibration", "session-1", "session-2")
    )
    run(parser.parse_args().phase)
