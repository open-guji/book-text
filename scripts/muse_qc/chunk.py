#!/usr/bin/env python3
"""切段：把维基十三經 wikisource-01 全文按段落边界切成约 3000 字一段。

用法：
    python3 chunk.py --book-text /path/to/book-text --out chunks.jsonl

只读 book-text，不写。每段一条 JSON：
    {"chunk_id": "<work_id>/<章文件>#<序号>", "work_id": "…", "work_title": "…",
     "chapter_title": "…", "chapter_file": "NNN.md",
     "start_line": N, "end_line": N, "text": "…"}

"段落"取「非空行」为最小不可切单位：书内有的以空行分段（如儀禮），
有的每行自成一段（如論語逐章逐句、周易逐卦），逐行累加直到加下一行
会超过软上限才切，保证不切断任何一行。
"""
import argparse
import json
import sys
from pathlib import Path

TARGET_CHARS = 3000

# 十三經：work_id -> 书名（由 index.json 的 version_label 核对，13 部共 626 章，与任务书数字对上）
THIRTEEN_CLASSICS = {
    "d59ezakdey2o": "周易",
    "d59ezajmkjcw": "尚書",
    "d59ezak9zc3k": "詩經",
    "d59f1ioc6m0w": "周禮",
    "d59ezak3445c": "儀禮",
    "d59f1iofm800": "禮記",
    "d59ezak6jq4g": "春秋左氏傳",
    "d59f1ioj1tz4": "春秋公羊傳",
    "d59ezajtfrb4": "春秋穀梁傳",
    "d59f1iopaku8": "論語",
    "d59f1iosq6tc": "孝經",
    "d59f24mpohs2": "爾雅",
    "d59ezajwvda8": "孟子",
}


def find_work_dir(book_text: Path, work_id: str) -> Path:
    matches = list(book_text.glob(f"Work/*/*/*/{work_id}"))
    if len(matches) != 1:
        raise FileNotFoundError(f"work_id={work_id} 找到 {len(matches)} 个目录，预期 1 个")
    return matches[0]


def split_into_chunks(lines_with_no):
    """lines_with_no: [(line_no, text), ...]（已过滤空行）。按 TARGET_CHARS 累加切段。"""
    chunks = []
    cur = []
    cur_len = 0
    for line_no, text in lines_with_no:
        add_len = len(text) + 1
        if cur and cur_len + add_len > TARGET_CHARS:
            chunks.append(cur)
            cur = []
            cur_len = 0
        cur.append((line_no, text))
        cur_len += add_len
    if cur:
        chunks.append(cur)
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-text", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    total_chars = 0
    total_chunks = 0
    total_chapters = 0

    with args.out.open("w", encoding="utf-8") as out:
        for work_id, work_title in THIRTEEN_CLASSICS.items():
            work_dir = find_work_dir(args.book_text, work_id)
            ws_dir = work_dir / "full_text" / "wikisource-01"
            index = json.loads((ws_dir / "index.json").read_text(encoding="utf-8"))
            assert index["version_label"] == work_title, (
                f"{work_id} 实测 version_label={index['version_label']!r}，"
                f"与写死的书名 {work_title!r} 不符"
            )
            for chapter in index["chapters"]:
                total_chapters += 1
                chapter_file = chapter["file"]
                chapter_title = chapter["title"]
                raw = (ws_dir / chapter_file).read_text(encoding="utf-8")
                raw_lines = raw.split("\n")
                lines_with_no = [
                    (i + 1, ln) for i, ln in enumerate(raw_lines) if ln.strip() != ""
                ]
                chunks = split_into_chunks(lines_with_no)
                for seq, chunk_lines in enumerate(chunks, start=1):
                    start_line = chunk_lines[0][0]
                    end_line = chunk_lines[-1][0]
                    text = "\n".join(t for _, t in chunk_lines)
                    chunk_id = f"{work_id}/{chapter_file}#{seq}"
                    rec = {
                        "chunk_id": chunk_id,
                        "work_id": work_id,
                        "work_title": work_title,
                        "chapter_title": chapter_title,
                        "chapter_file": chapter_file,
                        "start_line": start_line,
                        "end_line": end_line,
                        "text": text,
                    }
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total_chunks += 1
                    total_chars += len(text)

    print(
        f"完成：{len(THIRTEEN_CLASSICS)} 部、{total_chapters} 章、"
        f"{total_chunks} 段、约 {total_chars} 字，写入 {args.out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
