#!/usr/bin/env python3
"""《欽定四庫全書總目》光盤本（文淵閣四庫全書電子版）→ book-text 96mid1ogzk/wyg-cd 版本。

來源：殆知阁 sikuquanshu.daizhige.org 的 /data/0001..0005.jsonl（一叶一行，逐列帶大字／小注），
文字來自文淵閣四庫全書電子版，不是 OCR。本腳本只做機械格式轉換：

- 章節切分：照殿本 default/index.json 的 99 章，以各章第一個「欽定四庫全書總目卷X」列為界，
  使殿本第 n 章與本版第 n 章卷範圍相同，便於逐章對讀。
- 格式照 Kanripo 的 line_is_column 版：一行一列，列首全角空格＝抬頭，雙行夾注 `<右行|左行>`，
  每章 pages.tsv 記叶碼，不改字、不加標點、不統一異體。
- 私用碼：碼表 pua_table.jsonl（ai-team）verdict=char／multi 者換成表字（最相近字），其餘與「以圖代字」寫 〓；
  全部換字逐處記入 subst.tsv（章、行、列內位置、原碼、換成什麼、類別），可還原。

用法：
    build_zongmu_cd.py --raw <含 0001..0005.jsonl 的目錄> --pua-table <pua_table.jsonl> \
        --book-text <book-text 倉根> [--chapters 2,3]
"""
import argparse, json, os, re, sys

BOOK = "96mid1ogzk"
KEY = "wyg-cd"
NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
HEAD = re.compile(r"^欽定四庫全書(?:總目)?[卷巻]([首一二三四五六七八九十百]*)$")
PUA = re.compile("[-\U000f0000-\U0010ffff]")
IMG = "ခ"  # 以圖代字占位（緬文字母）


def cn(s):
    if s.startswith("首"):
        return "S" + str(NUM[s[1:]])
    if not s:
        return 1  # 卷一標題列在源裏漏了數字（0001-0213）
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


def label_key(label):
    m = re.match(r"^[卷巻](首?[一二三四五六七八九十百]+)", label)  # 殿本個別標題有「巻」異體
    return cn(m.group(1)) if m else None


def load_pua(path):
    t = {}
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        code = r["code"].split(":", 1)[1]
        if r["verdict"] == "char" and r.get("char"):
            t[code] = (r["char"], "pua-char", bool(r.get("nearest")))
        elif r["verdict"] == "multi" and r.get("chars"):
            t[code] = (r["chars"][0], "pua-multi", True)
    return t


