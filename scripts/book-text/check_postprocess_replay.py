#!/usr/bin/env python3
"""重跑比对：entity_postprocess.py 的 dry-run log 与既有金标 postprocess_log-册NNN.tsv 逐条对照（GUJI-378 ①）。

比对键＝(规则, 动作, before, after)，忽略 entity_id 与 after 里「同eNNNNN」的编号（重跑会重新编号）。
只比 --rules 指定的规则：输入若已应用过某规则（如 N1–N4 已落库），重跑不会再触发，不能拿来比。

用法  python3 check_postprocess_replay.py <in.entity.json> <金标 postprocess_log.tsv>
          [--rules N7,N6] [--book-index <book-index 根>]
退出码  0＝一致；1＝有差异（列出两侧独有条目）。
"""
import argparse
import collections
import csv
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read_log(path, rules):
    rows = list(csv.reader(open(path, encoding='utf-8'), delimiter='\t'))[1:]
    return collections.Counter(
        (r[0], r[2], r[3], re.sub(r'同e\d+', '同e*', r[4])) for r in rows if len(r) >= 5 and r[0] in rules)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('entity_json')
    ap.add_argument('gold_log')
    ap.add_argument('--rules', default='N7,N6', help='按此顺序执行；N7 必须先于 N6（N6 要用 N7 拆出的全名）')
    ap.add_argument('--book-index')
    a = ap.parse_args(argv)
    rules = set(a.rules.split(','))
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / 'replay.tsv'
        cmd = [sys.executable, str(HERE / 'entity_postprocess.py'), a.entity_json, '--dry-run',
               '--log', str(log), '--rules', a.rules]
        if a.book_index:
            cmd += ['--book-index', a.book_index]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        new = read_log(log, rules)
    gold = read_log(a.gold_log, rules)
    only_g, only_n = gold - new, new - gold
    print(f'金标 {sum(gold.values())}｜重跑 {sum(new.values())}｜仅金标 {sum(only_g.values())}｜仅重跑 {sum(only_n.values())}')
    for tag, c in (('仅金标', only_g), ('仅重跑', only_n)):
        for k, v in list(c.items())[:20]:
            print(f'  {tag} ×{v}  {k}')
    return 0 if not only_g and not only_n else 1


if __name__ == '__main__':
    sys.exit(main())
