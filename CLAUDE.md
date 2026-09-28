# book-text

古籍全文数据仓，由文本总管管理。数据的格式规范、判准、脚本和任务卡都在 `open-guji-core/overview`：
- 任务：看板 issue，标签 `块:文本`；
- 规划：`项目进展/总调度/规划/文本.md`；
- 格式：`项目进展/古籍文本/`；
- 脚本：`scripts/fetch-book-fulltext/`、`scripts/book-text/`。

本仓的会话如需读 overview，用只读方式 `add_repo`（access: read）。

## 提交与推送

- **直接提交到 `main` 并推送，不开分支、不开 PR。** 全文入库是批量数据提交，一直按这个惯例办（book-text 本身没有 CI，也没有 PR 审阅流程）。
- 推之前先 `git pull --rebase origin main`。有多条道同时往本仓推，冲突多半出在 `index/full_text/`。
- `index/full_text/` 一律用 overview 的 `scripts/book-text/build_index.py --root <本仓>` 重建，rebase 之后再重建一次。**不要手改，也不要用别的脚本生成。** 别的脚本会丢掉 `primary` 标记。
- commit message 用中文，写清是哪条道、哪一批、入库多少部。

## 目录

- 全文放在 `Work/<c1>/<c2>/<c3>/<work_id>/full_text/<来源>-NN/`，例如 `wikisource-01`、`kanripo-01`。版本已知的放 `Book/.../full_text/`。
- 每份全文一个 `index.json`，章节按 `NNN.md` 编号。
- 同一个 Work 有多份全文时，由 `build_index.py` 选出唯一的 primary。维基优于 Kanripo。另一份来源记在 primary 那份的 `other_sources` 里。

## 授权

逐文本授权，以各自 `index.json` 的 `source.license` 为准，详见 README「授權」一节。

## 写域

只动任务卡上「写域」一行列出的目录，别的道写的全文一律不碰。
