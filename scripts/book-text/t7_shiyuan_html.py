#!/usr/bin/env python3
"""T7：千頃堂适园本（d59f2mel8d1c/shiyuan）016／017／020 md 的 HTML 残片清洗。

残片 = `');">` 之前的最大 ASCII 段（属性残留，起点可能被切在标记词中间）。
批量判准（裁定 #535，2026-10-11）：
  1. 段内含标记片段（popup／tytip／entity／emap／onmouseover／class=／tyid／res=／person／office／work）；
  2. 删残片后，残片前后各 6 个汉字的拼接串，能在同条目 kanripo／wikisource 的正文中找到（对照，不推断）。
两条都满足才进批量；其余列为个例，原样留着。删除只去掉残片段＋`');">`，保留《与书名字。

默认只统计（--count）；--sample N 列前后对照；--chapter NNN --apply 才写。
用法：
  python3 t7_shiyuan_html.py <book-text 仓根> --count
  python3 t7_shiyuan_html.py <book-text 仓根> --sample 20
  python3 t7_shiyuan_html.py <book-text 仓根> --chapter 016 --apply
"""
import argparse
import glob
import io
import os
import re
import sys

WID = 'd59f2mel8d1c'
CHAPTERS = ['016', '017', '020']
END = "');\">"
ASC = re.compile(r"[A-Za-z0-9_=\"'(),;&.:/\- \t%]")
CJK = re.compile(r"[㐀-鿿豈-﫿\U00020000-\U0002ffff]")
MARKS = ('popup', 'tytip', 'entity', 'emap', 'onmouseover', 'class=', 'tyid', 'res=', 'person', 'office', 'work')
FULL_MARKS = ('entitypopup', 'datepopup', 'entityid=', 'onmouseover=', 'titytip', 'entity_')
BANNED_AFTER = ('popup', 'onmouseover', 'entityid', 'class="', END)


def norm(t):
    return re.sub(r"[\s<>「」『』《》〈〉()（）,，。、；;：:！!？?\[\]\{\}\|]", "", t)


def work_dir(root):
    hits = glob.glob(os.path.join(root, 'Work', '*', '*', '*', WID))
    if len(hits) != 1:
        sys.exit(f'找到 {len(hits)} 个条目目录，应为 1')
    return hits[0]


def reference(wd):
    ref = ''
    for v in ('kanripo', 'wikisource'):
        for f in sorted(glob.glob(os.path.join(wd, v, '*.md'))):
            ref += norm(io.open(f, encoding='utf-8').read())
    return ref


def residues(s, ref):
    """返回 [(起, 止, 类别, 前后文)]；类别 'batch' 或 'excluded:<原因>'。"""
    out = []
    pos = 0
    while True:
        e = s.find(END, pos)
        if e < 0:
            break
        i = e
        while i > 0 and ASC.match(s[i - 1]):
            i -= 1
        run = s[i:e]
        left = ''.join(CJK.findall(norm(s[max(0, i - 40):i])))[-6:]
        right = ''.join(CJK.findall(norm(s[e + len(END):e + len(END) + 40])))[:6]
        pat = left + right
        if not run:
            cat = 'excluded:段为空'
        elif not any(m in run for m in MARKS):
            cat = 'excluded:无标记片段'
        elif len(pat) < 6 or pat not in ref:
            cat = 'excluded:对照不到kanripo/wikisource'
        else:
            cat = 'batch'
        out.append((i, e + len(END), cat, (left, right, run)))
        pos = e + len(END)
    return out


def load(root, ch):
    wd = work_dir(root)
    s = io.open(os.path.join(wd, 'shiyuan', f'{ch}.md'), encoding='utf-8').read()
    return wd, s


