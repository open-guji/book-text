#!/usr/bin/env python3
"""每日把 dev 合进 main（2026-10-24 用户定：流程化小改直接提交 dev，每天合一次 main）。

定时任务在洛杉矶 03:30 跑（每夜全量 check.yml 是 04:00）。仓根下：
    python3 scripts/daily_merge.py              # 全套：合入 main → 重建索引 → 全仓检查 → 开／更新 PR → 换 PR 号 → 合并
    python3 scripts/daily_merge.py --no-merge   # 只开／更新 PR，不合
    python3 scripts/daily_merge.py --dry-run    # 只报 dev 比 main 多了什么

步骤：
  1. 工作区必须干净；fetch origin main dev，切到 dev（= origin/dev）
  2. main 上有 dev 没有的提交（单独 PR 合进 main 的）→ 先 merge 进 dev；冲突就停，报冲突文件
  3. dev 与 main 内容一样 → 什么都不做
  4. 重建 index/texts，有变化就提交到 dev
  5. `local_check.py --all` 必须全过，否则推 dev、开 PR，但不合，退出码 1
  6. 推 dev；找已开的 dev→main PR，没有就开；CHANGES.md 里本次新增的 `#TBD` 换成 PR 号，提交、推
  7. 用 merge commit 合并（不 squash：squash 会让 dev 与 main 分叉，明天的 PR 又带上今天合过的改动），再把 dev 快进到 main
退出码：0＝合了或无事可做；1＝检查没过或冲突（PR 留着）；2＝用法／环境问题。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = "open-guji/book-text"
PY = sys.executable


def sh(*cmd, check=False):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"✗ {' '.join(cmd)}\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
    return r


def gh(*args):
    r = subprocess.run(["gh", "api", *args], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-800:] or r.stdout.strip()[-800:])
    return json.loads(r.stdout) if r.stdout.strip() else None


def tbd_files(base: str) -> list[str]:
    """dev 比 base 多出来的 `#TBD`（只看本次新增的行）所在的 CHANGES.md。"""
    out = sh("git", "diff", "-U0", f"{base}...HEAD", "--", "*CHANGES.md").stdout
    files, cur = set(), None
    for ln in out.splitlines():
        if ln.startswith("+++ b/"):
            cur = ln[6:]
        elif ln.startswith("+") and not ln.startswith("+++") and "#TBD" in ln and cur:
            files.add(cur)
    return sorted(files)


def fill_tbd(files: list[str], base: str, n: int) -> int:
    """只换本次新增行里的 #TBD（旧行若遗留 #TBD 不动，免得错填别天的 PR 号）。"""
    added = set()
    for f in files:
        for ln in sh("git", "diff", "-U0", f"{base}...HEAD", "--", f).stdout.splitlines():
            if ln.startswith("+") and not ln.startswith("+++") and "#TBD" in ln:
                added.add(ln[1:])
    k = 0
    for f in files:
        p = os.path.join(ROOT, f)
        lines = open(p, encoding="utf-8").read().split("\n")
        for i, ln in enumerate(lines):
            if ln in added:
                lines[i] = ln.replace("#TBD", f"#{n}")
                k += 1
        open(p, "w", encoding="utf-8").write("\n".join(lines))
    return k


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-merge", action="store_true", help="只开／更新 PR，不合")
    ap.add_argument("--dry-run", action="store_true", help="只报 dev 比 main 多了什么，不改任何东西")
    a = ap.parse_args()

    if sh("git", "status", "--porcelain", "--untracked-files=no").stdout.strip():
        print("✗ 工作区有未提交的改动，先处理")
        return 2
    # 显式 refspec：单分支克隆（remote.origin.fetch 只有 main）里 `git fetch origin dev` 不更新 origin/dev
    sh("git", "fetch", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main",
       "+refs/heads/dev:refs/remotes/origin/dev", check=True)
    # 浅克隆里两边可能找不到共同祖先（merge 报 unrelated histories），逐步加深到找得到为止
    for depth in (100, 500, 2000):
        if sh("git", "merge-base", "origin/main", "origin/dev").returncode == 0:
            break
        sh("git", "fetch", "-q", f"--deepen={depth}", "origin", "+refs/heads/main:refs/remotes/origin/main",
           "+refs/heads/dev:refs/remotes/origin/dev")
    else:
        if sh("git", "merge-base", "origin/main", "origin/dev").returncode:
            print("✗ 浅克隆加深后 main 与 dev 仍找不到共同祖先，请 `git fetch --unshallow` 后重跑")
            return 2
    commits = sh("git", "log", "--oneline", "origin/main..origin/dev").stdout.strip().splitlines()
    files = sh("git", "diff", "--name-only", "origin/main", "origin/dev").stdout.split()
    print(f"dev 比 main 多 {len(commits)} 个提交、{len(files)} 个文件")
    for c in commits[:30]:
        print("  ", c)
    if a.dry_run:
        return 0
    if not files:
        print("dev 与 main 内容一样，今天不用合")
        return 0

    sh("git", "checkout", "-q", "-B", "dev", "origin/dev", check=True)
    if sh("git", "merge-base", "--is-ancestor", "origin/main", "HEAD").returncode:
        r = sh("git", "merge", "--no-ff", "-q", "origin/main", "-m", "每日合并：先合入 main 的新提交")
        if r.returncode:
            conflicted = sh("git", "diff", "--name-only", "--diff-filter=U").stdout.split()
            sh("git", "merge", "--abort")
            print(f"✗ 合入 main 冲突（{len(conflicted)} 个文件）：" + "、".join(conflicted[:20]))
            return 1
        print("已合入 main 的新提交")

    sh(PY, "scripts/book-text/build_texts_index.py", "--root", ".", check=True)
    if sh("git", "status", "--porcelain", "--", "index/texts").stdout.strip():
        sh("git", "add", "-A", "index/texts", check=True)
        sh("git", "commit", "-q", "-m", "每日合并：重建 index/texts", check=True)
        print("已重建 index/texts 并提交")

    chk = sh(PY, "scripts/local_check.py", "--all")
    ok = chk.returncode == 0
    print(chk.stdout.strip())
    sh("git", "push", "-q", "origin", "dev", check=True)

    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-7))).strftime("%Y-%m-%d")
    log = sh("git", "log", "--oneline", "--no-merges", "origin/main..HEAD").stdout.strip()
    body = (f"每日 dev→main 合并（{today}，`scripts/daily_merge.py`）。\n\n提交：\n```\n{log[:6000]}\n```\n\n"
            f"`python3 scripts/local_check.py --all`：\n```\n{chk.stdout.strip()[-3000:]}\n```\n")
    prs = gh(f"repos/{REPO}/pulls?state=open&base=main&head=open-guji:dev")
    if prs:
        n = prs[0]["number"]
        gh("-X", "PATCH", f"repos/{REPO}/pulls/{n}", "-f", f"title=每日合并 dev→main（{today}）", "-f", f"body={body}")
        print(f"已更新 PR #{n}")
    else:
        n = gh(f"repos/{REPO}/pulls", "-X", "POST", "-f", "base=main", "-f", "head=dev",
               "-f", f"title=每日合并 dev→main（{today}）", "-f", f"body={body}")["number"]
        print(f"已开 PR #{n}")

    tf = tbd_files("origin/main")
    if tf:
        k = fill_tbd(tf, "origin/main", n)
        sh("git", "add", *tf, check=True)
        sh("git", "commit", "-q", "-m", f"CHANGES：PR 号 #{n}（每日合并）", check=True)
        sh("git", "push", "-q", "origin", "dev", check=True)
        print(f"CHANGES：{k} 行 #TBD → #{n}")

    if not ok:
        print(f"✗ 全仓检查没过：PR #{n} 留着不合，修好后重跑本脚本")
        return 1
    if a.no_merge:
        print(f"PR #{n} 已就绪（--no-merge，不合）")
        return 0
    head = sh("git", "rev-parse", "HEAD").stdout.strip()
    # 刚推完 GitHub 还在算能不能合（mergeable 为 null），这时合并会报 405；等它算完
    for _ in range(12):
        if gh(f"repos/{REPO}/pulls/{n}").get("mergeable") is not None:
            break
        time.sleep(5)
    try:
        gh("-X", "PUT", f"repos/{REPO}/pulls/{n}/merge", "-f", "merge_method=merge", "-f", f"sha={head}",
           "-f", f"commit_title=每日合并 dev→main（{today}） (#{n})")
    except RuntimeError as e:
        print(f"✗ 合并失败：{e}")
        return 1
    print(f"✓ PR #{n} 已合并进 main")
    # dev 快进到 main 的合并提交，明天从同一点起（不快进也行，明天第 2 步会把 main 合回来，只是多一个空合并）
    sh("git", "fetch", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main")
    if sh("git", "push", "-q", "origin", "origin/main:refs/heads/dev").returncode:
        print("ⓘ dev 没能快进到 main（期间有人推了 dev），明天照常合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
