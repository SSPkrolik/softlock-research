"""Re-analyze existing levels with a terminal goal; never run the generator."""

import csv
import json
from pathlib import Path
from validate_level import build_graph, distances

ROOT = Path(__file__).resolve().parent


def reachable_sets(graph, start, goal):
    reverse = {cell: [] for cell in graph}
    for source, targets in graph.items():
        for target in targets:
            reverse[target].append(source)
    return (set(distances(graph, start)), set(distances(reverse, goal)))


def main():
    details = []
    for series in (
        "pilot",
        "density-control",
        "followup",
        "density-40",
        "density-60",
        "training-b-40",
        "training-b-60",
    ):
        for filename in sorted((ROOT / series).glob("*.lvl")):
            (mechanic, strategy, seed) = filename.stem.split("-")
            rows = [
                line
                for line in filename.read_text().splitlines()
                if line and (not line.startswith("META"))
            ]
            graph = build_graph(rows, mechanic)
            start = next((cell for cell in graph if rows[cell[0]][cell[1]] == "{"))
            goal = next((cell for cell in graph if rows[cell[0]][cell[1]] == "}"))
            (reachable, backward) = reachable_sets(graph, start, goal)
            terminal = build_graph(rows, mechanic, terminal_goal=True)
            (reachable_terminal, backward_terminal) = reachable_sets(
                terminal, start, goal
            )
            assert backward_terminal == backward
            assert reachable_terminal <= reachable
            (stuck, stuck_terminal) = (
                reachable - backward,
                reachable_terminal - backward_terminal,
            )
            assert stuck_terminal <= stuck
            details.append(
                {
                    "series": series,
                    "mechanic": mechanic,
                    "strategy": strategy,
                    "seed": int(seed),
                    "softlock_states": len(stuck),
                    "terminal_softlock_states": len(stuck_terminal),
                    "classification_changed": bool(stuck) != bool(stuck_terminal),
                }
            )
    with (ROOT / "semantics.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=details[0].keys())
        writer.writeheader()
        writer.writerows(details)
    groups = []
    for key in sorted(
        {(row["series"], row["mechanic"], row["strategy"]) for row in details}
    ):
        group = [
            row
            for row in details
            if (row["series"], row["mechanic"], row["strategy"]) == key
        ]
        groups.append(
            {
                "series": key[0],
                "mechanic": key[1],
                "strategy": key[2],
                "levels": len(group),
                "softlocked": sum((row["softlock_states"] > 0 for row in group)),
                "terminal_softlocked": sum(
                    (row["terminal_softlock_states"] > 0 for row in group)
                ),
                "changed_state_counts": sum(
                    (
                        row["softlock_states"] != row["terminal_softlock_states"]
                        for row in group
                    )
                ),
                "changed_classifications": sum(
                    (row["classification_changed"] for row in group)
                ),
            }
        )
    attempts = [
        json.loads(line)
        for line in (ROOT / "followup" / "attempts.jsonl").read_text().splitlines()
    ]
    baseline = [row for row in attempts if row["strategy"] == "baseline"]
    constrained = [row for row in attempts if row["strategy"] == "constrained"]
    attempt_cost = sum(
        (row["generation_seconds"] + row["validation_seconds"] for row in baseline)
    ) / len(baseline)
    accepted_cost = sum(
        (row["generation_seconds"] + row["validation_seconds"] for row in constrained)
    ) / sum((row["softlock_states"] == 0 for row in constrained))
    result = {
        "levels_reanalyzed": len(details),
        "groups": groups,
        "descriptive_cost_boundary": {
            "baseline_mean_attempt_seconds": attempt_cost,
            "constrained_seconds_per_accepted": accepted_cost,
            "acceptance_threshold_point_estimate": attempt_cost / accepted_cost,
            "softlock_threshold_point_estimate": 1 - attempt_cost / accepted_cost,
            "interpretation": "Algebraic plug-in estimate for this configuration, not an independently validated crossover.",
        },
    }
    (ROOT / "semantics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
