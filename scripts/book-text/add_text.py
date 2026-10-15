#!/usr/bin/env python3
"""往新结构（#307）的条目里加一份文本版本，并更新 manifest.json。

给抓取道用：抓取脚本照旧产出一个「旧式全文目录」——index.json（含 source、chapters 等，
章文件名 001.md…）＋ 各章 .md（可另带 pages.tsv 等附件）——再用本脚本放进条目：

    python3 add_text.py --root <book-text> --owner Work/t/m/o/<id> --src <旧式全文目录> [--dry-run]
    python3 build_texts_index.py --root <book-text>      # 改完必跑

规则（用户 09-30 定，与 migrate_texts.py 一致）：
- key 按来源：wikisource／kanripo／shidian（其他来源取 source.name 小写 ascii），同源第二份起 -2、-3。
- 主版本：整理本 → 维基 → Kanripo → 识典；同源比章数，多者优先。新版本排位高于现 default 时，
  现 default 挪到按其来源命名的 key，新版本放进 default/。
- 版本 index.json 原样保留旧 index 的全部字段（source、text_quality、variants、每章 md_len／
  page_title／revid 等），只把 chapters[].file 改成不带后缀的编号，并补 has_json。
- manifest 里的 license／source_name／source_url／quality 取自 source 与 text_quality。
"""
import argparse
import json
import os
import re
import shutil

RANK = {'collated': 0, 'wikisource': 1, 'kanripo': 2, 'shidian': 3}
LABEL = {'collated': '整理本', 'wikisource': '維基文庫', 'kanripo': 'Kanripo', 'shidian': '識典古籍'}
RESERVED = {'default', 'manifest', 'fragments', 'sources'}


def source_of(src_index):
    s = src_index.get('source') or {}
    name = (s.get('name') or '').strip()
    url = s.get('url') or ''
    if '維基' in name or '维基' in name or 'wikisource' in url or name.lower() == 'wikisource':
        return 'wikisource'
    if 'kanripo' in (name + url).lower():
        return 'kanripo'
    if '识典' in name or '識典' in name or 'shidianguji' in url:
        return 'shidian'
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not slug or not slug[0].isalpha():
        raise SystemExit(f'认不出来源：source.name={name!r}，请先在 add_text.py 里补映射')
    return slug


def rank(source, chapters):
    return (RANK.get(source, 99), -(chapters or 0))


def next_key(base, used):
    if base not in used and base not in RESERVED:
        return base
    i = 2
    while f'{base}-{i}' in used:
        i += 1
    return f'{base}-{i}'


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--owner', required=True, help='条目目录，相对仓根，如 Work/t/m/o/d59f2ew0ctmo')
    ap.add_argument('--src', required=True, help='旧式全文目录（index.json＋NNN.md）')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    owner_dir = os.path.join(a.root, a.owner)
    oid = os.path.basename(a.owner.rstrip('/'))
    src_index = json.load(open(os.path.join(a.src, 'index.json'), encoding='utf-8'))
    source = source_of(src_index)

    # 版本 index：原样保留，改 chapters[].file 与 has_json
    vidx = json.loads(json.dumps(src_index))
    chapters = vidx.get('chapters') or []
    for c in chapters:
        f = str(c.get('file') or '%03d' % c['n'])
        stem = f[:-3] if f.endswith('.md') else f
        c['file'] = stem
        c['has_json'] = os.path.exists(os.path.join(a.src, stem + '.json'))
        if not os.path.exists(os.path.join(a.src, stem + '.md')):
            raise SystemExit(f'缺章文件：{stem}.md')
    vidx.pop('primary', None)
    n_ch = len(chapters)
    if n_ch == 0:
        raise SystemExit('chapters 为空，不收')

    s = src_index.get('source') or {}
    tq = src_index.get('text_quality') or {}
    entry = {
        'key': None, 'kind': 'transcription', 'label': LABEL.get(source, s.get('name') or source),
        'source': source, 'source_name': s.get('name') or LABEL.get(source, source),
        'source_url': s.get('url'), 'license': s.get('license'),
        'quality': tq.get('grade') or src_index.get('grade') or 'source', 'chapters_total': n_ch,
    }
    if not entry['license']:
        raise SystemExit('source.license 为空，不收')

    mpath = os.path.join(owner_dir, 'manifest.json')
    manifest = json.load(open(mpath, encoding='utf-8')) if os.path.exists(mpath) else {'id': oid, 'versions': []}
    vs = manifest['versions']
    used = {v['key'] for v in vs} | {n for n in (os.listdir(owner_dir) if os.path.isdir(owner_dir) else [])}

    moves = []
    if not vs:
        entry['key'] = 'default'
        new_versions = [entry]
    else:
        cur = vs[0]
        assert cur['key'] == 'default'
        if rank(source, n_ch) < rank(cur['source'], cur['chapters_total']):
            k = next_key(cur['source'], used)
            moves.append((os.path.join(owner_dir, 'default'), os.path.join(owner_dir, k)))
            cur = dict(cur, key=k)
            entry['key'] = 'default'
            new_versions = [entry, cur] + vs[1:]
        else:
            entry['key'] = next_key(source, used)
            new_versions = vs + [entry]
    manifest['versions'] = new_versions
    dest = os.path.join(owner_dir, entry['key'])

    print(f"{oid}: 加 {source}（{n_ch} 章）→ key={entry['key']}" + (f'；原 default 挪到 {os.path.basename(moves[0][1])}' if moves else ''))
    if a.dry_run:
        return
    for src_d, dst_d in moves:
        os.rename(src_d, dst_d)
    os.makedirs(dest)
    for name in os.listdir(a.src):
        if name == 'index.json':
            continue
        p = os.path.join(a.src, name)
        (shutil.copytree if os.path.isdir(p) else shutil.copy2)(p, os.path.join(dest, name))
    write_json(os.path.join(dest, 'index.json'), vidx)
    write_json(mpath, manifest)


if __name__ == '__main__':
    main()
