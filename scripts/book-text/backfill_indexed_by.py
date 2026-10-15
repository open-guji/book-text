"""回補 `Work.indexed_by`：整理本繫了而 work 側未記者。

雙向鏈之一半。整理本某節寫著 `work_id: X`，即斷言「此志著錄了 X」；
X 之 `indexed_by` 便當有這一部志。實測 639 處只寫了一半——其中 631 條
之 `indexed_by` 本非空（列著別的志），單缺這一部，是漏，非有意。

**三條戒**：

1. **`source` 之名取既有慣例之眾數**，不可逕用 Work 之題。庫中作
   「舊唐書經籍志」而索引之題是「舊唐書·經籍志」，逕用則同一部志兩個名字，
   日後按名聚合者必分成兩堆。眾數各有數千條前例，唯一無歧。
2. **`summary` 不臆造**。該欄是志書著錄之原文；有則取節自身之正文
   （那正是該志之文），無則**不寫此欄**，不可由題目湊一句。
   正文之欄名兩制並存：多數整理本用 `content`，而《四庫全書總目》一部用
   `summary`。只讀 `content` 則四庫總目補出來的條全是有題無文的空殼
   （2026-09-05 實見三條），故二欄皆取。
3. **只補，不改**。已有同 `source_bid` 之條者一概跳過。

**2026-09-05 修**：本檔原將書條寫死為 `{'书', '書'}`，而 section `type` 已於
2026-08 遷至英文枚舉（`migrate_section_type.py`），遷後 `book` 一個也不匹配。
於是它一直報「斷鏈 0 處」——**不報錯，只是一節也篩不到**，實掃 126,570 節
無一命中。這正是 `sectype.py` 檔首所戒之「消費方未兼認新舊」，遷移三步走的
第 3 步漏了本檔。今改為一律過 `sectype`，並加一道閘：命中 0 節即 abort，
不讓「掃 0 節」與「全過」再輸出同一句話。

用法：
    python3 backfill_indexed_by.py --text ../book-text --meta ../book-index --dry-run
    python3 backfill_indexed_by.py --text ../book-text --meta ../book-index --meta . --apply
"""
import argparse
import collections
import glob
import json
import os
import sys


def _find_shared():
    """自本檔往上尋 sectype.py。**不可用 `~`**——$HOME 是 /root 而工作區在 /home/user。"""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        for base in (d, os.path.join(d, 'open-guji')):
            c = os.path.join(base, 'book-index-draft', '.claude', 'skills',
                             'hanzhi-curation', 'scripts')
            if os.path.exists(os.path.join(c, 'sectype.py')):
                return c
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    raise ImportError('尋不著 sectype.py（受控詞彙在 book-index-draft）')


sys.path.insert(0, _find_shared())
import sectype   # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import promotions_io as PIO  # noqa: E402  升格对照表统一读法（2026-10-08 起分片）

ap = argparse.ArgumentParser()
ap.add_argument('--text', default='../book-text')
ap.add_argument('--meta', action='append', default=None)
ap.add_argument('--apply', action='store_true')
ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--note', default='2026-08-26 雙向鏈回補：本志整理本繫本條而 work 側未記，今補。')
A = ap.parse_args()
if not (A.apply or A.dry_run):
    ap.error('須擇一：--dry-run 或 --apply')
TEXT = A.text.rstrip('/')
METAS = [m.rstrip('/') for m in (A.meta or ['../book-index'])]

SKIP_TYPE = {'anthology', 'fragment_collection'}

# **只補書條。** `indexed_by` 之義是「某志著錄了此書」，故節須是一條書目。
# 實測斷鏈之 639 節裡混著兩類不是書條的：
# - `tally`（舊作 `结语`）—— 「已上《禮記》。」之類的小結句，偶帶 work_id，非著錄
# - `verification`（舊作 `考证`）—— 考證之文，當入 `emendated_by`，是另一欄
# 不濾則這些會被寫成著錄條，而且寫進去之後看不出來歷。
# **詞表不自寫**，一律過 `sectype.is_book`（兼認 书／書／book）。


