# book-text 文档索引

> 2026-10-15（GUJI-361）起，原 overview `项目进展/古籍文本/` 与 `项目进展/专名识别与链接/` 的长期文档迁入本目录。已过时的历史报告没有迁，需要时从 overview 提交 `af1f3f6f3`（迁移前最后一版）取。
> 与 `open-guji/guji-format` 的 spec 有重叠的设计稿，**以 guji-format 为准**；本目录的设计稿是背景与来龙去脉。

## design/ 规范与设计
| 档 | 内容 |
|---|---|
| `2026-09-book-text格式规范.md` | 格式规范 v1，由 `scripts/validate_text_format.py` 执行 |
| `2026-10-文本版本号与仓库流程.md` | v2：main 受保护走 PR；`original` 的文本／标点／实体三线 semver；`bump_original.py`；F-OV-01～04 |
| `2026-10-已发1x文本修订流程.md` | 1.x 之后一律「意见→人裁事件→revise 落地」，每步留记录，撤销靠追加事件 |
| `2026-10-改字清单.md` | 文本 0.x 精校期改字清单 NNN.char-edits.json：单格替换登记后 F-OV-02 降软提示，`char_edits.py record/sync` 同步标点、实体校验字（草案，待 A34/A42 定稿） |
| `2026-10-修订流程自动化设计.md` | 修订流程的自动化：调和器、对象存放与状态、schema（意见、发布批、格谱系、算法重跑、策略、度量）、落地顺序 |
| `2026-10-每字坐标格式-v0.1.md` | 每字带坐标的自校文本格式（cv 仓副本，以 cv 仓为准；v1 草案及样例已删） |
| `2026-10-decision.json规范草案.md` | decision.json 草案（已废弃，见下一行） |
| `2026-11-book-text只录首选字.md` | book-text 只录首选字；删 decision.json；待审信息只在中心库／KV（2026-11-09 定） |
| `2026-09-展示格式方案.md`、`展示样张/` | 展示格式（用户已定）与样张 |
| `2026-09-表格记法方案.md` | `:::table` 表格记法（宋史已上线） |
| `2026-10-图片格与插图设计.md`、`图片格样例/` | 文本中插入图片：图片格（占一格的图形）与插图块；char `fig`、cord `marks.figure`、新文件 `NNN.fig.json`（GUJI-737，10-23 已评审） |

## 专名/ 专名判准与规则（GUJI-44）
`修订判准-试点后.md`（`entity_postprocess.py` 的依据）、`消歧规则.md`、`补标判读规则.md`、`专名标注格式契约-草稿.md`。建档清单、建档结果、不建档清单、试点差异清单、总计划与分块、`data/` 等过程记录已清理，需要时从清理前的提交取（见 git 历史）。

## reports/ 长期有用的报告
元素类型清单（07）、与 guji-markdown 对齐（08）、全文搜集落点（11）、四庫页眉剥除判准（48）；换图源重挂代处理／坐标迁移清单（GUJI-748，早期各册版本日志（已于 2026-11-10 删除，历史在 git log）引用过，勿删）：`2026-10-26-vol04-…`、`2026-10-27-vol01…vol18-…`。其余一次性报告已清理。

## 其他
`VERSIONING.md`（版本号摘要）、`ORIGINAL.md`（original 文件体系）、`GUJI-FORMAT-PIN.md`（guji-format pin）。脚本见 `scripts/README.md`。
