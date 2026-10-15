#!/usr/bin/env python3
"""补齐 book-text 整理本 `collated_edition/juan/*.json` 两类纯结构缺键（T21）：

1. `type=book` 的 section 缺 `work_id` 键 → 补 `"work_id": null`。
2. section 缺 `content` 键 → 补 `"content": ""`（登记例外：南齊書經籍志
   `d59f2ofu9i4i` 用 `paragraphs` 体例代替 `content`，不补，见 EXEMPT_CONTENT_WORK_IDS）。

只插入缺的键，不动任何已有值、不动下划线字段。新键按 dict 插入顺序自然落在
section 末尾。写回时按每个文件自身探测出的 JSON 格式参数（缩进宽度、是否有
结尾换行）原样输出，确保未改动的字节位不变——本仓 1,812 个 juan 文件实测
只有 indent=1／indent=2 两档、结尾有无换行两档，无第三种格式。

用法：
    python3 fill_missing_keys.py --root <book-text 仓根目录>            # dry-run，只报数
    python3 fill_missing_keys.py --root <book-text 仓根目录> --apply    # 真跑，落盘
"""
import argparse
import glob
import json
import os
from collections import defaultdict

EXEMPT_CONTENT_WORK_IDS = {"d59f2ofu9i4i"}  # 南齊書經籍志：paragraphs 体例，登记例外
DEFAULT_EXCLUDE_WORK_IDS = {"d59f2mel8d1c"}  # 千頃堂書目：文本总管 09-27 定，等整部目录重新文本化后再一起改，这次不补


def work_id_of(path: str) -> str:
    parts = path.split(os.sep)
    idx = parts.index("collated_edition")
    return parts[idx - 1]


def detect_format(orig: str, data) -> tuple[int, str] | None:
    """探测原文件是用哪套 (indent, 结尾换行) 序列化的；探测不出返回 None。"""
    for indent in (1, 2, 4):
        for nl in ("\n", ""):
            if json.dumps(data, indent=indent, ensure_ascii=False) + nl == orig:
                return indent, nl
    return None


def process_file(path: str, apply: bool, exclude_work_ids: set[str]):
    """返回 (work_id 补几处, content 补几处, 问题说明或 None)。"""
    orig = open(path, encoding="utf-8").read()
    data = json.loads(orig)
    wid = work_id_of(path)
    if wid in exclude_work_ids:
        return 0, 0, None
    exempt_content = wid in EXEMPT_CONTENT_WORK_IDS

    added_work_id = 0
    added_content = 0
    for sec in data.get("sections", []):
        if sec.get("type") == "book" and "work_id" not in sec:
            sec["work_id"] = None
            added_work_id += 1
        if not exempt_content and "content" not in sec:
            sec["content"] = ""
            added_content += 1

    if added_work_id == 0 and added_content == 0:
        return 0, 0, None

    if apply:
        fmt = detect_format(orig, json.loads(orig))  # 用改前的原始数据探测格式
        if fmt is None:
            return added_work_id, added_content, "探测不出原文件的 JSON 格式参数，已跳过未写"
        indent, nl = fmt
        new_text = json.dumps(data, indent=indent, ensure_ascii=False) + nl
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)

    return added_work_id, added_content, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="book-text 仓根目录")
    ap.add_argument("--apply", action="store_true", help="真跑落盘；不传则只 dry-run 报数")
    ap.add_argument(
        "--include-excluded",
        action="store_true",
        help=f"不排除默认名单（{sorted(DEFAULT_EXCLUDE_WORK_IDS)}），连它们一起补",
    )
    A = ap.parse_args()
    exclude_work_ids = set() if A.include_excluded else set(DEFAULT_EXCLUDE_WORK_IDS)

    files = sorted(glob.glob(os.path.join(A.root, "Work", "*", "*", "*", "*", "collated_edition", "juan", "*.json")))
    per_work = defaultdict(lambda: [0, 0])
    problems = []
    total_work_id = 0
    total_content = 0

    for p in files:
        wid = work_id_of(p)
        n_wid, n_content, problem = process_file(p, apply=A.apply, exclude_work_ids=exclude_work_ids)
        if n_wid or n_content:
            per_work[wid][0] += n_wid
            per_work[wid][1] += n_content
            total_work_id += n_wid
            total_content += n_content
        if problem:
            problems.append((p, problem))

    mode = "真跑（已落盘）" if A.apply else "dry-run（未改文件）"
    print(f"== fill_missing_keys.py {mode} ==")
    print(f"扫描 juan 文件 {len(files)} 个，涉及待补键 {len(per_work)} 部\n")
    print(f"{'work_id':<16}{'补 work_id':>10}{'补 content':>10}")
    for wid, (n_wid, n_content) in sorted(per_work.items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
        print(f"{wid:<16}{n_wid:>10}{n_content:>10}")
    print(f"\n合计：补 work_id {total_work_id} 处，补 content {total_content} 处，共 {total_work_id + total_content} 处")

    if problems:
        print(f"\n⚠️ {len(problems)} 个文件有问题：")
        for p, msg in problems:
            print(f"  {p}: {msg}")


if __name__ == "__main__":
    main()
