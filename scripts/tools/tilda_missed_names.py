#!/usr/bin/env python3
"""#543 ②专名漏标候选（只读）：在 char 字符流里找「未被任何实体覆盖」的书名／人名候选。

用法：tilda_missed_names.py <book default 目录> <输出目录>
读：NNN.char.json（字符流）、NNN.entity.json（已有实体）。不写 book-text。
输出：候选-NNN.json（机器可读）与 候选-NNN.md（人读，含 ±10 字上下文）。

三类候选，都只是建议，不是判定：
- unmatched：实体里未命中（status≠matched）的文本，在别处又出现且那处未被任何实体覆盖；
- title：「…撰／著／纂／注」前 2–12 个汉字，且未被实体覆盖（《》外的书名模式；char 流无标点，噪声大，仅供人工筛）；
- person：「號X」中的人名模式，未被实体覆盖（只认「號」，「字」因与普通词「字句」「字音」混淆而不用，人名需人工判断）。
"""
import glob, json, os, re, sys

CJK = r"[一-鿿㐀-䶿]"
TITLE_RE = re.compile(rf"({CJK}{{2,12}})(?=[撰著纂注])")  # char 流不含标点，无法按标点切；噪声大，仅供人工筛
PERSON_RE = re.compile(rf"號({CJK}{{1,3}})")  # 只认「號X」；「X字Y」与「字句」「字音」等普通词太吵，不用


def char_stream(path):
    """按页、列、格顺序拼出字符流，返回 (文本, 每个字符的 cell 锚点列表)。"""
    pages = json.load(open(path, encoding="utf-8")).get("pages", [])
    text, anchors = [], []
    for pg in pages:
        for col in pg.get("columns", []):
            for cell in col.get("cells", []):
                text.append(cell.get("c", ""))
                anchors.append(cell.get("a", ""))
    return "".join(text), anchors


def covered_mask(n, ents, text):
    """把实体的字面文本在字符流中的所有出现位置标为已覆盖。"""
    mask = [False] * n
    for e in ents:
        s = e.get("text") or ""
        if not s:
            continue
        i = text.find(s)
        while i != -1:
            for k in range(i, i + len(s)):
                mask[k] = True
            i = text.find(s, i + 1)
    return mask


def context(text, i, j, w=10):
    return text[max(0, i - w): i] + "【" + text[i: j] + "】" + text[j: j + w]


def scan(d, ch):
    text, anchors = char_stream(os.path.join(d, ch + ".char.json"))
    ents = json.load(open(os.path.join(d, ch + ".entity.json"), encoding="utf-8")).get("entities", [])
    mask = covered_mask(len(text), ents, text)
    out = []

    seen_unmatched = {}
    for e in ents:
        if (e.get("target") or {}).get("status") != "matched":
            seen_unmatched.setdefault(e.get("text", ""), (e.get("type"), (e.get("target") or {}).get("status")))
    for s, (typ, st) in seen_unmatched.items():
        if not s:
            continue
        i = text.find(s)
        while i != -1:
            if not any(mask[i: i + len(s)]):
                out.append({"kind": "unmatched", "text": s, "type": typ, "status": st, "pos": i,
                            "anchor": anchors[i] if i < len(anchors) else "", "ctx": context(text, i, i + len(s))})
            i = text.find(s, i + 1)

    for kind, rx in (("title", TITLE_RE), ("person", PERSON_RE)):
        for m in rx.finditer(text):
            g = m.group(1)
            i, j = m.span(1)
            if i < 0 or any(mask[i:j]):
                continue
            out.append({"kind": kind, "text": g, "type": None, "status": None, "pos": i,
                        "anchor": anchors[i] if i < len(anchors) else "", "ctx": context(text, i, j)})
    out.sort(key=lambda r: r["pos"])
    return out


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    d, outdir = argv[1], argv[2]
    os.makedirs(outdir, exist_ok=True)
    for ch in sorted(os.path.basename(p)[: -len(".char.json")] for p in glob.glob(os.path.join(d, "*.char.json"))):
        if not os.path.isfile(os.path.join(d, ch + ".entity.json")):
            continue
        rows = scan(d, ch)
        json.dump(rows, open(os.path.join(outdir, f"候选-{ch}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        with open(os.path.join(outdir, f"候选-{ch}.md"), "w", encoding="utf-8") as f:
            f.write(f"# 专名漏标候选 {ch}（只读，建议非判定）\n\n共 {len(rows)} 条\n\n")
            f.write("| 类 | 文本 | 原类型 | 原状态 | 锚点 | 上下文 |\n|---|---|---|---|---|---|\n")
            for r in rows:
                f.write(f"| {r['kind']} | {r['text']} | {r['type'] or ''} | {r['status'] or ''} | {r['anchor']} | {r['ctx']} |\n")
        print(f"{ch}: {len(rows)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
