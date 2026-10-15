#!/usr/bin/env python3
"""逐条核对一部整理本 collated_edition 的 md 与 json 是否内容一致。

背景：09-14 E-md补齐 道用过一个同名脚本核对过 3 部反向生成的 md，但没有入仓
（重找过，overview 全仓无此档）。本档按它报告 §五描述的方法重写，并推广到
两种既有版式：

- **line 模式**（宋史藝文志、漢書藝文志一类"一条一行"忠实底本 md）：
  md 每个非空、非注释、非标题行，对 json 对应 juan 里"带 content 字段"的
  section，按顺序一一配对，用 `difflib` 找出两侧独有的行／条。
- **heading 模式**（補南齊書經籍志一类"标题起段"结构化 md）：
  md 用 `#`/`##`/`###`... 标题分段，对 json 的 section 树按 level 逐层配对，
  每段内文字（text/source/note）与 json 的 paragraphs[].text / .source / note
  逐项比对。

两种模式共用 `normalize()`：去掉夹注／引号等记号的包裹符号（**只去符号，
不去内容**），折叠空白，这样"记号不同、内容相同"不会被误判为差异——
09 档 §七 的教训："记号处数不能判内容多寡，只能发现要人看"，
本脚本反过来先蒙眼去记号，只比内容，记号异同留给量记号脚本单独管。

用法：
    python3 verify_md.py <collated_edition 目录> --mode line
    python3 verify_md.py <collated_edition 目录> --mode heading
    加 --json 出档 把逐条差异写成 JSON 供后续处理
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

# 量记号2.py／取文本.py 属目录总管写域，只读引用，不改
_GEZHI = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "古籍目录", "目录录入", "二十五史艺文志考补", "scripts", "格式对齐",
)
sys.path.insert(0, os.path.abspath(_GEZHI))

# 夹注／引号记号的包裹符号——只去符号本身，不去被包住的文字
_WRAP_PAIRS = ["⟨⟩", "〔〕", "<>", "「」", "“”", "‘’", "『』"]
_DOUBLE_WRAP_PAIRS = ["（（））"]  # 宋史 md 独有的双层圆括号夹注


def normalize(s):
    """去记号包裹符号＋折叠空白，只留下要比较的文字本身。"""
    if not s:
        return ""
    for pair in _DOUBLE_WRAP_PAIRS:
        l, r = pair[:2], pair[2:]
        s = s.replace(l, "").replace(r, "")
    for pair in _WRAP_PAIRS:
        l, r = pair[0], pair[1]
        s = s.replace(l, "").replace(r, "")
    return re.sub(r"\s+", "", s)


def load_md_lines(path):
    """返回 (非空非注释非标题行的列表, 标题行列表[(行在原文件行号,层级,文字)])。

    HTML 注释按块跳过（书志头／页码注释都是 `<!-- ... -->`，页码注释是单行，
    书志头是跨行块——只跳单行开头会把书志头正文当成差异，**这是真实踩过的坑**：
    首次实现只判"行以 `<!--` 开头"，把 7 行书志头正文全部算成"md 独有"）。
    """
    with open(path, encoding="utf-8") as f:
        raw = f.read().split("\n")
    lines, headings = [], []
    in_comment = False
    for lineno, l in enumerate(raw, 1):
        stripped = l.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped == "":
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", l)
        if m:
            headings.append((lineno, len(m.group(1)), m.group(2).strip()))
            continue
        lines.append((lineno, l))
    return lines, headings


def mode_line(work_dir):
    """一条一行模式：md 非空行 vs json 带 content 的 section，**按去记号后的文字
    做多重集（bag）比对**，不按行号位置对齐——09 档 §七的量法就是"归一记号
    后按去重集合比对"，位置对齐在宋史这种双方各有独有条目、顺序也可能不同
    的场景下没有意义，反而会把"错位"误判成"内容不同"。

    多出的一侧＝该侧独有的真实条目（去重前后都报，前者供落盘用，
    后者供人看规模用）。
    """
    index = json.load(open(os.path.join(work_dir, "index.json"), encoding="utf-8"))
    report = {"mode": "line", "juan": []}
    for jf in index["juan_files"]:
        jpath = os.path.join(work_dir, jf)
        data = json.load(open(jpath, encoding="utf-8"))
        title = data.get("title", "")
        mdpath = os.path.join(work_dir, "text", title + ".md")
        entry = {"juan_file": jf, "juan_title": title}
        if not os.path.exists(mdpath):
            entry["error"] = f"找不到对应 md：{mdpath}"
            report["juan"].append(entry)
            continue
        md_lines, _headings = load_md_lines(mdpath)
        sections = [s for s in data["sections"] if "content" in s]

        md_bag = collections.Counter(normalize(l) for _, l in md_lines)
        json_bag = collections.Counter(normalize(s["content"]) for s in sections)
        # 保留原文（未 normalize）方便落待裁单：记一个 normalize 后文字 -> 原文样例 的映射
        md_orig = {}
        for lineno, l in md_lines:
            md_orig.setdefault(normalize(l), []).append({"行号": lineno, "文": l})
        json_orig = {}
        for s in sections:
            json_orig.setdefault(normalize(s["content"]), []).append(
                {"work_id": s.get("work_id"), "title": s.get("title"), "content": s.get("content")})

        md_only = md_bag - json_bag
        json_only = json_bag - md_bag
        diffs = []
        if md_only:
            diffs.append({"tag": "md_only", "去重条数": len(md_only), "总条数": sum(md_only.values()),
                          "样例": [{"次数": n, **md_orig[k][0]} for k, n in md_only.items()]})
        if json_only:
            diffs.append({"tag": "json_only", "去重条数": len(json_only), "总条数": sum(json_only.values()),
                          "样例": [{"次数": n, **json_orig[k][0]} for k, n in json_only.items()]})
        entry["md行数"] = len(md_lines)
        entry["json条数"] = len(sections)
        entry["差异段数"] = len(diffs)
        if diffs:
            entry["diffs"] = diffs
        report["juan"].append(entry)
    return report


def _md_heading_blocks(headings, all_lines_count):
    """把 (行号,层级,文字) 标题表转成 [(层级, 文字, 起始行号, 结束行号)] 区间。"""
    blocks = []
    for i, (lineno, level, text) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else all_lines_count + 1
        blocks.append((level, text, lineno, end))
    return blocks


def _split_body(lines_in_range):
    """把一个标题区间内的正文行，按空行分组（组内视为一段）。"""
    groups, cur = [], []
    for l in lines_in_range:
        if l.strip() == "":
            if cur:
                groups.append(cur)
                cur = []
        else:
            cur.append(l)
    if cur:
        groups.append(cur)
    return groups


def _parse_book_block(body_lines):
    """还原一个 book 段（### 标题下）的 paragraphs / note，对应 json 的
    paragraphs[].text / .source 与顶层 note。"""
    groups = _split_body(body_lines)
    paragraphs, note = [], None
    for g in groups:
        joined = "".join(g) if len(g) == 1 else g
        first = g[0]
        if re.match(r"^[〔<⟨]按[:：]", first) and len(g) == 1:
            note = normalize(re.sub(r"^[〔<⟨]按[:：]", "", first))
            continue
        text, source = "", ""
        idx = 0
        if idx < len(g) and not re.match(r"^[〔<⟨「“]", g[idx]):
            text = g[idx]
            idx += 1
        if idx < len(g):
            source = g[idx]
        paragraphs.append({"text": normalize(text), "source": normalize(source)})
    return paragraphs, note


def mode_heading(work_dir):
    """标题分段模式：md 按 #/##/### 分段，与 json 的 section 树按 level+title 配对。"""
    index = json.load(open(os.path.join(work_dir, "index.json"), encoding="utf-8"))
    report = {"mode": "heading", "juan": []}
    for jf in index["juan_files"]:
        jpath = os.path.join(work_dir, jf)
        data = json.load(open(jpath, encoding="utf-8"))
        title = data.get("title", "")
        mdpath = os.path.join(work_dir, "text", title + ".md")
        entry = {"juan_file": jf, "juan_title": title}
        if not os.path.exists(mdpath):
            entry["error"] = f"找不到对应 md：{mdpath}"
            report["juan"].append(entry)
            continue
        with open(mdpath, encoding="utf-8") as f:
            raw_lines = f.read().split("\n")
        _md_lines, headings = load_md_lines(mdpath)
        blocks = _md_heading_blocks(headings, len(raw_lines))
        # 只取 book 一类对应的最深层标题（level 最大的那一层通常是条目）
        book_blocks = {h[1].strip(): (h[0], h[1], h[2], h[3]) for h in blocks}

        sections = data["sections"]
        diffs = []
        md_titles_seen = set()
        for s in sections:
            if s.get("type") != "book":
                continue
            t = s["title"].strip()
            md_titles_seen.add(t)
            if t not in book_blocks:
                diffs.append({"tag": "json_only_title", "work_id": s.get("work_id"), "title": t})
                continue
            _lvl, _txt, start, end = book_blocks[t]
            body = [raw_lines[i - 1] for i in range(start + 1, end)]
            md_paras, md_note = _parse_book_block(body)
            json_paras = [{"text": normalize(p.get("text", "")), "source": normalize(p.get("source", ""))}
                          for p in s.get("paragraphs", [])]
            json_note = normalize(s.get("note", "")) if s.get("note") else None
            if md_paras != json_paras or (md_note or None) != (json_note or None):
                diffs.append({
                    "tag": "content_mismatch",
                    "work_id": s.get("work_id"),
                    "title": t,
                    "md_paragraphs": md_paras,
                    "json_paragraphs": json_paras,
                    "md_note": md_note,
                    "json_note": json_note,
                })
        md_only_titles = [h[1].strip() for h in blocks if h[0] >= 3 and h[1].strip() not in md_titles_seen
                           and h[1].strip() not in {b[1].strip() for b in blocks if b[0] < 3}]
        if md_only_titles:
            diffs.append({"tag": "md_only_titles", "titles": md_only_titles})
        entry["book段数"] = sum(1 for s in sections if s.get("type") == "book")
        entry["md标题数"] = len(blocks)
        entry["差异段数"] = len(diffs)
        if diffs:
            entry["diffs"] = diffs
        report["juan"].append(entry)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("work_dir", help="collated_edition 目录，如 .../d59f2gdp696q/collated_edition")
    p.add_argument("--mode", choices=["line", "heading"], required=True)
    p.add_argument("--json", default=None, help="把完整差异写成 JSON 到此路径")
    a = p.parse_args()

    fn = mode_line if a.mode == "line" else mode_heading
    report = fn(a.work_dir)

    total_diff = sum(j.get("差异段数", 0) for j in report["juan"])
    print(f"模式：{a.mode}　卷数：{len(report['juan'])}　差异段数合计：{total_diff}")
    for j in report["juan"]:
        if j.get("error"):
            print(f"  ⚠ {j['juan_file']}：{j['error']}")
        elif j.get("差异段数"):
            print(f"  {j['juan_file']}（{j['juan_title']}）：差异 {j['差异段数']} 段")

    if a.json:
        json.dump(report, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n已写 {a.json}")

    sys.exit(0 if total_diff == 0 else 1)


if __name__ == "__main__":
    main()
