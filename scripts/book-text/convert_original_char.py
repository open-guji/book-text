#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""book-text `original` 旧形态 → char／cord（T68 #417，规范 book-text docs/ORIGINAL.md）。

旧形态（10-06 以前）：`NNN.lines.md` 是真源，`NNN.pages.json`（cv 导出）里带字和框。
新形态：`NNN.char.json`（每格的字，guji-format 02）＋ `NNN.cord.json`（每格的框，不存字，01）；
lines.md、rich.md 改由 gen_original_derived.py 生成，放生成分支。

格位是 cv 口径（#419 定，见 original_char 模块头）：cord 从 pages.json 来，格位照抄它的 cv 锚点；
char 的字、分道、抬头挪抬、阙文取自 lines.md，格位和空列按读序取自 cord。
（cv 有自己的纯转换 `scripts/convert_pages_to_char_cord.py`，只读 pages.json；本脚本多拿 lines.md 交叉核。）

每册都核（任一不过就整批不落盘）：
  1. char 生成的 lines.md 与原 lines.md 逐字节一致；
  2. 分行稿与 pages.json 的页、有字的列、格数对得上，读序逐格字相同；
  3. 给了 --schema-dir 时，char、cord 都过 guji-format schema。

用法：
    convert_original_char.py <original 目录> [--chapter 002 …] --schema-dir <guji-format>/schemas          # 只核不写
    convert_original_char.py <original 目录> --schema-dir … --write            # 写 NNN.char.json、NNN.cord.json
    convert_original_char.py <original 目录> --schema-dir … --write --migrate  # 另把 index.json 改成 *_file 字段，
                                                                                # 并删掉旧的 lines.md、pages.json、rich.md、NNN.md
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import original_char as C  # noqa: E402
import original_version as OV  # noqa: E402

# 旧形态里、新形态 main 不再存的文件（生成物或旧真源）
OLD_SUFFIXES = ("lines.md", "pages.json", "rich.md", "md")
# index.json 章条目：旧字段 → 去掉；按 docs/ORIGINAL.md §二 用 *_file 声明
OLD_FIELDS = ("lines_file", "pages_file", "rich_file", "has_json")
FILE_FIELDS = ("char_file", "cord_file", "punct_file", "entity_file", "norm_file", "decision_file")


def load_schemas(schema_dir):
    if not schema_dir:
        return None
    import jsonschema
    out = {}
    for name in ("char", "cord"):
        with open(os.path.join(schema_dir, f"guji_{name}_v0.1.schema.json"), encoding="utf-8") as f:
            out[name] = jsonschema.Draft202012Validator(json.load(f))
    return out


def schema_errors(validator, obj, limit=5):
    errs = sorted(validator.iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(x) for x in e.absolute_path)}: {e.message}" for e in errs[:limit]], len(errs)


def convert_chapter(od, ch, book_id, version, schemas):
    """一册 → (char, cord, 报告行)；核不过抛 C.FormatError。"""
    stem = OV.chapter_file(ch)
    lines_path = os.path.join(od, f"{stem}.lines.md")
    pages_path = os.path.join(od, f"{stem}.pages.json")
    if not os.path.isfile(pages_path):
        raise C.FormatError(f"{stem}: 没有 {stem}.pages.json——cv 口径的格位、空列要从它取，只有分行稿转不了")
    text = OV.read_text(lines_path)
    vol = ch["n"]
    pj = OV.load_json(pages_path)
    cord = C.pages_to_cord(pj, book_id, vol)
    char = C.make_char(C.parse_lines_md(text, cord), book_id, vol, version)
    fig_path = os.path.join(od, ch["fig_file"]) if ch.get("fig_file") else None
    fig = OV.load_json(fig_path) if fig_path and os.path.isfile(fig_path) else None
    if C.render_lines(char, fig) != text:
        raise C.FormatError(f"{stem}: char 生成的 lines.md 与原文件不一致")
    old = [c for p in pj["pages"] for c in sorted(p["cells"], key=lambda c: c["o"] if isinstance(c["o"], int) else c["o"][0])]
    for k, (oc, (a, c)) in enumerate(zip(old, C.char_slots(char))):
        if oc.get("c") != c:
            raise C.FormatError(f"{stem}: 读序第 {k} 格 {a}：pages.json 是 {oc.get('c')!r}，分行稿是 {c!r}")
    if schemas:
        for name, obj in (("char", char), ("cord", cord)):
            errs, n = schema_errors(schemas[name], obj)
            if n:
                raise C.FormatError(f"{stem}.{name}.json 不过 schema（{n} 处）：" + "；".join(errs))
    n_cells = len(C.char_slots(char))
    n_cols = sum(len(p["columns"]) for p in char["pages"])
    n_blank = sum(1 for p in char["pages"] for c in p["columns"] if not c["cells"])
    dropped = sum(1 for p in pj["pages"] for r in p.get("regions") or [] if r.get("box") is None)
    row = (f"{stem}: {len(char['pages'])} 页 {n_cols} 列（空列 {n_blank}）{n_cells} 格；格位 cv 口径（取自 pages.json）；"
           f"lines.md 逐字节还原 ✓；字与 pages.json 逐格相同 ✓")
    if dropped:
        row += f"；{dropped} 个无版框区域（box 为 null）未收"
    if schemas:
        row += "；schema ✓"
    return char, cord, row


