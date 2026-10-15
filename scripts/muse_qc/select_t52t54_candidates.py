#!/usr/bin/env python3
"""T52/T54 候选抽段：issue #327 第 1 步。

候选：version 的 `index.json` 里 `edition_note` 含「T52」或「T54」、`source.name`
是維基文庫的 Work（book-text #307 新结构，每个条目是
`Work/<c1>/<c2>/<c3>/<id>/<key>/index.json`）。

抽样规则（issue 原文）：每部抽首章的第一段；章数 ≥3 的再按固定种子随机抽
1 章的 1 段。分段规则沿用 `chunk_works.py` 的 `split_into_chunks`（约 3,000 字
一段，按非空行累加，不切断整行）。

用法：
    python3 select_t52t54_candidates.py --book-text /path/to/book-text --out chunks.jsonl --seed 20261001
"""
import argparse
import json
import random
import sys
from pathlib import Path

from chunk_works import chapter_filename, split_into_chunks


def find_candidate_index_files(book_text: Path):
    for p in book_text.glob("Work/*/*/*/*/*/index.json"):
        yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-text", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--report", type=Path, default=None, help="候选清单（work_id/title/章数），供核对用")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    n_candidates = 0
    n_segments = 0
    n_errors = 0
    report_rows = []

    with args.out.open("w", encoding="utf-8") as out:
        for idx_path in find_candidate_index_files(args.book_text):
            try:
                index = json.loads(idx_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                n_errors += 1
                continue

            note = index.get("edition_note", "")
            if "T52" not in note and "T54" not in note:
                continue
            source = index.get("source", {})
            if source.get("name") != "維基文庫":
                continue

            work_id = index.get("work_id")
            work_title = index.get("version_label")
            chapters = index.get("chapters", [])
            if not chapters:
                n_errors += 1
                continue
            n_candidates += 1
            ws_dir = idx_path.parent

            def chunk_chapter(chapter):
                chapter_file = chapter_filename(chapter)
                raw = (ws_dir / chapter_file).read_text(encoding="utf-8")
                raw_lines = raw.split("\n")
                lines_with_no = [
                    (i + 1, ln) for i, ln in enumerate(raw_lines) if ln.strip() != ""
                ]
                return chapter_file, split_into_chunks(lines_with_no)

            picks = []  # (chapter, chapter_file, chunks, seq)
            chapter0 = chapters[0]
            file0, chunks0 = chunk_chapter(chapter0)
            if chunks0:
                picks.append((chapter0, file0, chunks0, 1))

            if len(chapters) >= 3:
                ci = rng.randrange(len(chapters))
                chapter_r = chapters[ci]
                file_r, chunks_r = chunk_chapter(chapter_r)
                if chunks_r:
                    seq_r = rng.randrange(len(chunks_r)) + 1
                    # 避免跟首段撞同一个 chunk
                    if not (ci == 0 and seq_r == 1):
                        picks.append((chapter_r, file_r, chunks_r, seq_r))

            for chapter, chapter_file, chunks, seq in picks:
                chunk_lines = chunks[seq - 1]
                start_line = chunk_lines[0][0]
                end_line = chunk_lines[-1][0]
                text = "\n".join(t for _, t in chunk_lines)
                chunk_id = f"{work_id}/{ws_dir.name}/{chapter_file}#{seq}"
                rec = {
                    "chunk_id": chunk_id,
                    "work_id": work_id,
                    "work_title": work_title,
                    "chapter_title": chapter["title"],
                    "chapter_file": chapter_file,
                    "start_line": start_line,
                    "end_line": end_line,
                    "text": text,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_segments += 1

            report_rows.append((work_id, work_title, len(chapters), len(picks)))

    print(
        f"候选 {n_candidates} 部（跳过/读取失败 {n_errors}），抽出 {n_segments} 段，写入 {args.out}",
        file=sys.stderr,
    )
    if args.report:
        with args.report.open("w", encoding="utf-8") as rf:
            for row in report_rows:
                rf.write(json.dumps(
                    {"work_id": row[0], "work_title": row[1], "chapters": row[2], "picked": row[3]},
                    ensure_ascii=False,
                ) + "\n")


if __name__ == "__main__":
    main()
