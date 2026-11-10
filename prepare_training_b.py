"""Prepare one deliberately bounded training example and audit learned rules."""

import json
import pickle
import subprocess
import sys
from run_pilot import ROOT, UPSTREAM
from validate_level import analyze

sys.path.insert(0, str(UPSTREAM))


def pattern_rules(filename):
    with filename.open("rb") as source:
        scheme = pickle.load(source)
    names = {**scheme.tileset.tile_to_text, -1: "VOID"}
    rules = set()
    for game, by_pattern in scheme.pattern_info.game_to_patterns.items():
        for input_locations, by_tiles in by_pattern.items():
            for input_tiles, by_output in by_tiles.items():
                for output_locations, outputs in by_output.items():
                    for output_tiles in outputs:
                        rules.add(
                            (
                                game,
                                tuple(input_locations),
                                tuple((names[t] for t in input_tiles)),
                                tuple(output_locations),
                                tuple((names[t] for t in output_tiles)),
                            )
                        )
    return rules


def main():
    example = ROOT / "training_b.lvl"
    rows = example.read_text().splitlines()
    metrics = analyze(rows, "driller")
    assert metrics[
        "solvable"
    ], "Training example must be solvable under driller movement."
    for command in [
        [
            "input2tile.py",
            "--outfile",
            str(ROOT / "driller_b.tile"),
            "--textfile",
            str(example),
        ],
        [
            "tile2scheme.py",
            "--outfile",
            str(ROOT / "driller_b.scheme"),
            "--tilefile",
            str(ROOT / "driller_b.tile"),
            "--pattern",
            "nbr-plus",
        ],
    ]:
        subprocess.run(
            [sys.executable] + command, cwd=UPSTREAM, capture_output=True, check=True
        )
    original = pattern_rules(ROOT / "driller.scheme")
    alternate = pattern_rules(ROOT / "driller_b.scheme")
    audit = {
        "provenance": "Researcher-authored static example, fixed before new generation; not a second external benchmark.",
        "design": "Bounded corridors; same driller mechanics; intended sensitivity test of learned local rules.",
        "metrics": metrics,
        "original_rule_count": len(original),
        "alternate_rule_count": len(alternate),
        "removed_rules": sorted(original - alternate),
        "added_rules": sorted(alternate - original),
        "representation_caveat": "Numeric tile IDs are assigned in encounter order and can differ between examples. Rule-set comparison is semantic; solver sampling distribution need not be invariant to representation.",
    }
    assert (
        original != alternate
    ), "A different layout alone is not a distinct learned model."
    (ROOT / "training_b_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
