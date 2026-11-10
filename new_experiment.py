"""Create an empty experiment copy; never overwrite the supplied measurements."""

import argparse
from pathlib import Path
import shutil
import json
from excel_io import read_xls

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    target = parser.parse_args().destination.resolve()
    target.mkdir(parents=True, exist_ok=False)
    for source in ROOT.glob("*.py"):
        if source.name not in ("reproduce.py", "verify_data.py", "new_experiment.py"):
            shutil.copy2(source, target / source.name)
    for name in (
        "requirements.txt",
        "training_b.lvl",
        "density_plan.json",
        "followup_plan.json",
        "training_b_plan.json",
        "replication/protocol.json",
        "prospective/protocol.json",
    ):
        source = ROOT / name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == '.json':
            value=read_xls(source.with_suffix('.xls'))
            destination.write_text(json.dumps(value,indent=2),encoding='utf-8')
        else:
            shutil.copy2(source, destination)
    print("Created empty experiment:", target)
    print("Clone pinned sturgeon-pub beside it and follow README.md.")


if __name__ == "__main__":
    main()
