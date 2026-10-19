# -*- coding: utf-8 -*-
"""book-text `original` 的 char（guji-format 02）读写与生成（T68 #417）。

- `parse_lines_md(text, cord)`：分行稿 `NNN.lines.md` ＋ 同章 cord → char 的 `pages`。**格位口径是 cv**
  （#419 定，= cv `formats/guji_char_cord.py` 缺省口径）：抬头负格、无第 0 格，行首排除格、列中留白格、
  空列都占号——这些分行稿里看不出来，所以格位 key 和列骨架（含空列）从 cord 按读序取，分行稿只给字、
  夹注／小注分道、抬头挪抬、阙文。不给 cord 时退回旧的 lines 口径（`original_version.lines_slots`，
  只作兼容、核旧数据用）。
- `render_lines`：char → 分行稿，记法与 cv `guji_char_cord.char_to_lines_md`（Step9 9.1）逐字相同：
  空列不出行；单边夹注写 `<x>`；残字 `□{guess=X}`；组字 `:zi[…]`；单行小注里的阙文写「□」。
- `render_rich`：char ＋ punct ＋ entity → `NNN.rich.md`，与 cv `siku_extract.assemble_volume`
  出 rich 的口径一致（照它重写，不 import cv）；
- `pages_to_cord`：旧形态 `NNN.pages.json`（cv 导出，带字）→ cord（不带字，格位照抄 pages.json 的 cv 锚点）。
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from original_version import dump_compact, dumps_compact  # noqa: E402,F401  写盘一格一行

CHAR_SCHEMA = "https://open-guji.org/schema/char/v0.1.json"
CORD_SCHEMA = "https://open-guji.org/schema/cord/v0.1.json"
SOLO_ATTR = "{type=单行}"
LACUNA = "[[]]"
BOX = "□"

_PAGE = re.compile(r"^<!--\s*p(\d+)\s*-->$")
_PREFIX = re.compile(r"^(\^*)(\.*)")
_UNIT = re.compile(
    r"<(?P<jz>[^<>]*)>"
    r"|:jz\[(?P<dj>[^\]]*)\](?P<djattr>\{[^}]*\})?"
    r"|:zi\[(?P<zi>[^\]]*)\]"
    r"|(?P<gap>\[\[[^\]]*\]\])"
    r"|□\{guess=(?P<guess>[^}]*)\}"
    r"|(?P<ch>.)", re.S)
_INNER = re.compile(r":zi\[(?P<zi>[^\]]*)\]|(?P<gap>\[\[[^\]]*\]\])|□\{guess=(?P<guess>[^}]*)\}|(?P<ch>.)", re.S)
_KEY = re.compile(r"^(\d+):(\d+):(-?[1-9]\d*)([ab]?)$")


class FormatError(ValueError):
    """分行稿里有 char 记不下、或转回去不能逐字节还原的写法；或分行稿与 cord 对不上。"""


def _next_grid(g):
    return 1 if g == -1 else g + 1


def _adv(g, n):
    for _ in range(n):
        g = _next_grid(g)
    return g


def _unit_cell(m, where, *, in_solo=False):
    """一个记号单元 → 格的字段（不含 a）。"""
    if m.group("gap") is not None:
        if m.group("gap") != LACUNA:
            raise FormatError(f"{where}: 阙文里有字 {m.group('gap')!r}，char 记不下")
        return {"c": BOX, "lacuna": True}
    if m.group("zi") is not None:
        raise FormatError(f"{where}: 组字 :zi[{m.group('zi')}] 在分行稿里不带近似字，还原不出 char 的 c")
    if m.group("guess") is not None:
        return {"c": m.group("guess"), "guess": True}
    ch = m.group("ch")
    if ch.isspace() or ch in "<>|[]{}":
        raise FormatError(f"{where}: 有记号字符 {ch!r}")
    if ch == BOX and in_solo:
        return {"c": BOX, "lacuna": True}           # Step9 在 :jz[…] 里把阙文写成「□」（cv 已知例外）
    return {"c": ch}


def _inner(s, where, *, in_solo=False):
    return [_unit_cell(m, where, in_solo=in_solo) for m in _INNER.finditer(s)]


def _line_cells(body, where):
    """一行正文 → [(格字段, 分道)]，读序；分道 main／solo／a／b。"""
    out = []
    for u in _UNIT.finditer(body):
        if u.group("jz") is not None:
            first, sep, second = u.group("jz").partition("|")
            if sep and (not first or not second):
                raise FormatError(f"{where}: 夹注有一半是空的却写了 |")
            if sep:
                out += [(c, "a") for c in _inner(first, where)] + [(c, "b") for c in _inner(second, where)]
            else:
                # 单边夹注 `<x>`：分不出左右（记 j），lines 口径记 a，cv 口径看 cord 的 key 后缀
                out += [(c, "j") for c in _inner(first, where)]
        elif u.group("dj") is not None:
            if (u.group("djattr") or "") != SOLO_ATTR:
                raise FormatError(f"{where}: 单行小注属性不是 {SOLO_ATTR}：{u.group(0)!r}")
            out += [(c, "solo") for c in _inner(u.group("dj"), where, in_solo=True)]
        else:
            out.append((_unit_cell(u, where), "main"))
    return out


def _lines_keys(page, col, raised, dots, cells):
    """旧 lines 口径的格位（= original_version.lines_slots）。"""
    g = (dots + 1) if dots else (-raised if raised else 1)
    keys = []
    k = 0
    while k < len(cells):
        lane = cells[k][1]
        if lane in ("a", "b", "j"):
            j = k
            while j < len(cells) and cells[j][1] in ("a", "b", "j"):
                j += 1
            na = sum(1 for _c, ln in cells[k:j] if ln != "b")
            nb = (j - k) - na
            keys += [f"{page}:{col}:{_adv(g, i)}a" for i in range(na)]
            keys += [f"{page}:{col}:{_adv(g, i)}b" for i in range(nb)]
            g = _adv(g, max(na, nb))
            k = j
        else:
            keys.append(f"{page}:{col}:{g}")
            g = _next_grid(g)
            k += 1
    return keys


def _cord_skeleton(cord):
    """cord → {页: (列号表, [格位 key…])}；列号表含没有字的列（cord.columns 与格位里出现过的列取并集）。"""
    out = {}
    for p in cord.get("pages") or []:
        keys = [c["a"] for c in p.get("cells") or []]
        cols = {c["col"] for c in p.get("columns") or []}
        for a in keys:
            m = _KEY.match(a)
            if not m:
                raise FormatError(f"cord 格位 key 不对：{a!r}")
            cols.add(int(m.group(2)))
        out[p["page"]] = (sorted(cols), keys)
    return out


def parse_lines_md(text, cord=None):
    """分行稿全文（＋cord）→ char 的 `pages` 列表。给 cord 是 cv 口径（见模块头），不给是旧 lines 口径。"""
    pages, cur, lines_of = [], None, {}
    for ln, raw in enumerate(text.split("\n"), 1):
        if raw == "":
            continue
        if raw != raw.strip():
            raise FormatError(f"第 {ln} 行首尾有空白")
        pm = _PAGE.match(raw)
        if pm:
            if raw != f"<!-- p{pm.group(1)} -->":
                raise FormatError(f"第 {ln} 行页码写法不规范：{raw!r}")
            cur = {"page": int(pm.group(1)), "columns": []}
            pages.append(cur)
            lines_of[cur["page"]] = []
            continue
        if cur is None:
            raise FormatError(f"第 {ln} 行在第一个页码标记之前")
        mp = _PREFIX.match(raw)
        lines_of[cur["page"]].append((ln, len(mp.group(1)), len(mp.group(2)),
                                      _line_cells(raw[mp.end():], f"第 {ln} 行")))
    skel = _cord_skeleton(cord) if cord is not None else None
    if skel is not None and set(skel) != set(lines_of):
        raise FormatError(f"分行稿与 cord 的页不一致：只在分行稿 {sorted(set(lines_of) - set(skel))[:5]}，"
                          f"只在 cord {sorted(set(skel) - set(lines_of))[:5]}")
    for page in pages:
        pn = page["page"]
        if skel is None:
            cols_with_text = list(range(1, len(lines_of[pn]) + 1))
            all_cols, keys = cols_with_text, None
        else:
            all_cols, keys = skel[pn]
            seen = []
            for a in keys:
                c = int(_KEY.match(a).group(2))
                if not seen or seen[-1] != c:
                    if c in seen:
                        raise FormatError(f"p{pn}: cord 的格位不按列读序（列 {c} 断开）")
                    seen.append(c)
            cols_with_text = seen
            n_cells = sum(len(x[3]) for x in lines_of[pn])
            if len(cols_with_text) != len(lines_of[pn]) or n_cells != len(keys):
                raise FormatError(f"p{pn}: 分行稿 {len(lines_of[pn])} 行 {n_cells} 字，cord 有字的列 "
                                  f"{len(cols_with_text)} 列、{len(keys)} 格，对不上")
        text_col = dict(zip(cols_with_text, lines_of[pn]))
        ki = 0
        for col in all_cols:
            column = {"col": col}
            if col not in text_col:
                column["kind"] = "blank"
                column["cells"] = []
                page["columns"].append(column)
                continue
            ln, raised, dots, cells = text_col[col]
            if raised:
                column["raised"] = raised
            if dots:
                column["lead_blank"] = dots
            if keys is None:
                ks = _lines_keys(pn, col, raised, dots, cells)
            else:
                ks = keys[ki:ki + len(cells)]
                ki += len(cells)
            out = []
            for (fields, lane), a in zip(cells, ks):
                m = _KEY.match(a)
                if keys is not None and (int(m.group(1)), int(m.group(2))) != (pn, col):
                    raise FormatError(f"第 {ln} 行：cord 格位 {a} 不在 p{pn} 第 {col} 列")
                sub = m.group(4)
                if lane == "solo":
                    if sub:
                        raise FormatError(f"第 {ln} 行：单行小注的格位 {a} 带了子列")
                elif lane == "main":
                    if sub:
                        raise FormatError(f"第 {ln} 行：正文的格位 {a} 带了子列，cord 和分行稿分道不一致")
                elif not sub or (lane != "j" and sub != lane):
                    raise FormatError(f"第 {ln} 行：夹注{'右' if lane == 'a' else '左' if lane == 'b' else ''}列的格位 {a} 子列不对")
                cell = {"a": a, "c": fields["c"]}
                if lane == "solo":
                    cell["lane"] = "solo"
                for k in ("lacuna", "guess"):
                    if fields.get(k):
                        cell[k] = True
                out.append(cell)
            column["cells"] = out
            page["columns"].append(column)
    return pages


# ── char 读取 ───────────────────────────────────────────────────────────

def cell_lane(cell):
    """格的 lane：显式 `lane` 优先，否则按格位后缀 a／b 推出夹注，其余为 main。"""
    lane = cell.get("lane")
    if lane:
        return lane
    a = cell["a"]
    if a.endswith("a"):
        return "jz_r"
    if a.endswith("b"):
        return "jz_l"
    return "main"


def iter_cells(char):
    """按读序逐格：(page, column, cell)。"""
    for page in char.get("pages") or []:
        for column in page.get("columns") or []:
            for cell in column.get("cells") or []:
                yield page, column, cell


from original_version import char_slots  # noqa: E402,F401  char → [(格位, 字)]，按读序


def _runs(cells):
    """一列的格 → [(kind, [cell…])]，kind 为 main／solo／jz；jz 一段 = 连续的 a 再连续的 b。"""
    runs = []
    for cell in cells:
        lane = cell_lane(cell)
        kind = "jz" if lane in ("jz_r", "jz_l") else lane
        if kind not in ("main", "solo", "jz"):
            raise FormatError(f"{cell['a']}: 不认识的 lane {lane!r}")
        if runs and runs[-1][0] == kind:
            if kind == "jz" and lane == "jz_r" and cell_lane(runs[-1][1][-1]) == "jz_l":
                runs.append((kind, [cell]))           # b 之后又来 a：新一段夹注
            else:
                runs[-1][1].append(cell)
        else:
            runs.append((kind, [cell]))
    return runs


def _glyph(cell, in_solo=False):
    """一格在分行稿／rich 里的写法（同 cv `guji_char_cord._tok`）。"""
    if cell.get("lacuna"):
        return BOX if in_solo else LACUNA
    if cell.get("zi") is not None:
        return f":zi[{cell['zi']}]"
    if cell.get("guess"):
        return f"□{{guess={cell['c']}}}"
    return cell["c"]


def _column_body(column):
    out = []
    for kind, cells in _runs(column.get("cells") or []):
        if kind == "main":
            out.extend(_glyph(c) for c in cells)
        elif kind == "solo":
            out.append(":jz[" + "".join(_glyph(c, True) for c in cells) + "]" + SOLO_ATTR)
        else:
            a = "".join(_glyph(c) for c in cells if cell_lane(c) == "jz_r")
            b = "".join(_glyph(c) for c in cells if cell_lane(c) == "jz_l")
            out.append(f"<{a}|{b}>" if a and b else f"<{a}{b}>")
    return "".join(out)


def _is_blank_column(column):
    return not column.get("cells")


def render_lines(char):
    """char → 分行稿全文（末尾带换行）。没有字的列不出行（同 cv `char_to_lines_md`、现有 lines.md）。"""
    out = []
    for page in char.get("pages") or []:
        out.append(f"<!-- p{page['page']} -->")
        for column in page.get("columns") or []:
            if _is_blank_column(column):
                continue
            out.append("^" * column.get("raised", 0) + "." * column.get("lead_blank", 0) + _column_body(column))
    return "\n".join(out) + "\n"


# ── rich.md ─────────────────────────────────────────────────────────────

_OPEN_JZ, _CLOSE_JZ = "<", ">"


def _render_tokens(char, break_after):
    """char → [(原文片段, 字)]，字为空串的是版面记号。口径同 cv reflow 后的段落拼接：
    夹注去掉 |；页码标记放在每页第一列前（没有字的页不出）；上一段夹注紧接下一段夹注、
    中间没有分段的，合成一条（cv reflow 的跨列夹注合并）。`break_after` 是分段处的字下标集合。"""
    toks = []
    idx = 0
    for page in char.get("pages") or []:
        first = True
        for column in page.get("columns") or []:
            if _is_blank_column(column):
                continue
            if first:
                toks.append((f"<!-- p{page['page']} -->", ""))
                first = False
            for kind, cells in _runs(column["cells"]):
                if kind == "jz":
                    if toks and toks[-1] == (_CLOSE_JZ, "") and (idx - 1) not in break_after:
                        toks.pop()                       # 与上一条夹注合并
                    else:
                        toks.append((_OPEN_JZ, ""))
                    ordered = ([c for c in cells if cell_lane(c) == "jz_r"]
                               + [c for c in cells if cell_lane(c) == "jz_l"])
                elif kind == "solo":
                    toks.append((":jz[", ""))
                    ordered = cells
                else:
                    ordered = cells
                for c in ordered:
                    toks.append((_glyph(c, kind == "solo"), c["c"]))
                    idx += 1
                if kind == "jz":
                    toks.append((_CLOSE_JZ, ""))
                elif kind == "solo":
                    toks.append(("]" + SOLO_ATTR, ""))
    return toks


def _punct_order(p, off):
    """同一字上的先后（同 cv `punct_order`）：标题符最先，before 在 after 前、分段符最后；
    before 里《排在「后，after 里》排在最前。"""
    inner = (p["mark"] == "《") if p["pos"] == "before" else (p["mark"] != "》")
    return (off, p.get("kind") != "heading", p["pos"] != "before", p["kind"] == "break", inner)


def resolve_offsets(char, items, key):
    """伴生层条目的格位 → 字下标；`key(item)` 给出格位。对不上的抛 FormatError。"""
    pos = {a: i for i, (a, _c) in enumerate(char_slots(char))}
    out = []
    for i, it in enumerate(items):
        a = key(it)
        if a not in pos:
            raise FormatError(f"第 {i} 条的格位 {a!r} 不在 char 里")
        out.append(pos[a])
    return out


def render_rich(char, punct=None, entity=None):
    """char ＋ punct ＋ entity → rich.md 全文（末尾带换行）。"""
    slots = char_slots(char)
    puncts = list((punct or {}).get("punctuations") or [])
    p_off = resolve_offsets(char, puncts, lambda p: p.get("anchor"))
    for p, off in zip(puncts, p_off):
        if "pre_char" in p and slots[off][1] != p["pre_char"]:
            raise FormatError(f"标点 {p['anchor']} 校验字应为 {p['pre_char']!r}，char 为 {slots[off][1]!r}")
    order = sorted(range(len(puncts)), key=lambda k: _punct_order(puncts[k], p_off[k]))
    ents = list((entity or {}).get("entities") or [])
    e_s = resolve_offsets(char, ents, lambda e: (e.get("anchor") or {}).get("start"))
    e_e = resolve_offsets(char, ents, lambda e: (e.get("anchor") or {}).get("end"))
    for e, s, t in zip(ents, e_s, e_e):
        got = "".join(c for _a, c in slots[s:t + 1])
        if "text" in e and got != e["text"]:
            raise FormatError(f"实体 {e.get('id')} 校验字应为 {e['text']!r}，char 为 {got!r}")

    break_after = {p_off[k] for k in order if puncts[k]["kind"] == "break"}
    tokens = _render_tokens(char, break_after)

    punct_map = {}
    for k in order:
        punct_map.setdefault(p_off[k], []).append(puncts[k])
    ent_starts, ent_ends = {}, {}
    for e, s, t in zip(ents, e_s, e_e):
        ent_starts[s] = e
        ent_ends[t] = e
    # 书名两层都记：与 work 实体同位的《》由实体包装出，这里跳过免得重出
    work_open = {s for e, s in zip(ents, e_s) if e["type"] == "work"}
    work_close = {t for e, t in zip(ents, e_e) if e["type"] == "work"}
    for k, ps in list(punct_map.items()):
        punct_map[k] = [p for p in ps
                        if not (p["mark"] == "《" and p["pos"] == "before" and k in work_open)
                        and not (p["mark"] == "》" and p["pos"] == "after" and k in work_close)]

    def linked(e):
        t = e.get("target") or {}
        return t.get("status") == "matched" and t.get("href")

    # 相邻专名（spec/03 §四第 6 条）：两个以上非 work 专名紧挨、中间无字无标点，
    # 这一串里每个都写指令 `:zm[甲]`，带链接写 `[:zm[甲]](href)`；只看紧挨，不看 group
    def _punct_between(k):
        """第 k 格与第 k+1 格之间有无标点（含分段）"""
        return (any(p["pos"] == "after" for p in punct_map.get(k, ()))
                or any(p["pos"] == "before" for p in punct_map.get(k + 1, ())))

    adjacent = set()
    for t, e in ent_ends.items():
        n = ent_starts.get(t + 1)
        if (n is not None and e["type"] != "work" and n["type"] != "work"
                and not _punct_between(t)):
            adjacent.update((id(e), id(n)))

    out, pending_marks, pending_breaks = [], [], []

    def flush_marks(heading=None):
        # 版面记号的次序：先收小注（`>`、`]{…}`），再分段，再标题（`#`× 级别加空格，须在行首），再页码标记／开小注
        k = 0
        while k < len(pending_marks) and pending_marks[k][:1] in (">", "]"):
            k += 1
        out.extend(pending_marks[:k])
        out.extend(pending_breaks)
        if heading:
            if out and not out[-1].endswith("\n"):
                out.append("\n\n")   # 标题前没有分段符（校验器 F-OV-12 会报）：仍保证另起一行
            out.append(heading)
        out.extend(pending_marks[k:])
        pending_marks.clear()
        pending_breaks.clear()

    pi = 0
    for orig, ch in tokens:
        if ch == "":
            pending_marks.append(orig)
            continue
        here = punct_map.get(pi, ())
        head = next((p for p in here if p.get("kind") == "heading"), None)
        flush_marks(head["mark"] + " " if head else None)
        for p in here:
            if p["pos"] == "before" and p.get("kind") != "heading":
                out.append(p["mark"])
        if pi in ent_starts:
            e = ent_starts[pi]
            if e["type"] == "work":
                out.append("《" + ("[" if linked(e) else ""))
            elif id(e) in adjacent:
                out.append("[:zm[" if linked(e) else ":zm[")
            else:
                out.append("[/" if linked(e) else "/")
        out.append(orig)
        if pi in ent_ends:
            e = ent_ends[pi]
            if e["type"] == "work":
                out.append((f"]({e['target']['href']})" if linked(e) else "") + "》")
            elif id(e) in adjacent:
                out.append(f"]](" + e['target']['href'] + ")" if linked(e) else "]")
            else:
                out.append(f"/]({e['target']['href']})" if linked(e) else "/")
        for p in punct_map.get(pi, ()):
            if p["pos"] == "after":
                (pending_breaks if p["kind"] == "break" else out).append(p["mark"])
        pi += 1
    flush_marks()
    return "".join(out) + "\n"


# ── pages.json（旧形态，cv 导出）→ cord ─────────────────────────────────

def _col_no(v):
    if isinstance(v, int):
        return v
    m = re.fullmatch(r"c(\d+)", str(v))
    if not m:
        raise FormatError(f"列号写法不认识：{v!r}")
    return int(m.group(1))


def pages_to_cord(pages_json, book_id, volume):
    """pages.json → cord：去掉字和 cv 内部字段，格位照抄 pages.json 的 cv 锚点（`a`），读序不变。
    pages.json 里格按字偏移 `o` 排序（同 cv `_cells_by_col`）。"""
    pages = []
    for p in pages_json["pages"]:
        page_no = p["page"]["index"] if isinstance(p.get("page"), dict) else p["page"]
        out = {"page": page_no}
        for key in ("image", "canvas", "producers"):
            if key in p:
                out[key] = p[key]
        # 没测出版框的区域（封面、扉页，box 为 null）不收：schema 要求有框
        regions = [{x: r[x] for x in ("id", "kind", "box", "rules") if x in r}
                   for r in p.get("regions") or [] if r.get("box") is not None]
        if regions:
            out["regions"] = regions
        if p.get("columns"):
            cols = []
            for c in p["columns"]:
                d = {"col": c["n"], "kind": c.get("kind", "body"), "box": c["box"]}
                if c.get("note"):
                    d["note"] = c["note"]
                cols.append(d)
            out["columns"] = cols
        cells = []
        for oc in sorted(p["cells"], key=lambda c: c["o"] if isinstance(c["o"], int) else c["o"][0]):
            if not oc.get("a"):
                raise FormatError(f"p{page_no} 字「{oc.get('c')}」没有锚点")
            d = {"a": oc["a"], "box": oc["box"]}
            if oc.get("id"):
                d["id"] = oc["id"]
            cells.append(d)
        out["cells"] = cells
        if p.get("marks"):
            marks = []
            for m in p["marks"]:
                d = {x: v for x, v in m.items() if x != "by"}
                if "col" in d:
                    d["col"] = _col_no(d["col"])
                marks.append(d)
            out["marks"] = marks
        pages.append(out)
    return {"$schema": CORD_SCHEMA, "book_id": book_id, "volume": volume, "pages": pages}


def make_char(pages, book_id, volume, version):
    return {"$schema": CHAR_SCHEMA, "version": version, "book_id": book_id, "volume": volume, "pages": pages}

