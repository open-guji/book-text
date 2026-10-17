#!/usr/bin/env python3
"""CHANGES.md 三项对应只读校验（GUJI-559 方案 C；设计 GUJI-543 §7：文本版本 ↔ r 号 ↔ cv 版本）。

不需要 ws 仓、不联网、不写任何东西，可放进 book-text 的 CI。规则：
凡「线」列为「文本」、版本列带「→<版本>」（版本变化行）且行内出现「快照 <哈希>」的行，必须同时写了
 ① r 号：`<册>-r<n>` 或 `<章号>-r<n>`（如 vol01-r1／001-r1）；
 ② cv commit 前 8 位（`cv … <8位十六进制>`，或「cv 0.2.0（commit 4a9388ac…」）。
「版本不变」行（如「0.1.1（不变）」）和不带快照的行不查。

用法：python3 check_changes.py <CHANGES.md> [--since-date YYYY-MM-DD]   退出码 0＝全过，1＝有行不合。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEX8 = re.compile(r"(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])")


def check(text: str, since: str = "") -> list[str]:
    errs = []
    for no, ln in enumerate(text.splitlines(), 1):
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 5 or not re.fullmatch(r"\d{4}-\d\d-\d\d", c[0]):
            continue
        date, vol, line, chg, note = c[0], c[1], c[2], c[3], c[4]
        if since and date < since:
            continue
        if line != "文本" or "→" not in chg or "不变" in chg or not re.search(r"快照\s*[`\w/.-]*[0-9a-f]{8}", note):
            continue
        chap = vol.rsplit("/", 1)[-1]
        if not re.search(rf"(?:vol\d+|{chap})-r\d+", note):
            errs.append(f"第 {no} 行（{vol} {chg}）没写 r 号（`<册>-r<n>` 或 `{chap}-r<n>`）")
        if not re.search(r"cv[^；;|]*?(?<![0-9a-f])[0-9a-f]{8}", note):
            errs.append(f"第 {no} 行（{vol} {chg}）没写 cv commit 前 8 位")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("changes", type=Path)
    ap.add_argument("--since-date", default="", help="只查这天及以后的行（旧行不追溯）")
    a = ap.parse_args()
    errs = check(a.changes.read_text(encoding="utf-8"), a.since_date)
    for e in errs:
        print("✗", e)
    print("CHANGES 三项对应：" + ("全部通过" if not errs else f"{len(errs)} 处不合"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
