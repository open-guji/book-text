# `original`：一章有哪些文件（10-06 用户定）

> 只管 `original`（本项目从书影做出来的文本）。格式见 guji-format 规范：01 cord、02 char、03 markdown、04 punct、05 entity。版本号见 [VERSIONING.md](VERSIONING.md)。

## 一、文件和代号

代号就是文件名里的那个词，说的时候就用代号。

| 代号 | 文件 | 是什么 | 性质 | 存在哪 |
|---|---|---|---|---|
| **char** | `NNN.char.json` | 每一格定下的字和版式。**文本版本号跟踪它** | 真源 | main |
| **cord** | `NNN.cord.json` | 每一格的像素框，**不存字**，按格位 key 对到 char | 真源 | main |
| **punct** | `NNN.punct.json` | 标点、分段、书名号 | 真源 | main |
| **entity** | `NNN.entity.json` | 专名，链 book-index | 真源 | main |
| **norm** | `NNN.norm.json` | 异体→通行字，按格位 | 真源 | main |
| **decision** | `NNN.decision.json` | 不确定的字的其他候选 | 真源 | **待设计**，先留白 |
| **lines** | `NNN.lines.md` | 一列一行的分行稿，由 char 生成 | 生成 | 生成分支 |
| **rich** | `NNN.rich.md` | 带标点、专名的阅读稿，由 char＋punct＋entity（＋norm）生成 | 生成 | 生成分支 |

- **真源**：仓里别的文件算不出来，改动要靠人或模型做。main 只存真源。
- **生成**：脚本从 main 的真源算出来，不手改；放在单独的生成分支上，main 不存。reflow（无标点的自然段稿）不再单独生成，直接出 rich。
- **两种坐标**：**cell** 是格位 key `页:列:格[子列]`（如 `3:5:12a`），char、punct、entity、norm 都用它；**box** 是像素框 `[x, y, w, h]`，只在 cord 里。
- 原来说的 Level 1／2／3、像素坐标层、文本层都不再用：Level 1 → cord（＋待设计的 decision），Level 2 → char，Level 3a → lines。
- 书影、cv 的中间产物、人裁事件、字形库不在 book-text，留在 IA 和 guji-workspace。
- 抽检表、运行报告、新实体候选表、模型对照稿这些工作文件只放 `wip/` 分支，不进 main。

## 二、章条目里声明各层文件

`original/index.json` 的 `chapters[]` 每一章用 `*_file` 字段声明有哪些文件：**有这个字段 = 有这个文件**，写了就必须存在。

| 字段 | 文件 | 必填 |
|---|---|---|
| `char_file` | `NNN.char.json` | 是 |
| `cord_file` | `NNN.cord.json` | 否 |
| `punct_file` | `NNN.punct.json` | 否 |
| `entity_file` | `NNN.entity.json` | 否 |
| `norm_file` | `NNN.norm.json` | 否 |
| `decision_file` | `NNN.decision.json` | 否（待设计） |

生成分支上的 `index.json` 另外加 `lines_file`、`rich_file`。前端读哪些文件、读哪个分支，由网站决定。

例（main）：

```json
{ "n": 2, "file": "002", "title": "卷首二（經部總敘·易類一至三）",
  "char_file": "002.char.json", "cord_file": "002.cord.json",
  "punct_file": "002.punct.json", "entity_file": "002.entity.json", "norm_file": "002.norm.json",
  "text_version": "1.0.0", "punct_version": "1.0.0", "entity_version": "1.0.0",
  "pages": "1-188" }
```

## 三、页码怎么对到书影（IIIF）

一条规则贯通各层，不需要另外的对照表：

- **册号** = 章条目的 `n` = 各文件顶层的 `volume` = IIIF canvas 网址里的两位册号。
- **页号 N**：格位 key 的「页」、cord 里的 `page`，都是这一册扫描图的**顺序号，从 1 起**（不是刻本的版心叶码，版心叶码记在 char 的 `label`）。
- 对应的 IIIF canvas：`https://data.kaiyuanguji.com/iiif/<book_id>/canvas/<册号两位>/<N 四位>`，即 cord 里该页的 `canvas.id`。
- 章条目的 `pages`（如 `"1-188"`）是这一章覆盖的页号范围，首尾都含。

## 四、生成分支

- main 合入后，用脚本从 main 的真源重新生成 lines.md、rich.md，连同 main 的全部内容推到生成分支，提交说明里写它对应的 main 提交号。
- 生成分支只由脚本写，不手改，也不往回并 main。
- 分支名和生成脚本随第一次落地时定（见 overview 卡）。

## 五、现状（10-06）

四庫總目 vol02、vol03 还在 `wip/siku` 上，是旧形态：`lines.md` 是真源，`pages.json` 里带字。要先把它们转成 char、cord，并写好生成脚本，才能按本规范并 main。
