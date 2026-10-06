# `original/index.json`：一章有哪些层（10-06 文本总管定）

> 只管 `original`（本项目从书影做出来的文本）。版本号见 [VERSIONING.md](VERSIONING.md)，各层文件格式见 guji-format 规范 01（pages）、04（标点）、05（实体）。

## 一、章条目里声明各层文件

`original/index.json` 的 `chapters[]` 每一章用 `*_file` 字段声明这一章有哪些层：**有这个字段 = 有这一层**，没有就是没有。前端、校验器都按字段读，不按「目录里有没有这个文件」猜，也不再用 `has_warp`、`warp_data` 这类布尔字段。

| 字段 | 文件 | 这一层是什么 | 必填 |
|---|---|---|---|
| `lines_file` | `NNN.lines.md` | 文本：按「页:列:格」定下的字流 | 是 |
| `punct_file` | `NNN.punct.json` | 标点（含书名号《》、分段） | 否 |
| `entity_file` | `NNN.entity.json` | 实体（人、地、书、官、朝代，链 book-index） | 否 |
| `pages_file` | `NNN.pages.json` | **对读**：每页每格的字框坐标（guji-pages/0.1，规范 01） | 否 |
| `norm_file` | `NNN.norm.json` | 规范层：异体 → 通行字 | 否 |
| `rich_file` | `NNN.rich.md` | 由上面几层合成的阅读稿（派生物，可重生成） | 否 |

- 字段值是同目录下的文件名；写了就必须存在。
- 版本号字段（`text_version`、`punct_version`、`entity_version`）也在同一条目里，见 VERSIONING.md。
- `has_json` 是另一回事（章是否有 `NNN.json` 检索索引），不变。

例：

```json
{ "n": 2, "file": "002", "title": "卷首二（經部總敘·易類一至三）",
  "lines_file": "002.lines.md", "punct_file": "002.punct.json", "entity_file": "002.entity.json",
  "pages_file": "002.pages.json", "norm_file": "002.norm.json", "rich_file": "002.rich.md",
  "pages": "1-188" }
```

## 二、页码怎么对到书影（IIIF）

一条规则贯通各层，**不需要另外的对照表**：

- **册号** = 章条目的 `n` = 标点、实体文件顶层的 `volume` = `pages.json` 的 `volume.index` = IIIF canvas 网址里的两位册号。
- **页号 N**：`lines.md` 里的 `<!-- pN -->`、标点和实体锚点 `页:列:格` 的「页」、`pages.json` 里每页的 `page.index`，都是同一个数：这一册扫描图的**顺序号，从 1 起**（不是刻本的版心叶码）。
- 对应的 IIIF canvas：`https://data.kaiyuanguji.com/iiif/<book_id>/canvas/<册号两位>/<N 四位>`，即 `pages.json` 里该页的 `canvas.id`（`seq` = N 补足四位）。
- 章条目的 `pages`（如 `"1-188"`）是这一章覆盖的页号范围，首尾都含。

所以前端从任一层拿到「页 N」，直接拼出 canvas，或到 `pages.json` 里找 `page.index == N` 那一页即可。
