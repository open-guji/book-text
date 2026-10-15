# 分块设计：专名识别与链接 ／ P8 判准固化成脚本＋vol04 试跑

> 块负责人：Tamsin（备：Lucian 接 P8，若 B3 拖延）　｜　项目主力：Tamsin　｜　状态：待评审（2026-10-12 洛杉矶 13:50）
> 对应总计划：`项目进展/专名识别与链接/计划/总计划.md` 第四节 P8 行

## 一、本块目标与边界
目标：把 N1–N7 机械规则做成可重跑脚本；vol04 第 1 份 Gemini 输出过脚本并验收　｜　不做：不做 vol05–vol10、不改 Gemini 驱动（归 Dana／#564）、不动整理本　｜　交付物：`scripts/book-text/entity_postprocess.py`＋`tests/`＋`专名匹配/vol04试跑报告.md`

## 二、Schema／数据格式（完整）
**输入**：Gemini 实体输出 JSON（#564 口径，字段同 `*.entity.json` 的 `entities[]`，`target.status` 一律 `new_candidate`）。
**输出**：同格式 `*.entity.json`（经 N1–N7 过滤／修正后），外加 `postprocess_log.tsv`：`rule`（N1…N7）｜`entity_id`｜`action`（`delete`／`retype`／`split`／`rebind`）｜`before`｜`after`。
**报告** `vol04试跑报告.md`：各规则触发数、与 Claude 对照 F1、抽样 30 span 的假命中数、结论（过／停在 vol04）。样例 log 行：`N1	e00812	delete	work:彖傳	-`。

## 三、程序架构
- 新写 `entity_postprocess.py`：规则表驱动（每规则一函数，注册于 `RULES`），`--rules N1,N2,N7` 选择，`--dry-run` 只出 log；N4（异体归一）、N5（重对现库）复用 `zi_convert.py`、`entity_apply.py --rematch`（P2）；N6（简称归并）、N7（朝代前缀拆分）新写。
- 测试：`scripts/book-text/tests/test_entity_postprocess.py`，用 `专名匹配/` 里试点已核的 25（N1）／10（N2）／4（N3）／3（N7）个真实例作断言。
- 入口：`python3 entity_postprocess.py in.entity.json --book-index <path> -o out.entity.json --log postprocess_log.tsv`。运行云端。

## 四、步骤流程
| 步 | 做什么 | 输入标准 | 产出 | 验收标准 | 谁验 | 估时 |
|---|---|---|---|---|---|---|
| 1 | N1／N2／N3／N7 正则规则＋单测 | `修订判准-试点后.md` N1–N10 为准；P2 步 1 的规则卡出 | 脚本 v0＋测试 | `python3 -m unittest` 全绿；在 vol02／03 现有实体上 dry-run，N1 命中 ≥25、N2 ≥10、N3 ≥4、N7 ≥3（不少于试点数）| Tamsin | 90 分钟 |
| 2 | N4／N5／N6 | 步 1；P2 `--rematch` 可用 | v1 | 在 vol02／03 上重现试点结果：N6 命中應麟≥8（10-12 改：不跨段；试点的 9 是跨段口径）；单姓简称（鄭／元）放弃，不设验收线（Lucian 抽样精度差，由 N8／P3 覆盖） | Tamsin | 60 分钟 |
| 3 | 取输入（2026-10-12 改）：**改用 vol02**（`wip/siku` 已有 `002.lines.md`，Lucian 实测 806269d3）→ `siku_volume_extract.py gemini-export` → push `wip/siku`；叫醒 Dana，只跑第 1 份（part 1）。vol04 待 Lucian 写「vol04 定稿，commit xxx」后另跑，不再阻塞本块 | 步 2 完成；P2、P3 已合并（vol02 实体层已是人核终稿，作金标） | Gemini 输出 JSON | Dana 回执含输出路径；JSON 可读且 entities 数 >0 | Dana／Tamsin | 视 Gemini（机器） |
| 4 | 与 vol02 终稿实体层（金标）及 Claude 原输出同段对照，算 F1 | 步 3 | 对照表 | 对金标 F1 ≥0.9（#564 口径）；<0.9 停并写原因 | Tamsin | 30 分钟 |
| 5 | 跑 `entity_postprocess.py`，抽 30 span 看假命中 | 步 4 过线 | 日志＋抽样表 | 假命中 ≤2/30 | Tamsin、Eric 抽 | 40 分钟 |
| 6 | 写 `vol04试跑报告.md`，在 #564 与 #574 回卡 | 步 5 | 报告 | 报告含上述全部数字；结论明确「可推 vol05」或「停在 vol04」 | Maren | 20 分钟 |

## 五、测试数据与金标
金标＝vol02／03 试点已人核的 N1–N7 改动（`命中统计与未命中清单`、`回挂-B档…`）；vol04 部分以 Claude 同段输出为对照，抽 30 span 人看。

## 六、与其他块的接口
| 方向 | 对方块／负责人 | 文件／格式 | 何时交接 | 对方已确认？ |
|---|---|---|---|---|
| 入 | Lucian（#10 整册整理） | vol02 `002.lines.md`（已有）；vol04 定稿后另跑 | 步 3 前 | 已确认有 vol02 |
| 入 | Dana | Gemini 输出 | 步 3 | 待 |
| 出 | P2 | 规则卡反馈（假阳性例） | 步 5 | 待 |

## 七、风险与未决
最可能出错的一处：Gemini 对书名误标成篇名，F1 不达标——不达标则停 vol04，不影响 P1–P7 收口。依赖 Lucian 的定稿时间；若 B3 拖延到下午，P8 步 1–2 交 Lucian 接（Lucian 已在 #564 接受备选，须在 #574 说「接」后才动，避免撞车）。步 3 改 vol02 的取舍：优点是有金标、不等人审；缺点是 vol02 本身是 Gemini 输出的对象之一、不检验“新册”泛化，所以验收报告里写明，vol04 定稿后另做一次抽样。

## 八、评审
| 日期 | 评审人 | 结论 | 意见 |
|---|---|---|---|
| 2026-10-12 | Maren | 通过 | 备选执行人 Lucian 我会当面通知（另需他在 #564 回 vol04 定稿）；步 1–2 若 B3 步 2 仍占 Tamsin，下午直接转 Lucian，不等再问。 |
