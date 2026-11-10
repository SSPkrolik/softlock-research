"""Freeze an external geometry adaptation and a small, prospective protocol."""

import json
import shutil
import subprocess
import sys
import time
from run_pilot import ROOT, UPSTREAM
from prepare_training_b import pattern_rules
from validate_level import analyze


def main():
    destination = ROOT / "extension"
    destination.mkdir(exist_ok=False)
    source = UPSTREAM / "levels/vglc/tloz1-1-generic.lvl"
    original = source.read_text().splitlines()
    room = [row[16:32] for row in original[:11]]
    assert all((len(row) == 16 and " " not in row for row in room))
    mapping = {"W": "X", "B": "X", "S": "X", "P": "X", "D": "-", "-": "-"}
    cells = [list("".join((mapping[tile] for tile in row))) for row in room]
    opened = [
        (r, c)
        for (r, row) in enumerate(cells)
        for (c, tile) in enumerate(row)
        if tile == "-"
    ]
    (start, goal) = (opened[0], opened[-1])
    cells[start[0]][start[1]] = "{"
    cells[goal[0]][goal[1]] = "}"
    example = destination / "training_c.lvl"
    example.write_text(
        "\n".join(("".join(row) for row in cells)) + "\n", encoding="utf-8"
    )
    metrics = analyze(example.read_text().splitlines(), "driller")
    assert metrics["solvable"]
    shutil.copyfile(source, destination / "vglc_source.lvl")
    shutil.copyfile(
        UPSTREAM / "levels/vglc/src/License.md", destination / "VGLC_LICENSE.md"
    )
    begin = time.perf_counter()
    for args in [
        [
            "input2tile.py",
            "--outfile",
            str(destination / "driller_c.tile"),
            "--textfile",
            str(example),
        ],
        [
            "tile2scheme.py",
            "--outfile",
            str(destination / "driller_c.scheme"),
            "--tilefile",
            str(destination / "driller_c.tile"),
            "--pattern",
            "nbr-plus",
        ],
    ]:
        subprocess.run(
            [sys.executable] + args, cwd=UPSTREAM, check=True, capture_output=True
        )
    preparation_seconds = time.perf_counter() - begin
    a = pattern_rules(ROOT / "driller.scheme")
    b = pattern_rules(ROOT / "driller_b.scheme")
    c = pattern_rules(destination / "driller_c.scheme")
    audit = {
        "source": "The Legend of Zelda dungeon 1, VGLC geometry distributed with Sturgeon",
        "repository": "https://github.com/TheVGLC/TheVGLC",
        "frozen_source": str(source.relative_to(UPSTREAM)),
        "upstream_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=UPSTREAM, text=True
        ).strip(),
        "crop_zero_based_half_open": {"rows": [0, 11], "columns": [16, 32]},
        "mapping": mapping,
        "start": start,
        "goal": goal,
        "metrics": metrics,
        "preparation_seconds": preparation_seconds,
        "caveat": "External geometry, researcher-defined binary adaptation; NOT native Zelda mechanics or an independent generator. Start/goal assigned to first/last open cell in row-major order. No outcomes used for selection.",
        "rule_counts": {"A": len(a), "B": len(b), "C": len(c)},
        "C_minus_A": sorted(c - a),
        "A_minus_C": sorted(a - c),
        "C_minus_B": sorted(c - b),
        "B_minus_C": sorted(b - c),
    }
    (destination / "source_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    plan = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "Two fixed-budget series; no expansion based on statistical significance.",
        "timing": {
            "examples": ["A", "B"],
            "walls": [40],
            "baseline": 100,
            "constrained": 20,
            "modes": ["cold", "warm"],
            "seed_base": 210000,
            "order_seed": 91001,
        },
        "transfer": {
            "examples": ["C"],
            "walls": [40, 60],
            "calibration": {"baseline": 60, "constrained": 20},
            "evaluation": {"baseline": 100, "constrained": 20},
            "seed_base": 310000,
            "order_seed": 91002,
        },
        "timeout_seconds": 15,
        "bootstrap_repetitions": 10000,
        "bootstrap_seed": 91003,
        "prediction": "Freeze per-cell recommendation from calibration cost-ratio nominal 95% bootstrap interval. Choose constrained if lower>1; rejection if upper<1; otherwise abstain. No override after evaluation.",
        "calibration_cost": "Charge all calibration attempts, worker startup and source preparation; no credit for usable calibration levels. Report break-even production horizon, not unqualified savings.",
        "batch_horizon": 100,
        "warm": "Import modules once. Each attempt reloads scheme, rebuilds constraints, creates fresh solver, saves output, runs exact validator. No clause/config/scheme cache. Parent measures request round-trip; includes audit/I/O and worker garbage collection. Worker startup recorded separately.",
        "cold": "Existing unmodified CLI, fresh process each attempt; parent round-trip includes log writing, validation and supplementary goal check. Paired seeds only for cold/warm within each strategy; strategy seeds disjoint.",
        "statistics": "Nominal pointwise exploratory intervals, no multiplicity adjustment. No probability-sampling claim. Holdout validates local calibration on new seeds, not zero-shot cross-game generalization.",
        "goal_semantics": "Traversable goal primary; terminal-goal diagnostic retained.",
    }
    (destination / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps({"audit": audit, "plan": plan}, indent=2))


if __name__ == "__main__":
    main()
