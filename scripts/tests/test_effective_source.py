# -*- coding: utf-8 -*-
"""产出方取值（guji-format 00 §4.6）：条目 source 优先，缺了取文件头 default_source；锚点漂移的 rule: 判定跟着走。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import original_version as OV  # noqa: E402


def test_effective_source():
    doc = {"default_source": "rule:reflow", "punctuations": []}
    assert OV.effective_source({"mark": "。"}, doc) == "rule:reflow"
    assert OV.effective_source({"mark": "。", "source": "human:x"}, doc) == "human:x"
    assert OV.effective_source({"mark": "。"}, {"punctuations": []}) == ""      # v0.2：不写就是未知
    assert OV.effective_source({"mark": "。"}) == ""


def test_drift_rule_from_default_source(tmp_path, monkeypatch):
    """v0.3 条目省了 source、文件头是 rule:… 时，漂移仍判硬失败（不能悄悄降成告警）。"""
    import json

    import check_anchor_drift as D
    old_c = {"pages": [{"page": 1, "columns": [{"col": 1, "cells": [{"a": "1:1:1", "c": "甲"}, {"a": "1:1:2", "c": "乙"}]}]}]}
    new_c = {"pages": [{"page": 1, "columns": [{"col": 1, "cells": [{"a": "1:1:1", "c": "丙"}, {"a": "1:1:2", "c": "甲"},
                                                                     {"a": "1:1:3", "c": "乙"}]}]}]}
    punct = {"default_source": "rule:reflow",
             "punctuations": [{"mark": "\n\n", "kind": "break", "pos": "after", "anchor": "1:1:1", "pre_char": "甲"}]}
    for name, obj in (("001.char.json", new_c), ("001.punct.json", punct)):
        (tmp_path / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(D, "ROOT", str(tmp_path))
    monkeypatch.setattr(D, "git_json", lambda base, path: old_c if path.endswith(".char.json") else punct)
    hard, soft = D.check_file("base", "001.char.json")
    assert len(hard) == 1 and not soft and "rule:reflow" in hard[0]
    punct["default_source"] = "glm:x"                                   # 非 rule: 的只告警
    (tmp_path / "001.punct.json").write_text(json.dumps(punct, ensure_ascii=False), encoding="utf-8")
    hard, soft = D.check_file("base", "001.char.json")
    assert not hard and len(soft) == 1
