"""以 book-text 之索引為權威，回寫元資料倉之 `Work._has_collated`。

拆分之前此欄由 `os.path.isdir(.../collated_edition)` 就地重算，兩者同倉，
自洽。拆分之後整理本在 book-text，元資料在 book-index，此欄遂成**跨倉派生**：
權威在 book-text 之 `index/collated/{0-f}.json`，元資料倉那一份只是快取
（網站列表頁要用，不能每條去問另一個倉）。

**此欄是唯一真指本地目錄之派生欄。** `_has_text`／`_has_image` 由
`resources[].types` 推得，說的是外部資源（ctext、IA 之屬），與本倉之檔無關——
抽樣三千條只二十三條真有本地目錄。本腳本一概不碰那兩欄。

用法：
    python3 sync_has_collated.py --text ../book-text --meta ../book-index --dry-run
    python3 sync_has_collated.py --text ../book-text --meta ../book-index --meta ../book-index-draft --apply
"""
import argparse
import glob
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import promotions_io as PIO  # noqa: E402  升格对照表统一读法（2026-10-08 起分片）

ap = argparse.ArgumentParser()
ap.add_argument('--text', default='../book-text')
ap.add_argument('--meta', action='append', default=None)
ap.add_argument('--apply', action='store_true')
ap.add_argument('--dry-run', action='store_true')
A = ap.parse_args()
if not (A.apply or A.dry_run):
    ap.error('須擇一：--dry-run 或 --apply')
TEXT = A.text.rstrip('/')
METAS = [m.rstrip('/') for m in (A.meta or ['../book-index'])]


def write(p, d):
    t = p + '.tmp'
    with open(t, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(t, p)


# ── 權威：book-text 之索引 ───────────────────────────────────────────
HAVE = set()
shards = sorted(glob.glob(f'{TEXT}/index/collated/*.json'))
for p in shards:
    HAVE |= set(json.load(open(p, encoding='utf-8')))

# **索引未必是最新的。** 以盤上目錄覈之，兩者不符即索引待重建——
# 索引若漏了一部，本腳本就會把那部的 `_has_collated` 抹成 false，
# 一次跑成全庫皆錯。故先對，不對則停。
ON_DISK = {os.path.basename(os.path.dirname(os.path.dirname(f)))
           for f in glob.glob(f'{TEXT}/Work/*/*/*/*/collated_edition/index.json')}
print(f'book-text 索引 {len(HAVE)} owner（{len(shards)} 片）　盤上 {len(ON_DISK)} 部')
if not shards:
    print('✗ 索引分片一份也沒讀到——路徑不對？先確認 --text 指得對，勿逕改資料。')
    sys.exit(1)
if HAVE != ON_DISK:
    print(f'✗ **索引與盤上不符**：索引多 {sorted(HAVE - ON_DISK)[:5]}，'
          f'盤上多 {sorted(ON_DISK - HAVE)[:5]}')
    print('  先跑 build_index.py 重建，再回來。索引漏一部，本腳本就把那部抹成 false。')
    sys.exit(1)

# draft → production 之歸一：整理本掛在 production id 上，而 draft 之墓碑
# 亦有此欄。**只可正向**（一個 draft 只升一次，是函數）。
D2P = {}
# promotions.json 自 2026-10-06 起在正式倉根（overview#432）：--meta 給的若是草稿倉，改讀其同級 book-index
PROMO_ROOTS = list(dict.fromkeys(
    os.path.join(os.path.dirname(m), 'book-index') if os.path.basename(m) == 'book-index-draft' else m
    for m in METAS))
for m in PROMO_ROOTS:
    if PIO.exists(m):
        for k, v in PIO.load_raw(m).items():
            D2P.setdefault(k, v['production_id'])

fixed = []
skipped_tomb = 0
n = 0
for m in METAS:
    for p in glob.glob(f'{m}/Work/*/*/*/*.json'):
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        # 墓碑不碰：stub 化後只留骨架欄，其 `_has_collated` 說的是升格前之事，
        # 文本早已隨升格遷走。與 chk-cross 之豁免同理。
        if d.get('_promoted_to') or d.get('merged_into'):
            skipped_tomb += 1
            continue
        n += 1
        i = d.get('id') or os.path.basename(p).split('-', 1)[0]
        want = (i in HAVE) or (D2P.get(i) in HAVE)
        cur = bool(d.get('_has_collated'))
        if cur != want:
            fixed.append((os.path.relpath(p, m), cur, want))
            if A.apply:
                if want:
                    d['_has_collated'] = True
                else:
                    d.pop('_has_collated', None)
                write(p, d)

print(f'掃 Work {n} 條（墓碑 {skipped_tomb} 不計）　須改 {len(fixed)}')
for a, b, c in fixed[:10]:
    print(f'   {a}：記 {b}，實 {c}')
if A.dry_run:
    print('（空跑，未動一字）')
