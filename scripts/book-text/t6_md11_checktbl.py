#!/usr/bin/env python3
"""F-MD-11 真候选（排除字书／音韵用语后）的「核图表」：每处给 Work 题名、版本来源、章、行号、上下文，供 CV 侧对书影核字。
只读。用法：t6_md11_checktbl.py <book-text根> <输出md> <输出csv>"""
import sys, os, glob, json, re, csv
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '项目进展', '古籍文本', 'scripts')
sys.path.insert(0, os.path.abspath(HERE))
import validate_text_format as V
from zi_convert import classify
root, outmd, outcsv = sys.argv[1:4]
rows = []
for f in sorted(glob.glob(f'{root}/Work/*/*/*/*/*/[0-9][0-9][0-9].md') + glob.glob(f'{root}/Book/*/*/*/*/*/[0-9][0-9][0-9].md')):
    text = open(f, encoding='utf-8').read(); masked = V.mask_inert(text)
    p = os.path.relpath(f, root).split('/')
    ent = os.path.join(root, *p[:5]); mf = os.path.join(ent, 'manifest.json')
    try: man = json.load(open(mf, encoding='utf-8'))
    except Exception: man = {}
    ver = next((v for v in man.get('versions', []) if v.get('key') == p[5]), {})
    title = man.get('title') or man.get('name') or ''
    if not title:
        g = glob.glob(f'/home/user/open-guji/book-index/Work/{p[4][-3]}/{p[4][-2]}/{p[4][-1]}/{p[4]}-*.json')
        if g: title = os.path.basename(g[0])[len(p[4]) + 1:-5]
    cur = 0
    for content in V.iter_jz_spans(masked):
        zc = classify(content)
        i = text.find('<' + content + '>', cur)
        if i < 0: i = text.find(content, cur)
        cur = i + 1 if i >= 0 else cur
        if zc.kind not in ('ids', 'nested-ids') or V._ZI_LEXICON_RE.search(content): continue
        line = text.count('\n', 0, i) + 1
        ctx = text[max(0, i - 14): i + len(content) + 16].replace('\n', ' ')
        rows.append(dict(work=p[4], title=title, version=p[5], label=ver.get('label') or ver.get('source_name') or '', src=ver.get('source') or '',
                         url=ver.get('source_url') or '', chapter=p[6][:3], line=line, note=content, candidate=zc.notation, context=ctx))
with open(outcsv, 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
L = ['# F-MD-11 核图表（133 处疑似组字）', '',
     f'> 生成：`scripts/book-text/t6_md11_checktbl.py`，book-text main；真候选 {len(rows)} 处（已排除字书／音韵用语）。**只读，没有改任何数据。**',
     '> 用途：这些 `<上X下Y>` 是转录者对"缺字／难识字"的部件描述，写成了夹注。要由 CV 侧对书影核出到底是哪个字（或确认确实无字可定）。',
     '> 注意：这些条目的来源是 kanripo／维基／识典转录，不是我们 original 版；**能否核图取决于该版本有没有可对的书影**（表中"版本来源"列；没有 URL 的需先找底本）。', '',
     '| # | Work | 版本 | 来源 | 章 | 行 | 夹注 | 候选 :zi | 上下文 |', '|--|--|--|--|--|--|--|--|--|']
for n, r in enumerate(rows, 1):
    L.append(f"| {n} | `{r['work']}` {r['title'][:12]} | {r['version']} | {r['label'][:14] or r['src'][:14]} | {r['chapter']} | {r['line']} | `<{r['note']}>` | `{r['candidate']}` | {r['context']} |")
open(outmd, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print(len(rows))
