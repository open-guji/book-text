#!/usr/bin/env python3
"""把 note 写着「同名 N 条待消歧: <id…>」的 new_candidate 改成 ambiguous＋candidates（T，#478；吻合度报告 E4）。

每个 id 按 book-index（正式）→ book-index-draft 的 Work／Entity／Book 文件名「<id>-<题名>.json」查题名；
只在草稿库的 id 不改写（升格后的回挂另批）。查不到的 id 丢掉并报告；剩 <2 个候选则保持 new_candidate。
note 里的「同名…待消歧」尾巴删掉，前面其他说明（如避諱字還原）保留。
用法：t_entity_ambiguous.py <book-index 根> <book-index-draft 根> <NNN.entity.json>... [--write]
"""
import json
import os
import re
import sys

PAT = re.compile(r"(?:^|；)?\s*同名\s*(\d+)\s*条待消歧:\s*((?:[0-9a-z]{12,13}\s*)+)")


def work_titles(*roots):
    t = {}
    for repo, root in enumerate(roots):
        for d, dirs, fs in os.walk(root):
            if d == root:
                dirs[:] = [x for x in dirs if x in ("Work", "Entity", "Book")]
            for f in fs:
                m = re.match(r"([0-9a-z]{12,13})-(.*)\.json$", f)
                if m:
                    t.setdefault(m.group(1), (repo, m.group(2)))
    return t


def load_promotions(root):
    """正式库 promotions/<末2位>.json 分片：草稿 id -> 正式 id。"""
    m = {}
    d = os.path.join(root, "promotions")
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            m.update({k: v["production_id"] for k, v in json.load(open(os.path.join(d, f), encoding="utf-8"))["promotions"].items()})
    return m


def convert(e, titles, promo=None):
    tg = e["target"]
    if tg.get("status") != "new_candidate" or "note" not in tg:
        return None
    m = PAT.search(tg["note"])
    if not m:
        return None
    ids = m.group(2).split()
    cands, dropped = [], []
    promo = promo or {}
    seen = set()
    for i in ids:
        if i not in titles and promo.get(i) in titles:
            i = promo[i]  # 草稿 id 已升格：改写成正式 id
        if i in seen:
            continue
        seen.add(i)
        if i in titles:
            cands.append({"entity_id": i, "canonical_name": titles[i][1]})
        else:
            dropped.append(i)
    info = {"n": int(m.group(1)), "ids": len(ids), "dropped": dropped, "kept": len(cands)}
    if len(cands) < 2:
        return None, info
    rest = (tg["note"][:m.start()] + tg["note"][m.end():]).strip("； ;")
    if int(m.group(1)) != len(ids):  # 原 note 只列了前几个 id
        rest = (rest + "；" if rest else "") + f"同名 {m.group(1)} 条，候选只列前 {len(ids)} 条"
    new = {"status": "ambiguous", "canonical_name": tg["canonical_name"], "candidates": cands}
    if rest:
        new["note"] = rest
    return new, info


def main(argv):
    a = [x for x in argv[1:] if not x.startswith("--")]
    titles = work_titles(a[0], a[1])
    promo = load_promotions(a[0])
    rep = {"converted": 0, "kept_nc": 0, "id_count_mismatch": 0, "dropped_ids": 0, "from_draft_only": 0}
    for f in a[2:]:
        d = json.load(open(f, encoding="utf-8"))
        for e in d["entities"]:
            r = convert(e, titles, promo)
            if not r:
                continue
            new, info = r
            rep["id_count_mismatch"] += info["n"] != info["ids"]
            rep["dropped_ids"] += len(info["dropped"])
            if new is None:
                rep["kept_nc"] += 1
                continue
            rep["from_draft_only"] += sum(titles[c["entity_id"]][0] == 1 for c in new["candidates"])
            rep["converted"] += 1
            if "--write" in argv:
                e["target"] = new
        if "--write" in argv:
            d["stats"]["ambiguous"] = sum(1 for e in d["entities"] if e["target"]["status"] == "ambiguous")
            d["stats"]["new_candidates"] = sum(1 for e in d["entities"] if e["target"]["status"] == "new_candidate")
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
