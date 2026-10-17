import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', 'decision')
sys.path.insert(0, os.path.join(HERE, '..'))
spec = importlib.util.spec_from_file_location('vtf', os.path.join(HERE, '..', 'validate_text_format.py'))
vtf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtf)


def load(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return json.load(f)


def subs(name):
    return [s for _m, s in vtf.decision_problems(load(name), load('char.json'))]


def test_valid_passes():
    assert subs('valid.decision.json') == []


def test_current_mismatch():
    assert any(s.endswith(':current') for s in subs('bad-current.decision.json'))


def test_missing_cell():
    assert any(s.endswith(':cell') for s in subs('bad-cell.decision.json'))


def test_resolved_current_in_cands():
    assert any(s.endswith(':cand0:same') or s.endswith(':resolved') for s in subs('bad-resolved-in-cands.decision.json'))
    assert any(s.endswith(':resolved') for s in subs('bad-resolved-in-cands.decision.json'))


def test_rejected_needs_by():
    assert any(s.endswith(':by') for s in subs('bad-no-by.decision.json'))


def test_book_id_and_volume_mismatch():
    d = load('valid.decision.json')
    d['book_id'], d['volume'] = 'other', 2
    s = [x for _m, x in vtf.decision_problems(d, load('char.json'))]
    assert 'book_id' in s and 'volume' in s


def v02(**kw):
    d = load('valid.decision.json')
    d['$schema'] = 'https://open-guji.org/schema/decision/v0.2.json'
    d['items'][0].update(kw)
    return [x for _m, x in vtf.decision_problems(d, load('char.json'))]


def test_v01_file_still_valid():
    assert subs('valid.decision.json') == []


def test_v02_without_new_keys_valid():
    assert v02() == []


def test_v02_seg_with_route_valid():
    assert v02(reason='seg_bad', route='recut') == []
    assert v02(reason='seg_missing_page', route='add_page', route_ref='GUJI-558') == []
    assert v02(reason='unclear') == []


def test_v02_seg_needs_route():
    assert any(x.endswith(':route:missing') for x in v02(reason='seg_recut'))


def test_v02_unclear_or_absent_rejects_route():
    assert any(x.endswith(':route:unexpected') for x in v02(reason='unclear', route='recut'))
    assert any(x.endswith(':route:unexpected') for x in v02(route='list'))


def test_v02_bad_enums_and_lone_ref():
    assert any(x.endswith(':reason') for x in v02(reason='blurry'))
    assert any(x.endswith(':route') for x in v02(reason='seg_bad', route='elsewhere'))
    assert any(x.endswith(':route_ref:alone') for x in v02(route_ref='GUJI-1'))


def test_v01_schema_rejects_v02_keys():
    d = load('valid.decision.json')
    d['items'][0]['reason'] = 'unclear'
    assert any(x.endswith(':reason:v01') for _m, x in vtf.decision_problems(d, load('char.json')))
