#!/usr/bin/env python3
"""表格记法转换原型（T19，2026-09-27）。

背景：book-text 129 个「表格章」现在存的是暂行格式——`convert_tables()`
（`scripts/fetch-book-fulltext/guji_clean.py`）把维基 wikitable 逐行拍成
`a | b | c`，前后包 `<!-- table -->`，丢掉了三样东西：
  1. 空单元格的位置（`.strip()` 把全角空格 U+3000 也当空白吃掉，空格再被
     `if c != ''` 整格删除，行内后续列全部错位）；
  2. 表头行与数据行的区分（wikitext 的 `!`/`!!` 与 `|`/`||` 被同一套
     `_split_table_row` 拍成同一种"格"，`has_table` 只记有没有表，不记哪几行是表头）；
  3. 真正的 colspan/rowspan（`_strip_cell_attr` 直接丢弃单元格属性）。

结论（方案 §一 已用 6 个实测样例逐条对照过）：这三样信息只能从原始 wikitext
重新解析拿回来，book-text 现存的线性化文本本身已经回天乏术。所以本脚本
提供两条路：

- `refetch` 模式（推荐）：给一个维基文库 page_title，联网重新取
  wikitext/HTML，按真实结构解析（表头、colspan、rowspan、空格），
  转成推荐记法（见方案 §二）。本脚本 6 个样例都走这条路验证过。
- `from-stored` 模式（机械兜底，不联网）：只吃 book-text 已存的
  `<!-- table -->` 线性化文本，尽力把缺的列在行尾补空占位符，
  并把"补了多少处、说明信息已经回不来了"计数上报——
  借用 guji-markdown spec §0.5「降级必须可数」的原则，不假装能复原丢掉的信息。

推荐记法本身（guji-markdown 自定义容器块 `:::table`）的设计说明见
`整体设计/2026-09-表格记法方案.md` §二。本文件是"把维基原始表格转成这个
记法"的机械转换器，不是记法本身的定义。

用法：
    python3 table_convert.py refetch <page_title> [--out DIR]
    python3 table_convert.py from-stored <book-text 章 md 路径> [--out DIR]
    python3 table_convert.py demo   # 跑方案挑的 6 个样例，产出到 展示样张/表格/
    python3 table_convert.py convert-chapter <page_title> <book-text 章 md 路径> [--dry-run]
    python3 table_convert.py convert-book <index.json 路径> [--chapters 210,211] [--dry-run] [--report OUT.json]

T22（2026-09-27，宋史 32 章试点）在 T19 原型基础上加的两件：

1. `convert-chapter`／`convert-book`：把 `refetch` 解析出的表格，**按出现顺序就地替换**
   book-text 现存章节 md 里的 `<!-- table -->...<!-- /table -->` 块，块外文字一字不动
   （`replace_stored_blocks()`）；`convert-book` 顺带给 `index.json` 加顶层
   `table_notation: "guji-table-v1"` 字段（`has_table` 每章保留不动，`revision` 不改）。
   `verify_conversion()` 做即时自检（块外文本是否原样、全篇汉字数是否不降、
   `:::table` 块内展开合并格后列数是否处处等于表头列数）——**正式把关仍以
   `validate_text_format.py` 新增的 `F-MD-09 --strict` 为准**，这里只是转换时的即时反馈。
2. `refetch`（连带 `demo`／`convert-chapter`）现在统一先过一遍
   `fetch_24shi.resolve_transclusions()`／`_extract_onlyinclude()`／`_expand_part_links()`
   再解析表格——T19 挑的 6 个样例没踩到，但宋史卷215（宗室世系一）正文被拆成
   `/第一部分`／`/第二部分`／`/第三部分` 三个子页，主页 wikitext 只剩三行链接，
   不展开会把整卷 3 个表格漏成 0 个（`fetch_24shi.py` 09-26 抓二十四史时已经踩过
   这个坑并写了 `_expand_part_links`，这里直接复用，不重新造）。对不需要展开的
   页面这三步都是空操作，不影响 T19 已验证过的 6 个样例。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FETCH_TOOLS_DIR = SCRIPT_DIR.parent.parent.parent / "scripts" / "fetch-book-fulltext"
sys.path.insert(0, str(FETCH_TOOLS_DIR))
import guji_clean  # noqa: E402  （复用同一套 wikitext→guji-markdown 单元格清洗，見上）
import wiki_api  # noqa: E402  （复用既有 API 封装：3 秒节流＋磁盘缓存，见 wiki_api.get_revision）
import fetch_24shi  # noqa: E402  （T22 复用：resolve_transclusions／_extract_onlyinclude／_expand_part_links，见上）


# ---------- 数据模型 ----------


@dataclass
class Cell:
    text: str  # 已清洗为 guji-markdown 的单元格内容（未清洗前的原始 wikitext 另存 raw）
    raw: str
    colspan: int = 1
    rowspan: int = 1
    empty: bool = False  # 原文就是全角空格/纯空白占位，不是我们弄丢的


@dataclass
class Row:
    is_header: bool
    cells: list[Cell] = field(default_factory=list)


@dataclass
class Table:
    rows: list[Row] = field(default_factory=list)
    # wikitable `|+`表格说明文字（如「燕王房」这种分支小标题），大多数表没有；
    # 不属于任何一行的格子，塞进 :::table 的行列语法里没有意义，T22 改成渲染时
    # 单独放在 :::table 块前一行（见 replace_stored_blocks），不静默丢弃。
    caption: str = ""

    @property
    def n_cols(self) -> int:
        """表的"视觉列数"——取第一行各格 colspan 之和作为基准。"""
        if not self.rows:
            return 0
        return sum(c.colspan for c in self.rows[0].cells)


# ---------- wikitext {|...|} 解析（保留 colspan/rowspan/表头/空格） ----------

_ATTR_RE = re.compile(r'^\s*((?:[\w-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|\S+)\s*)+)\|(?!\|)(.*)$', re.DOTALL)
_COLSPAN_RE = re.compile(r'colspan\s*=\s*"?(\d+)"?', re.IGNORECASE)
_ROWSPAN_RE = re.compile(r'rowspan\s*=\s*"?(\d+)"?', re.IGNORECASE)


def _split_attr(cell_src: str) -> tuple[str, int, int]:
    """`attr|content` -> (content, colspan, rowspan)；无属性则原样返回。"""
    m = _ATTR_RE.match(cell_src)
    attrs, content = (m.group(1), m.group(2)) if m else ("", cell_src)
    colspan = int(_COLSPAN_RE.search(attrs).group(1)) if _COLSPAN_RE.search(attrs) else 1
    rowspan = int(_ROWSPAN_RE.search(attrs).group(1)) if _ROWSPAN_RE.search(attrs) else 1
    return content, colspan, rowspan


_CELL_SOFTWRAP_RE = re.compile(r"[ \t]*\n[ \t]*")


def _collapse_cell_newlines(text: str) -> str:
    """`:::table` 是"一行一条记录"的记法，格子内容里不能再带真实换行——
    但 wikitable 本身有两种会在同一个格子里产生换行的写法：① 数据行"续行"
    （没有前导 `|` 的行接着算上一格，如 漢書/卷014）；② HTML `<td>` 内部
    直接写多段（如 遼史/卷63）。T32 09-27 查证：这些换行在源 wikitext 里
    本来就不是段落分隔，是长内容手工软换行（如 新唐書/卷026 的夹注
    `<初增九\n   末減隱>` 拆成两行只是排版方便，含义是同一整句"初增九末減隱"）
    ——旧的暂行线性化格式对这种情况本来就处理错误（同一个格子被拆成两条
    "记录"，内容错位窜到下一行/下一格，见 done 单实测），直接拼接消掉换行
    不是丢信息，是把这处旧 bug 一并修正。中文不需要词间空格，直接拼接
    （不留空格）与整句原意一致。"""
    return _CELL_SOFTWRAP_RE.sub("", text)


_CELL_CLEAN_SENTINEL = "\x02"


def _clean_cell_text(raw: str) -> tuple[str, bool]:
    raw_stripped = _collapse_cell_newlines(raw.strip())
    # 全角空格／纯空白＝原文自己的"无内容"占位，不是我们弄丢的，标记出来
    is_placeholder = raw_stripped == "" or raw_stripped.strip("　 \t") == ""
    if raw_stripped:
        # T32 09-27 修的坑：guji_clean.wikitext_to_guji_markdown() 是给"整章
        # 正文"设计的清洗管线，其中 NAV_ONLY_LINE_RE 这一步会把"整行只有一个
        # `[[目标|显示文字]]` 式链接、没有别的字"的行当成维基导航残留整行删掉
        # ——这对整章正文是对的（那种行确实是导航垃圾），但表格单元格是**单独**
        # 喂给这个函数清洗的，世系表/年表里"这一格恰好就是一个人名链接"极常见
        # （如 金史/卷59「[[金史/卷73|阿離合懣]]」），被误判成导航行整格删空，
        # 4 个汉字静默消失（本道靠"汉字数只增不减"的自检拦到，逐处查证实锤：
        # 该页 revid 与原ingestion时一致，排除"源文本身改了"的可能）。
        # 修法：给格内容临时垫一个不出现在任何 wiki 语法里的哨兵字符，让这一行
        # 不再"整行只是链接"，清洗完再摘掉——不改 guji_clean.py（整章正文清洗
        # 本身没问题，问题只在"喂给它的是单元格碎片"这个用法上）。
        cleaned = guji_clean.wikitext_to_guji_markdown(_CELL_CLEAN_SENTINEL + raw_stripped, {})
        cleaned = cleaned.replace(_CELL_CLEAN_SENTINEL, "", 1)
    else:
        cleaned = ""
    cleaned = _collapse_cell_newlines(cleaned)
    return cleaned, is_placeholder


def parse_wikitable(body: str) -> Table:
    """`body` 是 `{|...|}` 去掉首尾两行后的内容（含所有 `|-` 行）。"""
    lines = body.split("\n")
    rows: list[Row] = []
    captions: list[str] = []
    cur_row: Row | None = None
    cur_cell: Cell | None = None

    def flush_cell():
        # T32 09-27 修的坑：`.text`／`.empty` 不在这里算——一格可能横跨好几个物理行
        # （wikitable「无前导 `|` 的行＝续接上一格」的写法，见下面续行分支），
        # 这里就把 .text 算死，续行内容之后只改得到 .raw、改不到 .text，等于
        # 白追加。改成全表 raw 收集完，最后统一算一遍（见 parse_wikitable 末尾）。
        # 漢書/卷014 表 5（两行数据各带 1-2 行续接）就是这样静默丢了 109 个汉字：
        # 「河平四年四月，徙定陶，凡十九年薨。」「綏和元年，為皇太子。」等续接内容
        # 全部丢失，因为它们追加进已经 flush 过的 cell.raw，而 .text 早就算完了。
        nonlocal cur_cell
        if cur_cell is not None and cur_row is not None:
            cur_row.cells.append(cur_cell)
        cur_cell = None

    for line in lines:
        s = line.rstrip()
        stripped = s.strip()
        if stripped.startswith("|-"):
            flush_cell()
            if cur_row is not None:
                rows.append(cur_row)
            cur_row = Row(is_header=False)
            continue
        if stripped.startswith("|+"):
            # `|+`表格说明文字（如「燕王房」这类分支小标题，宋史/卷215/第一部分
            # 踩到过）：不进行列，但也不能白丢——存进 table.caption，交渲染层
            # 放到 :::table 块前一行（见 Table.caption 字段说明）。
            text, _ = _clean_cell_text(stripped[2:].strip())
            if text:
                captions.append(text)
            continue
        if stripped == "":
            continue
        if cur_row is None:
            # T22 09-27 修的坑：MediaWiki 表格首行前的 `|-` 是可省的（隐式首行），
            # 之前这里"没见过 `|-` 就整段忽略"会把没有前导 `|-` 的整个首行数据
            # 全部吃掉——宋史/卷230 等宗室世系表（一格一行的写法）踩了个正着，
            # 首行「餘姚郡王宗詠｜東陽郡公…」9+6=15 个汉字曾经被静默丢弃。
            # 现在改成：遇到真正的 `!`/`|` 内容行就隐式开一行，不再要求前导 `|-`。
            cur_row = Row(is_header=False)
        if stripped.startswith("!"):
            flush_cell()
            cur_row.is_header = True
            # T32 09-27 修的坑：MediaWiki 表头行同一行内 `!!`／`||` 都是合法的列分隔符
            # （MediaWiki 解析器内部把 `!!` 替换成 `||` 再统一切分，两种写法等价）——
            # 海國圖志/卷073「! 中國紀年 || 西洋紀年」用的是 `||`，之前只认 `!!` 会把
            # 整行当成一个格，后续每个数据行都因此被腰斩成一半（该表 280 行 2 列，
            # 汉字数从 7673 掉到 5495 就是这个 bug）。改成两种分隔符都认。
            defs = re.split(r"!!|\|\|", stripped[1:])
            for d in defs:
                content, colspan, rowspan = _split_attr(d.strip())
                cur_cell = Cell(text="", raw=content, colspan=colspan, rowspan=rowspan)
                flush_cell()
            cur_cell = None
        elif stripped.startswith("|") and not stripped.startswith("|}"):
            flush_cell()
            defs = stripped[1:].split("||")
            for d in defs:
                content, colspan, rowspan = _split_attr(d.strip())
                cur_cell = Cell(text="", raw=content, colspan=colspan, rowspan=rowspan)
                flush_cell()
            cur_cell = None
        elif stripped == "|}" or stripped == "":
            continue
        else:
            # 续行：并入上一个格（wikitable 的多行单元格写法）
            if cur_row.cells:
                cur_row.cells[-1].raw += "\n" + s
            elif cur_cell is not None:
                cur_cell.raw += "\n" + s
    flush_cell()
    if cur_row is not None:
        rows.append(cur_row)
    rows = [r for r in rows if r.cells]
    for r in rows:
        for c in r.cells:
            c.text, c.empty = _clean_cell_text(c.raw)
    return Table(rows=rows, caption="；".join(captions))


# ---------- 裸 HTML <table> 解析 ----------

_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr\s*>", re.DOTALL | re.IGNORECASE)
_CELL_START_RE = re.compile(r"<(t[dh])\b([^>]*)>", re.IGNORECASE)
_CELL_END_RE = re.compile(r"</t[dh]\s*>\s*$", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_html_table(body: str) -> Table:
    """T32 09-27 修的坑：旧代码要求 `<td>…</td>` 显式配对闭合，但真实维基页面
    有老式"标签汤"写法——`<td>` 之间互相顶替式隐式收尾，全篇没有一个 `</td>`
    （如 宋書/卷11／卷12、魏書/卷107上／107下／113 的律曆志表：
    `<tr><td>A<td>B<td>C</tr>`）。旧写法遇到这种表直接找不到任何格子，
    `find_tables()` 判"0 个表"，与暂行格式里记的块数对不上，整章拒绝转换。
    改成按"起始标签切分"：一格的内容 = 从它的起始标签之后，到下一个起始
    标签之前（或到本行结尾）——不管中间有没有显式收尾，两种写法通吃；
    如果确实写了显式收尾（`</td>`／`</th>`），顺手把它从内容尾部摘掉，
    不留作正文。"""
    rows: list[Row] = []
    for trm in _TR_RE.finditer(body):
        row_html = trm.group(1)
        is_header = False
        cells: list[Cell] = []
        starts = list(_CELL_START_RE.finditer(row_html))
        for i, sm in enumerate(starts):
            tag, attrs = sm.group(1), sm.group(2)
            if tag.lower() == "th":
                is_header = True
            end = starts[i + 1].start() if i + 1 < len(starts) else len(row_html)
            inner = _CELL_END_RE.sub("", row_html[sm.end():end])
            colspan = int(_COLSPAN_RE.search(attrs).group(1)) if _COLSPAN_RE.search(attrs) else 1
            rowspan = int(_ROWSPAN_RE.search(attrs).group(1)) if _ROWSPAN_RE.search(attrs) else 1
            raw = guji_clean.decode_html_entities(_TAG_RE.sub(" ", inner)).strip()
            text, is_empty = _clean_cell_text(raw)
            cells.append(Cell(text=text, raw=raw, colspan=colspan, rowspan=rowspan, empty=is_empty))
        if cells:
            rows.append(Row(is_header=is_header, cells=cells))
    return Table(rows=rows)


# ---------- 从原始 wikitext 里找出所有表格块（可能不止一个） ----------

_WT_TABLE_RE = re.compile(r"\{\|.*?\n\|\}", re.DOTALL)
_HTML_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table\s*>", re.DOTALL | re.IGNORECASE)


def prepare_wikitext(page_title: str, raw_content: str) -> str:
    """转录展开＋`<onlyinclude>`裁切＋"第N部分"子页展开（T22 新加，见文件头说明）。
    三步对不需要它们的页面都是空操作，可以对全部页面统一调用。"""
    content = fetch_24shi.resolve_transclusions(raw_content)
    content = fetch_24shi._extract_onlyinclude(content)
    content = fetch_24shi._expand_part_links(page_title, content)
    return content


def find_tables(wikitext: str) -> list[Table]:
    tables: list[Table] = []
    for m in _WT_TABLE_RE.finditer(wikitext):
        body = m.group(0)
        body = body.split("\n", 1)[1] if "\n" in body else ""  # 去掉开头 `{| class=...` 那一行
        t = parse_wikitable(body)
        if t.rows:
            tables.append(t)
    for m in _HTML_TABLE_RE.finditer(wikitext):
        t = parse_html_table(m.group(1))
        if t.rows:
            tables.append(t)
    return tables


# T22 09-27 实测踩到：宋史/卷234（revid=2551843）宗室世系表第 803、809 行（0-indexed，
# 表 0）源 wikitext 本身各少写了一个 `|`（空白格）——不是我们的清洗管线弄丢的，
# 该表全篇 0 处 rowspan/colspan（`grep -c rowspan` 核过），纯靠"每一代固定一列"
# 的排版规矩堆 1648 行空 `|` 占位，这两行物理上就是比别的行少一格。
# 靠什么定位缺的是哪一列：这类表"世代＝固定列"贯穿全篇（如本例 802/804/805/806
# 行的「嗣」字辈全部落在同一列，799/804/811 行的「彥／夫／時／若」各代同理），
# 拿第 803/809 行现有内容对齐前后 10 行的同代字样逐一核对列位置，两行都对得上
# "缺的是内容前面的空白格"（而不是尾部）——见本道 done 单细节，不是拍脑袋补的。
# 只认这两个精确签名（按该行去空格后的实际内容比对），源文本再变动、或别的页面
# 出现类似列数不齐，一律不套用这个表，直接报错，不静默展开到别处。
KNOWN_ROW_GAPS: dict[tuple[str, int], dict[int, tuple[int, str]]] = {
    ("宋史/卷234", 0): {
        803: (1, "嗣瑃"),
        809: (1, "時㣽|若宣|嗣鍒"),
    },
}


def apply_known_row_gaps(page_title: str, tables: list[Table]) -> list[Table]:
    """给 `find_tables()` 的结果打这份定点补丁（见上）；不在表里不动，命中了但
    对不上签名／列数就报错，绝不悄悄套到别的行或别的页面上。"""
    for table_idx, table in enumerate(tables):
        fixes = KNOWN_ROW_GAPS.get((page_title, table_idx))
        if not fixes:
            continue
        total_cols = table.n_cols
        for row_idx, (n_missing, expect_content) in fixes.items():
            if row_idx >= len(table.rows):
                raise ValueError(f"{page_title} 表{table_idx}：补丁指向的第 {row_idx} 行不存在，源文结构变了，拒绝套用")
            row = table.rows[row_idx]
            actual_content = "|".join(c.text for c in row.cells if not c.empty)
            cur_cols = sum(c.colspan for c in row.cells)
            if actual_content != expect_content or cur_cols != total_cols - n_missing:
                raise ValueError(
                    f"{page_title} 表{table_idx} 第{row_idx}行：补丁签名对不上"
                    f"（现有内容 {actual_content!r}、{cur_cols}/{total_cols} 列，"
                    f"预期内容 {expect_content!r}、缺 {n_missing} 格），源文本又变了，拒绝套用"
                )
            for _ in range(n_missing):
                row.cells.insert(0, Cell(text="", raw="", colspan=1, rowspan=1, empty=True))
    return tables


# ---------- 推荐记法渲染（:::table 容器块，方案 §二） ----------


def _cell_notation(cell: Cell) -> str:
    if cell.empty:
        body = "_"
    else:
        body = cell.text.replace("|", "\\|")
    suffix = ""
    if cell.colspan > 1:
        suffix += f"{{{cell.colspan}}}"
    if cell.rowspan > 1:
        suffix += f"^{cell.rowspan}"
    return body + suffix


def _row_grid_width(row: Row, pending: dict[int, int]) -> int:
    """按"续格插入 + 自身格子"交错展开一行，返回这一行的视觉宽度，并原地更新
    `pending`（供下一行使用）。不设总列数上限——纯粹按这一行自己的格子数
    （含 colspan）加上插进来的续格数来算，交给调用方决定"最大宽度是多少"。"""
    col = 0
    cell_iter = iter(row.cells)
    while True:
        if pending.get(col, 0) > 0:
            pending[col] -= 1
            col += 1
            continue
        cell = next(cell_iter, None)
        if cell is None:
            return col
        if cell.rowspan > 1:
            for k in range(col, col + cell.colspan):
                pending[k] = cell.rowspan - 1
        col += cell.colspan


def render_notation(table: Table) -> str:
    """按"视觉网格"逐列摆格：真 rowspan 的格子只在起始行写一次（带 `^n` 后缀），
    它续占的下几行在对应列位置写 `^`（续格标记，取账簿"仝上"传统写法），
    使每一行的格数 = 表格总列数，人工读 `.md` 源文件时列对列不必心算 rowspan。
    （方案 §一·2 实测：24/129 章有真实 colspan/rowspan，见 §一·2 全量扫描，
    此前只凭 6 个样例判断"没见过"是误判，已在方案文档更正。）

    T32 09-27 修的坑：总列数不能只看表头行（`table.rows[0]`）——真实数据里
    表头行本身可能比正文窄（如 明史/卷111「紀年｜七卿除罷」这个 2 格的
    节标题行，真正的列宽由下一行「吏部尚書｜戶部尚書｜…｜左右都御史」
    （8 格）撑开；金史/卷59、明史/卷101、元史/卷054 等也踩了同一个坑，
    只是没这么极端）。改法与生产端 `guji-table.ts` 的 `columns` 定义
    （"取各行按 colspan、续格计占位宽度的最大值"）保持一致：先跑一遍
    `_row_grid_width` 算出每行的真实展开宽度，取最大值当总列数，再正式渲染。
    """
    if not table.rows:
        return ":::table\n:::"
    probe_pending: dict[int, int] = {}
    total_cols = max((_row_grid_width(r, probe_pending) for r in table.rows), default=0)
    # pending[col] = 剩余续占行数（不含本行）；仅用于渲染续格标记，不改变 Cell 本身
    pending: dict[int, int] = {}
    lines = [":::table"]
    for row in table.rows:
        prefix = "!" if row.is_header else ""
        out_cells: list[str] = []
        col = 0
        cell_iter = iter(row.cells)
        while col < total_cols:
            if pending.get(col, 0) > 0:
                out_cells.append("^")
                pending[col] -= 1
                col += 1
                continue
            cell = next(cell_iter, None)
            if cell is None:
                # T32 09-27 修的坑：源 wikitext 里真有"本行天然比表头短"的行
                # （如 海國圖志/卷072 逐日历表里，"'''正月'''小建甲寅…"这种整月
                # 分隔行只写了 1 个格，没有 `||` 续格，也没有显式 colspan 属性）。
                # 这不是解析漏了，是源文本身没给够格子——按 HTML `<table>` 的真实
                # 渲染行为（`<tr>` 格数不足表头时，浏览器不会自动撑满，只是右边
                # 空着），在视觉网格里给它补满显式空格 `_`，而不是把行截断得比
                # 表头短（截断会让 F-MD-09 判"列不齐"，且丢了"这几格本来就是空
                # 的"这个信息）。
                out_cells.append("_")
                col += 1
                continue
            out_cells.append(_cell_notation(cell))
            if cell.rowspan > 1:
                for k in range(col, col + cell.colspan):
                    pending[k] = cell.rowspan - 1
            col += cell.colspan
        lines.append(f"{prefix}{' | '.join(out_cells)}")
    lines.append(":::")
    return "\n".join(lines)


# ---------- 浏览器可看的 HTML 预览（真 <table>，rowspan/colspan 原生展开） ----------

_JZ_RE = re.compile(r"<([^<>]+)>")  # guji-markdown 夹注 `<...>` -> <span class=jz>


def _inline_html(text: str) -> str:
    """把 cell.text 里的 guji-markdown `<…>` 夹注渲染成小字 span，其余原样转义。
    只处理夹注（本方案表格样例最常见的行内记号），书名号/专名号原样保留在文字里。"""
    out = []
    last = 0
    for m in _JZ_RE.finditer(text):
        out.append(escape(text[last : m.start()]))
        out.append(f'<span class="jz">{escape(m.group(1))}</span>')
        last = m.end()
    out.append(escape(text[last:]))
    return "".join(out)


def render_preview_html(table: Table, title: str, source_note: str) -> str:
    rows_html = []
    for row in table.rows:
        cells_html = []
        tag = "th" if row.is_header else "td"
        for c in row.cells:
            attrs = ""
            if c.colspan > 1:
                attrs += f' colspan="{c.colspan}"'
            if c.rowspan > 1:
                attrs += f' rowspan="{c.rowspan}"'
            content = "&nbsp;" if c.empty else _inline_html(c.text)
            cells_html.append(f"<{tag}{attrs}>{content}</{tag}>")
        rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: "Noto Serif CJK TC", "Songti TC", serif; margin: 2em; background: #faf7f0; color: #2a2015; }}
h1 {{ font-size: 1.2em; }}
.note {{ color: #86745a; font-size: .85em; margin-bottom: 1em; }}
table {{ border-collapse: collapse; width: 100%; font-size: .92em; }}
th, td {{ border: 1px solid #c9b998; padding: 4px 8px; vertical-align: top; text-align: left; }}
th {{ background: #eee0c4; }}
.jz {{ font-size: .8em; color: #7b6a54; }}
</style></head>
<body>
<h1>{escape(title)}</h1>
<p class="note">{escape(source_note)}</p>
<table>{''.join(rows_html)}</table>
</body></html>"""


