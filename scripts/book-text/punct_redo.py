# -*- coding: utf-8 -*-
"""文本改字后，只重标受影响的句子（original 的 punct／entity 两条线）。

为什么要有：标点、专名是外挂在 char 格位上的。文本线小改（补 □、改错字、增删格）以后，
大部分句子一个字没变，没必要整册重做；只有改过字的那几句要重新断句、重认专名。

两步：

  plan   python3 punct_redo.py plan  <版本目录> --chapter NNN --old-char <旧 char.json | git:REF>
         比对旧、新 char，找出改过的格，扩成所在整句（句界＝。？！和分段符；跨句的专名一并带上），
         写出工作稿 `redo-NNN.txt`（每句一段：旧标点、旧专名投到新字上，供人或模型改）和
         `redo-NNN.json`（各句在新文本里的字下标范围）。没改字就什么也不写。
  apply  python3 punct_redo.py apply <版本目录> --chapter NNN [--source claude:XXX] [--dry-run]
         读改好的工作稿，逐句核对字与新文本一致，生成这几句的点号和专名；句外的条目原样保留，
         只按新文本重算 char_offset／span 下标；改字落在格上的，校验字 pre_char／text 跟着新字走。
         写回 NNN.punct.json、NNN.entity.json。版本号不在这里改，之后照常用 bump_original.py
         升 patch（或 minor）并写 CHANGES。

工作稿记法（与 A33 逐句标注稿相同）：点号 `，。、；：？！「」『』` 直接写在字间；`《…》` 是书名，
自动出 work 专名；`[p…]` 人名、`[l…]` 地名、`[o…]` 官名、`[d…]` 朝代、`[r…]` 年号。
分段符、标题符是结构，不在工作稿里改：句界本来就落在分段处，标题锚在段首字前，原样保留。

专名挂库：新句里的专名，先找旧稿同一句里同类同字的条目，再找全册同类同字最常见的挂法，照抄
target；都找不到记 new_candidate，note 写「重标后待匹配」，留给匹配流程再跑。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from original_version import char_slots  # noqa: E402

ENDS = set("。？！")
PUN = set("，。、；：？！《》「」『』")
OPENERS = set("《「『")
TAG = {"p": "people", "l": "place", "o": "office", "d": "dynasty", "r": "reign"}
RTAG = {v: k for k, v in TAG.items()}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_old_char(spec, vdir, chapter):
    if spec.startswith("git:"):
        ref = spec[4:]
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=vdir, capture_output=True,
                              text=True, check=True).stdout.strip()
        rel = os.path.relpath(os.path.join(vdir, f"{chapter}.char.json"), root)
        out = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True, check=True).stdout
        return json.loads(out)
    return load(spec)


# ── 对齐 ─────────────────────────────────────────────────────────────────────

def align(old, new):
    """旧、新格序列（[(格位, 字)]）→ (o2n: 旧下标→新下标或 None, changed: 新文本里改过的下标集合,
    deleted_at: 删格处在新文本里的下标集合)。按格位对齐：格位相同即同一格（字可能改了）。"""
    sm = SequenceMatcher(a=[a for a, _ in old], b=[a for a, _ in new], autojunk=False)
    o2n = [None] * len(old)
    changed, deleted_at = set(), set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                o2n[i1 + k] = j1 + k
                if old[i1 + k][1] != new[j1 + k][1]:
                    changed.add(j1 + k)
        elif tag == "insert":
            changed.update(range(j1, j2))
        elif tag == "delete":
            deleted_at.add(min(j1, len(new) - 1))
        else:  # replace：格位变了，当增删处理
            changed.update(range(j1, j2))
            deleted_at.add(min(j1, len(new) - 1))
    return o2n, changed, deleted_at


def boundaries(punct, pos_new):
    """新文本里的句界：该下标之后断句（。？！或分段符）。"""
    b = set()
    for p in punct:
        if p.get("pos") == "after" and (p["kind"] == "break" or (p["kind"] == "point" and p["mark"] in ENDS)):
            j = pos_new.get(p.get("anchor"))
            if j is not None:
                b.add(j)
    return b


def spans_for(hits, bset, n, ents_new):
    """改动下标 → 受影响的句子 [(s, e)]（含两端，新下标），跨句专名并入。"""
    bl = sorted(bset)
    import bisect

    def sent(i):
        k = bisect.bisect_left(bl, i)
        s = bl[k - 1] + 1 if k > 0 else 0
        e = bl[k] if k < len(bl) else n - 1
        return s, e

    spans = sorted({sent(i) for i in hits})
    changed = True
    while changed:
        changed = False
        merged = []
        for s, e in spans:
            for es, ee in ents_new:
                if es <= e and ee >= s and (es < s or ee > e):
                    s, e = min(s, sent(es)[0]), max(e, sent(ee)[1])
                    changed = True
            if merged and s <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
            else:
                merged.append((s, e))
        spans = merged
    return spans


# ── 工作稿 ───────────────────────────────────────────────────────────────────

def render_span(chars, s, e, before, after, ents):
    """新字 s..e ＋ 投过来的旧点号、旧专名 → 工作稿一段。"""
    opens = collections.defaultdict(list)
    closes = collections.defaultdict(list)
    for t, es, ee in ents:
        if t == "work":
            continue  # 书名由《》表示
        if s <= es and ee <= e and t in RTAG:
            opens[es].append((ee, RTAG[t]))
            closes[ee].append(RTAG[t])
    out = []
    for i in range(s, e + 1):
        out.append("".join(before.get(i, [])))
        for _ee, t in sorted(opens.get(i, []), reverse=True):
            out.append("[" + t)
        out.append(chars[i])
        out.append("]" * len(closes.get(i, [])))
        out.append("".join(after.get(i, [])))
    return "".join(out)


def tokenize(s):
    """工作稿一段 → (字, before{i: 串}, after{i: 串}, 专名[(类型, 起, 止)])，下标是段内字序。"""
    chars, ents = [], []
    before, after = collections.defaultdict(str), collections.defaultdict(str)
    pending, estack, wstack = "", [], []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "[":
            t = s[i + 1]
            if t not in TAG:
                raise ValueError(f"未知专名标记 [{t}：{s[i:i + 12]}")
            estack.append((TAG[t], len(chars)))
            i += 2
            continue
        if ch == "]":
            t, st = estack.pop()
            ents.append((t, st, len(chars) - 1))
            i += 1
            continue
        if ch in PUN:
            if ch in OPENERS:
                pending += ch
                if ch == "《":
                    wstack.append(len(chars))
            else:
                if pending:
                    raise ValueError(f"开引号后直接接点号：{s[max(0, i - 10):i + 5]}")
                if ch == "》":
                    ents.append(("work", wstack.pop(), len(chars) - 1))
                after[len(chars) - 1] += ch
            i += 1
            continue
        if pending:
            before[len(chars)] += pending
            pending = ""
        chars.append(ch)
        i += 1
    if estack or wstack or pending:
        raise ValueError(f"括号不配对：{s[:30]}")
    return chars, before, after, ents


def read_work(path):
    out, cur = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = re.match(r"^=== (\d+)-(\d+)", line)
            if m:
                cur = (int(m.group(1)), int(m.group(2)))
                out[cur] = ""
                continue
            if cur is not None and line.strip() and not line.startswith("#"):
                out[cur] += line.strip()
    return out


# ── 主流程 ───────────────────────────────────────────────────────────────────

def project(old, new, punct, ents):
    """旧条目投到新文本：返回 (o2n, changed, 句界, 新下标的点号表, 新下标的专名表)。"""
    o2n, changed, deleted_at = align(old, new)
    pos_old = {a: i for i, (a, _c) in enumerate(old)}
    pos_new = {a: i for i, (a, _c) in enumerate(new)}
    before, after = collections.defaultdict(list), collections.defaultdict(list)
    for p in punct:
        if p["kind"] != "point":
            continue
        j = pos_new.get(p.get("anchor"))
        if j is None:
            continue
        (before if p["pos"] == "before" else after)[j].append(p["mark"])
    ents_new = []
    for x in ents:
        a = x.get("anchor") or {}
        i1, i2 = pos_old.get(a.get("start")), pos_old.get(a.get("end"))
        if i1 is None or i2 is None:
            continue
        j1 = next((o2n[i] for i in range(i1, i2 + 1) if o2n[i] is not None), None)
        j2 = next((o2n[i] for i in range(i2, i1 - 1, -1) if o2n[i] is not None), None)
        if j1 is not None and j2 is not None and j1 <= j2:
            ents_new.append((x["type"], j1, j2))
        elif j1 is None:  # 专名的字全删了：它所在处算改动
            deleted_at.add(min(o2n[i1 - 1] + 1 if i1 and o2n[i1 - 1] is not None else 0, len(new) - 1))
    return o2n, changed | deleted_at, boundaries(punct, pos_new), before, after, ents_new


def cmd_plan(a):
    vdir, ch = a.vdir, a.chapter
    new = char_slots(load(os.path.join(vdir, f"{ch}.char.json")))
    old = char_slots(load_old_char(a.old_char, vdir, ch))
    punct = load(os.path.join(vdir, f"{ch}.punct.json"))["punctuations"]
    ents = load(os.path.join(vdir, f"{ch}.entity.json"))["entities"]
    _o2n, hits, bset, before, after, ents_new = project(old, new, punct, ents)
    if not hits:
        print("没有改字，不用重标")
        return 0
    spans = spans_for(hits, bset, len(new), [(s, e) for _t, s, e in ents_new])
    chars = [c for _a, c in new]
    work = os.path.join(a.out or vdir, f"redo-{ch}.txt")
    with open(work, "w", encoding="utf-8") as f:
        f.write(f"# {ch} 重标工作稿：{len(spans)} 句。只改点号与专名标记，字不要动；改好后跑 apply。\n")
        for s, e in spans:
            f.write(f"=== {s}-{e}  {new[s][0]}  改动 {len([i for i in hits if s <= i <= e])} 处\n")
            f.write(render_span(chars, s, e, before, after, ents_new) + "\n")
    meta = {"chapter": ch, "old_char": a.old_char, "spans": spans, "changed": sorted(hits)}
    with open(os.path.join(a.out or vdir, f"redo-{ch}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    print(f"改动 {len(hits)} 处 → 重标 {len(spans)} 句，共 {sum(e - s + 1 for s, e in spans)} 字；工作稿 {work}")
    return 0


def _order(p, off):
    inner = (p["mark"] == "《") if p["pos"] == "before" else (p["mark"] != "》")
    return (off, p.get("kind") != "heading", p["pos"] != "before", p["kind"] == "break", inner)


def cmd_apply(a):
    vdir, ch = a.vdir, a.chapter
    base = a.out or vdir
    meta = load(os.path.join(base, f"redo-{ch}.json"))
    work = read_work(os.path.join(base, f"redo-{ch}.txt"))
    new = char_slots(load(os.path.join(vdir, f"{ch}.char.json")))
    old = char_slots(load_old_char(meta["old_char"], vdir, ch))
    pj_path, ej_path = os.path.join(vdir, f"{ch}.punct.json"), os.path.join(vdir, f"{ch}.entity.json")
    pj, ej = load(pj_path), load(ej_path)
    o2n, _hits, _b, _bf, _af, _en = project(old, new, pj["punctuations"], ej["entities"])
    pos_old = {x: i for i, (x, _c) in enumerate(old)}
    pos_new = {x: i for i, (x, _c) in enumerate(new)}
    spans = [tuple(s) for s in meta["spans"]]
    if set(work) != set(spans):
        raise SystemExit(f"工作稿的句子与 plan 不一致：缺 {sorted(set(spans) - set(work))}，多 {sorted(set(work) - set(spans))}")
    inside = lambda j: any(s <= j <= e for s, e in spans)  # noqa: E731
    chars = [c for _a, c in new]

    # 句外条目：保留，重算下标与校验字
    P, dropped_p = [], 0
    for p in pj["punctuations"]:
        j = pos_new.get(p.get("anchor"))
        if j is None:
            if p["kind"] == "point":
                dropped_p += 1
                continue
            # 结构符的格删了：分段符挪到前一格，标题挪到后一格
            i = pos_old[p["anchor"]]
            rng = range(i, -1, -1) if p["pos"] == "after" else range(i, len(old))
            j = next((o2n[k] for k in rng if o2n[k] is not None), None)
            if j is None:
                raise SystemExit(f"结构符 {p} 找不到可挪的格")
            p = dict(p, anchor=new[j][0])
        if p["kind"] == "point" and inside(j):
            dropped_p += 1
            continue
        p = dict(p, char_offset=j)
        if "pre_char" in p:
            p["pre_char"] = chars[j]
        P.append(p)

    E, old_in = [], collections.defaultdict(list)
    vol_targets = collections.defaultdict(collections.Counter)
    tjson = {}
    for x in ej["entities"]:
        if x["target"].get("status") in ("matched", "matched_multi"):
            k = json.dumps(x["target"], ensure_ascii=False, sort_keys=True)
            vol_targets[(x["type"], x["text"])][k] += 1
            tjson[k] = x["target"]
        an = x.get("anchor") or {}
        i1, i2 = pos_old.get(an.get("start")), pos_old.get(an.get("end"))
        j1 = o2n[i1] if i1 is not None else None
        j2 = o2n[i2] if i2 is not None else None
        hit = next(((s, e) for s, e in spans if j1 is not None and s <= j1 <= e or j2 is not None and s <= j2 <= e), None)
        if hit or j1 is None or j2 is None:
            if hit:
                old_in[hit].append(x)
            continue
        E.append(dict(x, text="".join(chars[j1:j2 + 1]), span={"start_offset": j1, "end_offset": j2 + 1}))

    # 句内：按工作稿重出
    src = a.source
    nid = max([int(x["id"][1:]) for x in ej["entities"] if re.match(r"^e\d+$", x.get("id", ""))] or [0])
    new_p = new_e = 0
    for (s, e) in spans:
        cs, bef, aft, ents = tokenize(work[(s, e)])
        want = "".join(chars[s:e + 1])
        if "".join(cs) != want:
            k = next((i for i in range(min(len(cs), len(want))) if cs[i] != want[i]), min(len(cs), len(want)))
            raise SystemExit(f"句 {s}-{e} 第 {k} 字与文本不符：稿「{''.join(cs[max(0, k - 6):k + 6])}」文本「{want[max(0, k - 6):k + 6]}」")
        for i in range(len(cs)):
            j = s + i
            for m in bef.get(i, ""):
                P.append({"mark": m, "kind": "point", "pos": "before", "char_offset": j, "pre_char": chars[j],
                          "anchor": new[j][0], "source": src})
                new_p += 1
            for m in aft.get(i, ""):
                P.append({"mark": m, "kind": "point", "pos": "after", "char_offset": j, "pre_char": chars[j],
                          "anchor": new[j][0], "source": src})
                new_p += 1
        local = collections.defaultdict(list)
        for x in old_in[(s, e)]:
            local[(x["type"], x["text"])].append(x)
        for t, i1, i2 in sorted(ents, key=lambda z: (z[1], -z[2])):
            j1, j2 = s + i1, s + i2
            text = "".join(chars[j1:j2 + 1])
            prev = local.get((t, text))
            if prev:
                x0 = prev.pop(0)
                tgt, eid, xsrc = x0["target"], x0["id"], x0.get("source", src)
            else:
                nid += 1
                eid, xsrc = f"e{nid:05d}", src
                c = vol_targets.get((t, text))
                if c:
                    tgt = dict(tjson[c.most_common(1)[0][0]])
                    tgt["note"] = "重标沿用全册同字挂法，待核" + (f"（原注：{tgt['note']}）" if tgt.get("note") else "")
                else:
                    tgt = {"status": "new_candidate", "canonical_name": text, "note": "重标后待匹配"}
                new_e += 1
            E.append({"id": eid, "type": t, "text": text, "anchor": {"start": new[j1][0], "end": new[j2][0]},
                      "span": {"start_offset": j1, "end_offset": j2 + 1}, "target": tgt, "source": xsrc})

    P.sort(key=lambda p: _order(p, p["char_offset"]))
    E.sort(key=lambda x: (x["span"]["start_offset"], -x["span"]["end_offset"]))
    pj["punctuations"], ej["entities"] = P, E
    pts = [p for p in P if p["kind"] == "point"]
    if "stats" in pj:
        pj["stats"].update({"total_annotations": len(P), "points": len(pts),
                            "paragraph_breaks": sum(p["kind"] == "break" for p in P),
                            "periods": sum(p["mark"] == "。" for p in pts), "commas": sum(p["mark"] == "，" for p in pts),
                            "headings": sum(p["kind"] == "heading" for p in P)})
    if "stats" in ej:
        st = collections.Counter(x["target"].get("status") for x in E)
        tc = collections.Counter(x["type"] for x in E)
        ej["stats"].update({"total_entities": len(E), "matched": st["matched"] + st["matched_multi"], "ambiguous": st["ambiguous"],
                            "new_candidates": st["new_candidate"], "works": tc["work"], "people": tc["people"],
                            "places": tc["place"], "offices": tc["office"], "dynasties": tc["dynasty"],
                            "reigns": tc["reign"]})
    print(f"重标 {len(spans)} 句：点号去 {dropped_p} 出 {new_p}；专名新增 {new_e}，"
          f"共 {len(P)} 条标点、{len(E)} 个专名")
    if a.dry_run:
        return 0
    for path, obj in ((pj_path, pj), (ej_path, ej)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print("已写回；接着用 bump_original.py 升 punct／entity 版本并重建索引")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply"):
        s = sub.add_parser(name)
        s.add_argument("vdir", help="original 版本目录（含 NNN.char.json）")
        s.add_argument("--chapter", required=True, help="册号，如 004")
        s.add_argument("--out", help="工作稿目录，缺省同版本目录")
        if name == "plan":
            s.add_argument("--old-char", required=True, help="旧 char.json 路径，或 git:<提交>")
        else:
            s.add_argument("--source", default="claude:redo", help="新条目的 source")
            s.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return cmd_plan(a) if a.cmd == "plan" else cmd_apply(a)


if __name__ == "__main__":
    sys.exit(main())
