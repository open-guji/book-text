#!/usr/bin/env python3
"""核对 guji entity v0.2 数据的规范（规则出处：guji-format spec/05-guji-entity.md §四·1、§五、§九）。

用法：t_entity_check.py <book_dir/default 或章目录> [--schema <guji_entity_v0.2.schema.json>]

对目录下每个 NNN.entity.json（配同目录 NNN.char.json、NNN.punct.json、index.json）逐条核对，
每条违规打一行「规则名 实体id 说明」，末行「总计 N 个问题」；有问题退出码 1，无则 0。
给了 --schema 且装了 jsonschema 时额外跑 JSON Schema 校验（规则名 jsonschema）；没装则提示一行后跳过。
"""
import argparse
import collections
import glob
import json
import os
import sys

SCHEMA_URL = "https://open-guji.org/schema/entity/v0.2.json"
TYPES = {"work", "people", "place", "office", "dynasty", "reign", "other"}
LEGACY = ("coarse", "reclass", "route_to", "entity_type")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(ent, char, punct, index, ch):
    """核对一章，返回 [(规则名, 实体id, 说明)]。ch 为章号（如 002）。"""
    out = []

    def bad(rule, eid, msg=""):
        out.append((rule, eid, f"[{ch}] {msg}".rstrip()))

    if ent.get("$schema") != SCHEMA_URL:
        bad("schema_url", ch, str(ent.get("$schema")))
    es = ent["entities"]
    ids = [e["id"] for e in es]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        bad("dup_id", dup)
    seq = [x for p in char["pages"] for col in p["columns"] for x in col["cells"]]
    pos = {x["a"]: i for i, x in enumerate(seq)}
    opens = {p["anchor"] for p in punct.get("punctuations", []) if p.get("mark") == "《"}
    closes = {p["anchor"] for p in punct.get("punctuations", []) if p.get("mark") == "》"}

    prev = -1
    for e in sorted(es, key=lambda e: e["span"]["start_offset"]):
        s, t = e["span"]["start_offset"], e["span"]["end_offset"]
        if s < prev:
            bad("overlap", e["id"], f"起点 {s} 早于前一 span 终点 {prev}")
        prev = max(prev, t)

    groups = collections.defaultdict(list)
    for e in es:
        eid, a, tg = e["id"], e["anchor"], e["target"]
        s, t = e["span"]["start_offset"], e["span"]["end_offset"]
        st = tg.get("status")
        if pos.get(a["start"]) != s or pos.get(a["end"]) != t - 1:
            bad("span_anchor", eid, f"anchor {a['start']}..{a['end']} 与 span {s}..{t}")
        if "".join(x["c"] for x in seq[s:t]) != e["text"]:
            bad("text", eid, e["text"])
        if st == "matched":
            if not all(k in tg for k in ("entity_id", "canonical_name", "href")) or "candidates" in tg:
                bad("matched_fields", eid)
            elif tg["href"].rsplit("/", 1)[-1] != tg["entity_id"]:
                bad("href_tail", eid, tg["href"])
        elif st == "ambiguous":
            if len(tg.get("candidates", [])) < 2:
                bad("ambiguous_lt2", eid, e["text"])
            if "entity_id" in tg or "href" in tg:
                bad("ambiguous_extra", eid)
        elif st == "new_candidate" and any(k in tg for k in ("entity_id", "href", "candidates")):
            bad("nc_extra", eid)
        for k in LEGACY:
            if k in tg:
                bad(f"legacy_{k}", eid)
        if e["type"] not in TYPES:
            bad("type", eid, e["type"])
        if "group" in e:
            groups[e["group"]["id"]].append(e)
        if e["type"] == "work":
            if a["start"] not in opens:
                bad("work_open_missing", eid, e["text"])
            if a["end"] not in closes:
                bad("work_close_missing", eid, e["text"])

    for gid, g in groups.items():
        g.sort(key=lambda e: e["span"]["start_offset"])
        first = g[0]
        if len(g) < 2:
            bad("group_lt2", gid)
        if gid != "g" + first["id"]:
            bad("group_id", gid, f"首 span 为 {first['id']}")
        if "".join(e["text"] for e in g) != first["group"]["text"]:
            bad("group_text", gid)
        for x, y in zip(g, g[1:]):
            if x["span"]["end_offset"] != y["span"]["start_offset"]:
                bad("group_adjacent", gid, f"{x['id']}→{y['id']}")
        if any(e["group"] != first["group"] for e in g):
            bad("group_mixed", gid)

    recs = [x for x in (index or {}).get("chapters", []) if x.get("file") == ch]
    if not recs or recs[0].get("entity_version") != ent.get("version"):
        bad("version_mirror", ch, f"entity.json {ent.get('version')}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--schema")
    a = ap.parse_args(argv)
    d = a.dir if glob.glob(os.path.join(a.dir, "*.entity.json")) else os.path.join(a.dir, "default")
    idx = os.path.join(d, "index.json")
    index = load(idx) if os.path.exists(idx) else None
    validator = None
    if a.schema:
        try:
            import jsonschema
            validator = jsonschema.Draft202012Validator(load(a.schema))
        except ImportError:
            print("提示：未装 jsonschema，跳过 schema 校验")
    problems = []
    for p in sorted(glob.glob(os.path.join(d, "*.entity.json"))):
        ch = os.path.basename(p)[: -len(".entity.json")]
        base = os.path.join(d, ch)
        ent = load(p)
        problems += check(ent, load(base + ".char.json"), load(base + ".punct.json"), index, ch)
        if validator:
            problems += [("jsonschema", ch, f"{list(e.path)[:3]} {e.message[:120]}")
                         for e in validator.iter_errors(ent)]
    for rule, eid, msg in problems:
        print(f"{rule} {eid} {msg}")
    print(f"总计 {len(problems)} 个问题")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