# ---------- from-stored 模式：只吃 book-text 已存的 <!-- table --> 线性化文本 ----------

_STORED_TABLE_RE = re.compile(r"<!-- table -->\n(.*?)\n<!-- /table -->", re.DOTALL)


def convert_from_stored(md_text: str) -> tuple[str, dict]:
    """机械兜底：给已经丢了空格/表头/合并信息的线性化文本，按第一行列数
    在行尾补 `_` 占位，并把补了多少处上报（降级必须可数）。"""
    report = {"tables": 0, "rows_padded": 0, "rows_total": 0}

    def repl(m: "re.Match[str]") -> str:
        report["tables"] += 1
        rows = [r for r in m.group(1).split("\n") if r.strip() != ""]
        if not rows:
            return m.group(0)
        header_cols = len(rows[0].split(" | "))
        out_lines = ["!" + rows[0]]
        for r in rows[1:]:
            report["rows_total"] += 1
            cells = r.split(" | ")
            if len(cells) < header_cols:
                cells = cells + ["_"] * (header_cols - len(cells))
                report["rows_padded"] += 1
            out_lines.append(" | ".join(cells))
        return ":::table\n" + "\n".join(out_lines) + "\n:::"

    new_text = _STORED_TABLE_RE.sub(repl, md_text)
    return new_text, report


