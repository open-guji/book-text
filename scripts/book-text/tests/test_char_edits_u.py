# -*- coding: utf-8 -*-
"""改字清单上了 u（char v0.6）：record 按 u 比、sync 按 u 守、uid 发号作废重挂（2026-11-24）。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import char_edits  # noqa: E402
import cell_uid as CU  # noqa: E402
import original_version as OV  # noqa: E402


def char(cells, version="0.3.0", umax=None, retired=None):
    d = {"$schema": CU.CHAR_V06, "version": version, "book_id": "bk0000000001", "volume": 1}
    if umax is not None:
        d["u_max"] = umax
    if retired:
        d["u_retired"] = retired
    d["pages"] = [{"page": 1, "columns": [{"col": 1, "cells": cells}]}]
    return d


def seq(spec):
    """'甲1 乙2 補 丙3' → 格列表，格号按位置 1..N，没数字的格不带 u。"""
    out = []
    for k, tok in enumerate(spec.split(), 1):
        c = {"a": f"1:1:{k}"}
        if len(tok) > 1:
            c["u"] = int(tok[1:])
        c["c"] = tok[0]
        out.append(c)
    return out


def dump(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def load(d, name):
    return json.load(open(os.path.join(d, name), encoding="utf-8"))


def setup(tmp_path, new_spec):
    d = os.path.join(str(tmp_path), "bk0000000001", "default")
    os.makedirs(d)
    dump(os.path.join(d, "old.json"), char(seq("甲1 乙2 丙3 丁4 戊5"), umax=5))
    dump(os.path.join(d, "001.char.json"), char(seq(new_spec), "0.4.0", umax=5))
    pt = lambda m, a, u, pc, pos="after": {"mark": m, "kind": "point", "pos": pos, "anchor": a, "u": u,  # noqa: E731
                                           "pre_char": pc, "source": "claude:A33"}
    dump(os.path.join(d, "001.punct.json"), {"$schema": CU.PUNCT_V04, "text_version": "0.3.0", "punctuations": [
        pt("，", "1:1:2", 2, "乙"), pt("。", "1:1:5", 5, "戊")]})
    dump(os.path.join(d, "001.entity.json"), {"$schema": CU.ENTITY_V04, "text_version": "0.3.0", "entities": [
        {"id": "e1", "type": "people", "text": "丙丁", "anchor": {"start": "1:1:3", "end": "1:1:4"},
         "u_start": 3, "u_end": 4, "target": {"status": "matched", "entity_id": "x"}}]})
    return d


def test_uid_insert_shifts_marks_with_their_chars(tmp_path, capsys):
    d = setup(tmp_path, "甲1 補 乙2 丙3 丁4 戊5")        # 「乙」前补一字，后面格号全后移
    assert char_edits.main(["uid", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json")]) == 0
    ch, P, E = load(d, "001.char.json"), load(d, "001.punct.json"), load(d, "001.entity.json")
    assert [c.get("u") for c in CU.cells(ch)] == [1, 6, 2, 3, 4, 5] and ch["u_max"] == 6
    assert [(p["anchor"], p["u"]) for p in P["punctuations"]] == [("1:1:3", 2), ("1:1:6", 5)]
    assert E["entities"][0]["anchor"] == {"start": "1:1:4", "end": "1:1:5"}
    for line, data in (("punct", P), ("entity", E)):
        assert OV.anchor_mismatches(ch, line, data) == []
        assert CU.layer_u_problems(ch, line, data) == []


def test_uid_delete_retires_and_moves_mark_for_review(tmp_path, capsys):
    d = setup(tmp_path, "甲1 丙3 丁4 戊5")               # 删「乙」，上面的逗号挪到「甲」后，待看
    rv = os.path.join(d, "rv.tsv")
    assert char_edits.main(["uid", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json"),
                            "--review", rv]) == 0
    ch, P = load(d, "001.char.json"), load(d, "001.punct.json")
    assert ch["u_retired"] == [{"u": 2, "gone": True}] and ch["u_max"] == 5
    p0 = P["punctuations"][0]
    assert (p0["anchor"], p0["u"], p0["pre_char"]) == ("1:1:1", 1, "乙")   # 校验字只报不改
    assert len(OV.anchor_mismatches(ch, "punct", P)) == 1                   # F-OV-02 会报，交人看
    assert "删了" in open(rv, encoding="utf-8").read()
    assert CU.continuity_problems(load(d, "old.json"), ch) == []


def test_uid_merge(tmp_path, capsys):
    d = setup(tmp_path, "甲1 乙2 丙3 戊5")               # 丁并进丙
    assert char_edits.main(["uid", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json"),
                            "--merge", "4:3"]) == 0
    ch, E = load(d, "001.char.json"), load(d, "001.entity.json")
    assert ch["u_retired"] == [{"u": 4, "into": 3}]
    assert E["entities"][0]["u_end"] == 3 and E["entities"][0]["anchor"]["end"] == "1:1:3"


def test_uid_needs_migrated_old(tmp_path, capsys):
    d = setup(tmp_path, "甲1 乙2 丙3 丁4 戊5")
    old = load(d, "old.json")
    for c in CU.cells(old):
        c.pop("u")
    old.pop("u_max")
    dump(os.path.join(d, "old.json"), old)
    assert char_edits.main(["uid", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json")]) == 2


def test_record_by_u_after_insert_and_sync_guard(tmp_path, capsys):
    d = setup(tmp_path, "甲1 補6 乙2 己3 丁4 戊5")       # 补字（已发号）＋原地改丙→己
    ch = load(d, "001.char.json")
    ch["u_max"] = 6
    dump(os.path.join(d, "001.char.json"), ch)
    assert char_edits.main(["record", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json"),
                            "--base-commit", "abc", "--ref", "r1"]) == 0
    ed = load(d, "001.char-edits.json")
    assert [(e["anchor"], e["old"], e["new"], e["u"]) for e in ed["edits"]] == [("1:1:4", "丙", "己", 3)]
    hard, _soft = OV.char_edits_problems(ch, ed, stem="001", book_id="bk0000000001")
    assert hard == []
    # 清单的 u 与格对不上（移位）时硬错
    ed["edits"][0]["u"] = 4
    hard, _soft = OV.char_edits_problems(ch, ed, stem="001", book_id="bk0000000001")
    assert any(sub.endswith(":u") for _m, sub in hard)


def test_sync_skips_when_u_differs(tmp_path, capsys):
    d = setup(tmp_path, "甲1 丁2 丙3 丁4 戊5")           # 原地改乙→丁（u=2）
    assert char_edits.main(["record", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json"),
                            "--base-commit", "abc", "--ref", "r1"]) == 0
    P = load(d, "001.punct.json")
    P["punctuations"][0]["u"] = 9                       # 标点的 u 与清单不同（错位）：不同步
    dump(os.path.join(d, "001.punct.json"), P)
    char_edits.sync(d, "001")
    assert load(d, "001.punct.json")["punctuations"][0]["pre_char"] == "乙"
    P["punctuations"][0]["u"] = 2
    dump(os.path.join(d, "001.punct.json"), P)
    char_edits.sync(d, "001")
    assert load(d, "001.punct.json")["punctuations"][0]["pre_char"] == "丁"


def test_remap_anchors_by_u(tmp_path, capsys):
    import remap_anchors
    d = setup(tmp_path, "甲1 補6 乙2 丙3 丁4 戊5")
    ch = load(d, "001.char.json")
    ch["u_max"] = 6
    dump(os.path.join(d, "001.char.json"), ch)
    assert remap_anchors.main([d, "--chapter", "001", "--by-u"]) == 0
    P = load(d, "001.punct.json")
    assert [p["anchor"] for p in P["punctuations"]] == ["1:1:3", "1:1:6"]
    import pytest
    with pytest.raises(SystemExit):
        remap_anchors.main([d, "--chapter", "001", "--cells", "x.tsv"])
