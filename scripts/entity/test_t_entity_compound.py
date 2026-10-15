import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from t_entity_compound import apply, cell_seq

CHARS = "禮部尚書泰州如臯韶州教授東湖書院山長"
# 两页：前 6 格在 1 页 1 列；其余在 2 页 3 列，含子列 a／b 的格位 key
CELLS1 = [{"a": "1:1:%d" % (i + 1), "c": c} for i, c in enumerate(CHARS[:6])]
CELLS2 = [{"a": "1:2:%d%s" % (i // 2 + 1, "ab"[i % 2]), "c": c} for i, c in enumerate(CHARS[6:])]
CHAR = {"pages": [{"page": 1, "columns": [{"col": 1, "cells": CELLS1}, {"col": 2, "cells": CELLS2}]}]}


def ent(i, text, typ, start):
    return {"id": "e%05d" % i, "type": typ, "text": text,
            "anchor": {"start": "", "end": ""},
            "span": {"start_offset": start, "end_offset": start + len(text)},
            "target": {"status": "new_candidate", "canonical_name": text}, "source": "t"}


def tables():
    cand = lambda sub, i, n: {"id": i, "subtype": sub, "primary_name": n, "level": "concrete"}
    return {
        "dynasty": {"keys": {}},
        "office": {"keys": {"尚書": [cand("office", "o1", "尚書")], "教授": [cand("office", "o2", "教授")],
                            "書院山長": [cand("office", "o3", "書院山長")], "禮部": [cand("官署", "i1", "禮部")]}},
        "place": {"keys": {"泰州": [cand("place", "p1", "泰州")], "如臯": [cand("place", "p2", "如臯縣")],
                           "韶州": [cand("place", "p3", "韶州")], "東湖": [cand("place", "p4", "東湖")]}},
    }


def run(entities):
    j = {"entities": entities, "stats": {}}
    rep = apply(CHAR, j, tables(), write=True)
    return j, rep


def test_office_split_with_anchors():
    j, rep = run([ent(1, "禮部尚書", "office", 0)])
    a, b = j["entities"]
    assert (a["text"], b["text"]) == ("禮部", "尚書")
    assert a["anchor"] == {"start": "1:1:1", "end": "1:1:2"} and b["anchor"] == {"start": "1:1:3", "end": "1:1:4"}
    assert a["span"] == {"start_offset": 0, "end_offset": 2} and b["span"] == {"start_offset": 2, "end_offset": 4}
    assert a["group"] == b["group"] and a["group"]["text"] == "禮部尚書"
    assert b["target"]["status"] == "matched" and a["target"]["entity_id"] == "i1"
    assert a["id"] == "e00001" and b["id"] == "e00002"


def test_place_compound():
    j, _ = run([ent(1, "泰州如臯", "place", 4)])
    a, b = j["entities"]
    assert (a["text"], a["type"], b["text"], b["type"]) == ("泰州", "place", "如臯", "place")
    assert a["anchor"]["start"] == "1:1:5" and b["anchor"]["end"] == "1:2:1b"


def test_place_plus_office_across_subcolumns():
    j, _ = run([ent(1, "韶州教授", "office", 8)])
    a, b = j["entities"]
    assert (a["type"], b["type"]) == ("place", "office")
    assert a["anchor"] == {"start": "1:2:2a", "end": "1:2:2b"} and b["anchor"] == {"start": "1:2:3a", "end": "1:2:3b"}


def test_academy_name_not_split():
    j, rep = run([ent(1, "東湖書院山長", "office", 12)])
    assert len(j["entities"]) == 1 and not rep


def test_matched_whole_untouched_and_stats():
    e = ent(1, "禮部尚書", "office", 0)
    e["target"] = {"status": "matched", "entity_id": "x", "canonical_name": "禮部尚書", "href": "h"}
    j, rep = run([e, ent(2, "泰州如臯", "place", 4)])
    assert j["entities"][0]["text"] == "禮部尚書" and len(rep) == 1
    assert j["stats"]["total_entities"] == 3 and j["stats"]["places"] == 2
    assert [x["id"] for x in j["entities"]] == ["e00001", "e00002", "e00003"]
