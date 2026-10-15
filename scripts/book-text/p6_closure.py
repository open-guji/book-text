#!/usr/bin/env python3
"""P6 步1（只读）：vol02/03 里 matched 到草稿库 place/office/官署 的条目，及其升格闭包。
用法：python3 p6_closure.py <book-text 根> <草稿库根> <正式库根> [输出 tsv]"""
import json, sys, glob
from pathlib import Path
bt, dr, pr = map(Path, sys.argv[1:4]); out = sys.argv[4] if len(sys.argv) > 4 else None
def load(root):
    d = {}
    for p in glob.glob(str(root / 'Entity/**/*.json'), recursive=True):
        e = json.load(open(p, encoding='utf-8')); d[e['id']] = e
    return d
D, P = load(dr), load(pr)
hit = {}
for p in sorted(glob.glob(str(bt / '*/*/*/*/96mid1ogzk/default/*.entity.json'))):
    for x in json.load(open(p, encoding='utf-8'))['entities']:
        t = x['target']
        if t['status'] == 'matched' and t.get('entity_id') in D and x['type'] in ('place', 'office'):
            hit.setdefault(t['entity_id'], x['type'])
def refs(e):
    r = []
    st = e.get('subtype')
    if st == 'place': r += [h['parent_id'] for h in e.get('history', []) if h.get('parent_id')]
    r += [e[k] for k in ('parent_id', 'base_office_id', 'institution_ref') if e.get(k)]
    r += [s['id'] for s in e.get('superiors', [])] + e.get('group_ids', [])
    return r
seen, queue, missing = {}, list(hit), []
while queue:
    i = queue.pop()
    if i in seen: continue
    if i in P: continue                      # 已在正式库
    if i not in D: missing.append(i); continue
    seen[i] = D[i]
    queue += [r for r in refs(D[i]) if r not in seen]
cnt = {}
for i, e in seen.items(): cnt[e['subtype']] = cnt.get(e['subtype'], 0) + 1
print('命中草稿条目（去重）', len(hit), {t: sum(1 for v in hit.values() if v == t) for t in ('place', 'office')})
print('升格闭包', len(seen), cnt, '| 不在两库的引用', len(missing), missing[:5])
if out:
    with open(out, 'w', encoding='utf-8') as f:
        f.write('草稿id\tsubtype\t名\t直接命中\n')
        for i, e in sorted(seen.items(), key=lambda kv: (kv[1]['subtype'], kv[1]['primary_name'])):
            f.write(f"{i}\t{e['subtype']}\t{e['primary_name']}\t{'是' if i in hit else '否'}\n")
