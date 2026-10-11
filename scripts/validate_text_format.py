#!/usr/bin/env python3
# 来源：open-guji-core/overview 的 项目进展/古籍文本/scripts/validate_text_format.py @ 9cd45542（复制进本仓；源头改后人工同步）
# -*- coding: utf-8 -*-
"""
book-text 文本格式校验器（T5 道，服务
项目进展/古籍文本/整体设计/2026-09-book-text格式规范.md；T6 道加基线机制）

按规范里的规则编号（F-CE-*／F-MD-*／F-FT-*／F-FR-*／F-SRC-*／F-ALL-*）逐条计数
不合规处。规则分两档：

  HARD（结构性缺陷，与「新入库/存量」无关，任何时候都不该有）
      —— --strict 时只看这一档，非 0 就退出码 1。
  SOFT（记法/风格类，存量按 09-14 裁决「不全面返工、逐本随整理自然转」，
        大量旧形态本来就该继续存在）
      —— 只报数，**不进 --strict 的失败条件**，否则 --strict 在这仓上
         永远不可能通过（比如夹注记法新旧四种并存是已知且允许的现状）。

这条 HARD/SOFT 划分本身写在规范 §七，不是本脚本自创。

结构（2026-09-30 起，#307；本脚本 10-02 按 #346 改认新结构）：
    <Work|Book>/<c1>/<c2>/<c3>/<id>/manifest.json   版本清单（versions[].key／kind）
    <id>/<key>/index.json ＋ NNN.md（整理本另有 NNN.json）   一个版本
    <id>/fragments/*.json                          辑佚
本脚本不再按目录名猜，而是读各条目的 manifest.json 找版本目录：kind=collated 的版本按「整理本」
规则（旧 collated_edition/）验，其余 kind 的版本按「全文」规则（旧 full_text/<key>/）验。
旧结构（collated_edition/、full_text/）不再识别；基线 key 也随之换成新路径，旧基线作废重建。

扫 0 档判失败（validate-collated.py 记过的坑：路径写死或写错时 glob 匹配
不到任何文件，脚本会安静地印出"全部合规"，跟真的全绿长得一模一样）：
本脚本按四类资产分别打印扫描档数，四类总和为 0 时退出码 2，不静默过关。

T6 道新增（存量基线，见 项目进展/总调度/古籍索引三块/任务书/T6-格式存量基线与清账.md）：
每条 HARD 违规按「文件路径＋序号（sections[] 则是 section 下标，其余规则是文件内
第几次命中）＋规则号」编一把 key。`--baseline` 指向的 json 冻结的就是这一整套 key。
    --baseline <json>                    读取该基线，配合 --strict 时只对不在基线里
                                          （新违规）的项计入失败；文件不存在时改为
                                          「冻结当前全部违规」写出该文件（初建基线）。
    --baseline <json> --update-baseline  收缩式刷新：现基线里「这次仍违规」的项保留，
                                          「这次已不违规」的项剔除；**不把新违规加进基线**
                                          （基线只减不增）。--path 限定时只动该范围内的
                                          basel key，范围外的原样保留。
    --path <某部书或某子树的目录>          只扫这棵子树（相对 root，或 root 下的绝对路径），
                                          key 仍按 root 算相对路径，基线可跨范围合用。

用法：
    python3 validate_text_format.py <book-text 根>
    python3 validate_text_format.py <book-text 根> --json out.json
    python3 validate_text_format.py <book-text 根> --strict   # CI 用：HARD 非 0 退出 1
    python3 validate_text_format.py <book-text 根> --path Work/x/x/x/<id> --strict
    python3 validate_text_format.py <book-text 根> --baseline format_baseline.json --strict
    python3 validate_text_format.py <book-text 根> --baseline format_baseline.json --update-baseline
    python3 validate_text_format.py --selftest                # 造坏样本自测，不需要仓
"""
import argparse
import collections
import datetime
import glob as _glob
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zi_convert import classify as _zi_classify  # noqa: E402 — 复用 T26 组字分类，见 F-MD-11
import original_version as OV  # noqa: E402 — original 三线版本号（T67 #400），见 F-OV-*

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

# ---------------------------------------------------------------------------
# 不生效区遮罩（与画像脚本、guji-markdown spec §0.1 同一口径）
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def mask_inert(text: str) -> str:
    def blank(m):
        return " " * len(m.group(0))

    text = _FENCE_RE.sub(blank, text)
    text = _COMMENT_RE.sub(blank, text)
    text = _INLINE_CODE_RE.sub(blank, text)
    return text


_ANGLE_JZ_RE = re.compile(r"⟨([^⟨⟩]*)⟩")
_HEX_RE = re.compile(r"〔([^〔〕]*)〕")
_WIDE_PAREN_RE = re.compile(r"（（(.*?)））", re.S)
_PAGE_COMMENT_RE = re.compile(r"<!--\s*p\d+\s*-->")

_T26_QW_RE = re.compile(r"\[\[[^\[\]]*\]\]")
_T26_QZ_RE = re.compile(r"□\{guess=[^\s{}]+\}")


def t26_new_syntax_counts(masked_text: str):
    """T26（guji-markdown 0.2.0）三条新语法的出现次数，仅统计、不判违规：
    阙文 `[[…]]`、缺字猜测 `□{guess=…}`、夹注内分行 `<a|b>`。
    分行计数认的是「`<…>` 夹注内容含字面 `|`」，转义 `\\|`（只在 `:::table`
    格内才需要转义，见 guji-markdown spec §1／§15）同样计入——渲染时它仍是
    分行点，统计口径与渲染行为一致。"""
    qw = len(_T26_QW_RE.findall(masked_text))
    qz = len(_T26_QZ_RE.findall(masked_text))
    jz_split = 0
    for line in masked_text.splitlines():
        i, L = 0, len(line)
        while i < L:
            if line[i] == "<":
                j = i + 1
                if j < L:
                    c = line[j]
                    if not (c.isascii() and (c.isalpha() or c in "/!?> \t")):
                        close = line.find(">", j)
                        if close != -1:
                            content = line[j:close]
                            if content.strip() and "|" in content:
                                jz_split += 1
                            i = close + 1
                            continue
            i += 1
    return {"阙文 [[…]]": qw, "缺字猜测 □{guess=…}": qz, "夹注分行 <a|b>": jz_split}


def spec_angle_jiazhu_count(masked_text: str):
    """guji-markdown spec §1 生效条件下真正的 <…> 夹注计数（按行）。"""
    n = 0
    for line in masked_text.splitlines():
        i, L = 0, len(line)
        while i < L:
            if line[i] == "<":
                j = i + 1
                if j < L:
                    c = line[j]
                    if not (c.isascii() and (c.isalpha() or c in "/!?> \t")):
                        close = line.find(">", j)
                        if close != -1 and line[j:close].strip():
                            n += 1
                            i = close + 1
                            continue
            i += 1
    return n


def iter_jz_spans(masked_text: str):
    """按 spec §1 生效条件逐一取出 <…> 夹注的内容，供 F-MD-11 复用（不只计数）。"""
    for line in masked_text.splitlines():
        i, L = 0, len(line)
        while i < L:
            if line[i] == "<":
                j = i + 1
                if j < L:
                    c = line[j]
                    if not (c.isascii() and (c.isalpha() or c in "/!?> \t")):
                        close = line.find(">", j)
                        if close != -1 and line[j:close].strip():
                            yield line[j:close]
                            i = close + 1
                            continue
            i += 1


