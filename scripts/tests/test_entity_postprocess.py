"""entity_postprocess.py N1–N7 规则的回归测试（GUJI-378）。纯内存，不依赖数据目录。"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'epp', os.path.join(HERE, '..', 'book-text', 'entity_postprocess.py'))
epp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(epp)


def ent(i, ty, text, text_all, nth=0, status='new_candidate', canon=None):
    s = -1
    for _ in range(nth + 1):
        s = text_all.index(text, s + 1)
    return {'id': i, 'type': ty, 'text': text,
            'anchor': {'start': '1:1:%d' % s, 'end': '1:1:%d' % s},
            'span': {'start_offset': s, 'end_offset': s + len(text)},
            'target': {'status': status, 'canonical_name': canon or text}}


def doc(*ents):
    return {'entities': list(ents), 'stats': {}}


def go(text, ents, rules, breaks=None):
    out, log = epp.run(doc(*ents), text, rules, breaks=breaks)
    return out['entities'], log


def test_n1_deletes_hexagram_quotations_not_book_names():
    t = '乾卦彖傳曰震象謙六五乾'
    es = [ent('e1', 'work', '乾卦彖傳', t), ent('e2', 'work', '震象', t),
          ent('e3', 'work', '謙六五', t), ent('e4', 'work', '乾', t, nth=0)]
    # e4 与 e1 重叠无关本测：单独的卦名（可能是书名简称）不删
    out, log = go(t, [es[0], es[1], es[2]], ['N1'])
    assert out == []
    assert [r[0] for r in log.rows] == ['N1'] * 3
    out, _ = go('乾', [ent('e4', 'work', '乾', '乾')], ['N1'])
    assert len(out) == 1


def test_n1_keeps_people_with_same_text():
    t = '大象'
    out, _ = go(t, [ent('e1', 'people', '大象', t)], ['N1'])
    assert len(out) == 1


def test_n2_deletes_category_names_after_anchor_only():
    t = '分爲十類曰易曰書曰詩'
    es = [ent('e1', 'work', '易', t), ent('e2', 'work', '書', t), ent('e3', 'work', '詩', t)]
    out, log = go(t, es, ['N2'])
    assert out == [] and len(log.rows) == 3
    # 无「分爲十類」锚点时不删；前一字不是「曰」也不删
    t2 = '曰易'
    out, _ = go(t2, [ent('e1', 'work', '易', t2)], ['N2'])
    assert len(out) == 1
    t3 = '分爲十類之易'
    out, _ = go(t3, [ent('e1', 'work', '易', t3)], ['N2'])
    assert len(out) == 1


def test_n3_retypes_tang_dynasty_to_work():
    t = '舊唐書與唐會要及唐人'
    es = [ent('e1', 'dynasty', '唐', t, nth=0), ent('e2', 'dynasty', '唐', t, nth=1),
          ent('e3', 'dynasty', '唐', t, nth=2)]
    out, log = go(t, es, ['N3'])
    by = {e['id']: e for e in out}
    assert by['e1']['type'] == 'work' and by['e1']['text'] == '舊唐書'
    assert by['e2']['type'] == 'work' and by['e2']['text'] == '唐會要'
    assert by['e3']['type'] == 'dynasty'          # 後不接 書／會要，不动
    assert by['e1']['target']['status'] == 'new_candidate'
    assert len(log.rows) == 2


def test_n7_splits_unambiguous_dynasty_prefix():
    t = '明劉日升著'
    e = ent('e1', 'people', '明劉日升', t)
    out, log = go(t, [e], ['N7'])
    assert [(x['type'], x['text']) for x in out] == [('dynasty', '明'), ('people', '劉日升')]
    assert out[0]['span'] == {'start_offset': 0, 'end_offset': 1}
    assert out[1]['span'] == {'start_offset': 1, 'end_offset': 4}
    assert out[0]['id'] != out[1]['id'] and 'e1' in (out[0]['id'], out[1]['id'])
    assert log.rows[0][2] == 'split'


def test_n7_does_not_split_real_surname_names():
    t = '魏了翁著'
    e = ent('e1', 'people', '魏了翁', t, status='matched')
    out, log = go(t, [e], ['N7'])
    assert len(out) == 1 and not log.rows
    # 魏王弼：库里 canonical 并了朝代，已知清单里才拆
    t2 = '魏王弼注'
    e2 = ent('e2', 'people', '魏王弼', t2, status='matched')
    out, _ = go(t2, [e2], ['N7'])
    assert [x['text'] for x in out] == ['魏', '王弼']


def test_n6_adds_given_name_short_form_in_same_paragraph():
    t = '王應麟著書應麟又云'
    full = ent('e1', 'people', '王應麟', t, status='matched')
    out, log = go(t, [full], ['N6'], breaks=[len(t)])
    shorts = [e for e in out if e['text'] == '應麟']
    assert len(shorts) == 1 and shorts[0]['norm'] == '王應麟'
    assert log.rows[0][2] == 'add'


def test_n6_does_not_cross_paragraph_break():
    t = '王應麟著書應麟又云'
    full = ent('e1', 'people', '王應麟', t, status='matched')
    out, _ = go(t, [full], ['N6'], breaks=[5])   # 「書」后断段，後文應麟在下一段
    assert [e['text'] for e in out] == ['王應麟']


def test_no_overlap_and_recount():
    t = '甲乙丙丁'
    a = ent('e1', 'work', '甲乙', t)
    b = ent('e2', 'work', '乙丙', t)
    assert epp.check_no_overlap([a, b]) == ['e1', 'e2']
    out, _ = epp.run(doc(a), t, ['N1'])
    assert out['stats']['total_entities'] == 1 and out['stats']['works'] == 1
