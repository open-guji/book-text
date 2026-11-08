#!/usr/bin/env python3
"""锚点漂移检查（2026-11-07，第31册补字后分段错位事件的补救）。

问题：char 里某列增删字（或整列左移／右移）后，格号 `页:列:格序` 重排，挂在旧格号上的
标点／专名会指到别的字上；而「校验字同步」会把 pre_char 一并改成新字，常规校验发现不了。

做法：对本次改动的每个 NNN.char.json，取基准版（--base，缺省 origin/dev）与现版，逐列用
difflib 对齐，把基准版每个标点锚点映射到现版格号；若
  - 该标点（同 mark、kind、锚点）仍原样留在旧格号上，而
  - 旧格号上的字已变（改字、补字、移位），且映射后的格号与旧格号不同，
就判为「疑似漂移」。
  rule:*（版面规则产的分段断点、标题）漂移 → 失败（退出码 1）；
  其他来源的标点、专名漂移 → 只告警（人工重标过的会被正确挪走，剩下的才会报）。

用法（仓根）：python3 scripts/check_anchor_drift.py [--base origin/dev] [--fail-all]
已知误报：旧文本列尾有重复字（如「是是」）、人工已有意把断点放在补字前一格的，核对后可忽略，
不在 local_check 里时用 --warn-only 跑。
"""
import argparse
import difflib
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def sh(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def git_json(ref, path):
    r = sh("git", "show", f"{ref}:{path}")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def columns(char):
    out = {}
    for p in char.get("pages", []):
        for c in p.get("columns", []):
            out[(p["page"], c["col"])] = [(x["a"], x["c"]) for x in c["cells"]]
    return out


def split_anchor(a):
    """'1:4:8a' -> (1, 4, '8')；取不出返回 None。"""
    try:
        pg, col, n = a.split(":")
    except ValueError:
        return None
    return int(pg), int(col), n.rstrip("abcdefghijklmnopqrstuvwxyz")


def map_cell(cells_old, cells_new, anchor):
    """基准版列里 anchor 对应的字，在现版列里的格号；对不上返回 None。"""
    ids_old = [a for a, _ in cells_old]
    if anchor not in ids_old:
        return None
    i = ids_old.index(anchor)
    so = "".join(c for _, c in cells_old)
    sn = "".join(c for _, c in cells_new)
    for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, so, sn, autojunk=False).get_opcodes():
        if i1 <= i < i2:
            if t == "equal":
                j = j1 + (i - i1)
            elif j2 > j1:
                j = j1 + min(i - i1, j2 - j1 - 1)
            else:
                return None
            return cells_new[j][0] if j < len(cells_new) else None
    return None


def check_file(base, char_path):
    pref = char_path[: -len(".char.json")]
    old_c = git_json(base, char_path)
    if old_c is None:
        return [], []
    with open(os.path.join(ROOT, char_path), encoding="utf-8") as f:
        new_c = json.load(f)
    old_p = git_json(base, pref + ".punct.json")
    new_pf = os.path.join(ROOT, pref + ".punct.json")
    if old_p is None or not os.path.exists(new_pf):
        return [], []
    with open(new_pf, encoding="utf-8") as f:
        new_p = json.load(f)
    co, cn = columns(old_c), columns(new_c)
    old_cell = {a: c for cells in co.values() for a, c in cells}
    new_cell = {a: c for cells in cn.values() for a, c in cells}
    new_keys = {(p["anchor"], p["mark"], p["kind"]) for p in new_p.get("punctuations", [])}
    hard, soft = [], []
    for p in old_p.get("punctuations", []):
        a = p["anchor"]
        sa = split_anchor(a)
        if not sa or (sa[0], sa[1]) not in co or (sa[0], sa[1]) not in cn:
            continue
        if (a, p["mark"], p["kind"]) not in new_keys:
            continue  # 已被挪走或重标
        if old_cell.get(a) == new_cell.get(a):
            continue  # 该格的字没变
        if old_cell.get(a) == "□":
            continue  # 占位符原地补字，不算移位
        col_old = co[(sa[0], sa[1])]
        if p["kind"] == "heading" and p.get("pos") == "before" and a == col_old[0][0]:
            continue  # 列首标题，前面补字后仍应在列首
        mapped = map_cell(col_old, cn[(sa[0], sa[1])], a)
        if mapped is None or mapped == a:
            continue
        msg = (f"{char_path.split('/')[-1]} {a}（{p['mark'].strip() or '断'} {p['kind']} {p.get('source','')}）："
               f"旧字「{old_cell.get(a)}」→现「{new_cell.get(a)}」，对齐后应在 {mapped}")
        (hard if str(p.get("source", "")).startswith("rule:") else soft).append(msg)
    return hard, soft


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/dev")
    ap.add_argument("--fail-all", action="store_true", help="非 rule:* 的也算失败")
    ap.add_argument("--warn-only", action="store_true", help="只告警，退出码恒 0")
    args = ap.parse_args()
    mb = sh("git", "merge-base", "HEAD", args.base)
    ref = mb.stdout.strip() if mb.returncode == 0 else args.base
    files = set(sh("git", "diff", "--name-only", ref).stdout.split())
    files |= set(sh("git", "ls-files", "-m", "--exclude-standard").stdout.split())
    chars = sorted(f for f in files if f.endswith(".char.json") and f.startswith(("Book/", "Work/")))
    hard, soft = [], []
    for f in chars:
        h, s = check_file(ref, f)
        hard += h
        soft += s
    print(f"锚点漂移检查：查 {len(chars)} 个改动的 char 文件，断点／标题漂移 {len(hard)} 处，其他标点 {len(soft)} 处")
    for m in hard:
        print("  失败", m)
    for m in soft[:30]:
        print("  告警", m)
    bad = bool(hard) or (args.fail_all and bool(soft))
    sys.exit(0 if (not bad or args.warn_only) else 1)


if __name__ == "__main__":
    main()
