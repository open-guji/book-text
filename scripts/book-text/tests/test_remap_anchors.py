# -*- coding: utf-8 -*-
"""换图源重挂：同格／改号改锚点、删新增配对补回、删除格与改字留待重标。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import remap_anchors as RA  # noqa: E402


def char(cells):
    return {"version": "0.4.0", "pages": [{"columns": [{"cells": [{"a": a, "c": c} for a, c in cells]}]}]}


def dump(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def row(o, n, oc, nc, kind):
    return {"旧格": o and f"vol01:{o}", "新格": n and f"vol01:{n}", "旧字": oc, "新字": nc, "类别": kind}


def test_remap(tmp_path, capsys):
    d = str(tmp_path)
    # 旧：3:1:1 甲 3:1:2 乙 3:1:3 丙 3:1:4 丁 3:1:5 戊；新：页 3→1，乙 IoU 低（删＋新增），丁 被删，戊 改字成 己
    dump(os.path.join(d, "001.char.json"), char([("1:1:1", "甲"), ("1:1:2", "乙"), ("1:1:3", "丙"), ("1:1:5", "己")]))
    pt = lambda a, pc, o: {"mark": "，", "kind": "point", "pos": "after", "anchor": a, "pre_char": pc, "char_offset": o}  # noqa: E731
    dump(os.path.join(d, "001.punct.json"), {"punctuations": [pt("3:1:2", "乙", 1), pt("3:1:4", "丁", 3), pt("3:1:5", "戊", 4),
                                                               pt("3:1:3", "丙", 2)]})
    dump(os.path.join(d, "001.entity.json"), {"entities": [
        {"id": "e1", "type": "people", "text": "甲乙丙", "anchor": {"start": "3:1:1", "end": "3:1:3"},
         "span": {"start_offset": 0, "end_offset": 3}, "target": {"status": "matched", "entity_id": "x"}, "source": "human"},
        {"id": "e2", "type": "people", "text": "丙丁", "anchor": {"start": "3:1:3", "end": "3:1:4"},
         "span": {"start_offset": 2, "end_offset": 4}, "target": {"status": "new_candidate"}}]})
    rows = [row("3:1:1", "1:1:1", "甲", "甲", "同格"), row("3:1:2", "", "乙", "", "删"), row("", "1:1:2", "", "乙", "新增"),
            row("3:1:3", "1:1:3", "丙", "丙", "改号"), row("3:1:4", "", "丁", "", "删"), row("3:1:5", "1:1:5", "戊", "己", "同格")]
    m, st = RA.build_map(rows)
    assert m["3:1:2"] == "1:1:2" and st["recovered"] == 1 and st["deleted"] == 1
    res, report = RA.remap(d, "001", rows)
    assert res == {"punct": [2, 2], "entity": [1, 1]}
    P = json.load(open(os.path.join(d, "001.punct.json"), encoding="utf-8"))["punctuations"]
    assert (P[0]["anchor"], P[0]["char_offset"]) == ("1:1:2", 1) and (P[3]["anchor"], P[3]["char_offset"]) == ("1:1:3", 2)
    assert P[1]["anchor"] == "3:1:4" and P[2]["anchor"] == "3:1:5"  # 留待重标的原样不动
    E = json.load(open(os.path.join(d, "001.entity.json"), encoding="utf-8"))["entities"]
    assert E[0]["anchor"] == {"start": "1:1:1", "end": "1:1:3"} and E[0]["span"] == {"start_offset": 0, "end_offset": 3}
    assert E[0]["target"] == {"status": "matched", "entity_id": "x"} and E[0]["source"] == "human"
    assert E[1]["anchor"]["start"] == "3:1:3"
    assert {r[0] for r in report} == {"punct", "entity"} and any("校验字变了" in r[5] for r in report)
