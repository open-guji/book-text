"""F-OV-16：待审格 pending_reason（guji-format 02 §4.8，char v0.4；sheldon 2026-11-03 定）。"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
spec = importlib.util.spec_from_file_location('vtf', os.path.join(HERE, '..', 'validate_text_format.py'))
vtf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtf)

V04 = "https://open-guji.org/schema/char/v0.4.json"


def char(cells, schema=V04):
    return {"$schema": schema, "version": "0.5.4", "book_id": "96mid1ogzk", "volume": 20,
            "pages": [{"page": 3, "columns": [{"col": 4, "cells": cells}]}]}


def subs(ch):
    return [s for _m, s in vtf.pending_reason_problems(ch)]


def test_ok_cells():
    assert subs(char([{"a": "3:4:1", "c": "□", "pending_reason": "ref_lacuna"},
                      {"a": "3:4:2", "c": "已", "pending_reason": "hard_pair"},
                      {"a": "3:4:3", "c": "□", "lacuna": True, "guess_c": "一"},
                      {"a": "3:4:4", "c": "定", "pending_reason": "unknown"}])) == []


def test_bad_value_and_mixed():
    assert subs(char([{"a": "3:4:1", "c": "□", "pending_reason": "Hard Pair"}])) == ["cell:3:4:1:shape"]
    assert subs(char([{"a": "3:4:1", "c": "□", "pending_reason": "no_such_reason"}])) == ["cell:3:4:1:unknown_value"]
    assert subs(char([{"a": "3:4:1", "c": "□", "lacuna": True, "pending_reason": "ref_lacuna"}])) == ["cell:3:4:1:mixed"]


def test_schema_must_be_v04():
    assert subs(char([{"a": "3:4:1", "c": "□", "pending_reason": "ref_lacuna"}],
                     schema="https://open-guji.org/schema/char/v0.3.json")) == ["char_schema"]
    assert subs(char([{"a": "3:4:1", "c": "□", "lacuna": True}], schema="https://open-guji.org/schema/char/v0.3.json")) == []


def test_reason_table_copy():
    d = json.load(open(vtf.PENDING_REASONS_FILE, encoding="utf-8"))
    assert "unknown" in d["reasons"] and len(d["reasons"]) >= 29
    assert all(vtf.PENDING_REASON_RE.match(k) for k in d["reasons"])
