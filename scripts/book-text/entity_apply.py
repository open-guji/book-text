#!/usr/bin/env python3
"""P2 步 4：把 漏标处置.tsv 里的「补标」写进 original 实体线（默认干跑，--apply 才写）。
用法：entity_apply.py <book-text根> <book-index根> <专名匹配目录> [--book 96mid1ogzk] [--vol 002 003] [--apply]
  N5：entity_apply.py ... --rematch --name-index 名索引.tsv [--log x.tsv] [--apply]（new_candidate 在库恰好一条才回挂）
  读 <专名匹配目录>/漏标候选-册NNN.tsv（offset/len/anchor）＋ 漏标处置.tsv（decision=补标）。
  新实体：id 接着本册最大号顺排；source=补标:N8|N9；target 有 target_id（或单一 match_id）→ matched，否则 new_candidate。
  校验：候选文字必须等于 char 拼接串 [offset, offset+len)，且不与现有 span 重叠；否则报错不写。
  写完重算 stats；实体按 span 起点排序但不改已有 id。"""
import argparse, collections, csv, glob, json, sys
from pathlib import Path

TYPE = {'N8_person': 'people', 'N9_work': 'work'}
STAT = (('works', 'work'), ('people', 'people'), ('places', 'place'), ('offices', 'office'), ('dynasties', 'dynasty'), ('reigns', 'reign'))


def names(bi):
    pn, wt = {}, {}
    for f in glob.glob(str(Path(bi) / 'index/entities/*.json')):
        for k, v in json.load(open(f, encoding='utf-8')).items():
            pn[k] = v.get('primary_name', '')
    for f in glob.glob(str(Path(bi) / 'index/works/*.json')):
        for k, v in json.load(open(f, encoding='utf-8')).items():
            wt[k] = v.get('title', '')
    return pn, wt


def tsv(p):
    ls = [l.rstrip('\n').split('\t') for l in open(p, encoding='utf-8') if l.strip()]
    return [dict(zip(ls[0], r)) for r in ls[1:]]


def recount(en):
    E = en['entities']; st = en['stats']
    for key, ty in STAT:
        st[key] = sum(1 for x in E if x['type'] == ty)
    st['total_entities'] = len(E)
    for key, sv in (('matched', 'matched'), ('ambiguous', 'ambiguous'), ('new_candidates', 'new_candidate')):
        st[key] = sum(1 for x in E if x['target'].get('status') == sv
                      or (sv == 'matched' and x['target'].get('status') == 'matched_multi'))  # 多链接也算已链接


# ---- N5：对现库重对 new_candidate（--rematch）----
MAN = str.maketrans({'𫎇': '蒙', '𠮓': '變', '𠈁': '侂', '彞': '彝', '頴': '穎', '埀': '垂', '𡚁': '弊', '㕘': '參', '葢': '蓋', '畧': '略',
                     '㫖': '旨', '叅': '參', '淸': '清', '尙': '尚', '郞': '郎', '戸': '戶', '歴': '曆', '秘': '祕', '𢰅': '撰', '䟦': '跋',
                     '絜': '潔', '鈎': '鉤', '註': '注', '内': '內', '爲': '為', '僞': '偽', '颕': '颖', '冑': '胄', '愼': '慎', '縕': '蘊',
                     '𥳑': '簡', '𢑴': '彝', '眞': '真', '啟': '啓', '顔': '顏', '卭': '邛'})


def make_norm():
    try:
        from opencc import OpenCC
        t2s = OpenCC('t2s')
        return lambda x: t2s.convert(x.translate(MAN)).translate(MAN)
    except ImportError:
        return lambda x: x.translate(MAN)


def load_names(bi_tsv):
    """名索引.tsv（type／entity_id／canonical_name）→ {norm名: [(id, type)]}；promotions 在 TSV 生成时已按正式 id 取名，这里不再跳转。"""
    norm = make_norm(); idx = collections.defaultdict(list)
    for r in tsv(bi_tsv):
        idx[(('work' if r['type'] == 'work' else 'people'), norm(r['canonical_name']))].append(r['entity_id'])
    return norm, idx


# 避讳／同名护栏：用这些字对不上的异体不自动回挂（玄↔元、弘↔宏、丘↔邱 等，如「鄭元」≠鄭玄 要看上下文），留给 P3
AVOID = set('玄元弘宏丘邱胤允曆歷')
MINLEN = {'people': 2, 'work': 3}


def avoid_hit(text, canon):
    return len(text) == len(canon) and any(a != b and (a in AVOID or b in AVOID) for a, b in zip(text, canon))


