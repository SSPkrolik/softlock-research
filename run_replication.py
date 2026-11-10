"""Fixed-budget session replication and a sliding-movement transfer check."""

import argparse
import json
from pathlib import Path
import platform
import random
import sys
import time
from run_extension import Worker
from run_pilot import ROOT, run_attempt

DEST = ROOT / "replication"


def run_session(session, smoke=False):
    protocol = DEST / "protocol.json"
    plan = json.loads(protocol.read_text())
    folder = DEST / ("smoke" if smoke else f"session-{session}")
    folder.mkdir(exist_ok=False)
    jobs = []
    for condition in plan["conditions"]:
        for strategy in ("baseline", "constrained"):
            count = 1 if smoke else condition[strategy]
            for index in range(count):
                seed = 9000000 if smoke else 2000000 + session * 100000
                seed += (
                    condition["seed_offset"]
                    + (10000 if strategy == "constrained" else 0)
                    + index
                )
                for mode in ("cold", "warm"):
                    jobs.append(
                        {
                            "mechanic": condition["mechanic"],
                            "strategy": strategy,
                            "seed": seed,
                            "mode": mode,
                            "walls": 40,
                            "scheme": str(ROOT / condition["scheme"]),
                            "session": session,
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
                output = (
                    folder
                    / f"{job['mechanic']}-{job['strategy']}-{job['mode']}-{job['seed']}"
                )
                job["output"] = str(output)
                start = time.perf_counter()
                if job["mode"] == "warm":
                    result = worker.run(job)
                else:
                    result = run_attempt(
                        job["mechanic"],
                        job["strategy"],
                        job["seed"],
                        output,
                        plan["timeout_seconds"],
                        40,
                        Path(job["scheme"]),
                    )
                    result["elapsed_seconds"] = time.perf_counter() - start
                result.update(job)
                result["execution_order"] = order
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                if order % 50 == 0 or smoke or result["status"] != "solved":
                    print(
                        f"session {session}: {order}/{len(jobs)} {job['mechanic']} {job['mode']} {job['strategy']} {result['status']}",
                        flush=True,
                    )
                if result["status"] in ("invalid", "error", "timeout"):
                    raise RuntimeError(
                        "Stopped on failure; original record retained, no replacement draw"
                    )
    finally:
        worker.close()
    metadata["completed_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (folder / "environment.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("session", type=int, choices=(0, 1, 2, 3))
    args = parser.parse_args()
    run_session(args.session, smoke=args.session == 0)
