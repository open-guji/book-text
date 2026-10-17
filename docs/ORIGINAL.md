# `original`：一章有哪些文件（10-06 用户定）

> 条目布局以 guji-format spec/07-book-text-条目布局.md（§2.3、§3.3）为准；manifest 一侧（kind／is_original／source／license）见 spec 07 §二。

> 只管 `original`（本项目从书影做出来的文本）。格式见 guji-format 规范：01 cord、02 char、03 markdown、04 punct、05 entity、06 norm、07 条目布局、08 decision。版本号见 [VERSIONING.md](VERSIONING.md)。

## 一、文件和代号

代号就是文件名里的那个词，说的时候就用代号。

| 代号 | 文件 | 是什么 | 性质 | 存在哪 |
|---|---|---|---|---|
| **char** | `NNN.char.json` | 每一格定下的字和版式。**文本版本号跟踪它** | 真源 | main |
| **cord** | `NNN.cord.json` | 每一格的像素框，**不存字**，按格位 key 对到 char | 真源 | main |
| **punct** | `NNN.punct.json` | 标点、分段、书名号 | 真源 | main |
| **entity** | `NNN.entity.json` | 专名，链 book-index | 真源 | main |
| **norm** | `NNN.norm.json` | 异体→通行字，按格位 | 真源 | main |
| **decision** | `NNN.decision.json` | 不确定的字的其他候选 | 真源 | 规范见 guji-format 08（v0.1 正式；v0.2 增可选 reason／route／route_ref，v0.1 文件仍合法）；校验 F-OV-05 已落地（`scripts/validate_text_format.py`，含 `scripts/tests/test_decision.py`） |
| **lines** | `NNN.lines.md` | 一列一行的分行稿，由 char 生成 | 生成 | 生成分支 |
| **rich** | `NNN.rich.md` | 带标点、专名的阅读稿，由 char＋punct＋entity（＋norm）生成 | 生成 | 生成分支 |

- **真源**：仓里别的文件算不出来，改动要靠人或模型做。main 只存真源。
- **生成**：脚本从 main 的真源算出来，不手改；放在单独的生成分支上，main 不存。reflow（无标点的自然段稿）不再单独生成，直接出 rich。
- **两种坐标**：**cell** 是格位 key `页:列:格[子列]`（如 `3:5:12a`），char、punct、entity、norm 都用它；**box** 是像素框 `[x, y, w, h]`，只在 cord 里。
- 原来说的 Level 1／2／3、像素坐标层、文本层都不再用：Level 1 → cord（＋decision，规范见 guji-format 08），Level 2 → char，Level 3a → lines。
- 书影、cv 的中间产物、人裁事件、字形库不在 book-text，留在 IA 和 guji-workspace。
- 抽检表、运行报告、新实体候选表、模型对照稿这些工作文件只放 `wip/` 分支，不进 main。

## 二、章条目里声明各层文件

`<版本目录>/index.json`（`<版本目录>` 指 manifest 里 `is_original` 为 true 的版本目录，常为 `default/`，旧条目仍可能是 `original/`） 的 `chapters[]` 每一章用 `*_file` 字段声明有哪些文件：**有这个字段 = 有这个文件**，写了就必须存在。

| 字段 | 文件 | 必填 |
|---|---|---|
| `char_file` | `NNN.char.json` | 是 |
| `cord_file` | `NNN.cord.json` | 否（文本线 0.x、校对中的册必填：精校页按格位查像素框；F-OV-04） |
| `punct_file` | `NNN.punct.json` | 否 |
| `entity_file` | `NNN.entity.json` | 否 |
| `norm_file` | `NNN.norm.json` | 否 |
| `decision_file` | `NNN.decision.json` | 否（规范见 08；校验 F-OV-05 已落地） |
| `pending_file` | `NNN.pending.json` | 否（册级待审清单，仅 `proofing: true` 时存在；校验 F-OV-07） |

`NNN.pending.json` 由整理侧导出（GUJI-543 §6.2）：顶层 `rev`（`<册>-r<n>`）、`cv_version`（字符串，首个正式 `cv-vX.Y.Z` tag 前可为 `null`）、`cv_commit`（必填）、`cells`（先只列格号 `cell` 与 `review` 状态；`why`／`cls` 等归 guji-proof 0.2）。坐标是原图轴对齐框。它不是版本线，不进 `*_version`、不进 CHANGES.md。

`chapters[]` 另有 `proofing`（选填布尔，校对中；文本线 0.x 时必填 true，F-OV-06；网站据此挂「欢迎帮助校对」banner）、`text_version`（必填）、`punct_version`（有 punct 时必填）、`entity_version`（有 entity 时必填）、`pages`（选填）、`n`／`file`／`title`；`*_version` 与各文件顶层 `version` 相等（F-OV-01，不手改）。字段见 spec 07 §3.3。版本 `index.json` 顶层字段同见 spec 07 §3.3。

生成分支上的 `index.json` 另外加 `lines_file`、`rich_file`。前端读哪些文件、读哪个分支，由网站决定。

例（main）：

```json
{ "n": 2, "file": "002", "title": "經部總敘·易類一至三",
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
- `derived` 是生成物，不是真源，**可以落后于 main**：线上读的是 main，不读它，落后不影响线上。重新生成与运维不属于 Schema落地项目，由文本块队列另案处理（overview #417）。10-14 洛杉矶实测：`derived` 在 `85123a73e4`（10-10 18:10），main 在其后又前进 31 个提交。

## 五、现状（10-11）

四庫總目 vol02、vol03 已并 main，在 `Book/g/z/k/96mid1ogzk/default/` 下，五层齐全（char／cord／punct／entity／norm）；vol03 另有 `003.decision.json`。
