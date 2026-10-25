# -*- coding: utf-8 -*-
"""單測：original_char.py、convert_original_char.py、gen_original_derived.py（T68 #417）。

覆蓋：lines.md ⇄ char 逐字節往返（抬頭、挪抬、雙行夾注、單邊夾注、單行小注、闕文、殘字）；
cv 口徑（#419）：格位與空列取自 cord，char → lines → char 逐格相同；不給 cord 時的舊 lines 口徑；
rich.md 生成（標點、分段、實體鏈接、跨列夾注合併、分段處不合併）；pages.json → cord；
轉換腳本 --write --migrate、生成腳本與 --check。
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import convert_original_char as CV  # noqa: E402
import gen_original_derived as G  # noqa: E402
import original_char as C  # noqa: E402
import original_version as OV  # noqa: E402

LINES = (
    "<!-- p1 -->\n"
    "<!-- p3 -->\n"
    "子夏易傳<舊本|卜子>\n"
    "<題|夏撰>內府\n"
    "<!-- p4 -->\n"
    "^藏本:jz[注]{type=单行}[[]]\n"
    "^..經<[[]]乙|丙>\n"
)
# 字序：子0 夏1 易2 傳3 舊4 本5 卜6 子7 題8 夏9 撰10 內11 府12 藏13 本14 注15 □16 經17 □18 乙19 丙20
HREF = "book-index://Work/w1"


def _cell(a, c, **kw):
    return dict({"a": a, "c": c}, **kw)


def punct(*items):
    return {"version": "0.1.0", "punctuations": [
        {"mark": m, "kind": k, "pos": pos, "anchor": a, "pre_char": pc} for m, k, pos, a, pc in items]}


ENTITY = {"version": "0.1.0", "entities": [
    {"id": "e1", "type": "work", "text": "子夏易傳", "anchor": {"start": "3:1:1", "end": "3:1:4"},
     "target": {"status": "matched", "href": HREF}},
    {"id": "e2", "type": "people", "text": "卜子", "anchor": {"start": "3:1:5b", "end": "3:1:6b"},
     "target": {"status": "new_candidate"}},
]}


class TestParseRender(unittest.TestCase):
    def setUp(self):
        self.char = C.make_char(C.parse_lines_md(LINES), "bk", 2, "0.1.0")

    def test_roundtrip(self):
        self.assertEqual(C.render_lines(self.char), LINES)

    def test_slots_same_as_lines_slots(self):
        self.assertEqual(C.char_slots(self.char), OV.lines_slots(LINES))

    def test_cells(self):
        p1, p3, p4 = self.char["pages"]
        self.assertEqual((p1["page"], p1["columns"]), (1, []))
        c1, c2 = p3["columns"]
        self.assertEqual(c1["cells"][4:8], [_cell("3:1:5a", "舊"), _cell("3:1:6a", "本"),
                                            _cell("3:1:5b", "卜"), _cell("3:1:6b", "子")])
        self.assertEqual(c2["cells"][:3], [_cell("3:2:1a", "題"), _cell("3:2:1b", "夏"), _cell("3:2:2b", "撰")])
        self.assertEqual(c2["cells"][3], _cell("3:2:3", "內"))
        a, b = p4["columns"]
        self.assertEqual((a.get("raised"), a.get("lead_blank")), (1, None))
        self.assertEqual(a["cells"], [_cell("4:1:-1", "藏"), _cell("4:1:1", "本"),
                                      _cell("4:1:2", "注", lane="solo"), _cell("4:1:3", "□", lacuna=True)])
        self.assertEqual((b.get("raised"), b.get("lead_blank")), (1, 2))
        self.assertEqual(b["cells"], [_cell("4:2:3", "經"), _cell("4:2:4a", "□", lacuna=True),
                                      _cell("4:2:5a", "乙"), _cell("4:2:4b", "丙")])

    def test_explicit_lanes_render_same(self):
        for _p, _col, c in C.iter_cells(self.char):
            c["lane"] = C.cell_lane(c)
        self.assertEqual(C.render_lines(self.char), LINES)

    def test_blank_column_no_line(self):
        # 空列不出行（同 cv char_to_lines_md、现有 lines.md）
        self.char["pages"][1]["columns"].append({"col": 3, "kind": "blank", "cells": []})
        self.assertEqual(C.render_lines(self.char), LINES)

    def test_single_half_jz_and_guess(self):
        text = "<!-- p1 -->\n甲<乙丙>□{guess=春}:jz[丁□]{type=单行}\n"
        char = C.make_char(C.parse_lines_md(text), "bk", 1, "0.1.0")
        cells = char["pages"][0]["columns"][0]["cells"]
        self.assertEqual(cells[1:3], [_cell("1:1:2a", "乙"), _cell("1:1:3a", "丙")])
        self.assertEqual(cells[3], _cell("1:1:4", "春", guess=True))
        self.assertEqual(cells[5], _cell("1:1:6", "□", lane="solo", lacuna=True))   # 小注里的 □ 是阙文
        self.assertEqual(C.render_lines(char), text)

    def test_unsupported(self):
        for bad in ("<!-- p1 -->\n甲[[乙]]\n", "<!-- p1 -->\n甲<|乙>\n", "<!-- p1 -->\n甲:zi[⿰木木]\n",
                    "<!-- p1 -->\n甲:jz[乙]{type=x}\n", "甲\n", "<!-- p1 -->\n甲 乙\n", "<!-- p1 -->\n甲{殘}\n"):
            with self.assertRaises(C.FormatError, msg=bad):
                C.parse_lines_md(bad)


class TestRich(unittest.TestCase):
    def setUp(self):
        self.char = C.make_char(C.parse_lines_md(LINES), "bk", 2, "0.1.0")

    def test_rich(self):
        p = punct(("《", "point", "before", "3:1:1", "子"), ("》", "point", "after", "3:1:4", "傳"),
                  ("。", "point", "after", "4:2:5a", "乙"),
                  ("，", "point", "after", "3:2:2b", "撰"), ("\n\n", "break", "after", "3:2:4", "府"),
                  ("。", "point", "after", "4:1:3", "□"))
        got = C.render_rich(self.char, p, ENTITY)
        self.assertEqual(got, f"<!-- p3 -->《[子夏易傳]({HREF})》<舊本/卜子/題夏撰，>內府\n\n"
                              "<!-- p4 -->藏本:jz[注]{type=单行}[[]]。經<[[]]乙。丙>\n")

    def test_adjacent_entities_use_directive(self):
        def ent(i, a, b, text, linked=False):
            e = {"id": i, "type": "people", "text": text, "anchor": {"start": a, "end": b}, "target": {"status": "new_candidate"}}
            if linked:
                e["target"] = {"status": "matched", "href": HREF}
            return e
        # 子夏｜易傳 紧挨 → 都写指令；带链接的包 [ ](href)
        ents = {"version": "0.1.0", "entities": [ent("a", "3:1:1", "3:1:2", "子夏", True), ent("b", "3:1:3", "3:1:4", "易傳")]}
        got = C.render_rich(self.char, None, ents)
        self.assertTrue(got.startswith(f"<!-- p3 -->[:zm[子夏]]({HREF}):zm[易傳]"), got)
        # 中间隔标点 → 仍是单个专名写法
        p = punct(("，", "point", "after", "3:1:2", "夏"))
        got = C.render_rich(self.char, p, ents)
        self.assertTrue(got.startswith(f"<!-- p3 -->[/子夏/]({HREF})，/易傳/"), got)

    def test_break_stops_jz_merge(self):
        p = punct(("\n\n", "break", "after", "3:1:6b", "子"))
        got = C.render_rich(self.char, p, None)
        self.assertTrue(got.startswith("<!-- p3 -->子夏易傳<舊本卜子>\n\n<題夏撰>內府<!-- p4 -->"), got)

    def test_heading(self):
        # 标题符（punct v0.2）：段首写 `#`× 级别加空格，排在页码注释与其他 before 标点之前；不带 pre_char
        p = punct(("《", "point", "before", "3:1:1", "子"), ("\n\n", "break", "after", "3:1:4", "傳"),
                  ("\n\n", "break", "after", "3:2:4", "府"))
        p["punctuations"] += [{"mark": "#", "kind": "heading", "pos": "before", "anchor": "3:1:1"},
                              {"mark": "##", "kind": "heading", "pos": "before", "anchor": "4:1:1"}]
        got = C.render_rich(self.char, p, None)
        self.assertTrue(got.startswith("# <!-- p3 -->《子夏易傳\n\n<舊本卜子題夏撰>內府\n\n"), got)
        # 4:1:1 前一字没有分段符（校验器会报）：仍另起一行，标题不粘在上一段末尾
        self.assertIn("<!-- p4 -->藏\n\n## 本", got)

    def test_bad_anchor(self):
        with self.assertRaises(C.FormatError):
            C.render_rich(self.char, punct(("，", "point", "after", "3:1:1", "夏")), None)
        with self.assertRaises(C.FormatError):
            C.render_rich(self.char, punct(("，", "point", "after", "9:9:9", "夏")), None)


def pages_json(char, shift=0):
    """仿 cv 导出的旧 pages.json：格位用几何格号（正格号整体 +shift，抬头负格不动），带字；
    每页比 char 多一个没有字的列（cv 口径空列也占号）。"""
    pages = []
    o = 0
    for p in char["pages"]:
        cells = []
        for col in p["columns"]:
            for c in col["cells"]:
                pg, cl, g = c["a"].split(":")
                sub = g[-1] if g[-1] in "ab" else ""
                n = int(g.rstrip("ab"))
                n = n + shift if n > 0 else n
                cells.append({"id": f"g{o}", "a": f"{pg}:{cl}:{n}{sub}", "o": o, "c": c["c"], "box": [o, 0, 10, 10]})
                o += 1
        pages.append({"page_id": f"bk/2/{p['page']}", "page": {"index": p["page"]},
                      "canvas": {"id": f"https://x/canvas/02/{p['page']:04d}"},
                      "regions": [{"id": "r1", "kind": "body", "box": None if not cells else [0, 0, 9, 9],
                                   "rules": [], "columns": ["c1"]}],
                      "columns": [{"id": f"c{k + 1}", "n": k + 1, "kind": "body", "box": [0, 0, 1, 1],
                                   "raised": 0, "lead_blank": 0, "runs": []} for k in range(len(p["columns"]) + 1)],
                      "marks": [{"id": "m1", "kind": "blank", "col": "c1", "slot": 1, "box": [0, 0, 1, 1], "by": "cv"}],
                      "cells": cells, "o": [0, 0]})
    return {"schema": "guji-pages/0.1", "pages": pages}


class TestCord(unittest.TestCase):
    def setUp(self):
        self.char = C.make_char(C.parse_lines_md(LINES), "bk", 2, "0.1.0")

    def test_cord(self):
        pj = pages_json(self.char, shift=2)
        cord = C.pages_to_cord(pj, "bk", 2)
        self.assertEqual([c["a"] for p in cord["pages"] for c in p["cells"]],
                         [c["a"] for p in pj["pages"] for c in p["cells"]])     # 格位照抄 cv 锚点
        p1, p3, _p4 = cord["pages"]
        self.assertNotIn("regions", p1)                       # 无版框（box null）的区域不收
        self.assertEqual(p3["regions"], [{"id": "r1", "kind": "body", "box": [0, 0, 9, 9], "rules": []}])
        self.assertEqual(p3["columns"][0], {"col": 1, "kind": "body", "box": [0, 0, 1, 1]})
        self.assertEqual(p3["marks"], [{"id": "m1", "kind": "blank", "col": 1, "slot": 1, "box": [0, 0, 1, 1]}])
        self.assertEqual(p3["cells"][0], {"a": "3:1:3", "box": [0, 0, 10, 10], "id": "g0"})
        self.assertFalse(any("c" in c for p in cord["pages"] for c in p["cells"]))

    def test_missing_anchor(self):
        pj = pages_json(self.char)
        pj["pages"][1]["cells"][2]["a"] = ""
        with self.assertRaises(C.FormatError):
            C.pages_to_cord(pj, "bk", 2)


class TestCvKeys(unittest.TestCase):
    """cv 口径：格位、空列取自 cord，分行稿给字和版式。"""

    def setUp(self):
        legacy = C.make_char(C.parse_lines_md(LINES), "bk", 2, "0.1.0")
        self.cord = C.pages_to_cord(pages_json(legacy, shift=2), "bk", 2)
        self.char = C.make_char(C.parse_lines_md(LINES, self.cord), "bk", 2, "0.1.0")

    def test_keys_from_cord(self):
        self.assertEqual([a for a, _c in C.char_slots(self.char)],
                         [c["a"] for p in self.cord["pages"] for c in p["cells"]])
        c1 = self.char["pages"][1]["columns"][0]["cells"]
        self.assertEqual(c1[:2], [_cell("3:1:3", "子"), _cell("3:1:4", "夏")])
        a = self.char["pages"][2]["columns"][0]
        self.assertEqual(a["cells"][:2], [_cell("4:1:-1", "藏"), _cell("4:1:3", "本")])
        self.assertEqual(self.char["pages"][1]["columns"][2], {"col": 3, "kind": "blank", "cells": []})

    def test_roundtrip(self):
        text = C.render_lines(self.char)
        self.assertEqual(text, LINES)
        again = C.make_char(C.parse_lines_md(text, self.cord), "bk", 2, "0.1.0")
        self.assertEqual(again, self.char)

    def test_mismatch(self):
        bad = json.loads(json.dumps(self.cord))
        bad["pages"][1]["cells"].pop()
        with self.assertRaises(C.FormatError):
            C.parse_lines_md(LINES, bad)
        bad = json.loads(json.dumps(self.cord))
        bad["pages"][1]["cells"][4]["a"] = "3:1:7"            # 夹注右列「舊」的格位没了子列
        with self.assertRaises(C.FormatError):
            C.parse_lines_md(LINES, bad)


FIG = {"figures": [{"id": "f3-1-2", "kind": "inline", "alt": "左半圈"},
                   {"id": "p4-fig1", "kind": "block", "alt": "河圖"}]}
LINES_FIG = ("<!-- p3 -->\n甲:tu[左半圈]{id=f3-1-2}乙\n丙\n"
             "<!-- p4 -->\n丁\n::tu[河圖]{id=p4-fig1}\n戊\n")
CORD_FIG = {"pages": [
    {"page": 3, "cells": [{"a": "3:1:1"}, {"a": "3:1:2"}, {"a": "3:1:3"}, {"a": "3:2:1"}]},
    {"page": 4, "cells": [{"a": "4:1:1"}, {"a": "4:4:1"}],
     "marks": [{"kind": "figure", "fig": "p4-fig1", "col": 2, "span": 2, "box": [0, 0, 5, 5]}]},
]}


class TestFigure(unittest.TestCase):
    """图片格 `:tu[…]`、图列 `::tu[…]`（GUJI-737，spec 03 §三·5）：char ⇄ lines.md 往返。"""

    def setUp(self):
        self.char = C.make_char(C.parse_lines_md(LINES_FIG, CORD_FIG), "bk", 5, "1.0.0")

    def test_parse(self):
        self.assertEqual(self.char["$schema"], C.CHAR_SCHEMA_FIG)
        p3, p4 = self.char["pages"]
        self.assertEqual(p3["columns"][0]["cells"][1], {"a": "3:1:2", "c": "□", "fig": "f3-1-2"})
        self.assertEqual(p4["columns"], [
            {"col": 1, "cells": [_cell("4:1:1", "丁")]},
            {"col": 2, "kind": "figure", "span": 2, "fig": "p4-fig1", "cells": []},     # 第 3 列被图占住，不另出
            {"col": 4, "cells": [_cell("4:4:1", "戊")]},
        ])
        self.assertEqual([c for _a, c in C.char_slots(self.char)], list("甲□乙丙丁戊"))

    def test_roundtrip(self):
        self.assertEqual(C.render_lines(self.char, FIG), LINES_FIG)
        again = C.make_char(C.parse_lines_md(C.render_lines(self.char, FIG), CORD_FIG), "bk", 5, "1.0.0")
        self.assertEqual(again, self.char)

    def test_without_fig_json(self):
        # 不给 fig.json：图片格写 □、图列不出（同 cv char_to_lines_md 不给 fig）
        self.assertEqual(C.render_lines(self.char), "<!-- p3 -->\n甲□乙\n丙\n<!-- p4 -->\n丁\n戊\n")

    def test_default_alt_and_bad_alt(self):
        self.assertIn(":tu[图形符号]{id=f3-1-2}", C.render_lines(self.char, {"figures": []}))
        with self.assertRaises(C.FormatError):
            C.render_lines(self.char, {"figures": [{"id": "f3-1-2", "alt": "九宫[图]"}]})

    def test_mismatch(self):
        moved = LINES_FIG.replace("丁\n::tu[河圖]{id=p4-fig1}\n戊", "丁\n戊\n::tu[河圖]{id=p4-fig1}")
        with self.assertRaisesRegex(C.FormatError, "位置"):
            C.parse_lines_md(moved, CORD_FIG)
        no_mark = json.loads(json.dumps(CORD_FIG))
        del no_mark["pages"][1]["marks"]
        with self.assertRaisesRegex(C.FormatError, "marks.figure"):
            C.parse_lines_md(LINES_FIG, no_mark)
        with self.assertRaisesRegex(C.FormatError, "没有 ::tu"):
            C.parse_lines_md(LINES_FIG.replace("::tu[河圖]{id=p4-fig1}\n", ""),
                             {"pages": [CORD_FIG["pages"][0], dict(CORD_FIG["pages"][1])]})
        with self.assertRaises(C.FormatError):
            C.parse_lines_md(LINES_FIG.replace("id=f3-1-2", "id=F 1"), CORD_FIG)
        with self.assertRaises(C.FormatError):
            C.parse_lines_md("<!-- p1 -->\n::zz[x]{id=a}\n")

    def test_legacy_lines_keys(self):
        # 不给 cord：每行一列，图列按一列数、不记 span
        char = C.parse_lines_md(LINES_FIG)
        self.assertEqual(char[1]["columns"][1], {"col": 2, "kind": "figure", "fig": "p4-fig1", "cells": []})
        self.assertEqual(char[1]["columns"][2]["cells"], [_cell("4:3:1", "戊")])

    def test_rich(self):
        got = C.render_rich(self.char, None, None, FIG)
        self.assertEqual(got, "<!-- p3 -->甲:tu[左半圈]{id=f3-1-2}乙丙<!-- p4 -->丁\n\n::tu[河圖]{id=p4-fig1}\n\n戊\n")
        self.assertEqual(C.render_rich(self.char), "<!-- p3 -->甲□乙丙<!-- p4 -->丁戊\n")


def quiet(fn, args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(list(args))
    return code, out.getvalue(), err.getvalue()


SCHEMA_DIR = os.environ.get("GUJI_FORMAT_SCHEMAS",
                            os.path.join(HERE, "..", "..", "..", "..", "guji-format", "schemas"))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.od = os.path.join(self.tmp.name, "Book", "a", "b", "c", "bk", "original")
        os.makedirs(self.od)
        char = C.make_char(C.parse_lines_md(LINES), "bk", 2, "0.1.0")
        files = {
            "002.lines.md": LINES, "002.md": "舊 reflow", "002.rich.md": "舊 rich",
            "002.pages.json": json.dumps(pages_json(char), ensure_ascii=False),
            "002.punct.json": json.dumps(punct(("，", "point", "after", "3:2:2b", "撰")), ensure_ascii=False),
            "002.entity.json": json.dumps(ENTITY, ensure_ascii=False),
            "index.json": json.dumps({"book_id": "bk", "chapters": [
                {"n": 2, "file": "002", "title": "卷二", "has_json": False, "lines_file": "002.lines.md",
                 "pages_file": "002.pages.json", "punct_file": "002.punct.json", "entity_file": "002.entity.json",
                 "rich_file": "002.rich.md", "pages": "1-4"}]}, ensure_ascii=False),
        }
        for name, text in files.items():
            with open(os.path.join(self.od, name), "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        self.tmp.cleanup()

    def test_convert_then_generate(self):
        args = [self.od, "--write", "--migrate"]
        if os.path.isdir(SCHEMA_DIR):
            args += ["--schema-dir", SCHEMA_DIR]
        code, out, err = quiet(CV.main, args)
        self.assertEqual(code, 0, err)
        self.assertIn("lines.md 逐字节还原 ✓", out)
        names = sorted(os.listdir(self.od))
        self.assertEqual(names, ["002.char.json", "002.cord.json", "002.entity.json", "002.punct.json", "index.json"])
        ch = OV.load_json(os.path.join(self.od, "index.json"))["chapters"][0]
        self.assertEqual(list(ch), ["n", "file", "title", "char_file", "cord_file", "punct_file", "entity_file",
                                    "pages", "text_version"])
        self.assertEqual(ch["text_version"], "0.1.0")
        self.assertIn('{"a": "3:1:1", "c": "子"}', OV.read_text(os.path.join(self.od, "002.char.json")))

        code, out, _ = quiet(G.main, [self.tmp.name])
        self.assertEqual(code, 0)
        self.assertEqual(OV.read_text(os.path.join(self.od, "002.lines.md")), LINES)
        self.assertTrue(OV.read_text(os.path.join(self.od, "002.rich.md")).startswith(f"<!-- p3 -->《[子夏易傳]({HREF})》"))
        ch = OV.load_json(os.path.join(self.od, "index.json"))["chapters"][0]
        self.assertEqual((ch["lines_file"], ch["rich_file"]), ("002.lines.md", "002.rich.md"))
        code, out, _ = quiet(G.main, [self.od, "--check"])
        self.assertEqual(code, 0)
        self.assertIn("002.rich.md: 逐字节一致", out)

    def test_convert_refuses_mismatch(self):
        pj = OV.load_json(os.path.join(self.od, "002.pages.json"))
        pj["pages"][1]["cells"][0]["c"] = "X"
        OV.dump_json(os.path.join(self.od, "002.pages.json"), pj)
        code, _out, err = quiet(CV.main, [self.od, "--write", "--migrate"])
        self.assertEqual(code, 1)
        self.assertIn("pages.json", err)
        self.assertFalse(os.path.exists(os.path.join(self.od, "002.char.json")))   # 核不过一个文件都不写

    def test_old_punct_skips_rich(self):
        quiet(CV.main, [self.od, "--write", "--migrate"])
        OV.dump_json(os.path.join(self.od, "002.punct.json"),
                     {"punctuations": [{"mark": "，", "kind": "point", "pos": "after", "char_offset": 3}]})
        code, out, _ = quiet(G.main, [self.od])
        self.assertEqual(code, 0)
        self.assertIn("rich 未出", out)
        self.assertNotIn("rich_file", OV.load_json(os.path.join(self.od, "index.json"))["chapters"][0])

    def test_old_form_book_untouched(self):
        # 另一部还是旧形态（没有 char.json）的书：index.json 一个字节都不动
        other = os.path.join(self.tmp.name, "Book", "x", "y", "z", "old", "original")
        os.makedirs(other)
        raw = '{"chapters": [{"n": 1, "file": "001", "lines_file": "001.lines.md", "rich_file": "001.rich.md"}]}'
        with open(os.path.join(other, "index.json"), "w", encoding="utf-8") as f:
            f.write(raw)
        quiet(CV.main, [self.od, "--write", "--migrate"])
        code, out, _ = quiet(G.main, [self.tmp.name])
        self.assertEqual(code, 0)
        self.assertIn("没有 001.char.json，跳过", out)
        self.assertEqual(OV.read_text(os.path.join(other, "index.json")), raw)

    def test_stale_anchor_skips_rich(self):
        quiet(CV.main, [self.od, "--write", "--migrate"])
        OV.dump_json(os.path.join(self.od, "002.punct.json"), punct(("，", "point", "after", "3:2:2b", "甲")))
        code, out, _ = quiet(G.main, [self.od])
        self.assertEqual(code, 0)
        self.assertIn("rich 未出（标点／实体锚点与 char 对不上", out)
        self.assertEqual(OV.read_text(os.path.join(self.od, "002.lines.md")), LINES)


if __name__ == "__main__":
    unittest.main()
