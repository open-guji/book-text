"""F-OV-16：book-text 只录首选字，char 不许带 pending_reason、不许用 v0.4（sheldon 2026-11-09 定）。"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
spec = importlib.util.spec_from_file_location('vtf', os.path.join(HERE, '..', 'validate_text_format.py'))
vtf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtf)

V01 = "https://open-guji.org/schema/char/v0.1.json"
V04 = "https://open-guji.org/schema/char/v0.4.json"


def char(cells, schema=V01):
    return {"$schema": schema, "version": "0.5.4", "book_id": "96mid1ogzk", "volume": 20,
            "pages": [{"page": 3, "columns": [{"col": 4, "cells": cells}]}]}


def subs(ch):
    return [s for _m, s in vtf.pending_reason_problems(ch)]


def test_plain_cells_ok():
    assert subs(char([{"a": "3:4:1", "c": "已"}, {"a": "3:4:2", "c": "□", "lacuna": True}])) == []


def test_pending_reason_forbidden():
    assert subs(char([{"a": "3:4:1", "c": "已", "pending_reason": "hard_pair"}])) == ["cell:3:4:1"]
    many = char([{"a": f"3:4:{i}", "c": "已", "pending_reason": "unknown"} for i in range(1, 8)])
    assert subs(many)[-1] == "more" and len(subs(many)) == 6


def test_v04_schema_forbidden():
    assert subs(char([{"a": "3:4:1", "c": "已"}], schema=V04)) == ["char_schema"]


def test_reason_table_copy_still_readable():
    assert "unknown" in vtf.pending_reasons()
