#!/usr/bin/env python3
# 注意（09-30 落地后记）：本脚本写版本 index.json 时只保留了章目录等少数字段，漏掉了 source、text_quality、每章 md_len 等；
# 落地时已用 restore_index_fields.py 从迁移前提交补回。以后往新结构加版本请用 add_text.py（原样保留全部字段），不要再用本脚本。
# -*- coding: utf-8 -*-
"""book-text `<id>/manifest.json` + `<id>/<key>/` 迁移脚本（T51 #307-B，卡 #309）。

規格：overview `項目進展/古籍索引網站/設計/閱讀文本.md`（#307）。以規格為準，
本檔只是把規格的字段/規則落成可重複執行、可干跑的程式。

三類來源：
  1. 整理本  <id>/collated_edition/{index.json, juan/NNN.json, text/*.md}   （65 部）
  2. Work 全文 <id>/full_text/<key>/{index.json, NNN.md}                   （key：wikisource-01／wikisource-02／kanripo-01）
  3. Book 全文 <id>/full_text/{index.json, NNN.md}                         （無 key 層，一 Book 一份）

輸出：
  <id>/manifest.json、<id>/default/…、<id>/<key>/…（--apply 時真的落地到 --out，
  預設 --dry-run 只讀源倉、產出對照表與統計，不寫任何檔案到源倉）。

用法：
  python3 migrate_texts.py --root <book-text 倉根> --dry-run --out <干跑產物目錄>
  python3 migrate_texts.py --root <book-text 倉根> --apply   --out <臨時輸出目錄>
  python3 migrate_texts.py --verify --old-root <book-text 倉根> --new-root <apply 輸出目錄> --map <TSV>

本檔不改 book-text／book-text-private 任何檔案：--apply 的輸出目錄必須不是
--root 本身（腳本會拒絕在兩者相同或互相包含時執行）。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
from collections import OrderedDict, defaultdict

# ───────────────────────── 常量：key／label／保留字 ──────────────────────────

# 規格 §二 表格。private 倉的「識典古籍」也在這張表裡（key=shidian）。
SOURCE_KEY = OrderedDict([
    ('collated', ('collated', '整理本')),
    ('wikisource', ('wikisource', '維基文庫')),
    ('kanripo', ('kanripo', 'Kanripo')),
    ('shidian', ('shidian', '識典古籍')),
])

# full_text 磁盤目錄名前綴 → 規格 key（去掉 -01/-02 序號部分）。
DIRNAME_PREFIX_TO_KEY = {
    'wikisource': 'wikisource',
    'kanripo': 'kanripo',
    'shidian': 'shidian',
}

# Book 全文沒有目錄 key 層，只能從 index.json 的 source.name 猜 key；
# 覆蓋不到的落到 _slugify_source_name() 兜底（並在統計裡點名，供人核對）。
SOURCE_NAME_TO_KEY = {
    '維基文庫': 'wikisource', '维基文库': 'wikisource',
    'Kanripo': 'kanripo', 'kanripo': 'kanripo',
    '識典古籍': 'shidian', '识典古籍': 'shidian',
}

# 千頃堂書目 `text_適園叢書本/` 一類「整理本裡藏的第二版本」：全倉掃出來後逐個手
# 填的 slug 表（規格未給死規則，只說「key 按來源定」）。適園叢書本是底本名不是
# 站點來源，套不進 SOURCE_NAME_TO_KEY，故單列一張表，供人核對、可隨時增補。
HIDDEN_VERSION_SLUG = {
    '適園叢書本': 'shiyuan',
}
HIDDEN_VERSION_LABEL = {
    '適園叢書本': '適園叢書本',
}

RESERVED_KEYS = {'default', 'manifest', 'fragments', 'sources'}

# 舊 full_text primary 排序規則，原樣照抄自 build_index.py（供「新 default 是否
# 與舊 primary 一致」的對照使用；不要另起一套）。
GRADE_RANK = {'published': 0, 'fine': 1, 'rough': 2, 'ocr': 3, 'source': 4}


def _src_rank(src):
    src = src or {}
    name = str(src.get('name', ''))
    if src.get('kind') in ('self', 'original') or '開源古籍' in name or '开源古籍' in name:
        return 0
    if '維基' in name or '维基' in name or 'wikisource' in name.lower():
        return 1
    return 2


# 新 default 挑選裡「維基優先 Kanripo」的同名規則，用同一張 rank 表，保證兩處
# 「維基優先」的口徑一致（新舊只是应用场景不同：旧用于全 full_text 内部选 primary，
# 新用于「没有整理本时」挑 default）。
SOURCE_PRIORITY_RANK = {'wikisource': 0, 'kanripo': 1, 'shidian': 2}


def source_priority(key_base):
    return SOURCE_PRIORITY_RANK.get(key_base, 99)


# ───────────────────────── 分片：與 build_index.py 同一函式 ──────────────────

def shard(i):
    """與 overview scripts/book-text/build_index.py 的 shard() 完全相同的雜湊，
    這裡不能 `import build_index`：那個檔案在 import 時就會跑 argparse 主邏輯
    （頂層 `A = ap.parse_args()`），沒有 --root 會直接崩潰，所以改為照抄算法，
    並在兩邊都留註解互相指明，算法有變動要兩邊一起改。"""
    h = 0
    for c in i:
        h = ((h * 31) + ord(c)) & 0xFFFFFFFF
    return '%x' % (h % 16)


def owner_shard_dir(owner_type, owner_id):
    """`<Work|Book>/<c1>/<c2>/<c3>/<id>` 的分片：id 末三字元各自一層（book-text
    現有慣例，見任一 Work/Book 路徑），不是 shard() 那種雜湊分片——两套分片本来
    就不是一回事（build_index.py 開頭注釋也点過这一点）。"""
    tail = (owner_id[-3:] if len(owner_id) >= 3 else owner_id.rjust(3, '_'))
    return os.path.join(owner_type, tail[0], tail[1], tail[2], owner_id)


# ───────────────────────── 整理本卷號 → text/*.md 配對 ───────────────────────
# 起步於 scripts/book-text/juan_text_match.py（09-30 干跑：1,735 卷配上
# 1,635，餘 100 卷在 14 部）。本檔在其基礎上擴充三類規則，把餘下 100 卷全部
# 配上（逐部核對過，見卡 #309 交付的 texts-migration-stats.md 「卷名配對」節）：
#   A) 標題/source_juan 裡夾的阿拉伯數字當卷序（如「第89冊」「49冊[親軍衛]」），
#      分別试 2/3 位補零與不補零去配 `NNN冊`／`NN冊`／`N冊`；
#   B) 標題裡的中文數字（如「卷四十七」）轉數字後去配 `juan_NN` 一類檔名；
#   C) 別名表（目前只有「附錄」→`fulu`，該標題本身没有数字可提取）；
#   D) 兜底：一部書裡按 A/B/C 仍配不上的，如果「剩餘未配的卷」與「剩餘未用的
#      text 檔」在該書裡都恰好只有 1 個，配為一對（人工核對過：8 部單卷書
#      + 1 部「重訂曲海總目」序言部分再无旁的候选，全部这么解决，不是瞎配）。
#      這一步全部記入統計的「兜底配對」清單，供人复核。

CN_DIGIT = {'〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9}


def cn_to_num(s):
    """『十』『二十三』『四十七』『一百廿』一類中文數字轉阿拉伯數字，僅覆蓋本倉
    實際出現過的卷名形態（兩三位數即可），配不出回 None。"""
    if not s:
        return None
    if s == '十':
        return 10
    total = 0
    if '百' in s:
        bai, _, s = s.partition('百')
        total += (CN_DIGIT.get(bai, 1) if bai else 1) * 100
    if '十' in s:
        shi, _, ge = s.partition('十')
        total += (CN_DIGIT.get(shi, 1) if shi else 1) * 10
        if ge:
            v = CN_DIGIT.get(ge)
            if v is None:
                return None
            total += v
    elif s:
        v = CN_DIGIT.get(s)
        if v is None:
            return None
        total += v
    return total or None


def _norm_stem(s):
    s = re.sub(r'[\s·_\-－—・]', '', s or '')
    s = s.replace('冊', '册')  # 繁簡兩種「册」字同形視作等價
    return s


def cn_juan(n):
    if n is None or n >= 100:
        return None
    if n < 10:
        return CN_DIGIT_REV[n] if n else '〇'
    t, o = divmod(n, 10)
    return ('' if t == 1 else CN_DIGIT_REV[t]) + '十' + (CN_DIGIT_REV[o] if o else '')


CN_DIGIT_REV = '〇一二三四五六七八九'

TITLE_ALIAS_STEM = {
    '附錄': 'fulu',
    '附录': 'fulu',
}


def _extract_num(*texts):
    """從標題/source_juan 裡找卷序數字：優先阿拉伯數字，其次『卷／第 + 中文數字』。"""
    for t in texts:
        if not t:
            continue
        m = re.search(r'\d+', t)
        if m:
            return int(m.group())
    for t in texts:
        if not t:
            continue
        m = re.search(r'[卷第]([〇一二三四五六七八九十百]+)', t)
        if m:
            n = cn_to_num(m.group(1))
            if n is not None:
                return n
    return None


def match_collated_texts(d):
    """`d` 是某部書的 `collated_edition` 目錄（絕對或相對路徑均可）。

    回傳 (matches, fallback_pairs, unmatched_juan, leftover_texts)：
      matches        {juan_file: text_relpath}  經 juan_text_match.py 原規則或
                     本檔擴充規則（A/B/C）配上的；
      fallback_pairs {juan_file: text_relpath}  D 類兜底配對（剩餘唯一對唯一）；
      unmatched_juan [juan_file,...]            仍配不上的（理論上應為空表）；
                     這部書若根本沒有 text/ 目錄（json-only 整理本，見下方
                     json-only 分支），回傳 None 而非空表，呼叫端要分開處理；
      leftover_texts [text_relpath,...]         配對後沒被任何卷認領的 text 檔
                     （juan_groups.* 一類附加檔案，或真正多出來的雜項）。
    """
    index_path = os.path.join(d, 'index.json')
    ij = json.load(open(index_path, encoding='utf-8'))
    jf = ij.get('juan_files') or sorted(
        os.path.relpath(f, d) for f in glob.glob(os.path.join(d, 'juan', '*.json')))
    texts = [os.path.relpath(f, d) for f in glob.glob(os.path.join(d, 'text', '*.md'))]
    if not texts:
        # 09-30 勘查：65 部裡有 3 部（如 d59f2mua7w8y）根本沒有 text/ 目錄——
        # 結構化內容全在 juan/*.json 的 sections 裡，沒有對應的 md 正文。這不
        # 是「配不上」，是這部書本來就沒有 md 層，呼叫端要按 json-only 處理，
        # 不要當成 unmatched 報出來。用專門的返回值區分。
        return {}, {}, None, []
    stems = {}
    for t in texts:
        stems.setdefault(_norm_stem(os.path.splitext(os.path.basename(t))[0]), t)

    matches = {}
    used = set()
    unmatched = []
    for i, j in enumerate(jf, 1):
        try:
            jj = json.load(open(os.path.join(d, j), encoding='utf-8'))
        except Exception:
            unmatched.append(j)
            continue
        title = jj.get('title', '')
        source_juan = jj.get('source_juan', '')
        cands = [title, source_juan]

        # 數字候選：第一順位沿用 juan_text_match.py 原規則——用 juan json 自己
        # 檔名裡的數字 n（如 `juan/005.json` -> 5；本倉 juan_files 幾乎都是
        # 001.json…順排，n 因此多半等於物理位置）。這是本倉目前已驗證能配上
        # 1,635/1,735 卷的機制，不能丟：比如 d59dh3vo9af4 位置 5–8，標題寫的是
        # 「卷001」–「卷004」（因前面 4 個「卷首」而有 4 的位移），但實際該配
        # 的是 juan005.md–juan008.md——這裡必須用檔名數字 n=5..8，用標題數字
        # 1..4 反而会配错。
        # 擴充 A/B 與原規則合併成同一套「給定數字 → 展開所有檔名樣式」模板，
        # 對兩個候選數字都跑一遍，按優先序放進 cands：
        #   n  —— juan json 自己檔名裡的數字（如 `juan/005.json` -> 5；本倉
        #         juan_files 幾乎都是 001.json…順排，n 因此多半等於物理位
        #         置）。這是本倉目前已驗證能配上 1,635/1,735 卷的機制，優先
        #         試它：比如 d59dh3vo9af4 位置 5–8，標題寫的是「卷001」–
        #         「卷004」（前面 4 個「卷首」造成 4 的位移），但實際該配的
        #         是 juan005.md–juan008.md，必須用檔名數字 n=5..8，標題數字
        #         1..4 反而會配錯，所以 n 必須排第一順位。
        #   n2 —— 標題/source_juan 裡夾的數字（阿拉伯或中文數字），給「第89
        #         冊」「49冊[親軍衛]」「卷四十七」一類標題數字與實際卷序一
        #         致、但 json 檔名編號規律不同的書用，n 配不上才輪到它。
        def _num_templates(num):
            out = [f'juan_{num:02d}', f'juan_{num:03d}', f'juan{num}', f'juan_{num}',
                   f'卷{num:02d}', f'卷{num:03d}', f'卷{num}',
                   f'{num}册', f'{num:02d}册', f'{num:03d}册', f'第{num}册']
            if cn_juan(num):
                out += ['卷' + cn_juan(num), '卷之' + cn_juan(num)]
            return out

        m = re.search(r'\d+', os.path.basename(j))
        n = int(m.group()) if m else i
        cands += _num_templates(n)
        n2 = _extract_num(title, source_juan)
        if n2 is not None and n2 != n:
            cands += _num_templates(n2)
        # 擴充 C：別名表（目前只有「附錄」一項，標題本身没有数字可提取）
        for key_text in (title, source_juan):
            if key_text and key_text.strip() in TITLE_ALIAS_STEM:
                cands.append(TITLE_ALIAS_STEM[key_text.strip()])

        hit = None
        for c in cands:
            c = _norm_stem(c)
            if c and c in stems and stems[c] not in used:
                hit = stems[c]
                break
        if not hit:
            for c in (title, source_juan):
                c = _norm_stem(c)
                if c:
                    hs = [t for s, t in stems.items()
                          if t not in used and (s.endswith(c) or (c.endswith(s) and len(s) > 1))]
                    if len(hs) == 1:
                        hit = hs[0]
                        break
        if hit:
            matches[j] = hit
            used.add(hit)
        else:
            unmatched.append(j)

    # 擴充 D：兜底——若該書「未配上的卷」與「未被認領的 text」都恰好只剩 1 個
    leftover_texts = [t for t in texts if t not in used]
    fallback_pairs = {}
    if len(unmatched) == 1 and len(leftover_texts) == 1:
        fallback_pairs[unmatched[0]] = leftover_texts[0]
        used.add(leftover_texts[0])
        unmatched = []

    leftover_texts = [t for t in texts if t not in used]
    return matches, fallback_pairs, unmatched, leftover_texts


# ───────────────────────── manifest / index 資料結構 ─────────────────────────

class Version:
    def __init__(self, key, kind, source, source_name, source_url, license_, quality,
                 label, chapters_total, chapter_specs, extra_files, index_extra,
                 old_ref, is_default=False):
        self.key = key
        self.kind = kind  # 'collated' | 'transcription'
        self.source = source
        self.source_name = source_name
        self.source_url = source_url
        self.license = license_
        self.quality = quality
        self.label = label
        self.chapters_total = chapters_total
        self.chapter_specs = chapter_specs  # [(n, title, src_md_abspath, src_json_abspath_or_None)]
        self.extra_files = extra_files      # [(src_abspath, dst_relname)]
        self.index_extra = index_extra      # dict, 併入 <key>/index.json
        self.old_ref = old_ref              # 供 TSV 用
        self.is_default = is_default

    def manifest_entry(self):
        return {
            'key': self.key,
            'kind': self.kind,
            'label': self.label,
            'source': self.source,
            'source_name': self.source_name,
            'source_url': self.source_url,
            'license': self.license,
            'quality': self.quality,
            'chapters_total': self.chapters_total,
        }


class Owner:
    def __init__(self, owner_type, owner_id):
        self.owner_type = owner_type
        self.owner_id = owner_id
        self.versions = []  # Version 列表，[0] 必為 default
        self.warnings = []  # 掃描中發現的與規格描述不符之處，逐條記錄供統計輸出


# ───────────────────────── 掃描：整理本 ──────────────────────────────────────

# 历史常量：09-30 一次性迁移时的口径。2026-10-06 起整理本的来源/许可以各条目 manifest 为准（见 阅读文本.md §三），
# 不要用本常量重新生成。
COLLATED_CONST = {
    'source_name': '開源古籍',
    'source_url': None,
    'license': 'CC0 1.0',  # 本項目自行整理之文本 CC0（book-text README「授權」，用戶 09-27 定）
}


def scan_collated(root, owner_type, owner_id, coll_dir, warnings):
    index_path = os.path.join(coll_dir, 'index.json')
    ij = json.load(open(index_path, encoding='utf-8'))
    jf = ij.get('juan_files') or sorted(
        os.path.relpath(f, coll_dir) for f in glob.glob(os.path.join(coll_dir, 'juan', '*.json')))

    matches, fallback, unmatched, leftover = match_collated_texts(coll_dir)
    all_matches = dict(matches)
    all_matches.update(fallback)
    json_only = unmatched is None  # 該書根本沒有 text/ 目錄

    if json_only:
        warnings.append(('collated_json_only', owner_id, f'{len(jf)} 卷全部只有 json，無 text/ 目錄'))
    else:
        for j in unmatched:
            warnings.append(('juan_unmatched', owner_id, j))
        for j, t in fallback.items():
            warnings.append(('juan_fallback_pair', owner_id, f'{j} -> {t}'))

    chapter_specs = []
    for n, j in enumerate(jf, 1):
        jpath = os.path.join(coll_dir, j)
        try:
            jj = json.load(open(jpath, encoding='utf-8'))
        except Exception:
            jj = {}
        title = jj.get('title') or jj.get('source_juan') or f'卷{n}'
        md_rel = all_matches.get(j)
        md_abs = os.path.join(coll_dir, md_rel) if md_rel else None
        chapter_specs.append((n, title, md_abs, jpath if os.path.exists(jpath) else None))

    # 整理本裡另附的檔案：text/ 下未被任何卷認領的 md（leftover），加上
    # collated_edition/ 根目錄下除 index.json、juan/、text/、text_*/ 之外的其他
    # 檔案（如 juan_groups.json、校勘記.md）。text_*/ 屬「隱藏第二版本」，另外
    # 單獨當一份版本處理，不算在這裡的附加檔案內。
    extra_files = []
    for t in leftover:
        extra_files.append((os.path.join(coll_dir, t), os.path.join('extra', t)))
        warnings.append(('extra_file', owner_id, t))
    for name in sorted(os.listdir(coll_dir)):
        p = os.path.join(coll_dir, name)
        if name in ('index.json', 'juan', 'text'):
            continue
        if name.startswith('text_'):
            continue  # 隱藏版本，另行處理
        if os.path.isdir(p):
            for f in sorted(glob.glob(os.path.join(p, '**', '*'), recursive=True)):
                if os.path.isfile(f):
                    rel = os.path.join('extra', os.path.relpath(f, coll_dir))
                    extra_files.append((f, rel))
        else:
            extra_files.append((p, os.path.join('extra', name)))

    tq = ij.get('text_quality')
    quality = tq.get('grade') if isinstance(tq, dict) else None

    src_name = COLLATED_CONST['source_name']
    src_url = COLLATED_CONST['source_url']
    lic = COLLATED_CONST['license']
    # 09-30 勘查：65 部裡僅 1 部（d59f2mua7w8y）index.json 有顯式 `source` 欄，
    # 但那是「kind/note」說明（底本來源敘述），不是版權信息，不能當 license 用
    # ——見卡 #309 附「我已勘查到的真實數據坑」第 1 條。這裡按規則不採用它覆蓋
    # license/source_name/source_url 常量，但把它原樣記進 index_extra，並在
    # warnings 裡點名，供人複核（萬一將來哪部真給了合法 license 字段，統計會
    # 把它单列出来，不会被静默吞掉）。
    if isinstance(ij.get('source'), dict):
        s = ij['source']
        if any(k in s for k in ('license', 'source_name', 'source_url', 'name', 'url')):
            warnings.append(('collated_has_source_field', owner_id, json.dumps(s, ensure_ascii=False)))

    index_extra = {}
    for k in ('type', 'total_entries', 'matched_entries', 'total_records', 'compiler',
              'edition', 'source_text', 'daxu', 'coverage', 'revision', 'revised_at',
              'references', 'juan_groups', 'juan_metadata', '_note', '_pending_note',
              '_emend_note', '_l2_note', '_match_note', '_text_note'):
        if k in ij:
            index_extra[k] = ij[k]

    label = SOURCE_KEY['collated'][1]
    v = Version(
        key=None, kind='collated', source='collated',
        source_name=src_name, source_url=src_url, license_=lic, quality=quality,
        label=label, chapters_total=len(chapter_specs), chapter_specs=chapter_specs,
        extra_files=extra_files, index_extra=index_extra,
        old_ref={'style': 'collated', 'owner_type': owner_type},
    )
    return v


def scan_hidden_versions(owner_id, coll_dir, warnings):
    """collated_edition/ 下除 text/ 外的 text_* 目錄——「整理本裡藏的第二版
    本」。全倉目前只掃到一份（千頃堂書目 text_適園叢書本/），按 HIDDEN_VERSION_SLUG
    給 key，若出現表裡沒有的新目錄名，退化為 slugify 並在 warnings 裡點名，
    絕不自作主張定規則。"""
    out = []
    for name in sorted(os.listdir(coll_dir)):
        if not name.startswith('text_'):
            continue
        p = os.path.join(coll_dir, name)
        if not os.path.isdir(p):
            continue
        label_src = name[len('text_'):]
        slug = HIDDEN_VERSION_SLUG.get(label_src)
        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', label_src.lower()).strip('-') or 'hidden'
            warnings.append(('hidden_version_unmapped_slug', owner_id, f'{name} -> {slug}（未登記，請人工核對）'))
        else:
            warnings.append(('hidden_version_found', owner_id, f'{name} -> key={slug}'))
        md_files = sorted(glob.glob(os.path.join(p, '*.md')))
        chapter_specs = [(i, os.path.splitext(os.path.basename(f))[0], f, None)
                          for i, f in enumerate(md_files, 1)]
        out.append((slug, HIDDEN_VERSION_LABEL.get(label_src, label_src), chapter_specs, name))
    return out


# ───────────────────────── 掃描：全文（Work / Book）───────────────────────────

def _dirkey_to_source_key(dirname):
    """`wikisource-01` -> ('wikisource', 1)；`kanripo-01` -> ('kanripo', 1)。"""
    m = re.match(r'^([a-z]+)-(\d+)$', dirname)
    if not m:
        return None, None
    base, seq = m.group(1), int(m.group(2))
    return DIRNAME_PREFIX_TO_KEY.get(base, base), seq


def _seq_to_key(base, seq):
    """wikisource-01 -> wikisource；wikisource-02 -> wikisource-2（規格 §二）。"""
    if seq <= 1:
        return base
    return f'{base}-{seq}'


def scan_full_text_dir(ft_dir, owner_type, owner_id, dir_key, warnings):
    """`ft_dir` 是某一份全文的目錄（Work 有 key 子層、Book 沒有，呼叫端負責傳入
    正確的 ft_dir；dir_key 是磁盤目錄名，Book 傳 None）。"""
    index_path = os.path.join(ft_dir, 'index.json')
    ij = json.load(open(index_path, encoding='utf-8'))
    src = ij.get('source') or {}
    tq = ij.get('text_quality')
    quality = tq.get('grade') if isinstance(tq, dict) else ij.get('grade')

    if dir_key:
        base, seq = _dirkey_to_source_key(dir_key)
        if base is None:
            base, seq = dir_key, 1
            warnings.append(('full_text_dirname_unrecognized', owner_id, dir_key))
        key_base = base
        seq_n = seq
    else:
        # Book：無目錄 key 層，从 source.name 猜
        name = str(src.get('name', ''))
        key_base = SOURCE_NAME_TO_KEY.get(name)
        if not key_base:
            key_base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'source'
            warnings.append(('book_source_name_unmapped', owner_id, f'{name!r} -> key={key_base}（未登記，請人工核對）'))
        seq_n = 1

    chapters = ij.get('chapters') or []
    chapter_specs = []
    for ch in chapters:
        n = ch.get('n')
        fname = ch.get('file')
        title = ch.get('title')
        md_abs = os.path.join(ft_dir, fname) if fname else None
        chapter_specs.append((n, title, md_abs, None))
    chapter_specs.sort(key=lambda t: (t[0] if t[0] is not None else 0))

    extra_files = []
    chapter_basenames = {os.path.basename(c[2]) for c in chapter_specs if c[2]}
    for f in sorted(glob.glob(os.path.join(ft_dir, '*'))):
        bn = os.path.basename(f)
        if bn in ('index.json',) or bn in chapter_basenames:
            continue
        if os.path.isfile(f):
            extra_files.append((f, bn))

    label = SOURCE_KEY.get(key_base, (key_base, key_base))[1]
    index_extra = {}
    if 'other_sources' in ij:
        index_extra['other_sources'] = ij['other_sources']
    for k in ('version_label', 'edition_note', 'fetched_at', 'scraped_at', 'guji_markdown',
              'line_is_column', 'fetch_stats', 'revision', 'work_id', 'book_id'):
        if k in ij:
            index_extra[k] = ij[k]

    v = Version(
        key=None, kind='transcription', source=key_base,
        source_name=src.get('name'), source_url=src.get('url'),
        license_=src.get('license'), quality=quality, label=label,
        chapters_total=ij.get('total_chapters') if ij.get('total_chapters') is not None else len(chapter_specs),
        chapter_specs=chapter_specs, extra_files=extra_files, index_extra=index_extra,
        old_ref={'style': 'fulltext', 'owner_type': owner_type,
                 'old_key': dir_key or 'book', 'key_base': key_base, 'seq': seq_n},
    )
    return v


# ───────────────────────── 掃描：一個 owner（Work 或 Book）的全部版本 ─────────

def scan_owner(root, owner_type, owner_id, owner_dir, warnings):
    o = Owner(owner_type, owner_id)
    versions = []

    coll_dir = os.path.join(owner_dir, 'collated_edition')
    has_collated = os.path.isdir(coll_dir)
    if has_collated:
        v = scan_collated(root, owner_type, owner_id, coll_dir, warnings)
        versions.append(v)
        for slug, label, chapter_specs, srcname in scan_hidden_versions(owner_id, coll_dir, warnings):
            hv = Version(
                key=None, kind='transcription', source=slug,
                source_name=label, source_url=None, license_=None, quality=None,
                label=label, chapters_total=len(chapter_specs), chapter_specs=chapter_specs,
                extra_files=[], index_extra={'hidden_from': srcname},
                old_ref={'style': 'hidden_collated_text', 'owner_type': owner_type, 'dirname': srcname},
            )
            versions.append(hv)

    ft_root = os.path.join(owner_dir, 'full_text')
    if os.path.isdir(ft_root):
        sub_keydirs = [p for p in sorted(glob.glob(os.path.join(ft_root, '*'))) if os.path.isdir(p)]
        has_key_layer = any(os.path.exists(os.path.join(p, 'index.json')) for p in sub_keydirs)
        if has_key_layer:
            for p in sub_keydirs:
                if not os.path.exists(os.path.join(p, 'index.json')):
                    continue
                v = scan_full_text_dir(p, owner_type, owner_id, os.path.basename(p), warnings)
                versions.append(v)
        elif os.path.exists(os.path.join(ft_root, 'index.json')):
            v = scan_full_text_dir(ft_root, owner_type, owner_id, None, warnings)
            versions.append(v)

    if not versions:
        return None

    # ── 選 default（用戶 09-30 在 #307 定）：整理本 → 維基 → Kanripo → 識典；
    #    章數只在同一來源內部比（多的優先），再不然按 key 字典序（穩定）。──
    collated_versions = [v for v in versions if v.source == 'collated']
    if collated_versions:
        default_v = collated_versions[0]
    else:
        def rank(v):
            return (source_priority(v.source), -(v.chapters_total or 0), v.source)
        default_v = sorted(versions, key=rank)[0]
    default_v.is_default = True

    # ── key 指派：default -> 'default'；其餘按來源 + 序號表；隱藏版本已在掃描
    #    時給了 slug，這裡只需做保留字/撞名檢查。──
    used_keys = {'default'}
    for v in versions:
        if v is default_v:
            v.key = 'default'
            continue
        if v.kind == 'collated':
            base_key = 'collated'
        elif v.old_ref.get('style') == 'hidden_collated_text':
            base_key = v.source
        else:
            base_key = _seq_to_key(v.old_ref['key_base'], v.old_ref['seq'])
        key = base_key
        n = 2
        while key in used_keys or key in RESERVED_KEYS:
            warnings.append(('key_conflict', owner_id, f'{base_key} 已被佔用，改用 {base_key}-{n}'))
            key = f'{base_key}-{n}'
            n += 1
        v.key = key
        used_keys.add(key)

    versions.sort(key=lambda v: (not v.is_default, v.key))
    o.versions = versions
    o.warnings = warnings
    return o


# ───────────────────────── 全量掃描 ──────────────────────────────────────────

def iter_owner_dirs(root, owner_type):
    for p in sorted(glob.glob(os.path.join(root, owner_type, '*', '*', '*', '*'))):
        if os.path.isdir(p):
            yield os.path.basename(p), p


def scan_all(root):
    owners = []
    all_warnings = []
    for owner_type in ('Work', 'Book'):
        base = os.path.join(root, owner_type)
        if not os.path.isdir(base):
            continue
        for owner_id, owner_dir in iter_owner_dirs(root, owner_type):
            has_coll = os.path.isdir(os.path.join(owner_dir, 'collated_edition'))
            has_ft = os.path.isdir(os.path.join(owner_dir, 'full_text'))
            if not has_coll and not has_ft:
                continue
            w = []
            o = scan_owner(root, owner_type, owner_id, owner_dir, w)
            all_warnings.extend(w)
            if o:
                owners.append(o)
    return owners, all_warnings


# ───────────────────────── 舊 full_text primary（供對照）─────────────────────

def compute_old_primaries(root):
    """照抄 build_index.py 的 full_text primary 演算法，只用來跟新 default 對照，
    不作其他用途；算法有變動要去改 build_index.py 再搬過來。"""
    ft = {}

    def add(owner, key, idx):
        d = json.load(open(idx, encoding='utf-8'))
        tq = d.get('text_quality') or {}
        src = d.get('source') or {}
        ft.setdefault(owner, []).append({
            'key': key,
            'grade': tq.get('grade') if isinstance(tq, dict) else None,
            'fetched_at': d.get('fetched_at') or d.get('scraped_at'),
            '_explicit': bool(d.get('primary')),
            '_src_rank': _src_rank(src),
            'total_chapters': d.get('total_chapters'),
        })

    for idx in sorted(glob.glob(os.path.join(root, 'Book', '*', '*', '*', '*', 'full_text', 'index.json'))):
        add(os.path.basename(os.path.dirname(os.path.dirname(idx))), 'book', idx)
    for idx in sorted(glob.glob(os.path.join(root, 'Work', '*', '*', '*', '*', 'full_text', '*', 'index.json'))):
        key = os.path.basename(os.path.dirname(idx))
        add(os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(idx)))), key, idx)

    primaries = {}
    for owner, lst in ft.items():
        best = sorted(lst, key=lambda e: (not e['_explicit'], GRADE_RANK.get(e['grade'], 9),
                                           e['_src_rank'],
                                           -int(str(e['fetched_at'] or '0').replace('-', '')[:8] or 0),
                                           e['key']))[0]
        primaries[owner] = {'key': best['key'], 'total_chapters': best['total_chapters']}
    return primaries


# ───────────────────────── 輸出：manifest / index / chapters ─────────────────

def _copy_or_record(actions, src_abs, dst_abs):
    actions.append((src_abs, dst_abs))


def build_apply_plan(owners):
    """回傳 (file_actions, manifests, version_indexes)：
      file_actions      [(src_abs, dst_abs), ...] 供 --apply 真的複製
      manifests          {owner_rel_dir: manifest_dict}
      version_indexes     {owner_rel_dir/key: index_dict}
    """
    file_actions = []
    manifests = {}
    version_indexes = {}
    for o in owners:
        owner_rel = owner_shard_dir(o.owner_type, o.owner_id)
        manifest = {'id': o.owner_id, 'versions': [v.manifest_entry() for v in o.versions]}
        manifests[owner_rel] = manifest
        for v in o.versions:
            chapters_meta = []
            for n, title, md_abs, json_abs in v.chapter_specs:
                fname = f'{n:03d}'
                if md_abs:
                    _copy_or_record(file_actions, md_abs, os.path.join(owner_rel, v.key, f'{fname}.md'))
                has_json = bool(json_abs)
                if json_abs:
                    _copy_or_record(file_actions, json_abs, os.path.join(owner_rel, v.key, f'{fname}.json'))
                chapters_meta.append({'n': n, 'file': fname, 'title': title, 'has_json': has_json})
            for src_abs, dst_rel in v.extra_files:
                _copy_or_record(file_actions, src_abs, os.path.join(owner_rel, v.key, dst_rel))
            idx = dict(v.index_extra)
            idx['chapters'] = chapters_meta
            version_indexes[os.path.join(owner_rel, v.key)] = idx
    return file_actions, manifests, version_indexes


def build_global_index(owners):
    buckets = {c: {} for c in '0123456789abcdef'}
    for o in owners:
        buckets[shard(o.owner_id)][o.owner_id] = [
            {'key': v.key, 'kind': v.kind, 'label': v.label, 'chapters_total': v.chapters_total}
            for v in o.versions
        ]
    return buckets


# ───────────────────────── TSV 對照表 ────────────────────────────────────────

def _old_full_style_key(key_base, seq):
    """full_text 舊 key 還原成磁碟原貌（wikisource-01／kanripo-01），供 TSV 的
    「舊 key」欄與規格 §六舊網址裡 `key=wikisource-01` 對齊。"""
    return f'{key_base}-{seq:02d}'


def build_tsv_rows(owners):
    rows = []  # (old_path, old_key, new_path, new_key, is_default)
    header = ['old_path', 'old_key', 'new_path', 'new_key', 'is_default']
    for o in owners:
        oid = o.owner_id
        for v in o.versions:
            is_default = 'yes' if v.is_default else 'no'
            new_key_seg = '' if v.is_default else f'/{v.key}'
            for n, title, md_abs, json_abs in v.chapter_specs:
                new_juan = f'{n:03d}'
                new_path = f'/read/{oid}{new_key_seg}/{new_juan}'
                if v.old_ref['style'] == 'collated':
                    old_juan = f'{n:03d}'
                    old_key = 'collated'
                    rows.append([f'item/{oid}/read?kind=collated&juan={old_juan}', old_key,
                                 new_path, v.key, is_default])
                    rows.append([f'item/{oid}/read?kind=collated&juan=juan/{old_juan}.json', old_key,
                                 new_path, v.key, is_default])
                elif v.old_ref['style'] == 'fulltext':
                    old_key = _old_full_style_key(v.old_ref['key_base'], v.old_ref['seq'])
                    if o.owner_type == 'Book':
                        rows.append([f'item/{oid}/read?kind=fulltext&juan={n}', 'book',
                                     new_path, v.key, is_default])
                    else:
                        rows.append([f'item/{oid}/read?kind=fulltext&key={old_key}&juan={n}', old_key,
                                     new_path, v.key, is_default])
                elif v.old_ref['style'] == 'hidden_collated_text':
                    # 舊結構裡這份根本沒有可定址的舊網址（藏在 collated_edition 內
                    # 部，從未被索引/路由過），沒有「舊路徑」可填，只登記新路徑，
                    # 舊路徑欄留空並註明原始檔案位置，供人核對。
                    rows.append([f'(未曾路由；原檔 {v.old_ref["dirname"]}/{os.path.basename(md_abs)})',
                                 '', new_path, v.key, is_default])
    return header, rows


# ───────────────────────── 統計 ──────────────────────────────────────────────

def build_stats(owners, warnings, old_primaries=None):
    old_primaries = old_primaries or {}
    n_owners = len(owners)
    n_versions = sum(len(o.versions) for o in owners)
    default_by_source = defaultdict(int)
    for o in owners:
        default_by_source[o.versions[0].source] += 1

    mismatches = []
    for o in owners:
        if o.owner_type == 'Book':
            # Book 的舊 full_text 從來只有一份（key 字面上固定寫 'book'，不是
            # 真正的多候選裡選出來的），跟新 default 比較沒有意義，只會比出
            # 字面上的 key 命名規則差異（'book' vs 'wikisource-01' 這種），不
            # 是真的「選擇不同」——不拿來湊 mismatch 清單。
            continue
        old = old_primaries.get(o.owner_id)
        if old is None:
            continue
        new_default = o.versions[0]
        new_old_style = None
        if new_default.old_ref['style'] == 'fulltext':
            new_old_style = _old_full_style_key(new_default.old_ref['key_base'], new_default.old_ref['seq'])
        elif new_default.old_ref['style'] == 'collated':
            new_old_style = None  # 整理本從未進過舊 full_text primary 的候選集合
        if new_old_style != old['key']:
            if new_default.source == 'collated':
                reason = '新規則：有整理本優先取整理本'
            else:
                old_n = old.get('total_chapters')
                new_n = new_default.chapters_total
                if old_n is not None and new_n is not None and new_n > old_n:
                    reason = f'新規則：章數最多者為 default（新 {new_n} 章 > 舊 primary {old_n} 章）'
                elif old_n is not None and new_n is not None and old_n == new_n:
                    reason = f'章數相同（{new_n} 章）：舊算法按來源優先序（自校>維基>其他）選，新規則只在「章數平手」時維基優先 Kanripo，兩者對這部書打平的方向不同'
                else:
                    reason = f'評分/排序細節差異（舊 {old_n} 章 vs 新 {new_n} 章）'
            mismatches.append((o.owner_id, old['key'], new_default.key, reason))

    unmatched = [w for w in warnings if w[0] == 'juan_unmatched']
    fallback = [w for w in warnings if w[0] == 'juan_fallback_pair']
    hidden = [w for w in warnings if w[0] in ('hidden_version_found', 'hidden_version_unmapped_slug')]
    key_conflicts = [w for w in warnings if w[0] == 'key_conflict']
    source_field_hits = [w for w in warnings if w[0] == 'collated_has_source_field']
    unmapped_book_src = [w for w in warnings if w[0] == 'book_source_name_unmapped']

    return {
        'n_owners': n_owners,
        'n_versions': n_versions,
        'default_by_source': dict(default_by_source),
        'primary_mismatches': mismatches,
        'juan_unmatched': unmatched,
        'juan_fallback_pairs': fallback,
        'hidden_versions': hidden,
        'key_conflicts': key_conflicts,
        'collated_source_field_hits': source_field_hits,
        'book_source_unmapped': unmapped_book_src,
    }


def write_stats_md(path, stats, label):
    lines = [f'# {label} 迁移干跑统计（脚本 migrate_texts.py，卡 #309）', '']
    lines.append(f'- 条目数（owner）：{stats["n_owners"]}')
    lines.append(f'- 版本数（version，含 default）：{stats["n_versions"]}')
    lines.append('- default 按来源分：')
    for k, v in sorted(stats['default_by_source'].items()):
        label2 = SOURCE_KEY.get(k, (k, k))[1]
        lines.append(f'  - {k}（{label2}）：{v} 部')
    lines.append(f'- default 与原 primary 不一致：{len(stats["primary_mismatches"])} 部（分类计数见下，逐部清单见文末）')
    reason_counter = defaultdict(int)
    for _, _, _, reason in stats['primary_mismatches']:
        reason_counter[reason.split('（')[0]] += 1
    for r, n in sorted(reason_counter.items(), key=lambda kv: -kv[1]):
        lines.append(f'  - {r}：{n} 部')
    lines.append('')
    lines.append('### default 与原 primary 不一致逐部清单')
    for oid, old, newkey, reason in stats['primary_mismatches']:
        lines.append(f'  - {oid}：旧 primary={old} → 新 default key={newkey}（{reason}）')
    lines.append(f'- 配不上的卷（应为 0）：{len(stats["juan_unmatched"])}')
    for _, oid, detail in stats['juan_unmatched']:
        lines.append(f'  - {oid}: {detail}')
    lines.append(f'- 兜底配对（仅存量 1:1 时才配，供复核）：{len(stats["juan_fallback_pairs"])}')
    for _, oid, detail in stats['juan_fallback_pairs']:
        lines.append(f'  - {oid}: {detail}')
    lines.append(f'- 隐藏版本：{len(stats["hidden_versions"])}')
    for _, oid, detail in stats['hidden_versions']:
        lines.append(f'  - {oid}: {detail}')
    lines.append(f'- key 冲突：{len(stats["key_conflicts"])}')
    for _, oid, detail in stats['key_conflicts']:
        lines.append(f'  - {oid}: {detail}')
    if stats['collated_source_field_hits']:
        lines.append(f'- 整理本 index.json 里带 source/license 相关字段的（人工核对用，未静默采用）：'
                      f'{len(stats["collated_source_field_hits"])}')
        for _, oid, detail in stats['collated_source_field_hits']:
            lines.append(f'  - {oid}: {detail}')
    if stats['book_source_unmapped']:
        lines.append(f'- Book 全文来源名未登记在映射表里（退化 slug，人工核对）：'
                      f'{len(stats["book_source_unmapped"])}')
        for _, oid, detail in stats['book_source_unmapped']:
            lines.append(f'  - {oid}: {detail}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def write_samples_md(path, owners, label):
    """抽样贴 manifest；私有仓调用时只贴元信息，不带正文内容。"""
    by_id = {o.owner_id: o for o in owners}
    picks = []

    def find(pred):
        for o in owners:
            if pred(o):
                return o
        return None

    single = find(lambda o: len(o.versions) == 1)
    double = find(lambda o: len(o.versions) == 2 and all(v.kind == 'transcription' for v in o.versions))
    coll_plus_ft = find(lambda o: any(v.kind == 'collated' for v in o.versions) and len(o.versions) > 1)
    book_ft = find(lambda o: o.owner_type == 'Book')
    hidden = find(lambda o: any(v.old_ref.get('style') == 'hidden_collated_text' for v in o.versions))

    lines = [f'# {label} manifest 样例（卡 #309 干跑）', '']
    for tag, o in [('单一份全文', single), ('维基＋Kanripo双份', double),
                   ('整理本＋全文', coll_plus_ft), ('Book 全文', book_ft),
                   ('带隐藏版本', hidden)]:
        lines.append(f'## {tag}')
        if o is None:
            lines.append('（全仓扫描未发现实例）')
            lines.append('')
            continue
        manifest = {'id': o.owner_id, 'versions': [v.manifest_entry() for v in o.versions]}
        lines.append(f'`{o.owner_id}`（{o.owner_type}）')
        lines.append('```json')
        lines.append(json.dumps(manifest, ensure_ascii=False, indent=2))
        lines.append('```')
        lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def write_tsv(path, header, rows):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\t'.join(header) + '\n')
        for r in rows:
            f.write('\t'.join(str(x) for x in r) + '\n')


# ───────────────────────── --apply：真的落地到 --out ─────────────────────────

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def do_apply(root, out_dir, owners):
    root_abs = os.path.abspath(root)
    out_abs = os.path.abspath(out_dir)
    if out_abs == root_abs or out_abs.startswith(root_abs + os.sep) or root_abs.startswith(out_abs + os.sep):
        raise SystemExit(f'--apply 的 --out 不能与 --root 相同或互相包含：{out_abs} vs {root_abs}')

    file_actions, manifests, version_indexes = build_apply_plan(owners)
    for src_abs, dst_rel in file_actions:
        dst_abs = os.path.join(out_dir, dst_rel)
        os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
        shutil.copyfile(src_abs, dst_abs)
    for owner_rel, manifest in manifests.items():
        write_json(os.path.join(out_dir, owner_rel, 'manifest.json'), manifest)
    for key_dir, idx in version_indexes.items():
        write_json(os.path.join(out_dir, key_dir, 'index.json'), idx)

    global_index = build_global_index(owners)
    for s, bucket in global_index.items():
        write_json(os.path.join(out_dir, 'index', 'texts', f'{s}.json'), bucket)

    return file_actions, manifests, version_indexes


# ───────────────────────── --verify：字节/计数自检 ───────────────────────────

def _md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def do_verify(root, out_dir, owners):
    file_actions, manifests, version_indexes = build_apply_plan(owners)
    problems = []
    n_checked = 0
    for src_abs, dst_rel in file_actions:
        dst_abs = os.path.join(out_dir, dst_rel)
        if not os.path.exists(dst_abs):
            problems.append(f'缺失：{dst_rel}')
            continue
        if dst_rel.endswith('.md'):
            if _md5(src_abs) != _md5(dst_abs):
                problems.append(f'md 字节不一致：{dst_rel}')
        n_checked += 1
    total_src_files = count_source_files(owners)
    total_dst_files = count_apply_output_files(out_dir)
    # 預期落地檔案數：章檔/附加檔（file_actions）+ 每個 owner 一份 manifest.json
    # + 每個版本一份 index.json + 全域索引固定 16 個分片檔（index/texts/{0-f}.json，
    # 16 進位分片，恆為 16 份，與 owners 是否覆蓋到每一格無關）。
    expected_dst_files = len(file_actions) + len(manifests) + len(version_indexes) + 16
    if total_dst_files != expected_dst_files:
        problems.append(f'落地檔案總數對不上：實際 {total_dst_files}，預期 {expected_dst_files}')
    if total_src_files != len(file_actions):
        problems.append(f'來源檔案計數對不上：count_source_files={total_src_files}，file_actions={len(file_actions)}')
    return {
        'files_checked': n_checked,
        'problems': problems,
        'source_files_considered': total_src_files,
        'dest_files_written': total_dst_files,
    }


def count_source_files(owners):
    n = 0
    for o in owners:
        for v in o.versions:
            n += sum(1 for _, _, md, js in v.chapter_specs if md)
            n += sum(1 for _, _, md, js in v.chapter_specs if js)
            n += len(v.extra_files)
    return n


def count_apply_output_files(out_dir):
    n = 0
    for _, _, files in os.walk(out_dir):
        n += len(files)
    return n


# ───────────────────────── main ──────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', help='book-text（或 book-text-private）仓根目录')
    ap.add_argument('--out', help='产物输出目录（干跑：对照表/统计；--apply：新结构落地目录）')
    ap.add_argument('--dry-run', action='store_true', help='只扫描 + 出对照表/统计，不写任何数据文件（默认）')
    ap.add_argument('--apply', action='store_true', help='把新结构真的落地到 --out（禁止等于或包含 --root）')
    ap.add_argument('--verify', action='store_true', help='核对一次 --apply 产物：md 字节不变、文件数守恒')
    ap.add_argument('--label', default='book-text', help='统计文件标题用的仓名（如 book-text-private）')
    ap.add_argument('--private', action='store_true', help='私有仓模式：样例文件不出现正文内容')
    A = ap.parse_args()

    if not A.root:
        ap.error('需要 --root')
    root = A.root.rstrip('/')

    owners, warnings = scan_all(root)
    if not owners:
        print('扫描结果为空，检查 --root 是否正确', file=sys.stderr)

    if A.apply:
        if not A.out:
            ap.error('--apply 需要 --out')
        file_actions, manifests, version_indexes = do_apply(root, A.out, owners)
        print(f'--apply 完成：{len(owners)} 个 owner，{len(file_actions)} 个文件，'
              f'{len(manifests)} 份 manifest，{len(version_indexes)} 份 version index')
        if A.verify:
            result = do_verify(root, A.out, owners)
            print(f'--verify：checked={result["files_checked"]} '
                  f'source_files={result["source_files_considered"]} '
                  f'dest_files={result["dest_files_written"]} '
                  f'problems={len(result["problems"])}')
            for p in result['problems'][:50]:
                print('  ', p)
        return

    # --dry-run（默认）
    if not A.out:
        ap.error('--dry-run 需要 --out')
    os.makedirs(A.out, exist_ok=True)
    old_primaries = compute_old_primaries(root)
    stats = build_stats(owners, warnings, old_primaries)
    header, rows = build_tsv_rows(owners)

    suffix = '-private' if A.private else ''
    write_tsv(os.path.join(A.out, f'texts-migration{suffix}-map.tsv'), header, rows)
    write_stats_md(os.path.join(A.out, f'texts-migration{suffix}-stats.md'), stats, A.label)
    if not A.private:
        write_samples_md(os.path.join(A.out, 'texts-migration-samples.md'), owners, A.label)

    print(f'owners={stats["n_owners"]} versions={stats["n_versions"]} '
          f'unmatched_juan={len(stats["juan_unmatched"])} '
          f'fallback_pairs={len(stats["juan_fallback_pairs"])} '
          f'hidden_versions={len(stats["hidden_versions"])} '
          f'key_conflicts={len(stats["key_conflicts"])} '
          f'primary_mismatches={len(stats["primary_mismatches"])}')


if __name__ == '__main__':
    main()
