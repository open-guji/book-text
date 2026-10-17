# book-text 版本号与仓库流程（摘要）

> 条目布局以 guji-format spec/07-book-text-条目布局.md（§2.3、§3.3）为准。

> 规范全文：overview `项目进展/古籍文本/整体设计/2026-10-文本版本号与仓库流程.md`（v2，用户 10-05 定）。
> 本文是摘要，两边不一致时以规范全文为准。落地任务卡：open-guji-core/overview#400（T67）。

## 一、仓库流程

1. **main 受保护，一律走 PR。** 一批活开一个分支（`<道名>-<主题>`，如 `t65-wiki-match`），分支上可以多次提交，整批做完开**一个** PR，审过 **squash merge**。`wip/` 前缀是反复改动中的工作分支（如 `wip/siku-vol02`），用户点头前不并 main。
2. **谁来合**：日常批次（入库、修正、撤除 50 部以内）文本总管审过就合。以下等用户点头：撤除超过 50 部；改全仓结构或规范；`original` 任何一条线升 **major**。
3. **开 PR 前**：把 main 合进分支，用 overview `scripts/book-text/build_texts_index.py --root <本仓>` 重建 `index/texts`，结果贴进 PR 描述：
   - `scripts/validate_text_format.py <本仓> --strict --baseline scripts/format_baseline.json` 退出码 0（脚本与基线是 overview 的副本，来源 commit 以脚本头为准；overview 改规则后要同步）；
   - `scripts/validate-collated.py --root <本仓>`（不带 `--strict`）退出码 0，且报告里没有本 PR 新增的问题（main 上已知存量：`d59f1iqd854w/default` 多一个 `108.md`）；
   - 重建索引后没有未提交的 diff。
4. PR 和推到 main 都跑 `.github/workflows/check.yml`（V1 validate-collated、V2 validate_text_format `--strict --baseline`、V3 check_license），仍靠审 PR 把关。

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
- **过渡已完成**（T68 #417 起）：文本线跟踪 `NNN.char.json`，验收记录放 char 顶层 `review`，`index.json` 的 `text_review` 不再用。`bump_original.py` 和校验器 F-OV-* 已读 char.json。
- 验收记录（`review`）至少含 `date`、`signed_by`、`sample`（抽检数据）。
- 每次升版本，在 `<版本目录>/CHANGES.md`（`<版本目录>` 同上：manifest 里 `is_original` 为 true 的版本目录，常为 `default/`，旧条目仍可能是 `original/`） 记一行：`| 日期 | 册 | 线 | 旧→新 | 说明 | PR |`。「册」一栏写 `<条目 id>/<章 NNN>`（如 `96mid1ogzk/002`），一次动几册就记几行，章级历史可按这一栏追。

### 三条线之间
- 标点、实体靠坐标锚在文本上，每个锚点带校验字：标点 `anchor`＋`pre_char`，实体 `anchor.start..end`＋`text`。
- 文本改了：锚点全对得上 → 伴生层只把 `text_version` 跟过去，**不升**它的版本（由 `bump_original.py --line text` 自动做，所以文本线一律用脚本升；手改 char.json 版本号会让伴生层 `text_version` 落后；F-OV-02 不论是否落后都核锚点，所以改字类修订合入时，同版本的标点／实体失效也会被当场发现）；对不上 → 伴生层按规模修，修好后自己升 patch 或 minor。
- **伴生层 major 不得高于文本线**：文本还没到出版级，标点、实体也不能先升（F-OV-01 查）。
- **每册只入库一份**标点稿、一份实体稿；模型对照稿只在本地测试，不进仓。
- **书名两层都记**：标点层出一对 `《》`，实体层出 `work` 实体挂 book-index id，两层起止一致。

## 四、三级怎么升

- **major = 质量等级**：0 粗校、1 可用（精校完）、2 出版级、3 定本。1 起从严，绝大多数停在 1；升要成文验收记录并用户点头；一升 minor、patch 归零。
- **0.x = 平台粗校完、精校未完**（2026-10-16 用户定，GUJI-543）：只有**文本线**有 0.x，粗校全流程跑完、各步 gate 过了就以 **0.1.0** 并 main，网站挂「欢迎帮助校对」；之后改格、重切照 patch／minor 升。0.x 阶段**没有标点、实体线**（精校完才开工），所以不存在伴生层 0.x。0.x → 1.0.0 是 major，走验收记录。
- **minor = 较大改动**：新功能、新分段、整批字符转换、质量小幅提升、整册重跑。
- **patch = 其余小范围改动**（最常见）。
- 拿不准 patch 还是 minor，选 minor；major 没有「拿不准」，达不到门槛就不升。

### major 门槛