# ---------- T22 就地替换：把现存 <!-- table --> 块换成 refetch 出的 :::table 记法 ----------

_NOTATION_TABLE_RE = re.compile(r":::table\n(.*?)\n:::", re.DOTALL)
# 供 verify_conversion() 算"块外文本"用：跟 replace_stored_blocks() 的替换范围对齐——
# 有 table.caption 时前面会多出一行 `**说明**\n\n`（如宋史/卷215/第一部分「燕王房」），
# 那一行是块替换范围的一部分，不是「块外」，这里一并吃掉，否则会误判块外文本变了。
_NOTATION_BLOCK_WITH_CAPTION_RE = re.compile(r"(?:\*\*[^\n]*\*\*\n\n)?:::table\n(?:.*?)\n:::", re.DOTALL)
# 匹配 render_notation() 输出的单元格结尾后缀：可选 `{colspan}`，再可选 `^rowspan`。
# 裸续格标记 "^"（无数字）落进 body 分支，colspan/rowspan 都按默认值 1 处理——
# 和 render_notation() 里 pending[col] 记账的语义一致（续格只占 1 列）。
_TOKEN_SUFFIX_RE = re.compile(r"^(?P<body>.*?)(?:\{(?P<colspan>\d+)\})?(?:\^(?P<rowspan>\d+))?$")


