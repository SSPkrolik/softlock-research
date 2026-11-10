"""Build both learned schemes once; preparation is outside per-attempt timing."""

import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT.parent / "sturgeon-pub"
COMMIT = "25bf8eef7006de04a3fcdd9e9cab18cb8b472129"


def main():
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=UPSTREAM, text=True
    ).strip()
    if commit != COMMIT:
        raise RuntimeError(f"Expected upstream commit {COMMIT}, got {commit}")
    records = []
    for mechanic in ("driller", "slide"):
        source = UPSTREAM / "levels" / "kenney" / f"{mechanic}.lvl"
        commands = [
            [
                sys.executable,
                "input2tile.py",
                "--outfile",
                str(ROOT / f"{mechanic}.tile"),
                "--textfile",
                str(source),
            ],
            [
                sys.executable,
                "tile2scheme.py",
                "--outfile",
                str(ROOT / f"{mechanic}.scheme"),
                "--tilefile",
                str(ROOT / f"{mechanic}.tile"),
                "--pattern",
                "nbr-plus",
            ],
        ]
        start = time.perf_counter()
        for command in commands:
            subprocess.run(command, cwd=UPSTREAM, check=True, capture_output=True)
        records.append(
            {
                "mechanic": mechanic,
                "setup_seconds": time.perf_counter() - start,
                "commands": commands,
            }
        )
    (ROOT / "setup.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print("Schemes ready; setup timing and source information recorded in setup.json.")


if __name__ == "__main__":
    main()
