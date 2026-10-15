# 自校文本格式草案 · 样例（T10 道）

服务 [自校文本格式草案.md](../2026-09-自校文本格式草案.md) 的完成判据 §2。

## 文件

- `p0010.json`：样例页数据，格式=草案 §二定义。
- `p0010.export.md`：由 `scripts/export_demo.py` 从 `p0010.json` 派生出的 guji-markdown 文本，证明"格式→guji-markdown"这条派生链路走得通。
- `scripts/export_demo.py`：派生脚本，算法照抄 `open-guji-cv` 仓 `open_guji_cv/render/guji_markdown.py::render_column`（只读实测，未改该仓一字）。

## 数据来源与一个必须说清楚的限制

`p0010.json` 第 1 列（`col: 1`）是**真实数据**：字符、列号、格序号、原图坐标全部取自
`guji-workspace`（私有仓，只读）『96mid1ogzk-欽定四庫全書總目武英殿刻本』
`output/glyph_store/instances/vol01.jsonl` 第 10 页第 1 列前 10 条实例，
坐标经 `bbox_tl_to_tr()`（`open_guji_cv/core/anchor.py:20-32`）从该文件里的
`raw_page_px@top-left` 换算到规范空间 `raw_page_px@top-right`，`width` 取
`data_full/zongmu/vol01/10.png` 实测像素宽 2396（PNG 头部直接解出，未装图像库）。

**第 2 列（`col: 99`）是示意，不是页 10 的真实版式**——原因是**任务书交底之外的一个真实数据缺口**：

`guji-workspace` 的 `.gitignore` 明文排除 `products/`（"2026-09-13 起运行时数据全部归
workspace…products/ 是可重算的数值产物（设计 §5 C 层），不进 git"），也排除 `cache/`。
这意味着 Step3 `cells`（格/抬头/夹注/空白的 `kind` 标记）与 Step7 `seed_admit`
（放行/人裁/阙文判定）这两份**本草案最需要的产物**，在只读 clone 这个仓时**根本拿不到**——
本仓（连同任何一本书的工作区）里没有任何一页能直接读出真实的 `kind`／`slot`／`sub`／
`order`／`unreadable` 组合。`output/glyph_store/instances/*.jsonl`（真源，进 git）只留了
字符层的 `char`／`col`／`idx`／`bbox`，不含这些结构标记。

因此本草案的样例只能做到：**用页 10 真实存在的字符与坐标**（col 1）证明"字符层字段"
（`id`／`char`／`bbox`／坐标换算）站得住；**用构造的 col 99** 证明"格式字段设计"
（抬头 `n_raised`、双行夹注 `sub=a/b`、阙文 `unreadable`、空白 `blank`）能覆盖
`guji-markdown` 现有渲染逻辑处理的全部非字元素分支，并跑通派生脚本验证语法正确——
但 col 99 的具体版式现象（哪个字抬头、哪几个字成对夹注）不代表页 10 真实如此，
每条示意记录都标了 `_note`／`_illustrative` 说明。

**这不是本道自己造出来的缺口**：任务书 §〇·3 交底的 `guji-workspace` 只读范围本身就没有
提到 `products/`，本道核实后如实记入待定问题清单（见草案 §七·1），供 CV 总管/文本总管
判断是否需要另开一条只读取数途径（比如挑一页现场跑一次管线，或由 CV 总管指定一页导出
真实产物快照）。

## 复跑

```bash
cd 项目进展/古籍文本/整体设计/自校格式样例
python3 scripts/export_demo.py
```

无外部依赖（标准库 `json`/`pathlib`），Python 3 即可。
