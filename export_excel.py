"""Convert fresh experiment records to XLS, verifying each file before removal."""
import json
from pathlib import Path
from excel_io import write_xls,read_xls

def main():
    root=Path(__file__).resolve().parent
    for path in list(root.rglob('*.json'))+list(root.rglob('*.jsonl')):
        records=path.suffix=='.jsonl'
        value=[json.loads(l) for l in path.read_text().splitlines()] if records else json.loads(path.read_text())
        target=path.with_suffix('.xls')
        write_xls(target,value,records)
        assert read_xls(target)==value
        path.unlink()
        print(target.relative_to(root))

if __name__=='__main__':
    main()
