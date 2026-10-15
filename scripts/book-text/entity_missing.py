#!/usr/bin/env python3
"""original 实体线漏标候选（只读，N8 人名 / N9 书名）。
用法：
  python3 entity_missing.py <book-text根> <book-index根> [--book 96mid1ogzk] [--vol 002 ...] [--out DIR] [--stop 停用词.txt]
  python3 entity_missing.py ... --check 漏标处置.tsv [--only hi|lo]   # 候选须每行有处置，否则退出码 1
候选 = 库里有名、文中有字、未被任何实体 span 盖住（含部分重叠）的位置。
N8：index/entities 里 people 的 primary_name，≥2 字。N9：index/works 的 title，≥3 字，且前 6 字内有引导词。
偏移口径 = 该册 char.json 全部 cell 按序拼接后的下标（与 entity span.start_offset 同）。"""
import argparse, collections, glob, json, sys
from pathlib import Path

GUIDE = '撰著作載云見據稱曰言引依按案'
RAW = ['']
DIGITS = set('一二三四五六七八九十百千萬零〇廿卅')
GUIDE_WIN = 6
# N4 异体归一（逐字映射，长度不变；仅用于查键，输出仍是原文）
FOLD = str.maketrans('頴啟彞註顔冲邱鈎巖璇温卭', '穎啓彝注顏沖丘鉤岩璿溫邛')
fold = lambda s: s.translate(FOLD)


def load_index(bi):
    people, works = collections.defaultdict(list), collections.defaultdict(list)
    for f in glob.glob(str(Path(bi) / 'index/entities/*.json')):
        for k, v in json.load(open(f)).items():
            if v.get('subtype') == 'people' and len(v.get('primary_name', '')) >= 2:
                people[fold(v['primary_name'])].append(k)
    for f in glob.glob(str(Path(bi) / 'index/works/*.json')):
        for k, v in json.load(open(f)).items():
            if len(v.get('title', '')) >= 3:
                works[fold(v['title'])].append(k)
    return people, works


def load_vol(bt, book, vol):
    base = glob.glob(str(Path(bt) / f'*/*/*/*/{book}/default'))[0]
    cells = [c for p in json.load(open(f'{base}/{vol}.char.json'))['pages'] for col in p['columns'] for c in col['cells']]
    ents = json.load(open(f'{base}/{vol}.entity.json'))['entities']
    return cells, ents


def scan(names, text, covered, stop, kind, cells):
    by_len = collections.defaultdict(set)
    for n in names:
        by_len[len(n)].add(n)
    lens = sorted(by_len, reverse=True)
    taken = bytearray(covered)
    out = []
    for i in range(len(text)):
        if taken[i]:
            continue
        for L in lens:
            s = text[i:i + L]
            if len(s) < L or s not in by_len[L] or s in stop or s.endswith('氏'):
                continue
            if any(taken[i:i + L]):
                continue
            guide = ''
            if kind == 'N9_work':
                g = [ch for ch in text[max(0, i - GUIDE_WIN):i] if ch in GUIDE]
                if not g:
                    continue
                guide = g[-1]
            for j in range(i, i + L):
                taken[j] = 1
            nb = (text[i - 1:i] in DIGITS) or (text[i + L:i + L + 1] in DIGITS)
            risk = 'hi' if (L >= 3 and not nb) else 'lo'
            ids = names[s]
            mid = ids[0] if len(ids) == 1 else 'ambig:' + '|'.join(ids)
            r = RAW[0]; ctx = r[max(0, i - 10):i] + '【' + r[i:i + L] + '】' + r[i + L:i + L + 10]
            out.append((RAW[0][i:i + L], i, L, cells[i]['a'], ctx, mid, guide, risk))
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bt'); ap.add_argument('bi')
    ap.add_argument('--book', default='96mid1ogzk')
    ap.add_argument('--vol', nargs='*', default=['002', '003'])
    ap.add_argument('--out', default='.')
    ap.add_argument('--stop', default=None)
    ap.add_argument('--check', default=None)
    ap.add_argument('--only', choices=['hi', 'lo'])
    a = ap.parse_args()
    stop = set()
    if a.stop and Path(a.stop).exists():
        stop = {l.strip() for l in open(a.stop, encoding='utf-8') if l.strip() and not l.startswith('#')}
    people, works = load_index(a.bi)
    allc = []
    for vol in a.vol:
        cells, ents = load_vol(a.bt, a.book, vol)
        text = ''.join(c['c'] for c in cells)
        RAW[0] = text; text = fold(text)
        cov = bytearray(len(text))
        for e in ents:
            for j in range(e['span']['start_offset'], e['span']['end_offset']):
                cov[j] = 1
        rows = [('N8_person',) + r for r in scan(people, text, cov, stop, 'N8_person', cells)]
        cov2 = bytearray(cov)
        for r in rows:  # 人名先占位，书名不与之重叠
            for j in range(r[2], r[2] + r[3]):
                cov2[j] = 1
        rows += [('N9_work',) + r for r in scan(works, text, cov2, stop, 'N9_work', cells)]
        rows.sort(key=lambda r: r[2])
        for n, r in enumerate(rows, 1):
            allc.append((f'M{vol}-{n:04d}', vol) + r)
    hdr = 'cand_id\tvol\tkind\ttext\toffset\tlen\tanchor\tctx\tmatch_id\tguide\trisk'
    rowfmt = lambda c: '\t'.join(str(x) for x in (c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10]))
    if a.check:
        done = {l.split('\t')[0] for l in (open(a.check, encoding='utf-8').read().splitlines()[1:] if Path(a.check).exists() else []) if l.strip()}
        need = [c[0] for c in allc if not a.only or c[10] == a.only]
        miss = [x for x in need if x not in done]
        print(f'候选 {len(need)}，已处置 {len(need) - len(miss)}，未处置 {len(miss)}')
        for x in miss[:50]:
            print('  缺', x)
        sys.exit(1 if miss else 0)
    outd = Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    for vol in a.vol:
        rows = [c for c in allc if c[1] == vol]
        (outd / f'漏标候选-册{vol}.tsv').write_text(hdr + '\n' + '\n'.join(rowfmt(c) for c in rows) + '\n', encoding='utf-8')
        cnt = collections.Counter((c[2], c[10]) for c in rows)
        print(vol, len(rows), dict(cnt))


if __name__ == '__main__':
    main()
