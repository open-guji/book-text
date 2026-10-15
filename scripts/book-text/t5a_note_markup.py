#!/usr/bin/env python3
"""T5a：千頃堂書目（d59f2mel8d1c，默认）或宋史藝文志（d59f2gdp696q，T5b）default 版的夾注括號 ⟨ ⟩ 改為 < >（記法解鎖後）。

只替換 ⟨（U+27E8）與 ⟩（U+27E9）两个字符，别的字符一律不碰。
默认只统计（--count）；--chapter NNN --apply 才写入。
对比对象是 origin/main：输出 md 与 json 两侧各自的改动数。

用法：
  python3 t5a_note_markup.py <book-text 仓根> --count
  python3 t5a_note_markup.py <book-text 仓根> --chapter 001 --apply
"""
import argparse
import glob
import io
import os
import subprocess
import sys

DEFAULT_WID = 'd59f2mel8d1c'
OPEN, CLOSE = '⟨', '⟩'
NEW_OPEN, NEW_CLOSE = '<', '>'


def default_dir(root, wid):
    hits = glob.glob(os.path.join(root, 'Work', '*', '*', '*', wid, 'default'))
    if len(hits) != 1:
        sys.exit(f'找到 {len(hits)} 个 default 目录，应为 1')
    return hits[0]


def base_text(root, relpath):
    """origin/main 上该文件的内容；不存在则返回 None。"""
    r = subprocess.run(['git', '-C', root, 'show', f'origin/main:{relpath}'],
                       capture_output=True)
    return r.stdout.decode('utf-8') if r.returncode == 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--count', action='store_true', help='只统计，不写')
    ap.add_argument('--chapter', help='章号 NNN（一档一个 commit 用）')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--work', default=DEFAULT_WID, help='条目 id（默认千頃堂 d59f2mel8d1c；T5b 用 d59f2gdp696q）')
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    d = default_dir(root, a.work)

    if a.count:
        tot = {'md': [0, 0], 'json': [0, 0]}
        for f in sorted(os.listdir(d)):
            ext = f.rsplit('.', 1)[-1]
            if ext not in ('md', 'json'):
                continue
            s = io.open(os.path.join(d, f), encoding='utf-8').read()
            o, c = s.count(OPEN), s.count(CLOSE)
            if o != c:
                sys.exit(f'{f}: ⟨ {o} 与 ⟩ {c} 不成对，停止')
            if o:
                tot[ext][0] += o
                tot[ext][1] += 1
        for ext, (hits, files) in tot.items():
            print(f'{ext}: 命中 {hits}，文件 {files}')
        return

    if not a.chapter:
        sys.exit('需要 --chapter NNN（或 --count）')
    for ext in ('md', 'json'):
        rel = os.path.relpath(os.path.join(d, f'{a.chapter}.{ext}'), root)
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        cur = io.open(path, encoding='utf-8').read()
        base = base_text(root, rel)
        if base is not None and base != cur:
            sys.exit(f'{rel} 与 origin/main 不一致，停止（先确认分支干净）')
        if NEW_OPEN in cur or NEW_CLOSE in cur:
            sys.exit(f'{rel} 已含 < 或 >，停止（会与夹注混淆）')
        o, c = cur.count(OPEN), cur.count(CLOSE)
        if o != c:
            sys.exit(f'{rel}: ⟨ {o} 与 ⟩ {c} 不成对，停止')
        if not o:
            print(f'{rel}: 无命中，跳过')
            continue
        new = cur.replace(OPEN, NEW_OPEN).replace(CLOSE, NEW_CLOSE)
        print(f'{rel}: 改动 ⟨⟩ 各 {o} 处（origin/main 命中 {base.count(OPEN) if base else "?"}）')
        if a.apply:
            io.open(path, 'w', encoding='utf-8', newline='').write(new)


if __name__ == '__main__':
    main()