def han_char_count(text: str) -> int:
    """汉字数：直接复用 `guji_clean.count_han()`（含 CJK 扩展 A／兼容区），
    不新造一套字符区间——避免跟管线其余环节的字数统计口径不一致。"""
    return guji_clean.count_han(text)


def _token_colspan(token: str) -> int:
    m = _TOKEN_SUFFIX_RE.match(token)
    if m and m.group("colspan"):
        return int(m.group("colspan"))
    return 1


def notation_row_cols(line: str) -> int:
    """算一行 `:::table` 记法展开合并格后的视觉列数：表头行去掉开头 `!`，
    按 `" | "` 切列（切之前把转义的 `\\|` 换成哨兵，避免把单元格内容里转义
    过的竖线当成列分隔符），每列按 `_token_colspan` 累加。"""
    s = line[1:] if line.startswith("!") else line
    sentinel = "\x01"
    tokens = s.replace("\\|", sentinel).split(" | ")
    return sum(_token_colspan(t.replace(sentinel, "\\|")) for t in tokens)


def replace_stored_blocks(md_text: str, tables: list[Table]) -> str:
    """按出现顺序，把 `md_text` 里全部 `<!-- table -->...<!-- /table -->` 块换成
    对应 `tables`（同一页 `find_tables()` 的返回，同为文档序）渲染出的 `:::table`
    记法。块外文本原样透传（直接按原字符串切片拼接，不重新排版）。块数与
    `tables` 数不一致时直接报错——T22 任务书铁律「块外不动，块内要么转对要么报错」，
    不做"数目对不上就凑活对齐"的猜测。
    """
    blocks = list(_STORED_TABLE_RE.finditer(md_text))
    if len(blocks) != len(tables):
        raise ValueError(
            f"现存 <!-- table --> 块数（{len(blocks)}）与重抓 wikitext 表格数（{len(tables)}）不一致，拒绝转换"
        )
    out = []
    last = 0
    for blk, table in zip(blocks, tables):
        out.append(md_text[last:blk.start()])
        piece = render_notation(table)
        if table.caption:
            piece = f"**{table.caption}**\n\n{piece}"
        out.append(piece)
        last = blk.end()
    out.append(md_text[last:])
    return "".join(out)


