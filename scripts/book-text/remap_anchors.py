# -*- coding: utf-8 -*-
"""换图源重编页号后，按格级对照表把标点、实体的锚点改到新格号（GUJI-748，open-guji-cv#632）。

  python3 remap_anchors.py <版本目录> --chapter NNN --cells old_new_cells_volNN.tsv[.gz] [--dry-run] [--report out.tsv]

对照表（cv 出，每册一张）列：旧格 新格 旧字 新字 类别 IoU 说明；格号带册前缀（vol04:3:1:1），类别取
同格／改号／删／新增。<版本目录> 里的 NNN.char.json 须已是新文本。

做法：
1. 同格、改号 → 旧格→新格。
2. 「删」与「新增」配对补救：旧页按多数格定出新页，同行同格、同字的「新增」格当作对上（IoU 低造成的漏配）。
3. 标点：改 anchor，按新 char 重算 char_offset（＝格在读序里的下标），核 pre_char。
4. 实体：改 start／end，要求新格在读序里连续、长度不变、文字与 text 一致；重算 span。
5. 对不上的（落在删除格、校验字变了、实体被拆开）不改、不删，原样留着并列进报告，交 A33 重标。
   改完用 validate_text_format.py 查 F-OV-02，应只剩报告里那些。

只改锚点和位置，不动 mark、target、source；不改版本号（之后用 bump_original.py 升，换源属整册动作，
标点、实体两线升 minor）。
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import original_version as OV  # noqa: E402

KEEP = ("同格", "改号")


def _strip(a):
    """vol04:3:1:1 → 3:1:1（book-text 锚点不带册名）。"""
    return a.split(":", 1)[1] if a and a.startswith("vol") else a


def load_cells(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return rows


def build_map(rows):
    """旧格→新格。返回 (映射, 统计)。"""
    m, dele, add = {}, {}, {}
    for r in rows:
        o, n, kind = _strip(r.get("旧格", "")), _strip(r.get("新格", "")), r.get("类别", "")
        if kind in KEEP and o and n:
            m[o] = n
        elif kind == "删" and o:
            dele[o] = r.get("旧字", "")
        elif kind == "新增" and n:
            add[n] = r.get("新字", "")
    votes = collections.Counter((o.split(":")[0], n.split(":")[0]) for o, n in m.items())
    page = {}
    for (op, np_), _c in votes.most_common():
        page.setdefault(op, np_)
    used = set(m.values())
    rec = 0
    for o, ch in dele.items():
        op, rest = o.split(":", 1)
        cand = f"{page.get(op)}:{rest}"
        if cand in add and add[cand] == ch and cand not in used:
            m[o] = cand
            used.add(cand)
            rec += 1
    return m, {"mapped": len(m), "recovered": rec, "deleted": len(dele) - rec, "added": len(add)}


def remap(vdir, chapter, rows, dry_run=False, out=None):
    out = out or sys.stdout
    m, st = build_map(rows)
    char = OV.load_json(os.path.join(vdir, f"{chapter}.char.json"))
    slots = OV.char_slots(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    report = []
    res = {"punct": [0, 0], "entity": [0, 0]}
    pf = OV.companion_path(vdir, chapter, "punct")
    if os.path.isfile(pf):
        data = OV.load_json(pf)
        for i, p in enumerate(data.get("punctuations") or []):
            a = p.get("anchor")
            if not a:
                continue
            n = m.get(a)
            why = None
            if n is None:
                why = "旧格无对应（删除格）"
            elif n not in pos:
                why = f"新格 {n} 不在新文本里"
            elif "pre_char" in p and slots[pos[n]][1] != p["pre_char"]:
                why = f"校验字变了：{p['pre_char']}→{slots[pos[n]][1]}"
            if why:
                res["punct"][1] += 1
                report.append(("punct", f"#{i}", a, n or "", repr(p.get("mark", ""))[1:-1], why))
                continue
            p["anchor"], p["char_offset"] = n, pos[n]
            res["punct"][0] += 1
        if not dry_run:
            OV.dump_json(pf, data)
    ef = OV.companion_path(vdir, chapter, "entity")
    if os.path.isfile(ef):
        data = OV.load_json(ef)
        for x in data.get("entities") or []:
            anc = x.get("anchor") or {}
            s, t = anc.get("start"), anc.get("end")
            if not s or not t:
                continue
            ns, nt = m.get(s), m.get(t)
            why = None
            if ns is None or nt is None:
                why = "首尾格无对应（删除格）"
            elif ns not in pos or nt not in pos:
                why = "新格不在新文本里"
            else:
                i, j = pos[ns], pos[nt]
                seg = "".join(c for _a, c in slots[i:j + 1])
                if j < i or j - i + 1 != len(x.get("text", "")):
                    why = f"新格不连续或长度变了（{seg[:20]}）"
                elif seg != x.get("text"):
                    why = f"文字变了：{x.get('text')}→{seg}"
            if why:
                res["entity"][1] += 1
                report.append(("entity", x.get("id", ""), f"{s}～{t}", f"{ns or ''}～{nt or ''}", x.get("text", ""), why))
                continue
            x["anchor"] = {"start": ns, "end": nt}
            if "span" in x:
                x["span"] = {"start_offset": pos[ns], "end_offset": pos[nt] + 1}
            res["entity"][0] += 1
        if not dry_run:
            OV.dump_json(ef, data)
    print(f"{chapter}：对照表 对上 {st['mapped']} 格（其中删／新增配对补回 {st['recovered']}），删 {st['deleted']}、新增 {st['added']}；"
          f"标点 改 {res['punct'][0]}、留待重标 {res['punct'][1]}；实体 改 {res['entity'][0]}、留待重标 {res['entity'][1]}", file=out)
    return res, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("vdir")
    ap.add_argument("--chapter", required=True)
    ap.add_argument("--cells", required=True, help="格级对照表 tsv（可 .gz）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", help="留待重标的条目写到这个 tsv")
    a = ap.parse_args(argv)
    _res, report = remap(a.vdir, a.chapter, load_cells(a.cells), a.dry_run)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write("层\t条目\t旧锚点\t新锚点\t内容\t原因\n")
            for r in report:
                f.write("\t".join(r) + "\n")
    else:
        for r in report[:30]:
            print("  " + "\t".join(r))
        if len(report) > 30:
            print(f"  ……共 {len(report)} 条，用 --report 导出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
