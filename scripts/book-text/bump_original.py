#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 book-text 某册 `original` 的一条线升版本号（T67 #400）。

规范：docs/design/2026-10-文本版本号与仓库流程.md（v2）。
只管 `original`（本项目从书影自做的文本）；维基、Kanripo、识典的转录不跟踪版本。

三条线各自 MAJOR.MINOR.PATCH（文件体系见 book-text docs/ORIGINAL.md）：
    text    original/NNN.char.json 顶层 version（index.json 的 text_version 同步）
    punct   original/NNN.punct.json 顶层 version（index.json 的 punct_version 同步）
    entity  original/NNN.entity.json 顶层 version（index.json 的 entity_version 同步）
每升一次，在 original/CHANGES.md 追加一行：日期｜册｜线｜旧→新｜说明｜PR。

升哪一级（以一次 PR 为单位）：一册改动 ≤50 处、且逐处改的算 patch；超过，或按规则
成批改的（整批字符转换、整册重跑、新增类型……）算 minor。拿不准选 minor。
major 是质量等级（1 可用／2 出版级／3 定本），要验收记录和用户点头，本脚本不升。

文本线升级后，自动核标点、实体两层的锚点校验字：
    全对得上 → 只把它们的 text_version 跟过去，不升它们的版本；
    有对不上 → 不动，列出来；修好以后对那条线再跑一次本脚本（会顺带把 text_version 跟上）。

用法：
    bump_original.py <original 目录或其上层条目目录> --line text --level patch --note "改 3 字" --pr 12
    bump_original.py <目录> --line punct --level minor --note "整册重跑标点" [--chapter 002]
    bump_original.py <目录> --init --note "四庫 vol02 首次并 main" --pr 12   # 三线都定为 1.0.0
    bump_original.py <目录> --init --version 0.1.0 --note "粗校完" --pr 12   # 文本线 0.1.0，proofing=true；有标点、实体稿的也定 0.1.0
    bump_original.py <目录> --init --line punct --note "标点首版" --pr 12    # 文本已入 main 后新开一条伴生线（文本 0.x 时 0.1.0，≥1 时 1.0.0）
    bump_original.py <目录> --proofing off --note "精校完" --pr 12           # 只改校对状态开关（见下）
文本线可停在 0.x（粗校完 0.1.0，之后 patch／minor 照升）；0.x 阶段章条目必须 proofing: true（F-OV-06）。
10-18 用户定（GUJI-240）：文本 0.x 时也可以加标点、实体，伴生层从 0.1.0 起、照常 patch／minor；
伴生层 major 不得高于文本线，所以文本 0.x 时伴生层也是 0.x。精校完升 1.0.0 是 major：手工改 char.json 版本和验收记录，
再 `--proofing off`；伴生层 0.x → 1.0.0 同样手工、附验收记录，可晚于文本。vol02／03 这类按旧定义已是 1.0.0、补走精校的，用 `--proofing on`。
不给 --chapter 时作用于 index.json 里全部的册。
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import original_version as OV  # noqa: E402

CHANGES_HEADER = (
    "# original 版本日志\n\n"
    "规范见本仓 `docs/design/2026-10-文本版本号与仓库流程.md`。\n\n"
    "| 日期 | 册 | 线 | 旧→新 | 说明 | PR |\n"
    "|---|---|---|---|---|---|\n"
)
LINE_NAME = {"text": "文本", "punct": "标点", "entity": "实体"}


class BumpError(Exception):
    pass


def resolve_original(path):
    path = os.path.abspath(path)
    if OV.is_original_dir(path):
        od = path
    elif os.path.isdir(os.path.join(path, "original")):
        od = os.path.join(path, "original")
    else:
        raise BumpError(f"{path} 不是 original 目录，下面也没有 original/（只有 original 跟踪版本）")
    if not os.path.isfile(os.path.join(od, "index.json")):
        raise BumpError(f"{od} 缺 index.json")
    return od


def select_chapters(index, chapters):
    chs = [c for c in index.get("chapters") or [] if isinstance(c, dict)]
    if not chs:
        raise BumpError("index.json 没有 chapters")
    if not chapters:
        return chs
    want = {c.zfill(3) for c in chapters}
    got = [c for c in chs if OV.chapter_file(c) in want]
    missing = want - {OV.chapter_file(c) for c in got}
    if missing:
        raise BumpError(f"index.json 里没有这些册：{sorted(missing)}")
    return got


def append_changes(od, rows):
    p = os.path.join(od, "CHANGES.md")
    new = not os.path.exists(p)
    with open(p, "a", encoding="utf-8") as f:
        if new:
            f.write(CHANGES_HEADER)
        for r in rows:
            f.write("| " + " | ".join(x.replace("|", "\\|") for x in r) + " |\n")


def _book_id(od):
    return os.path.basename(os.path.dirname(od))


def _dump(path, obj):
    # char.json 一格一行（convert_original_char.py 写出的样子），别的 json 照旧
    (OV.dump_compact if path.endswith(".char.json") else OV.dump_json)(path, obj)