def verify_conversion(orig_text: str, new_text: str) -> dict:
    """转换时的即时自检（正式把关仍以 `validate_text_format.py` 的 `F-MD-09
    --strict` 为准，这里只是转换当场给个反馈，免得等一整批转完才发现问题）：
    - 块外文本是否原样（`<!-- table -->` 块换成 `\\x00`、`:::table` 块也换成
      `\\x00` 之后两边字符串应完全相同）；
    - 全篇汉字数转换后是否不降（任务书要求：只增不减，原来被吃掉的格子补回来）；
    - 每个 `:::table` 块内，每一行展开合并格后的列数是否都等于表头列数。
    """
    outside_orig = _STORED_TABLE_RE.sub("\x00", orig_text)
    outside_new = _NOTATION_BLOCK_WITH_CAPTION_RE.sub("\x00", new_text)
    report = {
        "outside_unchanged": outside_orig == outside_new,
        "han_before": han_char_count(orig_text),
        "han_after": han_char_count(new_text),
        "col_mismatches": [],
    }
    report["han_ok"] = report["han_after"] >= report["han_before"]
    for bi, m in enumerate(_NOTATION_TABLE_RE.finditer(new_text)):
        rows = [r for r in m.group(1).split("\n") if r.strip() != ""]
        if not rows:
            continue
        header_cols = notation_row_cols(rows[0])
        for ri, r in enumerate(rows):
            n = notation_row_cols(r)
            if n != header_cols:
                report["col_mismatches"].append({"block": bi, "row": ri, "cols": n, "header_cols": header_cols})
    report["col_ok"] = len(report["col_mismatches"]) == 0
    return report


