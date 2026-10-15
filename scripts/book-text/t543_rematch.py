#!/usr/bin/env python3
"""#543 匹配器补强：异体归一＋对现库重对 new_candidate／ambiguous（只读，不改数据）。

对 original 实体线里 status 为 new_candidate／ambiguous 的实体，用「异体归一后的名」去查现库
（Work 的 title／additional_titles／original_title；Entity 的 primary_name／alt_names），分三类：
  EXACT   原文字面已在库里（建库后没回挂）
  VARIANT 只有归一后才命中（异体字没归一）
  NONE    库里确实没有 → 才是「要建档」的候选（还要过 §过滤）
归一：OpenCC t2s ＋ 手工异体表（𫎇→蒙 𠮓→變 𠈁→侂 …）。
用法：t543_rematch.py <book-index 根> <default 目录> <输出前缀> [册...]   默认册 002 003
输出：<前缀>.json（逐实体）和 <前缀>.md（汇总）
"""
import sys, os, glob, json, re, collections, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t543_rematch_norm import norm
DYN = '漢魏晉宋齊梁陳隋唐元明清周秦吳蜀'
ROOT, DEF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
VOLS = [a for a in sys.argv[4:]] or ['002', '003']

cache = '/tmp/claude-0/-home-user/54116cc6-d381-53c9-81d2-1c0266c69d0f/scratchpad/rematch_idx_v2.pkl'
if os.path.exists(cache):
    W, E = pickle.load(open(cache, 'rb'))
else:
    W = collections.defaultdict(list); E = collections.defaultdict(list)
    for f in glob.glob(f'{ROOT}/Work/*/*/*/*.json'):
        try: d = json.load(open(f, encoding='utf-8'))
        except Exception: continue
        if d.get('merged_into'): continue   # 已并入他条的 Work 不入匹配（10-14 B 侧约定；不按 indexed_by 过滤，空 indexed_by 的 Work 照常入）
        ts = [d.get('title'), d.get('original_title')] + [t if isinstance(t, str) else (t.get('title') or t.get('name') if isinstance(t, dict) else None) for t in (d.get('additional_titles') or [])]
        au = '、'.join(a.get('name', '') for a in (d.get('authors') or []) if isinstance(a, dict))[:30]
        for t in ts:
            if isinstance(t, str) and t: W[t].append((d['id'], d.get('dynasty') or '', au))
    for f in glob.glob(f'{ROOT}/Entity/*/*/*/*.json'):
        try: d = json.load(open(f, encoding='utf-8'))
        except Exception: continue
        ns = [d.get('primary_name')] + [a['name'] if isinstance(a, dict) else a for a in (d.get('alt_names') or [])]
        for n in ns:
            if isinstance(n, str) and n: E[n].append((d['id'], d.get('subtype') or '', d.get('dynasty') or ''))
    pickle.dump((dict(W), dict(E)), open(cache, 'wb'))
WN = collections.defaultdict(list); EN = collections.defaultdict(list)
for k, v in W.items(): WN[norm(k)] += [(k,) + x for x in v]
for k, v in E.items(): EN[norm(k)] += [(k,) + x for x in v]

rows = []
for vol in VOLS:
    en = json.load(open(f'{DEF}/{vol}.entity.json', encoding='utf-8'))['entities']
    for e in en:
        st = e['target'].get('status')
        if st not in ('new_candidate', 'ambiguous'): continue
        t, ty = e['text'], e['type']
        names = [t]
        if ty == 'people' and len(t) >= 3 and t[0] in DYN: names.append(t[1:])
        hits = []; kind = 'NONE'
        if ty in ('place', 'office'):
            rows.append({'vol': vol, 'id': e['id'], 'type': ty, 'text': t, 'anchor': e['anchor']['start'], 'status': st, 'kind': 'KEYTABLE', 'hits': [], 'n_hits': 0}); continue
        for nm in names:
            if ty == 'work':
                ex = W.get(nm); vr = WN.get(norm(nm))
                if ex: hits = [(nm,) + x for x in ex]; kind = 'EXACT'; break
                if vr: hits = vr; kind = 'VARIANT'; break
            else:
                ok = lambda sub: sub == ty or (ty == 'people' and sub in ('people', 'collective', ''))
                ex = [x for x in E.get(nm, []) if ok(x[1])]
                vr = [x for x in EN.get(norm(nm), []) if ok(x[2])]
                if ex: hits = [(nm,) + x for x in ex]; kind = 'EXACT'; break
                if vr: hits = vr; kind = 'VARIANT'; break
        rows.append({'vol': vol, 'id': e['id'], 'type': ty, 'text': t, 'anchor': e['anchor']['start'], 'status': st,
                     'kind': kind, 'hits': [list(h) for h in hits[:5]], 'n_hits': len(hits)})
