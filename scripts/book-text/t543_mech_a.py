#!/usr/bin/env python3
"""#543 机械单 A：四庫總目 original 实体线，删三类误标并改一类（只动 entity.json）。
  N1 卦名／爻位／「X彖」「X大象」「X象傳」等引文定位标成 work → 删
  N2 總敘「分爲十類，曰X」的十个类名标成 work → 删
  N3 「唐」被标成 dynasty 而实为书名一部分（唐會要、唐書、舊唐書經籍志、新唐書藝文志）→ 删 dynasty，换 work new_candidate
范围 = 指定册里「經部總敘＋易類一」两块。默认只报告，--apply 才写。
用法：t543_mech_a.py <default 目录> <册 002> [--apply]
"""
import json, re, sys, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import original_char as C

HEAD = ('經部總敘', '經部一', '易類一', '經部二', '易類二', '經部三', '易類三', '經部四', '易類四', '經部五', '易類五')
BLOCKS = ('經部總敘', '易類一')
N1 = re.compile(r'(.{0,2}(彖|大象)|[初上][六九]|謙六五|六五|震九四|乾卦|坤卦|乾坤|坤象傳|賁象傳|震彖傳)')
TEN = ('易', '書', '詩', '禮', '春秋', '孝經', '五經總義', '四書', '樂', '小學')
D, vol = sys.argv[1], sys.argv[2]; apply = '--apply' in sys.argv

ch = json.load(open(f'{D}/{vol}.char.json', encoding='utf-8'))
pu = json.load(open(f'{D}/{vol}.punct.json', encoding='utf-8'))
ef = f'{D}/{vol}.entity.json'
en = json.load(open(ef, encoding='utf-8'))
slots = C.char_slots(ch); pos = {a: i for i, (a, c) in enumerate(slots)}; text = ''.join(c for a, c in slots)
brk = sorted(pos[p['anchor']] for p in pu['punctuations'] if p['kind'] == 'break')
paras = []; s = 0
for b in brk: paras.append((s, b)); s = b + 1
if s < len(slots): paras.append((s, len(slots) - 1))
rng = []; cur = None
for (s, e) in paras:
    t = text[s:e + 1]
    if t in HEAD: cur = t; continue
    if cur in BLOCKS: rng.append((cur, s, e))
def where(i):
    for n, s, e in rng:
        if s <= i <= e: return n

ents = en['entities']; keep = []; ops = []; adds = []
nid = max(int(e['id'][1:]) for e in ents)
for e in ents:
    a, b = pos[e['anchor']['start']], pos[e['anchor']['end']]
    blk = where(a); t = e['text']
    if blk and e['type'] == 'work' and N1.fullmatch(t) and t not in ('彖傳', '象傳'):
        ops.append(('N1 删', e['id'], e['anchor']['start'], t)); continue
    if blk == '經部總敘' and e['type'] == 'work' and t in TEN and text[a - 1] == '曰':
        ops.append(('N2 删', e['id'], e['anchor']['start'], t)); continue
    if blk and e['type'] == 'dynasty' and t == '唐' and text[b + 1:b + 3] in ('會要', '書無', '書經', '書藝'):
        nxt = text[b + 1:b + 3]
        a2 = a - 1 if text[a - 1] in '新舊' else a
        b2 = b + {'會要': 2, '書無': 1, '書經': 4, '書藝': 4}[nxt]
        wt = text[a2:b2 + 1]
        assert wt in ('唐會要', '唐書', '舊唐書經籍志', '新唐書藝文志'), wt
        nid += 1
        note = '篇名' if wt.endswith('志') else ('简称，待核《舊唐書》《新唐書》' if wt == '唐書' else None)
        tg = {'status': 'new_candidate', 'canonical_name': wt}
        if note: tg['note'] = note
        adds.append({'id': f'e{nid:05d}', 'type': 'work', 'text': wt,
                     'anchor': {'start': slots[a2][0], 'end': slots[b2][0]},
                     'span': {'start_offset': a2, 'end_offset': b2 + 1}, 'target': tg, 'source': 'claude:T-manual'})
        ops.append(('N3 唐→work', e['id'], e['anchor']['start'], f'唐 → {wt}'))
        continue
    keep.append(e)
# 新增 span 不得与保留实体重叠
for x in adds:
    for k in keep:
        assert k['span']['end_offset'] <= x['span']['start_offset'] or k['span']['start_offset'] >= x['span']['end_offset'], (x['text'], k['id'], k['text'])
cnt = collections.Counter(o[0] for o in ops)
for o in ops: print(*o)
print(dict(cnt), '共', len(ops))
if apply:
    out = keep + adds
    en['entities'] = out; st = en['stats']
    st['total_entities'] = len(out)
    for key, ty in (('works', 'work'), ('people', 'people'), ('places', 'place'), ('offices', 'office'), ('dynasties', 'dynasty'), ('reigns', 'reign')):
        st[key] = sum(1 for x in out if x['type'] == ty)
    for key, sv in (('matched', 'matched'), ('ambiguous', 'ambiguous'), ('new_candidates', 'new_candidate')):
        st[key] = sum(1 for x in out if x['target'].get('status') == sv)
    json.dump(en, open(ef, 'w', encoding='utf-8'), ensure_ascii=False, indent=2); open(ef, 'a').write('\n')
    print('已写', ef)
