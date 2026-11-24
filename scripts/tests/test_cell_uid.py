"""字格永久编号 u（guji-format 02 §4.10，char v0.6；F-OV-18 与 cell_uid 工具）。"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import cell_uid as CU  # noqa: E402


def char(cells, **top):
    d = {"$schema": CU.CHAR_V06, "version": "0.2.0", "book_id": "b", "volume": 1}
    d.update(top)
    d["pages"] = [{"page": 1, "columns": [{"col": 1, "cells": cells}]}]
    return d


def plain():
    return {"$schema": "https://open-guji.org/schema/char/v0.1.json", "version": "0.2.0", "book_id": "b", "volume": 1,
            "pages": [{"page": 1, "columns": [{"col": 1, "cells": [
                {"a": "1:1:1", "c": "欽"}, {"a": "1:1:2", "c": "定"}, {"a": "1:1:3", "c": "四"}, {"a": "1:1:4", "c": "庫"}]}]}]}


def subs(probs):
    return {s for _m, s in probs}


# ── 形状 ──

def test_plain_char_has_no_u_problems():
    assert CU.u_problems(plain()) == []
    assert not CU.has_u(plain())


def test_number_char_reading_order():
    c = plain()
    st = CU.number_char(c)
    assert st == {"cells": 4, "from_map": 0, "new": 4, "u_max": 4}
    assert [x["u"] for x in CU.cells(c)] == [1, 2, 3, 4]
    assert list(CU.cells(c)[0]) == ["a", "u", "c"]          # u 紧跟 a
    assert list(c)[:6] == ["$schema", "version", "book_id", "volume", "u_max", "pages"]
    assert c["$schema"] == CU.CHAR_V06
    assert CU.u_problems(c) == []
    assert CU.number_char(c) is None                         # 已上 u 不重编


def test_number_char_from_ledger_map():
    c = plain()
    st = CU.number_char(c, amap={"1:1:1": 10, "1:1:2": 11, "1:1:4": 13}, umax=20)
    assert [x["u"] for x in CU.cells(c)] == [10, 11, 21, 13]
    assert st["u_max"] == 21 and st["from_map"] == 3 and st["new"] == 1
    assert CU.u_problems(c) == []


def test_u_problems_catch_each_rule():
    c = char([{"a": "1:1:1", "u": 1, "c": "甲"}, {"a": "1:1:2", "u": 1, "c": "乙"},
              {"a": "1:1:3", "c": "丙"}, {"a": "1:1:4", "u": 9, "c": "丁"}, {"a": "1:1:5", "u": 3, "c": "戊"}],
             u_max=5, u_retired=[{"u": 3, "gone": True}, {"u": 4, "into": 99}, {"u": 2, "into": 1, "gone": True}])
    s = subs(CU.u_problems(c))
    assert "dup:1" in s
    assert "cell:1:1:3:missing" in s           # 新格无 u
    assert "cell:1:1:4:max" in s               # 超 u_max
    assert "cell:1:1:5:retired" in s           # 用了作废号
    assert "retired:into:4" in s               # into 指向不存在
    assert "retired:2" in s                    # into 与 gone 同在


def test_u_without_u_max_and_wrong_schema():
    c = char([{"a": "1:1:1", "u": 1, "c": "甲"}])
    c["$schema"] = "https://open-guji.org/schema/char/v0.5.json"
    s = subs(CU.u_problems(c))
    assert {"u_max:missing", "schema"} <= s


# ── 前后版 ──

def test_continuity():
    old = char([{"a": "1:1:1", "u": 1, "c": "甲"}, {"a": "1:1:2", "u": 2, "c": "乙"}, {"a": "1:1:3", "u": 3, "c": "丙"}],
               u_max=3)
    new = copy.deepcopy(old)
    new["pages"][0]["columns"][0]["cells"] = [CU.cells(old)[0], CU.cells(old)[2]]   # 删了乙却没登记作废
    assert "lost:2" in subs(CU.continuity_problems(old, new))
    assert CU.retire_missing(old, new) == [(2, None)]
    assert new["u_retired"] == [{"u": 2, "gone": True}]
    assert CU.continuity_problems(old, new) == []
    assert CU.u_problems(new) == []
    newer = copy.deepcopy(new)
    newer["u_max"] = 2
    newer["u_retired"] = []
    s = subs(CU.continuity_problems(new, newer))
    assert {"u_max", "retired:changed:2"} <= s


def test_continuity_plain_old_is_fine():
    c = plain()
    n = copy.deepcopy(c)
    CU.number_char(n)
    assert CU.continuity_problems(c, n) == []
    assert subs(CU.continuity_problems(n, plain())) == {"dropped"}


# ── 发号 ──

def test_assign_new_takes_u_max_plus_one():
    c = char([{"a": "1:1:1", "u": 1, "c": "甲"}, {"a": "1:1:2", "c": "補"}, {"a": "1:1:3", "u": 2, "c": "乙"}],
             u_max=5, u_retired=[{"u": 5, "gone": True}])
    assert CU.assign_new(c) == [("1:1:2", 6)]
    assert c["u_max"] == 6
    assert CU.u_problems(c) == []


# ── 伴生层 ──

def _numbered():
    c = plain()
    CU.number_char(c)
    return c


def test_layer_requires_u_once_char_has_u():
    c = _numbered()
    p = {"$schema": "https://open-guji.org/schema/punct/v0.2.json",
         "punctuations": [{"mark": "。", "pos": "after", "anchor": "1:1:4", "pre_char": "庫"}]}
    assert subs(CU.layer_u_problems(c, "punct", p)) == {"p0:nou"}
    assert CU.layer_u_problems(plain(), "punct", p) == []   # 没上 u 的册不要求


def test_number_layer_and_consistency():
    c = _numbered()
    p = {"$schema": "https://open-guji.org/schema/punct/v0.2.json",
         "punctuations": [{"mark": "。", "pos": "after", "anchor": "1:1:4", "pre_char": "庫"},
                          {"mark": "，", "pos": "after", "anchor": "9:9:9", "pre_char": "無"}]}
    e = {"$schema": "https://open-guji.org/schema/entity/v0.3.json",
         "entities": [{"id": "e1", "type": "work", "text": "四庫", "anchor": {"start": "1:1:3", "end": "1:1:4"}}]}
    n = {"schema": "guji-norm/0.2", "book_id": "b", "volume": 1, "table": None,
         "items": [{"a": "1:1:2", "c": "定", "t": "定", "by": "table"}]}
    assert CU.number_layer(c, "punct", p) == (1, [(1, "9:9:9", "格位在 char 里找不到")])
    assert p["$schema"] == CU.PUNCT_V04
    assert list(p["punctuations"][0]) == ["mark", "pos", "anchor", "u", "pre_char"]
    assert CU.number_layer(c, "entity", e)[0] == 1
    assert e["entities"][0]["u_start"] == 3 and e["entities"][0]["u_end"] == 4
    assert CU.number_layer(c, "norm", n)[0] == 1
    assert list(n)[0] == "$schema" and "schema" not in n and n["items"][0]["u"] == 2
    for line, d in (("entity", e), ("norm", n)):
        assert CU.layer_u_problems(c, line, d) == []
    # 双写不一致
    p["punctuations"][0]["anchor"] = "1:1:3"
    assert "p0:anchor" in subs(CU.layer_u_problems(c, "punct", p))
    e["entities"][0]["u_end"] = 2
    assert "e0:order" in subs(CU.layer_u_problems(c, "entity", e))


# ── 重挂（补字、删字、并格）──

def test_relink_after_insert_and_delete():
    old = _numbered()                         # 欽1 定2 四3 庫4
    new = copy.deepcopy(old)
    # 补「書」「全」在「四」前，删「定」：格位 key 全列重排
    new["pages"][0]["columns"][0]["cells"] = [
        {"a": "1:1:1", "u": 1, "c": "欽"}, {"a": "1:1:2", "c": "書"}, {"a": "1:1:3", "c": "全"},
        {"a": "1:1:4", "u": 3, "c": "四"}, {"a": "1:1:5", "u": 4, "c": "庫"}]
    assert CU.assign_new(new) == [("1:1:2", 5), ("1:1:3", 6)]
    assert CU.retire_missing(old, new) == [(2, None)]
    p = {"$schema": CU.PUNCT_V04, "punctuations": [
        {"mark": "。", "pos": "after", "anchor": "1:1:4", "u": 4, "pre_char": "庫"},
        {"mark": "，", "pos": "after", "anchor": "1:1:2", "u": 2, "pre_char": "定"},
        {"mark": "#", "kind": "heading", "pos": "before", "anchor": "1:1:2", "u": 2, "label": "x"}]}
    moved, review = CU.relink(new, "punct", p, old_char=old)
    pts = p["punctuations"]
    assert (pts[0]["anchor"], pts[0]["u"], pts[0]["pre_char"]) == ("1:1:5", 4, "庫")   # 跟字走
    assert (pts[1]["anchor"], pts[1]["u"]) == ("1:1:1", 1)        # 删字：after 挪前邻格
    assert pts[1]["pre_char"] == "定"                             # 校验字只报不改
    assert (pts[2]["anchor"], pts[2]["u"]) == ("1:1:4", 3)        # 删字：before 挪后邻格
    assert moved == 3 and [r[0] for r in review] == [1, 2]
    assert CU.layer_u_problems(new, "punct", p) == []
    assert CU.u_problems(new) == [] and CU.continuity_problems(old, new) == []


def test_relink_follows_merge_and_reports_whole_entity_gone():
    c = char([{"a": "1:1:1", "u": 1, "c": "甲"}, {"a": "1:1:2", "u": 3, "c": "丙"}],
             u_max=3, u_retired=[{"u": 2, "into": 1}])
    n = {"$schema": CU.NORM_V03, "book_id": "b", "volume": 1, "items": [{"a": "1:1:2", "u": 2, "c": "乙", "t": "乙"}]}
    moved, review = CU.relink(c, "norm", n)
    assert n["items"][0]["a"] == "1:1:1" and n["items"][0]["u"] == 1 and "并进" in review[0][3]
    e = {"$schema": CU.ENTITY_V04, "entities": [
        {"id": "e1", "type": "x", "text": "乙", "anchor": {"start": "1:1:9", "end": "1:1:9"}, "u_start": 7, "u_end": 7}]}
    _m, review = CU.relink(c, "entity", e)
    assert review and review[0][2] is None
    assert e["entities"][0]["anchor"]["start"] == "1:1:9"          # 对不上的不动
