# book-text

古籍全文数据仓，由文本总管管理。数据的格式规范、判准、脚本和任务卡都在 `open-guji-core/overview`：
- 任务：看板 issue，标签 `块:文本`；
- 规划：`项目进展/总调度/规划/文本.md`；
- 格式：`项目进展/古籍文本/`；
- 脚本：`scripts/fetch-book-fulltext/`、`scripts/book-text/`。

本仓的会话如需读 overview，用只读方式 `add_repo`（access: read）。

## 提交与推送

- **直接提交到 `main` 并推送，不开分支、不开 PR。** 全文入库是批量数据提交，一直按这个惯例办（book-text 本身没有 CI，也没有 PR 审阅流程）。
- 推之前先 `git pull --rebase origin main`。有多条道同时往本仓推，冲突多半出在 `index/texts/`。
- **两步提交，避免 `index/texts/` 冲突**：先只提交 `Work/`、`Book/`（不带 `index/texts`）→ `git pull --rebase origin main`（不会冲突）→ 重建 `index/texts` 单独提交 → 推送。
- 本地已经卡在 `index/texts` 的 rebase 冲突、又被权限拦住时，不要绕：`git rebase --abort`，把提交推到自己的分支（`git push origin HEAD:refs/heads/<道名>`），在卡上说一声，由文本总管合进 main 并重建索引。
- `index/texts/` 一律用 overview 的 `scripts/book-text/build_texts_index.py --root <本仓>` 由各条目 `manifest.json` 汇总重建，rebase 之后再重建一次。**不要手改。**（旧的 `index/collated`、`index/full_text` 与 `build_index.py` 已随 09-30 迁移停用。）
- **组字式一律保留原样**：`[口*恒]`、`[薛/女]`、`{宀兒}`、`[B18D]` 这类 CBETA／维基组字式记的是字形，不得批量换成 `□`（10-01 T56 误换 4,467 处后已撤回，`3f8cbb0586`）。要转正字用 overview `项目进展/古籍文本/scripts/zi_convert.py`，查不到正字就保留组字式。
- commit message 用中文，写清是哪条道、哪一批、入库多少部。

## 目录（09-30 起新结构，规格见 overview `项目进展/古籍索引网站/设计/阅读文本.md`，#307）

- 每个条目（Work 或 Book）一个目录 `<Work|Book>/<c1>/<c2>/<c3>/<id>/`，其下：
  - `manifest.json`：本条目全部版本的清单（key、kind、label、source、source_name、source_url、license、quality、chapters_total）。`versions[0]` 永远是 `default`。
  - `default/`：主版本。`<key>/`：其他版本，key 按来源取 `collated`／`wikisource`／`kanripo`／`shidian`，同源第二份起 `wikisource-2`。
  - 每个版本目录：`index.json`（章目录 `chapters[{n, file, title, has_json}]` 及该版本特有元数据，含 `other_sources`）＋ `001.md`、`002.md`…；整理本另有同名 `001.json`。
- **主版本怎么定**（用户 09-30 定）：整理本 → 维基 → Kanripo → 识典，章数只在同一来源内部比。新加的版本若排位高于现 default，就把现 default 挪成按来源命名的 key，新的放进 `default/`。
- 同一个 Work 已有全文的，一般不再收第二份（#26），另一来源记在已收那份 `index.json` 的 `other_sources`。
- 加版本请用 overview 的入库脚本（见 #307／各道任务卡），它会同时改 manifest；改完跑 `build_texts_index.py`。

## 授权

逐文本授权，以各条目 `manifest.json` 里每个版本的 `license` 为准，详见 README「授權」一节。

## 写域

只动任务卡上「写域」一行列出的目录，别的道写的全文一律不碰。
