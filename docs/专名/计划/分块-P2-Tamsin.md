# 分块设计：专名识别与链接 ／ P2 补标与判读（含 P4 建档清单批 2、P7 回挂）

> 块负责人：判：Tamsin；执行：Tilda　｜　项目主力：Tamsin　｜　状态：待评审（2026-10-12 洛杉矶 13:50）
> 对应总计划：`项目进展/专名识别与链接/计划/总计划.md` 第四节 P2、P4、P7 行

## 一、本块目标与边界
目标：P1 候选每行有处置并写入实体线；new_candidate 得出「建档／不建档」去向；建档后回挂　｜　不做：不动正文标点、不改 schema、不自己建档（归 P5／P6）　｜　交付物：entity 线 minor 升版 PR；`专名匹配/建档清单-批2.md`；`专名匹配/不建档清单.md`；回挂两轮 PR

## 二、Schema／数据格式（完整）
**处置表** 同 P1 §二（`漏标处置.tsv`）。

**补标写入** `*.entity.json` 新增 entity：`{"id":"e<新序>","type":"person|work","text":..., "anchor":{...}, "span":{...}, "target":{"status":"matched"|"new_candidate", "entity_id"?, "canonical_name", "href"?}, "source":"补标:N8|N9"}`；序号接现有最大号后续编；`stats` 由 `bump_original.py` 重算。

**建档清单-批2** `专名匹配/建档清单-批2.md`：沿用批 1 版式（人物表：规范名｜别名｜朝代｜CBDB 号｜证据 span 数｜出处册／锚点；书名表：规范名｜别名｜撰人｜出处｜证据 span 数）。分两次交：先人物、后书名。

**不建档清单** `专名匹配/不建档清单.md`（表格，一行一 span 或一组同名 span）：`册｜anchor｜type｜text｜理由码｜备注`。理由码：`佚书无著录`、`泛称`、`引文内书名`、`篇名`、`同名难分`、`待核书影`（转 Mila）。

## 三、程序架构
- 新写 `scripts/book-text/entity_apply.py`（~120 行）：读处置表中 `补标` 行，把新 entity 写入册 `*.entity.json`（保序、编号续接），`--dry-run` 先出 diff 计数；`--rematch` 模式对 `new_candidate` 重对现库（复用 `t543_rematch.py` 逻辑，N4/N5）并按 `promotions.json` 解升格跳转。
- 复用：`t543_rematch.py`、`t543_rebind.py`、`bump_original.py`（`--pr` 必填，先开草稿 PR）。
- 配置：book-index 路径、`promotions.json` 路径作参数。
- 运行在云端会话；book-text 走 PR（分支 `tilda-entity-p2`），写域登记 `排班.md`。

## 四、步骤流程
| 步 | 做什么 | 输入标准 | 产出 | 验收标准 | 谁验 | 估时 |
|---|---|---|---|---|---|---|
| 1 | Tamsin 写判读规则卡（N8/N9 在两字名与书名上的边界例，≤1 页）放 `专名匹配/补标判读规则.md` | P1 步 4 完成 | 规则卡 | 覆盖 `lo` 档前 40 条样例，每例有结论 | Tamsin | 40 分钟 |
| 2 | Tilda 按规则卡填 `hi` 档处置（机械） | 步 1 完成 | `漏标处置.tsv` 的 hi 行 | `entity_missing.py --check --only hi` 退出码 0；Tamsin 抽 30 条，错判 ≤2 | Tamsin | 60 分钟 |
| 3 | Tilda 填 `lo` 档；Tamsin 抽 20% | 步 2 通过 | `lo` 行 | 抽审错判 ≤10%（超则整档回炉）；`--check` 退出码 0 | Tamsin | 90 分钟 |
| 4 | `entity_apply.py --dry-run` 再正式写入；开草稿 PR；`bump_original.py --pr N`（entity minor） | 步 3 通过；排班无冲突 | book-text PR＋CHANGES 行 | 三项校验退出码 0（命令见 book-text CLAUDE.md）；`entity_coverage.py` 总数＝2,056＋补标行数 | Maren 审 | 40 分钟＋校验约 15 分钟 |
| 5 | P4：对 new_candidate 分「建档／不建档」，写建档清单-批2（人物先） | 步 4 合并；P3 不依赖 | 清单 v1（人物） | 人物表每行有证据 span 与朝代；抽 20 条核 CBDB 号，错 ≤1；`不建档清单.md` 行数＋建档清单 span 数＝new_candidate 数（脚本比，差 0） | Tamsin 自验、Eric 抽 | 90 分钟 |
| 6 | 书名清单交付 | 步 5 | 清单 v2（书名） | 同上；唤醒 Soren 经 Mirren（跨号卡见步 9） | 同上 | 60 分钟 |
| 7 | P7 回挂第 1 轮：P5 上线后 `entity_apply.py --rematch` | P5 建档结果表交付，book-index 合并 | PR＋minor 升版 | `entity_coverage.py` people／work 链接率达参考线或差额逐条在不建档清单；三项校验 0 | Maren | 90 分钟 |
| 8 | P7 第 2 轮同上（P6 后） | P6 交付 | PR | 同上，覆盖 place／office／dynasty／reign | Maren | 90 分钟 |
| 9 | 跨号卡：开 open-guji-team issue（P5 给 Soren、P6 给 Sienna），首行 `【A→B｜收件人 Mirren｜发件人 Tamsin】` | 步 5 人物表出；P6 无依赖，可更早 | issue 链接 | issue 内含 Schema、输入文件、验收命令 | Maren | 20 分钟 |

## 五、测试数据与金标
抽查口径：每批随机抽 30 条，按处置表复核；误判率超线整档回炉。回挂用 `重对现库-册002-003.md` 为基线对照（N5 现库命中表）。

## 六、与其他块的接口
| 方向 | 对方块／负责人 | 文件／格式 | 何时交接 | 对方已确认？ |
|---|---|---|---|---|
| 入 | P1／Tamsin | 候选 TSV | P1 步 4 | 待 |
| 出 | P5 Soren（B） | 建档清单-批2 | 步 5／6 | 待（跨号卡） |
| 入 | P5／P6 | 建档结果-批2、建档结果-地官朝号 | 各自完成 | 待 |
| 出 | P9 Eiko | 抽样 URL 清单（每类型 ≥5 个 matched，含新建档） | P7 每轮后 | 待 |
| 出 | Mason | book-text／book-index 完整 SHA | 每轮 PR 合并后 | 已声明 |

## 七、风险与未决
最可能出错的一处：补标把年号、官名误当人名（如「開元」）——靠停用词与抽审。冲突：entity／punct 线同时只一个 PR 改版本，排队 Maren 定。若 `lo` 候选 >300 行，向 Morgan 提补一名 Haiku 机械改（已写总计划）。

## 八、评审
| 日期 | 评审人 | 结论 | 意见 |
|---|---|---|---|
| 2026-10-12 | Maren | 通过 | ①entity 线同时只一个 PR：P3 先合、P2 步 4 的 PR 在 P3 合并后再基于 main 开，避免 `CHANGES.md`／`index.json` 冲突；②Tilda 在 P2 步 1（规则卡）期间先做 P3 步 3，不空等；③P2 步 9 跨号卡 open-guji-team#5 已开，可更早推进。 |
