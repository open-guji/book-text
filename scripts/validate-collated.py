"""
整理本 / 全文 数据自洽性校验（按 manifest 认新结构，#307／#346，2026-10-02 改写）

扫 book-text 仓每个条目 `<Work|Book>/<c1>/<c2>/<c3>/<id>/manifest.json` 登记的**每个版本**
（default/、wikisource/、kanripo/、shidian/ 等），校验该版本 `index.json` 里登记的章
与磁盘上真实存在的 `NNN.md`／`NNN.json` 对得上。

新结构（09-30 起）：
    <id>/manifest.json            versions[]：key、kind(collated|transcription)、chapters_total…
    <id>/<key>/index.json         chapters[{n, file(无后缀的编号), title, has_json}]
    <id>/<key>/NNN.md             章文件；整理本另有同名 NNN.json（结构化条目，旧 juan/NNN.json）

背景（09-09 旧结构时代的事故，规范沿用）：juan_groups 与 juan_metadata 曾留着卷文件
**改名前**的旧名，前端按 groups 渲染侧栏，点出去的路径不存在 → 线上 404 且无报错。
规范：**chapters[] 是唯一可信来源**（取代旧 juan_files），其余一切引用都必须用它登记的章。

校验项（每个版本）：
1. chapters[].file 对应的 NNN.md 在磁盘上存在（整理本章可只有 NNN.json）；has_json=true 的另需 NNN.json 存在
2. 磁盘上的 NNN.md／NNN.json 都被 chapters 登记（无失联文件）
3. has_json 与磁盘上 NNN.json 是否存在一致（整理本章章应有 json）
4. manifest 里该版本的 chapters_total 与 chapters 条数相符
5. 整理本：index.json 的 juan_groups[].files（含 children 递归）、juan_metadata 的键，
   须与 chapters[].file **逐字相等**（`juan/005.json`／`005.json`／`005` 不再视作同一个）
6. 不应残留旧字段 juan_files／juan_files_original／total_juan／total_chapters 与 chapters 不符
7. 条目层：manifest.json 能解析、versions[0].key == 'default'、各版本目录存在

用法：
    python validate-collated.py [--root <book-text>]
    python validate-collated.py --json    # 输出 JSON 而非 markdown
    python validate-collated.py --strict  # 有问题时退出码非 0（CI 用）
（旧的 collated_edition/、full_text/ 结构已不再识别。）
"""

import sys, io, json, glob, os, re, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 仓根：--root > 环境变量 BOOK_TEXT_REPO > 常见位置探测。**不再写死单机路径。**
#
# 2026-09-14（E-md补齐 道所报）：原作写死 `D:/workspace/book-text`，云端会话的仓在
# `/home/user/book-text`，於是 glob 匹配不到任何档、`probs` 自然为空，
# **脚本印出「全部自洽」而其实一部都没扫**——路径错了不报错，只是悄悄扫出 0 部，
# 与真的全绿长得一模一样。与当日 pushmain.sh 那个 `--ours`、以及
# 「量对了数但量的不是那个东西」同族：**都朝着看起来没事的方向失效。**
# 治法有二，缺一不可：(1) 仓根改为可探测；(2) 扫出 0 个版本即判失败（见 main()）。
def _find_repo():
    env = os.environ.get('BOOK_TEXT_REPO')
    if env:
        return env.rstrip('/')
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.path.join(os.path.dirname(here), '..', 'book-text'),   # 与本仓并列
        '/home/user/book-text',
        '/home/user/open-guji/book-text',
        os.path.expanduser('~/workspace/book-text'),
        'D:/workspace/book-text',
    ]
    for c in cands:
        c = os.path.normpath(c)
        if os.path.isdir(os.path.join(c, 'Work')):
            return c.replace('\\', '/')
    return os.path.normpath(cands[0]).replace('\\', '/')   # 探不到也给个值，由 main() 的空扫检查拦下


REPO = _find_repo()

CHAPTER_FILE_RE = re.compile(r'^(\d+)\.(md|json)$')   # 版本目录下的章文件；其余（pages.tsv、校勘記.md 等）是附件，不算章


def load(path):
    try:
        return json.load(io.open(path, encoding='utf-8'))
    except Exception as e:
        return {'__error__': str(e)}


def stem(x):
    """`juan/005.json`／`005.json`／`005` → `005`"""
    return os.path.splitext(os.path.basename(str(x)))[0]


