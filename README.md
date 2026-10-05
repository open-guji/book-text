# book-text

古籍**文本**：整理本、輯佚、全文、抓取素材。

與 [`book-index`](https://github.com/open-guji/book-index)（**元資料**：Work／Book／
Collection／Entity 條目）分立而**共用同一套 snowflake ID**，靠 ID 互指。
一部書之書目著錄在 book-index，其文字在此。

## 目錄

```
<Work|Book>/<c1>/<c2>/<c3>/<id>/
├── manifest.json               本條目全部版本清單（key、來源、授權、章數；versions[0] 為 default）
├── default/                    主版本：index.json（章目錄）＋ 001.md、002.md…（整理本另有同名 001.json）
├── <key>/                      其他版本，key 按來源：collated／wikisource／kanripo／shidian（同源第二份 -2）
├── fragments/<書名>.json        輯佚
└── sources/<來源>/              抓取素材（ctext、source_text…）

index/                          本倉之索引分片
├── texts/{0-f}.json            由各 manifest 彙總（scripts/book-text/build_texts_index.py）
└── fragments/{0-f}.json
```

> 2026-09-30 起改為此結構（原 `collated_edition/`、`full_text/<key>/` 與 `index/collated`、`index/full_text` 已遷移停用），規格見 open-guji-core/overview#307。

`<c1>/<c2>/<c3>` 取 id **尾**三字元，與 book-index 同一套 `shard_dirs()`
（`book_index_manager.storage`）。**凡由 id 推路徑者一律經該函式，勿自拼。**

## 版本

只有 `original`（本項目自書影做出之文本，如四庫總目 `Book/.../96mid1ogzk/original/`）跟蹤版本。維基文庫、Kanripo、識典之轉錄**不跟蹤**，來源修訂號記於 `source`；舊有 `revision: "1.0.0"` 留而不維護。整理本（kind=collated）沿用 `bump-collated.py`。

**三條線**，各自 `MAJOR.MINOR.PATCH`，互不牽連：

| 線 | 檔 | 版本號記於 | 不管 |
|---|---|---|---|
| 文本 | `NNN.lines.md` | `original/index.json` 該章之 `text_version` | 像素坐標、字框（CV 產物） |
| 標點 | `NNN.punct.json` | 頂層 `version`（另 `text_version`＝對著哪一版文本做） | 字 |
| 實體 | `NNN.entity.json` | 頂層 `version`（另 `text_version`） | 字、標點 |

`index.json` 之章條目同時鏡像 `punct_version`、`entity_version`，三線一目了然，網站即由此讀。

**major ＝ 質量等級**，從嚴，須成文驗收記錄（`date`／`signed_by`／`sample`）及用戶點頭，腳本不升：

| 等級 | 文本 | 標點 | 實體 |
|---|---|---|---|
| 1 可用 | 每格有定字，疑難按規範記 | 機器標點，抽 200 處一致率 ≥95% | 抽 50 個精確率 ≥90%，誤掛 ≤5% |
| 2 出版級 | 全冊人工逐字校，抽 ≥2,000 字錯 ≤2 | 全冊人審，抽 500 處 ≥99.5% | 全部人工確認，精確率 ≥99%、召回 ≥95% |
| 3 定本 | 兩遍獨立校並對勘，抽 ≥10,000 字錯 ≤1，簽核 | 對權威點校本逐段覈，抽 1,000 處 ≥99.9%，簽核 | 逐段補漏召回 ≥99%，鏈接全已正式建檔，簽核 |

**minor／patch**：以一次 PR 為單位，一冊改動 ≤50 處且逐處改者為 patch；超過，或按規則成批改者（整批字符轉換、整冊重跑、換模型、新增類型……）為 minor。不確定者取 minor。文本改後伴生層錨點仍對得上：只把伴生層 `text_version` 跟過去，不升其版本。

**不跟蹤**：維基文庫、Kanripo、識典等轉錄；`wip/` 分支上反覆改動時亦不編號（可暫寫 `0.x`）。第一次併入 main 定為 `1.0.0`，夠不上第 1 級者不併。

**CHANGES.md**：每升一次，在 `original/CHANGES.md` 記一行 `| 日期 | 冊 | 線 | 舊→新 | 說明 | PR |`。升版一律用 overview `scripts/book-text/bump_original.py`（`--init` 首次定 1.0.0；`--line text|punct|entity --level patch|minor`），它同時改版本號、寫 CHANGES.md；major 不給腳本升。PR 描述附「冊 · 線 · 舊 → 新 · 理由」表。校驗器 `validate_text_format.py` 之 F-OV-01～03 規則把關。

詳見 [docs/VERSIONING.md](docs/VERSIONING.md)；規範全文在 overview `项目进展/古籍文本/整体设计/2026-10-文本版本号与仓库流程.md`。

## 與 book-index 之繫連

| 方向 | 欄位 |
|---|---|
| 文本 → 元資料 | 整理本 `section.work_id` / `work_ids` / `book_id` / `collection_id` / `target_bid`；輯佚 `work_id`、`collectors[].work_id`、`based_on[].source_bid` |
| 元資料 → 文本 | `Work._has_collated`（**唯一真指本地目錄之派生欄**） |

> **`_has_text` 與 `_has_image` 不指本倉。** 二欄由 `resources[].types` 推得，
> 說的是**外部資源**（ctext、IA 之屬），與此倉之檔無關。抽樣三千條只二十三條
> 真有本地目錄。凡據此二欄去找本倉之檔者，必落空。

## 校驗

跨倉之驗在 `book-index-draft/.claude/skills/hanzhi-curation/scripts/chk-cross.py`：

```
python3 chk-cross.py --text-root ../book-text --meta ../book-index
python3 chk-cross-selftest.py     # 造微型假倉，覈諸驗是否報得出來
```

**每一驗都印其掃了幾檔。** 掃 0 檔之驗與全過之驗輸出一模一樣，
本倉成立之際即已因此栽過四次（見 chk-cross.py 檔首）。數字對得上不算過關，
先看掃檔數。

## 授權

本倉**逐文本授權**：每份文本以其所屬條目 `manifest.json` 中該版本之 `license` 為準（有 `source.upstream` 者並從其上游之約定）。倉根 `LICENSE`（CC0 1.0）只適用於本項目**自行整理**之文本與元資料，不及於轉錄自他處之全文。

| 來源 | 授權 | 備註 |
|---|---|---|
| 本項目自行整理（整理本、自校文本） | CC0 1.0 | — |
| 維基文庫 | CC BY-SA 4.0 | 署名、相同方式分享 |
| Kanripo（四庫、四部叢刊、道藏等 Kanripo 自錄者） | CC BY-SA 4.0 | 署名、相同方式分享 |
| Kanripo 轉自 CBETA 之佛典（KR6…） | CC BY-NC-SA 4.0 | **限非營利**；再傳播須附 CBETA 版權說明及版本資訊，見 <https://www.cbeta.org/copyright> |
| 識典等轉載受限之來源 | — | 不入本倉，只入私有倉 `book-text-private` |

**方向**：以本項目自行整理、校對之文本逐步替代上表轉錄之文本，最終全倉達到 CC0。

## 遷入之由來

本倉之文本 2026-08-26 自 `book-index` 遷來，3,971 檔 130.0 MB。
兩倉之 commit 互指以資追溯：

| 倉 | commit | 事 |
|---|---|---|
| book-text | `386320e..1524af8` | 文本遷入（37 個 commit，按分片分批——代理拒 >100MB 之單包） |
| book-index | `036a055` | 同一批文本自元資料倉移出 |
| book-index | `4ba4799` | 遷前之格式歸一（卷檔入 `juan/NNN.json`、清單更名 `index.json`） |
| overview | `ed3f5b4` | 書影 87 MB 另移往 `overview/书影/`（不入本倉） |

遷前遷後以 `chk-cross.py` **同一時刻**兩根對跑，十二驗逐項同數同掃檔數——
拆分之正確即以此為據，非以「看著沒錯」為據。
