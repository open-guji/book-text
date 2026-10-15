#!/usr/bin/env python3
"""#330 ③章题规整：扫全量 book-text，先核对「光秃题」统计，再跑三层规则，
报出规则解决数与剩余未解决数（用来判断是否 ≤1500、能不能接着跑 muse）。

「光秃」判定：空、纯数字、纯中文数字，或「卷/卷第/卷之」+数字/中文数字/
上中下首末尾終终，或「第…回/章/卷/篇/節/则/齣/出」——即只有编号、没有任何
章节内容信息的标题。

三层规则（严格顺序，逐字摘录，不改写不拼接）：
  1. rule:md_heading —— 章节 md 首行 `## …` 标题，比当前光秃题更有信息量。
  2. rule:page_title —— chapters[].page_title 最后一段，比当前光秃题更有信息量
     （且不等于书名本身——书名本身不算章节信息）。
  3. rule:kanripo_head —— Kanripo 正文开头「卷X」紧跟着的尾巴文字，要求尾巴
     本身不是纯数字/中文数字/常见卷册计数后缀（册/编/集/部/息+数字等），
     否则仍判不可信、不算解决（宁可漏不可编）。
"""
import glob
import json
import re
from pathlib import Path

BOOK_TEXT = Path("/tmp/book-text")

CN_NUM = "〇零一二三四五六七八九十百千萬万"
BALD_PATTERNS = [
    re.compile(r"^\d+$"),
    re.compile(rf"^卷\s*\d+$"),
    re.compile(rf"^卷\s*[{CN_NUM}]+$"),
    re.compile(r"^卷[上中下首末尾終终]$"),
    re.compile(rf"^卷第\s*\d+$"),
    re.compile(rf"^卷第\s*[{CN_NUM}]+$"),
    re.compile(rf"^卷之\s*\d+$"),
    re.compile(rf"^卷之\s*[{CN_NUM}]+$"),
    re.compile(rf"^第\s*\d+\s*(回|章|卷|篇|節|则|則|齣|出)$"),
    re.compile(rf"^第\s*[{CN_NUM}]+\s*(回|章|卷|篇|節|则|則|齣|出)$"),
    re.compile(rf"^[{CN_NUM}]+$"),
]

# kanripo_head 尾巴若只是换一种写法继续计数（册/编/集/部/息 + 数字），不算有信息量
TAIL_COUNTER_RE = re.compile(rf"^[册冊編编集集部息][{CN_NUM}\d]*$")
JUAN_HEAD_RE = re.compile(
    rf"卷(第|之)?\s*(\d+|[{CN_NUM}]+)|[上中下首末尾終终]卷"
)
# 尾巴若是「朝代+人名+撰/著/編/輯/校/纂/述/注/箋/疏/訂/錄/評/點/集」这类四库式
# 题署行（著录作者，不是章节标题），不算有信息量——抽查发现这是 kanripo_head
# 最大的假阳性来源（如「宋　王益之　撰」），必须滤掉。
ATTRIBUTION_RE = re.compile(
    r"^[\s　]*[宋元明清唐晉晋漢汉魏隋秦周齊齐梁陳陈後后北南][\s　]*[一-鿿]{1,6}"
    r"[\s　]*(撰|著|編|编|輯|辑|校|纂|述|注|箋|笺|疏|訂|订|錄|录|評|评|點|点|集|譯|译)$"
)


def is_bald(title):
    if title is None:
        return True
    t = title.strip()
    if t == "":
        return True
    return any(p.match(t) for p in BALD_PATTERNS)


def rule_md_heading(md_path, current_title):
    try:
        with open(md_path, encoding="utf-8") as f:
            first_line = f.readline().strip()
    except FileNotFoundError:
        return None
    inner = re.sub(r"^#+\s*", "", first_line).strip()
    if not inner or inner == current_title or is_bald(inner):
        return None
    return inner


def rule_page_title(page_title, current_title, work_title):
    if not page_title or "/" not in page_title:
        return None
    _, _, last_seg = page_title.rpartition("/")
    last_seg = last_seg.strip()
    if not last_seg or last_seg == current_title or is_bald(last_seg):
        return None
    if work_title and last_seg == work_title.strip():
        return None
    return last_seg


