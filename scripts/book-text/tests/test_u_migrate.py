# -*- coding: utf-8 -*-
"""u_migrate：plan 不写盘，apply 只加 u（去掉 u 逐字节同），身份账按账发号。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from test_bump_original import _read, _write, make_repo, run  # noqa: E402
import cell_uid as CU  # noqa: E402
import u_migrate  # noqa: E402


def test_plan_then_apply(tmp_path, capsys):
    entry, od = make_repo(str(tmp_path))
    run(entry, "--init")
    before = {f: open(os.path.join(od, f), encoding="utf-8").read() for f in os.listdir(od)}
    out = os.path.join(str(tmp_path), "plan.tsv")
    assert u_migrate.main(["plan", od, "--out", out]) == 0
    assert {f: open(os.path.join(od, f), encoding="utf-8").read() for f in os.listdir(od)} == before
    assert "可迁" in open(out, encoding="utf-8").read()
    assert u_migrate.main(["apply", od, "--approved-by", "test"]) == 0
    c, p, e = (_read(os.path.join(od, f"002.{x}.json")) for x in ("char", "punct", "entity"))
    assert c["u_max"] == len(CU.cells(c)) and CU.u_problems(c) == []
    assert all("u" in x for x in p["punctuations"]) and all("u_start" in x for x in e["entities"])
    assert u_migrate.strip_u(c) == u_migrate.strip_u(json.loads(before["002.char.json"]))
    # 再跑一次：已上 u，跳过
    assert u_migrate.main(["apply", od, "--approved-by", "test"]) == 0


def test_ledger(tmp_path):
    entry, od = make_repo(str(tmp_path))
    led = os.path.join(str(tmp_path), "uid")
    os.makedirs(led)
    with open(os.path.join(led, "vol02.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"page": 3, "cells_sha": "x", "map": {"1:1": 100, "1:2": 101},
                            "lineage": [{"u": 102, "merged_into": 101}, {"u": 103, "gone": True}]}) + "\n")
    amap, umax, ret = u_migrate.load_ledger(led, 2)
    assert amap == {"3:1:1": 100, "3:1:2": 101} and umax == 103
    assert ret == [{"u": 102, "into": 101}, {"u": 103, "gone": True}]
    rep, writes = u_migrate.migrate_chapter(od, "002", led)
    assert rep["problems"] == [] and rep["from_ledger"] == 2
    c = writes[os.path.join(od, "002.char.json")]
    assert [x["u"] for x in CU.cells(c)][:3] == [100, 101, 104]
    assert c["u_retired"] == ret
