#!/usr/bin/env python3
"""original 实体线覆盖率（只读）：各册 × 各类型的 matched/ambiguous/new_candidate 计数与链接率。
用法：python3 entity_coverage.py <book-text 根> [条目id，默认 96mid1ogzk]"""
import json, sys, glob, collections
from pathlib import Path
root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
bid = sys.argv[2] if len(sys.argv) > 2 else '96mid1ogzk'
cnt = collections.defaultdict(collections.Counter)
for p in sorted(glob.glob(str(root / f'*/*/*/*/{bid}/default/*.entity.json'))):
    e = json.load(open(p)); vol = Path(p).name.split('.')[0]
    for x in e['entities']:
        s = x['target']['status']
        cnt[(vol, x['type'])][s] += 1; cnt[('全部', x['type'])][s] += 1; cnt[(vol, '合计')][s] += 1; cnt[('全部', '合计')][s] += 1
print(f"{'册':<6}{'类型':<8}{'总':>6}{'matched':>9}{'ambig':>7}{'new':>6}{'链接率':>8}")
for (vol, ty), c in sorted(cnt.items(), key=lambda kv: (kv[0][0] != '全部', kv[0])):
    n = sum(c.values())
    print(f"{vol:<6}{ty:<8}{n:>6}{c['matched']:>9}{c['ambiguous']:>7}{c['new_candidate']:>6}{c['matched']/n:>8.1%}")
