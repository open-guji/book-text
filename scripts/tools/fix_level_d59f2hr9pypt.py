#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T6 道 · 只修一件事：《漢藝文志考證》（work_id d59f2hr9pypt）缺 level 的 336 处 section。

依据：文本总管裁决（inbox/T6-格式存量基线与清账/20260926-0706-ask.md 的回批，见任务书
T6-格式存量基线与清账.md 末尾「裁决」§4）——
    - type=verification（310 处）：机械回填 level: 3（全库该 type 的压倒性众数，本书虽无
      内部锚点，但风险低，总管已直接批）。
    - type=preface（26 处）：**不套全库众数**，要求先看本书内部结构能否推出；本道核实过
      本书的 index.json（无 juan_groups，文件与卷/类一一对应）与 text/*.md（每档只有一个
      顶层 `#` 标题，entry 一级不落 md 标题，没有可比对的标题层级信号）——**本书内部推不
      出**，故 preface 26 处**不动**，继续留在基线里（裁决原文「推不出就留在基线里，报告
      写明」）。

只加 level 键，不改任何既有键的值；key 顺序按全库惯例插在 title 之后
（对照现状样本 {"title":..., "level":..., "type":...}）。

用法：
    python3 fix_level_d59f2hr9pypt.py <book-text 仓根>              # 干跑，只打印将改动的处数
    python3 fix_level_d59f2hr9pypt.py <book-text 仓根> --apply      # 真正写盘
"""
import json
import os
import sys

WORK_ID = "d59f2hr9pypt"
SHARD = ("y", "p", "t")  # <c1>/<c2>/<c3>，即 work_id 的倒数第 3/2/1 字符


def main():
    if len(sys.argv) < 2:
        print("用法：fix_level_d59f2hr9pypt.py <book-text 仓根> [--apply]", file=sys.stderr)
        sys.exit(2)
    root = sys.argv[1]
    apply = "--apply" in sys.argv

    juan_dir = os.path.join(root, "Work", *SHARD, WORK_ID, "collated_edition", "juan")
    if not os.path.isdir(juan_dir):
        print(f"路径不存在：{juan_dir}", file=sys.stderr)
        sys.exit(2)

    changed_files = 0
    changed_sections = 0
    skipped_preface = 0
    other_missing = []

    for name in sorted(os.listdir(juan_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(juan_dir, name)
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        file_changed = False
        for s in d.get("sections", []) if isinstance(d, dict) else []:
            if not isinstance(s, dict) or "level" in s:
                continue
            t = s.get("type")
            if t == "verification":
                new_s = {}
                for k, v in s.items():
                    new_s[k] = v
                    if k == "title":
                        new_s["level"] = 3
                if "level" not in new_s:  # 极端情况：没有 title 键，退回直接插到最前
                    new_s = {"level": 3, **s}
                s.clear()
                s.update(new_s)
                changed_sections += 1
                file_changed = True
            elif t == "preface":
                skipped_preface += 1
            else:
                other_missing.append((name, s.get("title"), t))
        if file_changed:
            changed_files += 1
            if apply:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                    f.write("\n")

    tag = "" if apply else "[干跑，未写盘] "
    print(f"{tag}改动文件数：{changed_files}／16；补 level=3 的 verification 处数：{changed_sections}"
          f"（期望 310）；跳过（本书内部推不出，留基线）的 preface 处数：{skipped_preface}（期望 26）")
    if other_missing:
        print(f"⚠️ 发现意料之外的类型也缺 level（{len(other_missing)} 处），未处理，人工看：")
        for name, title, t in other_missing[:20]:
            print(f"  {name} type={t} title={title!r}")


if __name__ == "__main__":
    main()
