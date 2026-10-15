#!/usr/bin/env python3
"""#543 建档批 1 回挂（Eric 建档结果-批1.md 的新 id）：精确同名的 new_candidate→matched；并做 span 修正。
span 修正：第五元→第五元先（扩一字）；嚴陵喻樗→喻樗；陳善捫蝨新話→人名陳善＋书名捫蝨新话；陳振孫書錄解題→陳振孫＋書錄解題；韓𠈁冑 target→韓侂胄。
默认干跑，--apply 才写。用法：t543_rebind_b1.py <default 目录> <建档结果-批1.md> [--apply]"""
import sys, re, json, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import original_char as C
D, MD = sys.argv[1:3]; apply = '--apply' in sys.argv
txt = open(MD, encoding='utf-8').read()
ids = {n.strip(): i for _, n, i in re.findall(r'^\| (\d+) \| ([^|]+?) \| `(hixi48\w+|d59fu304\w+)` \|', txt, re.M)}
ids['周易章句外編'] = ids['古周易章句外編']
ALIAS = {'書錄解題': 'd59f2htm01du', '毘陵易傳': 'd59f2hqd9a81', '兼山易說': 'd59f2hute0w0'}   # 既有 Work 补别名
CANON = {v: k for k, v in ids.items()}; CANON['周易章句外編'] = '古周易章句外編'
CANON.update({'d59f2htm01du': '直齋書錄解題', 'd59f2hqd9a81': '東坡易傳', 'd59f2hute0w0': '兼山易解'})
def tgt(i, name, note=None):
    kind = 'Work' if i.startswith('d59') else 'Entity'
    t = {'status': 'matched', 'entity_id': i, 'canonical_name': name, 'href': f'book-index://{kind}/{i}'}
    if note: t['note'] = note
    return t
log = collections.Counter()
for vol in ('002', '003'):
    ef = f'{D}/{vol}.entity.json'; en = json.load(open(ef, encoding='utf-8')); E = en['entities']
    ch = json.load(open(f'{D}/{vol}.char.json', encoding='utf-8')); sl = C.char_slots(ch); pos = {a: i for i, (a, c) in enumerate(sl)}
    nid = max(int(e['id'][1:]) for e in E); byid = {e['id']: e for e in E}
    def setspan(e, a, b, text):   # a,b 为 slot 序号（含端点）
        e['text'] = text; e['anchor'] = {'start': sl[a][0], 'end': sl[b][0]}; e['span'] = {'start_offset': a, 'end_offset': b + 1}
    # 1 精确同名
    for e in E:
        t = e['text']; i = ids.get(t) or ALIAS.get(t)
        if i and e['target'].get('status') == 'new_candidate' and e['type'] == ('work' if i.startswith('d59') else 'people'):
            e['target'] = tgt(i, CANON[i], note=(f'别名「{t}」' if t != CANON[i] else None)); log[(vol, '精确', t)] += 1
    # 2 span 修正
    for e in E:
        t = e['text']; a, b = pos[e['anchor']['start']], pos[e['anchor']['end']]
        if t == '第五元' and e['target']['status'] == 'new_candidate':
            assert sl[b + 1][1] == '先'; setspan(e, a, b + 1, '第五元先'); e['target'] = tgt(ids['第五元先'], '第五元先'); log[(vol, 'span', t)] += 1
        elif t == '韓𠈁冑':
            e['target'] = tgt(ids['韓侂胄'], '韓侂胄', note='原字形「韓𠈁冑」'); log[(vol, '字形', t)] += 1
        elif t == '嚴陵喻樗':
            assert sl[a][1] == '嚴' and sl[a + 1][1] == '陵'; setspan(e, a + 2, b, '喻樗'); e['target'] = tgt('hixhd2h9bhcp', '喻樗'); log[(vol, 'span', t)] += 1
        elif t == '陳善捫蝨新話':
            setspan(e, a, a + 1, '陳善'); e['type'] = 'people'; e['target'] = tgt('hixhd2h9bf1i', '陳善', note='《捫蝨新話》撰人（趙宋）')
            nid += 1; E.append({'id': f'e{nid:05d}', 'type': 'work', 'text': '捫蝨新話', 'anchor': {'start': sl[a + 2][0], 'end': sl[b][0]}, 'span': {'start_offset': a + 2, 'end_offset': b + 1}, 'target': tgt('d59f2ofqinsw', '捫蝨新話'), 'source': 'claude:T-manual'}); log[(vol, '拆分', t)] += 1
        elif t == '陳振孫書錄解題':
            setspan(e, a, a + 2, '陳振孫'); e['type'] = 'people'; e['target'] = tgt('hixhd2h9beoe', '陳振孫')
            nid += 1; E.append({'id': f'e{nid:05d}', 'type': 'work', 'text': '書錄解題', 'anchor': {'start': sl[a + 3][0], 'end': sl[b][0]}, 'span': {'start_offset': a + 3, 'end_offset': b + 1}, 'target': tgt('d59f2htm01du', '直齋書錄解題', note='别名「書錄解題」'), 'source': 'claude:T-manual'}); log[(vol, '拆分', t)] += 1
    st = en['stats']
    for key, ty in (('works', 'work'), ('people', 'people'), ('places', 'place'), ('offices', 'office'), ('dynasties', 'dynasty'), ('reigns', 'reign')): st[key] = sum(1 for x in E if x['type'] == ty)
    st['total_entities'] = len(E)
    for key, sv in (('matched', 'matched'), ('ambiguous', 'ambiguous'), ('new_candidates', 'new_candidate')): st[key] = sum(1 for x in E if x['target'].get('status') == sv)
    if apply: json.dump(en, open(ef, 'w', encoding='utf-8'), ensure_ascii=False, indent=2); open(ef, 'a').write('\n')
for k, v in sorted(log.items()): print(*k, v)
print('共', sum(log.values()), '处', '（已写）' if apply else '（干跑）')
