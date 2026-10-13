"""E3：为每个版本写入 manifest.json 的 script 字段（hant／hans／mixed）。

口径与 S4 分布表一致（03-文字类型分布.py §1.2）：章内 CJK 字，t2s／s2t 判简体特有字 S、
繁体特有字 T，剔除古汉语通用字（AMB）；S/(S+T) >0.7 为 hans，>0.05 为 mixed，其余 hant。
没有字的空版本不写。

用法：
  python3 scripts/set_script.py --root <本仓> --dry-run [--report 差异.tsv] [--expect-tsv S4明细.tsv]
  python3 scripts/set_script.py --root <本仓> --source wikisource [--source kanripo]

- 幂等：已有相同值不改；只改版本里的 script 一个键，其余字段与缩进原样保留。
- 写入时保留原文件的末尾换行习惯（有则有、无则无）；--check-format 只报告「不改内容时重写会不会变字节」。
"""
import argparse
import collections
import csv
import json
import os
import re
import sys

import opencc

SKIP_DIRS = {'.git', 'scripts', '.claude-inbox', 'index', 'sources', 'fragments'}
AMB = set('于云余后里干发台才只面象系几向制征当采须胡历朴松斗谷郁表折周范借卜复据儿么出历获价党别征坏回困姜刮克夸台尽恶楼并买卖扑咸冲准据谷赞丑乾')
COMMENT = re.compile(r'<!--.*?-->', re.S)
VERSION_FILE = re.compile(r'\d{3}\.md$')

t2s = opencc.OpenCC('t2s')
s2t = opencc.OpenCC('s2t')
_kind_cache = {}


def cjk(c):
    o = ord(c)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x20000 <= o <= 0x3134F or 0xF900 <= o <= 0xFAFF


def kind(c):
    k = _kind_cache.get(c)
    if k is None:
        a = t2s.convert(c)
        b = s2t.convert(c)
        k = 'T' if a != c else ('S' if (b != c and c not in AMB) else 'N')
        _kind_cache[c] = k
    return k


def band(ratio):
    if ratio > 0.7:
        return 'hans'
    if ratio > 0.05:
        return 'mixed'
    return 'hant'


def classify_version(vdir):
    """返回 (band, T, S)；没有可计字的返回 ('empty', 0, 0)。"""
    T = S = 0
    for f in sorted(os.listdir(vdir)):
        if not VERSION_FILE.match(f):
            continue
        with open(os.path.join(vdir, f), encoding='utf-8') as fh:
            text = COMMENT.sub('', fh.read())
        for c, n in collections.Counter(c for c in text if cjk(c)).items():
            k = kind(c)
            if k == 'T':
                T += n
            elif k == 'S':
                S += n
    if T + S == 0:
        return 'empty', T, S
    return band(S / (T + S)), T, S


def iter_manifests(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        if 'manifest.json' in fn:
            yield dp


def dump(obj, trailing_newline):
    out = json.dumps(obj, ensure_ascii=False, indent=2)
    return out + '\n' if trailing_newline else out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', required=True)
    ap.add_argument('--dry-run', action='store_true', help='只出差异，不写文件')
    ap.add_argument('--source', action='append', help='只处理这些 source（可多次给）；E4 分批用')
    ap.add_argument('--report', help='差异表输出（TSV）')
    ap.add_argument('--expect-tsv', help='S4 明细 TSV；逐版本比对 band，报告不一致数')
    ap.add_argument('--check-format', action='store_true', help='报告：不改内容时重写会变字节的 manifest 数')
    args = ap.parse_args()

    expect = {}
    if args.expect_tsv:
        with open(args.expect_tsv, encoding='utf-8') as fh:
            for r in csv.DictReader(fh, delimiter='\t'):
                expect[(r['rel'], r['key'])] = r['band']

    stats = collections.Counter()
    rows = []
    mismatch_expect = []
    fmt_bad = []

    for dp in sorted(iter_manifests(args.root)):
        rel = os.path.relpath(dp, args.root)
        mpath = os.path.join(dp, 'manifest.json')
        with open(mpath, encoding='utf-8') as fh:
            raw = fh.read()
        m = json.loads(raw)
        trailing = raw.endswith('\n')
        if args.check_format and dump(m, trailing) != raw:
            fmt_bad.append(rel)
        changed = False
        for v in m.get('versions', []):
            key = v.get('key', '?')
            src = v.get('source', '?')
            if args.source and src not in args.source:
                stats['skip-source'] += 1
                continue
            vdir = os.path.join(dp, key)
            if not os.path.isdir(vdir):
                stats['no-dir'] += 1
                continue
            new, T, S = classify_version(vdir)
            stats['versions'] += 1
            if (rel, key) in expect and expect[(rel, key)] != new:
                mismatch_expect.append((rel, key, expect[(rel, key)], new))
            if new == 'empty':
                stats['empty-not-written'] += 1
                continue
            old = v.get('script')
            if old == new:
                stats['unchanged'] += 1
                continue
            rows.append((rel, key, src, '' if old is None else old, new, T, S))
            stats['would-write' if args.dry_run else 'written'] += 1
            if not args.dry_run:
                v['script'] = new
                changed = True
        if changed:
            with open(mpath, 'w', encoding='utf-8') as fh:
                fh.write(dump(m, trailing))

    if args.report:
        with open(args.report, 'w', encoding='utf-8') as fh:
            fh.write('rel\tkey\tsource\told_script\tnew_script\tT\tS\n')
            for r in rows:
                fh.write('\t'.join(str(x) for x in r) + '\n')

    mode = 'dry-run' if args.dry_run else 'write'
    print(f'[{mode}] 版本 {stats["versions"]}；已一致不改 {stats["unchanged"]}；'
          f'{"将写入" if args.dry_run else "已写入"} {stats["would-write" if args.dry_run else "written"]}；'
          f'空版本跳过 {stats["empty-not-written"]}；按 source 跳过 {stats["skip-source"]}；无目录 {stats["no-dir"]}')
    print('改动 manifest 文件数（dry-run 预计）：'
          f'{len({r[0] for r in rows})}')
    print('data.yml：本仓没有此文件；只改 manifest.json，是否重传 manifest 由网站发布侧决定（未验）。')
    if args.expect_tsv:
        print(f'与 S4 明细逐版本比对：不一致 {len(mismatch_expect)}')
        for r in mismatch_expect[:20]:
            print('  mismatch', r)
    if args.check_format:
        print(f'重写会变字节的 manifest：{len(fmt_bad)}')
        for r in fmt_bad[:10]:
            print('  fmt', r)
    return 1 if mismatch_expect else 0


if __name__ == '__main__':
    sys.exit(main())