def walk_group_files(g):
    """递归取出一棵分组树里登记的所有文件名"""
    for x in (g.get('files') or []):
        yield x
    for c in (g.get('children') or []):
        yield from walk_group_files(c)


def check_version(vdir, owner_id, key, kind, mf_total):
    """校验一个版本目录，返回问题列表。owner_id/key 用于报告定位。"""
    wid = '%s/%s' % (owner_id, key)
    index_path = os.path.join(vdir, 'index.json')
    d = load(index_path)
    probs = []

    if not os.path.isfile(index_path):
        return [{'wid': wid, 'kind': '版本目录缺 index.json', 'detail': vdir}]
    if '__error__' in d:
        return [{'wid': wid, 'kind': 'index.json 解析失败', 'detail': d['__error__']}]

    chapters = d.get('chapters') or []
    if not chapters:
        return [{'wid': wid, 'kind': 'chapters 缺失或为空', 'detail': ''}]

    disk = set(os.listdir(vdir))
    reg = set()                      # 登记的章主干
    miss_md, miss_json, flag_bad = [], [], []
    for c in chapters:
        st = stem(c.get('file', ''))
        reg.add(st)
        # 整理本允许「只有 NNN.json、没有 NNN.md」（json-only 章，如 d59f2mua7w8y）；其余版本必须有 .md
        if st + '.md' not in disk and not (kind == 'collated' and st + '.json' in disk) \
                and not c.get('char_file'):  # original 形态（default 即 original）的章靠 char.json，无 .md
            miss_md.append(st + '.md')
        has_json = bool(c.get('has_json'))
        if has_json and st + '.json' not in disk:
            miss_json.append(st + '.json')
        if (st + '.json' in disk) != has_json:
            flag_bad.append(st)

    # 1) chapters → 磁盘
    if miss_md or miss_json:
        m = miss_md + miss_json
        probs.append({'wid': wid, 'kind': 'chapters 指向不存在的文件',
                      'detail': '%d/%d 章，例：%s' % (len(m), len(chapters), m[:3])})

    # 2) 磁盘 → chapters（失联文件：存在但没人登记，页面上永远打不开）
    orphan = sorted(f for f in disk
                    if CHAPTER_FILE_RE.match(f) and CHAPTER_FILE_RE.match(f).group(1) not in reg
                    and stem(f) not in reg)
    if orphan:
        probs.append({'wid': wid, 'kind': '磁盘上有未登记的章文件',
                      'detail': '%d 个，例：%s' % (len(orphan), orphan[:3])})

    # 3) has_json 与磁盘不一致
    if flag_bad:
        probs.append({'wid': wid, 'kind': 'has_json 与磁盘 NNN.json 不一致',
                      'detail': '%d 章，例：%s' % (len(flag_bad), flag_bad[:3])})

    # 4) manifest.chapters_total 与 chapters 条数
    if isinstance(mf_total, int) and mf_total != len(chapters):
        probs.append({'wid': wid, 'kind': 'manifest chapters_total 与 index chapters 条数不符',
                      'detail': 'manifest %d，index %d' % (mf_total, len(chapters))})

    # 5) 整理本：juan_groups / juan_metadata 引用须落在 chapters 里
    if kind == 'collated':
        reg_file = {c.get('file') for c in chapters}   # 逐字比，不取主干
        stale_g = []
        for g in (d.get('juan_groups') or []):
            stale_g += [x for x in walk_group_files(g) if x not in reg_file]
        if stale_g:
            probs.append({'wid': wid, 'kind': 'juan_groups 引用不在 chapters 中',
                          'detail': '%d 条，例：%s' % (len(stale_g), stale_g[:3])})
        stale_m = [k for k in (d.get('juan_metadata') or {}) if k not in reg_file]
        if stale_m:
            probs.append({'wid': wid, 'kind': 'juan_metadata 键不在 chapters 中',
                          'detail': '%d 条，例：%s' % (len(stale_m), stale_m[:3])})

    # 6) 旧字段残留 / total_chapters 口径漂移
    for old in ('juan_files', 'juan_files_original'):
        if old in d:
            probs.append({'wid': wid, 'kind': '残留旧字段 ' + old,
                          'detail': '09-30 后以 chapters 取代；应已随迁移删除'})
    tc = d.get('total_chapters')
    if isinstance(tc, int) and tc != len(chapters):
        probs.append({'wid': wid, 'kind': 'total_chapters 与实际章数不符',
                      'detail': '声明 %d，实际 %d' % (tc, len(chapters))})

    return probs


