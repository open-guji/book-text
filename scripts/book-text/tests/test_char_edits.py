# -*- coding: utf-8 -*-
"""改字清单：登记、软放行、同步、过期检查。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import char_edits  # noqa: E402
import original_version as OV  # noqa: E402


def char(text, version="0.3.0"):
    return {"version": version, "pages": [{"columns": [
        {"cells": [{"a": f"1:1:{k + 1}", "c": c} for k, c in enumerate(text)]}]}]}


def dump(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def setup(tmp_path, new_text="甲乙丁丁戊己庚辛", version="0.4.0"):
    d = os.path.join(str(tmp_path), "bk0000000001", "default")
    os.makedirs(d)
    old = char("甲乙丙丁戊己庚辛", "0.3.0")
    dump(os.path.join(d, "old.json"), old)
    dump(os.path.join(d, "001.char.json"), char(new_text, version))
    pt = lambda m, a, pc, src="claude:A33": {"mark": m, "kind": "point", "pos": "after", "anchor": a,  # noqa: E731
                                              "pre_char": pc, "char_offset": 0, "source": src}
    dump(os.path.join(d, "001.punct.json"), {"text_version": "0.3.0", "punctuations": [
        pt("，", "1:1:3", "丙", "human"), pt("。", "1:1:4", "丁"), pt("。", "1:1:8", "辛")]})
    dump(os.path.join(d, "001.entity.json"), {"text_version": "0.3.0", "entities": [
        {"id": "e1", "type": "people", "text": "乙丙", "anchor": {"start": "1:1:2", "end": "1:1:3"},
         "span": {"start_offset": 1, "end_offset": 3}, "target": {"status": "matched", "entity_id": "x"}, "source": "human"},
        {"id": "e2", "type": "people", "text": "己庚", "anchor": {"start": "1:1:6", "end": "1:1:7"},
         "span": {"start_offset": 5, "end_offset": 7}, "target": {"status": "matched", "entity_id": "y"}}]})
    return d


def load(d, name):
    return json.load(open(os.path.join(d, name), encoding="utf-8"))


def test_record_soft_and_sync(tmp_path, capsys):
    d = setup(tmp_path)
    assert char_edits.main(["record", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json"),
                            "--base-commit", "abc123", "--ref", "001-r1", "--by", "A32"]) == 0
    ed = load(d, "001.char-edits.json")
    assert ed["base_text_version"] == "0.3.0" and ed["volume"] == 1 and ed["book_id"] == "bk0000000001"
    assert [(e["anchor"], e["old"], e["new"]) for e in ed["edits"]] == [("1:1:3", "丙", "丁")]
    ch, P, E = load(d, "001.char.json"), load(d, "001.punct.json"), load(d, "001.entity.json")
    # 没清单：硬错；有清单（0.x）：降为软提示
    assert len(OV.anchor_mismatches(ch, "punct", P)) == 1
    soft = []
    assert OV.anchor_mismatches(ch, "punct", P, ed, soft=soft) == [] and len(soft) == 1
    soft = []
    assert OV.anchor_mismatches(ch, "entity", E, ed, soft=soft) == [] and len(soft) == 1
    hard, s2 = OV.char_edits_problems(ch, ed, stem="001", book_id="bk0000000001",
                                      layers={"punct": (P, "0.3.0"), "entity": (E, "0.3.0")})
    assert hard == [] and s2 == []
    # 1.x 不放行，且清单本身报硬错
    ch1 = dict(ch, version="1.0.0")
    assert len(OV.anchor_mismatches(ch1, "punct", P, ed, soft=[])) == 1
    assert any(sub == "major" for _m, sub in OV.char_edits_problems(ch1, ed)[0])
    # 同步：只改校验字，人裁条目的 source／target 不动；清单清空即删
    assert char_edits.main(["sync", d, "--chapter", "001"]) == 0
    out = capsys.readouterr().out
    assert "乙丙→乙丁" in out and "核挂法" in out
    P, E = load(d, "001.punct.json"), load(d, "001.entity.json")
    assert P["punctuations"][0] == {"mark": "，", "kind": "point", "pos": "after", "anchor": "1:1:3",
                                    "pre_char": "丁", "char_offset": 0, "source": "human"}
    assert E["entities"][0]["text"] == "乙丁" and E["entities"][0]["source"] == "human"
    assert E["entities"][0]["target"] == {"status": "matched", "entity_id": "x"}
    assert not OV.anchor_mismatches(ch, "punct", P) and not OV.anchor_mismatches(ch, "entity", E)
    assert not os.path.exists(os.path.join(d, "001.char-edits.json"))


def test_record_merge_and_revert(tmp_path):
    d = setup(tmp_path)
    args = ["record", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json"), "--base-commit", "c1"]
    assert char_edits.main(args) == 0
    # 同格再改：old 留最早
    dump(os.path.join(d, "mid.json"), load(d, "001.char.json"))
    dump(os.path.join(d, "001.char.json"), char("甲乙戊丁戊己庚辛", "0.4.1"))
    assert char_edits.main(["record", d, "--chapter", "001", "--old-char", os.path.join(d, "mid.json"),
                            "--base-commit", "c2"]) == 0
    e = load(d, "001.char-edits.json")["edits"]
    assert [(x["old"], x["new"], x["base_commit"]) for x in e] == [("丙", "戊", "c1")]
    # 改回原字：撤销，清单删掉
    dump(os.path.join(d, "mid.json"), load(d, "001.char.json"))
    dump(os.path.join(d, "001.char.json"), char("甲乙丙丁戊己庚辛", "0.4.2"))
    assert char_edits.main(["record", d, "--chapter", "001", "--old-char", os.path.join(d, "mid.json"),
                            "--base-commit", "c3"]) == 0
    assert not os.path.exists(os.path.join(d, "001.char-edits.json"))


def test_insert_rejected_and_unlisted_hard(tmp_path):
    d = setup(tmp_path, new_text="甲乙丙丁戊己庚辛壬")
    assert char_edits.main(["record", d, "--chapter", "001", "--old-char", os.path.join(d, "old.json"),
                            "--base-commit", "c1"]) == 2
    d2 = setup(tmp_path / "b", new_text="甲乙丁丁戊巳庚辛")
    ed = {"schema": OV.CHAR_EDITS_SCHEMA, "book_id": "bk0000000001", "volume": 1, "base_text_version": "0.3.0",
          "edits": [{"anchor": "1:1:3", "old": "丙", "new": "丁", "base_commit": "c1"}]}
    ch, E = load(d2, "001.char.json"), load(d2, "001.entity.json")
    # 己→巳 没登记：仍是硬错
    assert len(OV.anchor_mismatches(ch, "entity", E, ed, soft=[])) == 1
    # 清单过期（文本已不是 new）、伴生层落后于 base：硬错
    bad = dict(ed, edits=[dict(ed["edits"][0], new="乙")], base_text_version="0.3.5")
    subs = {s for _m, s in OV.char_edits_problems(ch, bad, layers={"entity": (E, "0.3.0")})[0]}
    assert "e0:stale" in subs and "entity:base" in subs


def test_multichar_and_missing_anchor_hard(tmp_path):
    c = char("甲乙丁丁")
    ed = {"schema": OV.CHAR_EDITS_SCHEMA, "book_id": "bk0000000001", "volume": 1, "base_text_version": "0.3.0",
          "edits": [{"anchor": "1:1:3", "old": "丙丙", "new": "丁", "base_commit": "abc"},
                    {"anchor": "1:1:9", "old": "丙", "new": "丁", "base_commit": "abc"},
                    {"anchor": "1:1:2", "old": "甲", "new": "", "base_commit": "abc"}]}
    hard, _soft = OV.char_edits_problems(c, ed, "001", "bk0000000001")
    subs = {s for _m, s in hard}
    assert "e0:len" in subs and "e1:anchor" in subs and "e2" in subs
