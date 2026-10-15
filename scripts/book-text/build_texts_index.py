#!/usr/bin/env python3
"""由各条目的 manifest.json 汇总生成全局索引 index/texts/{0-f}.json（#307 新结构）。

取代旧的 build_index.py（旧 index/collated、index/full_text 已随迁移删除）。
任何道改动了 book-text 里的文本（加版本、改章数、换 default），推送前都要跑一次：

    python3 build_texts_index.py --root <book-text 仓根>

输出格式与 migrate_texts.py 的 build_global_index 完全一致：
    { "<id>": [ {"key", "kind", "label", "chapters_total"[, "edition_label"][, "quality"][, "script"]}, ... ] }（edition_label 可选，10-01 起；quality 可选，10-10 起——book-index 的 none／placeholder 过滤靠它；script 可选，10-13 起——hant／hans／mixed，manifest 缺则这里也缺，不写 null，overview#605 E2），按 manifest.versions 顺序，
    分片用与 migrate_texts.shard() 相同的哈希。
"""
import argparse
import glob
import json
import os


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
    n = 0
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
    for s, b in buckets.items():
        write_json(os.path.join(a.root, 'index', 'texts', f'{s}.json'), b)
    print(f'index/texts/  {n} 个条目')


if __name__ == '__main__':
    main()
