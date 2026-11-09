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


def test_refresh_same_cell(tmp_path):
    """同格（IoU≥0.5）改字：标点刷新 pre_char、专名刷新 text 并进复核；改号改字仍留待重标。"""
    d = str(tmp_path)
    dump(os.path.join(d, "001.char.json"), char([("1:1:1", "宋"), ("1:1:2", "濂"), ("1:1:3", "乙")]))
    dump(os.path.join(d, "001.punct.json"), {"punctuations": [
        {"mark": "，", "kind": "point", "pos": "after", "anchor": "1:1:2", "pre_char": "濓", "char_offset": 1},
        {"mark": "。", "kind": "point", "pos": "after", "anchor": "9:1:3", "pre_char": "丙", "char_offset": 2}]})
    dump(os.path.join(d, "001.entity.json"), {"entities": [
        {"id": "e1", "type": "people", "text": "宋濓", "anchor": {"start": "1:1:1", "end": "1:1:2"},
         "span": {"start_offset": 0, "end_offset": 2}, "target": {"status": "new_candidate"}}]})
    mk = lambda o, n, oc, nc, k, iou: dict(row(o, n, oc, nc, k), IoU=iou)  # noqa: E731
    rows = [mk("1:1:1", "1:1:1", "宋", "宋", "同格", "0.95"), mk("1:1:2", "1:1:2", "濓", "濂", "同格", "0.90"),
            mk("9:1:3", "1:1:3", "乙", "乙", "改号", "0.90")]
    res, report = RA.remap(d, "001", rows)
    P = json.load(open(os.path.join(d, "001.punct.json"), encoding="utf-8"))["punctuations"]
    assert P[0]["pre_char"] == "濂" and res["refreshed"] == 1
    assert P[1]["anchor"] == "9:1:3"  # 改号改字仍严格
    E = json.load(open(os.path.join(d, "001.entity.json"), encoding="utf-8"))["entities"]
    assert E[0]["text"] == "宋濂"
    assert any(r[0] == "entity-复核" and "SPAN_REWORD" in r[5] for r in report)
    assert any(r[0] == "punct" and r[5].startswith("ANCHOR_MISS") for r in report)


def test_shift_and_illegal_cell(tmp_path):
    """列内文字整体平移：按文字对齐挪到相邻格，而不是原位刷新；映射到 -1 格的列首标记分流。"""
    d = str(tmp_path)
    # 旧列：本 題 魏 王 粲 撰（1..6）；新列在列首多一字「舊」：舊 本 題 魏 王 粲（框同号，字整体后移一格）
    dump(os.path.join(d, "001.char.json"), char([("1:1:%d" % (i + 1), c) for i, c in enumerate("舊本題魏王粲")] + [("1:2:-1", "撰")]))
    dump(os.path.join(d, "001.punct.json"), {"punctuations": [
        {"mark": "，", "kind": "point", "pos": "after", "anchor": "1:1:5", "pre_char": "粲", "char_offset": 4},
        {"mark": "《", "kind": "point", "pos": "before", "anchor": "1:2:1", "pre_char": "撰", "char_offset": 6}]})
    dump(os.path.join(d, "001.entity.json"), {"entities": []})
    mk = lambda o, n, oc, nc, k: dict(row(o, n, oc, nc, k), IoU="0.90")  # noqa: E731
    old = "本題魏王粲撰"
    rows = [mk(f"1:1:{i + 1}", f"1:1:{i + 1}", oc, nc, "同格") for i, (oc, nc) in enumerate(zip(old, "舊本題魏王粲"))]
    rows.append(mk("1:2:1", "1:2:-1", "撰", "撰", "改号"))
    res, report = RA.remap(d, "001", rows)
    P = json.load(open(os.path.join(d, "001.punct.json"), encoding="utf-8"))["punctuations"]
    assert P[0]["anchor"] == "1:1:6" and P[0]["pre_char"] == "粲" and res["shifted"] == 1
    assert P[1]["anchor"] == "1:2:1"  # 非法格号：不动、分流
    assert any("非法格号" in r[5] and r[5].startswith("ANCHOR_MISS") for r in report)
