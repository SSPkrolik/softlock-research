"""Exact graph checks for static driller and slide levels (no death states)."""

from collections import deque


def build_graph(rows, mechanic, terminal_goal=False):
    """Slide stops at a wall; leaving the board is not an available move.

    By default the goal remains traversable, matching upstream Sturgeon.
    terminal_goal provides a separate sensitivity check for end-on-goal games.
    """
    (height, width) = (len(rows), len(rows[0]))
    assert all((len(row) == width for row in rows))
    assert set("".join(rows)) <= set("X-{}")
    open_cells = {
        (r, c) for r in range(height) for c in range(width) if rows[r][c] != "X"
    }
    graph = {cell: [] for cell in sorted(open_cells)}
    directions = [(1, 0), (0, -1), (0, 1)]
    if mechanic == "slide":
        directions.append((-1, 0))
    elif mechanic != "driller":
        raise ValueError(mechanic)
    for row, col in graph:
        if terminal_goal and rows[row][col] == "}":
            continue
        for dr, dc in directions:
            destination = (row + dr, col + dc)
            if destination not in open_cells:
                continue
            if mechanic == "slide":
                while (destination[0] + dr, destination[1] + dc) in open_cells:
                    destination = (destination[0] + dr, destination[1] + dc)
                (stop_row, stop_col) = (destination[0] + dr, destination[1] + dc)
                if not (0 <= stop_row < height and 0 <= stop_col < width):
                    continue
            graph[row, col].append(destination)
    return graph


def distances(graph, start):
    distance = {start: 0}
    pending = deque([start])
    while pending:
        current = pending.popleft()
        for neighbor in graph[current]:
            if neighbor not in distance:
                distance[neighbor] = distance[current] + 1
                pending.append(neighbor)
    return distance


def analyze(rows, mechanic, terminal_goal=False):
    graph = build_graph(rows, mechanic, terminal_goal)
    starts = [cell for cell in graph if rows[cell[0]][cell[1]] == "{"]
    goals = [cell for cell in graph if rows[cell[0]][cell[1]] == "}"]
    assert len(starts) == len(goals) == 1
    (start, goal) = (starts[0], goals[0])
    reverse = {cell: [] for cell in graph}
    for source, targets in graph.items():
        for target in targets:
            reverse[target].append(source)
    forward = distances(graph, start)
    backward = distances(reverse, goal)
    softlocks = set(forward) - set(backward)
    return {
        "solvable": goal in forward,
        "reachable_states": len(forward),
        "softlock_states": len(softlocks),
        "softlock_fraction": len(softlocks) / len(forward),
        "shortest_path": forward.get(goal),
        "wall_fraction": sum((row.count("X") for row in rows))
        / (len(rows) * len(rows[0])),
    }