def col_text(c, pua):
    """一列 → (字符串, [(原, 換, 類別)])；夾注 <右|左>。"""
    sub = []

    def fix(s):
        o = []
        for ch in s:
            if ch == IMG:
                sub.append(("以圖代字", "〓", "img"))
                o.append("〓")
            elif PUA.match(ch):
                code = "U+%04X" % ord(ch)
                if code in pua:
                    sub.append((code, pua[code][0], pua[code][1]))
                    o.append(pua[code][0])
                else:
                    sub.append((code, "〓", "pua-unmapped"))
                    o.append("〓")
            else:
                o.append(ch)
        return "".join(o)

    out = []
    for i, r in enumerate(c["runs"]):
        if r["t"] == "text":
            out.append(("　" * max(0, r.get("start", 0)) if i == 0 else "") + fix(r["s"]))
        else:
            out.append("<" + fix("".join(x[1] for x in r["r"])) + "|" + fix("".join(x[1] for x in r["l"])) + ">")
    return "".join(out), sub


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--pua-table", required=True)
    ap.add_argument("--book-text", required=True)
    ap.add_argument("--chapters", default="")
    a = ap.parse_args()
    pua = load_pua(a.pua_table)

    base = os.path.join(a.book_text, "Book", BOOK[-3], BOOK[-2], BOOK[-1], BOOK)
    ref = json.load(open(os.path.join(base, "default", "index.json"), encoding="utf-8"))
    chs = ref["chapters"]
    starts, prev = [], None
    for c in chs:
        keys = []
        for h in (h for h in c["headings"] if h["level"] == 1):
            k = label_key(h["label"])
            if k is None:  # 殿本 011 章卷二十一標題是亂碼，按前一卷＋1 推
                assert isinstance(prev, int), (c["n"], h["label"])
                k = prev + 1
            keys.append(k)
            prev = k
        starts.append(keys[0])
    assert starts[0] == "S1", starts[:3]

    # 展平：(record, half, colstr)；找卷首列
    cols = []  # (pb, text-with-pua-raw col dict, rec_id)
    heads = {}
    for v in range(1, 6):
        for l in open(os.path.join(a.raw, "%04d.jsonl" % v), encoding="utf-8"):
            r = json.loads(l)
            if r["book"]["id"] != 1 or not r["cols"]:
                continue
            for c in r["cols"]:
                idx = len(cols)
                cols.append((r, c))
                raw = "".join(x["s"] for x in c["runs"] if x["t"] == "text") if all(x["t"] == "text" for x in c["runs"]) else None
                if raw is not None and c["no"] % 9 == 0:
                    m = HEAD.match(raw)
                    if m:
                        k = cn(m.group(1))
                        heads.setdefault(k, idx)
    want = set(starts[1:])
    miss = [k for k in want if k not in heads]
    assert not miss, miss
    bounds = [0] + [heads[k] for k in starts[1:]] + [len(cols)]
    assert bounds == sorted(bounds), "章界不單調"

    only = {int(x) for x in a.chapters.split(",") if x}
    vdir = os.path.join(base, KEY)
    os.makedirs(vdir, exist_ok=True)
    out_chapters, all_pages, all_subst = [], [], []
    for n, c in enumerate(chs, 1):
        if only and n not in only:
            continue
        lo, hi = bounds[n - 1], bounds[n]
        fn = "%03d" % n
        lines, cur_pb, nsub = ["## " + c["title"], ""], None, 0
        for idx in range(lo, hi):
            r, col = cols[idx]
            pb = "%s%s" % (r["page"], "右" if col["no"] // 9 == 0 else "左")
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
        with open(os.path.join(vdir, fn + ".md"), "w", encoding="utf-8") as f:
            f.write(body)
        out_chapters.append({"n": n, "file": fn, "title": c["title"], "has_json": False, "md_len": len(body)})
        print(fn, c["title"], "列", len(lines) - 2, "換字", nsub, file=sys.stderr)
    with open(os.path.join(vdir, "pages.tsv"), "w", encoding="utf-8") as f:
        f.write("file\tline_no\tpb\n" + "\n".join(all_pages) + "\n")
    with open(os.path.join(vdir, "subst.tsv"), "w", encoding="utf-8") as f:
        f.write("file\tline_no\torig\tto\tkind\tsrc_id\n" + "\n".join(all_subst) + "\n")
    idx = {
        "version_label": "文淵閣四庫全書電子版（光盤本）",
        "edition_note": "文字來自文淵閣四庫全書電子版（光盤本），經殆知阁整理，非 OCR；無標點，一行一列，章節與 default（殿本）逐章同範圍。不改字、不統一異體；私用碼按碼表換最相近字、以圖代字寫〓，逐處見 subst.tsv。",
        "fetched_at": "2026-11-07",
        "guji_markdown": "0.2.0",
        "line_is_column": True,
        "revision": "0.1.0",
        "book_id": BOOK,
        "chapters": out_chapters,
        "source": {"name": "殆知阁・文淵閣四庫全書", "url": "https://sikuquanshu.daizhige.org/",
                   "license": "公有領域（底本）；電子版轉錄之授權站方未標示，待核",
                   "base_edition": "文淵閣四庫全書", "files": "data/0001-0005.jsonl"},
        "total_chapters": len(out_chapters),
        "text_quality": {"grade": "source"},
    }
    with open(os.path.join(vdir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
