# -*- coding: utf-8 -*-
"""單測：bump_original.py ＋ validate_text_format.py 的 F-OV-* 規則（T67 #400）。

自造一個最小 book-text：Book/aa/bb/cc/testbook/ 下一個 original 版本、一冊 002，
覆蓋 init、patch、minor、major 拒絕、文本改字後錨點漂移報錯，以及 ≥2 級缺驗收記錄。
T68 #417 起文本線跟蹤 002.char.json（由下面的 lines.md 轉出），lines.md 不再放在 original/ 裏。
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
import bump_original as B  # noqa: E402
import original_char as C  # noqa: E402
import original_version as OV  # noqa: E402
import validate_text_format as V  # noqa: E402

LINES_MD = "<!-- p3 -->\n子夏易傳十一卷\n^內府藏本<舊本題|卜子夏撰>\n"
# 坐標：p3 第 1 列「子夏易傳十一卷」1..7；第 2 列抬一格「內」-1、「府」1…；夾注前半（右列，先讀）a、後半（左列）b


def _write(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if isinstance(obj, str):
            f.write(obj)
        else:
            json.dump(obj, f, ensure_ascii=False)


def _read(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def make_repo(root):
    entry = os.path.join(root, "Book", "aa", "bb", "cc", "testbook")
    od = os.path.join(entry, "original")
    _write(os.path.join(entry, "manifest.json"), {"versions": [{"key": "original", "kind": "original"}]})
    _write(os.path.join(od, "index.json"), {
        "book_id": "testbook", "revision": "1.0.0",
        "chapters": [{"n": 2, "file": "002", "char_file": "002.char.json",
                      "punct_file": "002.punct.json", "entity_file": "002.entity.json"}],
        "source": {"name": "本项目", "license": "CC BY 4.0"}, "total_chapters": 1,
        "version_label": "原书影", "fetched_at": "2026-10-05"})
    _write(os.path.join(od, "002.char.json"), C.make_char(C.parse_lines_md(LINES_MD), "testbook", 2, "0.1.0"))
    _write(os.path.join(od, "002.punct.json"), {
        "version": "0.1.0", "punctuations": [
            {"mark": "。", "anchor": "3:1:7", "pre_char": "卷"},
            {"mark": "，", "anchor": "3:2:3", "pre_char": "本"},
        ]})
    _write(os.path.join(od, "002.entity.json"), {
        "version": "0.1.0", "entities": [
            {"id": "e1", "type": "work", "text": "子夏易傳", "anchor": {"start": "3:1:1", "end": "3:1:4"}},
            {"id": "e2", "type": "people", "text": "卜子夏", "anchor": {"start": "3:2:4b", "end": "3:2:6b"}},
        ]})
    return entry, od


def run(*args):
    if "--pr" not in args:  # --pr 必填（B3 步 2(a)）
        args = args + ("--pr", "0")
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        code = B.main(list(args) + ["--date", "2026-10-05"])
    return code, err.getvalue()


def ov_violations(root):
    report, _s, _t = V.check(root)
    return {rid: [v["note"] for v in report[rid]["violations"]]
            for rid in ("F-OV-01", "F-OV-02", "F-OV-03", "F-OV-04", "F-OV-06", "F-OV-07", "F-OV-08", "F-OV-09", "F-OV-10", "F-OV-11", "F-FT-01")}


class TestBumpOriginal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.entry, self.od = make_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def idx(self):
        return _read(os.path.join(self.od, "index.json"))["chapters"][0]

    def comp(self, line):
        return _read(os.path.join(self.od, f"002.{line}.json"))

    def test_slots_match_cv_convention(self):
        self.assertEqual(OV.char_slots(self.comp("char")), OV.lines_slots(LINES_MD))
        slots = dict(OV.char_slots(self.comp("char")))
        self.assertEqual(slots["3:1:7"], "卷")
        self.assertEqual(slots["3:2:-1"], "內")
        self.assertEqual(slots["3:2:3"], "本")
        self.assertEqual(slots["3:2:4a"], "舊")
        self.assertEqual(slots["3:2:4b"], "卜")

    def test_before_init_validator_flags_0x(self):
        v = ov_violations(self.root)
        self.assertTrue(v["F-OV-01"], "0.x／缺 text_version 应报 F-OV-01")
        self.assertEqual(v["F-FT-01"], [], "original 的 char.json／punct.json 不该被当成章节文件名不合规")

    def test_text_version_mirror(self):
        run(self.entry, "--init")
        idx = _read(os.path.join(self.od, "index.json"))
        idx["chapters"][0]["text_version"] = "1.0.1"
        _write(os.path.join(self.od, "index.json"), idx)
        notes = ov_violations(self.root)["F-OV-01"]
        self.assertEqual(len(notes), 1)
        self.assertIn("text_version='1.0.1'", notes[0])

    def test_file_fields(self):
        run(self.entry, "--init")
        self.assertEqual(ov_violations(self.root)["F-OV-04"], [])
        idx = _read(os.path.join(self.od, "index.json"))
        ch = idx["chapters"][0]
        ch["cord_file"] = "002.cord.json"      # 声明了但没有文件
        ch["rich_file"] = "002.rich.json"      # 文件名不对
        del ch["char_file"]                    # 必填缺了
        _write(os.path.join(self.od, "index.json"), idx)
        notes = ov_violations(self.root)["F-OV-04"]
        self.assertEqual(len(notes), 3)
        self.assertTrue(any("文件不存在" in n for n in notes))
        self.assertTrue(any("002.rich.md" in n for n in notes))
        self.assertTrue(any("缺 char_file" in n for n in notes))

    def test_no_char_json(self):
        os.remove(os.path.join(self.od, "002.char.json"))
        code, err = run(self.entry, "--init")
        self.assertEqual(code, 1)
        self.assertIn("002.char.json", err)
        self.assertTrue(any("char.json" in n for n in ov_violations(self.root)["F-OV-01"]))

    def test_init(self):
        code, _ = run(self.entry, "--init", "--note", "首次并 main", "--pr", "7")
        self.assertEqual(code, 0)
        ch = self.idx()
        self.assertEqual((ch["text_version"], ch["punct_version"], ch["entity_version"]), ("1.0.0",) * 3)
        self.assertEqual(self.comp("char")["version"], "1.0.0")
        self.assertEqual(self.comp("punct")["text_version"], "1.0.0")
        # char.json 仍是一格一行
        self.assertIn('{"a": "3:1:1", "c": "子"}', OV.read_text(os.path.join(self.od, "002.char.json")))
        changes = OV.read_text(os.path.join(self.od, "CHANGES.md"))
        self.assertIn("| 2026-10-05 | testbook/002 | 文本＋标点＋实体 | →1.0.0 | 首次并 main | #7 |", changes)
        self.assertEqual(ov_violations(self.root),
                         {"F-OV-01": [], "F-OV-02": [], "F-OV-03": [], "F-OV-04": [], "F-OV-06": [], "F-OV-07": [], "F-OV-08": [], "F-OV-09": [], "F-OV-10": [], "F-OV-11": [], "F-FT-01": []})
        code, err = run(self.entry, "--init")
        self.assertEqual(code, 1)
        self.assertIn("不能再 init", err)

    def _coarse_only(self):
        """粗校完的形态：只有文本线，没有标点、实体稿。"""
        for line in ("punct", "entity"):
            os.remove(os.path.join(self.od, f"002.{line}.json"))
        idx = _read(os.path.join(self.od, "index.json"))
        for k in ("punct_file", "entity_file"):
            del idx["chapters"][0][k]
        idx["chapters"][0]["cord_file"] = "002.cord.json"
        _write(os.path.join(self.od, "index.json"), idx)
        _write(os.path.join(self.od, "002.cord.json"), {"cells": {}})

    def test_0x_needs_cord_file(self):
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        self.assertEqual(ov_violations(self.root)["F-OV-04"], [])
        idx = _read(os.path.join(self.od, "index.json"))
        del idx["chapters"][0]["cord_file"]
        _write(os.path.join(self.od, "index.json"), idx)
        self.assertTrue(any("cord_file" in n for n in ov_violations(self.root)["F-OV-04"]))

    def test_init_0_1_0_coarse(self):
        self._coarse_only()
        code, _ = run(self.entry, "--init", "--version", "0.1.0", "--note", "粗校完", "--pr", "9")
        self.assertEqual(code, 0)
        ch = self.idx()
        self.assertEqual((ch["text_version"], ch["proofing"]), ("0.1.0", True))
        self.assertNotIn("punct_version", ch)
        self.assertEqual(self.comp("char")["version"], "0.1.0")
        self.assertIn("| 文本 | →0.1.0 | 粗校完 | #9 |",
                      OV.read_text(os.path.join(self.od, "CHANGES.md")))
        self.assertTrue(all(not v for v in ov_violations(self.root).values()), ov_violations(self.root))

    def test_init_0_1_0_with_companions(self):
        # 10-18 用户定（GUJI-240）：文本 0.x 时也可以有标点、实体，伴生层同为 0.1.0
        idx = _read(os.path.join(self.od, "index.json"))
        idx["chapters"][0]["cord_file"] = "002.cord.json"
        _write(os.path.join(self.od, "index.json"), idx)
        _write(os.path.join(self.od, "002.cord.json"), {"cells": {}})
        code, _ = run(self.entry, "--init", "--version", "0.1.0", "--note", "粗校完", "--pr", "9")
        self.assertEqual(code, 0)
        ch = self.idx()
        self.assertEqual((ch["text_version"], ch["punct_version"], ch["entity_version"]), ("0.1.0",) * 3)
        self.assertEqual(self.comp("punct")["text_version"], "0.1.0")
        self.assertIn("| 文本＋标点＋实体 | →0.1.0 | 粗校完 | #9 |",
                      OV.read_text(os.path.join(self.od, "CHANGES.md")))
        self.assertTrue(all(not v for v in ov_violations(self.root).values()), ov_violations(self.root))
        # 伴生层 1.x 高于文本 0.x：报
        d = self.comp("punct")
        d["version"] = "1.0.0"
        _write(os.path.join(self.od, "002.punct.json"), d)
        idx = _read(os.path.join(self.od, "index.json"))
        idx["chapters"][0]["punct_version"] = "1.0.0"
        _write(os.path.join(self.od, "index.json"), idx)
        self.assertTrue(any("高于文本线" in n for n in ov_violations(self.root)["F-OV-01"]))

    def test_0x_init_line_later(self):
        # 文本先以 0.x 并 main，标点、实体后开：--init --line，定 0.1.0，text_version 跟当前文本
        punct, entity = self.comp("punct"), self.comp("entity")
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        run(self.od, "--line", "text", "--level", "patch", "--note", "改 1 字")
        _write(os.path.join(self.od, "002.punct.json"), punct)
        _write(os.path.join(self.od, "002.entity.json"), entity)
        code, err = run(self.od, "--init", "--line", "punct", "--note", "标点首版", "--pr", "11")
        self.assertEqual(code, 0, err)
        ch = self.idx()
        self.assertEqual((ch["punct_version"], ch["punct_file"]), ("0.1.0", "002.punct.json"))
        self.assertEqual(self.comp("punct")["text_version"], "0.1.1")
        code, err = run(self.od, "--init", "--line", "punct", "--note", "x")
        self.assertEqual(code, 1)
        self.assertIn("不能再 init", err)
        run(self.od, "--init", "--line", "entity", "--note", "实体首版")
        self.assertTrue(all(not v for v in ov_violations(self.root).values()), ov_violations(self.root))
        code, _ = run(self.od, "--line", "entity", "--level", "minor", "--note", "补链")
        self.assertEqual(code, 0)
        self.assertEqual(self.idx()["entity_version"], "0.2.0")
        # 0.0.x 不合格
        d = self.comp("punct")
        d["version"] = "0.0.1"
        _write(os.path.join(self.od, "002.punct.json"), d)
        self.assertTrue(any("低于 0.1.0" in n for n in ov_violations(self.root)["F-OV-01"]))

    def test_0x_bump(self):
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        code, _ = run(self.od, "--line", "text", "--level", "minor", "--note", "重切 3 页")
        self.assertEqual(code, 0)
        self.assertEqual((self.idx()["text_version"], self.comp("char")["version"]), ("0.2.0", "0.2.0"))
        self.assertTrue(self.idx()["proofing"])
        code, err = run(self.od, "--line", "punct", "--level", "patch", "--note", "x")
        self.assertEqual(code, 1)  # 没有标点稿
        self.assertIn("002.punct.json", err)
        self.assertTrue(all(not v for v in ov_violations(self.root).values()))

    def test_proofing_required_while_0x(self):
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        for bad in (None, False, "yes"):
            idx = _read(os.path.join(self.od, "index.json"))
            if bad is None:
                del idx["chapters"][0]["proofing"]
            else:
                idx["chapters"][0]["proofing"] = bad
            _write(os.path.join(self.od, "index.json"), idx)
            self.assertEqual(len(ov_violations(self.root)["F-OV-06"]), 1, bad)
        code, err = run(self.od, "--proofing", "off", "--note", "x")
        self.assertEqual(code, 1)
        self.assertIn("精校未完", err)

    def test_below_0_1_0_flagged(self):
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        d = self.comp("char")
        d["version"] = "0.0.9"
        _write(os.path.join(self.od, "002.char.json"), d)
        self.assertTrue(any("低于 0.1.0" in n for n in ov_violations(self.root)["F-OV-01"]))

    def _pending(self, **over):
        pd = {"rev": "002-r1", "cv_version": None, "cv_commit": "abc1234",
              "cells": [{"cell": "p3-r2-c5", "review": "pending"}]}
        pd.update(over)
        _write(os.path.join(self.od, "002.pending.json"), pd)
        idx = _read(os.path.join(self.od, "index.json"))
        idx["chapters"][0]["pending_file"] = "002.pending.json"
        _write(os.path.join(self.od, "index.json"), idx)

    def test_pending_file(self):
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        self._pending()
        self.assertTrue(all(not v for v in ov_violations(self.root).values()), ov_violations(self.root))
        for bad in ({"rev": "x-r1"}, {"cv_commit": ""}, {"cv_commit": None}, {"cv_version": 1},
                    {"cells": {}}, {"cells": [{"cell": "a"}]}):
            self._pending(**bad)
            self.assertEqual(len(ov_violations(self.root)["F-OV-07"]), 1, bad)
        self._pending(cv_version="cv-v0.1.0")
        self.assertEqual(ov_violations(self.root)["F-OV-07"], [])

    def test_pending_file_proof02_fields(self):
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        good = {"cell": "p3-r2-c5", "review": "pending", "why": ["none"], "cls": "replace_align", "conf": 0.62,
                "margin": None, "lib_top": [{"c": "己", "s": 0.9123}], "lib": {"verdict": "ok", "cov": 0.5, "wmax": 0.7},
                "ctx": {"c": "己", "margin": 0.2, "src": "m"}, "ref": {"c": "已", "op": "coord"},
                "ocr": [{"c": "己", "src": "x"}], "stale": {"c": "己", "ts": "t", "state": "valid"},
                "occ": {"c": "非字", "ref_blank": False}, "img": {"s": "p0003.webp", "x": 0, "y": 0, "w": 96, "h": 96},
                "ex": {}, "future_key": {"anything": 1}}
        self._pending(cells=[good])
        self.assertEqual(ov_violations(self.root)["F-OV-08"], [])
        for k, v in (("why", "none"), ("cls", 1), ("lib_top", [{"c": "己"}]), ("lib", {"verdict": "ok"}),
                     ("stale", {"c": "己", "ts": "t", "state": "weird"}), ("img", {"s": "a.webp", "x": "0", "y": 0, "w": 1, "h": 1}),
                     ("ex", {"己": [{"s": "a"}]}), ("occ", {"c": "x"})):
            self._pending(cells=[dict(good, **{k: v})])
            self.assertEqual(len(ov_violations(self.root)["F-OV-08"]), 1, k)

    def test_proof02_sprite_manifest(self):
        cell = {"img": {"s": "p1.webp", "x": 0, "y": 0, "w": 96, "h": 96}, "ex": {"己": [{"s": "ex-1.webp", "x": 0, "y": 0, "w": 96, "h": 96}]}}
        self.assertEqual(V.proof02_cell_problems(cell), [])
        self.assertEqual(V.proof02_cell_problems(cell, {"p1.webp", "ex-1.webp"}), [])
        self.assertEqual(len(V.proof02_cell_problems(cell, {"p1.webp"})), 1)
        self.assertEqual(len(V.proof02_cell_problems(cell, set())), 2)

    def test_assets_json(self):
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        apath = os.path.join(self.od, "assets.json")
        cell = {"cell": "a", "review": "pending", "img": {"s": "p0003.webp", "x": 96, "y": 0, "w": 96, "h": 96}}
        assets = {"schema": "guji-proof-assets/0.1", "book": "b", "volume": 2, "rev": "002-r1",
                  "files": [{"name": "p0003.webp", "bytes": 1, "sha256": "x", "w": 192, "h": 96}]}
        self._pending(cells=[cell])
        v = ov_violations(self.root)
        self.assertEqual(len(v["F-OV-09"]), 1)  # 有 s 无 assets.json
        _write(apath, assets)
        self.assertTrue(all(not x for x in ov_violations(self.root).values()), ov_violations(self.root))
        _write(apath, dict(assets, rev="002-r2"))
        self.assertEqual(len(ov_violations(self.root)["F-OV-11"]), 1)
        _write(apath, dict(assets, files=[dict(assets["files"][0], w=191)]))
        self.assertEqual(len(ov_violations(self.root)["F-OV-10"]), 1)
        _write(apath, dict(assets, files=[dict(assets["files"][0], name="p0004.webp")]))
        self.assertEqual(len(ov_violations(self.root)["F-OV-09"]), 1)
        os.remove(apath)
        self._pending()  # 无 s 时不要求 assets.json
        self.assertTrue(all(not x for x in ov_violations(self.root).values()), ov_violations(self.root))

    def test_assets_pointer(self):
        """桶清单不进仓：按 proof/<书>/<册>/sprites.pointer.json 取；离线只核指针，--fetch-assets 才下载核 sha256。"""
        import hashlib
        self._coarse_only()
        run(self.entry, "--init", "--version", "0.1.0")
        cell = {"cell": "a", "review": "pending", "img": {"s": "p0003.webp", "x": 96, "y": 0, "w": 96, "h": 96}}
        assets = {"schema": "guji-proof-assets/0.1", "book": "testbook", "volume": 2, "rev": "002-r1",
                  "files": [{"name": "p0003.webp", "bytes": 1, "sha256": "x", "w": 192, "h": 96}]}
        raw = json.dumps(assets).encode("utf-8")
        sha = hashlib.sha256(raw).hexdigest()
        kpath = os.path.join(self.root, "proof", "testbook", "002", "sprites.pointer.json")
        ptr = {"tag": "proof-testbook-002-1", "manifest_sha256": sha, "rev": "002-r1"}
        self._pending(cells=[cell])
        orig = V.fetch_bytes
        urls = []

        def fake(url, **kw):
            urls.append(url)
            return raw

        V.fetch_bytes = fake
        try:
            def viol(fetch):
                report, _s, _t = V.check(self.root, fetch_assets=fetch)
                return {r: [v["note"] for v in report[r]["violations"]] for r in ("F-OV-09", "F-OV-10", "F-OV-11", "F-OV-09w")}

            self.assertEqual(len(viol(False)["F-OV-09"]), 1)  # 有 s，无 assets.json、无指针
            _write(kpath, ptr)
            v = viol(False)
            self.assertTrue(all(not x for x in v.values()), v)  # 离线：只核指针
            self.assertEqual(urls, [])
            v = viol(True)
            self.assertTrue(all(not x for x in v.values()), v)  # 联网：sha 对、越界检查过
            self.assertEqual(urls, ["https://github.com/open-guji/open-guji-dataset/releases/download/proof-testbook-002-1/assets.json"])
            _write(kpath, dict(ptr, manifest_sha256="0" * 64))
            self.assertEqual(len(viol(True)["F-OV-09"]), 1)  # sha 不一致
            self.assertTrue(all(not x for x in viol(False).values()))
            _write(kpath, dict(ptr, rev="002-r2"))
            self.assertEqual(len(viol(False)["F-OV-11"]), 1)  # 指针 rev 与 pending 不一致，离线即报
            for bad_tag in ("..", "a/b", "x y"):
                _write(kpath, dict(ptr, tag=bad_tag))
                self.assertEqual(len(viol(False)["F-OV-09"]), 1, bad_tag)  # tag 不合规，不拼 URL
            _write(kpath, {"tag": "t"})
            self.assertEqual(len(viol(False)["F-OV-09"]), 1)  # 指针形状不对
            _write(kpath, ptr)
            V.fetch_bytes = lambda url, **kw: json.dumps(dict(assets, files=[dict(assets["files"][0], w=191)])).encode("utf-8")
            self.assertEqual(len(viol(True)["F-OV-09"]), 1)  # 内容变了 sha 对不上
            bad = json.dumps(dict(assets, files=[dict(assets["files"][0], w=191)])).encode("utf-8")
            _write(kpath, dict(ptr, manifest_sha256=hashlib.sha256(bad).hexdigest()))
            self.assertEqual(len(viol(True)["F-OV-10"]), 1)  # sha 对但越界

            for other in (dict(assets, book="otherbook"), dict(assets, volume=3)):
                rawo = json.dumps(other).encode("utf-8")
                _write(kpath, dict(ptr, manifest_sha256=hashlib.sha256(rawo).hexdigest()))
                V.fetch_bytes = lambda url, rawo=rawo, **kw: rawo
                self.assertEqual(len(viol(True)["F-OV-09"]), 1)  # 清单的 book／volume 与指针目录不一致

            def boom(url, **kw):
                raise OSError("offline")
            V.fetch_bytes = boom
            v = viol(True)
            self.assertEqual((len(v["F-OV-09w"]), len(v["F-OV-09"])), (1, 0))  # 下载失败：只警告（SOFT），不记 HARD
        finally:
            V.fetch_bytes = orig

    def test_pending_file_needs_proofing_and_exists(self):
        run(self.entry, "--init")
        self._pending()
        self.assertEqual(len(ov_violations(self.root)["F-OV-07"]), 1)
        run(self.od, "--proofing", "on", "--note", "补走精校")
        self.assertEqual(ov_violations(self.root)["F-OV-07"], [])
        os.remove(os.path.join(self.od, "002.pending.json"))
        self.assertEqual(len(ov_violations(self.root)["F-OV-04"]), 1)

    def test_proofing_switch_after_1_0_0(self):
        run(self.entry, "--init")
        self.assertNotIn("proofing", self.idx())
        code, _ = run(self.od, "--proofing", "on", "--note", "旧定义 1.0.0，补走精校", "--pr", "5")
        self.assertEqual(code, 0)
        self.assertTrue(self.idx()["proofing"])
        self.assertEqual(ov_violations(self.root)["F-OV-06"], [])
        code, _ = run(self.od, "--proofing", "off", "--note", "精校完")
        self.assertEqual(code, 0)
        self.assertFalse(self.idx()["proofing"])
        changes = OV.read_text(os.path.join(self.od, "CHANGES.md"))
        self.assertIn("| 校对状态 | 关→开 | 旧定义 1.0.0，补走精校 | #5 |", changes)

    def test_patch_and_minor(self):
        run(self.entry, "--init")
        code, _ = run(self.od, "--line", "punct", "--level", "patch", "--note", "改两处逗号", "--pr", "8")
        self.assertEqual(code, 0)
        self.assertEqual(self.comp("punct")["version"], "1.0.1")
        self.assertEqual(self.idx()["punct_version"], "1.0.1")
        code, _ = run(self.od, "--line", "entity", "--level", "minor", "--note", "整册重识别")
        self.assertEqual(code, 0)
        self.assertEqual(self.idx()["entity_version"], "1.1.0")
        code, _ = run(self.od, "--line", "text", "--level", "minor", "--note", "PUA 转 Unicode", "--chapter", "2")
        self.assertEqual(code, 0)
        # 文本没动字，锚点都对得上：伴生层只跟 text_version，不升自己的版本
        self.assertEqual(self.idx()["text_version"], "1.1.0")
        self.assertEqual(self.comp("char")["version"], "1.1.0")
        self.assertEqual(self.comp("punct")["text_version"], "1.1.0")
        self.assertEqual(self.comp("punct")["version"], "1.0.1")
        changes = OV.read_text(os.path.join(self.od, "CHANGES.md"))
        self.assertIn("| 标点 | 1.0.0→1.0.1 | 改两处逗号 | #8 |", changes)
        self.assertIn("| 文本 | 1.0.0→1.1.0 | PUA 转 Unicode | #0 |", changes)
        self.assertEqual(ov_violations(self.root)["F-OV-01"], [])

    def test_major_refused(self):
        run(self.entry, "--init")
        before = OV.read_text(os.path.join(self.od, "index.json"))
        code, err = run(self.od, "--line", "text", "--level", "major", "--note", "出版级")
        self.assertEqual(code, 1)
        self.assertIn("脚本不升", err)
        self.assertEqual(before, OV.read_text(os.path.join(self.od, "index.json")))

    def test_anchor_drift(self):
        run(self.entry, "--init")
        # 改字：「卜」→「十」，正好落在实体 e2 的锚点上
        _write(os.path.join(self.od, "002.char.json"), OV.read_text(os.path.join(self.od, "002.char.json")).replace("卜", "十"))
        code, err = run(self.od, "--line", "text", "--level", "patch", "--note", "改一字")
        self.assertEqual(code, 0)
        self.assertIn("实体层有 1 处锚点对不上", err)
        self.assertEqual(self.comp("punct")["text_version"], "1.0.1")   # 标点没受影响，跟过去
        self.assertEqual(self.comp("entity")["text_version"], "1.0.0")  # 实体对不上，原地不动
        v = ov_violations(self.root)
        self.assertEqual(len(v["F-OV-02"]), 1)
        self.assertIn("卜子夏", v["F-OV-02"][0])
        # 锚点没修好，实体线不许升
        code, err = run(self.od, "--line", "entity", "--level", "patch", "--note", "x")
        self.assertEqual(code, 1)
        self.assertIn("锚点", err)
        # 修好实体再升：实体 1.0.1，text_version 跟上，校验器清零
        ent = self.comp("entity")
        ent["entities"][1]["text"] = "十子夏"
        _write(os.path.join(self.od, "002.entity.json"), ent)
        code, _ = run(self.od, "--line", "entity", "--level", "patch", "--note", "修锚点")
        self.assertEqual(code, 0)
        self.assertEqual((self.comp("entity")["version"], self.comp("entity")["text_version"]), ("1.0.1", "1.0.1"))
        self.assertEqual(ov_violations(self.root)["F-OV-02"], [])

    def test_ov02_summary(self):
        """GUJI-591：CI 在 PR 上报「标点 pre_char 对不上 N 条、实体失效待看 N 条」。"""
        run(self.entry, "--init")
        report, _s, _t = V.check(self.root)
        np_, ne, md = V.ov02_summary(report)
        self.assertEqual((np_, ne), (0, 0))
        self.assertIn("<!-- ov02: punct=0 entity=0 -->", md)
        self.assertIn("✅", md)
        self.assertIn("核了标点 1 册 2 条、实体 1 册 2 条", md)
        # 同版本改字（不升文本版本，模拟改字 PR 未跟伴生层）：「卷」→「巻」碰标点 #0，「卜」→「十」碰实体 e2
        cp = os.path.join(self.od, "002.char.json")
        _write(cp, OV.read_text(cp).replace("卷", "巻").replace("卜", "十"))
        report, _s, _t = V.check(self.root)
        np_, ne, md = V.ov02_summary(report)
        self.assertEqual((np_, ne), (1, 1))
        self.assertTrue(md.startswith(V.OV02_MARK))
        self.assertIn("<!-- ov02: punct=1 entity=1 -->", md)
        self.assertIn("标点 pre_char 对不上 1 条、实体失效待看 1 条", md)
        self.assertIn("| `Book/aa/bb/cc/testbook/original/002.punct.json` | 标点 | 1 |", md)
        self.assertIn("| `Book/aa/bb/cc/testbook/original/002.entity.json` | 实体 | 1 |", md)
        self.assertIn("卜子夏", md)
        self.assertNotIn(self.root, md)  # 明细只用相对路径

    def test_ov02_summary_truncated(self):
        """一个文件超过 20 条时，「另有 N 处」那条的权重也计入总数。"""
        run(self.entry, "--init")
        p = os.path.join(self.od, "002.entity.json")
        ent = self.comp("entity")
        ent["entities"] = [dict(ent["entities"][0], id=f"x{i}", text="錯") for i in range(25)]
        _write(p, ent)
        report, _s, _t = V.check(self.root)
        np_, ne, md = V.ov02_summary(report)
        self.assertEqual((np_, ne), (0, 25))
        self.assertIn("另有 5 处未逐条列出", md)

    def test_major_needs_review(self):
        run(self.entry, "--init")
        p = os.path.join(self.od, "002.punct.json")
        d = self.comp("punct")
        d["version"] = "2.0.0"
        _write(p, d)
        idx = _read(os.path.join(self.od, "index.json"))
        idx["chapters"][0]["punct_version"] = "2.0.0"
        _write(os.path.join(self.od, "index.json"), idx)
        self.assertEqual(len(ov_violations(self.root)["F-OV-03"]), 1)
        d["review"] = {"date": "2026-11-01", "signed_by": "用户", "sample": "抽 500 处，一致 499"}
        _write(p, d)
        self.assertEqual(ov_violations(self.root)["F-OV-03"], [])

    def test_companion_major_not_above_text(self):
        run(self.entry, "--init")
        p = os.path.join(self.od, "002.punct.json")
        d = self.comp("punct")
        d["version"] = "2.0.0"
        d["review"] = {"date": "2026-11-01", "signed_by": "用户", "sample": "抽 500 处，一致 499"}
        _write(p, d)
        idx = _read(os.path.join(self.od, "index.json"))
        idx["chapters"][0]["punct_version"] = "2.0.0"
        _write(os.path.join(self.od, "index.json"), idx)
        notes = ov_violations(self.root)["F-OV-01"]
        self.assertEqual(len(notes), 1)
        self.assertIn("高于文本线", notes[0])
        idx["chapters"][0]["text_version"] = "2.0.0"
        _write(os.path.join(self.od, "index.json"), idx)
        char = self.comp("char")
        char["version"] = "2.0.0"
        _write(os.path.join(self.od, "002.char.json"), char)
        self.assertEqual(ov_violations(self.root)["F-OV-01"], [])
        # 文本线 ≥2 级的验收记录在 char.json 顶层 review
        self.assertEqual(len(ov_violations(self.root)["F-OV-03"]), 1)
        char["review"] = {"date": "2026-11-01", "signed_by": "用户", "sample": "抽 2000 字，错 1"}
        _write(os.path.join(self.od, "002.char.json"), char)
        self.assertEqual(ov_violations(self.root)["F-OV-03"], [])

    def test_major_above_3_rejected(self):
        run(self.entry, "--init")
        p = os.path.join(self.od, "002.entity.json")
        d = self.comp("entity")
        d["version"] = "4.0.0"
        d["review"] = {"date": "2026-11-01", "signed_by": "用户", "sample": "x"}
        _write(p, d)
        idx = _read(os.path.join(self.od, "index.json"))
        idx["chapters"][0]["entity_version"] = "4.0.0"
        _write(os.path.join(self.od, "index.json"), idx)
        notes = ov_violations(self.root)["F-OV-01"]
        self.assertEqual(len(notes), 1)
        self.assertIn("超过 3", notes[0])


class PrRequiredTest(unittest.TestCase):
    def test_missing_pr_rejected(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            B.main(["/nonexistent", "--line", "text", "--level", "patch", "--note", "x"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
