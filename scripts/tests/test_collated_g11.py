"""F-CE-06 整理本章 json 新写法（schema 审查第 11 组第二批，2026-11）：章顶层只留 title／sections／meta，section 只写 work_ids。"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
spec = importlib.util.spec_from_file_location('vtf', os.path.join(HERE, '..', 'validate_text_format.py'))
vtf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtf)


def subs(d):
    return [s for _m, s in vtf.collated_chapter_problems(d)]


def test_new_form_ok():
    assert subs({"title": "卷一", "meta": {"page_title": "x", "source_url": "u"},
                 "sections": [{"title": "a", "type": "book", "level": 2, "content": "c", "work_ids": ["w1", "w2"]},
                              {"title": "b", "type": "book", "level": 2, "content": "c", "work_ids": []},
                              {"title": "c", "type": "category", "level": 1, "content": ""}]}) == []


def test_old_forms_flagged():
    d = {"title": "卷一", "page_title": "x", "sections": [
        {"title": "a", "type": "book", "work_id": "w1"},
        {"title": "b", "type": "book"},
        {"title": "c", "type": "book", "work_ids": "w1"}]}
    assert subs(d) == ["top", "0:work_id", 1, "2:work_ids"]


def test_meta_must_be_object_and_non_chapter_ignored():
    assert subs({"title": "x", "meta": [], "sections": []}) == ["meta"]
    assert subs({"chapters": []}) == []
