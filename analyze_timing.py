"""Recover coarse timing stages from existing Sturgeon logs; no new timings."""

import csv
import json
import re
from analyze_structure import SERIES
from run_pilot import ROOT

STAGE_PATTERN = re.compile("^\\.\\.\\.(.+?) took ([\\d.]+), ([\\d.]+)$", re.MULTILINE)
TOTAL_PATTERN = re.compile("^--TOTALTIME ([\\d.]+)$", re.MULTILINE)


def main():
    details = []
    for series in SERIES:
        source = ROOT / series / "attempts.jsonl"
        for line in source.read_text().splitlines():
            record = json.loads(line)
            stem = f"{record['mechanic']}-{record['strategy']}-{record['seed']}"
            log = (ROOT / series / f"{stem}.log").read_text()
            stages = {
                name: float(seconds)
                for (name, seconds, cumulative) in STAGE_PATTERN.findall(log)
            }
            total = TOTAL_PATTERN.search(log)
            assert (
                total and record["status"] == "solved"
            ), "Incomplete log needs separate treatment."
            expected = {
                "add tile rules",
                "add pattern rules",
                "add reachability rules",
                "solve",
                "create output",
            }
            assert expected <= stages.keys(), (stem, stages)
            construction = sum(
                (value for (name, value) in stages.items() if name.startswith("add "))
            )
            measured = record["generation_seconds"]
            internal = float(total.group(1))
            details.append(
                {
                    "series": series,
                    "mechanic": record["mechanic"],
                    "strategy": record["strategy"],
                    "seed": record["seed"],
                    "accepted": int(record["softlock_states"] == 0),
                    "generation_seconds": measured,
                    "validation_seconds": record["validation_seconds"],
                    "constraint_seconds_rounded": construction,
                    "reachability_constraint_seconds_rounded": stages[
                        "add reachability rules"
                    ],
                    "solve_seconds_rounded": stages["solve"],
                    "create_output_seconds_rounded": stages["create output"],
                    "internal_total_seconds_rounded": internal,
                    "outside_timer_seconds_approx": measured - internal,
                    "internal_unassigned_seconds_approx": internal
                    - sum(stages.values()),
                }
            )
    summary = []
    for key in sorted(
        {(row["series"], row["mechanic"], row["strategy"]) for row in details}
    ):
        group = [
            row
            for row in details
            if (row["series"], row["mechanic"], row["strategy"]) == key
        ]
        accepted = sum((row["accepted"] for row in group))
        row = {
            "series": key[0],
            "mechanic": key[1],
            "strategy": key[2],
            "attempts": len(group),
            "accepted": accepted,
        }
        for name in list(group[0])[5:]:
            total = sum((item[name] for item in group))
            row[name + "_per_attempt"] = total / len(group)
            row[name + "_per_accepted"] = total / accepted if accepted else None
        summary.append(row)
    with (ROOT / "timing_stages.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=details[0].keys())
        writer.writeheader()
        writer.writerows(details)
    (ROOT / "timing_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    sensitivity = []
    for series in (
        "density-40",
        "followup",
        "density-60",
        "training-b-40",
        "training-b-60",
    ):
        group = [row for row in summary if row["series"] == series]
        baseline = next((row for row in group if row["strategy"] == "baseline"))
        constrained = next((row for row in group if row["strategy"] == "constrained"))

        def accounted_cost(row):
            return (
                row["internal_total_seconds_rounded_per_accepted"]
                + row["validation_seconds_per_accepted"]
            )

        sensitivity.append(
            {
                "series": series,
                "baseline_internal_plus_validation_per_accepted": accounted_cost(
                    baseline
                ),
                "constrained_internal_plus_validation_per_accepted": accounted_cost(
                    constrained
                ),
                "internal_accounting_ratio": accounted_cost(baseline)
                / accounted_cost(constrained),
                "caveat": "Rounded log timer plus validation, not a warm-process benchmark.",
            }
        )
    (ROOT / "timing_accounting_sensitivity.json").write_text(
        json.dumps(sensitivity, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            [
                row
                for row in summary
                if row["series"] in ("density-40", "training-b-40")
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
