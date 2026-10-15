#!/usr/bin/env python3
"""对照二：误报率抽样。从真实数据（不含 seeded）里按 muse 的 verdict 分层抽样，
50 条 muse 判 ok、20 条 muse 判 suspect，共 70 条，供 Claude 逐段复核。

用法：
    python3 sample_for_review.py --results results.jsonl --chunks chunks.jsonl \
        --out review_sample.jsonl --seed 20260927 --n-ok 50 --n-suspect 20

输出每条待复核记录带原文（从 chunks.jsonl 取回），复核时把 my_verdict／my_note
两个字段填上（ok|suspect，不一致的写谁对），另存一份 *_reviewed.jsonl。
"""
import argparse
import json
import random
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, type=Path)
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", required=True, type=int)
    ap.add_argument("--n-ok", type=int, default=50)
    ap.add_argument("--n-suspect", type=int, default=20)
    args = ap.parse_args()

    chunks_by_id = {}
    for l in args.chunks.read_text(encoding="utf-8").splitlines():
        if l.strip():
            c = json.loads(l)
            chunks_by_id[c["chunk_id"]] = c

    results = [json.loads(l) for l in args.results.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 只在真实数据里抽（chunk_id 能在 chunks.jsonl 里找到的），排除 seeded（seed_id 带 ~seed- 找不到）
    real_results = [r for r in results if r["chunk_id"] in chunks_by_id]

    ok_pool = [r for r in real_results if r.get("verdict") == "ok"]
    suspect_pool = [r for r in real_results if r.get("verdict") == "suspect"]

    rng = random.Random(args.seed)
    ok_sample = rng.sample(ok_pool, min(args.n_ok, len(ok_pool)))
    suspect_sample = rng.sample(suspect_pool, min(args.n_suspect, len(suspect_pool)))

    if len(ok_sample) < args.n_ok:
        print(f"警告：muse 判 ok 的只有 {len(ok_pool)} 条，不足 {args.n_ok}，全取")
    if len(suspect_sample) < args.n_suspect:
        print(f"警告：muse 判 suspect 的只有 {len(suspect_pool)} 条，不足 {args.n_suspect}，全取")

    with args.out.open("w", encoding="utf-8") as out:
        for r in ok_sample + suspect_sample:
            c = chunks_by_id[r["chunk_id"]]
            rec = {
                "chunk_id": r["chunk_id"],
                "work_title": c["work_title"],
                "chapter_title": c["chapter_title"],
                "text": c["text"],
                "muse_verdict": r.get("verdict"),
                "muse_issues": r.get("issues"),
                "my_verdict": None,
                "my_note": None,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"抽样完成：ok {len(ok_sample)} 条 ＋ suspect {len(suspect_sample)} 条 = {len(ok_sample) + len(suspect_sample)} 条，写入 {args.out}")


if __name__ == "__main__":
    main()
