#!/usr/bin/env python3
"""按文本总管 09-27 00:2x 的批复：842 段超过 muse 一窗（约 470 次），分两步跑。
第一步只跑 230 条（30 段坏样本全带 + 从 812 段真实数据里按 13 部占比分层抽 200 段）。

分层用最大余数法凑够整数 200（先按占比取整，再把小数部分最大的几部各加 1，
凑齐总数——不能简单四舍五入，会加出来 199 或 201）。

用法：
    python3 stratified_sample.py --chunks chunks.jsonl --n 200 --seed 20260927 \
        --out-sample stage1_real_200.jsonl --out-remaining stage2_remaining.jsonl
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def largest_remainder_alloc(counts: dict, n: int) -> dict:
    total = sum(counts.values())
    raw = {k: v / total * n for k, v in counts.items()}
    alloc = {k: int(x) for k, x in raw.items()}
    remainder = n - sum(alloc.values())
    order = sorted(raw.keys(), key=lambda k: raw[k] - alloc[k], reverse=True)
    for k in order[:remainder]:
        alloc[k] += 1
    return alloc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out-sample", required=True, type=Path)
    ap.add_argument("--out-remaining", required=True, type=Path)
    args = ap.parse_args()

    chunks = [json.loads(l) for l in args.chunks.read_text(encoding="utf-8").splitlines()]
    by_work = defaultdict(list)
    for c in chunks:
        by_work[c["work_id"]].append(c)

    counts = {wid: len(v) for wid, v in by_work.items()}
    alloc = largest_remainder_alloc(counts, args.n)

    rng = random.Random(args.seed)
    sampled = []
    sampled_ids = set()
    for wid, k in alloc.items():
        pick = rng.sample(by_work[wid], k)
        sampled.extend(pick)
        sampled_ids.update(c["chunk_id"] for c in pick)

    remaining = [c for c in chunks if c["chunk_id"] not in sampled_ids]

    with args.out_sample.open("w", encoding="utf-8") as f:
        for c in sampled:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with args.out_remaining.open("w", encoding="utf-8") as f:
        for c in remaining:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"分层抽样：{len(sampled)} 条（目标 {args.n}），按 13 部占比分配：")
    title_by_wid = {c["work_id"]: c["work_title"] for c in chunks}
    for wid, k in sorted(alloc.items(), key=lambda x: -x[1]):
        print(f"  {title_by_wid[wid]}（{wid}）：{k}／{counts[wid]}")
    print(f"剩余 {len(remaining)} 条写入 {args.out_remaining}（下一窗再跑）")


if __name__ == "__main__":
    main()
