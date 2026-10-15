#!/usr/bin/env python3
"""专名 span 归一与官名拆分（T 小总管，#478）。

归一：逐字映射表以键表文件的 `normalize` 为准；DEFAULT_NORMALIZE 仅作后备。
拆分：整串先查键（命中不拆，对应 O 设计档 §四·4.2 的 C 类固定复合）；
否则按「最长官署前缀＋官职后缀」拆（A 类），键集由调用方传入。
不写 id，只输出分类与片段。
"""
import json
import sys

DEFAULT_NORMALIZE = {"尙": "尚", "郞": "郎", "戸": "戶", "叅": "參", "秘": "祕", "歴": "曆", "淸": "清"}


def normalize(text, mapping=None):
    return text.translate(str.maketrans(mapping or DEFAULT_NORMALIZE))


def split_office(span, office_keys, institution_keys, mapping=None):
    """返回 dict：mode ∈ whole|split|tail_only|none。

    whole：整串是官职键；split：官署前缀＋官职后缀两头命中；
    tail_only：只有官职后缀命中（前缀留作 scope 文本）；none：全未命中。
    """
    s = normalize(span, mapping)
    if s in office_keys:
        return {"mode": "whole", "base": s}
    if s in institution_keys:
        return {"mode": "institution", "institution": s}
    for i in range(len(s) - 1, 0, -1):
        prefix, tail = s[:i], s[i:]
        if tail in office_keys:
            if prefix in institution_keys:
                return {"mode": "split", "institution": prefix, "base": tail}
    for i in range(1, len(s)):  # 最长后缀优先
        tail = s[i:]
        if tail in office_keys:
            return {"mode": "tail_only", "scope_text": s[:i], "base": tail}
    return {"mode": "none"}


def clean_place_span(span, place_keys, mapping=None):
    """地名 span 前处理：返回 (kind, 命中键)。

    kind：direct 直接命中；strip_person 去掉「人」「籍」等后缀后命中；
    prefix 取最长的键前缀（复合地名如 泰州如臯→泰州，余部留作 note）；none。
    只做试探统计，不改数据。
    """
    s = normalize(span, mapping)
    if s in place_keys:
        return "direct", s
    for suf in ("人", "籍"):
        if s.endswith(suf) and s[:-1] in place_keys:
            return "strip_person", s[:-1]
    for i in range(len(s) - 1, 1, -1):
        if s[:i] in place_keys:
            return "prefix", s[:i]
    return "none", None


def key_sets(keys):
    """从 office_keys.json 分出官职键集与官署键集（按候选 subtype）。"""
    off, inst = set(), set()
    for k, cands in keys["keys"].items():
        for c in cands:
            (inst if c["subtype"] == "官署" else off).add(k)
    return off, inst


def main(argv):
    """用法：t_entity_split.py office_keys.json NNN.entity.json [--list]"""
    keys = json.load(open(argv[1], encoding="utf-8"))
    ent = json.load(open(argv[2], encoding="utf-8"))
    mapping = keys.get("normalize")
    off, inst = key_sets(keys)
    out, miss = {}, {}
    for e in ent["entities"]:
        if e["type"] == "office":
            r = split_office(e["text"], off, inst, mapping)
            out[r["mode"]] = out.get(r["mode"], 0) + 1
            if r["mode"] == "none":
                miss[e["text"]] = miss.get(e["text"], 0) + 1
    print(json.dumps({"modes": out, "none": miss}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
