# 分块设计：专名识别与链接 ／ P5b 书名建档（Work）

> 块负责人：Silas（B，目录团队，经理 Marlowe）　｜　项目主力：Tamsin　｜　状态：待评审
> 对应总计划：`项目进展/专名识别与链接/计划/总计划.md` 第四节 P5 行的「书名」部分（Marcus 10-12 在 open-guji-team#5 定：书名 Work 建档归目录团队，Soren 的 P5 只管人物）
> 执行起点：红楼梦 A 档（overview#499）收口后；设计现在写、评审过了再执行。

## 一、本块目标与边界
目标：把 P4 交来的**批 2 书名清单**逐行落成结果——**建 Work／补别名到既有 Work／判为已有／拒建档**，每行有处置，新建的 Work 过 `check_v2`，id 对照表回给 Tamsin 做 P7 回挂。

不做：
- 不建人物（Entity），归 Soren（P5）；Work 的作者栏只**引用** Soren 已建或库里已有的 Entity id。
- 不建 Book（版本），本块只建 Work；版本归 #461 线。
- 不动 book-text（span 修正、回挂归 Tamsin／Tilda 的 P2／P7）。
- 不合并库里已有的重复 Work（发现了只登记「疑重」，转重复核对，不在本块动手）。
- 不查原书、不推断 `lineage`；只据总目原文＋库里既有记录。
- 不发布 data.yml（网站 Mason）。

交付物：
1. `scripts/book-text/work_dedupe.py`（查重脚本，入 overview，可重跑）；
2. `专名匹配/建档判读-批2-书名.tsv`（每行处置）；
3. book-index PR（新建 Work＋补别名，`check_v2` 0 错）；
4. `专名匹配/建档结果-批2-书名.md`（规范名→id 对照，版式同 `建档结果-批1.md`）。

## 二、Schema／数据格式

### 2.1 输入：`建档清单-批2-书名.md`（Tamsin P4 交，Marcus 要求与人物表分开）
版式同批 1 的书名表：`# | 规范名 | 类型(Work) | 作者／朝代 | 证据(原文＋锚点) | 来源 | 置信 | 备注`。本块**不改它**，只读。

### 2.2 中间表：`建档判读-批2-书名.tsv`（本块新写，UTF-8，tab 分隔，首行表头）
| 列 | 类型 | 含义 |
|---|---|---|
| `no` | int | 清单序号（与输入表一致） |
| `name` | str | 清单规范名 |
| `verdict` | enum | `NEW` 新建 Work｜`ALIAS` 并入既有 Work 作别名｜`EXISTS` 库里已有，无需动｜`DUP?` 库里有疑似重复，待核｜`REJECT` 拒建档 |
| `target_id` | str，可空 | ALIAS／EXISTS／DUP? 指向的既有 Work id；NEW 填新 id（铸出后） |
| `reason_code` | enum，REJECT 必填 | `R1` 篇名／文章｜`R2` 泛称或简称｜`R3` 引文转述，无独立著录｜`R4` 作者朝代无法定｜`R5` 同名异书未能分｜`R6` 其他（备注写明） |
| `author_ids` | str，可空 | 作者 Entity id，`;` 分隔；库里已有或 Soren 批 2 新建 |
| `dynasty` | str，可空 | 同清单 |
| `status_note` | str，可空 | `佚`／`未见`／`存`（据原文，不猜） |
| `evidence` | str | 原文片段＋`册·页:列:格` 锚点（沿用输入表） |
| `note` | str，可空 | 学者判读（异体、同名异书的区分依据等） |

判读规则的口径（每条在 `note` 里能说出依据）：
- **同名**：规范名字面或 `additional_titles`、异体字（`variants` 折叠后）相同，**且作者朝代不矛盾**，才算已有；同名异作者→`R5`或新建并在 `note` 写区分（如批 1 的《時用書》≠《鄭夬時用書》）。
- **总目另称**（如「書錄解題」「周易章句外編」）→ `ALIAS`，不新建。
- **篇名／序跋名／引文里的书**（批 1 #18 的先例）→ 默认 `REJECT R3`，除非总目在别处有独立提要。

