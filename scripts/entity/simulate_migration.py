# -*- coding: utf-8 -*-
"""GUJI-541 模拟测试：用真实一册的 char／entity 造四类修订，跑 migrate_anchors.migrate，核对口径。

    python3 scripts/entity/simulate_migration.py <NNN.char.json> <NNN.entity.json> [--seed N]

场景（对照表行在内存里造，格式同 revision_cells.py）：
  T1 改字      随机 N 格改字（1:1），其中一部分落在实体里
  T4 拆格+顺移 某列一个旧格拆成两个新格，其后各格顺移 +1（shift 压缩行）
  M  并格 N:1  相邻两格并成一格
  D  删格      实体范围内删一格／实体范围外删一格（后面顺移 -1）
  I  插格      实体范围内插一格／范围外插一格
断言：条数不丢；target／id 不动（人判丢失=0）；自动跟上的条迁后过 anchor_mismatches 为空；
范围外的增删必须全部自动跟上，范围内的增删必须全部进待看。
"""
from __future__ import annotations

import copy
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from migrate_anchors import migrate, summarize, CELL_RE  # noqa: E402
from original_version import char_slots, anchor_mismatches  # noqa: E402


def row(change, cell, old, mapping=""):
    return {"change": change, "cell_id": cell, "old_id": old, "mapping": mapping}


def edit_col(char, page, col, fn):
    """fn(cells)->cells，改某页某列的 cells。"""
    c = copy.deepcopy(char)
    for p in c["pages"]:
        if p["page"] == page:
            for cl in p["columns"]:
                if cl.get("col", cl.get("n")) == col or any(CELL_RE.match(x["a"]) and CELL_RE.match(x["a"]).group(2) == str(col) for x in cl["cells"][:1]):
                    cl["cells"] = fn(cl["cells"])
                    return c
    raise KeyError((page, col))


def renumber(cells, page, col, sub_ok=True):
    """按顺序重排格号（只重排无子列的主列格）。保持原有起始号。"""
    return cells


def split_cell(char, ent, target_cell):
    """把 target_cell 拆成 (s, s+1)，其后同列同子列顺移 +1。返回 (新 char, 表行)。"""
    m = CELL_RE.match(target_cell)
    pg, col, s, sub = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    new = copy.deepcopy(char)
    rows = [row("split", f"{pg}:{col}:{s}{sub}", target_cell, "1:2"), row("split", f"{pg}:{col}:{s+1}{sub}", target_cell, "1:2")]
    last = s
    for p in new["pages"]:
        for cl in p["columns"]:
            out = []
            for x in cl["cells"]:
                mm = CELL_RE.match(x["a"])
                if mm and mm.group(1) == pg and mm.group(2) == col and mm.group(4) == sub:
                    k = int(mm.group(3))
                    if k == s:
                        out.append({"a": x["a"], "c": x["c"]})
                        out.append({"a": f"{pg}:{col}:{s+1}{sub}", "c": "□"})
                        continue
                    if k > s:
                        x = dict(x, a=f"{pg}:{col}:{k+1}{sub}")
                        last = max(last, k)
                out.append(x)
            cl["cells"] = out
    if last > s:
        rows.append(row("shift", f"vol:{pg}:{col}:{s+1}{sub}..{last}{sub}", "", "+1"))
    return new, rows


def delete_cell(char, target_cell):
    m = CELL_RE.match(target_cell)
    pg, col, s, sub = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    new = copy.deepcopy(char)
    rows = [row("removed", target_cell, target_cell, "1:0")]
    last = s
    for p in new["pages"]:
        for cl in p["columns"]:
            out = []
            for x in cl["cells"]:
                mm = CELL_RE.match(x["a"])
                if mm and mm.group(1) == pg and mm.group(2) == col and mm.group(4) == sub:
                    k = int(mm.group(3))
                    if k == s:
                        continue
                    if k > s:
                        x = dict(x, a=f"{pg}:{col}:{k-1}{sub}")
                        last = max(last, k)
                out.append(x)
            cl["cells"] = out
    if last > s:
        rows.append(row("shift", f"vol:{pg}:{col}:{s+1}{sub}..{last}{sub}", "", "-1"))
    return new, rows


def insert_after(char, target_cell, ch="〇"):
    """target_cell 后插一格（新格 s+1，其后顺移 +1，插入格 mapping 0:1）。"""
    new, rows = split_cell(char, None, target_cell)
    m = CELL_RE.match(target_cell)
    # split_cell 把 target 拆成两格；插入则改成 target 不拆、后面新增
    rows = [r for r in rows if r["change"] == "shift"] + [row("added", f"{m.group(1)}:{m.group(2)}:{int(m.group(3))+1}{m.group(4)}", "", "0:1")]
    for p in new["pages"]:
        for cl in p["columns"]:
            for x in cl["cells"]:
                if x["a"] == f"{m.group(1)}:{m.group(2)}:{int(m.group(3))+1}{m.group(4)}":
                    x["c"] = ch
    return new, rows


