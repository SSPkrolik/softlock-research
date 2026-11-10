"""Small, fixed-budget pilot using the unmodified Sturgeon command-line tools.

Run with the experiment virtual environment. Each attempt has a fresh process.
Baseline attempts double as a rejection stream: no duplicate A/B experiment.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
from validate_level import analyze

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT.parent / "sturgeon-pub"


def command_for(mechanic, strategy, seed, output, walls=None, scheme_file=None):
    movement = "driller" if mechanic == "driller" else "tomb-full-50"
    connection = f"--src {{ --dst }} --move {movement}"
    connection += (
        " --method flat" if strategy == "baseline" else " --method fwdbwd --layers 101"
    )
    corners = ("tl", "br") if mechanic == "driller" else ("br", "tl")
    command = [
        sys.executable,
        "scheme2output.py",
        "--outfile",
        str(output),
        "--schemefile",
        str(scheme_file or ROOT / f"{mechanic}.scheme"),
        "--size",
        "10",
        "10",
        "--pattern-hard",
        "--reach-junction",
        "{",
        corners[0],
        "3",
        "--reach-junction",
        "}",
        corners[1],
        "3",
        "--reach-connect",
        connection,
        "--randomize",
        str(seed),
        "--solver",
        "pysat-minicard",
        "--out-result-none",
        "--out-tlvl-none",
    ]
    if strategy == "constrained":
        command += ["--custom", "fwdbwd-nostuck", "hard"]
    if walls is not None:
        command += [
            "--custom",
            "text-count",
            "0",
            "0",
            "10",
            "10",
            "X",
            str(walls),
            str(walls),
            "hard",
        ]
    return command


def run_attempt(
    mechanic, strategy, seed, output, timeout, walls=None, scheme_file=None
):
    command = command_for(mechanic, strategy, seed, output, walls, scheme_file)
    record = {
        "mechanic": mechanic,
        "strategy": strategy,
        "seed": seed,
        "command": command,
    }
    start = time.perf_counter()
    try:
        process = subprocess.run(
            command, cwd=UPSTREAM, capture_output=True, text=True, timeout=timeout
        )
        record["generation_seconds"] = time.perf_counter() - start
        output.with_suffix(".log").write_text(
            process.stdout + process.stderr, encoding="utf-8"
        )
        record["return_code"] = process.returncode
        if "--SOLVED" not in process.stdout or not output.with_suffix(".lvl").exists():
            record["status"] = "unsat" if "--NOSOLUTION" in process.stdout else "error"
            return record
    except subprocess.TimeoutExpired as error:
        record["generation_seconds"] = time.perf_counter() - start
        record["status"] = "timeout"
        partial = error.stdout or b""
        output.with_suffix(".log").write_bytes(
            partial if isinstance(partial, bytes) else partial.encode()
        )
        return record
    rows = [
        line
        for line in output.with_suffix(".lvl").read_text().splitlines()
        if line and (not line.startswith("META"))
    ]
    start = time.perf_counter()
    result = analyze(rows, mechanic)
    record["validation_seconds"] = time.perf_counter() - start
    record.update(result)
    if walls is not None:
        assert sum((row.count("X") for row in rows)) == walls
    record["terminal_goal_softlocks"] = analyze(rows, mechanic, terminal_goal=True)[
        "softlock_states"
    ]
    record["level_content"] = "\n".join(rows)
    record["status"] = "solved" if result["solvable"] else "invalid"
    if strategy == "constrained" and result["softlock_states"]:
        record["status"] = "invalid"
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--name", default="pilot")
    parser.add_argument(
        "--mechanics",
        nargs="+",
        choices=["driller", "slide"],
        default=["driller", "slide"],
    )
    parser.add_argument("--walls", type=int)
    parser.add_argument("--seed-start", type=int, default=1000)
    parser.add_argument(
        "--constrained-count",
        type=int,
        help="Separate budget for the more expensive constrained strategy.",
    )
    parser.add_argument("--constrained-seed-offset", type=int, default=0)
    parser.add_argument(
        "--purpose", default="exploratory pilot, not a confirmatory sample"
    )
    args = parser.parse_args()
    destination = ROOT / args.name
    destination.mkdir(exist_ok=False)
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
        "count_per_cell": args.count,
        "timeout_seconds": args.timeout,
        "order_seed": 20261109,
        "layers": 101,
        "pattern": "nbr-plus",
        "goal_semantics": "traversable (upstream); terminal-goal sensitivity also recorded",
        "purpose": args.purpose,
        "mechanics": args.mechanics,
        "walls": args.walls,
        "seed_start": args.seed_start,
        "constrained_count": (
            args.constrained_count if args.constrained_count is not None else args.count
        ),
        "constrained_seed_offset": args.constrained_seed_offset,
    }
    (destination / "environment.json").write_text(
        json.dumps(environment, indent=2), encoding="utf-8"
    )
    jobs = []
    for mechanic in args.mechanics:
        for strategy in ("baseline", "constrained"):
            count = (
                args.count
                if strategy == "baseline"
                else environment["constrained_count"]
            )
            offset = 0 if strategy == "baseline" else args.constrained_seed_offset
            jobs.extend(
                (
                    (mechanic, strategy, args.seed_start + offset + index)
                    for index in range(count)
                )
            )
    random.Random(environment["order_seed"]).shuffle(jobs)
    with (destination / "attempts.jsonl").open("w", encoding="utf-8") as log:
        for index, (mechanic, strategy, seed) in enumerate(jobs, 1):
            output = destination / f"{mechanic}-{strategy}-{seed}"
            record = run_attempt(
                mechanic, strategy, seed, output, args.timeout, args.walls
            )
            log.write(json.dumps(record) + "\n")
            log.flush()
            print(
                f"{index}/{len(jobs)} {mechanic} {strategy}: {record['status']}, {record['generation_seconds']:.3f}s, softlocks={record.get('softlock_states', '?')}",
                flush=True,
            )
            if record["status"] in ("invalid", "error"):
                raise RuntimeError(f"Stopped on validation/runtime failure: {output}")


if __name__ == "__main__":
    main()
