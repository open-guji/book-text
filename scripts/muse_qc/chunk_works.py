#!/usr/bin/env python3
"""切段（通用版）：把任意一批 book-text Work 的全文按段落边界切成约 3,000 字
一段。是 `chunk.py`（写死十三經）抽出来的通用版，供以后每个抓取道收工前的
批次复用（见 README「常规用法」）。

用法：
    python3 chunk_works.py --book-text /path/to/book-text --manifest manifest.json --out chunks.jsonl

manifest.json 形如 {"work_id": "书名", ...}；书名只用来核对 `index.json` 的
`version_label`（对不上就报错，不静默吃掉），不影响切段本身。

10-01 按 book-text #307 新结构改：每个 Work 目录下是 `manifest.json`
（`versions[]`，每项 `key`/`source`/...）＋若干 `<key>/`版本目录（`index.json`
＋`NNN.md`，`index.json` 的 `chapters[].file` 不带 `.md` 后缀）。旧结构
`full_text/<source>/` 仍兼容（读不到 manifest.json 时退回旧路径）。
"""
import argparse
import json
import sys
from pathlib import Path

TARGET_CHARS = 3000


def find_work_dir(book_text: Path, work_id: str) -> Path:
    matches = list(book_text.glob(f"Work/*/*/*/{work_id}"))
    if len(matches) != 1:
        raise FileNotFoundError(f"work_id={work_id} 找到 {len(matches)} 个目录，预期 1 个")
    return matches[0]


def find_version_dir(book_text: Path, work_id: str, version_key: str | None, source_filter: str) -> Path:
    """新结构走 manifest.json 找版本目录；manifest.json 不存在就退回旧的
    `full_text/<source_filter>/` 路径（兼容还没迁移的 Work）。"""
    work_dir = find_work_dir(book_text, work_id)
    manifest_path = work_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        versions = manifest.get("versions", [])
        if version_key:
            match = next((v for v in versions if v["key"] == version_key), None)
        else:
            wiki = [v for v in versions if v.get("source") == source_filter]
            match = wiki[0] if wiki else (versions[0] if versions else None)
        if match is None:
            raise FileNotFoundError(f"{work_id} 的 manifest.json 里找不到匹配版本（source={source_filter}）")
        return work_dir / match["key"]
    return work_dir / "full_text" / (version_key or "wikisource-01")


def chapter_filename(chapter: dict) -> str:
    """新结构 `chapters[].file` 不带 `.md` 后缀，旧结构带；统一补齐。"""
    f = chapter["file"]
    return f if f.endswith(".md") else f + ".md"


def split_into_chunks(lines_with_no):
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
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--source", default="wikisource-01", help="旧结构：全文来源子目录名")
    ap.add_argument("--version-key", default=None, help="新结构：manifest.json 里版本的 key（不填按 source-filter 自动挑）")
    ap.add_argument("--source-filter", default="wikisource", help="新结构：manifest.json versions[].source 匹配值，自动挑版本用")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    total_chars = 0
    total_chunks = 0
    total_chapters = 0
    per_work_stats = []

    with args.out.open("w", encoding="utf-8") as out:
        for work_id, work_title in manifest.items():
            ws_dir = find_version_dir(args.book_text, work_id, args.version_key, args.source_filter)
            index = json.loads((ws_dir / "index.json").read_text(encoding="utf-8"))
            assert index["version_label"] == work_title, (
                f"{work_id} 实测 version_label={index['version_label']!r}，"
                f"与 manifest 写的书名 {work_title!r} 不符"
            )
            work_chunks = 0
            work_chars = 0
            for chapter in index["chapters"]:
                total_chapters += 1
                chapter_file = chapter_filename(chapter)
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
                    work_chunks += 1
                    work_chars += len(text)
            per_work_stats.append((work_id, work_title, index["total_chapters"], work_chunks, work_chars))

    print(
        f"完成：{len(manifest)} 部、{total_chapters} 章、"
        f"{total_chunks} 段、约 {total_chars} 字，写入 {args.out}",
        file=sys.stderr,
    )
    for wid, title, n_ch, n_chunks, n_chars in sorted(per_work_stats, key=lambda r: r[3]):
        print(f"  {title}（{wid}）：{n_ch} 章 → {n_chunks} 段，约 {n_chars} 字", file=sys.stderr)


if __name__ == "__main__":
    main()
