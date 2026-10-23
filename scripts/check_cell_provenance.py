#!/usr/bin/env python3
"""格变动必须有出处（GUJI-733；设计 docs/design/2026-10-修订流程自动化设计.md §三）。

对比基准版本，`<章>.char.json` 里有格变了（改字、加格、删格），同一批改动里 CHANGES.md 新增的、写着这一册这一章的行，
必须带至少一个出处标记：意见 id（`op_…`）、人裁事件（`evt_…`）、精校 r 号（`…-r<n>`）或 Jira 卡号（`GUJI-<n>`）。
没有就报告：这样每次改字都能从 CHANGES 倒查到当时的理由。

缺省只告警（退出码 0），`--strict` 才让缺出处的退出码为 1。先告警、跑顺了再转红（设计要求）。

用法（仓根下）：
    python3 scripts/check_cell_provenance.py [--base origin/main] [--strict]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROVENANCE = re.compile(r"\bop_[a-z0-9-]+_[0-9a-f]{10}\b|\bevt_[\w-]+\b|(?:vol\d+|\d{3})-r\d+|GUJI-\d+")
CHAR_RE = re.compile(r"^((?:Book|Work)/[^/]+/[^/]+/[^/]+/[^/]+)/([^/]+)/(\d{3})\.char\.json$")


def cells(char: dict | None) -> dict[str, dict]:
    out = {}
    for p in (char or {}).get("pages") or []:
        for col in p.get("columns") or []:
            for c in col.get("cells") or []:
                out[c["a"]] = {k: v for k, v in c.items() if k != "a"}
    return out


def changed_cells(old: dict | None, new: dict | None) -> list[str]:
    """两版 char 之间变了的格号（改、增、删），顺序不重要。"""
    a, b = cells(old), cells(new)
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def has_provenance(lines: list[str], entry_id: str, vol: str) -> bool:
    """新增的 CHANGES 行里有一行写着 `<书 id>/<章>` 且带出处标记。"""
    key = f"{entry_id}/{vol}"
    return any(key in ln and PROVENANCE.search(ln) for ln in lines)


def _git(*a: str) -> str:
    r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def check(base: str) -> list[dict]:
    mb = _git("merge-base", "HEAD", base).strip() or base
    files = set(_git("diff", "--name-only", mb).split()) | set(_git("ls-files", "-m", "-o", "--exclude-standard").split())
    problems = []
    for f in sorted(files):
        m = CHAR_RE.match(f)
        if not m or not os.path.isfile(os.path.join(ROOT, f)):
            continue
        entry, vdir, vol = m.groups()
        old_text = _git("show", f"{mb}:{f}")
        old = json.loads(old_text) if old_text else None
        new = json.load(open(os.path.join(ROOT, f), encoding="utf-8"))
        diff = changed_cells(old, new)
        if not diff:
            continue
        ch = f"{entry}/{vdir}/CHANGES.md"
        old_ch = set(_git("show", f"{mb}:{ch}").splitlines())
        cur_ch = open(os.path.join(ROOT, ch), encoding="utf-8").read().splitlines() if os.path.isfile(os.path.join(ROOT, ch)) else []
        added = [ln for ln in cur_ch if ln not in old_ch]
        entry_id = entry.rsplit("/", 1)[-1]
        if not has_provenance(added, entry_id, vol):
            problems.append({"file": f, "cells": diff[:8], "n": len(diff)})
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--strict", action="store_true", help="缺出处就退出码 1（缺省只告警）")
    a = ap.parse_args()
    probs = check(a.base)
    for p in probs:
        print(f"告警  {p['file']}：{p['n']} 格变了（{', '.join(p['cells'])}{'…' if p['n'] > 8 else ''}），"
              "CHANGES 新增行里没有出处（意见 id／事件 id／r 号／GUJI 卡号）")
    print("格变动出处：" + ("全部有出处" if not probs else f"{len(probs)} 章缺出处"))
    return 1 if probs and a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
