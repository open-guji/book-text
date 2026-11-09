# book-text 只录首选字（2026-11-09 sheldon 定）

## 决定

1. **book-text 里每格只录一个字，就是首选字。** 待审的字和其他字看起来一样，不加任何标记；不录待审原因、候选、人裁、置信度。
2. **□ 只表示真阙文**（`lacuna: true`，审过定阙）。待审不等于阙文。
3. **删掉 `decision.json`**（候选字层），不再生成、不再声明。
4. **其他待审信息都在中心库待审单 → 网站 KV**：待审原因 `pending_reason`、候选（参校本、字形库、相似字、上下文）、人裁事件、网站票。这些改得快，不经 book-text。
5. **book-text 不要频繁改**：一个字从定字转到待审，只要首选字没变，book-text 不动，只是多一张待审单。

## 首选字怎么取

导出时（guji-manager `formats/guji_char_cord.apply_pending`，cv `export_guji_format --pending` 与 `republish.py` 入库都调它）：

- 机器已经给了字的格：就是它，不动。
- 机器没给字（现为 □）的待审格：按待审单该格取 `first_choice`，次序为
  旧人裁失效前的字 `stale.c` → 参校本 `ref.c`／`refc` → 字形库 `lib_top[0]` → 相似字 `alt[0]` → 上下文 `ctx.c`（只认单字）。
  这与网站候选的排序一致（参校本第一，用户 09-06 定）。
- 一个候选都没有：保持 □（少数，等人审）。

## 三处文件的分工（改后）

| 位置 | 管什么 | 谁改、多快 |
|---|---|---|
| book-text `NNN.char.json` | 现在显示什么字（首选字或定字；真阙文 □） | 换包、修订时改，升版本 |
| 中心库 `feedback/lists/proofing/<书>/<章>.pending.json` → 网站 KV | 哪些格还要人看、为什么、候选、图 | 每轮出单即换，不动 book-text |
| 中心库 events | 人裁事件 | 随投票随写 |

## 校验

- F-OV-16 改为：char 里不许有 `pending_reason`，`$schema` 不许是 v0.4（按实际写法取 v0.1／v0.2／v0.3）。
- F-OV-05 改为：章条目不许声明 `decision_file`；`NNN.decision.json` 不在允许的文件名里。
- `scripts/tests/test_decision.py` 与夹具删除。

## 存量迁移（11-09）

- dev（4b7c15c7d）：殿本 96mid1ogzk 97 章、北行日录 988g7gsqhd 001、全唐文 995ejelvk0 005–015：去 `pending_reason` 3,836 格；其中现为 □ 的 3,644 格按中心库现行待审单写首选字（参校本 3,102、字形库 477、旧人裁 64、相似字 1）；标点、专名按 `auto_remap` 档 1 重投影；各章文本线、伴生线升 patch。
- 本 PR：殿本 001 去 `pending_reason` 7 格（中心库 001-r12 单与现行切分不同版，首选字等换新包时写）；删 `005.decision.json`。
- 没写首选字、仍是 □ 的：殿本 007、015（单与 char 切分不同版，共 116 格内的待审格）、无候选 63 格。等换新包或人审。
- 已知风险：首选字多数来自参校本，个别是错的（如殿本一处标题由「雜史類□三□」变成「雜史類臣三弁」），这正是待审单要人看的格；book-text 显示它，不再显示 □。

## 影响

- 新导出要用含新 `apply_pending` 的 guji-manager（dev f4cd492 起，发版后执行机才拿到）；旧版导出会带 `pending_reason`，过不了 F-OV-16。
- 网站阅读页不读 char 的待审字段（只读待审单），不受影响；`decision.json` 网站没有在用。
- guji-format：char v0.4 §4.8（`pending_reason`）与 08 decision 规范标为废弃。
