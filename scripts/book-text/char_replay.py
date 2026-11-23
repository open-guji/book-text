#!/usr/bin/env python3
"""char.json 逐格重放（2026-11-10 用户定；ZM 提议）：以 main 为底，把 dev 相对共同祖先的改动按格重放。

规则（每个格地址 a 单独判断，base＝共同祖先，M＝main，D＝dev）：
  D==B → 取 M（dev 没动，main 的改动保留）；M==B → 取 D（只有 dev 改）；M==D → 取 M；
  M、D 都改且不同（真冲突）→ **取 M**（不用 dev 覆盖 main），记入冲突清单，交书项目裁。
dev 相对共同祖先增删了格时不自动合（返回 None 留给人）；main 新增或删除的格以 main 为准。
以「字 c」为准判断谁改了：dev 只动 pending_reason／lacuna 等附属字段、没改字，算 dev 没动。
用法：char_replay.py <path> --base <rev> --main <rev> --dev <rev> [--write]  打印格数统计和冲突清单。
"""
from __future__ import annotations
import argparse, json, subprocess, sys


def _git_show(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _cells(doc):
    return {x["a"]: x for pg in doc["pages"] for c in pg["columns"] for x in c["cells"]}


def replay(base_txt, main_txt, dev_txt):
    """返回 (合并后的 JSON 文本, 冲突清单[(a, base_c, main_c, dev_c)])；格地址集合不一致返回 (None, [])。"""
    if not (base_txt and main_txt and dev_txt):
        return None, []
    b, m, d = json.loads(base_txt), json.loads(main_txt), json.loads(dev_txt)
    bc, mc, dc = _cells(b), _cells(m), _cells(d)
    if dc.keys() != bc.keys():  # dev 增删了格：结构变化，留给人
        return None, []
    conflicts = []
    for a, mcell in mc.items():
        if a not in bc:  # main 新增的格（人审补回等），dev 没有，原样保留
            continue
        B, D = bc[a], dc[a]
        if D.get("c") == B.get("c") or mcell == D:
            continue  # dev 没改字（只动了 pending_reason／lacuna 等附属字段），取 main 整格
        if mcell.get("c") == B.get("c"):
            mcell.clear(); mcell.update(D)  # 只有 dev 改字
        else:
            conflicts.append((a, B.get("c"), mcell.get("c"), D.get("c")))  # 两边改了字且不同：取 main
    # 缩进沿用 main 原文的写法（探测：首行后是否缩进）
    indent = 2 if main_txt.startswith("{\n ") else None
    out = json.dumps(m, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
    return out + ("\n" if main_txt.endswith("\n") else ""), conflicts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path"); ap.add_argument("--base", required=True)
    ap.add_argument("--main", required=True); ap.add_argument("--dev", required=True)
    ap.add_argument("--write", action="store_true", help="把合并结果写到工作区的 path")
    a = ap.parse_args()
    out, conf = replay(*(_git_show(r, a.path) for r in (a.base, a.main, a.dev)))
    if out is None:
        print(f"✗ {a.path}：格地址集合不一致或缺文件，不自动合"); return 1
    print(f"✓ {a.path}：真冲突 {len(conf)} 格（取 main）")
    for a_, b_, m_, d_ in conf:
        print(f"  {a_}\tbase={b_}\tmain={m_}\tdev={d_}")
    if a.write:
        open(a.path, "w", encoding="utf-8").write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
