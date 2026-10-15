# P3 步 4 抽检记录（Tamsin，2026-10-12）

> 对象：`P3-消歧记录-Tilda.tsv`（152 行，pick 86／pending 66）。方法：固定种子 `20261012`，从 pick 抽 27 条、从 pending 抽 3 条，共 30 条；逐条对照 `entity_disambig.py --list --book-index` 的 `candidate_info` 与上下文，再对不放心的回查 book-index 原档与册文。

## 结论

**错选 1 条（≤2），通过。** 错的一条：003:e00108 周易尚占，应改 pending。另按 Maren 裁定复核子夏易傳 6 条，见下。

## 30 条明细

| # | entity_id | 词 | 类型 | Tilda | 复核 |
|--|--|--|--|--|--|
| 1 | 003:e00123 | 周易衍義 | work | pick d59f2gpbg935 | 对 |
| 2 | 002:e00020 | 漢書 | work | pick d59f1iqd854w | 对 |
| 3 | 002:e00101 | 馬融 | people | pick hixhd2f8waip | 对 |
| 4 | 002:e00014 | 子夏易傳 | work | pick d59f2q7cquww | 对 |
| 5 | 002:e00073 | 王弼 | people | pick hixhd2h9bne6 | 对 |
| 6 | 003:e00480 | 漢書 | work | pick d59f1iqd854w | 对 |
| 7 | 003:e00419 | 明史 | work | pick d59f2mc8bta8 | 对 |
| 8 | 002:e00135 | 京氏易傳 | work | pick d59f207lglc0 | 对 |
| 9 | 002:e00921 | 王弼 | people | pick hixhd2h9bne6 | 对 |
| 10 | 003:e00108 | 周易尚占 | work | pick d59f2gmevr40 | **错**：此处是转述《經義考》「周易尚占三卷佚」，指寶巴（保八）已佚之书；库里李道純本是《總目》著录的另一部同名书。应 pending |
| 11 | 003:e00641 | 明史 | work | pick d59f2mc8bta8 | 对 |
| 12 | 002:e00636 | 虞翻 | people | pick hixhd2h9bne4 | 对 |
| 13 | 002:e01061 | 周易會通 | work | pick d59f2gpl4lxd | 对 |
| 14 | 003:e00553 | 明史 | work | pick d59f2mc8bta8 | 对 |
| 15 | 003:e00481 | 周易集注 | work | pick d59f2nkxg9hf | 对 |
| 16 | 003:e00523 | 周易集解 | work | pick d59f28mx07wm | 对 |
| 17 | 002:e00217 | 周易集解 | work | pick d59f28mx07wm | 对 |
| 18 | 002:e01306 | 周易象義 | work | pick d59f2gpfic5e | 对 |
| 19 | 003:e00223 | 胡廣 | people | pick hixhd2h9beza | 对 |
| 20 | 002:e00267 | 周易口訣義 | work | pick d59f28mxbgg2 | 对 |
| 21 | 002:e00436 | 李衡 | people | pick hixhd2h9bdr6 | 对 |
| 22 | 002:e00238 | 馬融 | people | pick hixhd2f8waip | 对 |
| 23 | 003:e00061 | 說文 | work | pick d59f24lmclc5 | 对 |
| 24 | 003:e00195 | 周易本義通釋 | work | pick d59f2gohsphd | 对 |
| 25 | 002:e00439 | 周易象義 | work | pick d59f2gpfic5e | 对 |
| 26 | 002:e01282 | 讀易須知 | work | pick d59f6ery8cud | 对 |
| 27 | 002:e01248 | 周易會通 | work | pick d59f2gpl4lxd | 对 |
| 28 | 003:e00340 | 周易義疏 | work | pending | pending 合理（候选缺或撰人未明） |
| 29 | 002:e00144 | 陸氏 | people | pending | pending 合理（候选缺或撰人未明） |
| 30 | 002:e01142 | 周易集義 | work | pending | pending 合理（候选缺或撰人未明） |

## 子夏易傳 6 条复核（Maren 要求）

Maren 裁：同册同书名、上下文没有另一撰人时统一 pick 与 002:e00014 相同的 Work。逐条看上下文：

| entity_id | 上下文 | 建议 |
|--|--|--|
| 002:e00017 | 唐會要載開元七年詔子夏易傳近無習者，劉知幾議 | 指唐代所传本，与总目本是否同本有争议；**保持 pending** |
| 002:e00022 | 劉向七畧有子夏易傳，今所存多失真本 | 指汉志古本，与今本相对；**保持 pending** |
| 002:e00037／e00038 | 假託子夏易傳與眞子夏易傳兩列其目 | 真假并举；**保持 pending**（规则 5） |
| 002:e00063 | 仍託始於子夏易傳（凡例，四庫以此书居首） | 指本书条目；**改 pick** d59f2q7cquww |
| 003:e00235 | 其書所采自子夏易傳以逮張特立 | 泛指所采之书，同书名，无另一撰人；**改 pick** d59f2q7cquww |

## 请 Tilda 改的

1. 003:e00108 周易尚占：pick → pending，evidence 写「規則5：轉述經義考寶巴佚書，非總目本」。003:e00109 保持 pick（上下文指序稱李淸庵撰的秘笈本）。
2. 002:e00063、003:e00235 子夏易傳：改 pick d59f2q7cquww，evidence 写「規則2：同册同書名，上下文无另一撰人」。其余 4 条不动。
3. 改完先 `--apply --dry-run` 无 bad，再 apply。