def _pr(pr):
    return f"#{pr}" if pr else ""


def do_init(od, chapters, note, pr, today, version="1.0.0"):
    index = OV.load_json(os.path.join(od, "index.json"))
    rows, pending = [], []
    for ch in select_chapters(index, chapters):
        stem = OV.chapter_file(ch)
        char_path = OV.companion_path(od, stem, "text")
        if not os.path.isfile(char_path):
            raise BumpError(f"册 {stem} 没有 {stem}.char.json")
        char = OV.load_json(char_path)
        old = OV.parse_version(char.get("version"))
        if old and old[0] >= 1:
            raise BumpError(f"册 {stem} 已是 {char['version']}，不能再 init")
        char["version"] = version
        pending.append((char_path, char))
        ch["text_version"] = version
        lines = ["text"]
        if version == "0.1.0":
            ch["proofing"] = True
        for line in ("punct", "entity"):
            cf = OV.companion_path(od, stem, line)
            if not os.path.isfile(cf):
                continue
            cd = OV.load_json(cf)
            cd["version"] = version
            cd["text_version"] = version
            pending.append((cf, cd))
            ch[f"{line}_version"] = version
            lines.append(line)
        rows.append((today, f"{_book_id(od)}/{stem}", "＋".join(LINE_NAME[x] for x in lines),
                     f"→{version}", note or "首次并 main", _pr(pr)))
    # 全部核完再落盘：中途报错时一个文件都不改
    for path, obj in pending:
        _dump(path, obj)
    OV.dump_json(os.path.join(od, "index.json"), index)
    append_changes(od, rows)
    return rows


def do_init_line(od, line, chapters, note, pr, today):
    """文本已入 main 后新开一条伴生线：文本 0.x 时定 0.1.0，≥1 时定 1.0.0；text_version 跟当前文本。"""
    if line == "text":
        raise BumpError("--init --line 只用于标点、实体线；文本线首次并 main 用 --init [--version 0.1.0]")
    index = OV.load_json(os.path.join(od, "index.json"))
    rows, pending = [], []
    for ch in select_chapters(index, chapters):
        stem = OV.chapter_file(ch)
        char_path = OV.companion_path(od, stem, "text")
        if not os.path.isfile(char_path):
            raise BumpError(f"册 {stem} 没有 {stem}.char.json")
        char = OV.load_json(char_path)
        tv = char.get("version")
        tvt = OV.parse_version(tv)
        if not tvt or tvt < OV.MIN_TEXT_0X:
            raise BumpError(f"{stem}.char.json version={tv!r}，文本线先 --init")
        if ch.get(f"{line}_version") is not None:
            raise BumpError(f"册 {stem} 已登记 {line}_version={ch[f'{line}_version']}，不能再 init，用 --level 升")
        cf = OV.companion_path(od, stem, line)
        if not os.path.isfile(cf):
            raise BumpError(f"册 {stem} 没有 {os.path.basename(cf)}")
        cd = OV.load_json(cf)
        bad = OV.anchor_mismatches(char, line, cd)
        if bad:
            raise BumpError(f"{os.path.basename(cf)} 还有 {len(bad)} 处锚点和当前文本对不上，先修好再开："
                            + "；".join(n for _i, n in bad[:5]))
        new = "0.1.0" if tvt[0] == 0 else "1.0.0"
        cd["version"] = new
        cd["text_version"] = tv
        pending.append((cf, cd))
        ch[f"{line}_version"] = new
        ch[f"{line}_file"] = os.path.basename(cf)
        rows.append((today, f"{_book_id(od)}/{stem}", LINE_NAME[line], f"→{new}", note or "首次并 main", _pr(pr)))
    for path, obj in pending:
        _dump(path, obj)
    OV.dump_json(os.path.join(od, "index.json"), index)
    append_changes(od, rows)
    return rows


