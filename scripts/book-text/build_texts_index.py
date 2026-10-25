#!/usr/bin/env python3
"""由各条目的 manifest.json 汇总生成全局索引 index/texts/{0-f}.json（#307 新结构）。

取代旧的 build_index.py（旧 index/collated、index/full_text 已随迁移删除）。
任何道改动了 book-text 里的文本（加版本、改章数、换 default），推送前都要跑一次：

    python3 build_texts_index.py --root <book-text 仓根>

另：original 版本（目录名 original，或 manifest 里 is_original 的版本）的 index.json，按各册 punct 的标题符
重算章条目的 headings（目录缓存，guji-format spec/07 §3.3，GUJI-240）；没有标题符的册不写该键。

输出格式与 migrate_texts.py 的 build_global_index 完全一致：
    { "<id>": [ {"key", "kind", "label", "chapters_total"[, "edition_label"][, "quality"][, "script"]}, ... ] }（edition_label 可选，10-01 起；quality 可选，10-10 起——book-index 的 none／placeholder 过滤靠它；script 可选，10-13 起——hant／hans／mixed，manifest 缺则这里也缺，不写 null，overview#605 E2），按 manifest.versions 顺序，
    分片用与 migrate_texts.shard() 相同的哈希。
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import original_version as OV  # noqa: E402


def shard(i):
    # 与 migrate_texts.py / 旧 build_index.py 的 shard() 相同，改动须三处一起改
    h = 0
    for c in i:
        h = ((h * 31) + ord(c)) & 0xFFFFFFFF
    return '%x' % (h % 16)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    a = ap.parse_args()
    buckets = {c: {} for c in '0123456789abcdef'}
    n = nh = 0
    for m in (sorted(glob.glob(os.path.join(a.root, 'Work/*/*/*/*/manifest.json'))) +
              sorted(glob.glob(os.path.join(a.root, 'Book/*/*/*/*/manifest.json')))):
        d = json.load(open(m, encoding='utf-8'))
        oid = d['id']
        vs = d.get('versions') or []
        assert vs and vs[0]['key'] == 'default', f'{m}: versions[0] 必须是 default'
        buckets[shard(oid)][oid] = [
            {'key': v['key'], 'kind': v['kind'], 'label': v['label'], 'chapters_total': v['chapters_total'],
             **({'edition_label': v['edition_label']} if v.get('edition_label') else {}),
             **({'quality': v['quality']} if v.get('quality') else {}),
             **({'script': v['script']} if v.get('script') else {})}
            for v in vs
        ]
        n += 1
        for v in vs:
            vdir = os.path.join(os.path.dirname(m), v['key'])
            if os.path.isfile(os.path.join(vdir, 'index.json')) and OV.is_original_dir(vdir):
                if OV.sync_headings(vdir):
                    nh += 1
    # 防稀疏检出／缺文件：找到的条目远少于现有索引时拒绝覆盖（2026-10-25 #246 曾因稀疏检出把索引写成空 {}）
    old = 0
    for s in buckets:
        f = os.path.join(a.root, 'index', 'texts', f'{s}.json')
        if os.path.isfile(f):
            try:
                old += len(json.load(open(f, encoding='utf-8')))
            except ValueError:
                pass
    if n == 0 or n < old * 0.9:
        sys.exit(f'拒绝覆盖：只找到 {n} 个 manifest，现有索引 {old} 条。请在完整检出（含全部 manifest.json）上运行。')
    for s, b in buckets.items():
        write_json(os.path.join(a.root, 'index', 'texts', f'{s}.json'), b)
    print(f'index/texts/  {n} 个条目' + (f'；重算目录缓存 headings {nh} 个版本' if nh else ''))


if __name__ == '__main__':
    main()
