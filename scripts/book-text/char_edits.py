# -*- coding: utf-8 -*-
"""改字清单 NNN.char-edits.json：文本 0.x 精校期，改字方登记「改了哪些字」，标点、实体两层据此同步。

设计见 docs/design/2026-10-改字清单.md。清单只收单格替换（格数不变、锚点不动）；增删字、整句改动
不进清单，照旧推分支请 A33 重标。文本线 1.x 起不许有清单（改字走修订流程，伴生层就地跟进）。

  record  python3 char_edits.py record <版本目录> --chapter NNN --old-char <旧 char.json | git:REF>
              [--base-commit SHA] [--ref 出处] [--by 谁]
          比对旧、新 char，把改了字的格并进清单（同格再改：old 留最早、new 取最新；改回原字就删掉）。
          git:REF 时 base_commit 取 REF 的提交号；给文件路径时须另给 --base-commit。
          首次建清单时 base_text_version 取旧 char 的 version。改字方在提交改字的同一个提交里带上清单。
  sync    python3 char_edits.py sync <版本目录> --chapter NNN [--dry-run]
          按清单机械同步：punct 的 pre_char、entity 的 text 里，落在登记格上、仍是 old 的字改成 new。
          只改校验字，不重新断句、不动 target、不动 source（人裁／手改的条目也只同步校验字）。
          同步完列出：字变了的专名（要核挂法是否还对）、改字所在的句子（要不要重标由人定，
          要重标的用 punct_redo.py plan/apply）、这些句子里人裁／手改来源的标点与专名（单列，
          末尾汇总「涉及人裁 N 句」，要重标的先交 A34）。清单里同步完的格删掉，清空就删文件。
          末尾提示哪条线要升 patch；升版用 bump_original.py，必须在 sync 之后。
  uid     python3 char_edits.py uid <版本目录> --chapter NNN --old-char <旧 char.json | git:REF>
              [--merge 57:56 …] [--review 待看.tsv] [--dry-run]
          字格永久编号 u（guji-format 02 §4.10，char v0.6）：人在 char 里补字、删字、并格以后跑一次：
            补字：没有 u 的新格按读序取 u_max+1；
            删字：旧版有、新版没有的 u 记进 u_retired（gone: true）；--merge 旧u:留下的u 记成并格（into）；
            重挂：标点、专名、异体按 u 改格位 key（格号整列移位也跟着字走）；挂在删掉的 u 上的挪邻格
                  （标点 after／异体挪前一格，标题 before 挪后一格；专名起格往后、止格往前），并在待看清单里列出。
          校验字（pre_char、专名 text、异体 c）只报不改：挪了格的条目校验字多半对不上，F-OV-02 会报，
          由人核过再改（或 punct_redo 重标）。之后照常 bump_original.py 升版。

上了 u 的册（char 有 u_max），record 按 u 比对新旧（补删字不再拦，只登记原地改字，条目带 u）；
sync 只在条目的 u 与清单的 u 相同时才同步——格号移位造成的「同格异字」不会被洗白。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import original_version as OV  # noqa: E402
import cell_uid as CU  # noqa: E402
from punct_redo import load_old_char  # noqa: E402

ENDS = set("。？！")
MANUAL_KEYS = ("human", "manual", "人裁", "手改")


def is_manual(source):
    """人裁／手改来源：source 里含 human、manual（如 claude:manual、claude:T-manual）、人裁、手改。"""
    s = str(source or "").lower()
    return any(k in s for k in MANUAL_KEYS)


def _resolve(ref, vdir):
    return subprocess.run(["git", "rev-parse", "--short=10", ref], cwd=vdir, capture_output=True,
                          text=True, check=True).stdout.strip()


def _book_id(vdir):
    return os.path.basename(os.path.dirname(os.path.abspath(vdir)))


def diff_slots_u(old_char, new_char):
    """上了 u 的册：按 u 比新旧，原地改字的格 [(新格位, old, new, u)]；增删的格不在这里（用 uid 子命令）。"""
    oi, ni = CU.u_index(old_char), CU.u_index(new_char)
    out = [(ni[u][1], oi[u][2], ni[u][2], u) for u in sorted(ni, key=lambda x: ni[x][0])
           if u in oi and oi[u][2] != ni[u][2]]
    bad = [(a, o, n) for a, o, n, _u in out if len(o) != 1 or len(n) != 1]
    if bad:
        raise ValueError(f"格里不是单个字：{bad[:3]}（一格一字，清单只收单字替换）")
    return out


def diff_slots(old_char, new_char):
    """单格替换的差异 [(anchor, old, new)]；格序不一致（增删字）时抛 ValueError。
    新旧都上了 u 时按 u 比（见 diff_slots_u），返回 [(anchor, old, new, u)]。"""
    if CU.has_u(old_char) and CU.has_u(new_char):
        return diff_slots_u(old_char, new_char)
    old, new = OV.char_slots(old_char), OV.char_slots(new_char)
    if [a for a, _c in old] != [a for a, _c in new]:
        raise ValueError("新旧文本的格序不一致（有增删字）：改字清单只收单格替换，请推分支请 A33 重标")
    out = [(a, o, n) for (a, o), (_a, n) in zip(old, new) if o != n]
    bad = [(a, o, n) for a, o, n in out if len(o) != 1 or len(n) != 1]
    if bad:
        raise ValueError(f"格里不是单个字：{bad[:3]}（一格一字，清单只收单字替换）")
    return out


def merge(edits, changes, base_commit, ref=None, by=None):
    """把 changes 并进 edits（就地改），返回 (新增, 更新, 撤销) 计数。"""
    items = edits.setdefault("edits", [])
    idx = {e["anchor"]: e for e in items}
    n_add = n_upd = n_del = 0
    for a, o, n, *uu in changes:
        e = idx.get(a)
        if e is None:
            e = {"anchor": a, "old": o, "new": n, "base_commit": base_commit}
            if uu:
                e["u"] = uu[0]
            if ref:
                e["ref"] = ref
            if by:
                e["by"] = by
            items.append(e)
            idx[a] = e
            n_add += 1
        elif e["old"] == n:  # 改回原字
            items.remove(e)
            del idx[a]
            n_del += 1
        else:
            e["new"] = n
            if ref:
                e["ref"] = ref
            n_upd += 1
    return n_add, n_upd, n_del


def cmd_record(a):
    char_path = os.path.join(a.vdir, f"{a.chapter}.char.json")
    new_char = OV.load_json(char_path)
    tv = OV.parse_version(new_char.get("version"))
    if tv is None or tv[0] != 0:
        print(f"{a.chapter} 文本线 {new_char.get('version')} 不是 0.x：1.x 起改字走修订流程，不用清单", file=sys.stderr)
        return 2
    old_char = load_old_char(a.old_char, a.vdir, a.chapter)
    try:
        changes = diff_slots(old_char, new_char)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not a.ref:
        print("警告：没给 --ref（出处：意见 id／待审单 r 号／GUJI 卡号）。建议必填，"
              "便于和提交信息里的格变动出处（check_cell_provenance）对照", file=sys.stderr)
    if a.old_char.startswith("git:"):
        base = a.base_commit or _resolve(a.old_char[4:], a.vdir)
    elif a.base_commit:
        base = a.base_commit
    else:
        print("--old-char 给的是文件时须另给 --base-commit", file=sys.stderr)
        return 2
    path = OV.char_edits_path(a.vdir, a.chapter)
    edits = OV.load_char_edits(a.vdir, a.chapter) or {
        "schema": OV.CHAR_EDITS_SCHEMA, "book_id": _book_id(a.vdir), "volume": int(a.chapter),
        "base_text_version": old_char.get("version"), "edits": []}
    _rekey_by_u(edits, new_char)
    n_add, n_upd, n_del = merge(edits, changes, base, a.ref, a.by)
    order = {an: i for i, (an, _c) in enumerate(OV.char_slots(new_char))}
    edits["edits"].sort(key=lambda e: order.get(e["anchor"], -1))
    print(f"{a.chapter}：改字 {len(changes)} 格 → 清单新增 {n_add}、更新 {n_upd}、撤销 {n_del}，共 {len(edits['edits'])} 条")
    if a.dry_run:
        return 0
    if edits["edits"]:
        OV.dump_json(path, edits)
    elif os.path.exists(path):
        os.remove(path)
    return 0


def _rekey_by_u(edits, char):
    """清单里带 u 的条目，格位 key 改成 char 里该 u 现在的格（补删字后格号移位）。返回改了几条。"""
    idx = CU.u_index(char)
    n = 0
    for e in (edits or {}).get("edits") or []:
        if isinstance(e, dict) and e.get("u") in idx and e.get("anchor") != idx[e["u"]][1]:
            e["anchor"] = idx[e["u"]][1]
            n += 1
    return n


def _same_u(edit, u):
    """清单条目带 u 时，伴生层条目的 u 必须相同才同步（没上 u 的册两边都没有，放行）。"""
    return "u" not in edit or u is None or edit["u"] == u


def cmd_uid(a):
    """补字发号、删字记作废、按 u 重挂伴生层（见文件头 uid）。"""
    char_path = os.path.join(a.vdir, f"{a.chapter}.char.json")
    new_char = OV.load_json(char_path)
    old_char = load_old_char(a.old_char, a.vdir, a.chapter)
    if not CU.has_u(old_char):
        print(f"{a.chapter}：旧版还没上 u（没有 u_max），先用 u_migrate.py 迁移", file=sys.stderr)
        return 2
    merges = {}
    for m in a.merge or []:
        try:
            u, into = (int(x) for x in m.split(":"))
        except ValueError:
            print(f"--merge {m!r} 应写成 旧u:留下的u", file=sys.stderr)
            return 2
        merges[u] = into
    if "u_max" not in new_char or ("u_retired" not in new_char and old_char.get("u_retired")):
        # 改字时把顶层 u_max／u_retired 弄丢了：从旧版接上
        CU.set_top(new_char, new_char.get("u_max", old_char.get("u_max") or 0),
                   new_char.get("u_retired") or list(old_char.get("u_retired") or []))
    new = CU.assign_new(new_char)
    gone = CU.retire_missing(old_char, new_char, into=merges)
    probs = CU.u_problems(new_char) + CU.continuity_problems(old_char, new_char)
    if probs:
        for msg, _s in probs[:20]:
            print(f"  u 不合规：{msg}", file=sys.stderr)
        return 2
    print(f"{a.chapter}：新发 u {len(new)} 个"
          + (f"（{new[0][1]}–{new[-1][1]}）" if new else "")
          + f"，作废 {len(gone)} 个（并格 {sum(1 for _u, i in gone if i)}），u_max={new_char['u_max']}")
    review, writes = [], [(char_path, new_char)]
    for line in ("punct", "entity", "norm"):
        cf = os.path.join(a.vdir, f"{a.chapter}.{line}.json")
        if not os.path.isfile(cf):
            continue
        data = OV.load_json(cf)
        moved, rv = CU.relink(new_char, line, data, old_char=old_char)
        nou = sum(1 for _m, sub in CU.layer_u_problems(new_char, line, data) if sub.endswith(":nou"))
        print(f"  {line}：按 u 改格位 {moved} 条，待看 {len(rv)} 条" + (f"；另有 {nou} 条没写 u（先迁移）" if nou else ""))
        review += [(line, i, o, n, why) for i, o, n, why in rv]
        if moved or rv:
            writes.append((cf, data))
    for line, i, o, n, why in review:
        print(f"    待看 {line} #{i} {o} → {n or '（没挪）'}：{why}")
    if review:
        print("  校验字没改：挪了格的条目 F-OV-02 会报，人核过再改 pre_char／text（或 punct_redo 重标）")
    if a.review:
        with open(a.review, "w", encoding="utf-8") as f:
            f.write("层\t序号\t旧格\t新格\t说明\n")
            for line, i, o, n, why in review:
                f.write(f"{line}\t{i}\t{o}\t{n or ''}\t{why}\n")
    edits = OV.load_char_edits(a.vdir, a.chapter)
    if edits and _rekey_by_u(edits, new_char):
        writes.append((OV.char_edits_path(a.vdir, a.chapter), edits))
    if a.dry_run:
        return 0
    for path, obj in writes:
        OV.dump_like(path, obj)
    return 0


def _sentence(slots, i, bset):
    """slots 下标 i 所在句的 [s, e)：句界取 bset（句末点号所在格下标）。"""
    s = i
    while s > 0 and (s - 1) not in bset:
        s -= 1
    e = i
    while e < len(slots) - 1 and e not in bset:
        e += 1
    return s, e + 1


def sync(vdir, chapter, dry_run=False, out=None):
    out = out or sys.stdout
    char = OV.load_json(os.path.join(vdir, f"{chapter}.char.json"))
    edits = OV.load_char_edits(vdir, chapter)
    if not edits:
        print(f"{chapter} 没有改字清单", file=out)
        return {"punct": 0, "entity": 0, "cleared": 0}
    em = OV.edits_by_anchor(edits)
    slots = OV.char_slots(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    a2u = CU.a_to_u(char)
    changed = {"punct": 0, "entity": 0}
    touched_ents, ends = [], set()
    files = {}
    for line in ("punct", "entity"):
        cf = OV.companion_path(vdir, chapter, line)
        if os.path.isfile(cf):
            files[line] = (cf, OV.load_json(cf))
    if "punct" in files:
        for p in files["punct"][1].get("punctuations") or []:
            a = p.get("anchor")
            e = em.get(a)
            if (e and len(e["new"]) == 1 and p.get("pre_char") == e["old"] and a in pos
                    and slots[pos[a]][1] == e["new"] and _same_u(e, p.get("u"))):
                p["pre_char"] = e["new"]
                changed["punct"] += 1
            if p.get("mark") in ENDS and a in pos:
                ends.add(pos[a])
    if "entity" in files:
        for x in files["entity"][1].get("entities") or []:
            anc = x.get("anchor") or {}
            s, t = anc.get("start"), anc.get("end")
            if s not in pos or t not in pos or "text" not in x:
                continue
            seg = slots[pos[s]:pos[t] + 1]
            if len(seg) != len(x["text"]):
                continue
            txt = list(x["text"])
            hit = False
            useg = [a2u.get(a) for a, _c in seg]
            if "u_start" in x and (useg[0] != x.get("u_start") or useg[-1] != x.get("u_end")):
                continue  # 格位与 u 不一致（移位）：不同步，F-OV-18 会报
            for k, (a, now) in enumerate(seg):
                e = em.get(a)
                if e and len(now) == 1 and txt[k] == e["old"] and now == e["new"] and _same_u(e, useg[k]):
                    txt[k] = now
                    hit = True
            if hit:
                touched_ents.append((x.get("id"), x["text"], "".join(txt), (x.get("target") or {}).get("status"),
                                     (x.get("target") or {}).get("canonical_name"), OV.effective_source(x, files["entity"][1])))
                x["text"] = "".join(txt)
                changed["entity"] += 1
    # 清单里各层都已对上的格清掉
    soft_left = set()
    for line, (_cf, data) in files.items():
        sl = []
        OV.anchor_mismatches(char, line, data, edits, soft=sl)
        if line == "punct":
            pts = data.get("punctuations") or []
            soft_left |= {pts[i].get("anchor") for i, _n in sl}
        else:
            ents = data.get("entities") or []
            for i, _n in sl:
                anc = ents[i].get("anchor") or {}
                soft_left |= {a for a, _c in slots[pos[anc["start"]]:pos[anc["end"]] + 1]}
    keep = [e for e in edits["edits"] if e["anchor"] in soft_left or e["anchor"] not in pos
            or slots[pos[e["anchor"]]][1] != e["new"]]
    cleared = len(edits["edits"]) - len(keep)
    text = "".join(c for _a, c in slots)
    print(f"{chapter}：标点校验字同步 {changed['punct']} 处，专名文字同步 {changed['entity']} 处，"
          f"清单清掉 {cleared} 条、余 {len(keep)} 条", file=out)
    for eid, was, now, st, cn, src in touched_ents:
        print(f"  专名 {eid} {was}→{now}（{st} {cn or ''}，source={src}）：核挂法是否还对", file=out)
    seen = set()
    manual_sents = 0
    pdoc = files["punct"][1] if "punct" in files else {}
    edoc = files["entity"][1] if "entity" in files else {}
    pts, ents = pdoc.get("punctuations") or [], edoc.get("entities") or []
    for e in edits["edits"]:
        if e["anchor"] not in pos:
            continue
        s, t = _sentence(slots, pos[e["anchor"]], ends)
        if (s, t) in seen:
            continue
        seen.add((s, t))
        print(f"  句 {slots[s][0]}：{text[s:t]}", file=out)
        man = []
        for k, p in enumerate(pts):
            i = pos.get(p.get("anchor"))
            if i is not None and s <= i < t and is_manual(OV.effective_source(p, pdoc)):
                man.append(f"标点 #{k} {p.get('anchor')} {p.get('mark') or p.get('kind')}（source={OV.effective_source(p, pdoc)}）")
        for x in ents:
            anc = x.get("anchor") or {}
            i, j = pos.get(anc.get("start")), pos.get(anc.get("end"))
            if i is not None and j is not None and i < t and j >= s and is_manual(OV.effective_source(x, edoc)):
                man.append(f"专名 {x.get('id')} {anc.get('start')}～{anc.get('end')} {x.get('type')} {x.get('text')}"
                           f"（source={OV.effective_source(x, edoc)}）")
        if man:
            manual_sents += 1
            print("    人裁条目（要重标须先交 A34）：", file=out)
            for m in man:
                print(f"      {m}", file=out)
    print(f"涉及人裁 {manual_sents} 句", file=out)
    tv = OV.parse_version(char.get("version"))
    todo = [line for line, (_cf, data) in files.items()
            if changed[line] or OV.parse_version(data.get("text_version")) != tv]
    if todo:
        print("请对 " + "、".join(f"{line} 线" for line in todo) + " 升 patch（bump_original.py --line <线> --level patch，"
              "须在本次 sync 之后）", file=out)
    if not dry_run:
        for line, (cf, data) in files.items():
            if changed[line]:
                OV.dump_json(cf, data)
        path = OV.char_edits_path(vdir, chapter)
        if keep:
            edits["edits"] = keep
            OV.dump_json(path, edits)
        else:
            os.remove(path)
    return {"punct": changed["punct"], "entity": changed["entity"], "cleared": cleared,
            "manual_sentences": manual_sents, "bump": todo}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    s = sub.add_parser("sync")
    u = sub.add_parser("uid")
    for p in (r, s, u):
        p.add_argument("vdir", help="original 版本目录（含 NNN.char.json）")
        p.add_argument("--chapter", required=True, help="册号，如 007")
        p.add_argument("--dry-run", action="store_true")
    r.add_argument("--old-char", required=True, help="改字前的 char.json 路径，或 git:<提交>")
    r.add_argument("--base-commit", help="改字前的提交号（--old-char 给文件时必填）")
    r.add_argument("--ref", help="出处：意见 id／事件 id／待审单 r 号／GUJI 卡号（建议必填，缺了会警告）")
    r.add_argument("--by", help="改字方，如 A32")
    u.add_argument("--old-char", required=True, help="改字前的 char.json 路径，或 git:<提交>")
    u.add_argument("--merge", action="append", metavar="U:INTO", help="并格：旧 u 并进留下的 u（可多次）")
    u.add_argument("--review", help="待看清单写到这个 tsv")
    a = ap.parse_args(argv)
    if a.cmd == "record":
        return cmd_record(a)
    if a.cmd == "uid":
        return cmd_uid(a)
    sync(a.vdir, a.chapter, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
