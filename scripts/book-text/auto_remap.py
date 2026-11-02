# -*- coding: utf-8 -*-
"""新文本（char.json 改字／增删格）进来后，自动把 original 的标点、实体两线对齐上去。

背景：精校或换图源重跑会改 char.json。只换字、格数不变的，标点和实体按格位挂着，不用动；
增删了格的，偏移要挪；改字落在句子里的，要把这句重新投影一遍。这些以前靠人手逐批做，
这里把它们串成一道工序：

  python3 scripts/book-text/auto_remap.py <版本目录> --base <旧 char 所在提交> --vols 062-067
         [--prov 'vol{n}-r1'] [--write] [--review review.tsv]

对每一册：
  1. 与 --base 提交里的旧 char.json 比对，没有改字就跳过（text_version 由 bump_original 的 text 线带过去）。
  2. 档 1：纯换字（格数、锚点不变）。punct_redo plan/apply 原样投影旧标点和旧专名，句子其余部分不动。
  3. 档 2：增删了格。同样走 punct_redo，偏移按新格重算。
  4. 写回前修标题符、分段符位置（F-OV-12）：新增的格落在标题行的头或尾时，
     行首格与标题同列 → 标题符前移到行首；不同列 → 上一个分段符后移到标题符前。
  5. 档 3：改字落在专名 span 内、标点边界上或标题、分段附近的，列进复核单（--review），
     由 A33／A34 过一眼；其余不用人看。
  6. 标点、实体两线 patch 升版（bump_original），CHANGES 补出处（--prov），重建 headings，
     最后跑 local_check --dev。

不加 --write 只做 plan 和分档，不改任何文件。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, ".."))


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)


def cells(path_or_obj):
    c = path_or_obj
    return [(x["a"], x["c"]) for pg in c["pages"] for col in pg["columns"] for x in col["cells"]]


def old_char(base, vdir, v):
    rel = os.path.relpath(os.path.join(vdir, f"{v}.char.json"), ROOT)
    r = run(["git", "show", f"{base}:{rel}"])
    return json.loads(r.stdout) if r.returncode == 0 else None


def classify(old, new):
    """-> (改动格数, 档)。档：0 无改动／1 纯换字／2 增删格。"""
    o, n = cells(old), cells(new)
    if o == n:
        return 0, 0
    if [a for a, _ in o] == [a for a, _ in n]:
        return sum(1 for (_, x), (_, y) in zip(o, n) if x != y), 1
    import difflib
    sm = difflib.SequenceMatcher(None, "".join(c for _, c in o), "".join(c for _, c in n), autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for t, i1, i2, j1, j2 in sm.get_opcodes() if t != "equal"), 2


def fix_heading_breaks(vdir, v):
    """新增格落在标题行头尾时，把标题符／分段符挪回行界。返回修了几处。"""
    fp = os.path.join(vdir, f"{v}.punct.json")
    P = json.load(open(fp))
    C = cells(json.load(open(os.path.join(vdir, f"{v}.char.json"))))
    a2i = {a: i for i, (a, _) in enumerate(C)}
    pm = P["punctuations"]
    brk = {m["char_offset"] for m in pm if m["kind"] == "break" and m["pos"] == "after"}
    fixed = 0
    for h in [m for m in pm if m["kind"] == "heading" and m["pos"] == "before"]:
        o = h["char_offset"]
        if o == 0 or (o - 1) in brk:
            continue
        # 上一个分段符
        prev = [b for b in brk if b < o]
        if not prev:
            continue
        b = max(prev)
        gap = list(range(b + 1, o))
        if not gap or len(gap) > 3:
            continue
        hcol = h["anchor"].rsplit(":", 1)[0]
        if all(C[i][0].rsplit(":", 1)[0] == hcol for i in gap):
            h["char_offset"] = b + 1
            h["anchor"] = C[b + 1][0]
        else:
            for m in pm:
                if m["kind"] == "break" and m["pos"] == "after" and m["char_offset"] == b:
                    m["char_offset"] = o - 1
                    m["anchor"] = C[o - 1][0]
                    m["pre_char"] = C[o - 1][1]
        fixed += 1
    if fixed:
        pm.sort(key=lambda m: (m["char_offset"] + (0.4 if m["pos"] == "after" else -0.4), 0))
        json.dump(P, open(fp, "w"), ensure_ascii=False, indent=2)
        open(fp, "a").write("\n")
    return fixed


def review_items(vdir, v, old, new):
    """改字格落在专名 span 内、点号边界、标题／分段旁的，返回 (kind, 描述)。"""
    o, n = cells(old), cells(new)
    changed = set()
    if [a for a, _ in o] == [a for a, _ in n]:
        changed = {i for i, ((_, x), (_, y)) in enumerate(zip(o, n)) if x != y}
    else:
        import difflib
        sm = difflib.SequenceMatcher(None, "".join(c for _, c in o), "".join(c for _, c in n), autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                changed.update(range(j1, max(j2, j1 + 1)))
    ent = json.load(open(os.path.join(vdir, f"{v}.entity.json")))["entities"]
    pun = json.load(open(os.path.join(vdir, f"{v}.punct.json")))["punctuations"]
    pset = {m["char_offset"]: m["kind"] for m in pun if m["kind"] in ("heading", "break")}
    out = []
    for i in sorted(changed):
        ctx = "".join(c for _, c in n[max(0, i - 6): i + 7])
        hit = [e["text"] for e in ent if e["span"]["start_offset"] <= i < e["span"]["end_offset"]]
        if hit:
            out.append(("改字入专名", f"{v} {n[min(i, len(n) - 1)][0]} {ctx} 专名:{','.join(hit)}"))
        if any(abs(i - k) <= 1 for k in pset):
            out.append(("改字近分段／标题", f"{v} {n[min(i, len(n) - 1)][0]} {ctx}"))
    return out


def vols(spec):
    a = []
    for part in spec.split(","):
        if "-" in part:
            x, y = part.split("-")
            a += [f"{k:03d}" for k in range(int(x), int(y) + 1)]
        else:
            a.append(f"{int(part):03d}")
    return a


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vdir")
    ap.add_argument("--base", required=True, help="旧 char.json 所在提交（通常是新文本分支与 dev 的 merge-base）")
    ap.add_argument("--vols", required=True, help="如 062-067 或 20,22")
    ap.add_argument("--prov", default="vol{n}-r1", help="CHANGES 出处标记模板，{n} 为册号")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--review", help="复核单 tsv 输出路径")
    ap.add_argument("--source", default="claude:A33")
    a = ap.parse_args()
    vdir = os.path.abspath(a.vdir)
    review, done = [], []
    for v in vols(a.vols):
        oc = old_char(a.base, vdir, v)
        nc = json.load(open(os.path.join(vdir, f"{v}.char.json")))
        if oc is None:
            print(v, "旧 char 不存在，跳过")
            continue
        n, tier = classify(oc, nc)
        print(v, ["无改动", "档1 纯换字", "档2 增删格"][tier], f"{n} 处")
        if tier == 0:
            continue
        review += review_items(vdir, v, oc, nc)
        if not a.write:
            continue
        pr = os.path.join(HERE, "punct_redo.py")
        r = run([sys.executable, pr, "plan", vdir, "--chapter", v, "--old-char", f"git:{a.base}"])
        if os.path.exists(os.path.join(vdir, f"redo-{v}.txt")):
            r = run([sys.executable, pr, "apply", vdir, "--chapter", v, "--source", a.source])
            print("  ", (r.stdout.strip().splitlines() or ["?"])[0])
            os.remove(os.path.join(vdir, f"redo-{v}.txt"))
            if os.path.exists(os.path.join(vdir, f"redo-{v}.json")):
                os.remove(os.path.join(vdir, f"redo-{v}.json"))
        fx = fix_heading_breaks(vdir, v)
        if fx:
            print(f"   标题符／分段符位置修正 {fx} 处")
        done.append(v)
    if a.write and done:
        for v in done:
            for line in ("punct", "entity"):
                r = run([sys.executable, os.path.join(HERE, "bump_original.py"), vdir, "--line", line, "--level", "patch",
                         "--chapter", v, "--note", "新文本改字后按 auto_remap 重映射锚点（只重标改字所在句）", "--pr", "TBD"])
                if r.returncode:
                    print("  bump 失败", v, line, r.stderr[-200:])
        ch = os.path.join(vdir, "CHANGES.md")
        s = open(ch).read()
        for v in done:
            n = int(v)
            tag = a.prov.format(n=n)
            s = re.sub(rf"(vol{n} [^|]*?)（待 A33 重映射标点／实体锚点）", rf"\1（{tag}；标点、实体锚点已重映射）", s)
        open(ch, "w").write(s)
        run([sys.executable, os.path.join(HERE, "build_texts_index.py"), "--root", ROOT])
        run(["git", "checkout", "origin/dev", "--", "index/texts"])
    if a.review:
        with open(a.review, "w") as f:
            f.write("类别\t说明\n" + "".join(f"{k}\t{d}\n" for k, d in review))
        print(f"复核单 {len(review)} 条 → {a.review}")


if __name__ == "__main__":
    main()
