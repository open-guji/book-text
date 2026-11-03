"""读 book-index 源档（Entity/、Work/），代替将被删除的 book-index/index/ 缓存（A11 schema 审查落实，2026-11-03）。
- 只收存活记录：带 merged_into／promoted_to 的墓碑不收。
- people_names(bi)    → {id: {'subtype','primary_name','path'}}（Entity/）
- work_titles(bi)     → {id: {'title','path'}}（Work/）
- work_paths(bi)      → {id: 相对路径}（只看文件名，不读内容，最快）
"""
import json, os, re
from pathlib import Path

_ID = re.compile(r'^([0-9a-z]+)-')


def _walk(root, sub):
    base = Path(root) / sub
    for dp, _, fs in os.walk(base):
        for f in fs:
            if f.endswith('.json'):
                m = _ID.match(f)
                if m:
                    yield m.group(1), os.path.join(dp, f)


def _live(d):
    return isinstance(d, dict) and not (d.get('merged_into') or d.get('promoted_to') or d.get('_promoted_to'))


def entities(bi):
    out = {}
    for i, p in _walk(bi, 'Entity'):
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        if _live(d):
            out[i] = {'subtype': d.get('subtype', ''), 'primary_name': d.get('primary_name', ''),
                      'path': os.path.relpath(p, bi)}
    return out


def works(bi):
    out = {}
    for i, p in _walk(bi, 'Work'):
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        if _live(d):
            out[i] = {'title': d.get('title', ''), 'path': os.path.relpath(p, bi)}
    return out


def work_paths(bi):
    return {i: os.path.relpath(p, bi) for i, p in _walk(bi, 'Work')}
