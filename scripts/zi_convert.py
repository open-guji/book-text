#!/usr/bin/env python3
# 来源：open-guji-core/overview 的 项目进展/古籍文本/scripts/zi_convert.py @ 9cd45542（复制进本仓；源头改后人工同步）
"""组字（缺字部件）候选转换器（T26，2026-09-27）。

背景：`<句員>`、`<上雍下玉>`、`<三囗，囗中為歹>` 这类写法目前落进
guji-markdown 的夹注 `<…>`，网站会把它们渲染成小字注——但这些其实是整理者
对"底本这个字缺失、但看得出是哪几个部件拼成的"这件事的描述，不是真的注文，
渲染成小字会把意思弄错。guji-markdown 0.2.0 新增了组字指令 `:zi[…]`
（见 open-guji/guji-markdown `spec/syntax.md` §16），本脚本负责把已经散落在
book-text 里的这类写法转成 `:zi[…]`。

**只读不改**：本脚本只读 book-text（clone 到本地），只写 overview
（本文件、报告输出）。真要把候选应用回 book-text，由文本总管过目候选清单
之后另外动手，本脚本不做那一步（`convert` 子命令只把转换结果打印/写到
overview 侧的预览文件，从不改 book-text 工作区里的文件）。

## 判定规则（对应 guji-markdown spec §16 的三种写法）

给定 `<…>` 夹注内的原始文字 `note`：

1. **`上X下Y` / `左X右Y`，X、Y 各恰好一个字**：方位与部件都是单字，
   直接换算成 IDS —— `⿱XY` / `⿰XY`，写作 `:zi[⿱XY]`。
2. **`上X中Y下Z`，X、Y、Z 各恰好一个字**：三段顺序写清楚了，但 IDS 没有
   "三分" 操作符，只能嵌套成 `⿱X⿱YZ`（先分出最上一段，下面两段再嵌套）——
   **这一步涉及嵌套分组的选择，标成候选，供人核对**，不直接当作"已经转好"。
3. **含逗号／顿号，或出现"為"/"作"/"在"/"無"等替换、位置说明的自由文字**
   （如 `三囗，囗中為歹`、`与，一為廾`、`泑,ㄠ在力上`）：这些本来就不是简单
   "部件+方位"，是一句完整的校勘说明，原样收进 `:zi[原文]`，**不发明 IDS**，
   不涉及猜测，可以直接给候选。
4. **两个字、完全没有方位词**（如 `句員`、`人政`）：guji-markdown spec §16
   明确说了这种情况"不提供猜测规则"——`⿰句員`（左右）与 `⿱句員`（上下）
   是完全不同的字，猜错比不转更坏。**一律标成"需人工判读"，不给出候选记法**。
5. 其余（长度或形态不落在 1-4 任何一类，比如疑似 OCR 残留了多余符号的
   `人舄)`）：同样标"需人工判读"，不强行套用别的规则。

只有 1、2、3 三类会给出候选记法；4、5 只报"有这么一处，需要人看"，
不建议怎么改。

## 用法

    python3 zi_convert.py classify '<句員>'            # 单条测试，看落哪一类
    python3 zi_convert.py preview <book-text 章 md 路径>  # 转换预览，不改文件
        产出：同名 .zi-preview.md（转换后全文）+ 控制台印候选/需人工判读清单
    python3 zi_convert.py scan <book-text 根>            # 全仓扫描候选清单（默认只报有方位词的两类）
        --out <报告路径>（默认打印到控制台）
        --include-loose 连两字部件／自由文本也报——全仓噪声极大，见 cmd_scan 的说明，
                        建议只在 root 指到单本书目录时开
    python3 zi_convert.py --selftest                    # 自测，不需要仓
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

# 与 guji-markdown normalize.ts 的 canOpenJz 同一套排除条件：
# `<` 后不能是 ASCII 字母、/、!、?、>、空白——避开 HTML 标签、自动链接、空夹注。
_JZ_RE = re.compile(r"<([^<>\n]+)>")


def _is_real_jz_open(next_char: str) -> bool:
    if not next_char:
        return False
    if next_char.isascii() and (next_char.isalpha() or next_char in "/!?> \t"):
        return False
    return True


TOP_BOTTOM_RE = re.compile(r"^上(.)下(.)$")
LEFT_RIGHT_RE = re.compile(r"^左(.)右(.)$")
# 逗号／顿号隔开的写法（如「上萬，下杰」），逗号只是分隔符，不算进部件本身
TOP_BOTTOM_COMMA_RE = re.compile(r"^上(.)[，,、]下(.)$")
LEFT_RIGHT_COMMA_RE = re.compile(r"^左(.)[，,、]右(.)$")
TOP_MID_BOTTOM_RE = re.compile(r"^上(.)中(.)下(.)$")
# 八卦卦名——「上乾下坤」这类是describe易经卦象（上卦/下卦），不是缺字部件，
# 是本脚本全仓扫描踩到的最大一类假阳性（d59f2hrd5kow 等易类整部都是这个写法）。
_TRIGRAMS = set("乾坤震巽坎離离艮兌兊兑")
# "A上B下C"：A 在左，右边是上下叠的 B/C（如「王上虍下吊」= 左王、右边虍叠吊）
LEFT_TOPBOTTOM_RE = re.compile(r"^(.)上(.)下(.)$")
# "上XY下Z"：上段本身是左右两字（如「上召召下糸」= 上边召召并排、下边糸）
TOPPAIR_BOTTOM_RE = re.compile(r"^上(..)下(.)$")
# 自由文字说明：含逗号/顿号，或出现替换、位置类虚字
FREE_NOTE_RE = re.compile(r"[，,、]|為|作|在|無")
# 两字部件、无方位词：整串恰好两个字符，且不含数字/标点（真两字部件才算）
TWO_CHAR_RE = re.compile(r"^..$")


@dataclass
class ZiCandidate:
    original: str          # 原始 <…> 内文字
    kind: str              # "ids" | "nested-ids" | "text" | "ambiguous"
    notation: str | None   # 建议写法（:zi[…] 的完整形式），ambiguous 时为 None
    reason: str


def _is_trigram_pair(a: str, b: str) -> bool:
    return a in _TRIGRAMS and b in _TRIGRAMS


def _looks_like_glyph_char(ch: str) -> bool:
    """部件候选字符是否"像个字"——排除标点、数字、ASCII 字母、空白。

    真实假阳性实测过的例子：`頂上洿下。`／`上品下。` 里被正则捞到的
    最后一个"部件"其实是句号；只要有一个部件不像字，整条就不该算
    ids／nested-ids 候选。"""
    if ch.isascii() or ch.isspace() or ch.isdigit():
        return False
    return not unicodedata.category(ch).startswith("P")


def _all_parts_look_like_glyphs(*parts: str) -> bool:
    return all(_looks_like_glyph_char(ch) for part in parts for ch in part)


def classify(note: str) -> ZiCandidate:
    note = note.strip()

    m = TOP_BOTTOM_RE.match(note) or TOP_BOTTOM_COMMA_RE.match(note)
    if m:
        top, bottom = m.group(1), m.group(2)
        if not _all_parts_look_like_glyphs(top, bottom):
            return ZiCandidate(note, "ambiguous", None, "捕获到的部件里有标点/数字/ASCII 字母，不像真的组字，需人工判读")
        if _is_trigram_pair(top, bottom):
            return ZiCandidate(
                note, "ambiguous", None,
                f"「{note}」两字都是八卦卦名，很可能是描述易经卦象（上卦/下卦），"
                "不是缺字部件——本脚本按已知假阳性排除，仍需人核实"
            )
        return ZiCandidate(note, "ids", f":zi[⿱{top}{bottom}]", "上X下Y，X/Y 各一字，方位与部件都明确")

    m = LEFT_RIGHT_RE.match(note) or LEFT_RIGHT_COMMA_RE.match(note)
    if m:
        left, right = m.group(1), m.group(2)
        if not _all_parts_look_like_glyphs(left, right):
            return ZiCandidate(note, "ambiguous", None, "捕获到的部件里有标点/数字/ASCII 字母，不像真的组字，需人工判读")
        return ZiCandidate(note, "ids", f":zi[⿰{left}{right}]", "左X右Y，X/Y 各一字，方位与部件都明确")

    m = TOP_MID_BOTTOM_RE.match(note)
    if m:
        top, mid, bottom = m.group(1), m.group(2), m.group(3)
        if not _all_parts_look_like_glyphs(top, mid, bottom):
            return ZiCandidate(note, "ambiguous", None, "捕获到的部件里有标点/数字/ASCII 字母，不像真的组字，需人工判读")
        return ZiCandidate(
            note, "nested-ids", f":zi[⿱{top}⿱{mid}{bottom}]",
            "上X中Y下Z 三段顺序已定，但 IDS 无三分操作符，嵌套分组（先分上段、"
            "下两段再嵌套）是本脚本的选择，不是原文自带的信息，需要人核对"
        )

    m = LEFT_TOPBOTTOM_RE.match(note)
    if m:
        left, top, bottom = m.group(1), m.group(2), m.group(3)
        if not _all_parts_look_like_glyphs(left, top, bottom):
            return ZiCandidate(note, "ambiguous", None, "捕获到的部件里有标点/数字/ASCII 字母，不像真的组字，需人工判读")
        return ZiCandidate(
            note, "nested-ids", f":zi[⿰{left}⿱{top}{bottom}]",
            "A上B下C：左边一字、右边是上下叠的两字，三段顺序已定，"
            "嵌套分组是本脚本的选择，需要人核对"
        )

    m = TOPPAIR_BOTTOM_RE.match(note)
    if m:
        top_pair, bottom = m.group(1), m.group(2)
        if not _all_parts_look_like_glyphs(top_pair, bottom):
            return ZiCandidate(note, "ambiguous", None, "捕获到的部件里有标点/数字/ASCII 字母，不像真的组字，需人工判读")
        return ZiCandidate(
            note, "nested-ids", f":zi[⿱⿰{top_pair}{bottom}]",
            "上XY下Z：上边是左右并排的两字、下边一字，三段顺序已定，"
            "嵌套分组是本脚本的选择，需要人核对"
        )

    if FREE_NOTE_RE.search(note):
        return ZiCandidate(note, "text", f":zi[{note}]", "含逗号/顿号或替换、位置类说明，原文本身是完整校勘说明，原样收进 :zi[]，不发明 IDS")

    if TWO_CHAR_RE.match(note):
        return ZiCandidate(
            note, "ambiguous", None,
            "两个字、无方位词——⿰（左右）与⿱（上下）是完全不同的字，"
            "guji-markdown spec §16 定死不猜，需人工判读方位后再决定写法"
        )

    return ZiCandidate(note, "ambiguous", None, "形态不落在已知四类（含疑似 OCR 残留符号等），需人工判读")


def find_zi_candidates(text: str) -> list[tuple[int, int, str]]:
    """在原文里找出"看起来是组字部件描述"的 `<…>` 夹注，返回 (行号, 列号, 内容)。

    这里只挑"疑似组字"的，不是所有 `<…>` 都算——真正的人名/地名/音注夹注
    （如 `<孔子也>`、`<音洛>`）不该被本脚本碰。判据：内容不含常见的注音/
    释义虚字（也、者、曰、音、反、切）且长度 ≤ 12（部件描述天然短），
    这套判据是启发式的，扫出来的都是"候选"，最终仍由人核对，不是自动分类。
    """
    NOTE_STOPWORDS = re.compile(r"[也者曰音反切云謂讀爲今案按]")
    out: list[tuple[int, int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        i = 0
        while True:
            m = _JZ_RE.search(line, i)
            if not m:
                break
            content = m.group(1)
            nxt = line[m.start() + 1] if m.start() + 1 < len(line) else ""
            i = m.end()
            if not _is_real_jz_open(nxt):
                continue
            if len(content) > 12 or NOTE_STOPWORDS.search(content):
                continue
            # 至少要有一个 CJK 部首/汉字，纯数字/纯标点（页码类）不算
            if not re.search(r"[⺀-鿿]", content):
                continue
            out.append((lineno, m.start() + 1, content))
    return out


def preview_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()

    candidates = find_zi_candidates(text)
    results = [classify(note) for _, _, note in candidates]

    converted = text
    # 只替换 kind in (ids, nested-ids, text) 的那些，且原文整体只做精确子串替换
    # （同一个 note 在全文可能出现不止一次，逐条替换其对应的 <note> 记号）。
    for c in results:
        if c.notation is None:
            continue
        converted = converted.replace(f"<{c.original}>", c.notation)

    n_ids = sum(1 for c in results if c.kind == "ids")
    n_nested = sum(1 for c in results if c.kind == "nested-ids")
    n_text = sum(1 for c in results if c.kind == "text")
    n_ambiguous = sum(1 for c in results if c.kind == "ambiguous")

    return {
        "path": path,
        "total": len(results),
        "counts": {"ids": n_ids, "nested-ids": n_nested, "text": n_text, "ambiguous": n_ambiguous},
        "candidates": [asdict(c) for c in results],
        "converted_text": converted,
    }


def cmd_classify(args):
    c = classify(args.note.strip("<>"))
    print(json.dumps(asdict(c), ensure_ascii=False, indent=2))


def cmd_preview(args):
    result = preview_file(args.path)
    print(f"{args.path}: 共 {result['total']} 处疑似组字候选")
    for kind, n in result["counts"].items():
        print(f"  {kind}: {n}")
    print()
    for c in result["candidates"]:
        mark = "✅" if c["notation"] else "❓"
        print(f"  {mark} <{c['original']}> -> {c['notation'] or '（需人工判读）'}  # {c['reason']}")

    out_path = args.out or (os.path.splitext(args.path)[0] + ".zi-preview.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result["converted_text"])
    print(f"\n转换预览已写到（不改动 book-text 原文件）：{out_path}")

    report_path = args.report or (os.path.splitext(args.path)[0] + ".zi-report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in result.items() if k != "converted_text"}, f, ensure_ascii=False, indent=2)
    print(f"候选清单已写到：{report_path}")


def cmd_scan(args):
    """全仓扫描候选清单。

    默认只报「上X下Y」/「左X右Y」这类**有明确方位词**的写法（`kind in
    {ids, nested-ids}`）——实测这一档在全仓约 70 处上下，贴近任务书估的
    「约 60 处，散在十几部里」。**这一档也不是零假阳性**：实测全仓扫描
    命中过《易经》类"上乾下坤"这类描述卦象的写法（已用 `_TRIGRAMS`
    过滤掉八卦卦名两两相配的情况）、"以上並下殤"这类"上"字只是"以上"
    一词的一部分、以及"梁四公"故事里"上音攜，下琛去"这类实为
    "上字/下字"（复合词头一字/第二字）注音，根本不是部件方位——
    **每一条都要人工核实语境，本脚本只给出"形状对得上"的候选，不判语义**。

    `--include-loose` 打开"两字部件、无方位词"（`kind=ambiguous`）与
    自由文字（`kind=text`）两类的全量统计——**默认不开**，因为实测在全库
    开这两类会扫出五十万＋条，几乎全是普通夹注（地名、人名、释义，凡是
    恰好两个字或恰好带逗号的夹注都会命中），不是能看的候选清单。
    真要用这两类，建议只对**单本书**开（`root` 指到某个 Work 目录），
    像本脚本对宋史卷215 的 `preview` 子命令那样、且已知这本书大量使用
    这类写法时才有意义，不建议直接对全仓开。
    """
    root = args.root
    report = []
    total_counts = {"ids": 0, "nested-ids": 0, "text": 0, "ambiguous": 0}
    n_files_hit = 0

    patterns = [
        os.path.join(root, "**", "full_text", "*.md"),
        os.path.join(root, "**", "full_text", "*", "*.md"),
        os.path.join(root, "**", "collated_edition", "text", "*.md"),
    ]
    import glob as _glob
    files = sorted(set(f for p in patterns for f in _glob.glob(p, recursive=True)))

    report_kinds = {"ids", "nested-ids", "text", "ambiguous"} if args.include_loose else {"ids", "nested-ids"}

    for f in files:
        try:
            text = open(f, encoding="utf-8").read()
        except Exception as e:  # noqa: BLE001
            continue
        candidates = find_zi_candidates(text)
        if not candidates:
            continue
        results = [(lineno, col, classify(note)) for lineno, col, note in candidates]
        for _, _, c in results:
            total_counts[c.kind] += 1
        kept = [(lineno, col, c) for lineno, col, c in results if c.kind in report_kinds]
        if not kept:
            continue
        n_files_hit += 1
        report.append({
            "file": os.path.relpath(f, root),
            "candidates": [{"line": lineno, "column": col, **asdict(c)} for lineno, col, c in kept],
        })

    summary = {
        "files_scanned": len(files),
        "files_with_reported_candidates": n_files_hit,
        "total_counts（全部命中的原始分类，含未列进 files 明细的）": total_counts,
        "reported_kinds": sorted(report_kinds),
        "files": report,
    }

    out = args.out
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"扫描完毕：{len(files)} 档；{n_files_hit} 档有落进报告的候选（kind ∈ {sorted(report_kinds)}）；报告已写到 {out}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"全部原始分类统计：{total_counts}")
    if not args.include_loose:
        print("（默认只报 ids/nested-ids；text/ambiguous 两类全仓噪声极大，未列入，见 --include-loose 的说明）")
    print("⚠️ 以上全部是「形状候选」，不是语义判定——已知的假阳性至少三类："
          "易经卦象（上乾下坤）、「以上／以下」之类的普通虚词、复合词逐字注音"
          "（如「上音攜，下琛去」实为「上字／下字」）。每一条都要人工核实语境后再改 "
          "book-text，本脚本不自动改任何数据。")


def selftest():
    ok = True

    def check(note, expect_kind, expect_notation=None):
        nonlocal ok
        c = classify(note)
        status = "PASS" if c.kind == expect_kind and (expect_notation is None or c.notation == expect_notation) else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"[{status}] {note!r} -> kind={c.kind} notation={c.notation}")

    check("上雍下玉", "ids", ":zi[⿱雍玉]")
    check("左句右員", "ids", ":zi[⿰句員]")
    check("上宀中出下心", "nested-ids", ":zi[⿱宀⿱出心]")
    check("王上虍下吊", "nested-ids", ":zi[⿰王⿱虍吊]")
    check("上召召下糸", "nested-ids", ":zi[⿱⿰召召糸]")
    check("上萬，下杰", "ids", ":zi[⿱萬杰]")
    check("上乾下坤", "ambiguous", None)  # 八卦卦名，疑似易经卦象假阳性，不当组字
    check("三囗，囗中為歹", "text", ":zi[三囗，囗中為歹]")
    check("与，一為廾", "text", ":zi[与，一為廾]")
    check("句員", "ambiguous", None)
    check("人政", "ambiguous", None)
    check("人舄)", "ambiguous", None)

    # find_zi_candidates 不该把真正的音注/释义夹注当成组字候选
    text = "帝崩<孔子也>即位<音洛>正文<句員>正文"
    hits = find_zi_candidates(text)
    hit_notes = [n for _, _, n in hits]
    status = "PASS" if hit_notes == ["句員"] else "FAIL"
    if status == "FAIL":
        ok = False
    print(f"[{status}] find_zi_candidates 排除真夹注：{hit_notes}（期望 ['句員']）")

    print("自测：" + ("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    p_classify = sub.add_parser("classify")
    p_classify.add_argument("note")
    p_classify.set_defaults(func=cmd_classify)

    p_preview = sub.add_parser("preview")
    p_preview.add_argument("path")
    p_preview.add_argument("--out")
    p_preview.add_argument("--report")
    p_preview.set_defaults(func=cmd_preview)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("root")
    p_scan.add_argument("--out")
    p_scan.add_argument("--include-loose", action="store_true",
                         help="连两字部件／自由文本也报（全仓噪声极大，见函数 docstring；建议只在 root 指到单本书时开）")
    p_scan.set_defaults(func=cmd_scan)

    args = parser.parse_args()
    if args.selftest:
        sys.exit(0 if selftest() else 1)
    if not getattr(args, "func", None):
        parser.print_help()
        sys.exit(2)
    args.func(args)


if __name__ == "__main__":
    main()
