#!/usr/bin/env bash
# 把 book-text 某个分支的真源生成 lines.md、rich.md，推到生成分支（T68 #417，book-text docs/ORIGINAL.md §四）。
#
# 生成分支的每个提交 = 源分支那个提交的整棵树 ＋ 生成物（各 original/ 下 NNN.lines.md、NNN.rich.md，
# index.json 该章加 lines_file、rich_file）。生成分支只由本脚本写，不手改，不往回并。
#
# 用法（在 book-text 克隆里跑，不动当前工作区，借一个临时 worktree）：
#   publish_original_derived.sh <book-text 克隆> [源分支，默认 main] [生成分支，默认 derived] [--no-push]
# 现阶段（10-06）四庫 vol02、vol03 还在 wip/siku，生成分支从 wip/siku 生成：
#   publish_original_derived.sh ~/book-text wip/siku derived
# main 每次合入 original 改动后：
#   publish_original_derived.sh ~/book-text main derived
set -euo pipefail

REPO=$(cd "$1" && pwd)
SRC=${2:-main}
DST=${3:-derived}
PUSH=1
[[ "${4:-}" == "--no-push" ]] && PUSH=0
HERE=$(cd "$(dirname "$0")" && pwd)
OVERVIEW_SHA=$(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || echo "?")

# 用 FETCH_HEAD 取提交号：单分支克隆里没有 origin/<分支> 这种远程跟踪引用
git -C "$REPO" fetch -q --depth 1 origin "$SRC"
SRC_SHA=$(git -C "$REPO" rev-parse FETCH_HEAD)
DST_SHA=""
if git -C "$REPO" fetch -q --depth 1 origin "$DST" 2>/dev/null; then
  DST_SHA=$(git -C "$REPO" rev-parse FETCH_HEAD)
fi

WT=$(mktemp -d)/derived
cleanup() { git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || true; }
trap cleanup EXIT

if [[ -n "$DST_SHA" ]]; then
  # 已有生成分支：在它上面接一个新提交，树换成源分支的树再生成
  git -C "$REPO" worktree add -q --detach "$WT" "$DST_SHA"
  git -C "$WT" read-tree -u --reset "$SRC_SHA"
else
  # 第一次：从源分支那个提交长出来
  git -C "$REPO" worktree add -q --detach "$WT" "$SRC_SHA"
fi

python3 "$HERE/gen_original_derived.py" "$WT"

git -C "$WT" add -A
if [[ "$(git -C "$WT" rev-parse 'HEAD^{tree}')" == "$(git -C "$WT" write-tree)" ]]; then
  echo "生成结果与 $DST 现状相同，不提交"
  exit 0
fi
git -C "$WT" commit -q -m "derived: 由 $SRC@$(git -C "$REPO" rev-parse --short "$SRC_SHA") 生成 lines.md、rich.md

源提交：$SRC_SHA
生成脚本：overview scripts/book-text/gen_original_derived.py（overview $OVERVIEW_SHA）"
echo "生成提交：$(git -C "$WT" rev-parse --short HEAD)（源 $SRC@${SRC_SHA:0:10}）"
if [[ $PUSH == 1 ]]; then
  git -C "$WT" push origin "HEAD:refs/heads/$DST"
fi
