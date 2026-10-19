# -*- coding: utf-8 -*-
"""book-text `original` 三线版本号的公共部分（T67 #400）。

规范：项目进展/古籍文本/整体设计/2026-10-文本版本号与仓库流程.md（v2）。
validate_text_format.py（规则 F-OV-*）和 scripts/book-text/bump_original.py 共用本模块。

数据落点（每册 = original/ 下 index.json 的一个章条目；文件体系见 book-text docs/ORIGINAL.md，10-06 用户定）：
    original/index.json   chapters[]：{"n", "file": "002", "char_file", …, "text_version", "punct_version", "entity_version"}
                          三个 *_version 都是镜像
    original/NNN.char.json     文本线（guji-format 02）：顶层 "version"；major ≥2 时顶层另带 "review": {验收记录}
    original/NNN.punct.json    顶层 "version"（标点线）＋ "text_version"（对着哪一版文本做的）
    original/NNN.entity.json   同上（实体线）；major ≥2 时顶层另带 "review": {验收记录}
    original/CHANGES.md        每次升版本一行
（10-06 以前文本线跟踪 NNN.lines.md、验收记录在 index.json 的 text_review；T68 #417 起改读 char，
lines.md 只在生成分支上，由 char 生成。）

锚点校验字：
    punct  每条 {"anchor": "页:列:格[子列]", "pre_char": 该格的字}
    entity 每条 {"anchor": {"start", "end"}, "text": start..end 之间的字}
锚点按 char 的格位 key 对；start..end 之间的字按 char 的 cells 读序取。
`lines_slots` 留给旧形态转换（convert_original_char.py）核对：口径与 open-guji-cv
`render/siku_extract.parse_lines_md` 一致（空行不占列，双行夹注 `<甲|乙>` 的前一半（右列，先读）子列 a、
后一半（左列）子列 b，超框抬头负格位、无第 0 格，`[[…]]`／`□` 记作 □）。
"""
from __future__ import annotations

import json
import os
import re

LINES = ("text", "punct", "entity")
MIN_TEXT_0X = (0, 1, 0)  # 三线最低版本；文本线在 main 上可停在 0.x（精校前），标点、实体此时也从 0.1.0 起（10-18 用户定），0.0.x 不存在
MAX_MAJOR = 3  # major＝质量等级：1 可用／2 出版级／3 定本；guji-format 04/05 schema 同口径
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# 验收记录（major ≥2）至少要有的键：日期、签核人、抽检数据
REVIEW_KEYS = ("date", "signed_by", "sample")


def parse_version(v):
    """'1.4.1' → (1, 4, 1)；不合格式返回 None。"""
    if not isinstance(v, str):
        return None
    m = VERSION_RE.match(v)
    return tuple(int(x) for x in m.groups()) if m else None


def fmt_version(t):
    return ".".join(str(x) for x in t)


def bump(v, level):
    """按 patch／minor 升一级；major 不在此处理（要手工改并附验收记录）。"""
    t = parse_version(v)
    if t is None:
        raise ValueError(f"版本号格式不对：{v!r}")
    if level == "patch":
        return fmt_version((t[0], t[1], t[2] + 1))
    if level == "minor":
        return fmt_version((t[0], t[1] + 1, 0))
    raise ValueError(f"脚本不支持 level={level!r}")


def proofing_expected(text_ver):
    """文本线 major＝0（粗校完、精校未完）时，章条目必须带 proofing: true。"""
    t = parse_version(text_ver)
    return t is not None and t[0] == 0


def review_missing(rec):
    """验收记录缺了哪些键；rec 不是 dict 时视为全缺。"""
    if not isinstance(rec, dict):
        return list(REVIEW_KEYS)
    return [k for k in REVIEW_KEYS if not rec.get(k)]


def is_original_dir(vdir):
    vdir = os.path.normpath(vdir)
    if os.path.basename(vdir) == "original":
        return True
    # 用户 10-07 定：default 可以就是 original，由条目 manifest 的版本 is_original 声明
    try:
        import json
        with open(os.path.join(os.path.dirname(vdir), "manifest.json"), encoding="utf-8") as f:
            for v in json.load(f).get("versions", []):
                if v.get("key") == os.path.basename(vdir) and v.get("is_original"):
                    return True
    except (OSError, ValueError):
        pass
    return False


def companion_path(odir, file, line):
    """某册某线的数据文件路径。"""
    suffix = {"text": "char.json", "punct": "punct.json", "entity": "entity.json"}[line]
    return os.path.join(odir, f"{file}.{suffix}")


