"""Validate saved movement graphs directly, without file digests."""

from excel_io import read_xls
from pathlib import Path
from validate_level import analyze

ROOT = Path(__file__).resolve().parent


def main():
    count = 0
    for path in ROOT.rglob("attempts.xls"):
        if "results" in path.parts:
            continue
        for row in read_xls(path):
            result = analyze(row["level_content"].splitlines(), row["mechanic"])
            assert result["solvable"]
            assert result["softlock_states"] == row["softlock_states"]
            if row["strategy"] == "constrained":
                assert result["softlock_states"] == 0
            count += 1
    assert count == 5550
    print("Validated all 5,550 recorded levels against the movement model.")


if __name__ == "__main__":
    main()