def step2_plan(s, ref):
    """第二步（#535 2026-10-11 20:10 裁定）：只批量「对照不到」的纯 ASCII 残片段。
    条件：段为纯 ASCII；删后《紧接汉字书名（段前是《），或段后 8 字内为「人名《书名」形态。
    其余单列。返回 (可删 [(起, 止, 前后文行)], 单列 [(位置, 原因)])。"""
    ok, lst = [], []
    for b, e, cat, (l, r, run) in residues(s, ref):
        if cat != 'excluded:对照不到kanripo/wikisource':
            continue
        if not run or any(ord(c) > 127 for c in run):
            lst.append((b, '段内含非 ASCII')); continue
        if not any(f in run for f in FULL_MARKS):
            lst.append((b, '只有标记片段，无完整标记词')); continue
        prev = s[b - 1] if b > 0 else ''
        after = s[e:e + 8]
        if prev == '《' and CJK.match(s[e:e + 1] or ''):
            ok.append((b, e, 'a: 《紧接书名'))
        elif '《' in after and CJK.match(s[e:e + 1] or '') and after.index('《') <= 7:
            ok.append((b, e, 'b: 人名《书名》形态'))
        else:
            lst.append((b, '段前非《且段后无人名《书名》形态'))
    return ok, lst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--count', action='store_true')
    ap.add_argument('--sample', type=int)
    ap.add_argument('--chapter', choices=CHAPTERS)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--step2', action='store_true', help='第二步：对照不到的纯 ASCII 段')
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    wd = work_dir(root)
    ref = reference(wd)

    if a.count:
        import collections
        tot = collections.Counter()
        for ch in CHAPTERS:
            s = io.open(os.path.join(wd, 'shiyuan', f'{ch}.md'), encoding='utf-8').read()
            rs = residues(s, ref)
            c = collections.Counter(r[2] for r in rs)
            tot.update(c)
            print(f'{ch}: END {len(rs)}；' + '；'.join(f'{k} {v}' for k, v in sorted(c.items())))
        print('合计：' + '；'.join(f'{k} {v}' for k, v in sorted(tot.items())))
        return

    if a.sample:
        n = 0
        for ch in CHAPTERS:
            s = io.open(os.path.join(wd, 'shiyuan', f'{ch}.md'), encoding='utf-8').read()
            for b, e, cat, (l, r, run) in residues(s, ref):
                if cat != 'batch' or n >= a.sample:
                    continue
                n += 1
                lo = max(0, b - 25)
                print(f'{ch} #{n}\n  前: {s[lo:e + 6]!r}\n  后: {(s[lo:b] + s[e:e + 6])!r}')
        return

    if a.step2:
        if not a.chapter:
            sys.exit('--step2 需要 --chapter')
        path = os.path.join(wd, 'shiyuan', f'{a.chapter}.md')
        s = io.open(path, encoding='utf-8').read()
        ok, lst = step2_plan(s, ref)
        out = s
        recs = []
        for b, e, why in reversed(ok):
            seg = s[b:e]
            ln = s[:b].count('\n') + 1
            out = out[:b] + out[e:]
            recs.append((ln, why, s[max(0, b - 30):e + 12], seg))
        for x in BANNED_AFTER:
            assert out.count(x) == s.count(x) - sum(s[b:e].count(x) for b, e, _ in ok), x
        assert (out.count('《'), out.count('》')) == (s.count('《'), s.count('》')), '《》变了'
        print(f'{a.chapter}: 第二步可删 {len(ok)} 处；单列 {len(lst)} 处')
        for ln, why, before, seg in sorted(recs):
            print(f'  L{ln} {why} 删段={seg!r}')
        if a.apply:
            io.open(path, 'w', encoding='utf-8', newline='').write(out)
        return

    if not a.chapter:
        sys.exit('需要 --count、--sample 或 --chapter')
    path = os.path.join(wd, 'shiyuan', f'{a.chapter}.md')
    s = io.open(path, encoding='utf-8').read()
    spans = [(b, e) for b, e, cat, _ in residues(s, ref) if cat == 'batch']
    before = (s.count('《'), s.count('》'))
    out = s
    for b, e in reversed(spans):
        out = out[:b] + out[e:]
    for x in BANNED_AFTER:
        gone = sum(s[b:e].count(x) for b, e in spans)
        assert out.count(x) == s.count(x) - gone, f'{x!r} 数量与预期不符'
    assert (out.count('《'), out.count('》')) == before, '《》数量变了'
    print(f'{a.chapter}: 批量删 {len(spans)} 处；《》 前后各 {before}')
    if a.apply:
        io.open(path, 'w', encoding='utf-8', newline='').write(out)


if __name__ == '__main__':
    main()
