# book-text

古籍**文本**：整理本、輯佚、全文、抓取素材。

與 [`book-index`](https://github.com/open-guji/book-index)（**元資料**：Work／Book／
Collection／Entity 條目）分立而**共用同一套 snowflake ID**，靠 ID 互指。
一部書之書目著錄在 book-index，其文字在此。

## 目錄

```
Work/<c1>/<c2>/<c3>/<work_id>/
├── collated_edition/           整理本
│   ├── index.json              清單：type、juan_files、text_quality、references…
│   ├── juan/NNN.json           卷檔，內含 sections[]
│   └── text/*.md               派生純文本（可重生成）
├── fragments/<書名>.json        輯佚
└── sources/<來源>/              抓取素材（ctext、source_text…）

Book/<c1>/<c2>/<c3>/<book_id>/
└── full_text/{index.json, NNN.md}

index/                          本倉之索引分片
├── collated/{0-f}.json
└── fragments/{0-f}.json
```

`<c1>/<c2>/<c3>` 取 id **尾**三字元，與 book-index 同一套 `shard_dirs()`
（`book_index_manager.storage`）。**凡由 id 推路徑者一律經該函式，勿自拼。**

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
