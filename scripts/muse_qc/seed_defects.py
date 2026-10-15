#!/usr/bin/env python3
"""造坏样本：从 chunks.jsonl 里另取 30 段，人为注入六类已知缺陷（各 5 段），
记录真值到 seeded.jsonl，供质检对照用「召回率」。

用法：
    python3 seed_defects.py --chunks chunks.jsonl --out seeded.jsonl --seed 20260927

seeded 记录字段：
    {"seed_id": "<原 chunk_id>~seed-<类别>", "based_on": "<原 chunk_id>",
     "work_id", "work_title", "chapter_title", "chapter_file",
     "defect_type": "template|wikilink|html|garbled|non_text|table",
     "injected_text": "插入的那一行", "insert_after_line": N（在段内第几行之后插入，0=段首）,
     "text": "注入后的全文（喂给 muse 的就是这份）"}

六类样例注入文本，写死在这里、也照抄进报告，方便复核召回是否算对：
    1. template  {{NoteTA|1=zh-hans:里;zh-hant:裏;}}
    2. wikilink  參見[[維基文庫:凡例]]。
    3. html      <span style="color:red">校勘</span>&nbsp;
    4. garbled   锟斤拷烫烫烫��
    5. non_text  ==校勘記==\n卷中「云云」當作「雲雲」，據四庫本改。
       （或页脚体：本作品在全世界都属于公有领域，因为作者逝世已经超过100年，并且于1929年1月1日之前出版。）
    6. table     {| class="wikitable"\n|-\n| 甲 || 乙\n|-\n| 丙 || 丁\n|}
"""
import argparse
import json
import random
import sys
from pathlib import Path

DEFECT_SAMPLES = {
    "template": ["{{NoteTA|1=zh-hans:里;zh-hant:裏;}}"],
    "wikilink": ["參見[[維基文庫:凡例]]，另見[[漢典]]。"],
    "html": ['<span style="color:red">校勘</span>&nbsp;此處存疑。'],
    "garbled": ["锟斤拷烫烫烫���"],
    "non_text": [
        "==校勘記==\n卷中「云云」當作「雲雲」，據四庫本改。",
        "本作品在全世界都属于公有领域，因为作者逝世已经超过100年，并且于1929年1月1日之前出版。",
    ],
    "table": ['{| class="wikitable"\n|-\n| 甲 || 乙\n|-\n| 丙 || 丁\n|}'],
}

CATEGORIES = ["template", "wikilink", "html", "garbled", "non_text", "table"]
PER_CATEGORY = 5


def inject(text: str, snippet: str, rng: random.Random):
    lines = text.split("\n")
    pos = rng.randint(0, len(lines))  # 插到第 pos 行之后（0=段首）
    new_lines = lines[:pos] + [snippet] + lines[pos:]
    return "\n".join(new_lines), pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", required=True, type=int)
    args = ap.parse_args()

    chunks = [json.loads(l) for l in args.chunks.read_text(encoding="utf-8").splitlines()]
    rng = random.Random(args.seed)

    need = len(CATEGORIES) * PER_CATEGORY
    picked = rng.sample(chunks, need)
    rng.shuffle(picked)

    records = []
    idx = 0
    for cat in CATEGORIES:
        for _ in range(PER_CATEGORY):
            base = picked[idx]
            idx += 1
            snippet = rng.choice(DEFECT_SAMPLES[cat])
            new_text, pos = inject(base["text"], snippet, rng)
            seed_id = f"{base['chunk_id']}~seed-{cat}"
            records.append(
                {
                    "seed_id": seed_id,
                    "based_on": base["chunk_id"],
                    "work_id": base["work_id"],
                    "work_title": base["work_title"],
                    "chapter_title": base["chapter_title"],
                    "chapter_file": base["chapter_file"],
                    "defect_type": cat,
                    "injected_text": snippet,
                    "insert_after_line": pos,
                    "text": new_text,
                }
            )

    with args.out.open("w", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"造出 {len(records)} 段坏样本（每类 {PER_CATEGORY} 段），写入 {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
