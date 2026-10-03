#!/usr/bin/env python3
"""
删除整理本 index.json 里没人维护、还会误导的统计字段。

为什么删而不是校准
------------------
`total_juan` / `total_categories` / `total_sections` 是整理时写入的独立声明，
之后卷文件增删都没同步过，于是各写各的：

    d59f2mp38qv4  total_juan=1   实际 43 个卷文件
    d59f2mp2xibm  total_juan=4   实际 42
    d59f2htm01du  total_juan=22  实际 56   （total_sections 3062 vs 3415）
    d59f2mp1zsoz  total_juan=4   实际 1

而且口径本身就混着两种：d59f2htm01du 的 22 是该书传统卷数（二十二卷），
d59f2mp38qv4 的 1 显然不是。校准要先定语义，定错了会让数字看着对、含义错。

`juan_files` 数组才是可信来源——上面 4 部的 juan_files 长度都与实际文件数
一致，前端其余地方用的也是它。留着一个跟它冲突的冗余计数没有意义。

前端配套改动
------------
`CollatedEdition.tsx` 的「共 N 卷」原本读 total_juan（所以 d59f2mp38qv4
页面显示「共 1 卷」却列出 43 个卷按钮），已改为 allFiles.length，与考证类
分支的口径统一。本脚本必须与那个改动一起上线。

用法
----
    python scripts/drop-stale-totals.py --dry-run
    python scripts/drop-stale-totals.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 一并清掉的冗余统计字段。三者都无生产代码读取
# （total_categories/total_sections 此前仅被 e2e 断言引用）。
STALE_KEYS = ("total_juan", "total_categories", "total_sections")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = sorted(REPO.glob("Work/*/*/*/*/collated_edition/index.json"))
    touched = 0
    removed_total = 0
    mismatch_note: list[str] = []

    for p in files:
        data = json.loads(p.read_text(encoding="utf-8"))
        present = [k for k in STALE_KEYS if k in data]
        if not present:
            continue

        # 顺手记录一下删掉的值与实际差多少，便于评审时看清删的是什么
        juan_dir = p.parent / "juan"
        actual = len(sorted(juan_dir.glob("*.json"))) if juan_dir.is_dir() else 0
        declared = data.get("total_juan")
        if declared is not None and declared != actual:
            mismatch_note.append(
                f"  {p.parents[1].name}: total_juan={declared} 实际={actual}"
            )

        for k in present:
            data.pop(k)
        removed_total += len(present)
        touched += 1

        if args.apply:
            # newline="\n"：仓库存的是 LF，Windows 下默认写 CRLF 会让整个文件
            # 变成全行改写，真正的改动淹没在 diff 噪声里。
            p.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

    print(f"index.json 总数      : {len(files)}")
    print(f"含冗余字段、已处理   : {touched}")
    print(f"删除字段数（合计）   : {removed_total}")
    if mismatch_note:
        print(f"其中 total_juan 与实际不符的 {len(mismatch_note)} 部：")
        print("\n".join(mismatch_note))
    print()
    print("（dry-run，未写入）" if args.dry_run else "已写入文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