def migrate_index(index, stems_done, od):
    for ch in index.get("chapters") or []:
        stem = OV.chapter_file(ch)
        if stem not in stems_done:
            continue
        for k in OLD_FIELDS:
            ch.pop(k, None)
        files = {"char_file": f"{stem}.char.json"}
        if os.path.isfile(os.path.join(od, f"{stem}.cord.json")):
            files["cord_file"] = f"{stem}.cord.json"
        for line in ("punct", "entity", "norm", "decision"):
            if os.path.isfile(os.path.join(od, f"{stem}.{line}.json")):
                files[f"{line}_file"] = f"{stem}.{line}.json"
        rest = {k: v for k, v in ch.items() if k not in FILE_FIELDS}
        ch.clear()
        for k in ("n", "file", "title"):
            if k in rest:
                ch[k] = rest.pop(k)
        ch.update(files)
        ch.update(rest)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="original 目录")
    ap.add_argument("--chapter", action="append", help="只转这一册（NNN），可重复；不给就是 index.json 里全部有 lines.md 的册（还要有 pages.json）")
    ap.add_argument("--schema-dir", help="guji-format 的 schemas/ 目录；给了就做 schema 校验")
    ap.add_argument("--version", default="0.1.0", help="char 顶层 version（wip 上用 0.x；并 main 时用 bump_original --init 定 1.0.0）")
    ap.add_argument("--write", action="store_true", help="写 NNN.char.json、NNN.cord.json")
    ap.add_argument("--migrate", action="store_true", help="另改 index.json、删旧形态文件（须同时 --write）")
    a = ap.parse_args(argv)
    if a.migrate and not a.write:
        ap.error("--migrate 须同时 --write")
    od = os.path.abspath(a.dir)
    index_path = os.path.join(od, "index.json")
    index = OV.load_json(index_path)
    book_id = index.get("book_id") or os.path.basename(os.path.dirname(od))
    want = {c.zfill(3) for c in a.chapter} if a.chapter else None
    chapters = [ch for ch in index.get("chapters") or []
                if (want is None or OV.chapter_file(ch) in want)
                and os.path.isfile(os.path.join(od, f"{OV.chapter_file(ch)}.lines.md"))]
    if not chapters:
        print("错误：没有可转的册（要有 NNN.lines.md）", file=sys.stderr)
        return 1
    schemas = load_schemas(a.schema_dir)
    results = []
    try:
        for ch in chapters:
            results.append((OV.chapter_file(ch), ch) + convert_chapter(od, ch, book_id, a.version, schemas))
    except C.FormatError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    for _stem, _ch, _char, _cord, row in results:
        print(row)
    if not a.write:
        return 0
    for stem, ch, char, cord, _row in results:
        C.dump_compact(os.path.join(od, f"{stem}.char.json"), char)
        if cord is not None:
            C.dump_compact(os.path.join(od, f"{stem}.cord.json"), cord)
        if a.migrate:
            ch["text_version"] = char["version"]
    if a.migrate:
        stems = {r[0] for r in results}
        migrate_index(index, stems, od)
        OV.dump_json(index_path, index)
        for stem in sorted(stems):
            for suf in OLD_SUFFIXES:
                p = os.path.join(od, f"{stem}.{suf}")
                if os.path.isfile(p):
                    os.remove(p)
                    print(f"删 {os.path.basename(p)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
