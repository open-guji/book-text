# -*- coding: utf-8 -*-
"""字格永久编号 u：F-OV-18 接进 validate_text_format，bump_original 按 u 核、校验字只报不改（2026-11-24）。"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_bump_original import _read, _write, make_repo, run, V  # noqa: E402
import cell_uid as CU  # noqa: E402


def f18(root):
    report, _s, _t = V.check(root)
    return [v["note"] for v in report["F-OV-18"]["violations"]]


class TestU(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.entry, self.od = make_repo(self.root)
        self.assertEqual(run(self.entry, "--init")[0], 0)

    def tearDown(self):
        self.tmp.cleanup()

    def p(self, line):
        return os.path.join(self.od, f"002.{line}.json")

    def migrate(self):
        c = _read(self.p("char"))
        CU.number_char(c)
        _write(self.p("char"), c)
        for line in ("punct", "entity"):
            d = _read(self.p(line))
            CU.number_layer(c, line, d)
            _write(self.p(line), d)
        return c

    def test_plain_repo_must_migrate(self):
        # 11-24 起以 u 为准：original 的 char 没上 u 即报
        self.assertEqual(len(f18(self.root)), 1)
        self.assertIn("没上 u", f18(self.root)[0])

    def test_cord_cell_id_flagged(self):
        self.migrate()
        c = _read(self.p("char"))
        k = {"$schema": "https://open-guji.org/schema/cord/v0.1.json", "book_id": c["book_id"], "volume": c["volume"],
             "pages": [{"page": pg["page"], "cells": [{"a": x["a"], "box": [0, 0, 1, 1]}
                                                      for col in pg["columns"] for x in col["cells"]]} for pg in c["pages"]]}
        _write(self.p("cord"), k)
        ip = os.path.join(self.od, "index.json")
        idx = _read(ip)
        idx["chapters"][0]["cord_file"] = "002.cord.json"
        _write(ip, idx)
        self.assertEqual(f18(self.root), [])
        k["pages"][0]["cells"][0]["id"] = "g0"
        _write(self.p("cord"), k)
        self.assertTrue(any("cord 有 1 格还带 id" in m for m in f18(self.root)))

    def test_migrated_repo_clean_and_bumps(self):
        self.migrate()
        self.assertEqual(f18(self.root), [])
        code, err = run(self.entry, "--line", "text", "--level", "patch", "--note", "x")
        self.assertEqual(code, 0, err)
        self.assertEqual(_read(self.p("punct"))["text_version"], "1.0.1")

    def test_new_cell_without_u_blocks(self):
        c = self.migrate()
        CU.cells(c)[0].pop("u")
        _write(self.p("char"), c)
        notes = f18(self.root)
        self.assertTrue(any("没有 u" in n for n in notes), notes)
        code, err = run(self.entry, "--line", "text", "--level", "patch", "--note", "x")
        self.assertNotEqual(code, 0)
        self.assertIn("字格永久编号", err)

    def test_layer_missing_u_flags_and_bump_does_not_follow(self):
        self.migrate()
        p = _read(self.p("punct"))
        p["punctuations"][0].pop("u")
        _write(self.p("punct"), p)
        self.assertTrue(any("没写 u" in n for n in f18(self.root)))
        code, err = run(self.entry, "--line", "text", "--level", "patch", "--note", "x")
        self.assertEqual(code, 0, err)
        self.assertEqual(_read(self.p("punct"))["text_version"], "1.0.0")   # 不跟进，列出来
        self.assertEqual(_read(self.p("entity"))["text_version"], "1.0.1")

    def test_bump_never_rewrites_check_chars(self):
        c = self.migrate()
        cell = next(x for x in CU.cells(c) if x["a"] == "3:1:7")
        cell["c"] = "券"                                     # 原地改字，u 不变
        _write(self.p("char"), c)
        run(self.entry, "--line", "text", "--level", "patch", "--note", "x")
        p = _read(self.p("punct"))
        self.assertEqual(p["punctuations"][0]["pre_char"], "卷")  # 只报不改
        self.assertEqual(p["text_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
