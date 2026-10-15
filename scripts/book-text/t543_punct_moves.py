#!/usr/bin/env python3
"""#535 错位标点改点（Tamsin 逐对读句后定的改点表，只动 punct.json 标点线）。
  A. 纯挪位：pairs json（punct_compare.py --pairs-json 产出）里我读后认定「我方标点偏了一格」的对，
     把我方那个句读标记挪到对侧缝（类型取维基或保留我方，见 MOVES）。
  B. 个例：按「无标点原文串＋偏移」定位的增删换（MANUAL）。
默认干跑；--apply 才写。用法：t543_punct_moves.py <default 目录> <册> <pairs json...> [--apply]"""
import sys, json, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import original_char as C
D, vol = sys.argv[1:3]; apply = '--apply' in sys.argv
pj = [a for a in sys.argv[3:] if a.endswith('.json')]   # 顺序须为 易類一→二→三（册002）或 四→五（册003，--n0 24）
pf = f'{D}/{vol}.punct.json'; P = json.load(open(pf, encoding='utf-8')); ps = P['punctuations']
ch = json.load(open(f'{D}/{vol}.char.json', encoding='utf-8')); slots = C.char_slots(ch); pos = {a: i for i, (a, c) in enumerate(slots)}
text = ''.join(c for a, c in slots)
PUN = '，。；、：？！'
# A：对的序号（按四块 pairs 依次编号 1..41）→ 终标记（None＝取维基侧纯句读，'keep'＝保留我方类型）
MOVES = {1: None, 2: None, 3: None, 4: None, 5: None, 7: None, 8: None, 10: None, 11: None, 12: None, 13: None,
         21: None, 22: None, 23: None, 27: None, 31: None, 32: None, 36: None, 40: 'keep'}
def at(i, p): return [k for k, x in enumerate(ps) if x['char_offset'] == i and x['pos'] == p]
def remove(i, mark):
    ks = [k for k in at(i, 'after') if ps[k]['mark'] == mark]
    assert len(ks) == 1, (i, mark, [ps[k]['mark'] for k in at(i, 'after')])
    return ks[0]
def mk(i, mark, p='after'):
    return {'mark': mark, 'kind': 'point', 'pos': p, 'char_offset': i, 'pre_char': slots[i][1], 'anchor': slots[i][0], 'source': 'claude:T-manual'}
dels = []; adds = []; log = []
n = int(sys.argv[sys.argv.index('--n0') + 1]) if '--n0' in sys.argv else 0
for f in pj:
    for x in json.load(open(f, encoding='utf-8')):
        n += 1
        if n not in MOVES: continue
        og, wg = x['ours_gap'], x['wiki_gap']; i0, i1 = pos[x['anchors'][0]], pos[x['anchors'][1]]
        src = i0 if any(c in PUN for c in og[0]) else i1; dst = i1 if src == i0 else i0
        sm = [c for c in og[0 if src == i0 else 1] if c in PUN]; assert len(sm) == 1, (n, og)
        dm = [c for c in wg[1 if src == i0 else 0] if c in PUN]
        # 注意 wiki_gap[0] 对应 idx[0]，[1] 对应 idx[1]
        wd = [c for c in wg[0 if dst == i0 else 1] if c in PUN]
        mark = sm[0] if MOVES[n] == 'keep' else (wd[0] if wd else sm[0])
        dels.append(remove(src, sm[0])); adds.append(mk(dst, mark))
        log.append((n, x['block'], slots[src][0], sm[0], '→', slots[dst][0], mark, x['ours'][:34]))
# B：个例（先 find 无标点原文串，再按偏移增删；before＝开标记，after＝其余）
def find(s):
    i = text.find(s); assert i >= 0 and text.find(s, i + 1) < 0, ('串不唯一/未找到', s); return i
def rm(i, mark, p='after'):
    ks = [k for k in at(i, p) if ps[k]['mark'] == mark]; assert len(ks) == 1, (i, mark, p, [ps[k]['mark'] for k in at(i, p)]); dels.append(ks[0]); log.append(('M', '删', slots[i][0], mark, slots[i][1]))
def ad(i, mark, p='after'):
    adds.append(mk(i, mark, p)); log.append(('M', '增', slots[i][0], mark, slots[i][1]))
MAN = {
 '002': [
  ('黃中有易解或曰', lambda j: [(ad, j + 4, '。')]),                                   # 易解。或曰
  ('復姤生卦說始邵子但', lambda j: [(rm, j + 4, '，'), (ad, j + 7, '，')]),             # 說，始邵子但 → 說始邵子，但
  ('以意决擇□會初', lambda j: [(rm, j + 3, '，')]),                                    # 决擇，□會，初 → 决擇□會，初
  ('之書事檀弓之記禮必謹', lambda j: [(rm, j + 1, '，'), (rm, j + 2, '《', 'before'), (rm, j + 2, '》'), (ad, j + 2, '，'),
                                    (rm, j + 6, '，'), (rm, j + 7, '《', 'before'), (rm, j + 7, '》'), (ad, j + 7, '，')]),   # 《事》《禮》非书名
 ],
 '003': [
  ('其知易知其能簡能易簡而天下之理得', lambda j: [(rm, j + 2, '《', 'before'), (rm, j + 2, '》'), (rm, j + 2, '，'), (rm, j + 6, '；'),
                                                (ad, j + 3, '，'), (ad, j + 7, '，')]),
  ('集畧次分上經', lambda j: [(rm, j, '》'), (rm, j, '，'), (ad, j + 1, '》'), (ad, j + 1, '，')]),
  ('又爲六十四象正劉履丁則云', lambda j: [(rm, j + 5, '。'), (ad, j + 2, '《', 'before'), (ad, j + 6, '》'), (ad, j + 6, '。')]),
 ]}
for s, fn in MAN.get(vol, []):
    j = find(s)
    for op in fn(j):
        op[0](*op[1:])
for r in log: print(*r)
print('删', len(dels), '增', len(adds), '（已写）' if apply else '（干跑）')
if apply:
    for k in sorted(set(dels), reverse=True): del ps[k]
    ps.extend(adds); ps.sort(key=lambda x: (x['char_offset'], 0 if x['pos'] == 'before' else 1))
    P['stats']['total_annotations'] = len(ps)
    P['stats']['points'] = sum(1 for x in ps if x['kind'] == 'point')
    P['stats']['periods'] = sum(1 for x in ps if x['mark'] == '。'); P['stats']['commas'] = sum(1 for x in ps if x['mark'] == '，')
    json.dump(P, open(pf, 'w', encoding='utf-8'), ensure_ascii=False, indent=2); open(pf, 'a').write('\n')
