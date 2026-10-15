#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P5b 查重：建档清单书名 → 库内 Work 候选（只出候选，不下结论）。
用法: work_dedupe.py --list 建档清单-批2-书名.md --index <book-index root> --out 查重候选.tsv
      work_dedupe.py --self-test --index <root>   # 回放批1：16 本书应各自精确命中自己
档位: exact(字面) / fold(异体折叠) / near(含/被含，≥3字) """
import argparse, json, os, re, sys
FOLD = str.maketrans({"畧":"略","襍":"雜","㫖":"旨","旨":"旨","彞":"彝","繫":"系","係":"系","辭":"辞","詞":"辞","辞":"辞",
                      "髙":"高","𢑴":"彝","衞":"衛","啓":"啟","爲":"為","於":"于","眞":"真","裏":"裡","着":"著","説":"說","観":"觀"})
def fold(s): return re.sub(r"[\s·・（）()《》]", "", s).translate(FOLD)
def load(root):
    rows = []
    for d, _, fs in os.walk(os.path.join(root, "Work")):
        for f in fs:
            if not f.endswith(".json"): continue
            try: j = json.load(open(os.path.join(d, f), encoding="utf-8"))
            except Exception: continue
            names = [j.get("title", "")] + list(j.get("additional_titles") or [])
            au = ";".join(a.get("name", "") for a in (j.get("authors") or []) if isinstance(a, dict))
            rows.append((j.get("id", f.split("-")[0]), names, au, j.get("period", "")))
    return rows
def build(rows):
    ex, fo = {}, {}
    for i, names, au, per in rows:
        for n in names:
            if not n: continue
            ex.setdefault(n, []).append((i, names[0], au, per))
            fo.setdefault(fold(n), []).append((i, names[0], au, per))
    return ex, fo
def match(q, rows, ex, fo):
    out, seen = [], set()
    for h in ex.get(q, []):
        out.append(("exact",) + h); seen.add(h[0])
    for h in fo.get(fold(q), []):
        if h[0] not in seen: out.append(("fold",) + h); seen.add(h[0])
    fq = fold(q)
    if len(fq) >= 3:
        for i, names, au, per in rows:
            if i in seen: continue
            for n in names:
                fn = fold(n)
                if len(fn) >= 3 and (fq in fn or fn in fq):
                    out.append(("near", i, names[0], au, per)); seen.add(i); break
    return out
def parse_list(path):
    out = []
    for ln in open(path, encoding="utf-8"):
        m = re.match(r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", ln)
        if m: out.append((int(m.group(1)), m.group(2)))
    return out
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list"); ap.add_argument("--index", required=True)
    ap.add_argument("--out"); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    rows = load(a.index); ex, fo = build(rows)
    print("works loaded:", len(rows), file=sys.stderr)
    if a.self_test:
        b1 = ["古周易章句外編","周禮全解","三墳訓義","易禮圖說","鄭夬易傳","鄭夬時用書","明用書","易傳詞","易傳詞後語",
              "綠竹堂書目","傳易考","讀易韻考註","讀易約說","易雜說","詩書演義","讀易臆說"]
        bad = 0
        for n in b1:
            hs = [h for h in match(n, rows, ex, fo) if h[0] == "exact"]
            ok = len(hs) == 1 and hs[0][1].startswith("d59fu304ue")
            bad += (not ok)
            print(("OK  " if ok else "BAD ") + n, [h[1] for h in hs])
        print("mismatch=%d" % bad); return
    with open(a.out, "w", encoding="utf-8") as w:
        w.write("no\tname\ttier\thit_id\thit_title\thit_authors\thit_period\n")
        for no, name in parse_list(a.list):
            hs = match(name, rows, ex, fo)
            if not hs: w.write(f"{no}\t{name}\tnone\t\t\t\t\n")
            for t, i, tt, au, per in hs:
                w.write(f"{no}\t{name}\t{t}\t{i}\t{tt}\t{au}\t{per}\n")
if __name__ == "__main__": main()
