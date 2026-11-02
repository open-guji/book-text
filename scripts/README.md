# scripts/

> 2026-10-15 起（GUJI-361）overview 拆空，原在 overview 的脚本全部迁入本目录；**本仓是唯一一份**，不再有"两份同改"和 drift 检查（已删 `check_drift.py`、`overview-copies.sha256` 与 CI 的 drift 步骤）。

| 目录／文件 | 用途 |
|---|---|
| `validate_text_format.py`、`format_baseline.json` | 格式校验器，CI V2：`python3 scripts/validate_text_format.py . --strict --baseline scripts/format_baseline.json` |
| `local_check.py` | **提交前本地检查**：只查改动条目的 V2，加 V1／V3 与索引一致，几秒；`--all` 全仓。PR 不再跑云端 CI，用它代替 |
| `validate-collated.py` | 整理本校验（manifest／index.json／磁盘章文件一一对应），CI V1 |
| `check_license.py` | 授权串校验，CI V3 |
| `original_version.py` | `original` 三线版本号规则（F-OV-01～04） |
| `zi_convert.py` | 组字候选转正字 |
| `book-text/` | 原 overview 根 `scripts/book-text/`：`bump_original.py`（升版本，写 CHANGES.md）、`build_texts_index.py`（重建 `index/texts`）、`add_text.py`（入库）、`entity_*.py`、`t543_*.py`、`punct_compare.py`、`auto_remap.py`（新文本进来后一键对齐标点、实体：分档、修标题符位置、升版、出复核单）、`punct_redo.py`（文本改字后只重标受影响的句子：plan 出工作稿，apply 写回 punct／entity）等 |
| `entity/` | 原 `古籍文本/scripts/t_entity_*.py`（含测试）与 `check_draft.py`：专名候选、复合、拆分、命中统计 |
| `tools/` | 一次性／维护脚本：`table_convert.py`、`verify_md.py`、`recut_songshi_md.py`、`fill_missing_keys.py`、`fix_level_d59f2hr9pypt.py`、`tilda_missed_names.py` |
| `muse_qc/` | muse 质检驱动、提示词、schema。**jsonl 结果没有迁**（约 10.9M）：在 overview 提交 `af1f3f6f3` 的 `项目进展/古籍文本/scripts/muse_qc/*.jsonl` 可取 |
| `progress/` | `push_punct_progress.py`：把各册标点／专名版本与统计写进中心库 `progress.volume`（A33，后台「文本整理」用）；默认只打印，`--apply` 才写，各册合入 main 后再跑一次 |
| `tests/` | CI 的 pytest 目录；`book-text/tests/`、`entity/test_*.py` 为随脚本迁入的测试，暂未接入 CI |

脚本里原来写死的 `/home/user/overview/...` 路径已改为相对本文件目录；个别脚本仍读 overview 里的数据文件路径参数，使用时按需传参。
