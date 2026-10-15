#!/usr/bin/env python3
"""B3 现状扫描：吻合度报告 §六 15 条修正方案的可复现计数（只读）。
用法：python3 b3_status.py <book-text 根>"""
import json, re, sys, subprocess
from pathlib import Path
from collections import Counter

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
mans = sorted(root.glob('*/*/*/*/manifest.json')) + sorted(root.glob('*/*/*/*/*/manifest.json'))
mans = sorted(set(mans))
out = {}
# #8b 登记例外（Maren 2026-10-14 裁①）：仓内无可考出处，登记为合法 unknown，不算未清
SRC_UNKNOWN_EXC = {'Work/i/b/m/d59f2mp2xibm:default', 'Work/6/4/g/d59f2ofwg64g:default',
                   'Work/d/1/c/d59f2rujgd1c:default', 'Work/w/8/y/d59f2mua7w8y:default'}
unk, lic, notkey, nolic, noqual = [], Counter(), [], [], 0
for mp in mans:
    d = mp.parent
    m = json.loads(mp.read_text())
    for v in m.get('versions', []):
        lic[str(v.get('license'))] += 1
        if v.get('source') in ('unknown', None, ''):
            unk.append(f"{d.relative_to(root)}:{v.get('key')}")
        if v.get('license') in (None, '', '未知', 'unknown'):
            nolic.append(f"{d.relative_to(root)}:{v.get('key')}")
out['#8 original source/license'] = [
    (str(p.parent.relative_to(root)), v.get('source'), v.get('license'))
    for p in mans for v in json.loads(p.read_text()).get('versions', []) if v.get('is_original')]
out['#8b source==unknown'] = len(unk)
out['#8b 其中已登记例外'] = len([u for u in unk if u in SRC_UNKNOWN_EXC])
out['#8b 未登记（应为 0）'] = len([u for u in unk if u not in SRC_UNKNOWN_EXC])
out['#8b license 分布'] = dict(lic)
out['#8b license 缺/未知'] = len(nolic)

# #11 json 无 md；#12 has_json 缺、level 字符串；#10 juan_groups 旧路径
nomd, hj_missing, lvl_str, jg_old = Counter(), 0, 0, 0
def walk_sections(o):
    global lvl_str
    if isinstance(o, dict):
        if isinstance(o.get('level'), str): lvl_str += 1
        for v in o.values(): walk_sections(v)
    elif isinstance(o, list):
        for v in o: walk_sections(v)
for mp in mans:
    d = mp.parent
    for ip in d.glob('*/index.json'):
        vd = ip.parent
        try: idx = json.loads(ip.read_text())
        except Exception: continue
        for c in idx.get('chapters', []):
            if 'has_json' not in c and 'char_file' not in c: hj_missing += 1
            f = c.get('file')
            if f is None: continue
            stem = f if isinstance(f, str) else str(f)
            stem = re.sub(r'\.(md|json)$', '', stem)
            if (vd / f'{stem}.json').exists() and not (vd / f'{stem}.md').exists() \
               and 'char_file' not in c:
                nomd[str(d.relative_to(root))] += 1
        for g in idx.get('juan_groups', []) or []:
            for f in g.get('files', []) or []:
                if str(f).startswith('juan/'): jg_old += 1
# F-CE-05「json 为真源」登记例外（guji-format spec/07，10-14 登记）：work 目录 -> 章数
F_CE_05_EXC = {'Work/w/8/y/d59f2mua7w8y': 75, 'Work/c/n/5/d59f2ncf8cn5': 1,
               'Work/l/z/4/d59f2mcdblz4': 1}  # d59dh3vo9af4 已对齐，10-14 移出（book-text #99）
unreg = {k: v for k, v in nomd.items() if v > F_CE_05_EXC.get(k, 0)}
out['#11 json 有而 md 无的章'] = sum(nomd.values()); out['#11 分布'] = dict(nomd)
out['#11 未登记（应为 0）'] = sum(v - F_CE_05_EXC.get(k, 0) for k, v in unreg.items()); out['#11 已登记例外'] = sum(min(v, F_CE_05_EXC.get(k, 0)) for k, v in nomd.items())
out['#12 has_json 缺'] = hj_missing; out['#10 juan_groups 旧路径'] = jg_old

# #5 #6 stats.ambiguous / 同名待消歧
st_bad, nc_dup = 0, 0
for ep in root.glob('Book/*/*/*/96mid1ogzk/default/*.entity.json'):
    e = json.loads(ep.read_text()); s = e.get('stats', {})
    if 'ambiguous' not in s: st_bad += 1
    amb = sum(1 for x in e['entities'] if x.get('target', {}).get('status') == 'ambiguous')
    if s.get('ambiguous') != amb: st_bad += 1
    nc_dup += sum(1 for x in e['entities'] if x.get('target', {}).get('status') == 'new_candidate'
                  and '待消歧' in json.dumps(x.get('target'), ensure_ascii=False))
    if '/v0.2' not in e.get('$schema', '') and 'v0.2' not in e.get('$schema', ''): st_bad += 1
out['#5/#6 stats 或 $schema 不符'] = st_bad
out['#6 new_candidate 带「待消歧」'] = nc_dup

# #9 CHANGES.md PR 栏空
empty = total = 0
for cp in root.rglob('CHANGES.md'):
    for ln in cp.read_text().splitlines():
        if re.match(r'\|\s*20\d\d-', ln):
            total += 1
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if not cells[-1] or cells[-1] in ('-',): empty += 1
out['#9 CHANGES 行数/PR 栏空'] = (total, empty)

# #7 ⟨⟩ 与旧读法
g = subprocess.run(['git', 'grep', '-c', '⟨\\|⟩', '--', 'Work', 'Book'], cwd=root, capture_output=True, text=True)
out['⟨⟩ 命中文件数'] = len([l for l in g.stdout.splitlines() if l])
for k, v in out.items(): print(f'{k}: {v}')