def chapter_file(ch):
    """index.json 章条目 → 文件前缀（'002'）。缺 file 时按 n 补三位。"""
    if ch.get("file"):
        return str(ch["file"])
    if isinstance(ch.get("n"), int):
        return f"{ch['n']:03d}"
    return None


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── 写盘：一格一行 ───────────────────────────────────────────────────────

def _flat(v):
    if isinstance(v, dict):
        return all(not isinstance(x, dict) and _flat(x) for x in v.values())
    if isinstance(v, list):
        return all(not isinstance(x, dict) and _flat(x) for x in v)
    return True


def dumps_compact(obj, indent=0):
    """JSON：只含标量（及标量数组）的对象、数组写在一行（如一格 `{"a": …, "c": …}`、一个框），
    其余逐层缩进两格。比 indent=2 小一半多，diff 也是一格一行。"""
    pad, pad1 = "  " * indent, "  " * (indent + 1)
    if _flat(obj) or not isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))
    if isinstance(obj, dict):
        items = [f"{pad1}{json.dumps(k, ensure_ascii=False)}: {dumps_compact(v, indent + 1)}" for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}" if items else "{}"
    items = [pad1 + dumps_compact(v, indent + 1) for v in obj]
    return "[\n" + ",\n".join(items) + "\n" + pad + "]" if items else "[]"


def dump_compact(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps_compact(obj) + "\n")


# ── lines.md → 坐标 → 字（与 cv parse_lines_md 同口径）──────────────────────

_PAGE = re.compile(r"^<!--\s*p(\d+)\s*-->$")
_PREFIX = re.compile(r"^(\^*)(\.*)")
_UNIT = re.compile(
    r"<(?P<jz>[^<>]*)>"
    r"|:jz\[(?P<dj>[^\]]*)\](?:\{[^}]*\})?"
    r"|(?P<gap>\[\[[^\]]*\]\])"
    r"|(?P<box>□(?:\{[^}]*\})?)"
    r"|(?P<ch>.)", re.S)
_INNER = re.compile(r"(?P<gap>\[\[[^\]]*\]\])|(?P<box>□(?:\{[^}]*\})?)|(?P<ch>.)", re.S)


def _inner_chars(s):
    out = []
    for m in _INNER.finditer(s):
        if m.group("ch") is not None:
            if not m.group("ch").isspace():
                out.append(m.group("ch"))
        else:
            out.append("□")
    return out


def _next_grid(g):
    return 1 if g == -1 else g + 1


def lines_slots(text):
    """lines.md 全文 → [(坐标, 字)]，按字流顺序。"""
    slots = []
    page, col = 0, 0
    for raw in text.splitlines():
        line = raw.strip()
        pm = _PAGE.match(line)
        if pm:
            page, col = int(pm.group(1)), 0
            continue
        if not line:
            continue
        col += 1
        mp = _PREFIX.match(line)
        raised, dots = len(mp.group(1)), len(mp.group(2))
        body = line[mp.end():]
        g = (dots + 1) if dots else (-raised if raised else 1)
        for u in _UNIT.finditer(body):
            if u.group("jz") is not None:
                # `<甲|乙>`：甲是右列（先读）→ a，乙是左列 → b
                first, _, second = u.group("jz").partition("|")
                lc, rc = _inner_chars(first), _inner_chars(second)
                ga = gb = g
                for c in lc:
                    slots.append((f"{page}:{col}:{ga}a", c))
                    ga = _next_grid(ga)
                for c in rc:
                    slots.append((f"{page}:{col}:{gb}b", c))
                    gb = _next_grid(gb)
                for _ in range(max(len(lc), len(rc))):
                    g = _next_grid(g)
            elif u.group("dj") is not None:
                for c in _inner_chars(u.group("dj")):
                    slots.append((f"{page}:{col}:{g}", c))
                    g = _next_grid(g)
            elif u.group("gap") is not None or u.group("box") is not None:
                slots.append((f"{page}:{col}:{g}", "□"))
                g = _next_grid(g)
            else:
                ch = u.group("ch")
                if ch.isspace():
                    continue
                slots.append((f"{page}:{col}:{g}", ch))
                g = _next_grid(g)
    return slots


def char_slots(char):
    """char.json → [(格位, 字)]，按 cells 读序（guji-format 02 §三）。"""
    return [(c["a"], c["c"]) for p in char.get("pages") or [] for col in p.get("columns") or []
            for c in col.get("cells") or []]


