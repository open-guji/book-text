#!/usr/bin/env python3
"""#543 回挂小单生成：读 t543_rematch.py 的 json，把「库里恰好一个命中」的 new_candidate 分档（只读，出单不改数据）。
  A 高置信：work＝命中作者名出现在文中前后 80 字内，或题名≥6字；people＝名≥3字且命中唯一
  B 人工看：其余单命中
  H 暂扣：我人工看过判为有疑的（HOLD 表）
输出：<前缀>-A.json（给 Livia 的回挂单）、<前缀>-B.md（我自己看的清单）
用法：t543_rematch_plan.py <rematch.json> <default 目录> <输出前缀>"""
import sys, json, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import original_char as C
from t543_rematch_norm import norm   # 撰人比对走异体归一（彝／彞／𢑴 同组，𠮓＝變，𫎇＝蒙）
R, D, OUT = sys.argv[1:4]
HOLD = {'e00805': '易繫辭：疑为《易》之篇名，库条目无作者无朝代', 'e00928': '錄古周易：库条目无作者，需核', 'e01129': '內閣書目：库条目作者錢溥，文中指張萱重編本，疑非同书',
        '003:e00325': '㕘同契：库条目作者希還，是注本，文中泛指《參同契》', '003:e00321': '天台：疑为地名误标 people'}
rows = [r for r in json.load(open(R, encoding='utf-8')) if r['status'] in ('new_candidate', 'ambiguous') and r['n_hits'] == 1 and r['kind'] in ('EXACT', 'VARIANT') and r['type'] in ('work', 'people')]
txt = {}
for v in sorted({r['vol'] for r in rows}):
    ch = json.load(open(f'{D}/{v}.char.json', encoding='utf-8')); sl = C.char_slots(ch)
    txt[v] = (''.join(c for a, c in sl), {a: i for i, (a, c) in enumerate(sl)})
A, B, H = [], [], []
for r in rows:
    t, pos = txt[r['vol']]; i = pos[r['anchor']]; ctx = t[max(0, i - 80): i + len(r['text']) + 80]
    h = r['hits'][0]; key = r['id'] if r['vol'] == '002' else f"{r['vol']}:{r['id']}"
    item = dict(vol=r['vol'], entity=r['id'], anchor=r['anchor'], text=r['text'], kind=r['kind'], type=r['type'],
                target_name=h[0], target_id=h[1], dynasty=h[2] if r['type'] == 'work' else h[3], author=h[3] if r['type'] == 'work' else '')
    if key in HOLD: item['why'] = HOLD[key]; H.append(item); continue
    if r['type'] == 'work':
        ok = (item['author'] and any(a and norm(a) in norm(ctx) for a in item['author'].split('、'))) or len(r['text']) >= 6
    else:
        ok = len(r['text']) >= 3
        if len(h[0]) < len(r['text']):   # span 含朝代前缀：朝代对不上＝可能是另一人（周汝能≠汝能）；对得上也要先拆 span（N7），不在回挂单里做
            item['why'] = ('剥前缀后命中，但朝代对不上' if r['text'][0] not in (item['dynasty'] or '') else 'span 含朝代前缀，先拆 span（N7）再回挂'); H.append(item); continue
    (A if ok else B).append(item)
json.dump(A, open(OUT + '-A.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
L = [f'# 回挂小单：A 档 {len(A)} 条（给 Livia）／B 档 {len(B)} 条（Tamsin 人工）／暂扣 {len(H)} 条', '', '## B 档', '', '| 册 | 实体 | 文中 | 库名 | 库 id | 朝代 | 作者 | 类 |', '|--|--|--|--|--|--|--|--|']
for x in B: L.append(f"| {x['vol']} | {x['entity']} | {x['text']} | {x['target_name']} | {x['target_id']} | {x['dynasty']} | {x['author']} | {x['kind']} |")
L += ['', '## 暂扣', ''] + [f"- {x['vol']} {x['entity']} {x['text']} → {x['target_name']}（{x['target_id']}）：{x['why']}" for x in H]
open(OUT + '-B.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print(len(A), len(B), len(H), collections.Counter((x['type'], x['kind']) for x in A))