| 等级 | 文本 | 标点 | 实体 |
|---|---|---|---|
| 0.1.0 粗校完 | 粗校全部步骤、全部页面跑完，各步 gate 过；每格有定字或有去向（阙文、交重切清单）；机器定字＋自动放行，人审可以没做 | 不开工 | 不开工 |
| 1 可用（精校完） | 疑难、不确定的字至少过一遍人审（切分没修所以没法判的格单列、有去向，不算「看不出」）；自动检查通过；阙文、残字按规范记（`□`、`[[]]`、guess）；允许有可追溯的「看不出」存疑格。细则见 ai-team `team/整理/设计/文本整理三阶段流程.md` | 机器标点、只插不改字；抽 200 处一致率 ≥95% | 机器识别＋自动链接；抽 50 个类型与边界精确率 ≥90%，挂错 ≤5% |
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

- `wip/` 分支上不编号，版本字段可写 `0.x` 或不写。`wip/` 分支不跑开 PR 前的校验。
- **第一次并 main**（2026-10-16 起，GUJI-543）：
  - **粗校完**够得上 0.1.0 门槛的，以 **`0.1.0`** 并 main：`bump_original.py <目录> --init --version 0.1.0`，只定文本线，章条目写 `proofing: true`；没有标点、实体稿。
  - **精校完**够得上第 1 级的，升 **`1.0.0`**（major，手工改版本号并附验收记录），`--proofing off`；之后标点、实体线开工，各自从 `1.0.0` 起（`--init` 默认）。
  - 已按旧定义以 1.0.0 并 main 的册（四庫 vol02、vol03）保留 1.0.0，CHANGES 记一句「按旧定义定的 1.0.0」，补走精校时 `--proofing on`，精校合入算文本 minor。
  - 够不上 0.1.0 不并 main。
- 之后每次 squash merge，动到的线按本规范升，PR 描述列「册 · 线 · 旧 → 新 · 理由」表，文本总管对着 diff 核。

## 六、工具

- **升级脚本**：overview `scripts/book-text/bump_original.py`
  ```bash
  python3 scripts/book-text/bump_original.py <original 目录或条目目录> --init --note "首次并 main" --pr N   # 三线定 1.0.0
  python3 scripts/book-text/bump_original.py <目录> --init --version 0.1.0 --note "粗校完" --pr N        # 只定文本线 0.1.0，proofing=true
  python3 scripts/book-text/bump_original.py <目录> --proofing on|off --note "…" --pr N                  # 只改校对状态开关
  python3 scripts/book-text/bump_original.py <目录> --line text|punct|entity --level patch|minor --note "…" [--pr N] [--chapter NNN]
  ```
  改版本号、同步 `index.json` 镜像、写 `CHANGES.md`；升文本线后自动核伴生层锚点（对得上的跟 `text_version`，对不上的列出来）；锚点没修好的伴生层拒绝升；`--level major` 报错。
- **校验器**：本仓 `scripts/validate_text_format.py` 规则（只扫 key=`original` 的版本）：
  - **F-OV-01** 三线版本号格式、文本线 ≥0.1.0（伴生层 ≥1.0.0）、镜像一致、`text_version` 不超前、伴生层 major 不高于文本（所以文本线 0.x 时不能有伴生层）；
  - **F-OV-02** 伴生层（标点、实体两线）的锚点校验字必须仍对得上 char——`text_version` 落后或与文本同版本都核（GUJI-561，book-text#149）；
  - **F-OV-03** major ≥2 必须带验收记录。
  - **F-OV-04** 章条目的 `*_file` 声明与文件存在（`char_file` 必填；文本线 0.x 的册 `cord_file` 也必填）。
  - **F-OV-05** decision.json 对照同章 char：`$schema`、`book_id`／`volume` 一致，候选字层合法；`$schema` 接受 v0.1、v0.2，v0.2 的 `reason`／`route`／`route_ref` 规则见 guji-format 08 §3.4（已落地，含 `scripts/tests/test_decision.py`）。
  - **F-OV-06** 章条目的 `proofing`（校对中）只能是布尔；文本线 0.x 时必须为 `true`，≥1 时可写 `true`（补走精校）或不写。网站据此挂「欢迎帮助校对」banner，**不从版本号推**。
  - **F-OV-07** 章条目的 `pending_file`（册级待审清单）只在 `proofing: true` 时存在；文件顶层 `rev`＝`<册>-r<n>`、`cv_commit` 必填、`cv_version` 为字符串或 null，`cells` 每项有 `cell` 与 `review`。
- 格位 key 的定义见 guji-format 02（char）§二：双行夹注 a 是右列、先读，b 是左列；超框抬头负格位、无第 0 格；阙文写 □ 并带 `lacuna: true`。
