# book-text 版本号与仓库流程（摘要）

> 条目布局以 guji-format spec/07-book-text-条目布局.md（§2.3、§3.3）为准。

> 规范全文：overview `项目进展/古籍文本/整体设计/2026-10-文本版本号与仓库流程.md`（v2，用户 10-05 定）。
> 本文是摘要，两边不一致时以规范全文为准。落地任务卡：open-guji-core/overview#400（T67）。

## 一、仓库流程

1. **main 受保护，一律走 PR。** 一批活开一个分支（`<道名>-<主题>`，如 `t65-wiki-match`），分支上可以多次提交，整批做完开**一个** PR，审过 **squash merge**。`wip/` 前缀是反复改动中的工作分支（如 `wip/siku-vol02`），用户点头前不并 main。
2. **谁来合**：日常批次（入库、修正、撤除 50 部以内）文本总管审过就合。以下等用户点头：撤除超过 50 部；改全仓结构或规范；`original` 任何一条线升 **major**。
3. **开 PR 前**：把 main 合进分支，用 overview `scripts/book-text/build_texts_index.py --root <本仓>` 重建 `index/texts`，结果贴进 PR 描述：
   - `validate_text_format.py <本仓> --strict --baseline <overview>/项目进展/古籍文本/scripts/format_baseline.json` 退出码 0；
   - `validate-collated.py --root <本仓>`（不带 `--strict`）退出码 0，且报告里没有本 PR 新增的问题（main 上已知存量：`d59f1iqd854w/default` 多一个 `108.md`）；
   - 重建索引后没有未提交的 diff。
4. 不设 CI 必过检查，靠审 PR 把关。

## 二、跟踪范围

| 内容 | 跟不跟踪 | 说明 |
|---|---|---|
| `original`：本项目从书影做出来的文本 | **跟踪，分三条线** | 本文的对象 |
| 维基文库、Kanripo、识典的转录（`default`、`kanripo/`、`wikisource-2/` 等） | 不跟踪 | 来源修订号记在 `source`；现有 `revision: "1.0.0"` 留着不维护 |
| 整理本（`kind=collated`） | 不在本方案内 | 沿用 book-index 整理本版本规定和 `bump-collated.py` |

## 三、三条线

| 线 | 文件 | 跟踪什么 | 不管什么 |
|---|---|---|---|
| 文本 | `NNN.char.json` | 每一格定下的字：哪格是哪个字、分列、夹注、抬头、阙文（guji-format 02） | 像素框（`cord.json`，CV 产物）、候选字（`decision.json`） |
| 标点 | `NNN.punct.json` | 句读、点号、书名号、引号、分段 | 字 |
| 实体 | `NNN.entity.json` | 专名区间、类型（人、地、书、官、朝代）、链到 book-index 的 id | 字、标点 |

### 版本号落点（每册一套）

```jsonc
// <版本目录>/index.json
{ "chapters": [
  { "n": 2, "file": "002",
    "text_version": "1.4.1", "punct_version": "1.2.0", "entity_version": "1.0.3"
  } ] }

// <版本目录>/002.char.json 顶层
{ "version": "1.4.1",
  "review": { … } }             // 仅文本线 major ≥2 时

// <版本目录>/002.punct.json、002.entity.json 顶层
{ "version": "1.2.0", "text_version": "1.4.1",
  "review": { … } }             // 仅本线 major ≥2 时
```

- `index.json` 的 `text_version`／`punct_version`／`entity_version` 都是镜像，必须和 char、punct、entity 各自顶层的 `version` 一致；网站从 `index.json` 读三线版本。
- **过渡**：10-06 以前文本线跟踪的是 `lines.md`，文本线验收记录放在 `index.json` 的 `text_review`。`bump_original.py` 和校验器 F-OV-* 改读 char.json 之前，仍按旧口径跑。
- 验收记录（`review`）至少含 `date`、`signed_by`、`sample`（抽检数据）。
- 每次升版本，在 `<版本目录>/CHANGES.md`（`<版本目录>` 同上：manifest 里 `is_original` 为 true 的版本目录，常为 `default/`，旧条目仍可能是 `original/`） 记一行：`| 日期 | 册 | 线 | 旧→新 | 说明 | PR |`。「册」一栏写 `<条目 id>/<章 NNN>`（如 `96mid1ogzk/002`），一次动几册就记几行，章级历史可按这一栏追。

### 三条线之间
- 标点、实体靠坐标锚在文本上，每个锚点带校验字：标点 `anchor`＋`pre_char`，实体 `anchor.start..end`＋`text`。
- 文本改了：锚点全对得上 → 伴生层只把 `text_version` 跟过去，**不升**它的版本；对不上 → 伴生层按规模修，修好后自己升 patch 或 minor。
- **伴生层 major 不得高于文本线**：文本还没到出版级，标点、实体也不能先升（F-OV-01 查）。
- **每册只入库一份**标点稿、一份实体稿；模型对照稿只在本地测试，不进仓。
- **书名两层都记**：标点层出一对 `《》`，实体层出 `work` 实体挂 book-index id，两层起止一致。

