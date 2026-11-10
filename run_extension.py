"""Run paired process timing, then calibrated external-geometry holdout tests."""

import argparse
import json
from pathlib import Path
import platform
import queue
import random
import subprocess
import sys
import threading
import time
from run_pilot import ROOT, UPSTREAM, run_attempt

EXT = ROOT / "extension"


class Worker:

    def __init__(self, timeout):
        self.timeout = timeout
        self.replies = queue.Queue()
        start = time.perf_counter()
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "warm_worker.py")],
            cwd=UPSTREAM,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.reader = threading.Thread(target=self.read_lines, daemon=True)
        self.reader.start()
        assert self.receive().get("ready")
        self.startup_seconds = time.perf_counter() - start

    def read_lines(self):
        for line in self.process.stdout:
            self.replies.put(line)
        self.replies.put(None)

    def receive(self):
        try:
            line = self.replies.get(timeout=self.timeout)
        except queue.Empty:
            self.process.kill()
            self.process.wait()
            raise TimeoutError("Persistent worker exceeded the fixed attempt timeout")
        if line is None:
            raise RuntimeError("Persistent worker exited unexpectedly")
        return json.loads(line)

    def run(self, job):
        start = time.perf_counter()
        self.process.stdin.write(json.dumps(job) + "\n")
        self.process.stdin.flush()
        try:
            record = self.receive()
        except TimeoutError:
            record = {"status": "timeout"}
        record["elapsed_seconds"] = time.perf_counter() - start
        return record

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write("null\n")
            self.process.stdin.flush()
            self.process.wait(timeout=10)
        self.process.stdin.close()
        self.process.stdout.close()


def scheme_for(example):
    return {
        "A": ROOT / "driller.scheme",
        "B": ROOT / "driller_b.scheme",
        "C": EXT / "driller_c.scheme",
    }[example]


def jobs_for(series, plan):
    jobs = []
    section = plan["timing" if series == "timing" else "transfer"]
    if series == "timing":
        (counts, modes, phase_offset) = (section, section["modes"], 0)
    else:
        (counts, modes) = (section[series], ["warm"])
        phase_offset = 0 if series == "calibration" else 50000
    for ex_index, example in enumerate(section["examples"]):
        for walls in section["walls"]:
            for st_index, strategy in enumerate(("baseline", "constrained")):
                for index in range(counts[strategy]):
                    seed = (
                        section["seed_base"]
                        + phase_offset
                        + ex_index * 10000
                        + walls * 100
                        + st_index * 1000
                        + index
                    )
                    for mode in modes:
                        jobs.append(
                            {
                                "example": example,
                                "walls": walls,
                                "strategy": strategy,
                                "seed": seed,
                                "mode": mode,
                                "phase": series,
                                "scheme": str(scheme_for(example)),
                            }
                        )
    random.Random(section["order_seed"] + phase_offset).shuffle(jobs)
    return jobs


def run_series(series):
    plan = json.loads((EXT / "plan.json").read_text())
    if series == "evaluation":
        prediction = EXT / "predictions.json"
        assert prediction.exists(), "Freeze predictions before evaluating new seeds"
    folder = EXT / series
    folder.mkdir(exist_ok=False)
    jobs = jobs_for(series, plan)
    worker = Worker(plan["timeout_seconds"])
    metadata = {
        "worker_startup_seconds": worker.startup_seconds,
        "python": sys.version,
        "platform": platform.platform(),
        "jobs": len(jobs),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (folder / "environment.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    try:
        with (folder / "attempts.jsonl").open("w", encoding="utf-8") as stream:
            for order, job in enumerate(jobs, 1):
                output = (
                    folder
                    / f"driller-{job['example']}-{job['walls']}-{job['strategy']}-{job['mode']}-{job['seed']}"
                )
                job["output"] = str(output)
                if job["mode"] == "warm":
                    result = worker.run(job)
                else:
                    start = time.perf_counter()
                    result = run_attempt(
                        "driller",
                        job["strategy"],
                        job["seed"],
                        output,
                        plan["timeout_seconds"],
                        job["walls"],
                        Path(job["scheme"]),
                    )
                    result["elapsed_seconds"] = time.perf_counter() - start
                result.update(job)
                result["execution_order"] = order
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                if order % 20 == 0 or result["status"] != "solved":
                    print(
                        f"{series} {order}/{len(jobs)} {job['example']} {job['walls']} {job['mode']} {job['strategy']}: {result['status']}",
                        flush=True,
                    )
                if result["status"] in ("invalid", "error", "timeout"):
                    raise RuntimeError(f"Stopped; failed attempt retained: {result}")
    finally:
        worker.close()
    metadata["completed_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (folder / "environment.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def smoke():
    folder = EXT / "smoke"
    folder.mkdir(exist_ok=False)
    worker = Worker(15)
    results = []
    try:
        for example in ("A", "B", "C"):
            for walls in (40, 60) if example == "C" else (40,):
                for strategy in ("baseline", "constrained"):
                    job = {
                        "example": example,
                        "walls": walls,
                        "strategy": strategy,
                        "seed": 990001,
                        "scheme": str(scheme_for(example)),
                    }
                    job["output"] = str(
                        folder / f"driller-{example}-{walls}-{strategy}-warm"
                    )
                    warm = worker.run(job)
                    cold = run_attempt(
                        "driller",
                        strategy,
                        job["seed"],
                        folder / f"driller-{example}-{walls}-{strategy}-cold",
                        15,
                        walls,
                        scheme_for(example),
                    )
                    assert warm["status"] == cold["status"] == "solved", (warm, cold)
                    assert warm["level_content"] == cold["level_content"], (warm, cold)
                    results.append({"job": job, "warm": warm, "cold": cold})
    finally:
        worker.close()
    (folder / "checks.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(
        f"PASS: {len(results)} paired API/CLI smoke cases produce identical valid levels"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "series", choices=["smoke", "timing", "calibration", "evaluation"]
    )
    args = parser.parse_args()
    if args.series == "smoke":
        smoke()
    else:
        run_series(args.series)
