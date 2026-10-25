# -*- coding: utf-8 -*-
"""punct_redo：改字后只重标受影响的句子，句外条目原样保留。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import punct_redo  # noqa: E402
from original_version import anchor_mismatches  # noqa: E402


def char(text_cols):
    return {"version": "1.0.0", "pages": [{"columns": [
        {"cells": [{"a": f"1:{ci + 1}:{k + 1}", "c": c} for k, c in enumerate(col)]} for ci, col in enumerate(text_cols)]}]}


def dump(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def test_plan_apply(tmp_path):
    old = char(["甲乙丙丁", "戊己庚辛"])
    new = char(["甲乙丙丁", "戊巳庚辛"])  # 第二句改一字
    pt = lambda m, a, pc, pos="after": {"mark": m, "kind": "point", "pos": pos, "anchor": a, "pre_char": pc,  # noqa: E731
                                         "char_offset": 0, "source": "x"}
    punct = {"punctuations": [pt("，", "1:1:2", "乙"), pt("。", "1:1:4", "丁"),
                              {"mark": "\n\n", "kind": "break", "pos": "after", "anchor": "1:1:4", "pre_char": "丁",
                               "char_offset": 3, "source": "x"},
                              pt("，", "1:2:2", "己"), pt("。", "1:2:4", "辛")]}
    ent = {"entities": [
        {"id": "e00001", "type": "people", "text": "甲乙", "anchor": {"start": "1:1:1", "end": "1:1:2"},
         "span": {"start_offset": 0, "end_offset": 2}, "target": {"status": "matched", "entity_id": "x1"}},
        {"id": "e00002", "type": "people", "text": "戊己", "anchor": {"start": "1:2:1", "end": "1:2:2"},
         "span": {"start_offset": 4, "end_offset": 6}, "target": {"status": "matched", "entity_id": "x2"}}]}
    d = str(tmp_path)
    dump(os.path.join(d, "001.char.json"), new)
    dump(os.path.join(d, "old.json"), old)
    dump(os.path.join(d, "001.punct.json"), punct)
    dump(os.path.join(d, "001.entity.json"), ent)
    assert punct_redo.main(["plan", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json")]) == 0
    work = open(os.path.join(d, "redo-001.txt"), encoding="utf-8").read()
    assert "=== 4-7" in work and "[p戊巳]，庚辛。" in work and "甲" not in work.split("===", 1)[1]
    with open(os.path.join(d, "redo-001.txt"), "w", encoding="utf-8") as f:
        f.write(work.replace("[p戊巳]，庚辛。", "[p戊巳]庚[p辛]。"))
    assert punct_redo.main(["apply", d, "--chapter", "001"]) == 0
    P = json.load(open(os.path.join(d, "001.punct.json"), encoding="utf-8"))
    E = json.load(open(os.path.join(d, "001.entity.json"), encoding="utf-8"))
    assert [(p["mark"], p["anchor"]) for p in P["punctuations"]] == [
        ("，", "1:1:2"), ("。", "1:1:4"), ("\n\n", "1:1:4"), ("。", "1:2:4")]
    assert [(x["text"], x["target"].get("entity_id")) for x in E["entities"]] == [
        ("甲乙", "x1"), ("戊巳", None), ("辛", None)]
    assert E["entities"][1]["id"] == "e00003"  # 字变了，旧条目不沿用
    assert not anchor_mismatches(new, "punct", P) and not anchor_mismatches(new, "entity", E)


def test_no_change(tmp_path, capsys):
    c = char(["甲乙"])
    d = str(tmp_path)
    dump(os.path.join(d, "001.char.json"), c)
    dump(os.path.join(d, "old.json"), c)
    dump(os.path.join(d, "001.punct.json"), {"punctuations": []})
    dump(os.path.join(d, "001.entity.json"), {"entities": []})
    assert punct_redo.main(["plan", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json")]) == 0
    assert "没有改字" in capsys.readouterr().out
    assert not os.path.exists(os.path.join(d, "redo-001.txt"))
