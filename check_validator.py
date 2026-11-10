"""Exhaustive small-board cross-check against upstream movement templates."""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sturgeon-pub"))
import util_common
import util_reach
from validate_level import analyze, build_graph, distances

checked = 0
for mechanic, movement in [("driller", "driller"), ("slide", "tomb-full-50")]:
    info = util_reach.get_move_info(movement, False, False, False)
    for interior in itertools.product("X-", repeat=7):
        cells = ["{"] + list(interior) + ["}"]
        rows = ["".join(cells[index : index + 3]) for index in range(0, 9, 3)]
        graph = build_graph(rows, mechanic)
        locations = {(r, c) for r in range(3) for c in range(3)}
        closed = locations - set(graph)
        for source, destinations in graph.items():
            edges = util_common.get_edge_keys_from(
                source, 3, 3, info, locations, set(graph), closed, set()
            )
            expected = {(edge[2], edge[3]) for edge in edges}
            assert set(destinations) == expected, (mechanic, rows, source)
        reachable = distances(graph, (0, 0))
        stuck = sum(((2, 2) not in distances(graph, state) for state in reachable))
        assert analyze(rows, mechanic)["softlock_states"] == stuck
        checked += 1
print(f"PASS: {checked} exhaustive board/mechanic cases; edges and softlocks agree.")
generated = 0
folder = sys.argv[1] if len(sys.argv) > 1 else "pilot"
for filename in sorted((Path(__file__).resolve().parent / folder).glob("*.lvl")):
    mechanic = filename.name.split("-")[0]
    rows = [
        line
        for line in filename.read_text().splitlines()
        if line and (not line.startswith("META"))
    ]
    graph = build_graph(rows, mechanic)
    locations = {(r, c) for r in range(len(rows)) for c in range(len(rows[0]))}
    movement = "driller" if mechanic == "driller" else "tomb-full-50"
    info = util_reach.get_move_info(movement, False, False, False)
    for source, destinations in graph.items():
        edges = util_common.get_edge_keys_from(
            source,
            len(rows),
            len(rows[0]),
            info,
            locations,
            set(graph),
            locations - set(graph),
            set(),
        )
        assert set(destinations) == {(edge[2], edge[3]) for edge in edges}, filename
    generated += 1
print(f"PASS: all movement edges on {generated} full-size generated levels agree.")
