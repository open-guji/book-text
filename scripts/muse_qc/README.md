# muse_qc：维基清洗抽读质检的 muse 驱动

任务书：[T16-muse试点-维基清洗抽读质检](../../../总调度/古籍索引三块/任务书/T16-muse试点-维基清洗抽读质检.md)。
本目录只产候选文件，不直接改任何数据；`book-text` 全程只读。

## 管线

812 段真实数据 ＋ 30 段坏样本 = 842 段超过 muse 一个额度窗口（约 470 次调用），
文本总管 09-27 00:2x 批复**分两步跑**：第一步 230 条（30 坏样本全带 + 200 条按
13 部占比分层抽样）先算召回率/误报率；达阈值（召回 ≥90%、误报 ≤15%）才跑
剩下 612 条，且要等下一个 muse 窗口。

```bash
# 0. 前提：本机已装 muse 并登录（TBH_CREDENTIAL_BACKEND=file muse login，
#    只由用户在会话里直接发起，见 muse外包怎么用.md §三·3）

# 1. 只读 clone book-text
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/open-guji/book-text /tmp/book-text

# 2. 切段（十三經写死在 chunk.py 里，13 部 626 章 → 812 段）
python3 chunk.py --book-text /tmp/book-text --out chunks.jsonl

# 3. 造坏样本（30 段，六类各 5，固定随机种子可复现）
python3 seed_defects.py --chunks chunks.jsonl --out seeded.jsonl --seed 20260927

# 4a. 第一步：分层抽 200（按 13 部占比、最大余数法凑整），留出剩余 612 备第二步
python3 stratified_sample.py --chunks chunks.jsonl --n 200 --seed 20260927 \
    --out-sample stage1_real_200.jsonl --out-remaining stage2_remaining_612.jsonl

# 4b. 合批：第一步 200 条真实 + 30 条坏样本 = 230 条，打乱顺序
python3 build_batch.py --chunks stage1_real_200.jsonl --seeded seeded.jsonl \
    --out batch_stage1.jsonl --seed 20260927

# 5. 跑批（并发 ≤8，可续传；撞 429 全体自动冷却 60 秒再试，不重试风暴）
python3 run_muse.py --batch batch_stage1.jsonl --template prompt_template.txt \
    --schema schema.json --out results_stage1.jsonl --log muse_calls_log_stage1.json \
    --concurrency 8 --max-model-steps 2

# 6a. 对照一：召回率（用 seeded.jsonl 的真值核对）
python3 analyze_recall.py --results results_stage1.jsonl --seeded seeded.jsonl --out recall_report.json

# 6b. 对照二：误报率抽样（50 条 muse 判 ok + 20 条判 suspect，供 Claude 逐条复核；
#     第一步只有 200 条真实数据，suspect 池可能不够 20 条，脚本会打印警告并全取）
python3 sample_for_review.py --results results_stage1.jsonl --chunks chunks.jsonl \
    --out review_sample.jsonl --seed 20260927 --n-ok 50 --n-suspect 20
# 复核：把 review_sample.jsonl 每条的 my_verdict/my_note 填上，另存一份
# review_sample_reviewed.jsonl，与 muse_verdict 对比，报一致/不一致

# 7. 达阈值后、下一个 muse 窗口：跑剩下 612 条（不用再带坏样本，召回率已在第一步验过）
python3 build_batch.py --chunks stage2_remaining_612.jsonl --out batch_stage2.jsonl --seed 20260927
python3 run_muse.py --batch batch_stage2.jsonl --template prompt_template.txt \
    --schema schema.json --out results_stage2.jsonl --log muse_calls_log_stage2.json \
    --concurrency 8 --max-model-steps 2
# 全部真实结果 = results_stage1.jsonl 里的 200 条真实部分 + results_stage2.jsonl 的 612 条
```

## 给以后的抓取道复用：一键质检一批书（通用版，T15 批一验证过）

`chunk.py`（写死十三經）只是试点用的第一版。跑法验证过之后已经抽出通用版：

```bash
# manifest.json 形如 {"work_id": "书名", ...}，书名只用来核对 index.json 的
# version_label，随便一批 book-text Work 都能喂
python3 chunk_works.py --book-text /path/to/book-text --manifest manifest.json --out chunks.jsonl

# 有「大部头」只想抽样（如总字数太大、优先级低）时：
python3 select_bigbook_sample.py --chunks chunks.jsonl --big-work-ids ids.txt \
    --fraction 0.2 --seed <种子> --out chunks_selected.jsonl
```

