#!/usr/bin/env python3
"""键表命中统计与未命中清单（T 小总管，#464 / #478）。

读整理本 NNN.entity.json（已回挂后的），输出：
  - 各 type × status 计数；
  - matched 按 entity_id 的命中次数（供目录按命中分批升格）；
  - ambiguous 的写法与次数；
  - new_candidate 的写法与次数（建档候选清单）。
用法：t_entity_hitstats.py <entity.json>... [--md 输出.md]
"""
import collections
import json
import sys


def main(argv):
    files = [a for a in argv[1:] if not a.startswith("--") and a.endswith(".json")]
    c = collections.Counter()
    hit = collections.Counter()
    name = {}
    amb = collections.Counter()
    nc = collections.defaultdict(collections.Counter)
    for f in files:
        for e in json.load(open(f, encoding="utf-8"))["entities"]:
            tg = e["target"]
            c[(e["type"], tg["status"])] += 1
            if tg["status"] == "matched":
                hit[tg["entity_id"]] += 1
                name[tg["entity_id"]] = (e["type"], tg["canonical_name"], tg.get("level", ""))
            elif tg["status"] == "ambiguous":
                amb[(e["type"], e["text"], tuple(x["canonical_name"] for x in tg["candidates"]))] += 1
            else:
                nc[e["type"]][e["text"]] += 1
    out = {"counts": {f"{t}:{s}": n for (t, s), n in sorted(c.items())},
           "hits": [(i, *name[i], n) for i, n in hit.most_common()],
           "ambiguous": [(*k, n) for k, n in amb.most_common()],
           "new_candidate": {t: nc[t].most_common() for t in nc if t != "work" and t != "people"}}
    if "--md" in argv:
        md = open(argv[argv.index("--md") + 1], "w", encoding="utf-8")
        md.write("# 键表命中统计与未命中清单\n\n## 计数\n\n| type:status | 处数 |\n|---|---|\n")
        for k, n in out["counts"].items():
            md.write(f"| {k} | {n} |\n")
        md.write("\n## matched：按条目命中次数（高→低）\n\n| 条目 id | type | 规范名 | level | 命中 |\n|---|---|---|---|---|\n")
        for i, t, n_, lv, k in out["hits"]:
            md.write(f"| {i} | {t} | {n_} | {lv} | {k} |\n")
        md.write("\n## ambiguous（待年代／上下文消歧）\n\n| type | 写法 | 候选 | 处数 |\n|---|---|---|---|\n")
        for t, x, cs, k in out["ambiguous"]:
            md.write(f"| {t} | {x} | {'／'.join(cs)} | {k} |\n")
        md.write("\n## new_candidate（朝代／年号／官职／地名；人名、书名不列）\n")
        for t, lst in out["new_candidate"].items():
            md.write(f"\n### {t}（{sum(n for _, n in lst)} 处，{len(lst)} 种）\n\n" + "、".join(f"{x}×{n}" if n > 1 else x for x, n in lst) + "\n")
        md.close()
    else:
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