def rematch(a):
    norm, idx = load_names(a.name_index)
    base = glob.glob(str(Path(a.bt) / f'*/*/*/*/{a.book}/default'))[0]
    log = []
    for vol in a.vol:
        ef = f'{base}/{vol}.entity.json'; en = json.load(open(ef, encoding='utf-8'))
        pn, wt = names(a.bi)
        for e in en['entities']:
            if e['target'].get('status') != 'new_candidate' or e['type'] not in ('people', 'work'):
                continue
            ids = idx.get((e['type'], norm(e['text'])), []) if len(e['text']) >= MINLEN[e['type']] else []
            if len(ids) == 1 and avoid_hit(e['text'], (wt if e['type'] == 'work' else pn).get(ids[0]) or e['text']):
                log.append((vol, e['id'], e['type'], e['text'], 'AVOID', ids[0], (wt if e['type'] == 'work' else pn).get(ids[0]) or ''))
            elif len(ids) == 1:   # 恰好一条才回挂；0 条留 new_candidate，多条留给 P3
                tid = ids[0]; canon = (wt if e['type'] == 'work' else pn).get(tid) or e['text']
                kind = 'EXACT' if canon == e['text'] else 'VARIANT'
                tg = {'status': 'matched', 'entity_id': tid, 'canonical_name': canon, 'href': f"book-index://{'Work' if e['type'] == 'work' else 'Entity'}/{tid}"}
                if kind == 'VARIANT':
                    tg['note'] = f"异体归一：原文「{e['text']}」＝库名「{canon}」"
                log.append((vol, e['id'], e['type'], e['text'], kind, tid, canon))
                if a.apply:
                    e['target'] = tg
            elif len(ids) > 1:
                log.append((vol, e['id'], e['type'], e['text'], 'MULTI', '|'.join(ids), ''))
        if a.apply:
            recount(en)
            with open(ef, 'w', encoding='utf-8') as f:
                json.dump(en, f, ensure_ascii=False, indent=2); f.write('\n')
    c = collections.Counter((x[2], x[4]) for x in log)
    print('rematch', dict(c), '（已写）' if a.apply else '（干跑）')
    if a.log:
        with open(a.log, 'w', encoding='utf-8') as f:
            f.write('vol\tentity\ttype\ttext\tkind\ttarget_id\tcanonical\n')
            for x in log: f.write('\t'.join(x) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bt'); ap.add_argument('bi'); ap.add_argument('dir')
    ap.add_argument('--book', default='96mid1ogzk'); ap.add_argument('--vol', nargs='*', default=['002', '003'])
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--rematch', action='store_true', help='N5：对现库重对 new_candidate（需 --name-index）')
    ap.add_argument('--name-index', default=None); ap.add_argument('--log', default=None)
    a = ap.parse_args()
    if a.rematch:
        rematch(a); return
    pn, wt = names(a.bi)
    dec = {r['cand_id']: r for r in tsv(Path(a.dir) / '漏标处置.tsv')}
    base = glob.glob(str(Path(a.bt) / f'*/*/*/*/{a.book}/default'))[0]
    bad = 0
    for vol in a.vol:
        cands = [c for c in tsv(Path(a.dir) / f'漏标候选-册{vol}.tsv') if dec.get(c['cand_id'], {}).get('decision') == '补标']
        ef = f'{base}/{vol}.entity.json'
        en = json.load(open(ef, encoding='utf-8')); E = en['entities']
        cells = [c for p in json.load(open(f'{base}/{vol}.char.json'))['pages'] for col in p['columns'] for c in col['cells']]
        text = ''.join(c['c'] for c in cells)
        used = bytearray(len(text))
        for e in E:
            for j in range(e['span']['start_offset'], e['span']['end_offset']):
                used[j] = 1
        nid = max(int(e['id'][1:]) for e in E)
        add = []
        for c in cands:
            o, L = int(c['offset']), int(c['len'])
            ty = TYPE[c['kind']]
            if text[o:o + L] != c['text'] or cells[o]['a'] != c['anchor']:
                print('✗ 文字／锚点对不上', c['cand_id'], c['text'], text[o:o + L]); bad += 1; continue
            if any(used[o:o + L]):
                print('✗ 与现有 span 重叠', c['cand_id'], c['text']); bad += 1; continue
            for j in range(o, o + L):
                used[j] = 1
            tid = dec[c['cand_id']]['target_id'].strip()
            if not tid and not c['match_id'].startswith('ambig:') and c['match_id']:
                tid = c['match_id']
            nid += 1
            if tid:
                canon = (wt if ty == 'work' else pn).get(tid)
                if not canon:
                    print('✗ target_id 不在库里', c['cand_id'], tid); bad += 1; continue
                tg = {'status': 'matched', 'entity_id': tid, 'canonical_name': canon,
                      'href': f"book-index://{'Work' if ty == 'work' else 'Entity'}/{tid}"}
                if canon != c['text']:
                    tg['note'] = f"补标：原文「{c['text']}」＝库名「{canon}」"
            elif c['match_id'].startswith('ambig:'):   # 同名多条：写 ambiguous，交 P3 消歧
                cs = [i for i in c['match_id'][6:].split('|') if i]
                tg = {'status': 'ambiguous', 'canonical_name': c['text'],
                      'candidates': [{'entity_id': i, 'canonical_name': (wt if ty == 'work' else pn).get(i, c['text'])} for i in cs]}
            else:
                tg = {'status': 'new_candidate', 'canonical_name': c['text']}
            add.append({'id': f'e{nid:05d}', 'type': ty, 'text': c['text'],
                        'anchor': {'start': cells[o]['a'], 'end': cells[o + L - 1]['a']},
                        'span': {'start_offset': o, 'end_offset': o + L}, 'target': tg,
                        'source': '补标:' + ('N8' if ty == 'people' else 'N9')})
        print(vol, '补标', len(cands), '→ 新增', len(add), '其中 matched', sum(1 for x in add if x['target']['status'] == 'matched'))
        if a.apply and not bad:
            E.extend(add); E.sort(key=lambda e: e['span']['start_offset']); recount(en)
            with open(ef, 'w', encoding='utf-8') as f:
                json.dump(en, f, ensure_ascii=False, indent=2); f.write('\n')
    if bad:
        print('有', bad, '处错误，未写任何文件'); sys.exit(1)
    print('已写' if a.apply else '干跑完成（未写）')


if __name__ == '__main__':
    main()
