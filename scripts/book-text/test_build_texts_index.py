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
