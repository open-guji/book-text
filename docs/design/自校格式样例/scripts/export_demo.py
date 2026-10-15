#!/usr/bin/env python3
"""T10 草案 · 派生链路验证脚本（只读 overview 样例，不动任何代码仓/数据仓）。

把同目录 p0010.json（自校文本格式草案的样例数据）按列拼成 guji-markdown 源文本，
证明"本格式字段足够无损导出①横排分段 guji-markdown"这条派生链路走得通。

算法照抄 open-guji-cv 仓 `open_guji_cv/render/guji_markdown.py::render_column`
（2026-09-26 只读实测，未改该仓一字）：
- 行首 `^` × n_raised（抬头级数）＋ `.` × lead_blank（挪抬）
- 双行夹注 a/b 成段收集，两者都有内容才插 `|`，只有一边则不插，两边都空则整段不输出
- 单行小注 kind=jiazhu_solo（本样例未覆盖，故此脚本对应分支留空即可，不影响本页两列）
- blank / excluded 跳过不占位
- 阙文（unreadable）出 `[[]]`
"""
from __future__ import annotations

import json
from pathlib import Path


def char_text(cell: dict) -> str:
    if cell.get("unreadable"):
        return "[[]]"
    text = cell.get("char") or "[[]]"
    if text == "□" and cell.get("guess"):
        return f"□{{guess={cell['guess']}}}"
    return text


def render_column(cells: list[dict], n_raised: int, lead_blank: int) -> str:
    prefix = ("^" * n_raised if n_raised > 0 else "") + "." * lead_blank
    out: list[str] = []
    i = 0
    cells = sorted(cells, key=lambda c: c["order"])
    while i < len(cells):
        rec = cells[i]
        kind = rec["kind"]

        if kind in ("jiazhu_a", "jiazhu_b"):
            a_chars: list[str] = []
            b_chars: list[str] = []
            while i < len(cells) and cells[i]["kind"] in ("jiazhu_a", "jiazhu_b"):
                r = cells[i]
                if not r.get("excluded"):
                    (a_chars if r["kind"] == "jiazhu_a" else b_chars).append(char_text(r))
                i += 1
            if a_chars and b_chars:
                out.append("<" + "".join(a_chars) + "|" + "".join(b_chars) + ">")
            elif a_chars or b_chars:
                out.append("<" + "".join(a_chars) + "".join(b_chars) + ">")
            continue

        if kind == "jiazhu_solo":
            chars: list[str] = []
            while i < len(cells) and cells[i]["kind"] == "jiazhu_solo":
                r = cells[i]
                if not r.get("excluded"):
                    chars.append(char_text(r))
                i += 1
            if chars:
                out.append(":jz[" + "".join("□" if c == "[[]]" else c for c in chars) + "]{type=单行}")
            continue

        if kind == "blank":
            i += 1
            continue

        if rec.get("excluded"):
            i += 1
            continue

        out.append(char_text(rec))
        i += 1

    return prefix + "".join(out)


def render_page(page: dict) -> str:
    lines = []
    for col in page["columns"]:
        lines.append(render_column(col["cells"], col.get("n_raised", 0), col.get("lead_blank", 0)))
    return "\n".join(lines)


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    page = json.loads((here / "p0010.json").read_text(encoding="utf-8"))
    md = render_page(page)
    out_path = here / "p0010.export.md"
    header = (
        f"<!-- 由 export_demo.py 从 p0010.json 派生，验证格式→guji-markdown 链路通；"
        f"{page['book_title']}（{page['book_id']}） 第 {page['page']} 页 -->\n"
    )
    out_path.write_text(header + md + "\n", encoding="utf-8")
    print(f"写入 {out_path}")
    print("---")
    print(md)


if __name__ == "__main__":
    main()
