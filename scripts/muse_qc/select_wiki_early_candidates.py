#!/usr/bin/env python3
"""#348 T16 muse 放量④候选抽段：09-30 之前入库、还没质检过的维基全文。

候选：`manifest.json` 里 `source == "wikisource"` 的版本，排除：
  - #327 质检过的 2,096 部（及其「候选清单」`t52t54_candidates_report.jsonl`）；
  - #327 补窗①新增的 31 部；
  - 十三經 13 部；
  - T15 批一 31 部。

抽样规则（沿用 #327）：每部抽首章第一段；章数 ≥3 的再按固定种子随机抽 1 章
的 1 段，避免跟首段撞同一个 chunk。分段沿用 `chunk_works.py` 的
`split_into_chunks`（约 3,000 字一段，按非空行累加，不切断整行）。

用法：
    python3 select_wiki_early_candidates.py --book-text /tmp/book-text \
        --exclude excluded_work_ids.json --out chunks.jsonl --seed 20261002 \
        --report candidates_report.jsonl
"""
import argparse
import json
import random
import sys
from pathlib import Path

from chunk_works import chapter_filename, split_into_chunks


def iter_wikisource_versions(book_text: Path):
    for mf in book_text.glob("Work/*/*/*/*/manifest.json"):
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        work_id = manifest.get("id")
        work_dir = mf.parent
        for v in manifest.get("versions", []):
            if v.get("source") != "wikisource":
                continue
            key = v.get("key")
            idx_path = work_dir / key / "index.json"
            yield work_id, key, idx_path, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-text", required=True, type=Path)
    ap.add_argument("--exclude", required=True, type=Path, help="排除的 work_id 列表（JSON array）")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()

    excluded = set(json.loads(args.exclude.read_text(encoding="utf-8")))
    rng = random.Random(args.seed)
    n_candidates = 0
    n_segments = 0
    n_errors = 0
    n_excluded = 0
    report_rows = []

    with args.out.open("w", encoding="utf-8") as out:
        for work_id, key, idx_path, version in iter_wikisource_versions(args.book_text):
            if work_id in excluded:
                n_excluded += 1
                continue
            try:
                index = json.loads(idx_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, FileNotFoundError):
                n_errors += 1
                continue

            work_title = index.get("version_label") or version.get("label")
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

            picks = []
            chapter0 = chapters[0]
            try:
                file0, chunks0 = chunk_chapter(chapter0)
            except (OSError, FileNotFoundError):
                n_errors += 1
                continue
            if chunks0:
                picks.append((chapter0, file0, chunks0, 1))

            if len(chapters) >= 3:
                ci = rng.randrange(len(chapters))
                chapter_r = chapters[ci]
                try:
                    file_r, chunks_r = chunk_chapter(chapter_r)
                except (OSError, FileNotFoundError):
                    chunks_r = None
                if chunks_r:
                    seq_r = rng.randrange(len(chunks_r)) + 1
                    if not (ci == 0 and seq_r == 1):
                        picks.append((chapter_r, file_r, chunks_r, seq_r))

            for chapter, chapter_file, chunks, seq in picks:
                chunk_lines = chunks[seq - 1]
                start_line = chunk_lines[0][0]
                end_line = chunk_lines[-1][0]
                text = "\n".join(t for _, t in chunk_lines)
                chunk_id = f"{work_id}/{key}/{chapter_file}#{seq}"
                rec = {
                    "chunk_id": chunk_id,
                    "work_id": work_id,
                    "work_title": work_title,
                    "chapter_title": chapter.get("title"),
                    "chapter_file": chapter_file,
                    "start_line": start_line,
                    "end_line": end_line,
                    "text": text,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_segments += 1

            report_rows.append((work_id, work_title, len(chapters), len(picks)))

    print(
        f"候选 {n_candidates} 部（排除 {n_excluded} 部，读取失败 {n_errors}），"
        f"抽出 {n_segments} 段，写入 {args.out}",
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
