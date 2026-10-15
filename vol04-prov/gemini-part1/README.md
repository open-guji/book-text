# vol04 part 1 Gemini 实体标注（仅验 matcher，未定稿）
- 输入：004.lines.md（prov/vol04-unfinalized）经 siku_volume_extract.py gemini-export 切出 part01（P001–P072，72 段 4863 字）。
- 模型：gemini-3.8-flash-high（agy -p），#435 提示＋#564 首行「不要调用任何工具，直接在回答里输出结果」，一次调用。
- 自检：72 段齐，去标点／专名标记后与原文一致；P018 首次多插「·」，单段重跑后合格（重跑只改这一段）。
- 导入：gemini-import --parts 1，**book-index 用空目录**，故「命中 0」，实体全是新候选，由 matcher 自行重挂。
- 注意：004.entity.json 里 part1 之外的段（P073 起）没有 Gemini 标注，那部分实体来自导入脚本自身规则，不要当 Gemini 结果。
- part01.out.txt 为 Gemini 原样段文件。
