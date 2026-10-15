#!/usr/bin/env python3
"""P0 类型清理：按候选清单的 suggest 改实体类型（年号→reign、庙号/误标人名→people、drop 删除）。
用法：t_entity_p0_types.py <default 目录> <候选清单目录> [--write]  （无 --write 只报告）"""
import json, sys, glob, os, collections
d, cdir = sys.argv[1], sys.argv[2]; write = "--write" in sys.argv
M = {}
for f in glob.glob(os.path.join(cdir, "候选清单-*.json")):
    for r in json.load(open(f)):
        s = r["suggest"]
        if s in ("reign", "people", "people(庙号)", "drop"):
            M[(r["type"], r["text"])] = "people" if s.startswith("people") else s
PLUR = {"work": "works", "people": "people", "place": "places", "office": "offices", "dynasty": "dynasties", "reign": "reigns"}
for ef in sorted(glob.glob(os.path.join(d, "*.entity.json"))):
    D = json.load(open(ef)); cnt = collections.Counter(); out = []
    for e in D["entities"]:
        a = M.get((e["type"], e["text"]))
        if a == "drop": cnt["drop"] += 1; continue
        if a:
            cnt[f'{e["type"]}→{a}'] += 1; e["type"] = a
            e["target"] = {"status": "new_candidate", "canonical_name": e["text"].replace("歴", "曆")}
        out.append(e)
    print(os.path.basename(ef), dict(cnt))
    if write and cnt:
        D["entities"] = out; st = D.get("stats", {})
        c = collections.Counter(e["type"] for e in out)
        st["total_entities"] = len(out)
        for t, k in PLUR.items():
            if c[t] or k in st: st[k] = c[t]
        st["matched"] = sum(e["target"].get("status") == "matched" for e in out)
        st["new_candidates"] = sum(e["target"].get("status") == "new_candidate" for e in out)
        json.dump(D, open(ef, "w"), ensure_ascii=False, indent=2); open(ef, "a").write("\n")
