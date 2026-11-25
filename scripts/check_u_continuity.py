#!/usr/bin/env python3
"""字格永久编号 u 前后版连续性（guji-format 02 §4.10、§六，2026-11-24）：本次改动的每个 NNN.char.json，
取基准版（--base，缺省 origin/dev）与现版比：
  - 旧版有的 u 要么还在，要么进了 u_retired（不许悄悄丢号）；
  - u_max 只增不减；作废的号不许复活；u_retired 只增不改。
单文件的 u 形状（不重、≤u_max、新格无 u 等）由 validate_text_format.py 的 F-OV-18 核，本脚本只管跨版本。

用法（仓根）：python3 scripts/check_u_continuity.py [--base origin/dev]
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cell_uid as CU  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def sh(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def git_json(ref, path):
    r = sh("git", "show", f"{ref}:{path}")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def check_file(ref, path):
    old = git_json(ref, path)
    if old is None:
        return []
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            new = json.load(f)
    except (OSError, ValueError):
        return []  # 删了或坏了：别的检查会报
    return [f"{path}: {msg}" for msg, _sub in CU.continuity_problems(old, new)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/dev")
    args = ap.parse_args()
    mb = sh("git", "merge-base", "HEAD", args.base)
    ref = mb.stdout.strip() if mb.returncode == 0 else args.base
    files = set(sh("git", "diff", "--name-only", ref).stdout.split())
    files |= set(sh("git", "ls-files", "-m", "--exclude-standard").stdout.split())
    chars = sorted(f for f in files if f.endswith(".char.json") and f.startswith(("Book/", "Work/")))
    bad = []
    for f in chars:
        bad += check_file(ref, f)
    print(f"u 连续性：查 {len(chars)} 个改动的 char 文件，问题 {len(bad)} 处")
    for m in bad[:50]:
        print("  失败", m)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