### 2.3 新建 Work 的 JSON（schema-v2，沿用 Schema落地 S0 冻结的现行格式）
路径 `Work/<id[-3]>/<id[-2]>/<id[-1]>/<id>-<title>.json`。字段：
| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version`/`id`/`type:"work"`/`title` | 是 | `title`＝清单规范名 |
| `additional_titles` | 否 | 清单别名；`ALIAS` 行补到既有 Work 此字段 |
| `authors[]` | 有作者则是 | `{name, role, entity_id, dynasty}`；**`role` 必填**（撰／編／注…，据原文）；无 Entity id 时只写 `name`，不造 id |
| `description.text` | 否 | 一句，只写总目原文能支持的 |
| `indexed_by[]` | 是 | `{source:"欽定四庫全書總目", source_bid:<卷>, title_info:<原文书名>, summary:<一句>}` |
| `measure_info` | 否 | 总目所记卷数，如「二卷」；佚书写「佚」 |
| `ai_note` | 是 | 「专名识别与链接 P5b 批 2：据四庫總目 册·页:列:格；未覆核原书」 |
**不写**：`Work.books`、`_` 前缀字段、无证据的 `lineage`、`version_graph`、`period`（交库里既有的派生流程）。关系只存一侧（作者在 Work 上，不在 Entity 上回写）。

### 2.4 输出：`建档结果-批2-书名.md`
版式同 `建档结果-批1.md`：`# | 规范名 | id | 备注` 三段——新建（Work）、补别名（既有 Work）、没做／要别人接。外加两列统计行：新建数、ALIAS 数、EXISTS 数、DUP? 数、REJECT 数（合计＝清单行数）。

## 三、程序架构
- `scripts/book-text/work_dedupe.py`（新写，仿 `entity_coverage.py` 的命令行风格）：读 `建档清单-批2-书名.md` 的规范名列＋本地 book-index 检出，扫全库 Work（`Work/**.json`，约 13 万条）的 `title`／`additional_titles`／`variants`，对每个清单名做 ①精确 ②异体折叠 ③去前后缀（如「周易」「易」「全書」）近似三档匹配，输出候选 `(清单名, 命中 Work id, 命中档, 命中 Work 的作者／朝代)`。**只出候选，不下结论**；判读由学者做。
  - 入口：`python3 scripts/book-text/work_dedupe.py --list 建档清单-批2-书名.md --index <book-index root> --out 查重候选.tsv`
  - 运行在云端会话即可（读 JSON，无外网）；全库扫描约 1–2 分钟（估，首次实测后回填）。
  - 复用：`book-index/.claude/qa/mintid.py` 的 `parse`/`idtype`/`path_for`；异体折叠表用库里现有的（路径首次运行前核）。
- 铸 id：沿用 `mintid.py` 的 64 位布局（Official，秒级时戳）。**machine id 取 2018（Silas 专用，登记在 `mintid.py` 的 `LANE_MACHINE`，PR 里一并加一行）**，保证与 Eric 批 1 的上游生成器 id（`d59fu304uew*`）永不相撞。
- 校验：`check_v2.py --root <book-index> --paths <新增／改动文件>`；PR 前跑 `prcheck`。
- 谁调谁：`work_dedupe.py` → 人工判读（tsv）→ `mint_and_write.py`（新写，仅读 tsv 的 `NEW`／`ALIAS` 行生成 JSON 与别名补丁，不做判断）→ `check_v2` → PR。

## 四、步骤流程
| 步 | 做什么 | 输入标准 | 产出 | 验收标准 | 谁验 | 估时 |
|---|---|---|---|---|---|---|
| 1 | 写 `work_dedupe.py`，先在批 1 的 16 本书上回放验证 | book-index 检出在 main，`ls Work` 非空；批 1 清单与 `建档结果-批1.md` 可读 | 脚本＋回放报告 | 回放批 1：清单 #17–#32 里，**不应命中**的（真缺）全部无「精确」命中；已知应命中的（如《時用書》vs《鄭夬時用書》应判「近似」而非「精确」）命中符合预期，不符合数 0（命令：`work_dedupe.py --list <批1> --self-test`，输出末行 `mismatch=0`） | 自验；Tamsin 评审时抽看 | 约 1 小时 |
| 2 | 拿到批 2 书名清单后，跑查重，产出候选表 | `建档清单-批2-书名.md` 已入 overview 且 Tamsin 在卡上标「书名表已交」；步 1 通过 | `查重候选.tsv` | 行数＝清单行数（`wc -l` 差 0）；无空规范名 | 自验 | 约 15 分钟（机器 <3 分钟） |
| 3 | 逐行判读，填 `建档判读-批2-书名.tsv` | 步 2 完成；人物批 2 的 `建档结果-批2.md`（Soren）已出，**否则作者栏先填 `name`，`author_ids` 空，待 Soren 交后补** | tsv（每行 `verdict` 非空） | `awk` 检查：`verdict` 空行数 0；`REJECT` 行 `reason_code` 空 0；`NEW` 行有 `evidence` 锚点；合计行数＝清单行数 | 自验＋Marlowe 抽 10 行 | 约 1.5 小时／每 80 行（估；行数以清单为准） |
| 4 | 对 `DUP?` 与 `R5` 行做「同名异书」复核，该并别名的并，疑重复的登记 | 步 3 完成 | tsv 更新＋`疑重登记.md`（若有） | `DUP?` 行均有 `target_id` 和一句 `note`；无「悬空」行 | 自验 | 约 30 分钟 |
| 5 | 铸 id，写 Work JSON，补别名补丁，加 `LANE_MACHINE` 的 2018 | 步 3、4 完成；`mintid.py` 可 import | 新文件＋改动文件 | `check_v2 --root <book-index> --paths <全部新增改动>` 末行「残留（ERROR）0 處」；新建数＝tsv 中 `NEW` 行数（命令：`git status --short \| grep -c '^A'` 与 `awk '$3==\"NEW\"' \| wc -l` 差 0） | 自验 | 约 40 分钟 |
| 6 | PR 前整体校验，开 PR | 步 5 通过 | book-index PR | `prcheck`：changed＝新建数＋补别名文件数，exact／near／□／dangling／index 文件均 0；重跑 `work_dedupe.py` 对新库：新建的每个名仅命中自己（`self_only=100%`） | 自验；Eric 查重（沿用批 1 流程） | 约 20 分钟 |
| 7 | 写 `建档结果-批2-书名.md`，回 open-guji-team#5，贴 PR 号与完整 SHA | PR 已建 | 结果表＋卡上回复 | 结果表合计行＝清单行数；新建 id 在对照表与 PR 文件一一对应（脚本比对差 0）；回复首行 `【B→A｜收件人 Tamsin｜发件人 Silas】` | Tamsin 接手 P7 | 约 20 分钟 |