def do_bump(od, line, level, chapters, note, pr, today):
    if level == "major":
        raise BumpError(
            "major 是质量等级（1 可用／2 出版级／3 定本），脚本不升。请手工改版本号（minor、patch 归零），"
            "并附验收记录：写在 char.json（文本线）、punct.json、entity.json 各自顶层的 review，"
            "至少含 date、signed_by、sample（抽检数据）；还要用户点头。")
    if not note:
        raise BumpError("--note 必填：一句话说明改了什么")
    index = OV.load_json(os.path.join(od, "index.json"))
    rows, warnings, pending = [], [], []
    for ch in select_chapters(index, chapters):
        stem = OV.chapter_file(ch)
        book = f"{_book_id(od)}/{stem}"
        char_path = OV.companion_path(od, stem, "text")
        if not os.path.isfile(char_path):
            raise BumpError(f"册 {stem} 没有 {stem}.char.json")
        char = OV.load_json(char_path)
        if line == "text":
            old = char.get("version")
            if not OV.parse_version(old) or OV.parse_version(old) < OV.MIN_TEXT_0X:
                raise BumpError(f"{stem}.char.json version={old!r}，先 --init")
            new = OV.bump(old, level)
            char["version"] = new
            pending.append((char_path, char))
            ch["text_version"] = new
            rows.append((today, book, "文本", f"{old}→{new}", note, _pr(pr)))
            for comp in ("punct", "entity"):
                cf = OV.companion_path(od, stem, comp)
                if not os.path.isfile(cf):
                    continue
                cd = OV.load_json(cf)
                bad = OV.anchor_mismatches(char, comp, cd)
                if bad:
                    warnings.append(f"册 {stem} {LINE_NAME[comp]}层有 {len(bad)} 处锚点对不上，未跟进 text_version："
                                    + "；".join(n for _i, n in bad[:5]))
                else:
                    cd["text_version"] = new
                    pending.append((cf, cd))
        else:
            cf = OV.companion_path(od, stem, line)
            if not os.path.isfile(cf):
                raise BumpError(f"册 {stem} 没有 {os.path.basename(cf)}")
            cd = OV.load_json(cf)
            old = cd.get("version")
            if not OV.parse_version(old) or OV.parse_version(old) < OV.MIN_TEXT_0X:
                raise BumpError(f"{os.path.basename(cf)} version={old!r}，先 --init")
            bad = OV.anchor_mismatches(char, line, cd)
            if bad:
                raise BumpError(f"{os.path.basename(cf)} 还有 {len(bad)} 处锚点和当前文本对不上，先修好再升："
                                + "；".join(n for _i, n in bad[:5]))
            new = OV.bump(old, level)
            cd["version"] = new
            cd["text_version"] = char.get("version")
            pending.append((cf, cd))
            ch[f"{line}_version"] = new
            rows.append((today, book, LINE_NAME[line], f"{old}→{new}", note, _pr(pr)))
    # 全部核完再落盘：中途报错时一个文件都不改
    for path, obj in pending:
        _dump(path, obj)
    OV.dump_json(os.path.join(od, "index.json"), index)
    append_changes(od, rows)
    return rows, warnings


def do_proofing(od, flag, chapters, note, pr, today):
    index = OV.load_json(os.path.join(od, "index.json"))
    rows = []
    for ch in select_chapters(index, chapters):
        stem = OV.chapter_file(ch)
        tv = OV.load_json(OV.companion_path(od, stem, "text")).get("version")
        if not flag and OV.proofing_expected(tv):
            raise BumpError(f"册 {stem} 文本线 {tv} 是 0.x（精校未完），不能关校对状态；先手工升 1.0.0")
        old = ch.get("proofing") is True
        ch["proofing"] = flag
        rows.append((today, f"{_book_id(od)}/{stem}", "校对状态",
                     f"{'开' if old else '关'}→{'开' if flag else '关'}", note, _pr(pr)))
    OV.dump_json(os.path.join(od, "index.json"), index)
    append_changes(od, rows)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="original 目录，或含 original/ 的条目目录")
    ap.add_argument("--init", action="store_true", help="首次并 main：三线都定为 1.0.0（或 --version 0.1.0）；带 --line punct|entity 时只新开那条伴生线")
    ap.add_argument("--version", choices=("0.1.0", "1.0.0"), default="1.0.0",
                    help="--init 定的版本：粗校完 0.1.0（伴生层同为 0.1.0），或 1.0.0（默认）")
    ap.add_argument("--proofing", choices=("on", "off"), help="只改章条目的 proofing 开关（校对中），不升版本")
    ap.add_argument("--line", choices=OV.LINES)
    ap.add_argument("--level", choices=("patch", "minor", "major"))
    ap.add_argument("--chapter", action="append", help="只动这一册（NNN），可重复；不给就是全部")
    ap.add_argument("--note", default="", help="一句话说明，写进 CHANGES.md")
    ap.add_argument("--pr", required=True, help="PR 号（必填，写进 CHANGES.md；未开 PR 时先开草稿 PR 再升版本）")
    ap.add_argument("--date", help=argparse.SUPPRESS)  # 自测用
    a = ap.parse_args(argv)
    today = a.date or datetime.date.today().isoformat()
    try:
        od = resolve_original(a.dir)
        if a.proofing:
            if a.init or a.line or a.level:
                ap.error("--proofing 单独用")
            if not a.note:
                ap.error("--proofing 需要 --note")
            rows, warnings = do_proofing(od, a.proofing == "on", a.chapter, a.note, a.pr, today), []
        elif a.init:
            if a.level:
                ap.error("--init 不和 --level 同用")
            if a.line:
                rows, warnings = do_init_line(od, a.line, a.chapter, a.note, a.pr, today), []
            else:
                rows, warnings = do_init(od, a.chapter, a.note, a.pr, today, a.version), []
        else:
            if not (a.line and a.level):
                ap.error("需要 --line 和 --level（或 --init）")
            rows, warnings = do_bump(od, a.line, a.level, a.chapter, a.note, a.pr, today)
    except BumpError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    for r in rows:
        print(" ｜ ".join(r))
    for w in warnings:
        print(f"注意：{w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
