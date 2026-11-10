"""Lossless XLS storage for measured rows and nested analysis settings."""
import math
from pathlib import Path
import xlrd
import xlwt

HEADER = xlwt.easyxf('font: bold on, colour white; pattern: pattern solid, fore_colour dark_blue; alignment: wrap on, vert centre')
NUMBER = xlwt.easyxf(num_format_str='0.000000000000000')
TEXT = xlwt.easyxf('alignment: vert top')

def kind(value):
    if value is None: return 'null'
    if isinstance(value, bool): return 'bool'
    if isinstance(value, int): return 'int'
    if isinstance(value, float): return 'float' if math.isfinite(value) else 'special'
    if isinstance(value, str): return 'str'
    if isinstance(value, dict): return 'dict'
    if isinstance(value, list): return 'list'
    raise TypeError(type(value))

def encode(value):
    t = kind(value)
    return '' if t in ('null','dict','list') else str(value) if t == 'special' else value

def decode(t, value):
    if t == 'null': return None
    if t == 'bool': return bool(value)
    if t == 'int': return int(value)
    if t in ('float','special'): return float(value)
    if t == 'dict': return {}
    if t == 'list': return []
    return str(value)

def sheet(book, name, headers):
    ws = book.add_sheet(name)
    ws.set_panes_frozen(True)
    ws.set_horz_split_pos(1)
    ws.row(0).height = 640
    for c, title in enumerate(headers):
        ws.write(0, c, title, HEADER)
        ws.col(c).width = min(50, max(18, len(title)+2))*256
    return ws

def write_xls(path, value, records=False):
    book = xlwt.Workbook()
    if records:
        headers = list(dict.fromkeys(k for row in value for k in row))
        data = sheet(book, 'Measurements', headers)
        types = sheet(book, 'Cell types', headers)
        for r, row in enumerate(value, 1):
            for c, key in enumerate(headers):
                t = kind(row[key]) if key in row else 'missing'
                types.write(r, c, t)
                if t != 'missing':
                    assert t not in ('dict','list')
                    data.write(r, c, encode(row[key]), NUMBER if t=='float' else TEXT)
    else:
        data = sheet(book, 'Values', ['Path', 'Type', 'Value'])
        data.col(0).width = 90*256
        data.col(2).width = 65*256
        nodes = []
        def visit(v, p):
            nodes.append((p,kind(v),encode(v)))
            children = v.items() if isinstance(v,dict) else enumerate(v) if isinstance(v,list) else []
            for k, child in children:
                part = str(k).replace('~','~0').replace('/','~1')
                visit(child, p+'/'+part)
        visit(value, '')
        assert len(nodes)<65536
        for r, row in enumerate(nodes,1):
            for c,v in enumerate(row):
                data.write(r,c,v,NUMBER if c==2 and row[1]=='float' else TEXT)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    book.save(str(path))

def read_xls(path):
    book = xlrd.open_workbook(str(path))
    if 'Measurements' in book.sheet_names():
        data, types = book.sheet_by_name('Measurements'), book.sheet_by_name('Cell types')
        headers = data.row_values(0)
        return [{key:decode(types.cell_value(r,c),data.cell_value(r,c))
                 for c,key in enumerate(headers) if types.cell_value(r,c)!='missing'}
                for r in range(1,data.nrows)]
    data = book.sheet_by_name('Values')
    nodes = {}
    for r in range(1,data.nrows):
        p,t,v = data.row_values(r)
        obj = decode(t,v)
        nodes[p]=obj
        if p:
            parent,key=p.rsplit('/',1)
            key=key.replace('~1','/').replace('~0','~')
            if isinstance(nodes[parent],list):
                assert int(key)==len(nodes[parent])
                nodes[parent].append(obj)
            else: nodes[parent][key]=obj
    return nodes['']

def restore_inputs(root):
    """Adapt XLS inputs only inside the temporary analysis working directory."""
    import json
    for path in Path(root).rglob('*.xls'):
        if 'results' in path.relative_to(root).parts: continue
        value=read_xls(path)
        records=path.stem=='attempts'
        target=path.with_suffix('.jsonl' if records else '.json')
        text=''.join(json.dumps(r)+'\n' for r in value) if records else json.dumps(value,indent=2)
        target.write_text(text,encoding='utf-8')