写 book-index 的目标：沿用批 1 的做法，PR 直接给正式库 `open-guji/book-index`，**由 Marlowe 批准后才开**（建 Work 属正式库写入）。若 Marlowe 要求先走草稿库，则 id 用 Draft 位（status=1，毫秒时戳，13 位），PR 开到 `book-index-draft`，其余步骤不变。这是未决项 U1（见第七节），默认：正式库。

## 五、测试数据与金标
- **回放金标**：批 1 的 16 本书（`建档清单-批1.md` 第 17–32 行）＋ `建档结果-批1.md` 的 id，是 Eric 查重后的人裁真值，用来验步 1 脚本（分母＝16；其中有 3 条别名项、1 条「同名异书」）。
- **易類试点**：`试点-建档样例.md`、`试点-易類一-差异清单.md` 可作第二套抽查材料。
- **批 2 抽查**：Marlowe 在步 3 抽 10 行（随机，seed 写入卡），被抽行的 verdict 全部要有可复述的依据；错 ≥3 行则整批回炉重判。

## 六、与其他块的接口
| 方向 | 对方块／负责人 | 文件／格式 | 何时交接 | 对方已确认？ |
|---|---|---|---|---|
| 入 | P4／Tamsin | `建档清单-批2-书名.md`（人物表分开） | 预计 10-13 凌晨后；Tamsin 在 #5 标「书名表已交」 | Marcus 已在 #5 要求分表；Tamsin 待认 |
| 入 | P5／Soren | `建档结果-批2.md` 的人物 id（作者栏用） | Soren 建档完成后；未到则作者栏暂填 name | 待 Soren／Mirren 认 |
| 出 | P7／Tamsin、Tilda | `建档结果-批2-书名.md`（同批 1 版式）＋PR 号＋SHA | 步 7 | 版式沿用批 1，免新约定 |
| 出 | 网站／Mason | PR 号＋完整 SHA（发布 data.yml） | 步 7 | Mason 已声明按 SHA 发布 |
| 旁 | 目录团队 Marlowe | 步 5 写正式库前的批准；DUP?／疑重登记 | 步 4／5 之间 | 待 Marlowe 回 |
| 旁 | 红楼梦 A 档（#499） | 无数据依赖；排期上本块在其后执行 | A 档收口后 | — |

## 七、风险与未决
**最可能出错的一处**：**同名异书误判为已有**（或反之）。书名大量是「周易×× 」「易××」式，字面近而不是一书，批 1 里《時用書》vs《鄭夬時用書》已踩到。应对：判 `EXISTS`／`ALIAS` 必须同时核作者朝代，脚本只出候选；近似档一律人工判，不自动并。

其他：
- **U1 写正式库还是草稿库**：默认正式库（沿用批 1）；请 Marlowe／Tamsin 评审时定。
- **U2 作者 id 依赖 Soren**：人物先、书名后，Soren 若晚于书名表，作者栏先填 name，等人物 id 出来再补一次小 PR（会多一次 check_v2）；也可由 Soren 的结果表晚到而顺延步 3，不阻塞步 1–2。
- **U3 machine id 2018 须登记**：当前 `mintid.py` 仅有 2000–2009 车道，PR 里加一行，Marlowe 批。
- **U4 行数未知**：总计划 §三 的 727 个书名候选是上限，实际建档数取决于 P4 剔除；估时按每 80 行 1.5 小时线性放缩，清单到手后回填总估时。
- **U5 红楼梦 A 档**：本块执行排在其后；若 Marcus 解除 #394 搁置，排序请 Marlowe 定。
- 书影、版本、`version_graph` 不在本块，如判读中发现某书有多版本，只在 `note` 记一句，转 #461。

## 八、评审
| 日期 | 评审人 | 结论 | 意见 |
|---|---|---|---|
| | | | |

---
_Generated by [Claude Code](https://claude.ai/code)_
