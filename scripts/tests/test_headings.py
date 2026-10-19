"""标题符（guji-format spec/04 v0.2 §4.2，GUJI-240）：F-OV-12 结构检查、目录现算、index.json 目录缓存。
运行：python3 -m pytest scripts/tests/test_headings.py -q"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import original_version as OV  # noqa: E402

V02 = OV.PUNCT_V02


def char_of(*cols):
    """一页（39），每个字串一列，格号从 1 起。"""
    return {'pages': [{'page': 39, 'columns': [
        {'col': ci + 1, 'cells': [{'a': f'39:{ci + 1}:{i + 1}', 'c': c} for i, c in enumerate(t)]}
        for ci, t in enumerate(cols)]}]}


# 四庫總目第 2 册卷二开头的缩样
CHAR = char_of('欽定四庫全書總目卷二', '經部二', '易類二', '易數鈎隱圖三卷', '宋劉牧撰')


def H(a, mark, **kw):
    return dict({'mark': mark, 'kind': 'heading', 'pos': 'before', 'anchor': a}, **kw)


def BR(a, c, pos='after'):
    return {'mark': '\n\n', 'kind': 'break', 'pos': pos, 'anchor': a, 'pre_char': c}


def P(a, mark, c, pos='after'):
    return {'mark': mark, 'kind': 'point', 'pos': pos, 'anchor': a, 'pre_char': c}


def punct(*items, schema=V02):
    return {'$schema': schema, 'punctuations': list(items)}


GOOD = punct(
    H('39:1:1', '#', label='卷二　經部二'), BR('39:1:10', '二'),
    H('39:2:1', '#', toc=False), BR('39:2:3', '二'),
    H('39:3:1', '##'), BR('39:3:3', '二'),
    H('39:4:1', '###'), P('39:4:1', '《', '易', 'before'), P('39:4:5', '》', '圖'), BR('39:4:7', '卷'),
    P('39:5:4', '。', '撰'), BR('39:5:4', '撰'),
)


def subs(p, char=CHAR):
    return [s.split(':')[0] for _m, s in OV.heading_problems(char, p)]


def test_good_passes():
    assert subs(GOOD) == []


def test_extract_headings():
    assert OV.extract_headings(CHAR, GOOD) == [
        {'level': 1, 'label': '卷二　經部二', 'anchor': '39:1:1'},
        {'level': 2, 'label': '易類二', 'anchor': '39:3:1'},
        {'level': 3, 'label': '易數鈎隱圖', 'anchor': '39:4:1'},
    ]


def test_char_change_does_not_move_headings():
    # 换首字、换末字：标题照旧（标题符不写 pre_char）
    changed = char_of('钦定四庫全書總目卷貳', '經部二', '易類二', '易數鈎隱圖三卷', '宋劉牧撰')
    p = json.loads(json.dumps(GOOD))
    p['punctuations'][1]['pre_char'] = '貳'
    assert subs(p, changed) == []
    assert [h['anchor'] for h in OV.extract_headings(changed, p)] == ['39:1:1', '39:3:1', '39:4:1']


def test_break_before_rejected():
    p = punct(H('39:1:1', '#'), BR('39:2:1', '經', pos='before'), BR('39:5:4', '撰'))
    assert 'brkpos' in subs(p)


def test_heading_rules():
    assert 'hpos' in subs(punct(H('39:1:1', '#', pos='after'), BR('39:1:10', '二')))
    assert 'hmark' in subs(punct(H('39:1:1', '卷'), BR('39:1:10', '二')))
    assert 'hpre' in subs(punct(H('39:1:1', '#', pre_char='欽'), BR('39:1:10', '二')))
    assert 'hlabel' in subs(punct(H('39:1:1', '#', label=' '), BR('39:1:10', '二')))
    assert 'htoc' in subs(punct(H('39:1:1', '#', toc='no'), BR('39:1:10', '二')))
    assert 'hdup' in subs(punct(H('39:1:1', '#'), H('39:1:1', '##'), BR('39:1:10', '二')))
    assert 'label' in subs(punct(dict(P('39:1:2', '，', '定'), label='x')))


def test_boundaries_and_levels():
    # 标题前一字没有分段符
    assert 'hstart' in subs(punct(H('39:2:1', '#'), BR('39:2:3', '二')))
    # 标题后到下一个标题之前没有分段符
    assert 'hend' in subs(punct(H('39:1:1', '#'), H('39:2:1', '#')))
    # 册末的标题也要以分段符收尾
    assert 'hend' in subs(punct(H('39:1:1', '#')))
    # 跳级：# 之后直接 ###
    assert 'hskip' in subs(punct(H('39:1:1', '#'), BR('39:1:10', '二'), H('39:2:1', '###'), BR('39:2:3', '二')))


def test_schema_must_be_v02():
    p = punct(H('39:1:1', '#'), BR('39:1:10', '二'), schema='https://open-guji.org/schema/punct/v0.1.json')
    assert 'schema' in subs(p)
    # 没有标题符的 v0.1 文件照旧合法
    assert subs(punct(BR('39:1:10', '二'), schema='https://open-guji.org/schema/punct/v0.1.json')) == []


def test_sync_headings(tmp_path):
    od = tmp_path / 'original'
    od.mkdir()
    (od / '002.char.json').write_text(json.dumps(CHAR, ensure_ascii=False), encoding='utf-8')
    (od / '002.punct.json').write_text(json.dumps(GOOD, ensure_ascii=False), encoding='utf-8')
    (od / '003.char.json').write_text(json.dumps(CHAR, ensure_ascii=False), encoding='utf-8')
    (od / '003.punct.json').write_text(json.dumps(punct(BR('39:1:10', '二'))), encoding='utf-8')
    idx = {'chapters': [{'n': 2, 'file': '002'}, {'n': 3, 'file': '003', 'headings': [{'level': 1, 'label': 'x', 'anchor': '39:1:1'}]}]}
    (od / 'index.json').write_text(json.dumps(idx), encoding='utf-8')
    assert OV.sync_headings(str(od)) is True
    got = json.loads((od / 'index.json').read_text(encoding='utf-8'))
    assert got['chapters'][0]['headings'] == OV.extract_headings(CHAR, GOOD)
    assert 'headings' not in got['chapters'][1]      # 没有标题符的册删掉旧缓存
    assert OV.sync_headings(str(od)) is False         # 再跑一次不动盘


def test_heading_label_book_entry():
    from original_version import heading_label
    assert heading_label('《子夏易傳》十一卷内府藏本') == '子夏易傳'
    assert heading_label('新本《鄭氏周易》三卷江蘇巡撫採進本') == '新本鄭氏周易'
    assert heading_label('《某書》不分卷') == '某書'
    assert heading_label('讀《論語》法') == '讀論語法'      # 不是书目条：只去书名号
    assert heading_label('卷一　經部一') == '卷一　經部一'