## 四、三级怎么升

- **major = 质量等级**：1 可用、2 出版级、3 定本。从严，绝大多数停在 1；升要成文验收记录并用户点头；一升 minor、patch 归零。
- **minor = 较大改动**：新功能、新分段、整批字符转换、质量小幅提升、整册重跑。
- **patch = 其余小范围改动**（最常见）。
- 拿不准 patch 还是 minor，选 minor；major 没有「拿不准」，达不到门槛就不升。

### major 门槛

| 等级 | 文本 | 标点 | 实体 |
|---|---|---|---|
| 1 可用 | 每格有定字；疑难、阙文、残字按规范记（`□`、`[[]]`、guess）；机器定字＋自动放行闸，人审不必全覆盖 | 机器标点、只插不改字；抽 200 处一致率 ≥95% | 机器识别＋自动链接；抽 50 个类型与边界精确率 ≥90%，挂错 ≤5% |
| 2 出版级 | 全册人工逐字校一遍、疑难有裁决；随机抽 ≥2,000 字错 ≤2；阙文、异体、组字写法全合规 | 全册人审，书名号、引号层级、分段合规；抽 500 处 ≥99.5% | 全部人工确认类型、边界、链接；精确率 ≥99%；逐段抽 20 段查漏，召回 ≥95%；无「存疑」链接 |
| 3 定本 | 两遍独立校＋至少对勘一种别本或权威整理本，异文有校记；抽 ≥10,000 字错 ≤1；签核 | 对照权威点校本逐段核，分歧有记录；抽 1,000 处 ≥99.9%；签核 | 逐段补漏，召回 ≥99%；链接对象在 book-index 均正式建档且非存疑；签核 |

### minor 与 patch（举例）

| 线 | minor | patch |
|---|---|---|
| 文本 | 整批字符转换（PUA→Unicode、组字式→IDS、整册统一某异体记法）；新分列／夹注规则整册重排；一批人审裁决落地使覆盖率升 ≥10 个百分点；新增标记功能（`zi` 层、抬头记法） | 改个别字（一册 ≤约 50 处、位置已知）；补几处阙文 guess；记法笔误 |
| 标点 | 整册重跑或换模型、换提示词；新分段规则；新增标点类型；批量修一类错误 | 改几处、几十处标点；修少量锚点 |
| 实体 | 新增实体类型；整册重识别；一批 new_candidate 建档后集中回填 id；匹配器换规则后重链 | 改个别实体的边界、类型、链接；修少量锚点 |

**「小范围」怎么数**：以一次 PR 为单位，一册改动 ≤约 50 处 → patch；超过或按规则成批改 → minor。

## 五、什么时候开始编号

- `wip/` 分支上不编号，版本字段可写 `0.x` 或不写。`wip/` 分支不跑开 PR 前的校验；在 `wip/` 上跑 `--strict` 会因 `0.x` 报 F-OV-01，这是有意的：要并 main 就先 `--init` 定到 `1.0.0`。
- **第一次并 main 定 `1.0.0`**，前提是够得上第 1 级；够不上不并。
- 之后每次 squash merge，动到的线按本规范升，PR 描述列「册 · 线 · 旧 → 新 · 理由」表，文本总管对着 diff 核。

## 六、工具

- **升级脚本**：overview `scripts/book-text/bump_original.py`
  ```bash
  python3 <overview>/scripts/book-text/bump_original.py <original 目录或条目目录> --init --note "首次并 main" --pr N   # 三线定 1.0.0
  python3 <overview>/scripts/book-text/bump_original.py <目录> --line text|punct|entity --level patch|minor --note "…" [--pr N] [--chapter NNN]
  ```
  改版本号、同步 `index.json` 镜像、写 `CHANGES.md`；升文本线后自动核伴生层锚点（对得上的跟 `text_version`，对不上的列出来）；锚点没修好的伴生层拒绝升；`--level major` 报错。
- **校验器**：overview `validate_text_format.py` 规则（只扫 key=`original` 的版本）：
  - **F-OV-01** 三线版本号格式、≥1.0.0、镜像一致、`text_version` 不超前、伴生层 major 不高于文本；
  - **F-OV-02** 伴生层 `text_version` 落后时锚点校验字必须仍对得上；
  - **F-OV-03** major ≥2 必须带验收记录。
- 格位 key 的定义见 guji-format 02（char）§二：双行夹注 a 是右列、先读，b 是左列；超框抬头负格位、无第 0 格；阙文写 □ 并带 `lacuna: true`。
