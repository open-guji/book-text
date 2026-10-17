# -*- coding: utf-8 -*-
"""定稿后增量修订：按对照表把 NNN.entity.json 的锚点迁到新 char.json（GUJI-541）。

设计：ai-team 仓 team/整理/设计/定稿后增量修订.md §4 对照表、§6 迁移规则。
用法：
    python3 scripts/entity/migrate_anchors.py --old-char 旧.char.json --new-char 新.char.json \
        --table <册>-r<n-1>_to_r<n>.tsv --entity NNN.entity.json [--write 新.entity.json] [--report 报告.md]

对照表：revision_cells.py 的 TSV（`# key: value` 头行 + 列头 change,cell_id,old_id,mapping,…），
格号带不带 `volNN:` 前缀都行；shift 压缩行（`册:页:列:起..止`、mapping=+k）按旧格序展开。
表里没列的格＝格号不变；旧格不在新文本里又没列＝按"删"算并在警告里报。

每条实体分三类：
  自动跟上  起止格都迁得过去、范围内没增删、迁后文字与 text 一致 → 改 anchor、重算 span，target 一字不动
  失效待看  起止格被删／被并、范围内有增删、拆格后落点不唯一、改字落进实体、迁后文字对不上
            → 条目原样保留（锚点不动，CI F-OV-02 会报），列入待看清单交人
  未受影响  范围内每一格格号都没变且文字没变
人判条（target.note 非空，或 source 不是机器初标 glm／补标／rule／llm／qwen）只重挂、永不改 target；
脚本结束前核对：所有条目 target 与迁前逐条相等、条数不丢（人判丢失数必须为 0）。
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from original_version import char_slots  # noqa: E402

MACHINE_SOURCES = ("glm", "补标", "rule", "llm", "qwen")
CELL_RE = re.compile(r"^(-?\d+):(-?\d+):(-?\d+)([ab]?)$")
SHIFT_RE = re.compile(r"^(-?\d+):(-?\d+):(-?\d+)([ab]?)\.\.(-?\d+)([ab]?)$")


def norm_id(s):
    """去掉 `volNN:` 之类的册前缀，只留 页:列:格[子列]。"""
    s = (s or "").strip()
    parts = s.split(":")
    while parts and not re.match(r"^-?\d+[ab]?$", parts[0]):
        parts = parts[1:]
    return ":".join(parts)


def is_protected(ent):
    tgt = ent.get("target") or {}
    if tgt.get("note"):
        return True
    src = str(ent.get("source") or "")
    return bool(src) and src.split(":")[0] not in MACHINE_SOURCES


def read_table(path):
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        lines = [ln for ln in f if not ln.startswith("#") and ln.strip()]
    for r in csv.DictReader(lines, delimiter="\t"):
        rows.append(r)
    return rows


def build_map(old_ids, new_ids, rows):
    """返回 (old2new: {旧格:[新格]}, warnings)。"""
    old2new = {}
    warns = []
    old_set, new_set = set(old_ids), set(new_ids)
    for r in rows:
        ch = (r.get("change") or "").strip()
        cid, oid = norm_id(r.get("cell_id")), norm_id(r.get("old_id"))
        if ch == "shift":
            m = SHIFT_RE.match(cid)
            if not m:
                warns.append(f"shift 行无法解析：{cid}")
                continue
            pg, col, lo, sub, hi, _s2 = m.groups()
            k = int(str(r["mapping"]).replace("+", ""))
            for o in old_ids:
                mo = CELL_RE.match(o)
                if mo and mo.group(1) == pg and mo.group(2) == col and mo.group(4) == sub \
                        and int(lo) <= int(mo.group(3)) <= int(hi):
                    old2new[o] = [f"{pg}:{col}:{int(mo.group(3)) + k}{sub}"]
        elif ch in ("moved", "geom", "state", "char", "verdict"):
            old2new[oid or cid] = [cid or oid]
        elif ch in ("split", "merge"):
            old2new.setdefault(oid, [])
            if cid not in old2new[oid]:
                old2new[oid].append(cid)
        elif ch == "removed":
            old2new[oid or cid] = []
        elif ch == "added":
            pass
        else:
            warns.append(f"未知 change 类型 {ch!r}（{cid}）")
    for o in old_ids:
        if o not in old2new:
            if o in new_set:
                old2new[o] = [o]
            else:
                old2new[o] = []
                warns.append(f"旧格 {o} 不在新文本里、表里也没列，按删算")
    for o, ns in old2new.items():
        for n in ns:
            if n not in new_set:
                warns.append(f"对照表把 {o} 指到 {n}，但新文本里没有这个格")
    return old2new, warns


def migrate(old_char, new_char, rows, entity):
    """返回 (新 entity 数据, 逐条结果 list, 警告)。"""
    old_slots, new_slots = char_slots(old_char), char_slots(new_char)
    opos = {a: i for i, (a, _c) in enumerate(old_slots)}
    npos = {a: i for i, (a, _c) in enumerate(new_slots)}
    old2new, warns = build_map(list(opos), list(npos), rows)
    out = copy.deepcopy(entity)
    results = []
    for i, e in enumerate(out.get("entities") or []):
        anc = e.get("anchor") or {}
        s, t = anc.get("start"), anc.get("end")
        res = {"i": i, "id": e.get("id"), "text": e.get("text"), "protected": is_protected(e)}
        if not s or not t or s not in opos or t not in opos:
            res.update(cls="失效待看", why="旧锚点本来就对不上旧文本")
            results.append(res)
            continue
        cells = [a for a, _c in old_slots[opos[s]:opos[t] + 1]]
        res["touched"] = any(old2new.get(a) != [a] for a in cells)
        if not res["touched"]:
            got = "".join(c for _a, c in new_slots[npos[s]:npos[t] + 1])
            if got == e.get("text"):
                res.update(cls="未受影响")
            else:
                res.update(cls="失效待看", why="格号没变但文字变了（改字落进实体）")
            results.append(res)
            continue
        if any(not old2new.get(a) for a in cells):
            res.update(cls="失效待看", why="范围内有格被删")
            results.append(res)
            continue
        want = e.get("text") or ""
        ns, ne = old2new[s], old2new[t]
        if not all(x in npos for x in ns + ne):
            res.update(cls="失效待看", why="对照表指向的新格不存在")
            results.append(res)
            continue
        # 起点：候选里字等于首字的；终点同理；候选不唯一不猜
        cs = [x for x in ns if new_slots[npos[x]][1] == want[:1]]
        ce = [x for x in ne if new_slots[npos[x]][1] == want[-1:]]
        if len(cs) != 1 or len(ce) != 1:
            res.update(cls="失效待看", why=f"拆／并后起止落点不唯一或字对不上（起候选{len(cs)}、止候选{len(ce)}）")
            results.append(res)
            continue
        a, b = cs[0], ce[0]
        if npos[b] < npos[a]:
            res.update(cls="失效待看", why="迁后起止颠倒")
            results.append(res)
            continue
        got = "".join(c for _x, c in new_slots[npos[a]:npos[b] + 1])
        if got != want:
            n_old, n_new = len(cells), npos[b] - npos[a] + 1
            why = "范围内有增删或并格" if n_old != n_new else "改字落进实体"
            res.update(cls="失效待看", why=f"迁后文字 {got!r} ≠ {want!r}（{why}）")
            results.append(res)
            continue
        e["anchor"] = {"start": a, "end": b}
        e["span"] = {"start_offset": npos[a], "end_offset": npos[b] + 1}
        res.update(cls="自动跟上", new=f"{a}–{b}")
        results.append(res)
    # 复核：条数不丢、target 不动
    assert len(out.get("entities") or []) == len(entity.get("entities") or [])
    for e0, e1 in zip(entity.get("entities") or [], out.get("entities") or []):
        if e0.get("target") != e1.get("target") or e0.get("id") != e1.get("id"):
            raise RuntimeError(f"target／id 被动了：{e0.get('id')}")
    # 迁完后 span 也要和 anchor 一致（只对已迁的条）
    return out, results, warns


def summarize(results):
    c = defaultdict(int)
    for r in results:
        c[r["cls"]] += 1
        if r["protected"]:
            c["人判·" + r["cls"]] += 1
    c["总数"] = len(results)
    c["受影响"] = sum(1 for r in results if r.get("touched") or r["cls"] == "失效待看")
    c["人判总数"] = sum(1 for r in results if r["protected"])
    return dict(c)


def report_md(name, results, warns, stats):
    L = [f"# 锚点迁移报告 {name}", ""]
    L += [f"- 条目总数 {stats['总数']}；受影响 {stats['受影响']}；自动跟上 {stats.get('自动跟上', 0)}；"
          f"失效待看 {stats.get('失效待看', 0)}；未受影响 {stats.get('未受影响', 0)}",
          f"- 人判条 {stats['人判总数']}（自动跟上 {stats.get('人判·自动跟上', 0)}，失效待看 {stats.get('人判·失效待看', 0)}），"
          f"人判丢失 0（脚本已核对 target／id 逐条相等、条数不丢）", ""]
    if warns:
        L += ["## 警告", ""] + [f"- {w}" for w in warns[:50]] + [""]
    bad = [r for r in results if r["cls"] == "失效待看"]
    if bad:
        L += ["## 失效待看清单", "", "| id | 文字 | 人判 | 原因 |", "|---|---|---|---|"]
        L += [f"| {r['id']} | {r['text']} | {'是' if r['protected'] else ''} | {r['why']} |" for r in bad]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old-char", required=True)
    ap.add_argument("--new-char", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--entity", required=True)
    ap.add_argument("--write", help="迁后 entity.json 写到这里（待看条锚点原样保留）")
    ap.add_argument("--text-version", help="写出时把 text_version 改成它（新 char 的版本）")
    ap.add_argument("--report")
    a = ap.parse_args()
    load = lambda p: json.load(open(p, encoding="utf-8"))
    out, results, warns = migrate(load(a.old_char), load(a.new_char), read_table(a.table), load(a.entity))
    st = summarize(results)
    md = report_md(os.path.basename(a.entity), results, warns, st)
    if a.report:
        open(a.report, "w", encoding="utf-8").write(md)
    else:
        print(md)
    if a.write:
        if a.text_version:
            out["text_version"] = a.text_version
        with open(a.write, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps(st, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
