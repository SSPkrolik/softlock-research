"""Recompute reported analyses in a temporary copy, preserving supplied data."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from excel_io import restore_inputs, write_xls

ROOT = Path(__file__).resolve().parent
COMMANDS = [
    ["analyze_followup.py"],
    ["analyze_density.py"],
    ["compare_training_examples.py"],
    ["analyze_structure.py"],
    ["analyze_semantics.py"],
    ["analyze_timing.py"],
    ["analyze_extension.py", "summarize"],
    ["analyze_replication.py"],
    ["analyze_decisions.py"],
    ["analyze_prospective.py", "analyze"],
]


def main():
    with tempfile.TemporaryDirectory(prefix="softlock-reanalysis-") as temporary:
        work = Path(temporary) / "experiment"
        shutil.copytree(
            ROOT,
            work,
            ignore=shutil.ignore_patterns("results", "__pycache__", ".git", "*.zip"),
        )
        restore_inputs(work)
        # Reconstruct only files needed by the original diagnostic analyses.
        for relative, text in json.loads(
            (work / "diagnostic_inputs.json").read_text()
        ).items():
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        before = {p.relative_to(work) for p in work.rglob("*") if p.is_file()}
        for command in COMMANDS:
            result = subprocess.run(
                [sys.executable] + command, cwd=work, capture_output=True, text=True
            )
            if result.returncode:
                raise RuntimeError(
                    f"{command[0]} failed:\n{result.stderr}\n{result.stdout}"
                )
            print("Completed:", command[0], flush=True)
        outputs = [
            p
            for p in work.rglob("*")
            if p.is_file()
            and p.relative_to(work) not in before
            and p.suffix == ".json"
        ]
        for source in outputs:
            target = ROOT / "results" / source.relative_to(work)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == '.json':
                write_xls(target.with_suffix('.xls'), json.loads(source.read_text()))
            else:
                import csv
                with source.open(newline='', encoding='utf-8') as stream:
                    rows=list(csv.DictReader(stream))
                write_xls(target.with_suffix('.xls'), rows, records=True)
        print(
            "Results written to results/. No generation or timing reruns were performed."
        )


if __name__ == "__main__":
    main()
