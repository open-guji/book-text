"""以整理本為唯一真源，重投影 `Work.indexed_by` / `Work.emendated_by`。

與同目錄之 `backfill_indexed_by.py` 分工：那一支**只補不改**（整理本繫了而
work 側全無此源者，補一條）；本支**改已有者**——投影早於整理本之精修，或
中途經過吃字的管線，索引側遂成殘本。實測之三宗：

- 《直齋書錄解題》整理本 3,415 節解題俱在，投影到索引的 3,250 條裡
  2,086 條只剩書名。網站「引用」讀的正是索引側。
- 《欽定四庫全書總目》114 條**專名剝落**：《史記》條整理本 1,046 字完好，
  索引側 662 字，人名書名地名被整段吃掉（「撰，補。事蹟具本傳。，據引之説，
  以爲人，閒博士。」）。
- 《經義考》947 條、《宋史藝文志補》217 條同型。

**六條戒**（多半是踩出來的，勿刪）：

1. **只碰有整理本之源。** `source_bid` 所指之 Work 若無 `collated_edition`，
   其 `indexed_by` 條一概不動——那些是志書錄入直寫的，本倉沒有更好的版本。
2. **不刪。** 索引側有而整理本無對應者（孤條）只記不刪。《千頃堂書目》
   整理本 20,585 節裡只有 1 節掛了 work_id，而索引側有 12,600 條連結——
   照整理本重投影會刪掉 12,599 條真連結。孤條是**整理本缺連結**之症，
   不是索引側有髒；治法是把連結倒灌回整理本，不是在這裡刪。
3. **歧義不猜。** 一個 work_id 掛著整理本數節者（《陰符經注》五家、
   《易說》四家…四庫總目 177 組）跳過。先到先得地挑一節寫進去，
   就是把「同名異書誤合」從整理本複製到索引，而且再也看不出來歷。
4. **只在「索引側是整理本之刪節」時覆蓋，且刪掉的要夠多。**
   投影之壞是**單向刪字**——《直齋書錄解題》硬截在 100 字，
   《四庫全書總目》把人名書名地名整段吃掉（《史記》1,046→662 字）。
   二者之共相：索引側之文是整理本之**子序列**（只少字，不多字、不改字）。
   故判之以子序列，不以長短：
     - 兩邊歸一後相等          → 已同
     - 整理本之文 ⊆ 索引側     → 索引側更全（多半只是多個題名前綴，
                                《後漢藝文志》《三國藝文志》即此），**不動**
     - 索引側 ⊆ 整理本，且補回 ≥10 字且 ≥10%  → 覆蓋，這才是修
     - 索引側 ⊆ 整理本，但只補回三兩字        → 不動（`minor`）
   比長短之前先**剝掉整理本正文首行之書名**（若其等同節之 title）。
   《經義考》之投影是**有意**把首行書名剝去的（那一行已在 `title_info`），
   不剝而比，七千條都會判成「整理本更全」，於是把重複的書名再灌回
   `summary`——churn 七千條而網站上看不出分別。剝了再比，剩下的差
   只有一個「佚」字，自然落入 `minor`。
     - 索引側之「文」其實只是**書名**（等同節之 title，或為其子串）而
       整理本有正文 → 覆蓋。此為另一型之壞：投影只搬了題、沒搬文。
       《直齋書錄解題》2,339 條屬此——網站上那條「直齋書錄解題：史記」
       正是它。此型與刪字型不同，書名與解題正文互不包含，故須單判。
     - 長度相當而只差寥寥數字   → `variant`，字形之異（淸／清、内／內、
       韩／韓之屬），**不動**。整理本存原刻之異體，索引側用通行字，
       孰是孰非是繁體規範之政策，不歸本支決。抽樣所見「互異」十之八九是此。
     - 互不包含                → `divergent`，不猜，記入報告待人覈
   空正文一概不寫 `summary`，更不拿空串洗掉索引側已有之文。
5. **`title_info` 只補不改。** 索引側之 `title_info` 往往是**已規範過**的題
   （《元史藝文志》整理本作「金趙秉文易叢說十卷。」而索引側作「《易叢說》十卷」，
   後者才是題）。逕以節之 title 覆蓋，明史藝文志一部就要動 3,223 條，
   全是把規範題換成未規範的原文行——是倒退，不是修。故只在該欄**闕**時補。
6. **`source` 之名取既有慣例之眾數**，不可逕用 Work 之題。庫中作
   「舊唐書經籍志」而索引之題是「舊唐書·經籍志」，逕用則同一部志兩個名字。
7. **書條入 `indexed_by`，考證條入 `emendated_by`。** 二者是兩欄兩義。
   節之 type 一律過 `sectype.canon`，**不可自寫詞表**——`backfill_indexed_by.py`
   當初寫死 `{'书','書'}`，2026-08 資料遷到英文枚舉 `book` 之後它就一直
   靜默空轉，報「斷鏈 0 處」而實掃 126,570 節無一命中。本檔之 `--dry-run`
   一律先印每源掃了幾檔幾節，掃 0 即 abort。

用法：
    python3 reproject_indexed_by.py --text ../book-text --meta ../book-index --dry-run
    python3 reproject_indexed_by.py --text ../book-text --meta ../book-index --apply
    python3 reproject_indexed_by.py ... --source d59f2htm01du --apply   # 只做一部
"""
import argparse
import collections
import glob
import json
import os
import re
import sys


