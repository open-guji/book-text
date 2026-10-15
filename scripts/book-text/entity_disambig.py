#!/usr/bin/env python3
"""original 实体线 ambiguous 消歧（P3）。
--list  <book-text 根> [--book-index <根>]：导出待办 TSV（每条 ambiguous 一行，含候选；加 --book-index 则多两列：candidate_info＝朝代:撰人:是否著录于總目、context＝前后文各 20 字）
--apply <book-text 根> <消歧记录.tsv> [--dry-run]：按记录把 pick 行改 matched，pending 行保持 ambiguous
用法：python3 -I entity_disambig.py --list <book-text 根> > 消歧待办.tsv"""
import json, sys, glob, argparse
from pathlib import Path

BID = '96mid1ogzk'


def entity_files(root, bid):
    return sorted(glob.glob(str(root / f'*/*/*/*/{bid}/default/*.entity.json')))


def cand_info(bi, cid, typ):
    """候选的一句话：朝代；Work 另加撰人、是否著录于欽定四庫全書總目；people 加 cbdb。需 --book-index。"""
    for f in glob.glob(str(Path(bi) / ('index/works/*.json' if typ == 'work' else 'index/entities/*.json'))):
        d = json.load(open(f))
        if cid in d:
            v = d[cid]; break
    else:
        return '?'
    try:
        rec = json.load(open(Path(bi) / v['path']))
    except Exception:
        rec = {}
    if typ == 'work':
        au = rec.get('authors')
        au = '/'.join(a.get('name', '?') for a in au) if isinstance(au, list) else ''
        zm = '總目' if '欽定四庫全書總目' in str(rec.get('description', '')) else ''
        return f"{rec.get('dynasty') or v.get('dynasty') or '-'}:{au or '-'}:{zm}"
    return f"{v.get('dynasty') or '-'}:cbdb{v.get('cbdb_id') or '-'}"


def do_list(root, bid, bi=None):
    ctxcols = ['candidate_info', 'context'] if bi else []
    print('\t'.join(['entity_id', 'vol', 'type', 'text', 'anchor', 'candidates', 'candidate_names'] + ctxcols))
    for p in entity_files(root, bid):
        vol = Path(p).name.split('.')[0]
        T = ''
        if bi:
            cp = p.replace('.entity.json', '.char.json')
            T = ''.join(c['c'] for pg in json.load(open(cp))['pages'] for col in pg['columns'] for c in col['cells'])
        for x in json.load(open(p))['entities']:
            t = x['target']
            if t['status'] != 'ambiguous':
                continue
            cands = t.get('candidates', [])
            print('\t'.join([
                f"{vol}:{x['id']}", vol, x['type'], x['text'],
                f"{x['anchor']['start']}-{x['anchor']['end']}",
                '|'.join(c['entity_id'] for c in cands),
                '|'.join(c['canonical_name'] for c in cands),
            ] + ([' | '.join(cand_info(bi, c['entity_id'], 'work' if x['type'] == 'work' else 'people') for c in cands),
                  T[max(0, x['span']['start_offset'] - 20):x['span']['start_offset']] + '【' + x['text'] + '】' + T[x['span']['end_offset']:x['span']['end_offset'] + 20]] if bi else [])))


def do_apply(root, bid, tsv, dry):
    # 消歧记录列：entity_id type text candidates decision picked_id evidence by date
    recs = {}
    for line in open(tsv, encoding='utf-8'):
        f = line.rstrip('\n').split('\t')
        if len(f) < 6 or f[0] == 'entity_id':
            continue
        recs[f[0]] = f
    counts = {'pick': 0, 'pending': 0, 'bad': 0}
    touched = {}
    for p in entity_files(root, bid):
        vol = Path(p).name.split('.')[0]
        doc = json.load(open(p, encoding='utf-8'))
        changed = False
        for x in doc['entities']:
            key = f"{vol}:{x['id']}"
            r = recs.get(key)
            if not r or x['target']['status'] != 'ambiguous':
                continue
            decision, picked = r[4], r[5]
            cands = {c['entity_id']: c for c in x['target'].get('candidates', [])}
            if decision == 'pick':
                if picked not in cands:
                    counts['bad'] += 1
                    continue
                c = cands[picked]
                x['target'] = {'status': 'matched', 'entity_id': picked,
                               'canonical_name': c['canonical_name'],
                               'href': f"book-index://Work/{picked}",
                               'note': r[6]}
                counts['pick'] += 1
                changed = True
            elif decision == 'pending':
                counts['pending'] += 1
            else:
                counts['bad'] += 1
        if changed:
            touched[p] = doc
    print(json.dumps(counts, ensure_ascii=False))
    if dry:
        print(f"dry-run：将改 {len(touched)} 个文件，未写入")
        return
    for p, doc in touched.items():
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
    print(f"已写回 {len(touched)} 个文件")


if __name__ == '__main__':
    args = sys.argv[1:]
    dry = '--dry-run' in args
    args = [a for a in args if a != '--dry-run']
    mode, root = args[0], Path(args[1])
    if mode == '--list':
        bi = args[args.index('--book-index') + 1] if '--book-index' in args else None
        do_list(root, BID, bi)
    elif mode == '--apply':
        do_apply(root, BID, args[2], dry)
    else:
        sys.exit(__doc__)
