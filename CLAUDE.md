# book-text

古籍全文数据仓。数据的格式规范、判准、脚本和任务卡现分布如下（2026-10-15 起 overview 拆空）：
- 任务：Jira（项目 GUJI），标签 `项目-X`；
- 规划：`open-guji-core/ai-team` 的 `team/文本/`（目标、队列、台账）；
- 格式与判准：本仓 `docs/`（索引见 `docs/INDEX.md`：`docs/design/` 规范与设计、`docs/专名/` 专名判准与建档记录、`docs/reports/` 报告）；
- 脚本：本仓 `scripts/`（见 `scripts/README.md`）；抓取脚本 `scripts/fetch-book-fulltext/` 仍在 overview 根，待迁。

仓根 `scripts/`、`.claude-inbox/` 不属数据，不要当数据目录处理。

校验脚本（`scripts/validate_text_format.py`、`scripts/validate-collated.py`、`scripts/original_version.py`）与 `scripts/book-text/` 下的工具脚本（`bump_original.py`、`build_texts_index.py` 等）**只在本仓一份**（2026-10-15 GUJI-361 起 overview 拆空，已迁入，不再有 drift 检查）；以本仓 CI（`check.yml`）所跑的为准。

## 提交与推送（10-05 起：main 受保护，一律走 PR）

- **不直接推 main。** 一批活开一个分支，命名 `<道名>-<主题>`，比如 `t65-wiki-match`；`wip/` 前缀是反复改动中的工作分支，用户点头前不并 main。
- 分支上可以多次提交；**整批做完才开一个 PR**，不要零碎开 PR。**PR 自建、自审、自合并**（2026-10-24 用户定，取代原「文本总管审」）：提 PR 的会话自己读 diff、跑校验，与最初定下的设计和要求一致就自己用 **squash merge** 合并，main 上一个 PR 只留一个提交。
- 开 PR 前，先把 main 合进分支，用本仓 `scripts/book-text/build_texts_index.py --root <本仓>` 重建 `index/texts`，然后跑完三项校验，结果贴进 PR 描述：
  1. `scripts/validate_text_format.py <本仓> --strict --baseline scripts/format_baseline.json` 退出码 0；
  2. `scripts/validate-collated.py --root <本仓>`（不带 `--strict`）退出码 0，且没有本 PR 新增的问题（存量：`d59f1iqd854w/default/108.md`）；
  3. 重建索引后分支上没有未提交的 diff。
- **PR 不再跑云端 CI**（2026-10-20 用户定，仓库大、PR 频繁）：开 PR 前在本地跑 `python3 scripts/local_check.py`（只查改动条目，几秒；`--all` 全仓），结果贴进 PR 描述。云端 `check.yml` 只留每夜全量（洛杉矶 04:00）和手动触发兜底，出问题再修。
- `index/texts/` 不要手改；分支里可以先不管它，开 PR 前对齐 main 后再重建。
- **版本号只管 `original`**（本项目自己从书影做的文本），文本、标点、实体三条线各自独立 semver；维基、Kanripo 不跟踪版本。major 是质量等级（1 可用／2 出版级／3 定本），从严、要用户点头；规则见本仓 `docs/design/2026-10-文本版本号与仓库流程.md`，摘要见 `docs/VERSIONING.md`。升版本一律用本仓 `scripts/book-text/bump_original.py`（首次并 main 用 `--init` 定 1.0.0；它同时写 `<版本目录>/CHANGES.md`），不手改版本号（major 除外：手工改并附验收记录）；校验器规则 F-OV-01～03 把关。
- 合并：日常批次自审过就合（见上）；与原设计有偏离、撤除超过 50 部、改全仓结构或规范、`original` 升 major 的，先问用户。
- PR 描述和评论不写 Claude Code 署名。
- **组字式一律保留原样**：`[口*恒]`、`[薛/女]`、`{宀兒}`、`[B18D]` 这类 CBETA／维基组字式记的是字形，不得批量换成 `□`（10-01 T56 误换 4,467 处后已撤回，`3f8cbb0586`）。要转正字用本仓 `scripts/zi_convert.py`，查不到正字就保留组字式。
- commit message 用中文，写清是哪条道、哪一批、入库多少部。

## 目录（09-30 起新结构）

条目布局以 guji-format spec/07 为准（旧稿 overview `项目进展/古籍索引网站/设计/阅读文本.md`（#307） 仅作背景）。

- 每个条目（Work 或 Book）一个目录 `<Work|Book>/<c1>/<c2>/<c3>/<id>/`，其下：
  - `manifest.json`：本条目全部版本的清单（key、kind、label、source、source_name、source_url、license、quality、chapters_total）。`kind` 取 `transcription`／`collated`／`self_collated`，另有 `edition_label`、`is_original`、`note`、`visibility`，完整字段见 spec 07 §2.2。`versions[0]` 永远是 `default`。
  - `default/`：主版本。`<key>/`：其他版本，key 按来源取 `collated`／`wikisource`／`kanripo`／`shidian`，同源第二份起 `wikisource-2`。key 只用 `[a-z0-9-]` 且字母开头；`default`／`manifest`／`fragments`／`sources`／`extra` 是保留字，不能作非主版本 key。`fragments/`（辑佚）、`sources/`（抓取素材）与版本目录同级。
  - 每个版本目录：`index.json`（章目录 `chapters[{n, file, title, has_json}]` 及该版本特有元数据，含 `other_sources`）＋ `001.md`、`002.md`…；整理本另有同名 `001.json`。
- **主版本怎么定**（用户 09-30 定）：整理本 → 维基 → Kanripo → 识典，章数只在同一来源内部比。新加的版本若排位高于现 default，就把现 default 挪成按来源命名的 key，新的放进 `default/`。
- 同一个 Work 已有全文的，一般不再收第二份（#26），另一来源记在已收那份 `index.json` 的 `other_sources`。
- 加版本请用 overview 的入库脚本（见 #307／各道任务卡），它会同时改 manifest；改完跑 `build_texts_index.py`。

## 授权

逐文本授权，以各条目 `manifest.json` 里每个版本的 `license` 为准，详见 README「授權」一节。

CC0 1.0 只给 `is_original: true` 的版本；其余转录、整理本只能是上游明确的 CC 许可（如 BY-SA 4.0）或固定串 `来自网络，版权未知`；不许 `null`、`未知`、`unknown`。CI 的 V3（check_license）强制。（spec 07 §二）

## 写域

只动任务卡上「写域」一行列出的目录，别的道写的全文一律不碰。
