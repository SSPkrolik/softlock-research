"""A persistent Sturgeon worker; no generation state is shared across attempts."""

import contextlib
import gc
import io
import json
from pathlib import Path
import sys
import time
from run_pilot import UPSTREAM, command_for
from validate_level import analyze

sys.path.insert(0, str(UPSTREAM))
import scheme2output
import util_solvers


def attempt(job):
    output = Path(job["output"])
    mechanic = job.get("mechanic", "driller")
    command = command_for(
        mechanic,
        job["strategy"],
        job["seed"],
        output,
        job["walls"],
        Path(job["scheme"]),
    )
    log = io.StringIO()
    record = {
        "mechanic": mechanic,
        "strategy": job["strategy"],
        "seed": job["seed"],
        "command": command,
        "status": "unsat",
    }
    begin = time.perf_counter()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        cfg = scheme2output.scheme2output_argv2cfg(command[2:])
        result = scheme2output.scheme2output(cfg)
        if result is not None:
            scheme2output.scheme2output_save_result(cfg, result)
    record["generation_seconds"] = time.perf_counter() - begin
    output.with_suffix(".log").write_text(log.getvalue(), encoding="utf-8")
    if result is not None:
        rows = [
            line
            for line in output.with_suffix(".lvl").read_text().splitlines()
            if line and (not line.startswith("META"))
        ]
        begin = time.perf_counter()
        metrics = analyze(rows, mechanic)
        record["validation_seconds"] = time.perf_counter() - begin
        record.update(metrics)
        assert sum((row.count("X") for row in rows)) == job["walls"]
        record["terminal_goal_softlocks"] = analyze(rows, mechanic, terminal_goal=True)[
            "softlock_states"
        ]
        record["level_content"] = "\n".join(rows)
        record["status"] = "solved" if metrics["solvable"] else "invalid"
        if job["strategy"] == "constrained" and metrics["softlock_states"]:
            record["status"] = "invalid"
    del cfg, result
    gc.collect()
    return record


def main():
    assert util_solvers.try_import_pysat()
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        job = json.loads(line)
        if job is None:
            break
        try:
            record = attempt(job)
        except Exception:
            import traceback

            record = {"status": "error", "traceback": traceback.format_exc()}
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