def rule_kanripo_head(md_path):
    try:
        with open(md_path, encoding="utf-8") as f:
            lines = [next(f, "").strip() for _ in range(10)]
    except FileNotFoundError:
        return None
    for line in lines:
        if not line or line.startswith("#"):
            continue
        m = JUAN_HEAD_RE.search(line)
        if not m:
            continue
        tail = line[m.end():].strip()
        tail = re.sub(r"^[　\s,，、]+", "", tail)
        if not tail:
            continue
        if TAIL_COUNTER_RE.match(tail):
            continue
        if is_bald(tail):
            continue
        if ATTRIBUTION_RE.match(tail):
            continue
        if re.match(rf"^[{CN_NUM}\d]+$", tail):
            continue
        return tail[:40]
    return None


def chapter_filename(ch):
    fname = ch.get("file", "")
    return fname if fname.endswith(".md") else fname + ".md"


def iter_bald_chapters():
    manifests = glob.glob(str(BOOK_TEXT / "Work/*/*/*/*/manifest.json"))
    for mf in manifests:
        d = json.load(open(mf, encoding="utf-8"))
        work_id = d.get("id")
        work_dir = Path(mf).parent
        for v in d.get("versions", []):
            key = v.get("key")
            source = v.get("source", "<none>")
            idx_path = work_dir / key / "index.json"
            try:
                idx = json.load(open(idx_path, encoding="utf-8"))
            except FileNotFoundError:
                continue
            chapters = idx.get("chapters")
            if not chapters:
                continue
            work_title = v.get("label") or idx.get("version_label")
            for ch in chapters:
                title = ch.get("title")
                if not is_bald(title):
                    continue
                yield {
                    "work_id": work_id,
                    "key": key,
                    "source": source,
                    "work_title": work_title,
                    "n": ch.get("n"),
                    "file": ch.get("file"),
                    "current_title": title,
                    "page_title": ch.get("page_title"),
                    "work_dir": work_dir,
                }


def main():
    from collections import Counter

    resolved_by = Counter()
    unresolved = 0
    unresolved_by_source = Counter()
    total_bald = 0
    work_ids_bald = set()
    out_rows = []

    for item in iter_bald_chapters():
        total_bald += 1
        work_ids_bald.add(item["work_id"])
        md_path = item["work_dir"] / item["key"] / chapter_filename(item)

        proposed = None
        basis = "none"

        r1 = rule_md_heading(md_path, item["current_title"])
        if r1:
            proposed, basis = r1, "rule:md_heading"
        else:
            r2 = rule_page_title(item["page_title"], item["current_title"], item["work_title"])
            if r2:
                proposed, basis = r2, "rule:page_title"
            elif item["source"] == "kanripo":
                r3 = rule_kanripo_head(md_path)
                if r3:
                    proposed, basis = r3, "rule:kanripo_head"

        if proposed:
            resolved_by[basis] += 1
        else:
            unresolved += 1
            unresolved_by_source[item["source"]] += 1

        out_rows.append({
            "id": f'{item["work_id"]}/{item["key"]}',
            "key": item["key"],
            "n": item["n"],
            "file": item["file"],
            "current_title": item["current_title"],
            "proposed_title": proposed,
            "basis": basis,
            "work_id": item["work_id"],
            "source": item["source"],
        })

    print(f"扫到光秃章：{total_bald}（涉及 {len(work_ids_bald)} 部）")
    print("规则命中：", dict(resolved_by))
    print(f"规则未解决剩余：{unresolved}")
    print("未解决按来源：", dict(unresolved_by_source))

    # 明细是全量 8 万+ 行的大文件，按仓库规矩只放 scratchpad，不进 git。
    out_path = Path(
        "/tmp/claude-0/-home-user-overview/"
        "f6f55dc5-48c0-561f-a917-1a7f92fce755/scratchpad/chapter_titles/"
        "chapter_rule_scan_raw.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"明细写入 {out_path}")


if __name__ == "__main__":
    main()
