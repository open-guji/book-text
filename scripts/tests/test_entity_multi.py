"""F-OV-14：专名多链接 matched_multi 的形状。"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
spec = importlib.util.spec_from_file_location('vtf', os.path.join(HERE, '..', 'validate_text_format.py'))
vtf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtf)


def tg(i, n, part=None):
    return ({"part": part} if part else {}) | {"entity_id": i, "canonical_name": n, "href": "book-index://Entity/" + i}


def doc(target, text="正嘉"):
    return {"entities": [{"id": "e1", "type": "reign", "text": text, "target": target}]}


OK = {"status": "matched_multi", "canonical_name": "正德＋嘉靖", "targets": [tg("a1", "正德", "正"), tg("b2", "嘉靖", "嘉")]}


def test_ok_and_single_ignored():
    assert vtf.entity_multi_problems(doc(OK)) == []
    assert vtf.entity_multi_problems(doc({"status": "matched", "entity_id": "a1"})) == []


def test_part_optional():
    t = dict(OK, targets=[tg("a1", "甲"), tg("b2", "乙")])
    assert vtf.entity_multi_problems(doc(t)) == []


def test_bad_shapes():
    assert vtf.entity_multi_problems(doc(dict(OK, targets=[tg("a1", "正德")])))  # <2
    assert vtf.entity_multi_problems(doc(dict(OK, entity_id="a1")))  # 顶层带 id
    bad = tg("a1", "正德"); bad["href"] = "book-index://Entity/zzz"
    assert vtf.entity_multi_problems(doc(dict(OK, targets=[bad, tg("b2", "嘉靖")])))  # href 尾段
    bad2 = tg("a1", "正德"); del bad2["canonical_name"]
    assert vtf.entity_multi_problems(doc(dict(OK, targets=[bad2, tg("b2", "嘉靖")])))
    assert vtf.entity_multi_problems(doc(dict(OK, targets=[tg("a1", "正德", "隆"), tg("b2", "嘉靖")])))  # part 不在 text
    assert vtf.entity_multi_problems(doc(dict(OK, targets=[tg("a1", "正德", "嘉"), tg("b2", "嘉靖", "正")])))  # 全写 part 但拼不回 text
    assert vtf.entity_multi_problems(doc(dict(OK, targets=[tg("a1", "正德", "正"), tg("b2", "嘉靖", "嘉")]), text="正嘉以")) # 少一字
