# -*- coding: utf-8 -*-
"""字格永久编号 u 存量迁移（guji-format 02 §4.10，char v0.6；punct／entity v0.4、norm v0.3；2026-11-24）。

给 original 的 char 每格写 u（顶层 u_max），punct／entity／norm 按格位 key 补 u（双写：格位 key 照留，两者指同一格），
各文件 $schema 升到带 u 的版本。只加字段，不改字、不改格位、不改校验字、不升版本号。

  plan   python3 u_migrate.py plan <original 目录…> [--chapter 031 …] [--ledger <身份账目录>] [--out 提案.tsv]
         只出提案，不写文件：每册格数、u_max、各层补 u 条数、格位在 char 里找不到的条目；并在内存里迁一遍，
         核「迁后 F-OV-18 全过、去掉 u 后与迁前逐字节相同、文本读序不变」。
  apply  python3 u_migrate.py apply <original 目录> --chapter 031 [--ledger …] --approved-by <谁在哪儿点的头>
         真写。动 book-text 正式数据，要先回主导线程（CV0「设计字格永久编号 u」）拿到点头，--approved-by 必填。
         写完照常 local_check.py、按仓规提交（不升版本号：只加 u，文本、标点、实体内容都没变）。

身份账（guji-manager T1，`<feedback>/uid/<册>.jsonl`，一行一页一次切分：page、cells_sha、map 格号→u、lineage）：
给了 --ledger 就按账发号（每页取最后一行的 map），账里没有的格接着 u_max 往后发；没给就按读序 1..N。
账里 lineage 的并、删（{u, into}／{u, gone: true} 或 merged_into／gone）照抄进 u_retired。
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import cell_uid as CU  # noqa: E402
import original_version as OV  # noqa: E402

LINES = ("punct", "entity", "norm")


def strip_u(obj):
    """去掉 u 相关字段、把 $schema 还原前的比较用：返回深拷贝。"""
    o = copy.deepcopy(obj)
    o.pop("u_max", None)
    o.pop("u_retired", None)
    o.pop("$schema", None)
    o.pop("schema", None)
    for c in CU.cells(o):
        c.pop("u", None)
    for key in ("punctuations", "entities", "items"):
        for e in o.get(key) or []:
            if isinstance(e, dict):
                for k in ("u", "u_start", "u_end"):
                    e.pop(k, None)
    return o


def load_ledger(ledger_dir, vol):
    """身份账 → ({格位 key: u}, u_max, [u_retired 项])；找不到账返回 (None, None, None)。"""
    if not ledger_dir:
        return None, None, None
    cands = [os.path.join(ledger_dir, f"{n}.jsonl") for n in (f"vol{vol:02d}", f"vol{vol}", f"{vol:03d}", str(vol))]
    path = next((p for p in cands if os.path.isfile(p)), None)
    if path is None:
        return None, None, None
    pages, umax, retired = {}, 0, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pg = row.get("page")
            pages[pg] = row
            for v in (row.get("map") or {}).values():
                if isinstance(v, int):
                    umax = max(umax, v)
            for lg in row.get("lineage") or []:
                if not isinstance(lg, dict) or not isinstance(lg.get("u"), int):
                    continue
                umax = max(umax, lg["u"])
                into = lg.get("into", lg.get("merged_into"))
                if isinstance(into, int):
                    retired[lg["u"]] = {"u": lg["u"], "into": into}
                elif lg.get("gone") is True:
                    retired[lg["u"]] = {"u": lg["u"], "gone": True}
            if isinstance(row.get("u_max"), int):
                umax = max(umax, row["u_max"])
    amap = {}
    for pg, row in pages.items():
        for k, v in (row.get("map") or {}).items():
            key = k if str(k).count(":") == 2 else f"{pg}:{k}"
            amap[key] = v
    live = set(amap.values())
    return amap, umax, [r for u, r in sorted(retired.items()) if u not in live]


def migrate_chapter(od, stem, ledger_dir=None):
    """内存里迁一册，返回 (报告 dict, {路径: 新对象})；不写盘。"""
    rep = {"dir": od, "chapter": stem}
    char_path = OV.companion_path(od, stem, "text")
    char = OV.load_json(char_path)
    if CU.has_u(char):
        rep["status"] = "已上 u，跳过"
        return rep, {}
    before = copy.deepcopy(char)
    amap, umax, retired = load_ledger(ledger_dir, int(stem)) if str(stem).isdigit() else (None, None, None)
    st = CU.number_char(char, amap=amap, umax=umax, retired=retired)
    rep.update(status="可迁", cells=st["cells"], u_max=st["u_max"], from_ledger=st["from_map"] if amap else "",
               ledger_new=st["new"] if amap else "")
    writes = {char_path: char}
    problems = [f"char: {m}" for m, _s in CU.u_problems(char)]
    if strip_u(char) != strip_u(before) or OV.char_slots(char) != OV.char_slots(before):
        problems.append("char: 去掉 u 后与迁前不同（不该发生）")
    for line in LINES:
        cf = os.path.join(od, f"{stem}.{line}.json")
        if not os.path.isfile(cf):
            continue
        data = OV.load_json(cf)
        orig = copy.deepcopy(data)
        added, miss = CU.number_layer(char, line, data)
        rep[f"{line}_u"] = added
        rep[f"{line}_miss"] = len(miss)
        problems += [f"{line} #{i} {a}：{why}（没补 u）" for i, a, why in miss[:10]]
        lp = [m for m, sub in CU.layer_u_problems(char, line, data)]
        # 格位找不到的条目本来就该 F-OV-02 报；这里只把 u 本身的问题算进来
        lp = [m for m in lp if "没写 u" not in m] + ([f"{len(miss)} 条格位在 char 里找不到"] if miss else [])
        problems += [f"{line}: {m}" for m in lp[:10]]
        if strip_u(data) != strip_u(orig):
            problems.append(f"{line}: 去掉 u 后与迁前不同（不该发生）")
        if added:
            writes[cf] = data
    rep["problems"] = problems
    return rep, writes


def chapters_of(od, wanted):
    idx = OV.load_json(os.path.join(od, "index.json"))
    out = []
    for ch in idx.get("chapters") or []:
        stem = OV.chapter_file(ch)
        if stem and (not wanted or stem in wanted) and os.path.isfile(OV.companion_path(od, stem, "text")):
            out.append(stem)
    return out


def resolve_dirs(paths):
    out = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(os.path.join(p, "index.json")) and glob.glob(os.path.join(p, "*.char.json")):
            out.append(p)
        else:
            out += sorted(os.path.dirname(f) for f in glob.glob(os.path.join(p, "*", "index.json"))
                          if glob.glob(os.path.join(os.path.dirname(f), "*.char.json")))
    return out


COLS = ("dir", "chapter", "status", "cells", "u_max", "from_ledger", "ledger_new",
        "punct_u", "punct_miss", "entity_u", "entity_miss", "norm_u", "norm_miss", "problems")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pa = sub.add_parser("apply")
    for p in (pl, pa):
        p.add_argument("dirs", nargs="+", help="original 版本目录，或其上层条目目录")
        p.add_argument("--chapter", action="append", help="只迁这几册，如 031（可多次）")
        p.add_argument("--ledger", help="身份账目录（guji-manager 的 <feedback>/uid/）")
    pl.add_argument("--out", help="提案写到这个 tsv")
    pa.add_argument("--approved-by", required=True, help="谁、在哪儿同意动正式数据（写进输出，提交信息照抄）")
    a = ap.parse_args(argv)
    rows, all_writes = [], {}
    for od in resolve_dirs(a.dirs):
        for stem in chapters_of(od, set(a.chapter or [])):
            rep, writes = migrate_chapter(od, stem, a.ledger)
            rows.append(rep)
            all_writes.update(writes)
    n_ok = sum(1 for r in rows if r.get("status") == "可迁")
    n_prob = sum(1 for r in rows if r.get("problems"))
    cells = sum(r.get("cells") or 0 for r in rows)
    print(f"共 {len(rows)} 册：可迁 {n_ok}、已上 u {len(rows) - n_ok}；字格 {cells}；"
          f"标点补 u {sum(r.get('punct_u') or 0 for r in rows)}、专名 {sum(r.get('entity_u') or 0 for r in rows)}、"
          f"异体 {sum(r.get('norm_u') or 0 for r in rows)}；有问题 {n_prob} 册")
    for r in rows:
        for m in (r.get("problems") or [])[:5]:
            print(f"  {os.path.basename(os.path.dirname(r['dir']))}/{r['chapter']}：{m}")
    if a.cmd == "plan":
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write("\t".join(COLS) + "\n")
                for r in rows:
                    f.write("\t".join("；".join(r.get(c) or []) if c == "problems" else str(r.get(c, ""))
                                      for c in COLS) + "\n")
        return 0
    if n_prob:
        print("有问题的册先处理，apply 不写", file=sys.stderr)
        return 2
    for path, obj in all_writes.items():
        OV.dump_like(path, obj)
    print(f"已写 {len(all_writes)} 个文件（{a.approved_by}）；不升版本号，提交前跑 local_check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