其余 3–6 步（造坏样本、合批、跑批、对照）不用改，把 `--chunks` 换成
`chunks_selected.jsonl`（或不抽样就直接用 `chunks.jsonl`）即可。

**账号共用额度要分窗跑**：一批调用数远超一窗（约 400–470 次）时，按约 400 次一窗
切成多个 `batch_wNN.jsonl`（简单按行数切，不用再打乱——`build_batch.py` 已经打乱过
一次），一窗跑完再跑下一窗，把窗口让给其他 muse 驱动道；`run_muse.py` 的续传是按
`chunk_id` 去重，同一个 `--out` 文件重复调用多个窗口是安全的。

**大批量的中间产物不进 git**：`chunks.jsonl`／`batch.jsonl` 这类嵌了原文全文的
文件，批量一大就是几十上百 MB——它们能靠 `chunk_works.py` + manifest + 固定随机种子
**确定性重新生成**，没必要占 overview 仓的历史。放到会话的 scratchpad 目录里跑，
`muse_qc/` 目录只留脚本、manifest、`seeded*.jsonl`（体量小，且装着「哪段被注入了
什么」的真值，值得留痕）、和最终的 `results*.jsonl`／`recall_report.json` 等结果文件。

## 各脚本

| 脚本 | 做什么 | 依赖 muse |
|---|---|---|
| `chunk.py` | 切段，写 `chunks.jsonl` | 否 |
| `seed_defects.py` | 造 30 段坏样本，写 `seeded.jsonl` | 否 |
| `stratified_sample.py` | 按 13 部占比分层抽样（第一步 200 条 + 剩余 612 条） | 否 |
| `build_batch.py` | 合批打乱（`--seeded` 可留空） | 否 |
| `run_muse.py` | 逐段调 `muse exec`，写 `results.jsonl`＋`muse_calls_log.json` | **是** |
| `analyze_recall.py` | 算召回率，写 `recall_report.json` | 否（读 `run_muse.py` 的产物） |
| `sample_for_review.py` | 抽样误报率复核样本，写 `review_sample.jsonl` | 否（同上） |

## 已知坑

- `muse exec` 的输出偶尔在 `quote`／`note` 字段里带 `{`／`|` 这类字符（原文摘录本身
  就是维基残留标记），朴素的「找第一段花括号配平」解析会数错——`extract_json` 必须
  跳过字符串字面量里的花括号，`run_muse.py` 已修（自测过 5/842 条命中过这个坑）。
- 输出格式在真跑之前只能按 [Step6 的实测](../../../图片初步数字化/进度/Step6-上下文裁决/进度卡-Step6词典加AI.md)
  假定（`--prompt-file` 没有变量替换参数，所以每次调用要把变化的内容整份拼进新的
  prompt 文件里，`run_muse.py` 就是这么做的）；真跑第一批后如与实测不符，按此规矩
  改脚本、把出入记进报告。
- `muse exec` 偶发瞬时失败（`exit=1: local session messaging disabled` 这行提示
  是固定伴随输出的无害信息，不是真实原因；或 180 秒超时，說文解字这类一段里要列
  几十处缺陷的长输出尤其容易撞）。`run_muse.py` 按 `chunk_id` 去重可续传，降并发
  （8→4→1）直接重跑基本都能过，重试率一般在 0.5%–1.5% 之间，正常现象，不是
  脚本或登录的问题；默认超时已从 180s 提到 300s。
- **误报率复核时，摘录（`quote`）偶尔有 muse 自己转写引入的轻微 drift**（最常见
  是把原文的繁体字转写成形近简体/异体，如「爲」→「為」、「鳴」→「鸣」、「掃」→
  「扫」），导致摘录字面在原文里搜不到（逐字 `in` 判断会是 `False`）。**这不代表
  muse 编造了问题**——多次人工核对后，缺陷本身都是真的，只是复制原文这一步笔误了。
  核对摘录对不上的几条时，先去原文里人工确认缺陷是否存在，别因为摘录对不上就
  当成误报算进「不一致」。