def write(p, d):
    t = p + '.tmp'
    with open(t, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(t, p)


# ── 元資料 ──────────────────────────────────────────────────────────
W_PATH = {}
for m in METAS:
    for s in '0123456789abcdef':
        p = os.path.join(m, 'index', 'works', f'{s}.json')
        if os.path.exists(p):
            for i, e in json.load(open(p, encoding='utf-8')).items():
                W_PATH.setdefault(i, os.path.join(m, e['path']))
D2P = {}
# promotions.json 自 2026-10-06 起在正式倉根（overview#432）：--meta 給的若是草稿倉，改讀其同級 book-index
PROMO_ROOTS = list(dict.fromkeys(
    os.path.join(os.path.dirname(m), 'book-index') if os.path.basename(m) == 'book-index-draft' else m
    for m in METAS))
for m in PROMO_ROOTS:
    if PIO.exists(m):
        for k, v in PIO.load_raw(m).items():
            D2P.setdefault(k, v['production_id'])


def nz(i):
    return D2P.get(i, i)


# ── `source` 之慣用名：取既有 indexed_by 中該 source_bid 之眾數 ────────
NAME = collections.defaultdict(collections.Counter)
for m in METAS:
    for p in glob.glob(f'{m}/Work/*/*/*/*.json'):
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        for y in (d.get('indexed_by') or []):
            if y.get('source_bid') and y.get('source'):
                NAME[nz(y['source_bid'])][y['source']] += 1


def canon(bid):
    c = NAME.get(nz(bid))
    return c.most_common(1)[0][0] if c else None


# ── 掃整理本，找斷鏈 ────────────────────────────────────────────────
TYPE, SUB = {}, {}
for f in glob.glob(f'{TEXT}/Work/*/*/*/*/collated_edition/index.json'):
    own = os.path.basename(os.path.dirname(os.path.dirname(f)))
    d = json.load(open(f, encoding='utf-8'))
    TYPE[own], SUB[own] = d.get('type'), d.get('collated_edition_type')

n_book = [0]                          # 命中之書條數，供閘用
todo = collections.defaultdict(list)   # work 檔路徑 → [(owner, sec)]
other_type = collections.Counter()
no_name = collections.Counter()
for f in sorted(glob.glob(f'{TEXT}/Work/*/*/*/*/collated_edition/juan/*.json')):
    own = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(f))))
    if TYPE.get(own) in SKIP_TYPE or SUB.get(own) in SKIP_TYPE:
        continue
    for sec in (json.load(open(f, encoding='utf-8')).get('sections') or []):
        if not sectype.is_book(sec.get('type')):
            other_type[sectype.canon(sec.get('type'))] += 1
            continue
        n_book[0] += 1
        ws = [sec['work_id']] if isinstance(sec.get('work_id'), str) else []
        v = sec.get('work_ids')
        if isinstance(v, list):
            ws += [x for x in v if isinstance(x, str)]
        for i in ws:
            p = W_PATH.get(i) or W_PATH.get(nz(i))
            if not p:
                continue
            try:
                d = json.load(open(p, encoding='utf-8'))
            except Exception:
                continue
            if d.get('_promoted_to') or d.get('merged_into'):
                continue
            sb = {nz(y.get('source_bid'))
                  for y in (d.get('indexed_by') or []) + (d.get('emendated_by') or [])
                  if y.get('source_bid')}
            if sb & {nz(own), own}:
                continue
            if not canon(own):
                no_name[own] += 1
                continue
            todo[p].append((own, sec))

if n_book[0] == 0:
    sys.exit('✗ 掃遍整理本，書條命中 0 節——多半是 section type 詞表又分岔了。'
             '「掃 0 節」與「全過」輸出一模一樣，故此處硬停。')
n = sum(len(v) for v in todo.values())
print(f'書條命中 {n_book[0]} 節；其中斷鏈 {n} 處，散在 {len(todo)} 條 Work')
per = collections.Counter(o for v in todo.values() for o, _ in v)
for k, c in per.most_common(8):
    print(f'   {canon(k)}（{k}）{c}')
if no_name:
    print(f'\n⚠ 下列 owner 在既有 indexed_by 中無前例，無從定其慣用名，**跳過不補**：')
    for k, c in no_name.most_common():
        print(f'   {k} {c} 處')

print(f'\n非書條之節（不補，另計）：{dict(other_type.most_common(6))}')
def body_of(sec):
    return (sec.get('content') or sec.get('summary') or '').strip()


with_sum = sum(1 for v in todo.values() for _o, s in v if body_of(s))
print(f'\n其中節有 content 可作 summary 者 {with_sum}，餘 {n - with_sum} 條不寫 summary')

if A.dry_run:
    print('\n（空跑，未動一字）')
    for p, v in list(todo.items())[:3]:
        o, s = v[0]
        print(f'   {os.path.basename(p)}  ← {canon(o)}　title_info={s.get("title")}')
    sys.exit(0)

changed = 0
added = 0
for p, v in sorted(todo.items()):
    d = json.load(open(p, encoding='utf-8'))
    ib = d.get('indexed_by') or []
    have = {nz(y.get('source_bid')) for y in ib if y.get('source_bid')}
    new = []
    for own, sec in v:
        if nz(own) in have:      # 同一 work 被同一志繫兩節，只補一條
            continue
        have.add(nz(own))
        e = {'source': canon(own), 'source_bid': nz(own)}
        if sec.get('title'):
            e['title_info'] = sec['title']
        c = body_of(sec)
        if c:
            e['summary'] = c
        e['note'] = A.note
        new.append(e)
    if not new:
        continue
    d['indexed_by'] = ib + new
    write(p, d)
    changed += 1
    added += len(new)
print(f'\n改 Work {changed} 條，補 indexed_by {added} 條')
