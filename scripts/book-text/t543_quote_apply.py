#!/usr/bin/env python3
"""#543/#535 引号机械单：按引号政策改 punct.json（只动标点线）。
  H  我方用「」『』标篇名、维基用《》且同一 span → 改成《》
  D  维基有「」直接引语整句、我方没有 → 加「」
输入是 punct_compare.py --quote-json 产出的候选 json（D 只收 kind=D直接引语）。默认干跑，--apply 才写。
用法：t543_quote_apply.py <default 目录> <册 002|003> <H|D> <候选json...> [--apply]"""
import sys, json, collections
D, vol, mode = sys.argv[1:4]
cj = [a for a in sys.argv[4:] if a.endswith('.json')]; apply = '--apply' in sys.argv
pf = f'{D}/{vol}.punct.json'; P = json.load(open(pf, encoding='utf-8')); ps = P['punctuations']
ch = json.load(open(f'{D}/{vol}.char.json', encoding='utf-8'))
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import original_char as C
slots = C.char_slots(ch); pos = {a: i for i, (a, c) in enumerate(slots)}
at = collections.defaultdict(list)
for k, x in enumerate(ps): at[(x['anchor'], x['pos'])].append(k)
ops = []
for f in cj:
    d = json.load(open(f, encoding='utf-8'))
    for c in (d['H'] if mode == 'H' else [x for x in d['D'] if x['kind'] == 'D直接引语']):
        ops.append(c)
# 人工剔除（读句子后判为字面引用而非篇名）：99:3:5『文言』二字
SKIP = {('H', '99:3:5')}
ops = [c for c in ops if (mode, c['start']) not in SKIP]
log = []; new = []
for c in ops:
    s, e = c['start'], c['end']
    if mode == 'H':
        ks = [k for k in at[(s, 'before')] if ps[k]['mark'] in '「『']; ke = [k for k in at[(e, 'after')] if ps[k]['mark'] in '」』']
        assert len(ks) == 1 and len(ke) == 1, (c['block'], s, e, c['text'])
        log.append((c['block'], s, e, c['text'], ps[ks[0]]['mark'] + ps[ke[0]]['mark'], '《》'))
        if apply:
            ps[ks[0]]['mark'] = '《'; ps[ke[0]]['mark'] = '》'
            for k in (ks[0], ke[0]): ps[k]['source'] = 'claude:T-manual'
    else:
        assert not [k for k in at[(s, 'before')] if ps[k]['mark'] in '「『《'] and not [k for k in at[(e, 'after')] if ps[k]['mark'] in '」』》'], (s, e)
        for a, p_, m in ((s, 'before', '「'), (e, 'after', '」')):
            i = pos[a]; new.append({'mark': m, 'kind': 'point', 'pos': p_, 'char_offset': i, 'pre_char': slots[i][1], 'anchor': a, 'source': 'claude:T-manual'})
        log.append((c['block'], s, e, c['text'][:30], '', '「」'))
if apply and new:
    ps.extend(new); ps.sort(key=lambda x: (x['char_offset'], 0 if x['pos'] == 'before' else 1))
    P['stats']['total_annotations'] = len(ps); P['stats']['points'] = P['stats'].get('points', 0) + len(new)
for r in log: print(*r)
print(mode, len(log), '处', '（已写）' if apply else '（干跑）')
if apply: json.dump(P, open(pf, 'w', encoding='utf-8'), ensure_ascii=False, indent=2); open(pf, 'a').write('\n')
