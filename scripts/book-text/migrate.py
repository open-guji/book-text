"""book-index → book-text 之搬遷。

搬什麼、不搬什麼，依 `2026-08-book-text-仓库拆分设计.md` §1 之邊界：

  搬  Work/<id>/collated_edition/**    整理本
      Work/<id>/fragments/**           輯佚
      Work/<id>/ctext|source_text/**   抓取素材 → 併入 `sources/<來源>/`
      Book/<id>/full_text/**           全文
  不搬 Collection/<id>/*/volume_book_mapping.json   卷冊映射，元資料性質
      Book/<id>/tex/                   排版產物，另議
      Work/<id>/**/_working/           工作中間態
      Book/<id>/images/                書影，已於本日移往 overview

分片沿用 book-index 之 `shard_dirs()`（取 id **尾**三字元三級），
故原路徑之 `<c1>/<c2>/<c3>/<id>` 四段**原樣照搬**，不重算——
重算一遍徒然多一處出錯的機會，而兩倉本就該同一套。

用法：
    python3 migrate.py --src ../book-index --dst ../book-text --dry-run
    python3 migrate.py --src ../book-index --dst ../book-text --apply
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--src', required=True)
ap.add_argument('--dst', required=True)
ap.add_argument('--apply', action='store_true')
ap.add_argument('--dry-run', action='store_true')
A = ap.parse_args()
if not (A.apply or A.dry_run):
    ap.error('須擇一：--dry-run 或 --apply')
SRC, DST = A.src.rstrip('/'), A.dst.rstrip('/')

# 抓取素材之目錄名 → 併入 sources/ 之下的來源名
SOURCE_DIRS = {'ctext': 'ctext', 'source_text': 'source_text'}
KEEP_AS_IS = ('collated_edition', 'fragments')
EXCLUDE_DIR = {'_working'}


def plan():
    """(來源檔絕對路徑, 新倉之相對路徑) 之列。"""
    out = []
    for d in sorted(glob.glob(f'{SRC}/Work/*/*/*/*/*')):
        if not os.path.isdir(d):
            continue
        sub = os.path.basename(d)
        rel_owner = os.path.relpath(os.path.dirname(d), SRC)   # Work/c/c/c/<id>
        if sub in KEEP_AS_IS:
            newsub = sub
        elif sub in SOURCE_DIRS:
            newsub = f'sources/{SOURCE_DIRS[sub]}'
        else:
            continue
        for r, ds, fs in os.walk(d):
            ds[:] = [x for x in ds if x not in EXCLUDE_DIR]
            for f in sorted(fs):
                src = os.path.join(r, f)
                out.append((src, os.path.join(
                    rel_owner, newsub, os.path.relpath(src, d))))
    for d in sorted(glob.glob(f'{SRC}/Book/*/*/*/*/full_text')):
        rel_owner = os.path.relpath(os.path.dirname(d), SRC)
        for r, ds, fs in os.walk(d):
            ds[:] = [x for x in ds if x not in EXCLUDE_DIR]
            for f in sorted(fs):
                src = os.path.join(r, f)
                out.append((src, os.path.join(
                    rel_owner, 'full_text', os.path.relpath(src, d))))
    return out


P = plan()
by_kind = {}
for s, d in P:
    # 路徑形如 Work/c/c/c/<id>/<kind>/…，故資產類在第 5 段（自 0 數），
    # 第 4 段是 owner id——取錯一位即按 owner 分組，數目看著像那麼回事而其實答非所問
    parts = d.split('/')
    k = parts[5] if len(parts) > 5 else '?'
    by_kind.setdefault(k, [0, 0])
    by_kind[k][0] += 1
    by_kind[k][1] += os.path.getsize(s)

print(f'搬 {len(P)} 檔，{sum(v[1] for v in by_kind.values())/1e6:.1f} MB')
for k, (n, b) in sorted(by_kind.items(), key=lambda x: -x[1][1]):
    print(f'   {k:<18} {n:>5} 檔  {b/1e6:>7.1f} MB')

excluded = [d for d in glob.glob(f'{SRC}/Work/*/*/*/*/*/_working')]
if excluded:
    print(f'\n不搬（工作中間態）：{len(excluded)} 目錄')
    for d in excluded:
        print('   ', os.path.relpath(d, SRC))

if A.dry_run:
    print('\n（空跑，未動一字）')
    for s, d in P[:3]:
        print(f'   {os.path.relpath(s, SRC)}\n     → {d}')
    sys.exit(0)

# ── 落實：先全量拷入新倉並逐檔覈 sha256，覈畢方動舊倉 ──────────────
# **不可邊拷邊刪。** 拷貝中途失敗而舊倉已缺，兩頭都不全。
n = 0
for s, rel in P:
    dst = os.path.join(DST, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(s, dst)
    n += 1
print(f'\n已拷 {n} 檔入 {DST}')

bad = []
for s, rel in P:
    dst = os.path.join(DST, rel)
    if hashlib.sha256(open(s, 'rb').read()).hexdigest() != \
            hashlib.sha256(open(dst, 'rb').read()).hexdigest():
        bad.append(rel)
if bad:
    print(f'✗ **{len(bad)} 檔內容不符，舊倉一字未動**：{bad[:5]}')
    sys.exit(1)
print(f'✓ 逐檔 sha256 覈對相符（{len(P)} 檔）')
print('\n舊倉之刪除另行——先跑 chk-cross 覈新倉，再刪。')
