#!/usr/bin/env python3
"""合批：把 chunks.jsonl（真实段）与 seeded.jsonl（坏样本）混成一份 batch.jsonl 喂给 muse。

混合后打乱顺序，muse 看到的字段只有 chunk_id/work_title/chapter_title/text，
不带任何「这段是不是坏样本」的标记——坏样本的真值只留在 seeded.jsonl 里，
跑完批次后用 seeded.jsonl 对 batch 的结果算召回率。

用法：
    python3 build_batch.py --chunks chunks.jsonl --seeded seeded.jsonl --out batch.jsonl --seed 20260927
"""
import argparse
import json
import random
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--seeded", type=Path, default=None, help="第二批之后不用带坏样本，留空即可")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", required=True, type=int)
    args = ap.parse_args()

    real = [json.loads(l) for l in args.chunks.read_text(encoding="utf-8").splitlines()]
    seeded = (
        [json.loads(l) for l in args.seeded.read_text(encoding="utf-8").splitlines()]
        if args.seeded
        else []
    )

    batch = []
    for r in real:
        batch.append(
            {
                "chunk_id": r["chunk_id"],
                "work_title": r["work_title"],
                "chapter_title": r["chapter_title"],
                "text": r["text"],
            }
        )
    for s in seeded:
        batch.append(
            {
                "chunk_id": s["seed_id"],
                "work_title": s["work_title"],
                "chapter_title": s["chapter_title"],
                "text": s["text"],
            }
        )

    rng = random.Random(args.seed)
    rng.shuffle(batch)

    with args.out.open("w", encoding="utf-8") as out:
        for rec in batch:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"合批完成：真实 {len(real)} 段 ＋ 坏样本 {len(seeded)} 段 = {len(batch)} 段，写入 {args.out}")


if __name__ == "__main__":
    main()