def convert_chapter(page_title: str, md_path: Path, dry_run: bool = False) -> dict:
    """单章就地转换：refetch 该页 wikitext → 解析表格 → 替换 `md_path` 里的
    `<!-- table -->` 块 → 自检 → （非 dry-run 时）写回。返回一份可直接
    `json.dumps` 的报告，供 `convert-book` 聚合与人工核对。"""
    r = wiki_api.get_revision(page_title)
    if not r.get("exists"):
        return {"page_title": page_title, "md_path": str(md_path), "error": "页面不存在"}
    tables = apply_known_row_gaps(page_title, find_tables(prepare_wikitext(page_title, r["content"])))
    orig_text = md_path.read_text(encoding="utf-8")
    try:
        new_text = replace_stored_blocks(orig_text, tables)
    except ValueError as e:
        return {"page_title": page_title, "md_path": str(md_path), "n_tables_wiki": len(tables), "error": str(e)}
    verify = verify_conversion(orig_text, new_text)
    if not dry_run:
        md_path.write_text(new_text, encoding="utf-8")
    return {
        "page_title": page_title,
        "md_path": str(md_path),
        "revid": r.get("revid"),
        "n_tables": len(tables),
        **verify,
    }


def cmd_convert_book(index_json: Path, chapters: "list[int] | None", dry_run: bool = False, report_out: "Path | None" = None):
    idx = json.loads(index_json.read_text(encoding="utf-8"))
    chap_dir = index_json.parent
    targets = [c for c in idx["chapters"] if c.get("has_table") and (chapters is None or c["n"] in chapters)]
    results = []
    for c in targets:
        md_path = chap_dir / c["file"]
        res = convert_chapter(c["page_title"], md_path, dry_run=dry_run)
        res["n"] = c["n"]
        results.append(res)
        ok = "error" not in res and res.get("outside_unchanged") and res.get("han_ok") and res.get("col_ok")
        print(f"[{'OK' if ok else '异常'}] 第 {c['n']} 卷 {c['page_title']}：{json.dumps(res, ensure_ascii=False)}")
    if report_out:
        report_out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"报告已写入 {report_out}")
    if not dry_run and all("error" not in r for r in results) and results:
        idx["table_notation"] = "guji-table-v1"
        index_json.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已在 {index_json} 加 table_notation: guji-table-v1（has_table／revision 未动）")
    return results


