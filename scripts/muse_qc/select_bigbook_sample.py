#!/usr/bin/env python3
"""大部头抽样：文本总管交代——T15 批次里的几部大部头只抽 20% 的段，其余部跑全量。

用法：
    python3 select_bigbook_sample.py --chunks chunks_t15b1.jsonl --big-work-ids ids.txt \
        --fraction 0.2 --seed 20260927 --out selected.jsonl
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--big-work-ids", required=True, type=Path, help="一行一个 work_id，抽样对象")
    ap.add_argument("--fraction", type=float, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    big_ids = {l.strip() for l in args.big_work_ids.read_text(encoding="utf-8").splitlines() if l.strip()}
    chunks = [json.loads(l) for l in args.chunks.read_text(encoding="utf-8").splitlines()]

    by_work = defaultdict(list)
    for c in chunks:
        by_work[c["work_id"]].append(c)

    rng = random.Random(args.seed)
    selected = []
    report = []
    for wid, recs in by_work.items():
        if wid in big_ids:
            k = max(1, round(len(recs) * args.fraction))
            picked = rng.sample(recs, k)
            selected.extend(picked)
            report.append((recs[0]["work_title"], wid, len(recs), k, "20%抽样"))
        else:
            selected.extend(recs)
            report.append((recs[0]["work_title"], wid, len(recs), len(recs), "全量"))

    missing = big_ids - set(by_work.keys())
    if missing:
        print(f"警告：--big-work-ids 里有 {len(missing)} 个 work_id 在 chunks 里找不到：{missing}")

    with args.out.open("w", encoding="utf-8") as out:
        for c in selected:
            out.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"选出 {len(selected)}／{len(chunks)} 段，写入 {args.out}")
    for title, wid, total, k, mode in sorted(report, key=lambda r: -r[2]):
        print(f"  {title}（{wid}）：{k}／{total}（{mode}）")


if __name__ == "__main__":
    main()
