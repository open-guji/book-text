#!/usr/bin/env python3
"""#535 句末缺句号：条目正文段末（后接书名行《…》）缺「。」，按段末格补。我读句后确认 8 处。默认干跑。
用法：t543_punct_period.py <default 目录> <册> [--apply]"""
import sys, json
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import original_char as C
D, vol = sys.argv[1:3]; apply = '--apply' in sys.argv
ANCH = {'002': ['59:7:9', '61:9:14', '83:5:7', '136:3:15', '142:4:6', '159:1:9'], '003': ['100:2:9', '106:6:16']}
pf = f'{D}/{vol}.punct.json'; P = json.load(open(pf, encoding='utf-8')); ps = P['punctuations']
ch = json.load(open(f'{D}/{vol}.char.json', encoding='utf-8')); slots = C.char_slots(ch); pos = {a: i for i, (a, c) in enumerate(slots)}
new = []
for a in ANCH.get(vol, []):
    i = pos[a]
    assert not [x for x in ps if x['char_offset'] == i and x['pos'] == 'after' and x['kind'] == 'point'], (a, '已有标记')
    new.append({'mark': '。', 'kind': 'point', 'pos': 'after', 'char_offset': i, 'pre_char': slots[i][1], 'anchor': a, 'source': 'claude:T-manual'})
    print(vol, a, slots[i][1], '→ 补 。', ''.join(c for _, c in slots[i - 7:i + 1]))
if apply and new:
    ps.extend(new); ps.sort(key=lambda x: (x['char_offset'], 0 if x['pos'] == 'before' else 1))
    P['stats']['total_annotations'] = len(ps); P['stats']['points'] = sum(1 for x in ps if x['kind'] == 'point'); P['stats']['periods'] = sum(1 for x in ps if x['mark'] == '。')
    json.dump(P, open(pf, 'w', encoding='utf-8'), ensure_ascii=False, indent=2); open(pf, 'a').write('\n')