# ---------- CLI ----------

DEMO_SAMPLES = [
    # (page_title, 展示用文件名, 说明)
    ("宋史/卷210", "01-宋史卷210-宰輔年表", "纯矩阵＋空单元格丢失：6 列固定，源文显式 `||   ||` 三个空格被现有管线吞掉"),
    ("漢書/卷013", "02-漢書卷013-異姓諸侯王表", "多层表头＋真实 colspan＋夹注：两行表头（`楚` colspan=4 等），夹注用 `{{*|…}}` 模板"),
    ("新唐書/卷073上", "03-新唐書卷073上-宰相世系表", "稀疏矩阵：12 列固定，几乎全用全角空格「　」占位，无 colspan/rowspan"),
    ("元史/卷096", "04-元史卷096-食貨志官俸表", "小表＋前导空格错位：3 列，首格为空时现有管线整行错位"),
    ("遼史/卷66", "05-遼史卷066-皇族表", "真实 rowspan＋colspan 密集：全量扫描 24/129 章命中真合并格的代表，验证 `^`／`{n}` 续格标记"),
    ("遼史/卷42", "06-遼史卷042-曆象志損益表", "裸 HTML <table> 写法：`<th>`/`<td>`/`<p>` 规范嵌套，与前 5 例的 wikitext `{|...|}` 对照"),
]


