# 分块设计：专名识别与链接 ／ P3 同名待消歧 152 条

> 块负责人：判：Tamsin；执行：Tilda　｜　项目主力：Tamsin　｜　状态：待评审（2026-10-12 洛杉矶 13:50）
> 对应总计划：`项目进展/专名识别与链接/计划/总计划.md` 第四节 P3 行

## 一、本块目标与边界
目标：把 152 个 `ambiguous` 逐条定为 `matched`（确认 id）或登记「仍待」　｜　不做：不建档、不改 span、不改 canonical_name 以外字段　｜　交付物：entity 线 minor 升版 PR；`专名匹配/仍待消歧.md`；`专名匹配/消歧记录.tsv`

## 二、Schema／数据格式（完整）
**消歧记录** `专名匹配/消歧记录.tsv`：`entity_id`（册内 id，如 `002:e00231`）｜`type`｜`text`｜`candidates`（`id1|id2…`）｜`decision`（`pick`／`pending`）｜`picked_id`｜`evidence`（撰人／朝代／同段共现的一句话）｜`by`｜`date`。
**仍待消歧** `专名匹配/仍待消歧.md`：每条 `册:id｜text｜候选与差异｜卡在哪｜谁能解`。
写入：`pick` → `target={status:matched, entity_id, canonical_name, href}`；`pending` → 保持 ambiguous，`target.candidates` 保留。样例：`002:e00231	work	周易注	Work/a1|Work/b2	pick	Work/a1	撰人王弼，同段「魏王弼」	Tilda	2026-10-12`。

## 三、程序架构
- 新写 `scripts/book-text/entity_disambig.py`（~100 行）：`--list` 导出 152 条待办（含候选的撰人、朝代、已有 `other_sources`），`--apply 消歧记录.tsv` 写回 `*.entity.json`（`--dry-run` 先出计数）。
- 复用：`entity_coverage.py` 做前后对数。运行云端；book-text 走 PR（`tilda-entity-p3`）。

## 四、步骤流程
| 步 | 做什么 | 输入标准 | 产出 | 验收标准 | 谁验 | 估时 |
|---|---|---|---|---|---|---|
| 1 | 写 `--list`，导出 152 条待办 | `entity_coverage.py` 显示 ambig=152 | `消歧待办.tsv` | 行数＝152（work91／people34／dynasty18／place9）| Tamsin | 30 分钟 |
| 2 | Tamsin 写 5 类消歧规则（撰人优先、同段全名、朝代、版本年份、仍无法定则 pending）及 10 条样例 | 步 1 | `专名匹配/消歧规则.md` | 样例 10 条每条有结论与依据 | Eric 抽 | 30 分钟 |
| 3 | Tilda 按规则填 `消歧记录.tsv`（work、dynasty 先） | 步 2 | 记录 | 行数＝152；`pick` 行 `picked_id` 全在 candidates 内（脚本检）| Tamsin 抽 30 | 90 分钟 |
| 4 | 抽审与回炉 | 步 3 | 修订记录 | 抽 30 条错 ≤2；超则整类型回炉 | Tamsin | 20 分钟 |
| 5 | `--apply --dry-run`→正式；开草稿 PR；`bump_original.py --pr N` | 步 4；排班无冲突 | PR | `entity_coverage.py` 全部 `ambig` ＝ 仍待条数；仍待条数＝`仍待消歧.md` 行数；三项校验 0 | Maren | 30 分钟＋校验 15 分钟 |

## 五、测试数据与金标
无外部金标；`pick` 以撰人／朝代证据为准，Tamsin 抽 30 条人裁。分母＝152。

## 六、与其他块的接口
| 方向 | 对方块／负责人 | 文件／格式 | 何时交接 | 对方已确认？ |
|---|---|---|---|---|
| 出 | P7 | 仍待消歧不进回挂 | 步 5 | 待 |
| 入 | 无 | — | — | 是 |

## 七、风险与未决
最可能出错的一处：work 同名多版（如多种《周易注》）证据不足时误 pick——pending 优先于错 pick。需别人先定：无。

## 八、评审
| 日期 | 评审人 | 结论 | 意见 |
|---|---|---|---|
| 2026-10-12 | Maren | 通过 | 建议排在 P2 之前先合（与 P2 同改 `*.entity.json` 版本线）；步 3 验收请加「`picked_id` 在 book-index 中真实存在」一条（不只在 candidates 内）。 |
