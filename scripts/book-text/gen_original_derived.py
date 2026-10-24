#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 book-text `original` 的真源生成 lines.md、rich.md（T68 #417，规范 book-text docs/ORIGINAL.md §四）。

    NNN.lines.md ← NNN.char.json
    NNN.rich.md  ← NNN.char.json ＋ NNN.punct.json（＋ NNN.entity.json）
生成物只放生成分支（`derived`），main 不存；index.json 该章加 `lines_file`、`rich_file`。
norm 层还没有条目格式（四庫 vol02、vol03 的 norm 都是空表），rich 暂不套 norm。

标点层还是旧格式（条目没有 anchor 格位）、或标点／实体锚点与 char 对不上的册不出 rich，
只出 lines，并在输出里说明（生成分支上该章就没有 rich_file）。

用法：
    gen_original_derived.py <book-text 根目录 | 条目目录 | original 目录>            # 写生成物、改 index.json
    gen_original_derived.py <…> --check                                           # 只比对：生成结果与盘上现有文件逐字节比
怎么推到 derived 分支见 publish_original_derived.sh。
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import original_char as C  # noqa: E402
import original_version as OV  # noqa: E402


def _entry_original_dirs(entry_dir):
    """条目目录里的 original 版本目录：manifest 声明 is_original 的版本（key 可以是 default），或旧写法的 original/。"""
    out = []
    try:
        for v in OV.load_json(os.path.join(entry_dir, "manifest.json")).get("versions", []):
            d = os.path.join(entry_dir, v.get("key", ""))
            if v.get("is_original") and os.path.isfile(os.path.join(d, "index.json")):
                out.append(d)
    except (OSError, ValueError):
        pass
    legacy = os.path.join(entry_dir, "original")
    if os.path.isfile(os.path.join(legacy, "index.json")) and legacy not in out:
        out.append(legacy)
    return out


def find_original_dirs(path):
    path = os.path.abspath(path)
    if os.path.isfile(os.path.join(path, "index.json")) and OV.is_original_dir(path):
        return [path]
    if os.path.isfile(os.path.join(path, "manifest.json")):
        return _entry_original_dirs(path)
    # book-text 根：Book|Work/<c1>/<c2>/<c3>/<id>/manifest.json（只有 original 才会命中）
    found = []
    for kind in ("Book", "Work"):
        entries = {os.path.dirname(m) for pat in ("manifest.json", os.path.join("original", "index.json"))
                   for m in glob.glob(os.path.join(path, kind, "*", "*", "*", "*", pat))}
        entries = {os.path.dirname(e) if os.path.basename(e) == "original" else e for e in entries}
        for e in sorted(entries):
            found += _entry_original_dirs(e)
    return found


def gen_chapter(od, ch):
    """一册 → {文件名: 内容}、说明。"""
    stem = OV.chapter_file(ch)
    char_name = ch.get("char_file") or f"{stem}.char.json"
    char_path = os.path.join(od, char_name)
    if not os.path.isfile(char_path):
        return {}, f"{stem}: 没有 {char_name}，跳过"
    char = OV.load_json(char_path)
    fig_path = os.path.join(od, ch["fig_file"]) if ch.get("fig_file") else None
    fig = OV.load_json(fig_path) if fig_path and os.path.isfile(fig_path) else None    # 有图：写 :tu／::tu
    out = {f"{stem}.lines.md": C.render_lines(char, fig)}
    notes = [f"{stem}: lines.md"]
    punct_path = os.path.join(od, ch.get("punct_file") or f"{stem}.punct.json")
    if os.path.isfile(punct_path):
        punct = OV.load_json(punct_path)
        if any(not p.get("anchor") for p in punct.get("punctuations") or []):
            notes.append("rich 未出（标点层是旧格式，有条目没有 anchor 格位）")
        else:
            ent_path = os.path.join(od, ch.get("entity_file") or f"{stem}.entity.json")
            entity = OV.load_json(ent_path) if os.path.isfile(ent_path) else None
            try:
                out[f"{stem}.rich.md"] = C.render_rich(char, punct, entity, fig)
                notes.append("rich.md" + ("（含实体）" if entity else "（无实体层）"))
            except C.FormatError as e:
                # 伴生层还没跟上文本（锚点对不上）：只出 lines，等标点、实体修好再出 rich
                notes.append(f"rich 未出（标点／实体锚点与 char 对不上：{e}）")
    else:
        notes.append("没有标点层，不出 rich")
    return out, "、".join(notes)


def process(od, check):
    index_path = os.path.join(od, "index.json")
    index = OV.load_json(index_path)
    before = json.dumps(index, ensure_ascii=False)
    reports, diffs = [], []
    for ch in index.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        try:
            files, note = gen_chapter(od, ch)
        except C.FormatError as e:
            reports.append(f"{od}: 册 {OV.chapter_file(ch)} 生成失败：{e}")
            diffs.append(OV.chapter_file(ch))
            continue
        reports.append(f"{od}: {note}")
        for name, text in files.items():
            p = os.path.join(od, name)
            if check:
                old = OV.read_text(p) if os.path.isfile(p) else None
                if old != text:
                    diffs.append(name)
                    reports.append(f"  {name}: " + ("盘上没有" if old is None else "与盘上现有文件不一致"))
                else:
                    reports.append(f"  {name}: 逐字节一致")
            else:
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
        if not check and files:          # 没有 char.json 的册（旧形态）index 一字不动
            for kind in ("lines", "rich"):
                name = f"{OV.chapter_file(ch)}.{kind}.md"
                if name in files:
                    ch[f"{kind}_file"] = name
                else:
                    ch.pop(f"{kind}_file", None)
    if not check and json.dumps(index, ensure_ascii=False) != before:
        OV.dump_json(index_path, index)
    return reports, diffs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="book-text 根目录、条目目录或 original 目录")
    ap.add_argument("--check", action="store_true", help="只比对不写")
    a = ap.parse_args(argv)
    dirs = find_original_dirs(a.path)
    if not dirs:
        print("没有找到 original 目录", file=sys.stderr)
        return 1
    bad = []
    for od in dirs:
        reports, diffs = process(od, a.check)
        for r in reports:
            print(r)
        bad += diffs
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