def unclosed_hex_count(masked_text: str):
    """〔…〕同行未闭合处数（F-MD-03）：逐行数 〔 与 〕 是否配平。"""
    total = 0
    docs_hit = False
    for line in masked_text.splitlines():
        d = line.count("〔") - line.count("〕")
        if d != 0:
            total += abs(d)
            docs_hit = True
    return total, docs_hit


_DIRECTIVE_OPEN_RE = re.compile(r"^:::([\w-]+)")
_DIRECTIVE_CLOSE_RE = re.compile(r"^:::\s*$")
# render_notation() 单元格结尾后缀：可选 `{colspan}` 再可选 `^rowspan`；裸续格标记
# "^"（无数字）落进 body 分支，colspan 按默认值 1 处理——与 table_convert.py 的
# _token_colspan 同一条正则、同一个语义（T22，见 2026-09-表格记法方案.md §二）。
_TABLE_TOKEN_SUFFIX_RE = re.compile(r"^(?P<body>.*?)(?:\{(?P<colspan>\d+)\})?(?:\^(?P<rowspan>\d+))?$")


def _table_token_colspan(token):
    m = _TABLE_TOKEN_SUFFIX_RE.match(token)
    if m and m.group("colspan"):
        return int(m.group("colspan"))
    return 1


def _table_row_cols(line):
    s = line[1:] if line.startswith("!") else line
    sentinel = "\x01"
    tokens = s.replace("\\|", sentinel).split(" | ")
    return sum(_table_token_colspan(t.replace(sentinel, "\\|")) for t in tokens)


def scan_table_blocks(masked_text):
    """在已遮罩（code fence／HTML 注释／行内 code 已挖空）的文本里找 `:::table` 容器块
    （F-MD-09）。guji-markdown 容器块不嵌套（`:::tt`／`:::table` 现状用法一致）：
    一个 open 后，下一行裸 `:::` 就是它的 close；如果在关闭前又遇到另一个 open，
    判前一个未闭合。返回 (blocks, unclosed_count)；blocks 是 [(name='table' 的)
    (start_line_idx, end_line_idx, body_lines)]。"""
    lines = masked_text.splitlines()
    blocks = []
    unclosed = 0
    pending = None  # (name, start_idx)
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        om = _DIRECTIVE_OPEN_RE.match(line)
        cm = _DIRECTIVE_CLOSE_RE.match(line)
        if om:
            if pending is not None and pending[0] == "table":
                unclosed += 1
            pending = (om.group(1), i)
        elif cm and pending is not None:
            if pending[0] == "table":
                blocks.append((pending[1], i, lines[pending[1] + 1 : i]))
            pending = None
    if pending is not None and pending[0] == "table":
        unclosed += 1
    return blocks, unclosed


def check_table_block_cols(body_lines):
    """`:::table` 块内容行（不含 `:::table`/`:::` 本身）列数是否处处等于表头列数
    （展开 `{n}` colspan／`^` 续格之后）。返回 (header_cols, [(行下标, 实际列数), ...])。"""
    rows = [l for l in body_lines if l.strip() != ""]
    if not rows:
        return 0, []
    header_cols = _table_row_cols(rows[0])
    problems = [(ri, n) for ri, r in enumerate(rows) if (n := _table_row_cols(r)) != header_cols]
    return header_cols, problems