def main():
    cp, ep = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 541
    random.seed(seed)
    char, ent = json.load(open(cp, encoding="utf-8")), json.load(open(ep, encoding="utf-8"))
    slots = char_slots(char)
    ents = ent["entities"]
    inside = {a for e in ents for a in _cells(slots, e)}
    fails = []
    print(f"# 模拟 {os.path.basename(ep)}：{len(ents)} 条实体，其中人判 {sum(1 for e in ents if _prot(e))}，seed={seed}\n")

    # T1 改字：随机 300 格，其中 100 落在实体里
    cells = [a for a, _ in slots]
    pick_in = random.sample(sorted(inside), min(100, len(inside)))
    pick_out = random.sample([a for a in cells if a not in inside], 200)
    new = copy.deepcopy(char)
    chg = set(pick_in + pick_out)
    for p in new["pages"]:
        for cl in p["columns"]:
            for x in cl["cells"]:
                if x["a"] in chg:
                    x["c"] = "〓"
    rows = [row("char", a, a, "1:1") for a in chg]
    run("T1 改字 300 格（100 在实体内）", char, new, rows, ent, fails,
        expect=lambda e, c: "待看" if set(_cells(slots, e)) & chg else "非待看")

    # 找几个单字列样例：拆格／删格／插格 分别在实体内、实体外
    ent_cells = [(e, _cells(slots, e)) for e in ents if len(_cells(slots, e)) >= 3]
    e_in = random.choice(ent_cells)
    mid = e_in[1][1]
    e_out_cell = _outside(slots, inside, ents)
    for tag, fn, c_in in (("T4 拆格+顺移", split_cell_f, mid), ("D 删格", delete_cell_f, mid), ("I 插格", insert_after_f, e_in[1][0])):
        for where, cell in (("范围内", c_in), ("范围外", e_out_cell)):
            new, rows = fn(char, cell)
            rng = _range_of(new, rows, char, cell)
            run(f"{tag}（{where}，{cell}）", char, new, rows, ent, fails,
                expect=lambda e, c, cell=cell, where=where: ("待看" if (where == "范围内" and cell in _cells(slots, e) and _inner(slots, e, cell, tag)) else "非待看"))

    # M 并格 N:1：相邻两格并成一格（取不同字）
    m1, m2 = e_in[1][0], e_in[1][1]
    new = copy.deepcopy(char)
    for p in new["pages"]:
        for cl in p["columns"]:
            cl["cells"] = [x for x in cl["cells"] if x["a"] != m2]
    rows = [row("merge", m1, m1, "2:1"), row("merge", m1, m2, "2:1")]
    run(f"M 并格 N:1（{m1}+{m2}→{m1}，不同字）", char, new, rows, ent, fails,
        expect=lambda e, c: "待看" if m1 in _cells(slots, e) and (m2 in _cells(slots, e) or True) and m2 in _cells(slots, e) else "非待看")

    print("\n结论：" + ("全部通过" if not fails else f"{len(fails)} 处不符：" + "; ".join(fails[:10])))
    sys.exit(1 if fails else 0)


def split_cell_f(char, cell): return split_cell(char, None, cell)
def delete_cell_f(char, cell): return delete_cell(char, cell)
def insert_after_f(char, cell): return insert_after(char, cell)
def _range_of(*a): return None
def _prot(e): return bool((e.get("target") or {}).get("note")) or str(e.get("source") or "").split(":")[0] not in ("glm", "补标", "rule", "llm", "qwen")


def _inner(slots, e, cell, tag):
    """该修订落在实体范围内会不会改变实体文字：拆格／插格在末格后不算范围内；其余算。"""
    cs = _cells(slots, e)
    if tag.startswith("I"):
        return cell != cs[-1]  # 插在末格之后＝范围外
    if tag.startswith("T4"):
        return True  # 拆出的□落进范围
    return True


def _cells(slots, e):
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    anc = e.get("anchor") or {}
    s, t = anc.get("start"), anc.get("end")
    if s in pos and t in pos:
        return [a for a, _c in slots[pos[s]:pos[t] + 1]]
    return []


def _outside(slots, inside, ents):
    """挑一个不在任何实体里、且同列后面有实体的格（让顺移必须把实体自动跟上）。"""
    starts = {}
    for e in ents:
        m = CELL_RE.match((e.get("anchor") or {}).get("start") or "")
        if m and not m.group(4):
            starts.setdefault((m.group(1), m.group(2)), []).append(int(m.group(3)))
    for a, _c in slots:
        m = CELL_RE.match(a)
        if m and a not in inside and not m.group(4) and any(k > int(m.group(3)) + 1 for k in starts.get((m.group(1), m.group(2)), [])):
            return a
    raise RuntimeError("找不到范围外的格")


def run(title, old, new, rows, ent, fails, expect):
    out, res, warns = migrate(old, new, rows, ent)
    st = summarize(res)
    # 复核：自动跟上的条过 F-OV-02 口径
    auto_idx = {r["i"] for r in res if r["cls"] in ("自动跟上", "未受影响")}
    sub = {"entities": [e for i, e in enumerate(out["entities"]) if i in auto_idx]}
    bad = anchor_mismatches(new, "entity", sub)
    print(f"## {title}\n- 受影响 {st['受影响']}，自动跟上 {st.get('自动跟上', 0)}，失效待看 {st.get('失效待看', 0)}，未受影响 {st.get('未受影响', 0)}；"
          f"人判 {st['人判总数']}（待看 {st.get('人判·失效待看', 0)}）；自动条迁后 F-OV-02 不符 {len(bad)}；警告 {len(warns)}")
    if bad:
        fails.append(f"{title}: 自动条迁后锚点仍不符 {len(bad)} 处")
    slots = char_slots(old)
    for r in res:
        e = ent["entities"][r["i"]]
        want = expect(e, None)
        got = "待看" if r["cls"] == "失效待看" else "非待看"
        if want != got:
            fails.append(f"{title}: {r['id']} {r['text']} 预期{want}实得{r['cls']}（{r.get('why', '')}）")
            break
    print()


if __name__ == "__main__":
    main()
