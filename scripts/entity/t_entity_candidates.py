#!/usr/bin/env python3
"""#464 P1：抽取 original 形态书的 entity.json 里 dynasty／office 候选，去重统计，带 ±10 字上下文，并按规则给出 P0 类型建议。
用法：t_entity_candidates.py <book 的 default 目录> <输出目录>"""
import json, sys, glob, os, collections, re
sys.path.insert(0, os.path.dirname(__file__))
from original_version import char_slots

# P0 规则：type=dynasty 里的非朝代
REIGN = {"萬歴", "萬曆", "嘉靖", "隆慶", "淳熙"}                       # 年号
EMPEROR = {"徽宗", "孝宗", "神宗", "哲宗", "欽宗", "寧宗"}             # 庙号 → people
NOT_DYN = {"聖人"}                                                     # 泛称，去标
PERSON_AS_OFFICE = {"黃登賢", "勵守謙"}                                # 人名 → people
GENERIC_OFFICE = {"老師宿儒"}                                          # 泛称，去标


def suggest(typ, text):
    if typ == "dynasty":
        if text in REIGN: return "reign"
        if text in EMPEROR: return "people(庙号)"
        if text in NOT_DYN: return "drop"
    if typ == "office":
        if text in PERSON_AS_OFFICE: return "people"
        if text in GENERIC_OFFICE: return "drop"
    return typ


def main(d, outdir):
    os.makedirs(outdir, exist_ok=True)
    agg = {}
    for ef in sorted(glob.glob(os.path.join(d, "*.entity.json"))):
        vol = os.path.basename(ef).split(".")[0]
        cf = ef.replace(".entity.json", ".char.json")
        slots = char_slots(json.load(open(cf)))
        pos = {a: i for i, (a, _c) in enumerate(slots)}
        for e in json.load(open(ef))["entities"]:
            if e["type"] not in ("dynasty", "office"): continue
            anc = e.get("anchor") or {}
            s, t = pos.get(anc.get("start")), pos.get(anc.get("end"))
            ctx = ""
            if s is not None and t is not None:
                g = lambda a, b: "".join(c for _x, c in slots[max(a, 0):b])
                ctx = f"{g(s-10, s)}【{g(s, t+1)}】{g(t+1, t+11)}"
            k = (e["type"], e["text"])
            r = agg.setdefault(k, {"type": e["type"], "text": e["text"], "suggest": suggest(*k),
                                   "status": e["target"]["status"], "count": 0, "examples": []})
            r["count"] += 1
            if len(r["examples"]) < 3:
                r["examples"].append({"vol": vol, "id": e["id"], "ctx": ctx})
    for typ in ("dynasty", "office"):
        rows = sorted((r for r in agg.values() if r["type"] == typ), key=lambda r: (-r["count"], r["text"]))
        json.dump(rows, open(os.path.join(outdir, f"候选清单-{typ}.json"), "w"), ensure_ascii=False, indent=1)
        print(typ, len(rows), sum(r["count"] for r in rows),
              "需改类型:", sum(1 for r in rows if r["suggest"] != typ))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