def cmd_refetch(page_title: str, out_dir: Path, label: str | None = None, note: str = ""):
    r = wiki_api.get_revision(page_title)
    if not r.get("exists"):
        print(f"[跳过] {page_title} 页面不存在", file=sys.stderr)
        return
    tables = apply_known_row_gaps(page_title, find_tables(prepare_wikitext(page_title, r["content"])))
    if not tables:
        print(f"[跳过] {page_title} 未解析出表格", file=sys.stderr)
        return
    slug = label or page_title.replace("/", "-")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_parts, html_parts = [], []
    for i, t in enumerate(tables):
        md_parts.append(render_notation(t))
        html_parts.append(
            render_preview_html(
                t,
                f"{page_title} 表 {i + 1}/{len(tables)}",
                f"来源：zh.wikisource.org「{page_title}」revid={r.get('revid')}；{note}",
            )
        )
    (out_dir / f"{slug}.md").write_text("\n\n".join(md_parts), encoding="utf-8")
    (out_dir / f"{slug}.html").write_text(
        "\n<hr>\n".join(html_parts) if len(html_parts) > 1 else html_parts[0], encoding="utf-8"
    )
    print(f"[完成] {page_title} -> {slug}.md / {slug}.html（{len(tables)} 个表）")


def cmd_demo(out_dir: Path):
    for page_title, slug, note in DEMO_SAMPLES:
        cmd_refetch(page_title, out_dir, label=slug, note=note)
    print(f"\n六个样例已产出到 {out_dir}，浏览器直接打开对应 .html 即可看。")


def cmd_from_stored(md_path: Path):
    text = md_path.read_text(encoding="utf-8")
    new_text, report = convert_from_stored(text)
    print(json.dumps(report, ensure_ascii=False))
    out_path = md_path.with_suffix(".converted.md")
    out_path.write_text(new_text, encoding="utf-8")
    print(f"写入 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("refetch", help="联网重抓一个维基文库页面并转换（推荐路径）")
    p1.add_argument("page_title")
    p1.add_argument("--out", type=Path, default=Path("."))

    p2 = sub.add_parser("from-stored", help="只吃 book-text 已存的线性化文本，机械兜底（不联网）")
    p2.add_argument("md_path", type=Path)

    sub.add_parser("demo", help="跑方案挑的 6 个样例")

    p3 = sub.add_parser("convert-chapter", help="T22：refetch 一页 wikitext，就地替换某个 book-text 章节 md 里的 <!-- table --> 块")
    p3.add_argument("page_title")
    p3.add_argument("md_path", type=Path)
    p3.add_argument("--dry-run", action="store_true", help="只跑自检不写回文件")

    p4 = sub.add_parser("convert-book", help="T22：按 index.json 里 has_table 的章节批量 convert-chapter，并给 index.json 加 table_notation")
    p4.add_argument("index_json", type=Path)
    p4.add_argument("--chapters", help="逗号分隔的卷号子集，默认全部 has_table 章")
    p4.add_argument("--dry-run", action="store_true", help="只跑自检不写回文件")
    p4.add_argument("--report", type=Path, help="把每章的转换报告写成 JSON 到这个路径")

    args = ap.parse_args()
    if args.cmd == "refetch":
        cmd_refetch(args.page_title, args.out)
    elif args.cmd == "from-stored":
        cmd_from_stored(args.md_path)
    elif args.cmd == "demo":
        cmd_demo(Path(__file__).resolve().parent.parent / "整体设计" / "展示样张" / "表格")
    elif args.cmd == "convert-chapter":
        res = convert_chapter(args.page_title, args.md_path, dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif args.cmd == "convert-book":
        chapters = [int(x) for x in args.chapters.split(",")] if args.chapters else None
        cmd_convert_book(args.index_json, chapters, dry_run=args.dry_run, report_out=args.report)


if __name__ == "__main__":
    main()
