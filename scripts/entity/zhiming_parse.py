#!/usr/bin/env python3
"""职名页结构化（GUJI-378／GUJI-138）：每列切成 〔官衔串｜臣｜姓名〕。

用法：
  zhiming_parse.py <default 目录> <册号如 001> <起页> <止页> [--out 结果.tsv] [--min-name 2] [--max-name 4]

输入：<default>/NNN.char.json（格号 页:列:格，夹注格带 a／b 后缀）＋ NNN.cord.json（每页 cells[].box=[x,y,w,h]，用来比字宽）。
只读，不改任何文件。输出 TSV 列：
  page col n_cells 官衔串 姓名串 起格 臣格 姓名起格 姓名止格 off_臣 把握 备注
读序：就是 char.json 里该列 cells 的出现顺序（夹注 a 右行在前、b 左行在后，文件序已是读序）。
把握：高＝臣在末尾「臣＋2–4 字」且姓名格全无 a／b 后缀、臣的字宽明显小于姓名字宽；
      中＝结构对但字宽/后缀证据不全；低＝只能按位置切；待人核＝切不出（无臣、姓名过短过长、含缺字□）。
交接：定稿导出时必须附 NNN.cord.json，否则无字宽证据、全部把握只能判低。
以「職名」结尾的列（如「…諸臣職名」）一律标 heading。
无「臣」的列标 heading（类目、总裁官等标题列）。不猜：证据不够就标待人核。
"""
import argparse
import json
import os
import statistics
import sys

SUFFIX = ('a', 'b')


HEADING_TAILS = ('諸臣職名', '臣職名', '職名')


def is_small(anchor):
    return anchor[-1] in SUFFIX


def load_cells(default_dir, vol):
    char = json.load(open(os.path.join(default_dir, f'{vol}.char.json'), encoding='utf-8'))
    box = {}
    cp = os.path.join(default_dir, f'{vol}.cord.json')
    if os.path.exists(cp):
        for pg in json.load(open(cp, encoding='utf-8')).get('pages', []):
            for c in pg.get('cells', []):
                box[c['a']] = c.get('box')
    flat = {}
    n = 0
    for pg in char['pages']:
        for col in pg['columns']:
            for ce in col['cells']:
                flat[ce['a']] = n
                n += 1
    return char, box, flat


def parse_column(cells, box, min_name=2, max_name=4):
    """cells: [{'a','c',(lacuna)}]，返回 dict。"""
    s = ''.join(('□' if c.get('lacuna') else c['c']) for c in cells)
    idx = [i for i, c in enumerate(cells) if c['c'] == '臣' and not c.get('lacuna')]
    if s.endswith(HEADING_TAILS):
        return {'kind': 'heading', 'text': s, 'conf': '', 'note': '标题（諸臣職名／職名）'}
    if not idx:
        return {'kind': 'heading', 'text': s, 'conf': '', 'note': '无臣'}
    i = idx[-1]
    name = cells[i + 1:]
    if not (min_name <= len(name) <= max_name):
        return {'kind': '待人核', 'text': s, 'conf': '待人核', 'note': f'末个臣后 {len(name)} 字，不在 {min_name}–{max_name}'}
    if any(c.get('lacuna') for c in name):
        return {'kind': '待人核', 'text': s, 'conf': '待人核', 'note': '姓名含缺字'}
    head = cells[:i]
    note = []
    conf = '高'
    if any(is_small(c['a']) for c in name):
        conf = '低'
        note.append('姓名格带夹注后缀')
    w = lambda c: (box.get(c['a']) or [0, 0, 0, 0])[2]
    wn = [w(c) for c in name if w(c)]
    wc = w(cells[i])
    if not wn or not wc:
        conf = '低' if conf == '高' else conf
        note.append('缺字宽证据')
    elif wc >= 0.85 * statistics.median(wn):
        conf = '中' if conf == '高' else conf
        note.append('臣字宽与姓名接近')
    return {'kind': 'entry', 'head': ''.join(c['c'] for c in head), 'name': ''.join(c['c'] for c in name),
            'a_head0': head[0]['a'] if head else '', 'a_chen': cells[i]['a'],
            'a_name0': name[0]['a'], 'a_name1': name[-1]['a'], 'n_head': len(head),
            'conf': conf, 'note': ';'.join(note), 'text': s, 'idx_chen': i}


def run(default_dir, vol, p0, p1, min_name=2, max_name=4):
    char, box, flat = load_cells(default_dir, vol)
    out = []
    for pg in char['pages']:
        if not (p0 <= pg['page'] <= p1):
            continue
        for col in pg['columns']:
            cells = col['cells']
            if not cells:
                continue
            r = parse_column(cells, box, min_name, max_name)
            r.update(page=pg['page'], col=col['col'], n_cells=len(cells))
            if r['kind'] == 'entry':
                r['off_chen'] = flat[r['a_chen']]
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('default'); ap.add_argument('vol'); ap.add_argument('p0', type=int); ap.add_argument('p1', type=int)
    ap.add_argument('--out'); ap.add_argument('--min-name', type=int, default=2); ap.add_argument('--max-name', type=int, default=4)
    a = ap.parse_args()
    rows = run(a.default, a.vol, a.p0, a.p1, a.min_name, a.max_name)
    f = open(a.out, 'w', encoding='utf-8', newline='') if a.out else sys.stdout
    f.write('page\tcol\tn_cells\t类\t官衔串\t姓名串\t起格\t臣格\t姓名起格\t姓名止格\toff_臣\t把握\t备注\n')
    for r in rows:
        if r['kind'] == 'entry':
            f.write('\t'.join(map(str, [r['page'], r['col'], r['n_cells'], 'entry', r['head'], r['name'], r['a_head0'], r['a_chen'],
                                        r['a_name0'], r['a_name1'], r['off_chen'], r['conf'], r['note']])) + '\n')
        else:
            f.write('\t'.join(map(str, [r['page'], r['col'], r['n_cells'], r['kind'], r['text'], '', '', '', '', '', '', r['conf'], r['note']])) + '\n')
    cnt = {}
    for r in rows:
        k = r['kind'] if r['kind'] != 'entry' else '条:' + r['conf']
        cnt[k] = cnt.get(k, 0) + 1
    print(json.dumps({'列数': len(rows), '分布': cnt}, ensure_ascii=False), file=sys.stderr)


if __name__ == '__main__':
    main()