def check_owner(mpath):
    """校验一个条目（manifest.json）及其全部版本。返回 (n_versions, n_collated, problems)"""
    owner_dir = os.path.dirname(mpath)
    owner_id = os.path.basename(owner_dir)
    layer = os.path.relpath(mpath, REPO).replace(os.sep, '/').split('/', 1)[0]
    oid = '%s:%s' % (layer, owner_id)
    mf = load(mpath)
    if '__error__' in mf:
        return 0, 0, [{'wid': oid, 'kind': 'manifest.json 解析失败', 'detail': mf['__error__']}]

    vs = mf.get('versions') or []
    probs = []
    if not vs:
        return 0, 0, [{'wid': oid, 'kind': 'manifest versions 为空', 'detail': ''}]
    if (vs[0] or {}).get('key') != 'default':
        probs.append({'wid': oid, 'kind': 'versions[0] 不是 default',
                      'detail': str((vs[0] or {}).get('key'))})
    nc = 0
    for v in vs:
        key = (v or {}).get('key')
        if not key:
            probs.append({'wid': oid, 'kind': 'manifest 版本缺 key', 'detail': str(v)[:80]})
            continue
        kind = v.get('kind') or 'transcription'
        nc += kind == 'collated'
        vdir = os.path.join(owner_dir, key)
        if not os.path.isdir(vdir):
            probs.append({'wid': oid, 'kind': 'manifest 登记的版本目录不存在', 'detail': key})
            continue
        probs += check_version(vdir, oid, key, kind, v.get('chapters_total'))
    return len(vs), nc, probs


def main():
    global REPO
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', help='book-text 仓根（缺省：BOOK_TEXT_REPO 或自动探测）')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--strict', action='store_true')
    args = ap.parse_args()
    if args.root:
        REPO = args.root.rstrip('/').replace('\\', '/')

    manifests = sorted(glob.glob(REPO + '/Work/*/*/*/*/manifest.json')
                       + glob.glob(REPO + '/Book/*/*/*/*/manifest.json'))

    # ⚠️ 空扫必须判失败，不许静默报「全部自洽」（2026-09-14，见顶部 _find_repo 注）
    if not manifests:
        sys.stderr.write(
            '扫出 0 个条目 — 判失败，勿读作「全部自洽」。\n'
            '  仓根探测为：%s\n'
            '  该目录下没有 <Work|Book>/*/*/*/<id>/manifest.json（旧结构 collated_edition/、full_text/ 已不识别）。\n'
            '  指定仓根：--root /path/to/book-text 或 BOOK_TEXT_REPO=...\n' % REPO)
        sys.exit(2)

    probs = []
    n_ver = n_col = 0
    for m in manifests:
        a, b, p = check_owner(m)
        n_ver += a
        n_col += b
        probs += p

    if args.json:
        print(json.dumps({
            'n_owners': len(manifests),
            'n_versions': n_ver,
            'n_collated': n_col,
            'problems': probs,
        }, ensure_ascii=False, indent=2))
    else:
        print('# 整理本 / 全文 数据自洽性校验\n')
        print('扫描：条目 **%d** 个，版本 **%d** 个（其中整理本 **%d** 个）\n' % (len(manifests), n_ver, n_col))

        if not probs:
            print('✅ 全部自洽：manifest／index 登记的章与磁盘文件一一对应。\n')
        else:
            by_kind = {}
            for p in probs:
                by_kind.setdefault(p['kind'], []).append(p)
            print('| 问题 | 条目数 |')
            print('|---|---|')
            for k, v in sorted(by_kind.items(), key=lambda x: -len(x[1])):
                print('| %s | **%d** |' % (k, len(v)))
            print()
            for k, v in sorted(by_kind.items(), key=lambda x: -len(x[1])):
                print('**%s**（前 5）:' % k)
                for p in v[:5]:
                    print('  - `%s`: %s' % (p['wid'], p['detail']))
                print()

        print('## 总结\n')
        print('**问题条目数**: %d' % len(probs))
        if not probs:
            print('\n规范：`chapters[]` 是唯一可信来源，groups/metadata 一律引用它登记的章。')

    if args.strict and probs:
        sys.exit(1)


if __name__ == '__main__':
    main()