json.dump(rows, open(OUT + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
c = collections.Counter((r['type'], r['kind']) for r in rows)
L = ['# 重对现库（异体归一）：四庫總目 册002／003 的 new_candidate／ambiguous\n',
     f'- 对象：{len(rows)} 个实体（status 为 new_candidate 或 ambiguous）；库：Work {len(W)} 个题名、Entity {len(E)} 个名（均含别名）。',
     '- 归一：OpenCC t2s ＋手工异体表。**只读，没有改任何数据**。\n', '| 类型 | EXACT（字面已在库） | VARIANT（归一后命中） | NONE（库里没有） |', '|--|--|--|--|']
for ty in ('work', 'people', 'place', 'office', 'dynasty', 'reign'):
    L.append(f"| {ty} | {c[(ty,'EXACT')]} | {c[(ty,'VARIANT')]} | {c[(ty,'NONE')]} |")

def flag(r):
    t = r['text']
    if r['type'] == 'work':
        if len(t) <= 2: return '过短（类名／简称？）'
        if re.search(r'(彖|象傳|大象|卦|爻)$', t): return '引文定位／卦名'
        if re.search(r'(傳|志|序|跋|記|書)$', t) and len(t) <= 6 and not re.search(r'(易傳|經籍志|藝文志)', t) is None: return '疑篇名／章'
        if re.search(r'(經籍志|藝文志|儒林傳|列傳|本傳|傳)$', t): return '疑篇名（史志／史传）'
    if r['type'] == 'people':
        if len(t) <= 2: return '过短（简称？）'
        if re.search(r'(氏|公|君|子)$', t): return '疑称谓'
    return ''
none = collections.defaultdict(list)
for r in rows:
    if r['kind'] == 'NONE' and r['type'] in ('work', 'people'): none[(r['type'], r['text'])].append(r)
single = [r for r in rows if r['kind'] in ('EXACT', 'VARIANT') and r['n_hits'] == 1 and r['status'] == 'new_candidate']
multi = [r for r in rows if r['kind'] in ('EXACT', 'VARIANT') and r['n_hits'] > 1 and r['status'] == 'new_candidate']
L += ['', '## 一、可回挂（new_candidate 且库里**恰好一个**命中）', '',
      f"- EXACT 单命中 {sum(1 for r in single if r['kind']=='EXACT')}；VARIANT 单命中 {sum(1 for r in single if r['kind']=='VARIANT')}；多命中（需消歧，应转 ambiguous）{len(multi)}。",
      '- 逐条在 .json（`hits` 含库名、id、朝代、作者）。VARIANT 命中一律抽审后再回挂；EXACT 单命中里的 work 要防"同名异书"（看作者朝代）。',
      '', '## 二、库里没有（NONE）：work／people 去重后', '']
cw = [(k, v) for k, v in none.items() if k[0] == 'work']; cp = [(k, v) for k, v in none.items() if k[0] == 'people']
L.append(f"- work {len(cw)} 种写法（{sum(len(v) for _,v in cw)} 处）；people {len(cp)} 种（{sum(len(v) for _,v in cp)} 处）；place/office 走键表，不在此。")
for ty, lst in (('work', cw), ('people', cp)):
    clean = [(k, v) for k, v in lst if not flag(v[0])]
    L += ['', f'### {ty}：过滤掉疑篇名／过短后剩 {len(clean)} 种（按出现次数降序，前 80）', '', '| 名 | 次数 | 首见锚点 | 状态 |', '|--|--|--|--|']
    for (k, v) in sorted(clean, key=lambda kv: -len(kv[1]))[:80]:
        L.append(f"| {k[1]} | {len(v)} | {v[0]['vol']}:{v[0]['anchor']} | {v[0]['status']} |")
    L += ['', f'<details><summary>被过滤的 {len(lst)-len(clean)} 种（疑篇名／过短／称谓）</summary>', '', '、'.join(f"{k[1]}[{flag(v[0])}]" for k, v in lst if flag(v[0])), '', '</details>']
open(OUT + '.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
