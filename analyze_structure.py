"""Describe irreversible loss of goal reachability on saved level graphs."""

import csv
import json
from statistics import median
import networkx as nx
from run_pilot import ROOT
from validate_level import build_graph, distances

SERIES = (
    "pilot",
    "density-control",
    "followup",
    "density-40",
    "density-60",
    "training-b-40",
    "training-b-60",
)


def structural_metrics(rows, mechanic, terminal_goal=False):
    graph = build_graph(rows, mechanic, terminal_goal)
    start = next((cell for cell in graph if rows[cell[0]][cell[1]] == "{"))
    goal = next((cell for cell in graph if rows[cell[0]][cell[1]] == "}"))
    reverse = {cell: [] for cell in graph}
    for source, targets in graph.items():
        for target in targets:
            reverse[target].append(source)
    forward = distances(graph, start)
    can_finish = set(distances(reverse, goal))
    safe = set(forward) & can_finish
    trapped = set(forward) - can_finish
    entries = [
        (source, target)
        for source in sorted(safe)
        for target in graph[source]
        if target in trapped
    ]
    assert all((target in trapped for source in trapped for target in graph[source]))
    assert bool(trapped) == bool(
        entries
    ), "For a solvable level, a trap needs an entry."
    trap_graph = nx.DiGraph()
    trap_graph.add_nodes_from(trapped)
    trap_graph.add_edges_from(
        ((source, target) for source in trapped for target in graph[source])
    )
    components = list(nx.strongly_connected_components(trap_graph))
    terminal_components = [
        component
        for component in components
        if all(
            (target in component for source in component for target in graph[source])
        )
    ]
    safe_actions = sum((len(graph[cell]) for cell in safe))
    bottom = len(rows) - 1
    return {
        "reachable_states": len(forward),
        "softlock_states": len(trapped),
        "softlock_fraction": len(trapped) / len(forward),
        "entry_edges": len(entries),
        "dangerous_decision_states": len({edge[0] for edge in entries}),
        "entry_edge_fraction": len(entries) / safe_actions if safe_actions else 0,
        "first_softlock_move": min(
            (forward[source] + 1 for (source, target) in entries), default=None
        ),
        "terminal_trap_components": len(terminal_components),
        "bottom_softlock_states": sum((row == bottom for (row, col) in trapped)),
        "bottom_entry_edges": sum(
            (target[0] == bottom for (source, target) in entries)
        ),
        "terminal_components_touching_bottom": sum(
            (
                any((row == bottom for (row, col) in part))
                for part in terminal_components
            )
        ),
    }


def main():
    example = ["XXXXX", "X{--X", "XX-}X", "XX-XX", "XXXXX"]
    test = structural_metrics(example, "driller")
    assert (
        test["softlock_states"],
        test["entry_edges"],
        test["first_softlock_move"],
    ) == (1, 1, 3)
    records = []
    for series in SERIES:
        for filename in sorted((ROOT / series).glob("*.lvl")):
            (mechanic, strategy, seed) = filename.stem.split("-")
            rows = [
                line
                for line in filename.read_text().splitlines()
                if line and (not line.startswith("META"))
            ]
            metrics = structural_metrics(rows, mechanic)
            terminal = structural_metrics(rows, mechanic, terminal_goal=True)
            records.append(
                {
                    "series": series,
                    "mechanic": mechanic,
                    "strategy": strategy,
                    "seed": int(seed),
                    **metrics,
                    "terminal_goal_entry_edges": terminal["entry_edges"],
                }
            )
    summary = []
    for key in sorted(
        {(row["series"], row["mechanic"], row["strategy"]) for row in records}
    ):
        group = [
            row
            for row in records
            if (row["series"], row["mechanic"], row["strategy"]) == key
        ]
        stuck = [row for row in group if row["softlock_states"]]
        summary.append(
            {
                "series": key[0],
                "mechanic": key[1],
                "strategy": key[2],
                "levels": len(group),
                "softlocked_levels": len(stuck),
                "median_entry_edges_all_levels": median(
                    (row["entry_edges"] for row in group)
                ),
                "median_softlock_fraction_all_levels": median(
                    (row["softlock_fraction"] for row in group)
                ),
                "median_first_softlock_move_conditional": (
                    median((row["first_softlock_move"] for row in stuck))
                    if stuck
                    else None
                ),
                "levels_with_bottom_softlocks": sum(
                    (row["bottom_softlock_states"] > 0 for row in group)
                ),
                "levels_with_bottom_entry": sum(
                    (row["bottom_entry_edges"] > 0 for row in group)
                ),
                "median_terminal_trap_components_all_levels": median(
                    (row["terminal_trap_components"] for row in group)
                ),
            }
        )
    with (ROOT / "structure.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    (ROOT / "structure_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(
        json.dumps([row for row in summary if row["strategy"] == "baseline"], indent=2)
    )


if __name__ == "__main__":
    main()