def anchor_mismatches(char, line, data):
    """伴生层（punct／entity）锚点校验字与当前文本（char.json 的内容）逐个核对，返回对不上的 [(序号, 说明)]。
    没有锚点的条目（流水线对账失败、坐标留空的）不核。"""
    slots = char_slots(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    bad = []
    if line == "punct":
        for i, p in enumerate(data.get("punctuations") or []):
            a = p.get("anchor")
            if not a:
                continue
            if a not in pos:
                bad.append((i, f"标点 #{i} 锚点 {a} 在文本里已不存在"))
            elif "pre_char" in p and slots[pos[a]][1] != p["pre_char"]:
                bad.append((i, f"标点 #{i} 锚点 {a} 校验字应为 {p['pre_char']!r}，文本现为 {slots[pos[a]][1]!r}"))
    elif line == "entity":
        for i, e in enumerate(data.get("entities") or []):
            anc = e.get("anchor") or {}
            s, t = anc.get("start"), anc.get("end")
            if not s or not t:
                continue
            if s not in pos or t not in pos or pos[t] < pos[s]:
                bad.append((i, f"实体 #{i} 锚点 {s}–{t} 在文本里已不存在"))
                continue
            got = "".join(c for _a, c in slots[pos[s]:pos[t] + 1])
            if "text" in e and got != e["text"]:
                bad.append((i, f"实体 #{i} {s}–{t} 校验字应为 {e['text']!r}，文本现为 {got!r}"))
    return bad


# ── 标题符（guji-format spec/04 v0.2 §4.2，GUJI-240）──────────────────────────
# punct 里 kind: heading 的条目锚在标题首字前（pos: before），mark 是 1～6 个 #（级别），
# 标题到下一个分段符为止；不写 pre_char（改字不影响标题）。分段符只锚段末字之后（pos: after），
# 在分段处插字时由改字工具判定归前段还是后段、挪不挪分段符。

PUNCT_V02 = "https://open-guji.org/schema/punct/v0.2.json"
PUNCT_KINDS = ("point", "break", "heading")
_HEADING_MARK = re.compile(r"^#{1,6}$")
# 书目条：「[前缀]《书名》N卷…」，卷数起是著录信息（卷数、版本来源），目录只留书名
_BOOK_ENTRY = re.compile(r"^([^《》]*)《([^《》]+)》\s*(?:[〇零一二三四五六七八九十百千]+|不分|無|无)卷")
_TITLE_MARKS = str.maketrans("", "", "《》〈〉")


def heading_label(text):
    """标题原文 → 目录名：书目条只留书名（连前缀，如「新本」）；书名号一律去掉。
    与网站 book-index-ui `headingLabel` 同口径。显式 label 不经过这里。"""
    t = (text or "").strip()
    m = _BOOK_ENTRY.match(t)
    if m:
        t = m.group(1) + m.group(2)
    return t.translate(_TITLE_MARKS).strip()


def _pkind(p):
    return p.get("kind") or "point"


def _ppos(p):
    return p.get("pos") or "after"


def extract_headings(char, punct):
    """char ＋ punct → 本册目录 [{level, label, anchor}]，按读序；只收 toc 不为 false 的标题。
    label：标题符的 label，缺省由标题原文（首字到下一个分段符之间的字，带其间的点号与成对标号）
    经 heading_label 化简：书目条只留书名，去书名号。
    与网站 book-index-ui `headingsFromPunct` 同口径。"""
    puncts = (punct or {}).get("punctuations") or []
    if not any(_pkind(p) == "heading" for p in puncts):
        return []
    by = {}
    for p in puncts:
        by.setdefault(p.get("anchor"), []).append(p)
    out, cur = [], None

    def close():
        nonlocal cur
        if cur is not None:
            h, text, fixed = cur
            if not fixed:
                h["label"] = heading_label(text)
            if h["label"]:
                out.append(h)
        cur = None

    for a, c in char_slots(char):
        here = by.get(a, [])
        head = next((p for p in here if _pkind(p) == "heading" and _ppos(p) == "before"
                     and _HEADING_MARK.match(p.get("mark") or "")), None)
        if head is not None:
            close()
        if head is not None and head.get("toc") is not False:
            label = head.get("label").strip() if isinstance(head.get("label"), str) else ""
            cur = [{"level": len(head["mark"]), "label": label, "anchor": a}, "", bool(label)]
        if cur is not None and not cur[2]:
            cur[1] += "".join(p["mark"] for p in here if _pkind(p) == "point" and _ppos(p) == "before")
            cur[1] += c
            cur[1] += "".join(p["mark"] for p in here if _pkind(p) == "point" and _ppos(p) != "before")
        if any(_pkind(p) == "break" and _ppos(p) != "before" for p in here):
            close()
    close()
    return out


def heading_problems(char, punct):
    """标题符与 v0.2 标点类别的结构检查（F-OV-12），返回 [(说明, sub)]。锚点存在与否由 F-OV-02 管。"""
    puncts = (punct or {}).get("punctuations") or []
    slots = char_slots(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    probs = []
    uses_v02 = False
    ends = set()                     # 段终点：分段符所在字（锚段末字之后）
    heads = []
    seen_head = set()
    for i, p in enumerate(puncts):
        k, ps = _pkind(p), _ppos(p)
        if k not in PUNCT_KINDS:
            probs.append((f"标点 #{i} kind={k!r} 不认识（只许 point／break／heading）", f"kind:{i}"))
            continue
        if ps not in ("before", "after"):
            probs.append((f"标点 #{i} pos={ps!r} 不认识（只许 before／after）", f"pos:{i}"))
            continue
        if k != "heading" and ("label" in p or "toc" in p):
            probs.append((f"标点 #{i} label／toc 只能出现在标题符上", f"label:{i}"))
        if k == "break":
            if p.get("mark") != "\n\n":
                probs.append((f"分段符 #{i} mark 应为 \"\\n\\n\"", f"brkmark:{i}"))
            if ps == "before":
                probs.append((f"分段符 #{i}（{p.get('anchor')}）pos 必须是 after（锚段末字之后）", f"brkpos:{i}"))
                continue
            a = p.get("anchor")
            if a in pos:
                ends.add(pos[a])
        elif k == "heading":
            uses_v02 = True
            a = p.get("anchor")
            if ps != "before":
                probs.append((f"标题符 #{i}（{a}）pos 必须是 before", f"hpos:{i}"))
            if not _HEADING_MARK.match(p.get("mark") or ""):
                probs.append((f"标题符 #{i}（{a}）mark={p.get('mark')!r} 应为 1～6 个 #", f"hmark:{i}"))
                continue
            if "pre_char" in p:
                probs.append((f"标题符 #{i}（{a}）不写 pre_char（改字不影响标题）", f"hpre:{i}"))
            if "label" in p and not (isinstance(p["label"], str) and p["label"].strip()):
                probs.append((f"标题符 #{i}（{a}）label 须为非空字符串", f"hlabel:{i}"))
            if "toc" in p and not isinstance(p["toc"], bool):
                probs.append((f"标题符 #{i}（{a}）toc 须为布尔", f"htoc:{i}"))
            if a in seen_head:
                probs.append((f"标题符 #{i}（{a}）同一格有两个标题符", f"hdup:{i}"))
            seen_head.add(a)
            if a in pos:
                heads.append((pos[a], len(p["mark"]), a, i))
    if uses_v02 and (punct or {}).get("$schema") != PUNCT_V02:
        probs.append((f"用了标题符，$schema 应为 {PUNCT_V02}", "schema"))
    heads.sort()
    prev_level = None
    for n, (off, level, a, i) in enumerate(heads):
        if not (off == 0 or (off - 1) in ends):
            probs.append((f"标题符 #{i}（{a}）前面不是分段处（前一字须带分段符）", f"hstart:{i}"))
        nxt = heads[n + 1][0] if n + 1 < len(heads) else len(slots)
        if not any(off <= e < nxt for e in ends):
            where = "下一个标题之前" if n + 1 < len(heads) else "册末之前"
            probs.append((f"标题符 #{i}（{a}）到{where}没有分段符", f"hend:{i}"))
        if prev_level is not None and level > prev_level + 1:
            probs.append((f"标题符 #{i}（{a}）跳级：{'#' * prev_level} 之后直接是 {'#' * level}", f"hskip:{i}"))
        prev_level = level
    return probs


def sync_headings(odir):
    """把各册 punct 的标题符现算成 index.json 章条目的 `headings`（目录缓存，spec/07 §3.3）。
    有进目录的标题就写，没有就删掉该键；内容不变不动盘。返回 True＝改了 index.json。"""
    ipath = os.path.join(odir, "index.json")
    try:
        idx = load_json(ipath)
    except (OSError, ValueError):
        return False
    changed = False
    for ch in idx.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        stem = chapter_file(ch)
        cpath = companion_path(odir, stem, "text") if stem else None
        ppath = companion_path(odir, stem, "punct") if stem else None
        heads = []
        if cpath and ppath and os.path.isfile(cpath) and os.path.isfile(ppath):
            try:
                punct = load_json(ppath)
                if any(_pkind(p) == "heading" for p in punct.get("punctuations") or []):
                    heads = extract_headings(load_json(cpath), punct)
            except (OSError, ValueError):
                heads = ch.get("headings") or []   # 解析失败由校验器报，这里不动
        if heads:
            if ch.get("headings") != heads:
                ch["headings"] = heads
                changed = True
        elif "headings" in ch:
            del ch["headings"]
            changed = True
    if changed:
        dump_json(ipath, idx)
    return changed
