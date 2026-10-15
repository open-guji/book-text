#!/usr/bin/env python3
"""对照一：召回率。用 seeded.jsonl 的真值核对 results.jsonl 里同 chunk_id 的判断。

「查出」＝ muse 把这段判成 suspect（不论类别对不对）。
「类别对了」＝ 查出的同时，issues 里至少一条 type 与注入的 defect_type 一致。

用法：
    python3 analyze_recall.py --results results.jsonl --seeded seeded.jsonl --out recall_report.json
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, type=Path)
    ap.add_argument("--seeded", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    results = {}
    for l in args.results.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            results[r["chunk_id"]] = r

    seeded = [json.loads(l) for l in args.seeded.read_text(encoding="utf-8").splitlines()]

    per_category = defaultdict(lambda: {"total": 0, "found": 0, "type_correct": 0, "missed": []})
    rows = []
    for s in seeded:
        cat = s["defect_type"]
        per_category[cat]["total"] += 1
        res = results.get(s["seed_id"])
        found = bool(res) and res.get("verdict") == "suspect"
        type_correct = found and any(
            issue.get("type") == cat for issue in res.get("issues", [])
        )
        if found:
            per_category[cat]["found"] += 1
        if type_correct:
            per_category[cat]["type_correct"] += 1
        if not found:
            per_category[cat]["missed"].append(s["seed_id"])
        rows.append(
            {
                "seed_id": s["seed_id"],
                "defect_type": cat,
                "injected_text": s["injected_text"],
                "muse_verdict": res.get("verdict") if res else "无结果",
                "muse_issues": res.get("issues") if res else None,
                "found": found,
                "type_correct": type_correct,
            }
        )

    total = len(seeded)
    total_found = sum(v["found"] for v in per_category.values())
    total_type_correct = sum(v["type_correct"] for v in per_category.values())

    report = {
        "total_seeded": total,
        "found": total_found,
        "found_rate": round(total_found / total, 4) if total else None,
        "type_correct": total_type_correct,
        "type_correct_rate": round(total_type_correct / total, 4) if total else None,
        "per_category": {
            cat: {
                "total": v["total"],
                "found": v["found"],
                "type_correct": v["type_correct"],
                "missed_seed_ids": v["missed"],
            }
            for cat, v in per_category.items()
        },
        "rows": rows,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"召回：{total_found}/{total} 段查出（{report['found_rate']:.1%}）；"
        f"{total_type_correct}/{total} 段类别判对（{report['type_correct_rate']:.1%}）"
    )
    for cat, v in per_category.items():
        print(f"  {cat}: 查出 {v['found']}/{v['total']}，类别对 {v['type_correct']}/{v['total']}")


if __name__ == "__main__":
    main()
