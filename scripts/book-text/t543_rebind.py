#!/usr/bin/env python3
"""#543 回挂：按 t543_rematch_plan.py 的 A 档单，把 new_candidate 改成 matched（只改 target，不动 span／type）。
用法：t543_rebind.py <A档.json> <default 目录> [--apply]"""
import sys, json, collections
A, D = sys.argv[1], sys.argv[2]; apply = '--apply' in sys.argv
items = json.load(open(A, encoding='utf-8'))
by = collections.defaultdict(list)
for x in items: by[x['vol']].append(x)
for vol, xs in by.items():
    ef = f'{D}/{vol}.entity.json'; en = json.load(open(ef, encoding='utf-8')); idx = {e['id']: e for e in en['entities']}
    n = 0
    for x in xs:
        e = idx[x['entity']]
        assert e['text'] == x['text'] and e['anchor']['start'] == x['anchor'] and e['target']['status'] == 'new_candidate', (vol, x['entity'])
        kind = 'Work' if x['type'] == 'work' else 'Entity'
        tg = {'status': 'matched', 'entity_id': x['target_id'], 'canonical_name': x['target_name'], 'href': f"book-index://{kind}/{x['target_id']}"}
        if x['kind'] == 'VARIANT': tg['note'] = f"异体归一：原文「{x['text']}」＝库名「{x['target_name']}」"
        e['target'] = tg; n += 1; print(vol, x['entity'], x['text'], '→', x['target_name'], x['target_id'])
    st = en['stats']
    st['matched'] = sum(1 for e in en['entities'] if e['target'].get('status') == 'matched')
    st['new_candidates'] = sum(1 for e in en['entities'] if e['target'].get('status') == 'new_candidate')
    print(vol, '改', n, 'matched', st['matched'], 'new_candidates', st['new_candidates'])
    if apply:
        json.dump(en, open(ef, 'w', encoding='utf-8'), ensure_ascii=False, indent=2); open(ef, 'a').write('\n')