def jload(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:  # noqa: BLE001 — 校验器需要把任何解析失败都当一条违规上报
        return None, str(e)


# ---------------------------------------------------------------------------
# 各规则校验
# ---------------------------------------------------------------------------

# 新结构整理本版本 index.json 用 chapters[] 取代旧的 juan_files（章文件 NNN.json／NNN.md）
CE_REQUIRED_FIELDS = ["work_id", "total_entries", "chapters", "text_quality", "revision", "revised_at"]
# F-CE-03 裁决（文本总管 2026-09-26 09:1x）：新入库只许 5 正式值；placeholder 仅存量占位。
CE_TYPE_OFFICIAL = {"catalog", "anthology", "collated_edition", "kaozhen", "fragment_collection"}
CE_TYPE_KNOWN = CE_TYPE_OFFICIAL | {"placeholder"}
TQ_GRADE_KNOWN = {"rough", "fine", "ocr", "source", "placeholder", "none"}
# 全文 index.json 必填（09-26 文本总管按 E-11 修订）：公共键＋按层的归属键＋抓取时间二选一。
# 原表按旧 Book 全文写死 book_id／scraped_at／scraped_from，Work 层（full_text/<key>/）按 E-11 用 work_id、fetched_at。
FT_REQUIRED_FIELDS = ["chapters", "revision", "source", "total_chapters", "version_label"]
FT_OWNER_KEY = {"Book": "book_id", "Work": "work_id"}
FT_TIME_KEYS = ("fetched_at", "scraped_at")
FT_CHAPTER_NAME_RE = re.compile(r"^\d+\.(md|json)$")  # 章文件 NNN.md，可另有同名 NNN.json
# T30（Kanripo 方案 B，line_is_column）新增旁档：叶码精确到列，另存 pages.tsv，
# 不是章节 md，不该被「章节文件名不符 N.md」误判。任务书原话「不要改数据迁就规则」，
# 但此处不是改数据、是给规则本身补一个此前没设计到的合法文件名，故直接放行。
FT_SIDECAR_FILES = {"index.json", "pages.tsv"}
# original（本项目从书影自做的文本）一册一组（book-text docs/ORIGINAL.md，10-06 用户定）：
# 真源 NNN.char／cord／punct／entity／norm／decision.json，生成分支上另有 lines.md、rich.md；
# 以及版本日志 CHANGES.md。
ORIGINAL_SIDECAR_FILES = {"index.json", "CHANGES.md"}
ORIGINAL_FILE_RE = re.compile(r"^\d+\.(char|cord|punct|entity|norm|decision)\.json$|^\d+\.(lines|rich)\.md$")
# index.json 章条目用 *_file 声明一册有哪些文件：有字段＝有文件，char_file 必填（ORIGINAL.md §二）
ORIGINAL_FILE_FIELDS = ("char_file", "cord_file", "punct_file", "entity_file", "norm_file", "decision_file",
                        "lines_file", "rich_file")
FR_REQUIRED_FIELDS = [
    "ai_note", "based_on", "collectors", "coverage", "fragments", "loss_status",
    "provenance", "provenance_note", "schema_ref", "schema_version", "statement",
    "title", "type", "work_id",
]
# F-MD-11 排除：<…> 内容含字书／音韵用语（通俗正同聲平去入）的不是组字描述，见调用处注释。
_ZI_LEXICON_RE = re.compile("[通俗正同聲平去入]")
# F-CE-06：曾登记补南齊書經籍志（d59f2ofu9i4i）用 paragraphs 代替 content 的存量例外；
# 2026-10-11 T2b（overview#535，book-text#45）已把 267 个 paragraphs 转为 content，例外取消，名单置空（保留机制）。
SEC_CONTENT_EXCEPTION_WORKS = set()


def _under(a, b):
    """a 是否等于 b 或在 b 之下（绝对路径比较）。"""
    a, b = os.path.abspath(a), os.path.abspath(b)
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def discover_versions(root, scan_root):
    """按 manifest.json 找出全部版本目录。返回 (versions, problems)：
    versions = [(版本目录, kind, 层 Work|Book)]；problems = [(manifest 路径, 说明, sub)]（F-MF-01）。
    --path 可指到条目、版本目录或更上层：与 scan_root 有包含关系的版本才保留。"""
    manifests = [m for m in _glob.glob(os.path.join(scan_root, "**", "manifest.json"), recursive=True)]
    if not manifests:  # --path 指到条目内部（如某版本目录）：向上找最近的 manifest
        cur = os.path.abspath(scan_root)
        while _under(cur, root) and cur != os.path.abspath(root):
            if os.path.isfile(os.path.join(cur, "manifest.json")):
                manifests = [os.path.join(cur, "manifest.json")]
                break
            cur = os.path.dirname(cur)
    versions, problems = [], []
    for m in sorted(manifests):
        relm = os.path.relpath(m, root).replace(os.sep, "/")
        layer = relm.split("/", 1)[0]
        if layer not in ("Work", "Book"):
            continue
        owner = os.path.dirname(m)
        try:
            with open(m, encoding="utf-8") as f:
                mf = json.load(f)
        except Exception as e:  # noqa: BLE001
            problems.append((m, f"{relm}: manifest 解析失败：{e}", "parse"))
            continue
        listed = set()
        for i, v in enumerate(mf.get("versions") or []):
            key = v.get("key") if isinstance(v, dict) else None
            if not key:
                problems.append((m, f"{relm}: versions[{i}] 缺 key", f"nokey:{i}"))
                continue
            listed.add(key)
            vdir = os.path.join(owner, key)
            if not os.path.isfile(os.path.join(vdir, "index.json")):
                problems.append((m, f"{relm}: 版本 {key} 缺目录或 index.json", f"missing:{key}"))
                continue
            if _under(vdir, scan_root) or _under(scan_root, vdir):
                versions.append((vdir, v.get("kind") or "transcription", layer))
        if not mf.get("versions"):
            problems.append((m, f"{relm}: versions 为空", "empty"))
        # 反向：条目下有 index.json 的子目录没登记进 manifest
        for name in sorted(os.listdir(owner)):
            if name in listed or name in ("fragments", "sources") or not os.path.isdir(os.path.join(owner, name)):
                continue
            if os.path.isfile(os.path.join(owner, name, "index.json")):
                problems.append((m, f"{relm}: 目录 {name}/ 有 index.json 但未登记进 manifest", f"unlisted:{name}"))
    return versions, problems


def check(root: str, scan_root: str = None):
    """跑全部规则，返回 (report, scanned_counts, total_scanned)。

    root：基线 key 里"文件路径"锚定的根（一律用它算相对路径，跨 --path 范围也能合用同一份基线）。
    scan_root：实际去 glob 扫描的目录，默认等于 root；--path 时是 root 下的某棵子树。
    report[rule_id] = {"level", "n_scanned", "violations": [{"key","note","weight"}, ...]}
    """
    if scan_root is None:
        scan_root = root
    report = {}
    scanned = {}

    def rel(f):
        return os.path.relpath(f, root).replace(os.sep, "/")

    def only_data(files):
        """递归 glob 会把 index/（派生索引，总管收道后重建，不是某部书的数据）也扫进来；
        真数据只在 Work/ 与 Book/ 两棵树下，按相对 root 的第一段过滤掉 index/ 等杂项目录。"""
        out = []
        for f in files:
            top = rel(f).split("/", 1)[0]
            if top in ("Work", "Book"):
                out.append(f)
        return out

    def rule(rule_id, level):
        report[rule_id] = {"level": level, "rule_id": rule_id, "n_scanned": 0, "violations": []}
        return report[rule_id]

    def add(r, f, note, sub=None, weight=1):
        relf = rel(f)
        key = f"{relf}::{r['rule_id']}" if sub is None else f"{relf}::{r['rule_id']}::{sub}"
        r["violations"].append({"key": key, "note": note, "weight": weight})

    # ---- 按 manifest 找版本目录（新结构 #307）----
    versions, mf_problems = discover_versions(root, scan_root)
    ce_vdirs = sorted(v for v, kind, _l in versions if kind == "collated")
    ft_vdirs = sorted((v, layer) for v, kind, layer in versions if kind != "collated")
    r_mf01 = rule("F-MF-01", "HARD")   # manifest 与版本目录对不上（缺目录、未登记、解析失败）
    for m, note, sub in mf_problems:
        add(r_mf01, m, note, sub=sub)
    r_mf01["n_scanned"] = len({os.path.dirname(v) for v, _k, _l in versions})
    scanned["manifest.json（条目）"] = r_mf01["n_scanned"]

    # ---- 整理本 index.json（kind=collated 的版本）----
    ce_files = [os.path.join(v, "index.json") for v in ce_vdirs]
    r_ce01 = rule("F-CE-01", "HARD")
    r_ce02 = rule("F-CE-02", "HARD")
    r_ce03 = rule("F-CE-03", "HARD")   # 裁决 B：新入库只许 5 正式值 + placeholder 存量占位
    r_ce04 = rule("F-CE-04", "HARD")
    r_ce04b = rule("F-CE-04b", "HARD")  # 裁决 B：type=placeholder 必须配 grade=placeholder
    r_ce04c = rule("F-CE-04c", "SOFT")  # grade 取值是否在已知枚举内（记法层面，报告用）
    for f in ce_files:
        for r in (r_ce01, r_ce02, r_ce03, r_ce04, r_ce04b, r_ce04c):
            r["n_scanned"] += 1
        d, err = jload(f)
        if err:
            add(r_ce01, f, f"{f}: JSON 解析失败：{err}")
            continue
        missing = [k for k in CE_REQUIRED_FIELDS if k not in d]
        if missing:
            add(r_ce01, f, f"{f}: 缺字段 {missing}")
        t = d.get("type")
        if t is None:
            add(r_ce02, f, f"{f}: type 为 null")
        elif t not in CE_TYPE_KNOWN:
            add(r_ce03, f, f"{f}: type={t!r} 不在现状枚举内（5 正式值 + placeholder）")
        tq = d.get("text_quality")
        grade = tq.get("grade") if isinstance(tq, dict) else None
        if not isinstance(tq, dict) or "grade" not in tq or not grade:
            add(r_ce04, f, f"{f}: text_quality 不是含 grade 的 dict：{tq!r}")
        else:
            if grade not in TQ_GRADE_KNOWN:
                add(r_ce04c, f, f"{f}: text_quality.grade={grade!r} 不在现状枚举内")
            if t == "placeholder" and grade != "placeholder":
                add(r_ce04b, f, f"{f}: type=placeholder 但 grade={grade!r}（应同为 placeholder）")
    scanned["整理本 index.json"] = len(ce_files)

    # ---- 整理本章 NNN.json：sections[] 字段完整性（F-CE-06；index.json 除外）----
    juan_files = sorted(f for v in ce_vdirs for f in _glob.glob(os.path.join(v, "*.json"))
                        if os.path.basename(f) != "index.json")
    r_ce06 = rule("F-CE-06", "HARD")
    for f in juan_files:
        r_ce06["n_scanned"] += 1
        wid = _work_id_from_path(f)
        d, err = jload(f)
        if err:
            add(r_ce06, f, f"{f}: JSON 解析失败：{err}", sub="parse")
            continue
        for idx, s in enumerate(d.get("sections", []) if isinstance(d, dict) else []):
            if not isinstance(s, dict):
                add(r_ce06, f, f"{f}#sections[{idx}]: 不是 dict", sub=idx)
                continue
            if "title" not in s:
                add(r_ce06, f, f"{f}#sections[{idx}]: 缺 title", sub=idx)
            if "type" not in s:
                add(r_ce06, f, f"{f}#sections[{idx}]: 缺 type", sub=idx)
            if "level" not in s:
                add(r_ce06, f, f"{f}#sections[{idx}]: 缺 level", sub=idx)
            if wid not in SEC_CONTENT_EXCEPTION_WORKS and "content" not in s:
                add(r_ce06, f, f"{f}#sections[{idx}]: 缺 content（非登记的存量例外 Work）", sub=idx)
            if s.get("type") == "book" and "work_id" not in s:
                add(r_ce06, f, f"{f}#sections[{idx}]: type=book 但缺 work_id 键", sub=idx)
            # 下划线过程字段（_author、_title_only、_dead_work_id 等）不再计为违规：
            # 用户 09-27 定，它们是整理未收尾的待办记录，随整理做完自然删，校验器忽略。
    scanned["整理本章 NNN.json"] = len(juan_files)

    # ---- 整理本章 NNN.md：括注同行闭合（F-MD-03）＋ 记法分布（F-MD-01，报告用）
    #      ＋ 标题不跳级（F-MD-07）＋ 标题层级分布（F-MD-08，报告用）----
    md_files = sorted(f for v in ce_vdirs for f in _glob.glob(os.path.join(v, "*.md")))
    r_md03 = rule("F-MD-03", "HARD")
    r_md01 = rule("F-MD-01", "SOFT")  # 记法分布，仅统计不判违规
    r_md07 = rule("F-MD-07", "HARD")
    r_md08 = rule("F-MD-08", "SOFT")  # 每部用了哪几级标题，仅报告
    mark_totals = collections.Counter()
    mark_docs = collections.defaultdict(set)
    work_heading_levels = collections.defaultdict(set)
    for f in md_files:
        for r in (r_md03, r_md01, r_md07, r_md08):
            r["n_scanned"] += 1
        try:
            text = open(f, encoding="utf-8").read()
        except Exception as e:  # noqa: BLE001
            add(r_md03, f, f"{f}: 读取失败：{e}", sub="readerr")
            continue
        masked = mask_inert(text)

        n, hit = unclosed_hex_count(masked)
        if hit:
            add(r_md03, f, f"{f}: 〔〕 同行未闭合 {n} 处", weight=n)

        jz = len(_ANGLE_JZ_RE.findall(masked))
        hx = len(_HEX_RE.findall(masked))
        wp = len(_WIDE_PAREN_RE.findall(masked))
        ang = spec_angle_jiazhu_count(masked)
        if jz:
            mark_totals["⟨…⟩"] += jz
            mark_docs["⟨…⟩"].add(f)
        if hx:
            mark_totals["〔…〕"] += hx
            mark_docs["〔…〕"].add(f)
        if wp:
            mark_totals["（（…））"] += wp
            mark_docs["（（…））"].add(f)
        if ang:
            mark_totals["<…>（spec 生效）"] += ang
            mark_docs["<…>（spec 生效）"].add(f)

        # F-MD-07／F-MD-08：标题层级（ATX # 个数），逐行扫 masked 文本
        prev_level = None
        jump_seq = 0
        wid = _work_id_from_path(f)
        for line in masked.splitlines():
            m = re.match(r"(#{1,6})\s", line.strip())
            if not m:
                continue
            lvl = len(m.group(1))
            work_heading_levels[wid].add(lvl)
            if prev_level is not None and lvl > prev_level + 1:
                add(r_md07, f, f"{f}: 标题从 {'#'*prev_level} 跳到 {'#'*lvl}", sub=jump_seq)
                jump_seq += 1
            prev_level = lvl
    r_md01["mark_detail"] = [
        f"{name}: {mark_totals[name]} 处 / {len(mark_docs[name])} 档" for name in mark_totals
    ]
    r_md08["mark_detail"] = [
        f"{wid}: 用了 {sorted('#'*l for l in levels)}"
        for wid, levels in sorted(work_heading_levels.items())
    ]
    scanned["整理本章 NNN.md"] = len(md_files)

    # ---- 全文版本（kind≠collated 的版本：wikisource／kanripo／shidian…，含 default）----
    # 旧结构只认 Book 层 full_text/index.json 与 Work 层 full_text/<key>/index.json；
    # 新结构一律经 manifest 取版本目录，Work／Book 两层同一条规则（owner 键按层区分）。
    ft_files = [os.path.join(v, "index.json") for v, _l in ft_vdirs]
    r_ft01 = rule("F-FT-01", "HARD")
    for f in ft_files:
        r_ft01["n_scanned"] += 1
        d, err = jload(f)
        if err:
            add(r_ft01, f, f"{f}: JSON 解析失败：{err}", sub="parse")
            continue
        missing = [k for k in FT_REQUIRED_FIELDS if k not in d]
        rel_parts = os.path.relpath(f, root).split(os.sep)
        layer = rel_parts[0] if rel_parts and rel_parts[0] in FT_OWNER_KEY else None
        if layer and FT_OWNER_KEY[layer] not in d:
            missing.append(FT_OWNER_KEY[layer])
        if not any(k in d for k in FT_TIME_KEYS):
            missing.append("fetched_at|scraped_at")
        # 09-27 网站总管建议：全文页按 source.name/license 显示署名（CC BY-SA 要求），缺了就是许可缺口
        src = d.get("source")
        if isinstance(src, dict):
            missing += [f"source.{k}" for k in ("name", "license") if not src.get(k)]
        if missing:
            add(r_ft01, f, f"{f}: 缺字段 {missing}", sub="missing")
        chap_dir = os.path.dirname(f)
        is_orig = OV.is_original_dir(chap_dir)
        for name in sorted(os.listdir(chap_dir)):
            if name in FT_SIDECAR_FILES:
                continue
            if is_orig and (name in ORIGINAL_SIDECAR_FILES or ORIGINAL_FILE_RE.match(name)):
                continue
            if not FT_CHAPTER_NAME_RE.match(name):
                add(r_ft01, f, f"{chap_dir}/{name}: 章节文件名不符 N.md", sub=f"name:{name}")
    scanned["全文版本 index.json（Book＋Work）"] = len(ft_files)

    # ---- original 三线版本号（T67 #400，规范 2026-10-文本版本号与仓库流程.md；T68 #417 起文本线读 char）----
    # 只管 key=original 的版本；维基、Kanripo、识典的转录不跟踪版本，不在此列。
    # 文本线的版本是 NNN.char.json 顶层 version，index.json 的 text_version 是镜像。
    # F-OV-01 版本号格式：每册文本／标点／实体三线都要有 MAJOR.MINOR.PATCH，且 1.0.0 ≤ 版本、major ≤3
    #         （0.x 只许留在 wip/ 分支，并 main 时 init 为 1.0.0）；index.json 里的
    #         text_version／punct_version／entity_version 要与 char、punct、entity 的 version 一致；伴生层的
    #         text_version 不能超前于当前文本版本；标点、实体的 major 不得高于文本线的 major
    #         （文本还没到出版级，伴生层也不能先升，10-05 用户定）。
    # F-OV-02 伴生层的 text_version 落后于当前文本时，逐个核锚点校验字（按 char 的格位和字），对不上就报。
    # F-OV-03 任一线 major ≥2，必须带验收记录（date／signed_by／sample）：
    #         文本线在 char.json 顶层的 review，标点、实体在各自 json 顶层的 review。
    # F-OV-04 章条目的文件声明（ORIGINAL.md §二）：char_file 必填；写了的 *_file 必须存在，
    #         且文件名是 NNN.<代号>.json／.md。
    ov_dirs = sorted(v for v, _l in ft_vdirs if OV.is_original_dir(v))
    r_ov01 = rule("F-OV-01", "HARD")
    r_ov02 = rule("F-OV-02", "HARD")
    r_ov03 = rule("F-OV-03", "HARD")
    r_ov04 = rule("F-OV-04", "HARD")
    n_ov_chapters = 0
    for od in ov_dirs:
        f = os.path.join(od, "index.json")
        d, err = jload(f)
        if err or not isinstance(d, dict):
            continue  # 解析失败 F-FT-01 已报
        for ci, ch in enumerate(d.get("chapters") or []):
            if not isinstance(ch, dict):
                continue
            stem = OV.chapter_file(ch)
            r_ov04["n_scanned"] += 1
            for k in ORIGINAL_FILE_FIELDS:
                if k not in ch:
                    continue
                code = k[:-len("_file")]
                want = f"{stem}.{code}." + ("md" if code in ("lines", "rich") else "json")
                if ch[k] != want:
                    add(r_ov04, f, f"{f}: 册 {stem} {k}={ch[k]!r}，应为 {want!r}", sub=f"{stem}:{k}:name")
                elif not os.path.isfile(os.path.join(od, want)):
                    add(r_ov04, f, f"{f}: 册 {stem} 声明了 {k}={want!r}，文件不存在", sub=f"{stem}:{k}:missing")
            if "char_file" not in ch:
                add(r_ov04, f, f"{f}: chapters[{ci}] 缺 char_file（必填）", sub=f"{ci}:nochar")
            char_path = OV.companion_path(od, stem, "text") if stem else None
            if not char_path or not os.path.isfile(char_path):
                add(r_ov01, f, f"{f}: chapters[{ci}] 找不到对应的 NNN.char.json", sub=f"{ci}:nochar")
                continue
            char, cerr = jload(char_path)
            if cerr or not isinstance(char, dict):
                add(r_ov01, char_path, f"{char_path}: JSON 解析失败：{cerr}", sub="parse")
                continue
            n_ov_chapters += 1
            for r in (r_ov01, r_ov02, r_ov03):
                r["n_scanned"] += 1
            tv = char.get("version")
            tvt = OV.parse_version(tv)
            if tvt is None:
                add(r_ov01, char_path, f"{char_path}: version={tv!r} 不是 MAJOR.MINOR.PATCH", sub="version")
            elif tvt[0] < 1:
                add(r_ov01, char_path, f"{char_path}: version={tv} 还是 0.x（并 main 前须 init 为 1.0.0）", sub="version")
            elif tvt[0] > OV.MAX_MAJOR:
                add(r_ov01, char_path, f"{char_path}: version={tv} 的 major 超过 {OV.MAX_MAJOR}（质量等级只有 1–3）", sub="version")
            elif tvt[0] >= 2 and OV.review_missing(char.get("review")):
                add(r_ov03, char_path, f"{char_path}: 文本线 {tv} ≥2 级，review 缺 {OV.review_missing(char.get('review'))}",
                    sub="review")
            if ch.get("text_version") != tv:
                add(r_ov01, f, f"{f}: 册 {stem} text_version={ch.get('text_version')!r} 与 {os.path.basename(char_path)} 的 version={tv!r} 不一致",
                    sub=f"{stem}:text:mirror")
            for line in ("punct", "entity"):
                cf = OV.companion_path(od, stem, line)
                if not os.path.isfile(cf):
                    if ch.get(f"{line}_version") is not None:
                        add(r_ov01, f, f"{f}: 册 {stem} 登记了 {line}_version 但没有 {os.path.basename(cf)}", sub=f"{stem}:{line}:nofile")
                    continue
                cd, cerr = jload(cf)
                if cerr or not isinstance(cd, dict):
                    add(r_ov01, cf, f"{cf}: JSON 解析失败：{cerr}", sub="parse")
                    continue
                v, ctv = cd.get("version"), cd.get("text_version")
                vt, ctvt = OV.parse_version(v), OV.parse_version(ctv)
                if vt is None or vt[0] < 1:
                    add(r_ov01, cf, f"{cf}: version={v!r} 不合格式或还是 0.x", sub="version")
                elif vt[0] > OV.MAX_MAJOR:
                    add(r_ov01, cf, f"{cf}: version={v} 的 major 超过 {OV.MAX_MAJOR}（质量等级只有 1–3）", sub="version")
                elif vt[0] >= 2 and OV.review_missing(cd.get("review")):
                    add(r_ov03, cf, f"{cf}: {line} 线 {v} ≥2 级，review 缺 {OV.review_missing(cd.get('review'))}", sub="review")
                if vt is not None and tvt is not None and tvt[0] < vt[0] <= OV.MAX_MAJOR:
                    add(r_ov01, cf, f"{cf}: {line} 线 {v} 的等级高于文本线 {tv}（伴生层 major 不得高于文本）", sub="above_text")
                if ch.get(f"{line}_version") != v:
                    add(r_ov01, f, f"{f}: 册 {stem} {line}_version={ch.get(f'{line}_version')!r} 与 {os.path.basename(cf)} 的 version={v!r} 不一致",
                        sub=f"{stem}:{line}:mirror")
                if ctvt is None or ctvt[0] < 1:
                    add(r_ov01, cf, f"{cf}: text_version={ctv!r} 不合格式或还是 0.x", sub="text_version")
                    continue
                if tvt is None:
                    continue
                if ctvt > tvt:
                    add(r_ov01, cf, f"{cf}: text_version={ctv} 超前于当前文本 {tv}", sub="ahead")
                elif ctvt < tvt:
                    bad = OV.anchor_mismatches(char, line, cd)
                    for i, note in bad[:20]:
                        add(r_ov02, cf, f"{cf}: 落后于文本（{ctv} < {tv}）且{note}", sub=f"anchor:{i}")
                    if len(bad) > 20:
                        add(r_ov02, cf, f"{cf}: 另有 {len(bad) - 20} 处锚点对不上未逐条列出", sub="anchor:more",
                            weight=len(bad) - 20)
    scanned["original 册（三线版本号）"] = n_ov_chapters

    # ---- :::table 容器块语法（F-MD-09，T22 新增，服务 2026-09-表格记法方案.md）----
    # 记法目前只出现在全文版本的章节 md（kind≠collated 的版本下 NNN.md），
    # 顺带也扫整理本章 md（`md_files`，上面 F-MD-03/07 已读过的那批）——
    # 万一未来整理本正文也用得上同一套语法，不必再加一条规则。
    ft_chapter_md = sorted(f for v, _l in ft_vdirs for f in _glob.glob(os.path.join(v, "*.md")))
    r_md09 = rule("F-MD-09", "HARD")
    # F-MD-10（T26，guji-markdown 0.2.0 三条新语法出现次数，SOFT，仅统计不判违规）：
    # 认了不误报——三条写法都不落在既有 HARD 规则的判定范围内（F-MD-03 只管
    # 〔…〕、F-MD-09 只管 :::table 本身的块结构，不管格内内容），本条只加统计，
    # 不改任何判违规逻辑。
    r_md10 = rule("F-MD-10", "SOFT")
    # F-MD-11（T26，组字候选报警，SOFT）：<…> 夹注内容如果整段只是「上X下Y／
    # 左X右Y」这类部件+方位描述（复用 zi_convert.classify() 判 kind），
    # 大概率是本该写成 guji-markdown `:zi[…]` 组字、还没转的旧写法，报出来
    # 供人核对。只报「ids」「nested-ids」两档——`text`／`ambiguous` 两档在
    # 全仓层面噪声极大（实测两字部件、无方位词一档全仓命中 60 万＋条，
    # 几乎全是普通夹注），不适合做成规则，见
    # `古籍文本/进度/E-文本整理本/34-组字候选清单.md` §3.2。
    r_md11 = rule("F-MD-11", "SOFT")
    t26_totals = collections.Counter()
    t26_docs = collections.defaultdict(set)
    for f in ft_chapter_md + md_files:
        r_md09["n_scanned"] += 1
        r_md10["n_scanned"] += 1
        r_md11["n_scanned"] += 1
        try:
            text = open(f, encoding="utf-8").read()
        except Exception as e:  # noqa: BLE001
            add(r_md09, f, f"{f}: 读取失败：{e}", sub="readerr")
            continue
        masked = mask_inert(text)
        blocks, unclosed = scan_table_blocks(masked)
        if unclosed:
            add(r_md09, f, f"{f}: :::table 块未闭合 {unclosed} 处", sub="unclosed", weight=unclosed)
        for bi, (_s, _e, body) in enumerate(blocks):
            header_cols, problems = check_table_block_cols(body)
            if problems:
                detail = "、".join(f"第{ri}行{n}列" for ri, n in problems[:5])
                add(r_md09, f, f"{f}: 第 {bi} 个 :::table 块列数不齐（表头 {header_cols} 列），{len(problems)} 行不对：{detail}",
                    sub=f"cols:{bi}", weight=len(problems))
        for name, n in t26_new_syntax_counts(masked).items():
            if n:
                t26_totals[name] += n
                t26_docs[name].add(f)
        for zi_seq, content in enumerate(iter_jz_spans(masked)):
            zc = _zi_classify(content)
            if zc.kind in ("ids", "nested-ids"):
                # 2026-10-11 T6（overview#535，Maren 裁）：字样书／音注用语「上通下正」「並上俗下正」「上聲下同」
                # 「上平下去」读作「上字X、下字Y」，不是组字描述（实测 934 处里 801 处，集中在《干祿字書》《說郛》）。
                # 按内容含字书／音韵用语排除，不按 Work 白名单，免得换书又漏。
                if _ZI_LEXICON_RE.search(content):
                    continue
                add(r_md11, f, f"{f}: <{content}> 疑似组字未转（{zc.reason}），候选写法 {zc.notation}",
                    sub=f"zi:{zi_seq}")
    scanned["全文/整理本 md 中的 :::table 块"] = len(ft_chapter_md) + len(md_files)
    r_md10["mark_detail"] = [
        f"{name}: {t26_totals[name]} 处 / {len(t26_docs[name])} 档" for name in t26_totals
    ]

    # ---- 辑佚 fragments ----
    fr_files = sorted(only_data(_glob.glob(os.path.join(scan_root, "**", "fragments", "*.json"), recursive=True)))
    r_fr01 = rule("F-FR-01", "HARD")
    for f in fr_files:
        r_fr01["n_scanned"] += 1
        d, err = jload(f)
        if err:
            add(r_fr01, f, f"{f}: JSON 解析失败：{err}", sub="parse")
            continue
        if not isinstance(d, dict):
            add(r_fr01, f, f"{f}: 顶层不是 dict", sub="nondict")
            continue
        missing = [k for k in FR_REQUIRED_FIELDS if k not in d]
        if missing:
            add(r_fr01, f, f"{f}: 缺字段 {missing}", sub="missing")
    scanned["辑佚 fragments/*.json"] = len(fr_files)

    total_scanned = sum(scanned.values())
    return report, scanned, total_scanned


def n_violations(r):
    return sum(v["weight"] for v in r["violations"])


def all_hard_keys(report):
    """report 里全部 HARD 规则的违规 key 集合（去重）。"""
    keys = set()
    for r in report.values():
        if r["level"] == "HARD":
            for v in r["violations"]:
                keys.add(v["key"])
    return keys


# ---------------------------------------------------------------------------
# 基线：冻结 / 收缩式刷新 / --strict 时的 key 过滤
# ---------------------------------------------------------------------------

def load_baseline(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_baseline(path, keys, note=""):
    data = {
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "count": len(keys),
        "note": note,
        "keys": sorted(keys),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return data


def scope_prefix_of(root, scan_root):
    """--path 对应的相对前缀；无 --path 时返回 None（代表整仓，不设限）。"""
    if os.path.abspath(scan_root) == os.path.abspath(root):
        return None
    p = os.path.relpath(scan_root, root).replace(os.sep, "/")
    return p


def key_in_scope(key, prefix):
    if prefix is None:
        return True
    return key.startswith(prefix.rstrip("/") + "/")


def update_baseline(baseline_path, current_keys, root, scan_root):
    """收缩式刷新：只减不增。范围外（--path 未覆盖）的 key 原样保留。"""
    prefix = scope_prefix_of(root, scan_root)
    if os.path.exists(baseline_path):
        old = load_baseline(baseline_path)
        old_keys = set(old.get("keys", []))
    else:
        old_keys = set()
    kept = set()
    dropped = set()
    for k in old_keys:
        if key_in_scope(k, prefix):
            if k in current_keys:
                kept.add(k)
            else:
                dropped.add(k)
        else:
            kept.add(k)  # 范围外，不动
    data = write_baseline(baseline_path, kept, note="update-baseline：收缩式刷新，未新增")
    return data, dropped


def init_baseline(baseline_path, current_keys):
    return write_baseline(baseline_path, current_keys, note="init：冻结当次全部违规")


# ---------------------------------------------------------------------------
# glob 帮助（<c1>/<c2>/<c3>/<id> 四层分片，见 book-text README；改用递归 glob
# 让 --path 指到任意子树都能直接复用同一套规则）
# ---------------------------------------------------------------------------

def _work_id_from_path(path):
    """从 .../Work/<c1>/<c2>/<c3>/<work_id>/<key>/... 里取 work_id。"""
    parts = os.path.normpath(path).split(os.sep)
    try:
        i = parts.index("Work")
        return parts[i + 4]
    except (ValueError, IndexError):
        return "?"


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

def render_markdown(report, scanned, total_scanned):
    lines = ["# book-text 文本格式校验报告", ""]
    lines.append("## 扫描档数（分母）")
    for name, n in scanned.items():
        lines.append(f"- {name}：{n}")
    lines.append(f"- **合计**：{total_scanned}")
    lines.append("")
    lines.append("## 规则计数")
    lines.append("")
    lines.append("| 规则 | 档次 | 扫描数 | 不合规数 |")
    lines.append("|---|---|---:|---:|")
    for rid, r in report.items():
        lines.append(f"| {rid} | {r['level']} | {r['n_scanned']} | {n_violations(r)} |")
    lines.append("")
    for rid, r in report.items():
        notes = [v["note"] for v in r["violations"]] or r.get("mark_detail", [])
        if notes:
            lines.append(f"### {rid} 明细（前 20 条）")
            for d in notes[:20]:
                lines.append(f"- {d}")
            if len(notes) > 20:
                lines.append(f"- …（共 {len(notes)} 条，仅列前 20）")
            lines.append("")
    return "\n".join(lines)


def render_json(report, scanned, total_scanned):
    out_report = {}
    for rid, r in report.items():
        out_report[rid] = {
            "level": r["level"],
            "n_scanned": r["n_scanned"],
            "n_violations": n_violations(r),
            "detail": [v["note"] for v in r["violations"]][:200] or r.get("mark_detail", []),
        }
    return {"scanned": scanned, "total_scanned": total_scanned, "report": out_report}


# ---------------------------------------------------------------------------
# 自测：造一个故意造坏的小样本，验证每条 HARD 规则都能被捉到 ＋ 基线机制
# ---------------------------------------------------------------------------

def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _vd(root, layer, shard, oid, key, kind):
    """造样本：在条目 manifest.json 里登记一个版本并返回其目录（新结构 #307）。"""
    owner = os.path.join(root, layer, shard[0], shard[1], shard[2], oid)
    mp = os.path.join(owner, "manifest.json")
    mf = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {"id": oid, "versions": []}
    mf["versions"].append({"key": key, "kind": kind, "source": "x", "license": "CC0 1.0"})
    _write_json(mp, mf)
    return os.path.join(owner, key)


def _ok_ft_index(layer_key="work_id", oid="x"):
    """合规的全文版本 index.json（样本用）。"""
    return {"chapters": [], "revision": 1, "source": {"name": "n", "license": "CC0 1.0"},
            "total_chapters": 0, "version_label": "v", layer_key: oid, "fetched_at": "2026-10-02"}


def _build_bad_sample(root):
    good_dir = _vd(root, "Work", "god", "goodwork", "default", "collated")
    _write_json(os.path.join(good_dir, "index.json"), {
        "work_id": "goodwork", "total_entries": 1, "chapters": [{"n": 1, "file": "001"}],
        "text_quality": {"grade": "rough", "source_note": "x"},
        "revision": 1, "revised_at": "2026-09-26", "type": "catalog",
    })
    _write_text(os.path.join(good_dir, "001.md"), "正文<夹注>正文\n〔校勘记〕\n字样<上通下正>与<並上俗下正>及音注<上聲下同>不算组字\n")  # F-MD-11 排除样本（T6）

    bad_dir = _vd(root, "Work", "bad", "badwork", "default", "collated")
    _write_json(os.path.join(bad_dir, "index.json"), {
        "work_id": "badwork",
        "text_quality": "rough",  # 不是 dict，触发 F-CE-04
        "type": None,  # 触发 F-CE-02
    })
    _write_text(os.path.join(bad_dir, "001.md"),
                "正文〔未闭合校勘记\n下一行〕\n# 一级标题\n### 三级标题（跳过二级）\n"
                "缺字<上雍下玉>正文\n")  # 疑似组字未转，触发 F-MD-11（SOFT，不进 --strict）
    _write_json(os.path.join(bad_dir, "001.json"), {
        "title": "卷一",
        "sections": [
            {"level": 2, "type": "book"},                     # 缺 title/content/work_id
            {"title": "x", "level": 2, "type": "category", "content": "y", "_tmp": 1},  # 下划线字段
        ],
    })

    badtype_dir = _vd(root, "Work", "typ", "badtype", "default", "collated")
    _write_json(os.path.join(badtype_dir, "index.json"), {
        "work_id": "badtype", "total_entries": 1, "chapters": [],
        "text_quality": {"grade": "rough"}, "revision": 1, "revised_at": "2026-09-26",
        "type": "不明类型",  # 触发 F-CE-03
    })
    badph_dir = _vd(root, "Work", "ph1", "badplaceholder", "default", "collated")
    _write_json(os.path.join(badph_dir, "index.json"), {
        "work_id": "badplaceholder", "total_entries": 1, "chapters": [],
        "text_quality": {"grade": "rough"}, "revision": 1, "revised_at": "2026-09-26",
        "type": "placeholder",  # 与 grade 不同步，触发 F-CE-04b
    })

    ft_dir = _vd(root, "Book", "bad", "badbook", "default", "transcription")
    _write_json(os.path.join(ft_dir, "index.json"), {"book_id": "badbook"})  # 缺其余 7 字段
    _write_text(os.path.join(ft_dir, "chapter-one.md"), "内容")

    # F-MF-01：manifest 登记了 ghost 版本但无目录；另有未登记的版本目录
    _vd(root, "Work", "mfx", "badmanifest", "ghost", "transcription")
    _write_json(os.path.join(root, "Work", "m", "f", "x", "badmanifest", "stray", "index.json"), {})

    fr_dir = os.path.join(root, "Work", "b", "a", "d", "badfrag", "fragments")
    _write_json(os.path.join(fr_dir, "badfrag.json"), {"title": "x", "work_id": "badfrag"})

    # F-MD-09（T22，:::table 容器块）：好样本覆盖 colspan／rowspan／续格／空格／夹注
    # 五种记号同框出现，不能互相误报；坏样本各踩「块没闭合」与「列数不齐」一条。
    goodtable_dir = _vd(root, "Work", "got", "goodtable", "default", "transcription")
    _write_json(os.path.join(goodtable_dir, "index.json"), _ok_ft_index())
    _write_text(os.path.join(goodtable_dir, "001.md"),
                "正文正文。\n\n"
                ":::table\n"
                "!公元 | 宰相 | 執政\n"
                "960 | 范質<字仲甫>{2}\n"
                "961 | 趙普^2 | 王溥\n"
                "962 | ^ | _\n"
                ":::\n\n"
                "正文結尾。\n")

    badtable_dir = _vd(root, "Work", "bat", "badtable", "default", "transcription")
    _write_json(os.path.join(badtable_dir, "index.json"), _ok_ft_index())
    _write_text(os.path.join(badtable_dir, "001.md"),
                "正文。\n\n"
                ":::table\n"
                "!年 | 宰相\n"
                "960 | 范質\n")  # 故意不写收尾的 ":::"，触发「块未闭合」
    _write_text(os.path.join(badtable_dir, "002.md"),
                ":::table\n"
                "!年 | 宰相 | 執政\n"
                "960 | 范質\n"  # 只有 2 列，表头 3 列，触发「列数不齐」
                ":::\n")

    # F-MD-10（T26，guji-markdown 0.2.0 三条新语法）：好样本覆盖阙文／缺字猜测／
    # 夹注分行，且格内分行按 T26 规矩转义 `\|`，三者不能互相误报、也不能误触发
    # 既有 HARD 规则（F-MD-03／F-MD-09 等）。
    goodT26_dir = _vd(root, "Work", "got", "goodT26", "default", "collated")
    _write_json(os.path.join(goodT26_dir, "index.json"), {
        "work_id": "goodT26", "total_entries": 1, "chapters": [{"n": 1, "file": "001"}],
        "text_quality": {"grade": "rough"}, "revision": 1, "revised_at": "2026-10-02", "type": "catalog",
    })
    _write_text(os.path.join(goodT26_dir, "001.md"),
                "帝崩，[[凡三字漫漶]]即位。\n"
                "太子□{guess=即}位。\n"
                "詔曰<甲|乙>。\n")
    goodT26_ft_dir = _vd(root, "Work", "got", "goodT26", "wikisource", "transcription")
    _write_json(os.path.join(goodT26_ft_dir, "index.json"), _ok_ft_index())
    _write_text(os.path.join(goodT26_ft_dir, "001.md"),
                ":::table\n"
                "!甲 | 乙\n"
                "[[缺]] | <丙\\|丁>\n"
                ":::\n")


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        root = tmp
        _build_bad_sample(root)
        report, scanned, total = check(root)

        expectations = {
            "F-CE-01": 1,  # badwork 缺字段
            "F-CE-02": 1,  # badwork type=null
            "F-CE-03": 1,  # badtype type 不在枚举内
            "F-CE-04": 1,  # badwork text_quality 非 dict
            "F-CE-04b": 1,  # badplaceholder type=placeholder 但 grade!=placeholder
            "F-CE-06": 3,  # badwork juan：section0 缺 title/content/work_id 三项（section1 的下划线字段不计，09-27 定）
            "F-MD-03": 1,  # badwork 〔 未闭合（跨行，按行计每行各算一次，此处两行各差 1）
            "F-MD-07": 1,  # badwork 标题从 # 跳到 ###
            "F-FT-01": 2,  # 缺字段 1 处 + 章节命名不合规 1 处
            "F-FR-01": 1,  # badfrag 缺核心字段
            "F-MF-01": 2,  # badmanifest：登记了 ghost 版本无目录 + stray/ 未登记
            "F-MD-09": 2,  # badtable/001.md 未闭合 1 处 + badtable/002.md 列数不齐 1 处
            "F-MD-11": 1,  # badwork 里 <上雍下玉> 疑似组字未转
        }
        for rid, expect_min in expectations.items():
            got = n_violations(report[rid])
            status = "PASS" if got >= expect_min else "FAIL"
            if status == "FAIL":
                ok = False
            print(f"[{status}] {rid}: 期望至少 {expect_min} 处不合规，实得 {got}")
        for rid, r in report.items():
            if r["level"] == "HARD":
                for v in r["violations"]:
                    if "goodwork" in v["note"] or "goodtable" in v["note"] or "goodT26" in v["note"]:
                        print(f"[FAIL] {rid}: 合规样本被误报：{v['note']}")
                        ok = False

        md10_status = "PASS" if n_violations(report.get("F-MD-10", {"violations": []})) == 0 else "FAIL"
        # F-MD-10 是 SOFT／仅统计，n_violations 恒为 0（没有 add() 写违规），
        # 真正要看的是 mark_detail 里三条新语法都数到了：
        md10_detail = report.get("F-MD-10", {}).get("mark_detail", [])
        md10_names = {d.split(":")[0] for d in md10_detail}
        expect_names = {"阙文 [[…]]", "缺字猜测 □{guess=…}", "夹注分行 <a|b>"}
        if not expect_names.issubset(md10_names):
            md10_status = "FAIL"
            ok = False
        print(f"[{md10_status}] F-MD-10（T26 新语法统计）：{md10_detail}")

        print("规则自测：" + ("全部通过 ✅" if ok else "存在未捉到的坏样本 ❌"))

        # ---- 基线机制自测：造一个新违规 → --strict 失败；只有基线内违规 → 通过 ----
        baseline_path = os.path.join(tmp, "format_baseline.json")
        cur_keys = all_hard_keys(report)
        init_baseline(baseline_path, cur_keys)

        # 场景一：仅基线内违规 → strict 应通过（不合规数为 0）
        report2, _, _ = check(root)
        baseline = load_baseline(baseline_path)
        bset = set(baseline["keys"])
        unbaselined = [v for r in report2.values() if r["level"] == "HARD" for v in r["violations"] if v["key"] not in bset]
        status = "PASS" if len(unbaselined) == 0 else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"[{status}] 基线场景一（只有基线内违规应通过 strict）：未在基线内的违规数 {len(unbaselined)}（期望 0）")

        # 场景二：引入一个新违规（新建一部书）→ strict 应失败
        newbad_dir = _vd(root, "Work", "new", "newbadwork", "default", "collated")
        _write_json(os.path.join(newbad_dir, "index.json"), {
            "work_id": "newbadwork",
            "text_quality": "rough",
            "type": None,
        })
        report3, _, _ = check(root)
        unbaselined3 = [v for r in report3.values() if r["level"] == "HARD" for v in r["violations"] if v["key"] not in bset]
        status = "PASS" if len(unbaselined3) > 0 else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"[{status}] 基线场景二（新违规应使 strict 失败）：未在基线内的违规数 {len(unbaselined3)}（期望 >0）")

        # 场景三：修掉 badwork 的 juan 缺字段问题 → update-baseline 后基线项应减少、不新增
        _write_json(os.path.join(root, "Work", "b", "a", "d", "badwork", "default", "001.json"), {
            "title": "卷一",
            "sections": [
                {"title": "y", "level": 2, "type": "book", "content": "z", "work_id": None},
                {"title": "x", "level": 2, "type": "category", "content": "y"},
            ],
        })
        report4, _, _ = check(root)
        cur_keys4 = all_hard_keys(report4)
        data_before = load_baseline(baseline_path)
        data_after, dropped = update_baseline(baseline_path, cur_keys4, root, root)
        shrank = len(data_after["keys"]) < len(data_before["keys"])
        no_growth = set(data_after["keys"]) <= set(data_before["keys"])
        status = "PASS" if (shrank and no_growth) else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"[{status}] 基线场景三（update-baseline 只减不增）：{len(data_before['keys'])} → {len(data_after['keys'])}，"
              f"剔除 {len(dropped)} 项，new⊆old={no_growth}")

    print("自测总结：" + ("全部通过 ✅" if ok else "存在失败项 ❌"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", help="book-text 仓根目录")
    ap.add_argument("--json", metavar="OUT", help="额外把结果写成 JSON 到指定路径")
    ap.add_argument("--strict", action="store_true", help="HARD 档（扣除基线内已知项后）非 0 时退出码 1")
    ap.add_argument("--path", metavar="SUBDIR", help="只扫 root 下的这棵子树（相对路径，或 root 下的绝对路径），供单部入库自检用")
    ap.add_argument("--baseline", metavar="JSON", help="基线文件路径；配合 --strict 只对不在基线里的违规失败；文件不存在时改为冻结当次全部违规写出")
    ap.add_argument("--update-baseline", action="store_true", help="收缩式刷新基线：这次已不违规的项剔除，不新增；需要 --baseline")
    ap.add_argument("--selftest", action="store_true", help="造坏样本自测（含基线机制），不需要真仓")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if not args.root:
        ap.error("需要传 book-text 仓根目录，或用 --selftest 自测")

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"路径不存在：{root}", file=sys.stderr)
        sys.exit(2)

    scan_root = root
    if args.path:
        scan_root = args.path if os.path.isabs(args.path) else os.path.join(root, args.path)
        scan_root = os.path.abspath(scan_root)
        if not os.path.isdir(scan_root):
            print(f"--path 路径不存在：{scan_root}", file=sys.stderr)
            sys.exit(2)
        if args.update_baseline and not args.baseline:
            ap.error("--update-baseline 需要 --baseline")
        if args.baseline and not os.path.exists(args.baseline) and not args.update_baseline:
            print("首次冻结基线时不许带 --path（会只冻住这一部书，其余全仓欠账永远进不了基线）。"
                  "先在整仓上跑一次 --baseline 建基线，再用 --path 配 --update-baseline 做单部收缩式刷新。",
                  file=sys.stderr)
            sys.exit(2)

    report, scanned, total_scanned = check(root, scan_root)

    print(f"扫描档数：{scanned}（合计 {total_scanned}）", file=sys.stderr)
    if total_scanned == 0:
        print("扫到 0 档——多半是仓根路径不对，判为失败，不当作『全部合规』。", file=sys.stderr)
        sys.exit(2)

    current_keys = all_hard_keys(report)

    if args.baseline:
        if args.update_baseline:
            data_after, dropped = update_baseline(args.baseline, current_keys, root, scan_root)
            print(f"基线刷新：{args.baseline} 现有 {data_after['count']} 项，本次剔除 {len(dropped)} 项（已修掉）；"
                  f"只减不增，未新增任何项。", file=sys.stderr)
        elif not os.path.exists(args.baseline):
            data = init_baseline(args.baseline, current_keys)
            print(f"基线不存在，已初建：{args.baseline}，冻结 {data['count']} 项。", file=sys.stderr)

    md = render_markdown(report, scanned, total_scanned)
    print(md)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(render_json(report, scanned, total_scanned), f, ensure_ascii=False, indent=2)

    if args.strict:
        baseline_keys = set()
        if args.baseline and os.path.exists(args.baseline):
            baseline_keys = set(load_baseline(args.baseline).get("keys", []))
        hard_violations = 0
        for r in report.values():
            if r["level"] != "HARD":
                continue
            for v in r["violations"]:
                if v["key"] not in baseline_keys:
                    hard_violations += v["weight"]
        if hard_violations > 0:
            print(f"\n--strict：HARD 档共 {hard_violations} 处不合规（已扣除基线内 {len(baseline_keys)} 项已知欠账），退出码 1。",
                  file=sys.stderr)
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
