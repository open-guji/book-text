#!/usr/bin/env python3
"""检查 Book 条目的授权字段：值必须是非空字符串，不得为 null、「未知」「unknown」。

读 Book/*/*/*/*/manifest.json 的 versions[].license，以及 default/ 或 original/
版本目录 index.json 里的 source.license（有则查）。逐值统计，有违规退出码 1。
用法：python3 scripts/check_license.py [仓根目录]
"""
import glob
import json
import os
import sys
from collections import Counter

BAD = {'未知', 'unknown'}


def check(root):
    counts, bad = Counter(), []

    def look(path, value):
        counts[repr(value)] += 1
        if not isinstance(value, str) or not value.strip() or value.strip().lower() in BAD:
            bad.append((os.path.relpath(path, root), value))

    for mp in sorted(glob.glob(os.path.join(root, 'Book', '*', '*', '*', '*', 'manifest.json'))):
        with open(mp, encoding='utf-8') as f:
            manifest = json.load(f)
        for v in manifest.get('versions', []):
            look(mp, v.get('license'))
        for key in ('default', 'original'):
            ip = os.path.join(os.path.dirname(mp), key, 'index.json')
            if not os.path.isfile(ip):
                continue
            with open(ip, encoding='utf-8') as f:
                src = json.load(f).get('source') or {}
            if 'license' in src:
                look(ip, src['license'])
    return counts, bad


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    counts, bad = check(root)
    for value, n in counts.most_common():
        print(f'{n}\t{value}')
    for path, value in bad:
        print(f'违规: {path}: license={value!r}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
