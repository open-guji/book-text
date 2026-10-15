#!/usr/bin/env python3
"""issue #328 第②步：给 1,138 部多版本 Work 的各版本补版本名候选。

三条规则，规则得不出的留给 muse（见 version_prompt_template.txt／version_schema.json）：
1. Kanripo 版本：manifest.json 的 versions[].source=="kanripo"；读该版本自己的
   index.json 的 source.base_edition，查 KANRIPO_EDITION_MAP。代码没收录的
   （目前只有 NFKB 1 例查无实据）不猜，留 null。
2. 維基文庫版本：从 manifest.json 的 source_url 解码出 page_title，取结尾的
   「(…)」/「（…）」括号内容当版本名。取不到（多数是书名本身没有括号后缀）的
   留给 muse。
3. 整理本（collated）版本：目前实测 17 个 collated 组合的 `collated_edition/index.json`
   都是 catalog/anthology 结构，没有 `edition` 字段——没数据就不编，留 null。

用法：
    python3 select_version_labels.py --book-text /path/to/book-text \
        --out version_labels_candidates.jsonl --muse-batch muse_batch.jsonl
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

KANRIPO_EDITION_MAP = {
    "WYG": "文淵閣四庫全書本",
    "SBCK": "四部叢刊本",
    "HFL": "正統道藏·涵芬樓本",
    "T": "大正新脩大藏經本（CBETA）",
    "X": "卍續藏經本（CBETA）",
    "J": "嘉興藏本（CBETA）",
    "C": "中華大藏經本（CBETA）",
    # NFKB：仅 1 例（全唐文），仓库无 README、查无实据，不猜，留 null。
}

TRAILING_PAREN_RE = re.compile(r"[（(]([^()（）]{1,30})[）)]$")


def find_multiversion_works(book_text: Path):
    for manifest_path in book_text.glob("Work/*/*/*/*/manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        versions = manifest.get("versions", [])
        if len(versions) >= 2:
            yield manifest_path.parent, manifest["id"], versions


def wiki_title_from_source_url(source_url: str) -> str | None:
    if not source_url or "/wiki/" not in source_url:
        return None
    return unquote(source_url.split("/wiki/")[-1]).replace("_", " ")


def chapter_excerpt(work_dir: Path, key: str, max_chars: int = 1500):
    index_path = work_dir / key / "index.json"
    if not index_path.exists():
        return None, None
    index = json.loads(index_path.read_text(encoding="utf-8"))
    chapters = index.get("chapters", [])
    if not chapters:
        return index, None
    first = chapters[0]
    f = first["file"]
    chapter_file = f if f.endswith(".md") else f + ".md"
    chapter_path = work_dir / key / chapter_file
    if not chapter_path.exists():
        return index, None
    text = chapter_path.read_text(encoding="utf-8")
    return index, text[:max_chars]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-text", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--muse-batch", required=True, type=Path)
    args = ap.parse_args()

    rows = []
    muse_batch = []
    stats = {"rule:kanripo_base": 0, "rule:wiki_title": 0, "none": 0, "muse_pending": 0}

    for work_dir, work_id, versions in find_multiversion_works(args.book_text):
        for v in versions:
            key = v["key"]
            source = v.get("source", "")
            current_label = v.get("label", "")
            row = {
                "id": work_id,
                "key": key,
                "source": source,
                "current_label": current_label,
                "edition_label": None,
                "basis": "none",
                "evidence": None,
            }
            if source == "kanripo":
                index, _ = chapter_excerpt(work_dir, key, max_chars=1)
                code = (index or {}).get("source", {}).get("base_edition") if index else None
                if code and code in KANRIPO_EDITION_MAP:
                    row["edition_label"] = KANRIPO_EDITION_MAP[code]
                    row["basis"] = "rule:kanripo_base"
                    row["evidence"] = f"source.base_edition={code}"
                    stats["rule:kanripo_base"] += 1
                else:
                    row["evidence"] = f"未知或缺失 base_edition={code!r}，不猜"
                    stats["none"] += 1
            elif source == "wikisource":
                title = wiki_title_from_source_url(v.get("source_url", ""))
                m = TRAILING_PAREN_RE.search(title) if title else None
                if m:
                    row["edition_label"] = m.group(1)
                    row["basis"] = "rule:wiki_title"
                    row["evidence"] = title
                    stats["rule:wiki_title"] += 1
                else:
                    index, excerpt = chapter_excerpt(work_dir, key)
                    edition_note = (index or {}).get("edition_note", "")
                    if excerpt is None:
                        row["evidence"] = "首章读取失败，跳过 muse"
                        stats["none"] += 1
                    else:
                        book_title = (index or {}).get("version_label") or work_id
                        muse_batch.append({
                            "chunk_id": f"{work_id}/{key}",
                            "work_title": book_title,
                            "chapter_title": edition_note or "（无 edition_note）",
                            "text": excerpt,
                        })
                        row["basis"] = "muse"
                        stats["muse_pending"] += 1
            elif source == "collated":
                row["evidence"] = "collated_edition/index.json 无 edition 字段（实测 catalog/anthology 结构）"
                stats["none"] += 1
            else:
                row["evidence"] = f"未知 source={source!r}"
                stats["none"] += 1
            rows.append(row)

    with args.out.open("w", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    with args.muse_batch.open("w", encoding="utf-8") as out:
        for r in muse_batch:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"总版本行数 {len(rows)}；{stats}", file=sys.stderr)
    print(f"muse 待跑 {len(muse_batch)} 条，写入 {args.muse_batch}", file=sys.stderr)


if __name__ == "__main__":
    main()
