"""build_texts_index.py：manifest 的 script 原样带进 index/texts，缺则缺（overview#605 E2）。
运行：python3 -m pytest scripts/book-text/test_build_texts_index.py -q"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _ver(key, **extra):
    v = {'key': key, 'kind': 'transcription', 'label': 'L', 'source': 'wikisource', 'source_name': 'W',
         'source_url': None, 'license': 'CC BY-SA 4.0', 'quality': 'source', 'chapters_total': 1}
    v.update(extra)
    return v


def _build(tmp_path, versions_by_id):
    for oid, vs in versions_by_id.items():
        d = tmp_path / 'Work' / oid[0] / oid[1] / oid[2] / oid
        d.mkdir(parents=True)
        (d / 'manifest.json').write_text(json.dumps({'id': oid, 'versions': vs}, ensure_ascii=False), encoding='utf-8')
    subprocess.run([sys.executable, os.path.join(HERE, 'build_texts_index.py'), '--root', str(tmp_path)], check=True,
                   capture_output=True)
    merged = {}
    for f in (tmp_path / 'index' / 'texts').glob('*.json'):
        merged.update(json.loads(f.read_text(encoding='utf-8')))
    return merged


def test_script_passthrough_and_absent(tmp_path):
    out = _build(tmp_path, {
        'abc1': [_ver('default', script='hant'), _ver('kanripo', script='mixed'), _ver('wikisource-2')],
        'abc2': [_ver('default', script='hans')],
    })
    assert [v.get('script') for v in out['abc1']] == ['hant', 'mixed', None]
    assert 'script' not in out['abc1'][2]          # 缺字段的版本不写 null
    assert out['abc2'][0]['script'] == 'hans'
    # 既有键不受影响
    assert out['abc1'][0]['quality'] == 'source' and out['abc1'][0]['chapters_total'] == 1


def test_original_headings_cache(tmp_path):
    """original 版本：按各册 punct 的标题符重算 index.json 章条目的 headings（GUJI-240）；其他版本不碰。"""
    oid = 'bk01'
    d = tmp_path / 'Book' / oid[0] / oid[1] / oid[2] / oid
    od = d / 'original'
    od.mkdir(parents=True)
    (d / 'manifest.json').write_text(json.dumps({'id': oid, 'versions': [_ver('default'), _ver('original', is_original=True)]}),
                                     encoding='utf-8')
    char = {'pages': [{'page': 1, 'columns': [{'col': 1, 'cells': [{'a': '1:1:1', 'c': '卷'}, {'a': '1:1:2', 'c': '一'}]},
                                                {'col': 2, 'cells': [{'a': '1:2:1', 'c': '正'}]}]}]}
    punct = {'$schema': 'https://open-guji.org/schema/punct/v0.2.json', 'punctuations': [
        {'mark': '#', 'kind': 'heading', 'pos': 'before', 'anchor': '1:1:1'},
        {'mark': '\n\n', 'kind': 'break', 'pos': 'after', 'anchor': '1:1:2', 'pre_char': '一'}]}
    (od / '001.char.json').write_text(json.dumps(char, ensure_ascii=False), encoding='utf-8')
    (od / '001.punct.json').write_text(json.dumps(punct, ensure_ascii=False), encoding='utf-8')
    (od / 'index.json').write_text(json.dumps({'chapters': [{'n': 1, 'file': '001'}]}), encoding='utf-8')
    subprocess.run([sys.executable, os.path.join(HERE, 'build_texts_index.py'), '--root', str(tmp_path)], check=True,
                   capture_output=True)
    idx = json.loads((od / 'index.json').read_text(encoding='utf-8'))
    assert idx['chapters'][0]['headings'] == [{'level': 1, 'label': '卷一', 'anchor': '1:1:1'}]
