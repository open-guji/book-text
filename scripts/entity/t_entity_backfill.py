#!/usr/bin/env python3
"""把键表命中回写到整理本 NNN.entity.json 的 target（T 小总管，#478）。

只改 target 与（订正用）type，不动 anchor／span／text。默认干跑；--write 才落盘。
规则（契约草稿 §二）：
  - 唯一候选 -> matched（entity_id、canonical_name、href=book-index://Entity/<id>）
  - 地名多候选且恰一个 default -> matched，note 记「default」
  - 朝代／年号多候选（<=6）-> ambiguous + candidates
  - 官职多候选且恰一条概念条（无 ambiguous）-> matched，level=concept
  - 其余保持不动；已是 matched 的不改
  - span 类型与候选 subtype 不一致（dynasty vs reign 等）-> 不写，记入报告 reclass
整串命中才回写；复合名拆分（相邻 span）另批做。
用法：t_entity_backfill.py <dynasty_reign_keys.json> <office_keys.json> <place_keys.json> <NNN.entity.json> [--write] [--fix-type e00126=place]
"""
import json
import sys

from t_entity_split import normalize

TYPE_SUBTYPES = {
    "dynasty": {"dynasty"},
    "reign": {"reign"},
    "office": {"office", "官署"},
    "place": {"place"},
}


def load(path):
    return json.load(open(path, encoding="utf-8"))


def cand(c):
    return {"entity_id": c["id"], "canonical_name": c["primary_name"]}


def decide(e, tables):
    t = e["type"]
    if t not in TYPE_SUBTYPES or e["target"].get("status") == "matched":
        return None, None
    if t == "place" and len(e["text"]) < 2:  # 閩、蜀、贛 等单字多为区域／政权，不配
        return None, None
    keys = tables["dynasty" if t in ("dynasty", "reign") else t]
    s = normalize(e["text"], keys.get("normalize"))
    cs = keys["keys"].get(s, [])
    ok = [c for c in cs if c.get("subtype") in TYPE_SUBTYPES[t]]
    if cs and not ok:
        return None, {"reclass": [c.get("subtype") for c in cs]}
    if len(ok) == 1 and ok[0].get("ambiguous"):
        return {"status": "ambiguous", "canonical_name": e["text"], "candidates": [cand(ok[0])]}, None
    if len(ok) == 1:
        c = ok[0]
        tg = {"status": "matched", **cand(c), "href": "book-index://Entity/" + c["id"]}
        if c.get("level") == "concept":
            tg["level"] = "concept"
        return tg, None
    if len(ok) > 1:
        d = [c for c in ok if c.get("default")]
        if t == "place" and len(d) == 1:
            c = d[0]
            return {"status": "matched", **cand(c), "href": "book-index://Entity/" + c["id"], "note": "default"}, None
        if t == "office" and not any(c.get("ambiguous") for c in ok):
            con = [c for c in ok if c.get("level") == "concept" and c.get("subtype") == "office"]
            if len(con) == 1:
                c = con[0]
                return {"status": "matched", **cand(c), "href": "book-index://Entity/" + c["id"],
                        "level": "concept", "note": "未定朝代，挂概念条"}, None
        if len(ok) <= 6 and t != "office":
            return {"status": "ambiguous", "canonical_name": e["text"], "candidates": [cand(c) for c in ok]}, None
    return None, None


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    write = "--write" in argv
    fixes = dict(a.split("=", 1)[1].split("=") for a in argv[1:] if a.startswith("--fix-type="))
    tables = {"dynasty": load(args[0]), "office": load(args[1]), "place": load(args[2])}
    d = load(args[3])
    stat, reclass = {}, []
    for e in d["entities"]:
        if e["id"] in fixes:
            stat["type_fix"] = stat.get("type_fix", 0) + 1
            if write:
                e["type"] = fixes[e["id"]]
        tg, info = decide(e, tables)
        if info:
            reclass.append((e["id"], e["type"], e["text"], info["reclass"]))
        if tg:
            k = e["type"] + ":" + tg["status"]
            stat[k] = stat.get(k, 0) + 1
            if write:
                e["target"] = tg
    if write:
        m = sum(1 for e in d["entities"] if e["target"].get("status") == "matched")
        d["stats"]["matched"] = m
        d["stats"]["new_candidates"] = sum(1 for e in d["entities"] if e["target"].get("status") == "new_candidate")
        json.dump(d, open(args[3], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(args[3], "a", encoding="utf-8").write("\n")
    print(json.dumps({"stat": stat, "reclass": reclass}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
