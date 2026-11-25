# -*- coding: utf-8 -*-
"""字格永久编号 u 存量迁移（guji-format 02 §4.10，char v0.6；punct／entity v0.4、norm v0.3；2026-11-24）。

给 original 的 char 每格写 u（顶层 u_max），punct／entity／norm 按格位 key 补 u（格位 key 照留给人读，以 u 为准），
各文件 $schema 升到带 u 的版本。2026-11-24 全库 174 册已迁完，本脚本只留给新入库的书。只加字段，不改字、不改格位、不改校验字、不升版本号。

  plan   python3 u_migrate.py plan <original 目录…> [--chapter 031 …] [--ledger <身份账目录>] [--out 提案.tsv]
         只出提案，不写文件：每册格数、u_max、各层补 u 条数、格位在 char 里找不到的条目；并在内存里迁一遍，
         核「迁后 F-OV-18 全过、去掉 u 后与迁前逐字节相同、文本读序不变」。
  apply  python3 u_migrate.py apply <original 目录> --chapter 031 [--ledger …] --approved-by <谁在哪儿点的头>
         真写。动 book-text 正式数据，要先回主导线程（CV0「设计字格永久编号 u」）拿到点头，--approved-by 必填。
         写完照常 local_check.py、按仓规提交（不升版本号：只加 u，文本、标点、实体内容都没变）。

身份账（guji-manager `feedback/uid/<册>.jsonl`，格式见 guji-manager doc/参考/字格身份账.md，v=1）：
给了 --ledger（该目录）就按账发号（每页取最后一行的 map，键「册:页:列:格」去掉册前缀），账里没有的格接着 u_max 往后发；
没给就按读序 1..N。账里 lineage 的 {u, into}／{u, gone: true} 照抄进 u_retired（只抄 char 里确实没有的号）。

--ledger-src init（2026-11-24 与身份账 T1 定）：每页只取 src=init 的那一行（init 是从 book-text dev 现行 char 建的，
格号与 a 一一对应；后来的 advance 行描述 cv 新切分，格号不同、u 相同）。u_max 仍取整本账的最大号（advance 给新切出的格
发了更大的号，book-text 以后改字要从它往后发，取小了会撞号）。缺 init 行的页、账里没有的格都算问题，apply 不写。
已上 u 的册给了账：逐格核 u 与账是否一致，一致且账的 u_max 更大就只把 u_max 调上去（「补 u_max」）。
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


def load_ledger(ledger_dir, vol, src=None, missing=None):
    """身份账（guji-manager doc/参考/字格身份账.md，v=1）→ ({格位 key: u}, u_max, [u_retired 项])；找不到账返回 (None, None, None)。
    一行一页一次切分；一页现行状态取该页最后一行；map 键是完整格号「册:页:列:格[a|b]」，去掉册前缀即 book-text 的 a；
    page=0 是册级记录（可带 u_max）；u_max 取全账各行 map、lineage 里的 u 与册级 u_max 的最大者；
    作废号＝lineage 里的 {u, into: U}／{u, gone: true}（{u, new: true}、{u, split_from: U} 不是作废）。
    src 给了（如 "init"）：每页只认 src 相同的行；有行却没有该 src 行的页号追加进 missing（列表）。"""
    if not ledger_dir:
        return None, None, None
    cands = [os.path.join(ledger_dir, f"{n}.jsonl") for n in (f"vol{vol:02d}", f"vol{vol}", f"{vol:03d}", str(vol))]
    path = next((p for p in cands if os.path.isfile(p)), None)
    if path is None:
        return None, None, None
    pages, umax, retired, seen = {}, 0, {}, set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("kind", "uid_ledger") != "uid_ledger":
                continue
            pg = row.get("page")
            if isinstance(row.get("u_max"), int):
                umax = max(umax, row["u_max"])
            for v in (row.get("map") or {}).values():
                if isinstance(v, int):
                    umax = max(umax, v)
            for lg in row.get("lineage") or []:
                if not isinstance(lg, dict) or not isinstance(lg.get("u"), int):
                    continue
                umax = max(umax, lg["u"])
                if isinstance(lg.get("into"), int):
                    retired[lg["u"]] = {"u": lg["u"], "into": lg["into"]}
                elif lg.get("gone") is True:
                    retired[lg["u"]] = {"u": lg["u"], "gone": True}
            if pg:
                seen.add(pg)
                if src is None or row.get("src") == src:
                    pages[pg] = row      # 同页后来的行覆盖前面的：现行＝最后一行
    amap = {}
    for row in pages.values():
        for k, v in (row.get("map") or {}).items():
            parts = str(k).split(":")
            amap[":".join(parts[-3:])] = v   # 册:页:列:格 → 页:列:格
    if missing is not None:
        missing += sorted(seen - set(pages))
    live = set(amap.values())
    return amap, umax, [r for u, r in sorted(retired.items()) if u not in live]


def migrate_chapter(od, stem, ledger_dir=None, ledger_src=None):
    """内存里迁一册，返回 (报告 dict, {路径: 新对象})；不写盘。"""
    rep = {"dir": od, "chapter": stem}
    char_path = OV.companion_path(od, stem, "text")
    char = OV.load_json(char_path)
    missing = []
    amap, umax, retired = (load_ledger(ledger_dir, int(stem), src=ledger_src, missing=missing)
                           if str(stem).isdigit() else (None, None, None))
    if ledger_dir and amap is None:
        rep.update(status="没有账", problems=[f"身份账目录里没有这册的账（{ledger_dir}）"])
        return rep, {}
    if CU.has_u(char):
        return _check_numbered(rep, char_path, char, amap, umax, missing)
    before = copy.deepcopy(char)
    st = CU.number_char(char, amap=amap, umax=umax, retired=retired)
    rep.update(status="可迁", cells=st["cells"], u_max=st["u_max"], from_ledger=st["from_map"] if amap else "",
               ledger_new=st["new"] if amap else "")
    writes = {char_path: char}
    problems = [f"char: {m}" for m, _s in CU.u_problems(char)]
    if missing:
        problems.append(f"账里 {len(missing)} 页没有 src={ledger_src} 行：{missing[:10]}")
    if ledger_src and amap and st["new"]:
        problems.append(f"{st['new']} 格账里没有（按 src={ledger_src} 读），不该另发号")
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


def _check_numbered(rep, char_path, char, amap, umax, missing):
    """已上 u 的册：没给账就跳过；给了账就逐格核 u，一致且账的 u_max 更大时把 u_max 调上去。"""
    if amap is None:
        rep["status"] = "已上 u，跳过"
        return rep, {}
    cells = CU.cells(char)
    bad = [(c["a"], c.get("u"), amap.get(c["a"])) for c in cells if amap.get(c["a"]) != c.get("u")]
    rep.update(cells=len(cells), u_max=char.get("u_max"), from_ledger=len(cells) - len(bad), ledger_new="")
    problems = [f"账里 {len(missing)} 页缺行：{missing[:10]}"] if missing else []
    if bad:
        problems.append(f"已上 u，但 {len(bad)} 格与账不符（如 {bad[0][0]}: 文本 u={bad[0][1]}，账 {bad[0][2]}）")
    rep["problems"] = problems
    if problems or not umax or umax <= (char.get("u_max") or 0):
        rep["status"] = "已上 u，与账一致" if not problems else "已上 u，与账不符"
        return rep, {}
    CU.set_top(char, umax, char.get("u_retired") or [])
    rep.update(status="已上 u，补 u_max", u_max=umax)
    rep["problems"] = [f"char: {m}" for m, _s in CU.u_problems(char)]
    return rep, {char_path: char}


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
        p.add_argument("--ledger-src", help="每页只取账里 src 为此值的行（全库迁移用 init）")
    pl.add_argument("--out", help="提案写到这个 tsv")
    pa.add_argument("--approved-by", required=True, help="谁、在哪儿同意动正式数据（写进输出，提交信息照抄）")
    a = ap.parse_args(argv)
    rows, all_writes = [], {}
    for od in resolve_dirs(a.dirs):
        for stem in chapters_of(od, set(a.chapter or [])):
            rep, writes = migrate_chapter(od, stem, a.ledger, a.ledger_src)
            rows.append(rep)
            all_writes.update(writes)
    n_ok = sum(1 for r in rows if r.get("status") in ("可迁", "已上 u，补 u_max"))
    n_prob = sum(1 for r in rows if r.get("problems"))
    cells = sum(r.get("cells") or 0 for r in rows)
    print(f"共 {len(rows)} 册：可迁 {n_ok}、已上 u {len(rows) - n_ok}；字格 {cells}；"
          f"标点补 u {sum(r.get('punct_u') or 0 for r in rows)}、专名 {sum(r.get('entity_u') or 0 for r in rows)}、"
          f"异体 {sum(r.get('norm_u') or 0 for r in rows)}；有问题 {n_prob} 册"
          + (f"；已上 u 补 u_max {sum(1 for r in rows if r.get('status') == '已上 u，补 u_max')} 册" if a.ledger else ""))
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
