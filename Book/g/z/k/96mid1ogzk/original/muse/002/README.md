# vol02 part01 专名对照：muse 批次（overview#397 第 2 步）

- `batch.jsonl`：34 条，一段一条，取自 `../../gemini/002/in/part01.txt` 的 P001–P034（终稿三）。
- `prompt_template.txt`：只标专名（`{人/地/官/朝:…}` 和《》），不加标点，不改字。
- `schema.json`：`{chunk_id, annotated}`。
- 跑法（muse 驱动道，并发 2）：
  ```bash
  python3 <overview>/项目进展/古籍文本/scripts/muse_qc/run_muse.py \
    --batch batch.jsonl --template prompt_template.txt --schema schema.json \
    --out results.jsonl --log muse_calls_log.json --concurrency 2 --max-model-steps 2
  ```
- 产出：`results.jsonl` 和 `muse_calls_log.json` 推回本目录。这是候选，T66 负责收回，并和 GLM、`ref-claude` 做对照。
