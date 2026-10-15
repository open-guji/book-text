#!/usr/bin/env python3
"""
修复「多书合并著录被误拆后说明文字重复」。

背景
----
志书原文常用顿号把多部书连写在一条著录里，说明文字只写一遍、管整条：

    《古禮經》十七卷、《古禮注》十七卷   漢大司農北海鄭康成撰。相傳以為……
    《周易注》六卷、《略例》一卷、《繫辭注》三卷   魏……

整理成 collated_edition 时按书名拆成了多个独立 section（这是对的，它们
确实是各自独立的书，各有 work_id），但**每个 section 都复制了一份完整的
说明文字**，于是页面上同一段话连续出现两到四次。

修法
----
说明只保留在首条，后续条目 content 置空，并加 `content_from` 指向首条
标题，表明「本条说明承接上一条」。前端对空 content 已能正确处理：
不渲染展开箭头和正文，只显示书名——正是想要的效果。

判据
----
**content 完全相同 且 index 连续相邻**。

不能只看 content 相同：原书里多部书共用一句极短说明（如「唐陸德明撰。」）
是正常的。实测中 `《古禮釋文》一卷`(idx=2) 与 `《周禮釋文》二卷`(idx=15)
都是「唐陸德明撰。」，但相隔 13 条，属正常巧合，必须排除。

另设 MIN_LEN 门槛：太短的说明即便相邻也可能是巧合，不动。

用法
----
    python scripts/dedupe-merged-entries.py --work d59f2htm01du --dry-run
    python scripts/dedupe-merged-entries.py --work d59f2htm01du --apply
    python scripts/dedupe-merged-entries.py --all --dry-run     # 扫全库
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# 说明短于此长度时，即便相邻也不认定为拆分错误——
# 「某某撰。」这类五六个字的说明，两部书恰好相同是很常见的。
MIN_LEN = 15

REPO = Path(__file__).resolve().parent.parent


def find_groups(sections: list[dict]) -> list[list[int]]:
    """找出「content 相同且相邻」的下标组。"""
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(sections):
        c = (s.get("content") or "").strip()
        if c and len(c) >= MIN_LEN:
            buckets[c].append(i)

    groups = []
    for idxs in buckets.values():
        if len(idxs) < 2:
            continue
        # 切成连续段：[4,5,6,20,21] -> [[4,5,6],[20,21]]
        run = [idxs[0]]
        for prev, cur in zip(idxs, idxs[1:]):
            if cur - prev == 1:
                run.append(cur)
            else:
                if len(run) > 1:
                    groups.append(run)
                run = [cur]
        if len(run) > 1:
            groups.append(run)
    return sorted(groups)


def process_file(path: Path, apply: bool) -> tuple[int, int, list[str]]:
    """返回 (组数, 改动条目数, 明细)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = data.get("sections") or []
    groups = find_groups(sections)
    if not groups:
        return 0, 0, []

    detail = []
    changed = 0
    for run in groups:
        head = sections[run[0]]
        head_title = head.get("title", "?")
        detail.append(f"  {head_title}")
        for i in run[1:]:
            s = sections[i]
            kind = "附屬部帙" if s.get("section_kind") else "獨立著錄"
            detail.append(f"    ↳ 清空说明: {s.get('title','?')}  [{kind}]")
            if apply:
                # 就地把 content 换成空值 + content_from，保持 content_from
                # 紧跟在 content 后面。若直接 s["content_from"]=... 会追加到
                # 字典末尾，导致原末位字段被迫加逗号，diff 多出几千行噪声。
                rebuilt = {}
                for k, v in s.items():
                    if k == "content":
                        rebuilt["content"] = ""
                        # 记录说明承接自哪条，信息不丢、便于回溯与还原
                        rebuilt["content_from"] = head_title
                    else:
                        rebuilt[k] = v
                s.clear()
                s.update(rebuilt)
            changed += 1

    if apply and changed:
        # newline="\n" 是必须的：仓库里存的是 LF，Windows 下 Python 默认会写成
        # CRLF，导致整个文件被当成全行改写，diff 从 2 千行涨到 1 万多行，
        # 真正的改动淹没在噪声里、没法评审。
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return len(groups), changed, detail


def iter_juan_files(work_id: str | None):
    root = REPO / "Work"
    pattern = "*/*/*/*/collated_edition/juan/*.json"
    for p in sorted(root.glob(pattern)):
        # Work/<a>/<b>/<c>/<work_id>/collated_edition/juan/NNN.json
        wid = p.parents[2].name
        if work_id and wid != work_id:
            continue
        yield wid, p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", help="只处理某个 work_id")
    ap.add_argument("--all", action="store_true", help="处理全库")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.work and not args.all:
        ap.error("需指定 --work <id> 或 --all")

    per_work: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # files, groups, changed
    all_detail: list[str] = []

    for wid, path in iter_juan_files(args.work):
        groups, changed, detail = process_file(path, args.apply)
        if groups:
            st = per_work[wid]
            st[0] += 1
            st[1] += groups
            st[2] += changed
            if detail:
                all_detail.append(f"[{wid} {path.name}]")
                all_detail.extend(detail)

    if not per_work:
        print("没有发现需要修复的条目。")
        return 0

    if args.dry_run and all_detail:
        print("\n".join(all_detail[:80]))
        if len(all_detail) > 80:
            print(f"... 另有 {len(all_detail)-80} 行明细省略")
        print()

    print(f"{'':<16}{'卷数':>6}{'组数':>6}{'清空条目':>10}")
    tf = tg = tc = 0
    for wid, (f, g_, c) in sorted(per_work.items()):
        print(f"{wid:<16}{f:>6}{g_:>6}{c:>10}")
        tf += f; tg += g_; tc += c
    print(f"{'合计':<16}{tf:>6}{tg:>6}{tc:>10}")
    print()
    print("（dry-run，未写入）" if args.dry_run else "已写入文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
