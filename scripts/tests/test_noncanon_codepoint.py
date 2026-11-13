"""F-OV-18 非本书码位：validate_text_format.noncanon_problems / codepoint_map_for。运行：python3 -m pytest scripts/tests 或直接 python3 本文件。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import validate_text_format as V  # noqa: E402


def _char(*chars):
    return {"pages": [{"columns": [{"cells": [{"a": f"1:1:{i + 1}", "c": c} for i, c in enumerate(chars)]}]}]}


def test_default_pairs_flagged():
    norm = V.codepoint_map_for(V.load_codepoints(), "x")
    probs = V.noncanon_problems(_char("别", "別", "晩", "屛", "晚", "屏"), norm)
    assert {s for _, s in probs} == {"屛→屏", "别→別", "晩→晚"}


def test_canonical_clean():
    norm = V.codepoint_map_for(V.load_codepoints(), "x")
    assert V.noncanon_problems(_char("別", "晚", "屏", "即", "卽"), norm) == []


def test_book_override_and_count():
    cp = {"default": {"别": "別"}, "books": {"b1": {"刋": "刊"}}}
    assert V.codepoint_map_for(cp, "b2") == {"别": "別"}
    norm = V.codepoint_map_for(cp, "b1")
    probs = V.noncanon_problems(_char(*["刋"] * 7), norm)
    assert len(probs) == 1 and "7 格" in probs[0][0]


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ok")
