#!/usr/bin/env python3
"""P6 步6：bim promote 之后，把新升格 production 文件里残留的草稿 id 引用（主要是
office 的 dynasty_ids）按 book-index/promotions 映射改成正式 id。
用法：p6_fix_refs.py <book-index 根> <文件...>   只改 `"1jb…"` 形的字符串值。"""
import json, re, sys, glob, os
root, files = sys.argv[1], sys.argv[2:]
m = {}
for f in glob.glob(os.path.join(root, 'promotions', '*.json')):
    for k, v in json.load(open(f, encoding='utf-8')).items():
        if isinstance(v, dict) and 'production_id' in v:
            m[k] = v['production_id']
        elif isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, dict) and 'production_id' in vv:
                    m[kk] = vv['production_id']
pat = re.compile(r'"(1jb[0-9a-z]{10})"')
n = 0
for p in files:
    t = open(p, encoding='utf-8').read()
    u = pat.sub(lambda g: '"%s"' % m[g.group(1)] if g.group(1) in m else g.group(0), t)
    if u != t:
        open(p, 'w', encoding='utf-8').write(u); n += 1; print('改', p)
print('共改', n, '个文件')
