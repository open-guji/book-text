# 官名升格任务书（带教：Sienna → Stella）

卡：GUJI-176（总：GUJI-115）。2026-10-13 洛杉矶。

## 一、任务
把 book-index-draft 里的 office（共 1794 条未升格）按“常见”顺序升格到 book-index。升格 = 内容不改，只换 id 和位置，**只经 bim 的 `promote` 写**，不手改 `promotions/`。

## 二、判准（一条一条判，写进处置表）
对每条 office 给出处置，五选一：
1. **升格**：官名确是一个固定官职（有品级／职掌／朝代），草稿字段完整、依据在 `basis`，且属“常见”（A 侧命中频次表到前用 Sawyer 的 F 道清单当优先序）。
2. **改别名**：其实是已升格条的异写／简称（如“秘書省”→已有条的别名）。在已有条上加 alt_names，**至少两条独立原典依据**，不单独升格。
3. **不建档**：泛称、非官职（如“某官”“太守之类”的类称）、与别条重复。
4. **转A**：名称里夹地名／人名／朝代，需 A 侧切分，不是实体问题。
5. **暂缓**：草稿字段缺（朝代、上级、概念条缺）、需要补。写明缺什么。

升格前必查：
- **闭包**：`dynasty_ids`、`parent_id`、`concept_id`／`institution_ref` 等所有指向草稿 id 的引用，链上每一条也必须升格（或已升格）。闭包不全会在正式库悬空。我给你的 `p6_closure` 思路：沿引用递归，已在 `promotions/` 里的不再带。
- **同名不是重复**：同名异朝代、异地的先看 history／dynasty，别合并（寧鄉縣就是两个地方）。
- **依据**：只能写自己读过的公版原典（《新唐書》《宋史》《元史》《明史》《清史稿》《讀史方輿紀要》等）；CBDB／CHGIS 只用来人工核对，不抄编号、不进字段。**凑不到两条独立依据就不动，写“不动＋理由”，不拿印象凑。**

## 三、流程（跟我 P6 同一套）
1. 在 overview `项目进展/总调度/古籍索引三块/排班.md` §一登记一行（book-index × 你的分支名），收工改“已释放”。
2. 写批文件 `batchN.txt`（每行一个草稿 id，可带 `# 名称`）。
3. 分支：book-index `stella/promote-bN`，book-index-draft `stella/promote-dN`，都从 origin/main 切。
4. 干跑：`cd book-index-manager && python3 -m book_index_manager promote --batch batchN.txt --root /home/user/open-guji --dry-run`；再真跑去掉 `--dry-run`。
5. bim **不会**改写 office 的 `dynasty_ids`（草稿朝代 id）：用 overview `scripts/book-text/p6_fix_refs.py <正式库根> <新增文件...>` 补成正式朝代 id。
6. 门禁：`python3 .claude/qa/check_v2.py --root . --paths <新增文件>` ERROR=0；`python3 -m book_index_manager validate-promotions --root /home/user/open-guji --verbose`，新增的 E04（正式库条指向草稿 id）必须 0。
7. 两个 PR（正式库＋草稿库墓碑）一起提，每批 ≤50 条，PR 号回 GUJI-176 评论，Mirren 审、合并由经理。

## 四、交付格式（每批）
- 处置表 TSV：`草稿 id｜名称｜处置(升格/改别名/不建档/转A/暂缓)｜依据（书名＋卷，改别名写两条）｜备注`
- 成账：在 overview `项目进展/古籍文本/专名匹配/` 追加 `建档结果-官名-批N.md`：规范名→草稿 id→正式 id（版式同 `建档结果-地官朝号.md`）。

## 五、验收与放量
- 先做 Sawyer 的 F 道清单（49 行）当试做批；我抽检**≥20%**，处置一致率≥**85%** 才放量到每批 50。
- 地名／官名错一处依据即回炉，不放过。
- 门禁 0 错；闭包 0 悬空。

## 六、边界
不合 PR、不发布、不动仓库变量；不确定就不改、只报。进度写 GUJI-176 评论，抬头“「文献学者｜Stella」”。
