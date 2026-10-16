import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zhiming_parse as Z


def mk(page, col, spec):
    """spec: [(char, anchor_suffix_or_'', width)]"""
    cells, boxes = [], []
    for k, (c, suf, w) in enumerate(spec, 1):
        a = f'{page}:{col}:{k}{suf}'
        cells.append({'a': a, 'c': c})
        boxes.append({'a': a, 'box': [0, k * 100, w, 100]})
    return {'col': col, 'cells': cells}, boxes


def fixture(cols):
    with tempfile.TemporaryDirectory() as d:
        pages, cord = [], []
        for col, spec in cols:
            c, b = mk(90, col, spec)
            pages.append(c); cord += b
        json.dump({'pages': [{'page': 90, 'columns': pages}]}, open(os.path.join(d, '001.char.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        json.dump({'pages': [{'page': 90, 'cells': cord}]}, open(os.path.join(d, '001.cord.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        return Z.run(d, '001', 90, 90)


def test_entry_high():
    spec = [(c, '', 120) for c in '經筵講官'] + [(c, 'a', 60) for c in '協辦'] + [(c, 'b', 60) for c in '大學'] + [('臣', '', 60)] + [(c, '', 120) for c in '蔡新']
    r = fixture([(8, spec)])[0]
    assert r['kind'] == 'entry' and r['head'] == '經筵講官協辦大學' and r['name'] == '蔡新' and r['conf'] == '高'
    assert r['a_name0'] == '90:8:10' and r['a_name1'] == '90:8:11' and r['a_chen'] == '90:8:9'


def test_dachen_in_head_not_cut():
    spec = [(c, '', 120) for c in '軍機大臣'] + [('臣', '', 60)] + [(c, '', 120) for c in '阿桂']
    r = fixture([(1, spec)])[0]
    assert r['head'] == '軍機大臣' and r['name'] == '阿桂'


def test_heading_and_unsure():
    h = [(c, '', 120) for c in '總裁官']
    bad = [(c, '', 120) for c in '經筵講官'] + [('臣', '', 60)] + [('桂', '', 120)]
    rows = fixture([(1, h), (2, bad)])
    assert rows[0]['kind'] == 'heading'
    assert rows[1]['kind'] == '待人核'


def test_title_with_chen_is_heading():
    h = [(c, '', 120) for c in '欽定四庫全書勘閱繕校諸臣職名']
    rows = fixture([(1, h)])
    assert rows[0]['kind'] == 'heading'


def test_wide_chen_lowers_confidence():
    spec = [(c, '', 120) for c in '吏部尚書'] + [('臣', '', 118)] + [(c, '', 120) for c in '劉墉']
    r = fixture([(3, spec)])[0]
    assert r['conf'] == '中'
