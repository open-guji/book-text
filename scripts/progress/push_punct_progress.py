#!/usr/bin/env python3
"""把「标点／专名进度」写进中心库 progress.volume（A33，栏目文档见 kaiyuanguji-web docs/text-progress.md）。

读本仓 Book/<id>/default/index.json 的各章 punct_version／entity_version 和 NNN.punct.json／NNN.entity.json 的 stats，
对每册调 progress.put_volume(book_id, vol, 字段, 'A33')，只写 punct_status 和 extra.a33，不动别的字段。
可重复跑；各册更新后（合入 main 后）再跑一次。

    python3 scripts/progress/push_punct_progress.py            # 只打印，不写库
    python3 scripts/progress/push_punct_progress.py --apply    # 写库

连库：NEON_DATABASE_URL（正式库 main）或 GUJI_DATA_PG_DSN，经 open_guji_cv 的 connect（云会话自动起 443 桥）；
用 /opt/guji-venv/bin/python 跑。凭据只从环境变量取，不进仓。
"""
import argparse
import json
import sys
from pathlib import Path

BOOK_ID = "96mid1ogzk"  # 四庫全書總目：目前只有这一部有标点／专名线
WRITER = "A33"


def parse_range(s):
    out = set()
    for part in filter(None, s.split(",")):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def vol_fields(vdir, ch, wip):
    n = ch["n"]
    pv, ev = ch.get("punct_version"), ch.get("entity_version")
    if not (pv and ev):
        status = "进行中，未入库" if n in wip else "未开始"
        return {"punct_status": status, "extra": {"a33": {"punct_version": pv, "entity_version": ev}}}
    f = vdir / ch["file"]
    ps = json.loads(f.with_suffix(".punct.json").read_text("utf-8")).get("stats", {})
    es = json.loads(f.with_suffix(".entity.json").read_text("utf-8")).get("stats", {})
    total, matched = es.get("total_entities", 0), es.get("matched", 0)
    pct = round(100 * matched / total) if total else 0
    status = (f"标点 {pv}、专名 {ev} 已入库：标点 {ps.get('total_annotations', 0)} 处，"
              f"专名 {total} 个（已挂 {matched}，{pct}%；歧义 {es.get('ambiguous', 0)}，待建 {es.get('new_candidates', 0)}）")
    return {"punct_status": status,
            "extra": {"a33": {"punct_version": pv, "entity_version": ev,
                              "punct": ps, "entity": es, "entity_matched_pct": pct}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]), help="book-text 检出（应为最新 main）")
    ap.add_argument("--book", default=BOOK_ID)
    ap.add_argument("--wip", default="6-10", help="正在做、尚未入库的册号，如 6-10")
    ap.add_argument("--apply", action="store_true", help="真写库；不加只打印")
    a = ap.parse_args()

    vdir = next(Path(a.root).glob(f"Book/*/*/*/{a.book}/default"))
    chapters = json.loads((vdir / "index.json").read_text("utf-8"))["chapters"]
    wip = parse_range(a.wip)
    rows = [(f"{ch['n']:03d}", vol_fields(vdir, ch, wip)) for ch in chapters]
    for vol, fields in rows:
        print(vol, fields["punct_status"])
    if not a.apply:
        print("（未写库；加 --apply）")
        return
    from open_guji_cv.datastore.connect import connect
    with connect() as conn:
        for vol, fields in rows:
            conn.execute("SELECT progress.put_volume(%s, %s, %s::jsonb, %s)",
                         (a.book, vol, json.dumps(fields, ensure_ascii=False), WRITER))
    print(f"已写 {len(rows)} 册")


if __name__ == "__main__":
    sys.exit(main())
