"""Summarize a fixed-attempt exploratory pilot without discarding failed runs."""

import csv
import json
import math
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent


def wilson(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = (
        z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    )
    return [max(0, center - half), min(1, center + half)]


def main():
    folder = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "pilot")
    records = [
        json.loads(line)
        for line in (folder / "attempts.jsonl").read_text().splitlines()
    ]
    summary = []
    for mechanic in ("driller", "slide"):
        for strategy in ("baseline", "constrained"):
            group = [
                row
                for row in records
                if row["mechanic"] == mechanic and row["strategy"] == strategy
            ]
            if not group:
                continue
            solved = [row for row in group if row["status"] == "solved"]
            accepted = [row for row in solved if row["softlock_states"] == 0]
            stuck = len(solved) - len(accepted)
            seconds = sum(
                (
                    row["generation_seconds"] + row.get("validation_seconds", 0)
                    for row in group
                )
            )
            summary.append(
                {
                    "mechanic": mechanic,
                    "strategy": strategy,
                    "attempts": len(group),
                    "solved": len(solved),
                    "softlocked": stuck,
                    "accepted": len(accepted),
                    "prevalence_wilson_95": wilson(stuck, len(solved)),
                    "total_seconds": seconds,
                    "seconds_per_accepted": (
                        seconds / len(accepted) if accepted else None
                    ),
                    "median_generation_seconds": median(
                        (row["generation_seconds"] for row in group)
                    ),
                    "median_validation_ms": (
                        median((row["validation_seconds"] for row in solved)) * 1000
                        if solved
                        else None
                    ),
                    "unique_solved": len({row["level_content"] for row in solved}),
                    "median_wall_fraction": (
                        median((row["wall_fraction"] for row in solved))
                        if solved
                        else None
                    ),
                    "median_shortest_path": (
                        median((row["shortest_path"] for row in solved))
                        if solved
                        else None
                    ),
                    "goal_semantics_disagreements": sum(
                        (
                            row["softlock_states"] != row["terminal_goal_softlocks"]
                            for row in solved
                        )
                    ),
                    "timeouts": sum((row["status"] == "timeout" for row in group)),
                }
            )
    (folder / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    columns = [key for key in records[0] if key != "command"]
    for row in records:
        columns += [key for key in row if key != "command" and key not in columns]
    with (folder / "attempts.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
