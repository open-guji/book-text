"""t_entity_check.py 的单测：每条规则一个「恰好触发该规则」的夹具，外加一个全合规用例。

无 pytest 时逐个调用：
  python3 -c "import sys; sys.path.insert(0,'项目进展/古籍文本/scripts'); import test_t_entity_check as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t_entity_check import check  # noqa: E402

CHARS = "甲乙丙丁戊己庚辛"


def base():
    """一章合规夹具：8 个格位，6 个实体（work 带书名号、matched／new_candidate／ambiguous、一组两 span）。"""
    char = {"pages": [{"page": 1, "columns": [{"col": 1, "cells": [
        {"a": f"1:1:{i + 1}", "c": c} for i, c in enumerate(CHARS)]}]}]}
    punct = {"punctuations": [
        {"mark": "《", "anchor": "1:1:1"}, {"mark": "》", "anchor": "1:1:2"}]}
    index = {"chapters": [{"file": "002", "entity_version": "1.0.0"}]}
    grp = {"id": "ge3", "text": "丁戊"}

    def ent(eid, typ, text, s, anchor, target, group=None):
        e = {"id": eid, "type": typ, "text": text, "anchor": {"start": anchor[0], "end": anchor[1]},
             "span": {"start_offset": s, "end_offset": s + len(text)}, "target": target}
        if group:
            e["group"] = dict(group)
        return e

    es = [
        ent("e1", "work", "甲乙", 0, ("1:1:1", "1:1:2"),
            {"status": "matched", "entity_id": "abc", "canonical_name": "甲乙",
             "href": "book-index://Work/abc"}),
        ent("e2", "people", "丙", 2, ("1:1:3", "1:1:3"), {"status": "new_candidate", "canonical_name": "丙"}),
        ent("e3", "people", "丁", 3, ("1:1:4", "1:1:4"), {"status": "new_candidate", "canonical_name": "丁"}, grp),
        ent("e4", "people", "戊", 4, ("1:1:5", "1:1:5"), {"status": "new_candidate", "canonical_name": "戊"}, grp),
        ent("e5", "office", "己", 5, ("1:1:6", "1:1:6"),
            {"status": "ambiguous", "candidates": [{"entity_id": "x1", "canonical_name": "己"},
                                                    {"entity_id": "x2", "canonical_name": "己"}]}),
        ent("e6", "place", "庚", 6, ("1:1:7", "1:1:7"), {"status": "new_candidate", "canonical_name": "庚"}),
    ]
    return {"$schema": "https://open-guji.org/schema/entity/v0.2.json", "version": "1.0.0",
            "entities": es}, char, punct, index


def run(mut=None):
    """对基础夹具施加 mut(ent, char, punct, index) 修改后核对，返回规则名集合与全部行。"""
    ent, char, punct, index = (copy.deepcopy(x) for x in base())
    if mut:
        mut(ent, char, punct, index)
    rows = check(ent, char, punct, index, "002")
    return {r[0] for r in rows}, rows


def by_id(ent, eid):
    return next(e for e in ent["entities"] if e["id"] == eid)


def only(rule, mut):
    rules, rows = run(mut)
    assert rules == {rule}, f"期望只触发 {rule}，实际 {rows}"


def test_clean_zero_problems():
    rows = run()[1]
    assert rows == [], rows


def test_schema_url():
    only("schema_url", lambda e, c, p, i: e.update({"$schema": "https://example.org/x.json"}))


def test_dup_id():
    only("dup_id", lambda e, c, p, i: by_id(e, "e4").update({"id": "e3"}))


def test_overlap():
    def mut(e, c, p, i):  # e5 改为 戊己（4..6），与 e4（4..5）重叠
        x = by_id(e, "e5")
        x.update({"text": "戊己", "span": {"start_offset": 4, "end_offset": 6},
                  "anchor": {"start": "1:1:5", "end": "1:1:6"}})
    only("overlap", mut)


def test_span_anchor():
    only("span_anchor", lambda e, c, p, i: by_id(e, "e2").update({"anchor": {"start": "1:1:3", "end": "1:1:4"}}))


def test_text():
    only("text", lambda e, c, p, i: by_id(e, "e2").update({"text": "丁"}))


def test_matched_fields():
    only("matched_fields", lambda e, c, p, i: by_id(e, "e1")["target"].pop("canonical_name"))


def test_matched_fields_has_candidates():
    only("matched_fields", lambda e, c, p, i: by_id(e, "e1")["target"].update({"candidates": []}))


def test_href_tail():
    only("href_tail", lambda e, c, p, i: by_id(e, "e1")["target"].update({"href": "book-index://Work/zzz"}))


def test_ambiguous_lt2():
    only("ambiguous_lt2", lambda e, c, p, i: by_id(e, "e5")["target"].update({"candidates": [{"entity_id": "x1"}]}))


def test_ambiguous_extra():
    only("ambiguous_extra", lambda e, c, p, i: by_id(e, "e5")["target"].update({"entity_id": "x1"}))


def test_nc_extra():
    only("nc_extra", lambda e, c, p, i: by_id(e, "e2")["target"].update({"href": "book-index://Work/q"}))


def test_legacy_fields():
    for k in ("coarse", "reclass", "route_to", "entity_type"):
        only(f"legacy_{k}", lambda e, c, p, i, k=k: by_id(e, "e2")["target"].update({k: "x"}))


def test_type():
    only("type", lambda e, c, p, i: by_id(e, "e2").update({"type": "xx"}))


def test_group_lt2():
    def mut(e, c, p, i):  # 组内只剩 e3
        by_id(e, "e4").pop("group")
        by_id(e, "e3")["group"]["text"] = "丁"
    only("group_lt2", mut)


def test_group_id():
    def mut(e, c, p, i):
        for eid in ("e3", "e4"):
            by_id(e, eid)["group"]["id"] = "gX"
    only("group_id", mut)


def test_group_text():
    def mut(e, c, p, i):
        for eid in ("e3", "e4"):
            by_id(e, eid)["group"]["text"] = "丁戊丙"
    only("group_text", mut)


def test_group_adjacent():
    def mut(e, c, p, i):  # 删 e5，e4 挪到 5..6（与 e3 之间留空）
        e["entities"] = [x for x in e["entities"] if x["id"] != "e5"]
        x = by_id(e, "e4")
        x.update({"text": "己", "span": {"start_offset": 5, "end_offset": 6},
                  "anchor": {"start": "1:1:6", "end": "1:1:6"}})
        for eid in ("e3", "e4"):
            by_id(e, eid)["group"]["text"] = "丁己"
    only("group_adjacent", mut)


def test_group_mixed():
    def mut(e, c, p, i):
        by_id(e, "e4")["group"]["text"] = "丁戊"
        by_id(e, "e4")["group"]["extra"] = 1
    only("group_mixed", mut)


def test_work_open_missing():
    only("work_open_missing", lambda e, c, p, i: p.update({"punctuations": [
        x for x in p["punctuations"] if x["mark"] != "《"]}))


def test_work_close_missing():
    only("work_close_missing", lambda e, c, p, i: p.update({"punctuations": [
        x for x in p["punctuations"] if x["mark"] != "》"]}))


def test_version_mirror():
    only("version_mirror", lambda e, c, p, i: i["chapters"][0].update({"entity_version": "2.0.0"}))


if __name__ == "__main__":
    failed = 0
    for name in sorted(n for n in dir(sys.modules[__name__]) if n.startswith("test_")):
        try:
            globals()[name]()
            print("ok  ", name)
        except AssertionError as exc:
            failed += 1
            print("FAIL", name, exc)
    print("全部通过" if not failed else f"{failed} 个失败")
    sys.exit(1 if failed else 0)
