"""A pre-outcome protocol amendment after the semantic rule audit."""

import json
import subprocess
import sys
import time
from run_pilot import ROOT, UPSTREAM
from prepare_training_b import pattern_rules

folder = ROOT / "extension"
assert not (folder / "smoke").exists(), "Amend before any C generation"
plan_file = folder / "plan.json"
plan = json.loads(plan_file.read_text())
(folder / "plan_before_rule_audit.json").write_text(
    json.dumps(plan, indent=2), encoding="utf-8"
)
begin = time.perf_counter()
subprocess.run(
    [
        sys.executable,
        "tile2scheme.py",
        "--outfile",
        str(folder / "driller_c.scheme"),
        "--tilefile",
        str(folder / "driller_c.tile"),
        "--pattern",
        "nbr-2",
    ],
    cwd=UPSTREAM,
    check=True,
    capture_output=True,
)
plan["external_pattern"] = "nbr-2"
plan["amendment"] = {
    "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "reason": "Before generating any C outputs, nbr-plus audit found C and B have identical semantic rule sets. Use nbr-2 for C to test a distinct configuration. Selection not based on prevalence/timing.",
    "interpretation": "Transfer to external geometry AND different pattern; not an isolated source effect. New seeds still require local calibration.",
    "additional_preparation_seconds": time.perf_counter() - begin,
    "external_rule_count": len(pattern_rules(folder / "driller_c.scheme")),
}
plan_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")
print(json.dumps(plan["amendment"], indent=2))
