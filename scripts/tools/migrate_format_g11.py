#!/usr/bin/env python3
"""schema 审查第 11 组：book-text 格式清理的一次性迁移（guji-format 04／05 §十一、07，2026-11）。

第一批（--part 1）
  A  entity：站内 target.href／targets[].href 删掉（由 entity_id 推）；href 与 entity_id 不一致的记账
  B  punct、entity：删顶层 stats
  D  版本 index.json：scraped_at 并入 fetched_at
  E  整理本章 NNN.json：section 里下划线证据字段收进 evidence（键名去掉前导下划线）
第二批（--part 2，等网站读取端两认上线后）
  C  整理本 section：work_id／work_ids 只留 work_ids（null → []，两者都有取并集、work_id 排第一）
  F  整理本章顶层只留 title、sections、meta，其余键收进 meta

只改格式，不改内容；原样保留各文件的缩进与结尾换行。默认干跑，--apply 才写。
用法：python3 scripts/tools/migrate_format_g11.py --root <book-text> --part 1 [--apply] [--log <tsv>]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

KEEP_TOP = ("title", "sections", "meta")


def load(p):
    with open(p, encoding="utf-8") as fh:
        s = fh.read()
    return s, json.loads(s)


def dump_like(orig: str, d) -> str:
    """按原文件的缩进（2／1／4）与结尾换行写回。"""
    for ind in (2, 1, 4):
        a = json.dumps(json.loads(orig), ensure_ascii=False, indent=ind)
        if orig in (a, a + "\n"):
            out = json.dumps(d, ensure_ascii=False, indent=ind)
            return out + ("\n" if orig.endswith("\n") else "")
    return json.dumps(d, ensure_ascii=False, indent=2) + "\n"


def mig_entity(d, log, rel):
    n = 0
    if d.pop("stats", None) is not None:
        n += 1
    for e in d.get("entities") or []:
        t = e.get("target") or {}
        if t.get("status") == "external":
            continue
        for x in [t] + [y for y in (t.get("targets") or []) if isinstance(y, dict)]:
            h = x.get("href")
            if h is None:
                continue
            tail = h.rsplit("/", 1)[-1]
            if x.get("entity_id") and tail != x["entity_id"]:
                log.append((rel, e.get("id", ""), e.get("text", ""), h, x["entity_id"]))
            del x["href"]
            n += 1
    return n


def mig_punct(d, log, rel):
    return 1 if d.pop("stats", None) is not None else 0


def mig_index(d, log, rel):
    if "scraped_at" not in d:
        return 0
    v = d.pop("scraped_at")
    if "fetched_at" in d and d["fetched_at"] != v:
        log.append((rel, "", "scraped_at", v, d["fetched_at"]))
        return 1
    # 放回原位置附近：scraped_at 改名为 fetched_at
    d["fetched_at"] = d.get("fetched_at", v)
    return 1


def mig_sections_evidence(d, log, rel):
    n = 0
    for s in d.get("sections") or []:
        if not isinstance(s, dict):
            continue
        us = [k for k in s if k.startswith("_")]
        if not us:
            continue
        ev = s.get("evidence") if isinstance(s.get("evidence"), dict) else {}
        for k in us:
            nk = k.lstrip("_")
            if nk in ev and ev[nk] != s[k]:
                raise SystemExit(f"{rel}: evidence.{nk} 已有不同的值，停")
            ev[nk] = s.pop(k)
            n += 1
        s["evidence"] = ev
    return n


def mig_sections_work_ids(d, log, rel):
    n = 0
    for s in d.get("sections") or []:
        if not isinstance(s, dict) or ("work_id" not in s and "work_ids" not in s):
            continue
        if "work_id" not in s:
            continue
        ids = []
        for v in [s.get("work_id")] + list(s.get("work_ids") or []):
            if isinstance(v, str) and v and v not in ids:
                ids.append(v)
        # 原位替换：work_id 的位置放 work_ids
        new = {}
        for k, v in s.items():
            if k == "work_id":
                new["work_ids"] = ids
            elif k == "work_ids":
                continue
            else:
                new[k] = v
        s.clear()
        s.update(new)
        n += 1
    return n


def mig_meta(d, log, rel):
    extra = [k for k in d if k not in KEEP_TOP]
    if not extra:
        return 0
    meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
    for k in extra:
        if k in meta and meta[k] != d[k]:
            raise SystemExit(f"{rel}: meta.{k} 已有不同的值，停")
        meta[k] = d.pop(k)
    secs = d.pop("sections")
    title = d.pop("title", None)
    d.clear()
    if title is not None:
        d["title"] = title
    d["meta"] = meta
    d["sections"] = secs
    return len(extra)


def is_chapter_json(d):
    return isinstance(d, dict) and isinstance(d.get("sections"), list)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--part", type=int, choices=(1, 2), required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--log", help="写不一致账（tsv）")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    jobs = []  # (glob, func, 名)
    if a.part == 1:
        jobs = [("*.entity.json", [mig_entity], "entity"), ("*.punct.json", [mig_punct], "punct"),
                ("index.json", [mig_index], "index"), ("[0-9][0-9][0-9].json", [mig_sections_evidence], "chapter")]
    else:
        jobs = [("[0-9][0-9][0-9].json", [mig_sections_work_ids, mig_meta], "chapter")]
    cnt = collections.Counter()
    files = collections.Counter()
    log = []
    for pat, funcs, name in jobs:
        for p in sorted(glob.glob(os.path.join(root, "[WB][oa]*", "*", "*", "*", "*", "*", pat))):
            rel = os.path.relpath(p, root)
            s, d = load(p)
            if name == "chapter" and not is_chapter_json(d):
                continue
            n = 0
            for f in funcs:
                k = f(d, log, rel)
                cnt[f"{name}:{f.__name__}"] += k
                n += k
            if n:
                files[name] += 1
                if a.apply:
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write(dump_like(s, d))
    for k, v in sorted(cnt.items()):
        print(f"{k}\t{v}")
    for k, v in sorted(files.items()):
        print(f"改动文件 {k}\t{v}")
    print(f"不一致\t{len(log)}")
    if a.log and log:
        with open(a.log, "w", encoding="utf-8") as fh:
            fh.write("file\tentity\ttext\told\tkept\n")
            for r in log:
                fh.write("\t".join(str(x) for x in r) + "\n")
    print("（已写）" if a.apply else "（干跑）")


if __name__ == "__main__":
    sys.exit(main())