def _find_shared():
    """自本檔往上尋 sectype.py（受控詞彙之唯一副本，不另抄）。
    **不可用 `~` 展開**——本環境 $HOME 是 /root 而工作區在 /home/user。"""
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
ap.add_argument('--source', action='append', default=None,
                help='只處理這些 source_bid（可重複），預設全部')
ap.add_argument('--apply', action='store_true')
ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--max-change', type=float, default=0.5,
                help='單一源改動比例上限，超出即拒絕該源（防管線倒退時大規模誤傷）')
ap.add_argument('--report', default=None, help='把逐源統計寫成 TSV')
ap.add_argument('--show', type=int, default=0, help='印出前 N 處改動之新舊對照')
ap.add_argument('--force-source', action='append', default=None,
                help='這些 source_bid 之整理本無條件為準，繞過「索引側更全／微差」'
                     '之保護。**只在剛校正過該整理本時用**——保護之設是防管線'
                     '倒退，剛修過的整理本不在此列。2026-09-06 修《宋史藝文志》'
                     '之切分錯位，刪去了誤入之字，索引側那份反因「更長」被判成'
                     '更全而跳過 3,092 條，即須此旗。')
A = ap.parse_args()
if not (A.apply or A.dry_run):
    ap.error('須擇一：--dry-run 或 --apply')
TEXT = A.text.rstrip('/')
METAS = [m.rstrip('/') for m in (A.meta or ['../book-index'])]

# 節之 type → 落在 Work 的哪一欄
FIELD = {'book': 'indexed_by', 'verification': 'emendated_by'}
# 這些整理本不是書目志，其節不投影
SKIP_EDITION_TYPE = {'anthology', 'fragment_collection', 'placeholder'}
# 《漢書藝文志》整理本用 `category.works[]` 之別體（無 section type、無 content），
# 其投影另有管線且已帶 section／page，是全庫體例最佳者。本支不碰。
SKIP_SRC = {'d59f23o7ygw2'}


