#!/usr/bin/env python3
"""由中心库的 codepoints.yaml 生成 scripts/codepoints.json（F-OV-18 的归一表副本），不手抄。

用法：
  python3 scripts/tools/sync_codepoints.py --default <config/codepoints.yaml> \\
      --book 96mid1ogzk=<books/96mid1ogzk.yaml 或含 codepoints 键的 yaml> [--book ...]
  python3 scripts/tools/sync_codepoints.py --from-json <含 "books.<书号>" 键的 json> ...   # 过渡：ZM 导出的同步件
yaml 里取顶层 `codepoints: {另一码位: 本书码位}`；册表覆盖 default；与 default 相同的键不重复写进册表。
"""
import argparse
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "codepoints.json")


def load_yaml_cp(path):
    import yaml
    with open(path, encoding="utf-8") as fh:
        y = yaml.safe_load(fh) or {}
    return {str(k): str(v) for k, v in (y.get("codepoints") or {}).items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--default", help="工作区 config/codepoints.yaml（对所有书生效的部分）")
    ap.add_argument("--book", action="append", default=[], metavar="ID=YAML")
    ap.add_argument("--from-json", action="append", default=[], help="含 default／books.<书号> 键的同步件")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    cur = json.load(open(a.out, encoding="utf-8")) if os.path.exists(a.out) else {}
    default = dict(cur.get("default") or {})
    books = dict(cur.get("books") or {})
    if a.default:
        default = load_yaml_cp(a.default)
    for b in a.book:
        bid, _, p = b.partition("=")
        books[bid] = load_yaml_cp(p)
    for j in a.from_json:
        d = json.load(open(j, encoding="utf-8"))
        for k, v in d.items():
            if k.startswith("books."):
                books[k[len("books."):]] = v
    for bid in books:
        books[bid] = {k: v for k, v in books[bid].items() if default.get(k) != v}
    cur.update({"default": default, "books": books})
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")
    print(f"写出 {a.out}：default {len(default)} 条，books {sorted(books)}", file=sys.stderr)


if __name__ == "__main__":
    main()
