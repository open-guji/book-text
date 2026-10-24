"""check_cell_provenance.py（GUJI-733：格变动必须有出处）单测。"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ccp", os.path.join(HERE, "..", "check_cell_provenance.py"))
ccp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ccp)


def char(*cs):
    return {"pages": [{"page": 3, "columns": [{"col": 1, "cells": [{"a": a, "c": c} for a, c in cs]}]}]}


def test_changed_cells_edit_add_remove():
    old = char(("3:1:1", "甲"), ("3:1:2", "乙"), ("3:1:3", "丙"))
    new = char(("3:1:1", "甲"), ("3:1:2", "丁"), ("3:1:4", "戊"))
    assert ccp.changed_cells(old, new) == ["3:1:2", "3:1:3", "3:1:4"]
    assert ccp.changed_cells(old, old) == []
    assert ccp.changed_cells(None, old) == ["3:1:1", "3:1:2", "3:1:3"]


def test_flag_changed_not_just_lacuna_key():
    a = char(("3:1:1", "□"))
    b = {"pages": [{"page": 3, "columns": [{"col": 1, "cells": [{"a": "3:1:1", "c": "□", "lacuna": True, "guess_c": "一"}]}]}]}
    assert ccp.changed_cells(a, b) == ["3:1:1"]


def test_has_provenance_requires_entry_vol_and_token():
    ok = ["| 2026-10-23 | 96mid1ogzk/002 | 文本 | 1.0.2→1.0.3 | 读者意见 op_span_29a02d06d6 | #218 |"]
    assert ccp.has_provenance(ok, "96mid1ogzk", "002")
    assert not ccp.has_provenance(ok, "96mid1ogzk", "003")                     # 别的章
    assert not ccp.has_provenance(["| x | 96mid1ogzk/002 | 文本 | 1→2 | 改了 3 格 | #1 |"], "96mid1ogzk", "002")
    for tok in ("evt_b1_000001", "vol05-r8", "004-r6", "GUJI-697"):
        assert ccp.has_provenance([f"| x | 96mid1ogzk/005 | 文本 | 1→2 | 说明 {tok} | #1 |"], "96mid1ogzk", "005")
