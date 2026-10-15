#!/usr/bin/env python3
"""B3 步 2(b)：只读检查「标点《》书名号范围」与「work 实体 span」是否起止一致。

用法：b3_shuming_check.py <book-text 根> [--book 96mid1ogzk] [--tsv 输出.tsv]

口径（Tamsin 10-14 定）：
- 《 取 punct 里 mark=='《' 的 char_offset 为起点（该字是书名首字）；
  》 取其后第一个 mark=='》' 的 char_offset+1 为终点（半开）。
- 与 entity.json 里 type=='work' 的 span[start_offset,end_offset) 逐一对照。
- 分类：
  EXACT        书名号范围与某 work 实体完全相同（一致，不输出明细）
  START/END    只有起点或终点不同（范围有重叠）→ 需处置：改实体边界或确认不是书名删《》
  NO_ENTITY    有《》但没有任何重叠的 work 实体 → 机械补实体 / 确认不是书名
  NO_BRACKET   work 实体没有被任何《》范围覆盖 → 登记（常为无书名号的书名）
只读，不写任何数据。
"""
import argparse, json, pathlib, sys


def pairs(punct):
    out, op = [], None
    for x in sorted((x for x in punct if x['mark'] in ('《', '》')), key=lambda x: (x['char_offset'], x['mark'] == '》')):
        if x['mark'] == '《':
            op = x['char_offset']
        elif op is not None:
            out.append((op, x['char_offset'] + 1)); op = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root'); ap.add_argument('--book', default='96mid1ogzk'); ap.add_argument('--tsv')
    a = ap.parse_args()
    d = next(pathlib.Path(a.root).glob(f'Book/*/*/*/{a.book}/default'))
    rows, tot = [], {}
    for pf in sorted(d.glob('*.punct.json')):
        vol = pf.name.split('.')[0]
        ef = d / f'{vol}.entity.json'
        if not ef.exists(): continue
        P = pairs(json.loads(pf.read_text())['punctuations'])
        W = [(e['span']['start_offset'], e['span']['end_offset'], e['id'], e['text'])
             for e in json.loads(ef.read_text())['entities'] if e['type'] == 'work']
        cj = json.loads((d / f'{vol}.char.json').read_text())
        S = ''.join(x['c'] for pg in cj['pages'] for c in pg['columns'] for x in c['cells'])
        used = set()
        for s, t in P:
            ov = [w for w in W if w[0] < t and s < w[1]]
            ex = [w for w in ov if w[0] == s and w[1] == t]
            if ex: used.add(ex[0][2]); tot[('EXACT')] = tot.get('EXACT', 0) + 1; continue
            if not ov:
                k = 'NO_ENTITY'; rows.append((vol, k, s, t, '', S[s:t])); tot[k] = tot.get(k, 0) + 1
            else:
                for w in ov:
                    used.add(w[2])
                    k = 'START' if w[0] != s and w[1] == t else 'END' if w[1] != t and w[0] == s else 'BOTH'
                    rows.append((vol, k, s, t, w[2], S[s:t] + '|' + w[3])); tot[k] = tot.get(k, 0) + 1
        for w in W:
            if w[2] not in used:
                rows.append((vol, 'NO_BRACKET', w[0], w[1], w[2], S[max(0, w[0] - 6):w[1] + 6] + '|' + w[3])); tot['NO_BRACKET'] = tot.get('NO_BRACKET', 0) + 1
    print(tot)
    if a.tsv:
        pathlib.Path(a.tsv).write_text('vol\tclass\tbracket_start\tbracket_end\tentity\ttext(书名号内文|实体文)\n' +
                                       ''.join('\t'.join(map(str, r)) + '\n' for r in rows), encoding='utf8')
    return 0


sys.exit(main())