def write(p, d):
    t = p + '.tmp'
    with open(t, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(t, p)


def norm(s):
    """歸一：壓空白、去書名號、去末尾句號。只用於判斷，
    不用於寫入——寫入一律用整理本原文。"""
    s = re.sub(r'\s+', '', (s or '').strip())
    for ch in '《》〈〉':
        s = s.replace(ch, '')
    return s.rstrip('。．.')


def is_sub(a, b):
    """a 是否為 b 之子序列（a 由 b 只刪字得到）。空 a 恆真。"""
    if len(a) > len(b):
        return False
    it = iter(b)
    return all(c in it for c in a)


def is_variant(a, b):
    """長度相當而只差寥寥數字者，判為字形之異，非內容之異。

    門檻須按長度縮放，不可用定值：短題（十幾字）差 2 字已是大異，
    長篇考證（動輒上千字）差 2 字卻是無傷大雅之異體字。原定值 2
    對長文一律先卡死於長度門檻，SequenceMatcher 根本沒機會跑——
    實測姚振宗考證、三國藝文志裡差一兩個异體字（图/圖、内/內）之
    千字長條，因中間插字使前後錯位，逐位比對 `zip` 又把後續整段
    判成「全不同」，兩者疊加，白白把「幾乎全同」歸進「互異」，
    抽樣十之八九屬此。改以同一縮放門檻同時卡長度差與內容差，
    且一律用 SequenceMatcher（比逐位 zip 穩，不怕中間插字錯位）。

    另須關 `autojunk`：志書條目滿是「《某書》一卷」型高重複短語，
    difflib 預設之 autojunk（>1% 出現率即判為雜訊、不參與比對）一遇
    這種高重複文本就把比對搞爛——實測反使原判為變體者更常判成互異，
    方向與初衷相反，故一律 `autojunk=False`。
    """
    if not a or not b:
        return False
    import difflib
    limit = max(2, max(len(a), len(b)) * 0.05)
    if abs(len(a) - len(b)) > limit:
        return False
    d = (1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()) * max(len(a), len(b))
    return d <= limit + 1e-6   # 浮點：整數判等常因乘除誤差差 1e-15 而假性落敗


MIN_GAIN_ABS = 10      # 補回之字數下限
MIN_GAIN_REL = 0.10    # 補回之比例下限


# ── 元資料：id → 檔路徑 ─────────────────────────────────────────────
W_PATH = {}
for m in METAS:
    for s in '0123456789abcdef':
        p = os.path.join(m, 'index', 'works', f'{s}.json')
        if os.path.exists(p):
            for i, e in json.load(open(p, encoding='utf-8')).items():
                W_PATH.setdefault(i, os.path.join(m, e['path']))
if not W_PATH:
    sys.exit('✗ index/works 為空，元資料倉路徑有誤——掃 0 條與全過輸出一樣，故此處硬停')
print(f'元資料：work 索引 {len(W_PATH)} 條（{", ".join(METAS)}）')

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


# ── `source` 慣用名：既有 indexed_by/emendated_by 中該 bid 之眾數 ─────
NAME = collections.defaultdict(collections.Counter)
scan_meta = 0
for m in METAS:
    for p in glob.glob(f'{m}/Work/*/*/*/*.json'):
        scan_meta += 1
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        for fld in ('indexed_by', 'emendated_by'):
            for y in (d.get(fld) or []):
                if y.get('source_bid') and y.get('source'):
                    NAME[nz(y['source_bid'])][y['source']] += 1
print(f'慣用名：掃 work 檔 {scan_meta}，得 {len(NAME)} 個源之前例')


def canon_name(bid):
    c = NAME.get(nz(bid))
    return c.most_common(1)[0][0] if c else None


# ── 掃整理本 ────────────────────────────────────────────────────────
EDITIONS = {}
for f in glob.glob(f'{TEXT}/Work/*/*/*/*/collated_edition/index.json'):
    own = os.path.basename(os.path.dirname(os.path.dirname(f)))
    d = json.load(open(f, encoding='utf-8'))
    EDITIONS[own] = d.get('type') or d.get('collated_edition_type')
if not EDITIONS:
    sys.exit('✗ 未掃到任何 collated_edition/index.json，--text 路徑有誤')
todo_srcs = [s for s in EDITIONS
             if EDITIONS[s] not in SKIP_EDITION_TYPE and s not in SKIP_SRC]
if A.source:
    todo_srcs = [s for s in todo_srcs if s in set(A.source)]
print(f'整理本：{len(EDITIONS)} 部，其中書目志類 {len(todo_srcs)} 部待處理\n')


def collect(src):
    """回傳 (掃檔數, 節數, {(欄, work_id): [節…]}, 各節之 section 路徑)。"""
    jd = glob.glob(f'{TEXT}/Work/*/*/*/{src}/collated_edition/juan')
    if not jd:
        return 0, 0, {}
    files = sorted(glob.glob(jd[0] + '/*.json'))
    wmap = collections.defaultdict(list)
    nsec = 0

    def walk(secs, path):
        nonlocal nsec
        for s in secs:
            t = sectype.canon(s.get('type'))
            if t == 'category' and s.get('title'):
                sub = path + [s['title']]
            else:
                sub = path
            if t in FIELD:
                nsec += 1
                s = dict(s)
                s['_path'] = '／'.join(path)
                ids = []
                if isinstance(s.get('work_id'), str):
                    ids.append(s['work_id'])
                for x in (s.get('work_ids') or []):
                    if isinstance(x, str):
                        ids.append(x)
                for i in ids:
                    wmap[(FIELD[t], i)].append(s)
            if isinstance(s.get('sections'), list):
                walk(s['sections'], sub)

    for p in files:
        walk(json.load(open(p, encoding='utf-8')).get('sections') or [], [])
    return len(files), nsec, wmap


STAT = []
SHOW = []
pending = collections.defaultdict(dict)   # 檔路徑 → 待寫之 dict
for src in sorted(todo_srcs):
    nfile, nsec, wmap = collect(src)
    name = canon_name(src)
    st = dict(src=src, name=name or '?', files=nfile, secs=nsec, linked=len(wmap),
              hit=0, same=0, fixed=0, filled=0, ambiguous=0, empty=0,
              richer=0, minor=0, stub=0, variant=0, divergent=0, nowork=0,
              refused='')
    if nfile == 0 or nsec == 0:
        st['refused'] = '掃 0 檔／0 節'
        STAT.append(st)
        continue
    if not name:
        st['refused'] = '索引側無此源之條（尚未投影，非本支之事）'
        STAT.append(st)
        continue

    changes = []      # (檔路徑, 欄, 條 index, 新 title_info, 新 summary, 新增之 section)
    for (fld, wid), lst in sorted(wmap.items()):
        p = W_PATH.get(wid) or W_PATH.get(nz(wid))
        if not p:
            st['nowork'] += 1
            continue
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            st['nowork'] += 1
            continue
        es = [(k, e) for k, e in enumerate(d.get(fld) or [])
              if nz(e.get('source_bid')) in (nz(src), src)]
        if not es:
            continue                      # 缺條是 backfill_indexed_by.py 的活
        st['hit'] += len(es)
        if len(lst) > 1:                  # 戒 3：歧義不猜
            st['ambiguous'] += len(es)
            continue
        sec = lst[0]
        body = (sec.get('content') or sec.get('summary') or '').strip()
        ti = (sec.get('title') or '').strip()
        nt = norm(ti)
        # 比較用之正文：剝掉與節題重複之首行（見戒 4）
        body_cmp = body
        if nt:
            head, _, rest = body.partition('\n')
            if rest and norm(head) == nt:
                body_cmp = rest.strip()
        for k, e in es:
            upd = {}
            old = (e.get('summary') or '').strip()
            forced = src in (set(A.force_source) if A.force_source else set())
            if forced and body:
                if norm(old) != norm(body):
                    upd['summary'] = body
                else:
                    pass
            elif not body:
                st['empty'] += 1                      # 戒 4：空不覆蓋非空
            elif not forced:
                no, nb = norm(old), norm(body_cmp)
                gain = len(nb) - len(no)
                if no == nb:
                    pass                              # 已同
                elif not no:
                    upd['summary'] = body             # 索引側本無文
                elif is_sub(nb, no):
                    st['richer'] += 1                 # 索引側已含整理本之文
                elif is_sub(no, nb):
                    if gain >= MIN_GAIN_ABS and gain >= len(nb) * MIN_GAIN_REL:
                        upd['summary'] = body         # 這才是修
                    else:
                        st['minor'] += 1
                elif is_variant(no, nb):
                    st['variant'] += 1                # 字形之異，不動
                elif nt and no in nt and gain >= MIN_GAIN_ABS:
                    upd['summary'] = body             # 索引側只搬了題，沒搬文
                    st['stub'] += 1
                else:
                    st['divergent'] += 1              # 互有出入，不猜
            fill = {}
            if ti and not (e.get('title_info') or '').strip():
                fill['title_info'] = ti               # 戒 5：只補不改
            for k2, v2 in (('section', sec.get('_path')),
                           ('page', sec.get('page')),
                           ('juan', sec.get('juan'))):
                if v2 and not e.get(k2):
                    fill[k2] = v2
            if upd:
                changes.append((p, fld, k, upd, fill))
            elif fill:
                changes.append((p, fld, k, {}, fill))
                st['filled'] += 1
            else:
                st['same'] += 1
    st['fixed'] = sum(1 for c in changes if c[3])
    st['filled'] = sum(1 for c in changes if not c[3])

    # 驗收閘：改動比例過大即拒絕（管線倒退時，整理本可能反而比索引側差）
    denom = max(st['hit'] - st['ambiguous'], 1)
    ratio = st['fixed'] / denom
    if ratio > A.max_change:
        st['refused'] = f'改動比例 {ratio:.0%} > {A.max_change:.0%}，拒絕（--max-change 可放寬）'
        STAT.append(st)
        continue
    STAT.append(st)

    for p, fld, k, upd, fill in changes:
        d = pending.get(p) or json.load(open(p, encoding='utf-8'))
        pending[p] = d
        e = d[fld][k]
        if A.show and upd.get('summary') and len(SHOW) < A.show:
            SHOW.append((name, os.path.basename(p), e.get('summary'), upd['summary']))
        e.update(upd)
        e.update(fill)

# ── 報告 ────────────────────────────────────────────────────────────
hdr = (f"{'目錄書':16}{'卷檔':>5}{'節':>7}{'掛work':>7}{'命中':>7}{'已同':>7}"
       f"{'修正':>6}{'補欄':>6}{'歧義':>6}{'索引全':>7}{'微差':>6}{'只題':>6}"
       f"{'互異':>6}{'無work':>7}")
print(hdr)
print('─' * len(hdr.encode('gbk', 'ignore')))
for s in sorted(STAT, key=lambda x: -x['secs']):
    line = (f"{s['name'][:15]:16}{s['files']:5d}{s['secs']:7d}{s['linked']:7d}"
            f"{s['hit']:7d}{s['same']:7d}{s['fixed']:6d}{s['filled']:6d}"
            f"{s['ambiguous']:6d}{s['richer']:7d}{s['minor']:6d}{s['stub']:6d}"
            f"{s['variant']:6d}{s['divergent']:6d}{s['nowork']:7d}")
    if s['refused']:
        line += f'   ✗ {s["refused"]}'
    print(line)
tot_fix = sum(s['fixed'] for s in STAT if not s['refused'])
tot_fill = sum(s['filled'] for s in STAT if not s['refused'])
tot_amb = sum(s['ambiguous'] for s in STAT)
print(f"\n合計：修正 {tot_fix} 條、補欄 {tot_fill} 條，散在 {len(pending)} 個 work 檔；"
      f"歧義跳過 {tot_amb} 條")

if A.report:
    import csv
    with open(A.report, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(STAT[0].keys()), delimiter='\t')
        w.writeheader()
        w.writerows(STAT)
    print(f'逐源統計寫出：{A.report}')

for nm, f, before, after in SHOW:
    print(f'\n── {nm}　{f}')
    print(f'   舊（{len(before or "")}字）:', repr(before)[:200])
    print(f'   新（{len(after)}字）:', repr(after)[:200])

if A.dry_run:
    print('\n（空跑，未動一字）')
    sys.exit(0)

for p, d in sorted(pending.items()):
    write(p, d)
print(f'\n已寫 {len(pending)} 個 work 檔')
