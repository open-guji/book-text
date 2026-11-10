#!/usr/bin/env python3
"""《史記》光盤本（文淵閣四庫全書電子版）→ book-text 988g3f0wsu。

來源：殆知阁 sikuquanshu.daizhige.org 的 /data/0243.jsonl、0244.jsonl（書 id 792，一叶一行，逐列帶大字／小注），
文字來自文淵閣四庫全書電子版，不是 OCR。格式與總目光盤本（build_zongmu_cd.py，96mid1ogzk/wyg-cd）相同：

- 章節：一冊一章，照本書登記的 42 冊（ai-team domain/CV/新书登记/史记文渊阁/vols_plan.json：[冊, 檔, djvu 起, djvu 止]），
  與將來自校本的冊（001–042）一一對應，便於逐冊對讀；章名按殆知阁 roll 寫「卷一至卷三」，冊一寫「卷首」。
- 一行一列（每半叶 ncol=8 列，空列也留），列首全角空格＝抬頭，雙行夾注 `<右行|左行>`；pages.tsv 記叶碼。
- 不改字、不加標點、不統一異體。私用碼：碼表 pua_table.jsonl（ai-team，sheldon 11-06 定）verdict=char 的換表字；
  multi（一碼多字，按格定）與表外碼一律寫 〓，以圖代字也寫 〓；逐處記入 subst.tsv（章、行、原碼、換成什麼、類別、源叶），可還原。

本書 book-text 裏還沒有自校本，暫放 default/；自校本入庫時照規矩挪到 wyg-cd/（與總目同 key）。

用法：
    build_shiji_cd.py --raw <含 0243、0244.jsonl 的目錄> --pua-table <pua_table.jsonl> \
        --vols-plan <vols_plan.json> --book-text <book-text 倉根> [--key default]
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_zongmu_cd import col_text, load_pua  # noqa: E402

BOOK = "988g3f0wsu"
DZG_BOOK = 792
NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
ROLL = re.compile(r"^卷([一二三四五六七八九十百]+)")
CN = "〇一二三四五六七八九"


def cn(s):
    n, t = 0, s
    if "百" in t:
        a, t = t.split("百", 1)
        n += 100 * (NUM[a] if a else 1)
    if "十" in t:
        a, t = t.split("十", 1)
        n += 10 * (NUM[a] if a else 1)
    if t:
        n += NUM[t]
    return n


def to_cn(n):
    """1..130 → 一…一百三十（四庫本寫法：一百一、一百十）"""
    out = ""
    if n >= 100:
        out += "一百"
        n %= 100
        if n == 0:
            return out
        if n < 10:
            return out + CN[n]
        if n < 20:
            return out + "十" + (CN[n % 10] if n % 10 else "")
    if n >= 10:
        out += ("" if n < 20 and not out else CN[n // 10]) + "十"
        n %= 10
    return out + (CN[n] if n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--pua-table", required=True)
    ap.add_argument("--vols-plan", required=True)
    ap.add_argument("--book-text", required=True)
    ap.add_argument("--key", default="default")
    a = ap.parse_args()
    pua = {k: (("〓", kind, n) if kind == "pua-multi" else (c, kind, n)) for k, (c, kind, n) in load_pua(a.pua_table).items()}
    plan = json.load(open(a.vols_plan, encoding="utf-8"))

    recs = {}
    for f in sorted({p[1] for p in plan}):
        rs = [json.loads(l) for l in open(os.path.join(a.raw, f + ".jsonl"), encoding="utf-8")]
        assert all(r["book"]["id"] == DZG_BOOK for r in rs), f
        assert [r["leaf"] for r in rs] == sorted(r["leaf"] for r in rs), f + " 叶序不單調"
        recs[f] = rs
    seen = set()

    base = os.path.join(a.book_text, "Book", BOOK[-3], BOOK[-2], BOOK[-1], BOOK)
    vdir = os.path.join(base, a.key)
    os.makedirs(vdir, exist_ok=True)
    out_chapters, all_pages, all_subst = [], [], []
    for n, f, d0, d1 in plan:
        rs = [r for r in recs[f] if d0 <= r["djvu"] <= d1]
        seen.update(r["id"] for r in rs)
        nums = [cn(m.group(1)) for r in rs if r.get("roll") and (m := ROLL.match(r["roll"]["name"]))]
        if not nums:
            title = "卷首"
        elif nums[0] == nums[-1]:
            title = "卷" + to_cn(nums[0])
        else:
            title = "卷%s至卷%s" % (to_cn(nums[0]), to_cn(nums[-1]))
        fn = "%03d" % n
        lines, cur_pb, nsub = ["## " + title, ""], None, 0
        for r in rs:
            ncol = r["geom"]["ncol"]
            for col in r["cols"]:
                pb = "%s%s" % (r["page"], "右" if col["no"] // ncol == 0 else "左")
                lineno = len(lines) + 1
                if pb != cur_pb:
                    all_pages.append("%s.md\t%d\t%s" % (fn, lineno, pb))
                    cur_pb = pb
                s, sub = col_text(col, pua)
                for orig, to, kind in sub:
                    all_subst.append("%s.md\t%d\t%s\t%s\t%s\t%s" % (fn, lineno, orig, to, kind, r["id"]))
                nsub += len(sub)
                lines.append(s)
        body = "\n".join(lines) + "\n"
        with open(os.path.join(vdir, fn + ".md"), "w", encoding="utf-8") as fo:
            fo.write(body)
        out_chapters.append({"n": n, "file": fn, "title": title, "has_json": False, "md_len": len(body)})
        print(fn, title, "叶", len(rs), "列", len(lines) - 2, "換字", nsub, file=sys.stderr)
    left = [r["id"] for rs in recs.values() for r in rs if r["id"] not in seen and r["cols"]]
    assert not left, ("有正文叶不在 42 冊範圍內", left[:5])

    with open(os.path.join(vdir, "pages.tsv"), "w", encoding="utf-8") as fo:
        fo.write("file\tline_no\tpb\n" + "\n".join(all_pages) + "\n")
    with open(os.path.join(vdir, "subst.tsv"), "w", encoding="utf-8") as fo:
        fo.write("file\tline_no\torig\tto\tkind\tsrc_id\n" + "\n".join(all_subst) + "\n")
    idx = {
        "version_label": "文淵閣四庫全書電子版（光盤本）",
        "edition_note": "文字來自文淵閣四庫全書電子版（光盤本），經殆知阁整理，非 OCR；無標點，一行一列，一冊一章（與本書登記的 42 冊同範圍）。不改字、不統一異體；私用碼按碼表換最相近字，一碼多字、表外碼與以圖代字寫〓，逐處見 subst.tsv。",
        "fetched_at": "2026-11-09",
        "guji_markdown": "0.2.0",
        "line_is_column": True,
        "revision": "0.1.0",
        "book_id": BOOK,
        "chapters": out_chapters,
        "source": {"name": "殆知阁・文淵閣四庫全書", "url": "https://sikuquanshu.daizhige.org/",
                   "license": "来自网络，版权未知",
                   "base_edition": "文淵閣四庫全書", "files": "data/0243.jsonl, data/0244.jsonl"},
        "total_chapters": len(out_chapters),
        "text_quality": {"grade": "source"},
    }
    with open(os.path.join(vdir, "index.json"), "w", encoding="utf-8") as fo:
        json.dump(idx, fo, ensure_ascii=False, indent=2)
        fo.write("\n")

    mpath = os.path.join(base, "manifest.json")
    m = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {"id": BOOK, "versions": []}
    entry = {
        "key": a.key,
        "kind": "transcription",
        "label": "殆知閣",
        "source": "daizhige-wyg",
        "source_name": "殆知阁・文淵閣四庫全書",
        "source_url": "https://sikuquanshu.daizhige.org/",
        "license": "来自网络，版权未知",
        "quality": "source",
        "chapters_total": len(out_chapters),
        "edition_label": "文淵閣四庫全書電子版（光盤本）",
        "script": "hant",
        "note": "無標點、保持原分行；一冊一章（42 冊），供與自校本逐冊對讀。私用碼換字逐處見 subst.tsv。自校本入庫後挪到 wyg-cd。",
    }
    m["versions"] = [v for v in m["versions"] if v.get("key") != a.key]
    m["versions"].insert(0 if a.key == "default" else len(m["versions"]), entry)
    with open(mpath, "w", encoding="utf-8") as fo:
        json.dump(m, fo, ensure_ascii=False, indent=2)
        fo.write("\n")


if __name__ == "__main__":
    main()
