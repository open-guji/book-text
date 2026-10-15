#!/usr/bin/env python3
"""T6：F-MD-11（疑似组字未转）全量清单，按 Work／章分组，附系统性模式统计。只出清单，不改数据。
用法：t6_md11_list.py <book-text根> <输出md>   （复用 validate_text_format 的 iter_jz_spans／mask_inert 与 zi_convert.classify）"""
import sys, os, glob, collections
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '项目进展', '古籍文本', 'scripts')
sys.path.insert(0, os.path.abspath(HERE))
import validate_text_format as V
from zi_convert import classify
root, out = sys.argv[1], sys.argv[2]
rows = []; excluded = 0
for f in sorted(glob.glob(f'{root}/Work/*/*/*/*/*/[0-9][0-9][0-9].md') + glob.glob(f'{root}/Book/*/*/*/*/*/[0-9][0-9][0-9].md')):
    text = open(f, encoding='utf-8').read(); masked = V.mask_inert(text)
    for seq, content in enumerate(V.iter_jz_spans(masked)):
        zc = classify(content)
        if zc.kind in ('ids', 'nested-ids'):
            if V._ZI_LEXICON_RE.search(content): excluded += 1; continue   # 字书／音韵用语，校验器已排除（T6）
            p = os.path.relpath(f, root).split('/')
            rows.append((p[4], p[5], p[6][:3], content, zc.kind, zc.notation, zc.reason))
by = collections.defaultdict(list)
for r in rows: by[(r[0], r[1])].append(r)
cont = collections.Counter(r[3] for r in rows); kinds = collections.Counter(r[4] for r in rows); works = collections.Counter(r[0] for r in rows)
L = ['# T6：F-MD-11 疑似组字未转清单（只留备查，不批量改）', '',
     f'> 生成：`scripts/book-text/t6_md11_list.py`，基线 book-text main；排除字书／音韵用语 **{excluded}** 处后，剩余真候选 **{len(rows)}** 处 / {len(by)} 个版本 / {len(works)} 个 Work（排除前共 {len(rows)+excluded} 处）。规则见 overview#535 Maren 10-10 裁⑤：清单入仓、按章分组；若看出系统性模式先报，不直接批量改。', '',
     '## 一、概览', '', f'- 档位：{dict(kinds)}', '- 命中最多的 Work：' + '、'.join(f'`{w}` {n}' for w, n in works.most_common(8)),
     '- 重复最多的写法（同一误排反复出现＝可能的系统性模式）：']
L += [f'  - `<{c}>` × {n}' for c, n in cont.most_common(15)]
L += ['', '## 二、按 Work／版本／章', '']
for (w, v), rs in sorted(by.items()):
    L.append(f'### `{w}` / `{v}`（{len(rs)} 处）'); L.append('')
    ch = collections.defaultdict(list)
    for r in rs: ch[r[2]].append(r)
    for c, items in sorted(ch.items()):
        L.append(f'- 第 {c} 章：' + '；'.join(f'`<{i[3]}>`→`{i[5]}`' for i in items))
    L.append('')
open(out, 'w', encoding='utf-8').write('\n'.join(L))
print('excluded',excluded,len(rows), len(by), len(works), kinds.most_common(), cont.most_common(5))
