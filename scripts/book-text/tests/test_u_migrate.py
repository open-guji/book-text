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
    rows = [
        {"id": "a", "kind": "uid_ledger", "v": 1, "book": "vol02", "page": 0, "target": {"book": "vol02"},
         "cells_sha": None, "map": {}, "lineage": [], "u_max": 90},
        {"id": "b", "kind": "uid_ledger", "v": 1, "book": "vol02", "page": 3, "cells_sha": "s1",
         "map": {"vol02:3:1:1": 50, "vol02:3:1:2": 51}, "lineage": [{"u": 50, "new": True}, {"u": 51, "new": True}]},
        {"id": "c", "kind": "uid_ledger", "v": 1, "book": "vol02", "page": 3, "cells_sha": "s2",
         "map": {"vol02:3:1:1": 100, "vol02:3:1:2": 101},
         "lineage": [{"u": 100, "new": True}, {"u": 101, "split_from": 100}, {"u": 102, "into": 101}, {"u": 103, "gone": True}]},
    ]
    with open(os.path.join(led, "vol02.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))
    amap, umax, ret = u_migrate.load_ledger(led, 2)
    assert amap == {"3:1:1": 100, "3:1:2": 101} and umax == 103
    assert ret == [{"u": 102, "into": 101}, {"u": 103, "gone": True}]
    rep, writes = u_migrate.migrate_chapter(od, "002", led)
    assert rep["problems"] == [] and rep["from_ledger"] == 2
    c = writes[os.path.join(od, "002.char.json")]
    assert [x["u"] for x in CU.cells(c)][:3] == [100, 101, 104]
    assert c["u_retired"] == ret


def _init_ledger(tmp_path, od, umax_extra=500, drop_page=None, drop_cell=None):
    """按 char 读序建 init 行，再加一行 advance（另一套格号、u 相同＋新号），模拟 T1 的账。"""
    c = _read(os.path.join(od, "002.char.json"))
    led = os.path.join(str(tmp_path), "uid")
    os.makedirs(led, exist_ok=True)
    rows, u = [], 0
    for pg in c["pages"]:
        m = {}
        for col in pg["columns"]:
            for x in col["cells"]:
                u += 1
                if x["a"] != drop_cell:
                    m[f"vol02:{x['a']}"] = u
        if pg["page"] != drop_page:
            rows.append({"id": f"i{pg['page']}", "kind": "uid_ledger", "v": 1, "src": "init", "book": "vol02",
                         "page": pg["page"], "map": m, "lineage": []})
        rows.append({"id": f"a{pg['page']}", "kind": "uid_ledger", "v": 1, "src": "advance", "book": "vol02",
                     "page": pg["page"], "map": {f"{k}x": v for k, v in m.items()},
                     "lineage": [{"u": umax_extra, "new": True}, {"u": 1, "gone": True}]})
    with open(os.path.join(led, "vol02.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))
    return led, u


def test_ledger_src_init(tmp_path):
    entry, od = make_repo(str(tmp_path))
    led, n = _init_ledger(tmp_path, od)
    rep, writes = u_migrate.migrate_chapter(od, "002", led, "init")
    assert rep["problems"] == [] and rep["from_ledger"] == n and rep["ledger_new"] == 0
    c = writes[os.path.join(od, "002.char.json")]
    assert [x["u"] for x in CU.cells(c)] == list(range(1, n + 1))
    assert c["u_max"] == 500                      # 取整本账的最大号（含 advance）
    assert "u_retired" not in c                   # 账上作废的 1 在文本里还在：不列
    # 不给 src：按最后一行（advance）读，格号对不上，全部另发
    rep2, _w = u_migrate.migrate_chapter(od, "002", led)
    assert rep2["from_ledger"] == 0


def test_ledger_src_init_missing_page_and_cell(tmp_path):
    entry, od = make_repo(str(tmp_path))
    c = _read(os.path.join(od, "002.char.json"))
    first = CU.cells(c)[0]["a"]
    led, _n = _init_ledger(tmp_path, od, drop_cell=first)
    rep, _w = u_migrate.migrate_chapter(od, "002", led, "init")
    assert any("账里没有" in m for m in rep["problems"])
    assert u_migrate.main(["apply", od, "--ledger", led, "--ledger-src", "init", "--approved-by", "t"]) == 2
    led2 = os.path.join(str(tmp_path), "uid2")
    os.rename(led, led2)
    led, _n = _init_ledger(tmp_path, od, drop_page=c["pages"][0]["page"])
    rep, _w = u_migrate.migrate_chapter(od, "002", led, "init")
    assert any("没有 src=init 行" in m for m in rep["problems"])


def test_numbered_chapter_bumps_u_max_from_ledger(tmp_path):
    entry, od = make_repo(str(tmp_path))
    led, n = _init_ledger(tmp_path, od)
    assert u_migrate.main(["apply", od, "--approved-by", "t"]) == 0          # 先按读序上 u（同试点）
    assert _read(os.path.join(od, "002.char.json"))["u_max"] == n
    assert u_migrate.main(["apply", od, "--ledger", led, "--ledger-src", "init", "--approved-by", "t"]) == 0
    c = _read(os.path.join(od, "002.char.json"))
    assert c["u_max"] == 500 and CU.u_problems(c) == []
    # 文本的 u 与账不符：只报，不改
    c["pages"][0]["columns"][0]["cells"][0]["u"], c["pages"][0]["columns"][0]["cells"][1]["u"] = 2, 1
    _write(os.path.join(od, "002.char.json"), c)
    rep, writes = u_migrate.migrate_chapter(od, "002", led, "init")
    assert writes == {} and any("与账不符" in m for m in rep["problems"])
