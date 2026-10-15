# vol04 part1 试跑（未定稿，仅验 matcher）

> **vol04 未定稿，仅验 matcher，不入正式数据。** Tamsin，2026-10-14（洛杉矶）。GUJI-18。
> 输入：book-text 分支 `dana-vol04-gemini-part1`（759dca54）`vol04-prov/gemini-part1/004.entity.json`（394 条，part1 P001–P072）＋ `prov/vol04-unfinalized`（f62ad8173）的 `004.char.json`／punct；book-index d0a897e7e3。

## P8 `entity_postprocess.py`（N4 开）
- 实体 394 → 406。触发：N6 add 11、N4 rebind 2、N7 split 1；N1／N2／N3 为 0（这些规则针对易類一与总叙，vol04 part1 无对应误标，属预期）。
- 校验线（F1≥0.9 对金标、30 span 抽样假命中≤2）**未做**：vol04 没有金标，抽样人工核留给定稿后的复核卡。

## matcher 重对现库（`t543_rematch.py`，下面是工具原样输出，对象含 N6 新增的 12 条，共 404 个）

| 类型 | EXACT（字面已在库） | VARIANT（归一后命中） | NONE（库里没有） |
|--|--|--|--|
| work | 98 | 1 | 64 |
| people | 97 | 3 | 74 |
| place | 0 | 0 | 0 |
| office | 0 | 0 | 0 |
| dynasty | 33 | 0 | 12 |
| reign | 0 | 0 | 0 |

## 一、可回挂（new_candidate 且库里**恰好一个**命中）


单命中可回挂：EXACT 123、VARIANT 4；多命中 105；NONE：work 64、people 74、dynasty 12。VARIANT 4 条与 NONE 清单未抽审。
