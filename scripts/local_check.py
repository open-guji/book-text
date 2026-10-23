#!/usr/bin/env python3
"""本地提交前检查：只查这次改动涉及的条目，几秒到十几秒（2026-10-20 起 PR 不再跑云端 CI，改用本脚本）。

用法（仓根下）：
    python3 scripts/local_check.py            # 对比 origin/main，查分支上全部改动＋工作区未提交改动
    python3 scripts/local_check.py --base HEAD~1
    python3 scripts/local_check.py --all      # 全仓（等同原来的云端 CI，约 1 分钟）

做的事（对应原 CI 的 V1／V2／V3 与索引一致）：
  V2  validate_text_format --strict --baseline，对每个改动条目 `--path <条目>`
  V1  validate-collated（全仓，2 秒；只允许存量 d59f1iqd854w/default/108.md）
  V3  check_license（全仓，1 秒）
  索引  重建 index/texts 后工作区不应多出未提交的改动（有就先 git add／提交）
  出处  格变动出处（check_cell_provenance.py，只告警）：char 里有格变了，CHANGES 新增行要有意见 id／事件 id／r 号／GUJI 卡号
没做：manifest／index 的 schema 校验（需要 guji-format 副本）、pin-drift、单元测试；这几项仍可手动跑，或随夜间全量 CI 兜底。
退出码 0 = 全过，1 = 有不通过项。
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
KNOWN_V1 = {("Work:d59f1iqd854w/default", "磁盘上有未登记的章文件")}


def sh(*cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def changed_entries(base):
    mb = sh("git", "merge-base", "HEAD", base)
    ref = mb.stdout.strip() if mb.returncode == 0 else base
    files = set(sh("git", "diff", "--name-only", ref).stdout.split())
    files |= set(sh("git", "ls-files", "-m", "-o", "--exclude-standard").stdout.split())
    entries = set()
    for f in files:
        p = f.split("/")
        if len(p) >= 5 and p[0] in ("Work", "Book"):
            entries.add("/".join(p[:5]))
    return sorted(entries)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main", help="对比基准，缺省 origin/main")
    ap.add_argument("--all", action="store_true", help="V2 查全仓而不只查改动条目")
    args = ap.parse_args()

    results = []

    def report(name, ok, detail=""):
        results.append(ok)
        print(f"{'通过' if ok else '失败'}  {name}" + (f"  {detail}" if detail else ""))

    if args.all:
        targets = [None]
    else:
        targets = changed_entries(args.base)
        print(f"改动条目 {len(targets)} 个" + (": " + ", ".join(t.split('/')[-1] for t in targets[:8]) if targets else ""))

    bl = os.path.join(ROOT, "scripts", "format_baseline.json")
    for t in targets:
        cmd = [PY, "scripts/validate_text_format.py", ".", "--strict", "--baseline", bl]
        if t:
            cmd += ["--path", t]
        r = sh(*cmd)
        tail = [l for l in r.stderr.splitlines() if l.strip()][-1:] or [""]
        report(f"V2 格式校验 {t or '全仓'}", r.returncode == 0, "" if r.returncode == 0 else tail[0])
        if r.returncode != 0:
            print(r.stdout[-1500:])

    r = sh(PY, "scripts/validate-collated.py", "--root", ".", "--json")
    try:
        d = json.loads(r.stdout)
        extra = [p for p in d["problems"] if (p["wid"], p["kind"]) not in KNOWN_V1]
        report("V1 整理本校验", not extra, f"新问题 {len(extra)} 个" if extra else "")
        for p in extra[:10]:
            print("   ", p)
    except Exception as e:  # noqa: BLE001
        report("V1 整理本校验", False, f"输出读不出来：{e}")

    r = sh(PY, "scripts/check_license.py", ".")
    report("V3 授权串", r.returncode == 0, "" if r.returncode == 0 else r.stdout[-500:])

    before = set(sh("git", "status", "--porcelain", "--", "index/texts").stdout.splitlines())
    r = sh(PY, "scripts/book-text/build_texts_index.py", "--root", ".")
    after = set(sh("git", "status", "--porcelain", "--", "index/texts").stdout.splitlines())
    new = after - before
    report("索引 index/texts 与数据一致", r.returncode == 0 and not new,
           "重建后多出未提交的改动，请 git add／提交 index/texts" if new else "")

    # 格变动出处（GUJI-733）：缺省只告警，不影响退出码；跑顺后改 --strict 转红
    r = sh(PY, "scripts/check_cell_provenance.py", "--base", args.base)
    print(r.stdout.strip() or "格变动出处：（无输出）")

    ok = all(results)
    print("\n全部通过" if ok else "\n有不通过项")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
