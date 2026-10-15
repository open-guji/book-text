#!/usr/bin/env python3
"""复合专名拆成相邻 span（T 小总管，#478 批2；网站经理 10-08 采纳方案 A）。

整串 span 删除，换成上级／下级两个相邻 span，各带自己的 anchor、span 偏移和 target；
整串信息放在每个 part 的可选 `group`（网站忽略，不影响渲染）。
逐字 anchor 由 NNN.char.json 的格位序列换算：序列＝pages→columns→cells 的文件顺序，
span 偏移即序列下标，anchor＝格位 a。拆分后核：序列字＝part 文本、首尾 a＝anchor。

拆哪些（只拆整串未命中、且两头都能在键表命中的）：
  office  split      官署前缀＋官职后缀 -> [官署(office), 官职(office)]
  office  tail_only  前缀是地名键       -> [地名(place), 官职(office)]
  place   州＋縣      两头都是地名键（各≥2字）-> [地名, 地名]
用法：t_entity_compound.py <dynasty_keys> <office_keys> <place_keys> <char.json> <entity.json> [--write]
"""
import json
import sys

from t_entity_backfill import decide, load
from t_entity_split import normalize, split_office


def cell_seq(char_json):
    return [cell for p in char_json["pages"] for col in p["columns"] for cell in col["cells"]]


def make_part(seq, e, i, j, ptype, text, new_id, group):
    s = e["span"]["start_offset"]
    return {
        "id": new_id,
        "type": ptype,
        "text": text,
        "anchor": {"start": seq[s + i]["a"], "end": seq[s + j - 1]["a"]},
        "span": {"start_offset": s + i, "end_offset": s + j},
        "target": {"status": "new_candidate", "canonical_name": text},
        "source": e.get("source", ""),
        "group": group,
    }


def plan(e, tables, place_keys, office_keys, inst_keys):
    """返回 [(i, j, type)] 或 None。"""
    t = e["text"]
    mp = tables["office"].get("normalize")
    if e["type"] == "office":
        r = split_office(t, office_keys, inst_keys, mp)
        n = normalize(t, mp)
        if r["mode"] == "split":
            k = len(r["institution"])
            return [(0, k, "office"), (k, len(n), "office")]
        if (r["mode"] == "tail_only" and r["scope_text"] in place_keys and len(r["scope_text"]) >= 2
                and not r["base"].startswith("書院")):  # 東湖書院山長 的「東湖」是书院名，不是行政区
            k = len(r["scope_text"])
            return [(0, k, "place"), (k, len(n), "office")]
    if e["type"] == "place":
        n = normalize(t, tables["place"].get("normalize"))
        if n in place_keys:
            return None
        for k in range(len(n) - 2, 1, -1):  # 上级尽量长
            if k >= 2 and n[:k] in place_keys and len(n) - k >= 2 and n[k:] in place_keys:
                return [(0, k, "place"), (k, len(n), "place")]
    return None


def apply(char_json, ent_json, tables, write=False):
    seq = cell_seq(char_json)
    office_keys = set(k for k, cs in tables["office"]["keys"].items() if any(c["subtype"] == "office" for c in cs))
    inst_keys = set(k for k, cs in tables["office"]["keys"].items() if any(c["subtype"] == "官署" for c in cs))
    place_keys = set(tables["place"]["keys"])
    nid = max(int(x["id"][1:]) for x in ent_json["entities"] if x["id"][1:].isdigit()) + 1
    out, report = [], []
    for e in ent_json["entities"]:
        pl = plan(e, tables, place_keys, office_keys, inst_keys) if e["target"].get("status") != "matched" else None
        if not pl:
            out.append(e)
            continue
        group = {"id": "g" + e["id"], "text": e["text"], "kind": "compound"}
        parts = []
        for n, (i, j, ptype) in enumerate(pl):
            text = e["text"][i:j]
            pid = e["id"] if n == 0 else "e%05d" % nid
            if n:
                nid += 1
            p = make_part(seq, e, i, j, ptype, text, pid, group)
            got = "".join(c["c"] for c in seq[p["span"]["start_offset"]:p["span"]["end_offset"]])
            assert got == text, (e["id"], got, text)
            tg, _ = decide(p, tables)
            if tg:
                p["target"] = tg
            parts.append(p)
        out.extend(parts)
        report.append((e["id"], e["text"], [(p["type"], p["text"], p["target"]["status"]) for p in parts]))
    if write:
        ent_json["entities"] = out
        st = ent_json["stats"]
        st["total_entities"] = len(out)
        for key, ty in (("works", "work"), ("people", "people"), ("places", "place"),
                        ("offices", "office"), ("dynasties", "dynasty"), ("reigns", "reign")):
            st[key] = sum(1 for x in out if x["type"] == ty)
        st["matched"] = sum(1 for x in out if x["target"].get("status") == "matched")
        st["new_candidates"] = sum(1 for x in out if x["target"].get("status") == "new_candidate")
    return report


def main(argv):
    a = [x for x in argv[1:] if not x.startswith("--")]
    tables = {"dynasty": load(a[0]), "office": load(a[1]), "place": load(a[2])}
    ent = load(a[4])
    rep = apply(load(a[3]), ent, tables, "--write" in argv)
    if "--write" in argv:
        with open(a[4], "w", encoding="utf-8") as f:
            json.dump(ent, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps({"n": len(rep), "split": rep}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
