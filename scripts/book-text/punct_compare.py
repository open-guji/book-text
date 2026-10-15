#!/usr/bin/env python3
"""四庫總目 original 标点线 ↔ 维基文库带标点本 逐缝对照（只读）。

用法：punct_compare.py <册 002|003> <块名 如 易類一> <维基卷档,...> [--out 报告.md]
以字序列做 difflib 对齐；对齐上的相邻字之间（缝）比较标点串。
文字差异（replace/insert/delete）单列，供回书影核（分类③），不进标点统计。
《》另算一列（属专名）。
"""
import sys, re, json, difflib, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__))); sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
import original_char as C
D = '/home/user/book-text/Book/g/z/k/96mid1ogzk/default'
HEAD = ('經部總敘','經部一','易類一','經部二','易類二','經部三','易類三','經部四','易類四','經部五','易類五')
OPEN = set('《「『（(〈'); CLOSE = set('》」』）)〉')
PUNCT = set('，。、：；？！《》「」『』（）“”‘’·')
NORM = {'“':'「','”':'」','‘':'『','’':'』'}

def ours(vol, name):
    ch = json.load(open(f'{D}/{vol}.char.json', encoding='utf-8')); pu = json.load(open(f'{D}/{vol}.punct.json', encoding='utf-8'))
    slots = C.char_slots(ch); pos = {a: i for i, (a, c) in enumerate(slots)}; text = ''.join(c for a, c in slots)
    brk = sorted(pos[p['anchor']] for p in pu['punctuations'] if p['kind'] == 'break')
    paras = []; s = 0
    for b in brk: paras.append((s, b)); s = b + 1
    if s < len(slots): paras.append((s, len(slots)-1))
    blk = None; sel = []
    for (s, e) in paras:
        t = text[s:e+1]
        if t in HEAD: blk = t; continue
        if blk in name.split('+'): sel.append((s, e))
    gaps = collections.defaultdict(str)   # gap index g: 在 slot g 之前（g 即 slot 号）
    for p in pu['punctuations']:
        if p['kind'] == 'break': continue
        i = pos[p['anchor']]; g = i if p['pos'] == 'before' else i + 1
        gaps[g] += p['mark']
    chars = []; gapl = []; anch = []
    for (s, e) in sel:
        for i in range(s, e+1):
            chars.append(slots[i][1]); anch.append(slots[i][0])
            gapl.append(gaps.get(i+1, '') if i < e else '')   # 段尾缝不比
        if gapl: gapl[-1] = gaps.get(e+1, '')
    # 缝 k = 第 k 字之后；开括号在下一字前的并入前一字之后（与维基同法）
    # 重做：以「字后」为缝，开标记 before 并入前一字后（同段内）
    gp = [''] * len(chars)
    idx = 0
    for (s, e) in sel:
        for i in range(s, e+1):
            gp[idx] = (gaps.get(i+1, '') if i < e else gaps.get(i+1, ''))
            idx += 1
    loc = {a: k for k, a in enumerate(anch)}
    en = json.load(open(f'{D}/{vol}.entity.json', encoding='utf-8'))['entities']
    ents = []
    for x in en:
        a, b = x['anchor']['start'], x['anchor']['end']
        if a in loc and b in loc:
            ents.append((loc[a], loc[b], x['type'], x['target']['status'], x.get('id', '')))
    return chars, gp, anch, ents

def wiki(files):
    chars = []; gp = []; heads = []; sec = []; si = -1
    for f in files:
        t = open(f, encoding='utf-8').read()
        t = re.sub(r'\{\{[^}]*\}\}', '', t)
        t = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', t)
        t = re.sub(r"'''|<[^>]+>", '', t)
        for line in t.split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith('='):
                heads.append(line.strip('= ')); line = line.strip('= '); si += 1   # 标题当文字行，与我们的书名行相配
            for c in line:
                c = NORM.get(c, c)
                if c in PUNCT:
                    if gp: gp[-1] += c
                elif c.isspace(): continue
                else:
                    chars.append(c); gp.append(''); sec.append(si)
            if gp: gp[-1] += '\n'          # 行尾，不当标点；比较时去掉
    gp = [g.replace('\n', '') for g in gp]
    return chars, gp, sec, heads

VAR = {}
def main():
    vol, name, files = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
    out = sys.argv[sys.argv.index('--out')+1] if '--out' in sys.argv else None
    oc, og, oa, oents = ours(vol, name); wc, wg, wsec, wheads = wiki(files)
    # 旧式节：只有句号、几乎无逗号 → 不比标点
    sc = collections.defaultdict(collections.Counter)
    for c, g, s in zip(wc, wg, wsec):
        for m in g: sc[s][m] += 1
    old = {s for s, c in sc.items() if c['，'] + c['、'] + c['；'] + c['：'] == 0 and c['。'] >= 2}
    sty = {s: ('旧式' if s in old else '新式') for s in range(len(wheads))}
    # 对齐前先学异体：第一遍
    sm = difflib.SequenceMatcher(None, oc, wc, autojunk=False)
    pairs = collections.Counter()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'replace' and i2-i1 == j2-j1:
            for a, b in zip(oc[i1:i2], wc[j1:j2]): pairs[(a, b)] += 1
    WL = set('蓋變參內偽為略旨別既彞註閒徴刊穎祕渉'); var = {b: a for (a, b), n in pairs.items() if n >= 2 and b in WL}
    wn = [var.get(c, c) for c in wc]
    sm = difflib.SequenceMatcher(None, oc, wn, autojunk=False)
    rows = []; txt = []; eq = 0; nold = [0]
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2-i1):
                i, j = i1+k, j1+k; eq += 1
                if k == i2-i1-1 and i2 < len(oc): pass
                a, b = og[i], wg[j]
                if wsec[j] in old: nold[0] += 1; continue
                rows.append((i, j, a, b))
        else:
            txt.append((tag, i1, i2, j1, j2))
    def spans(ch, gp_, skip=lambda k: False):
        res = []; st = []
        for k in range(len(ch)):
            # 开标记在「上一字之后」的缝里（同缝内多个标记按序）；闭标记也在字后
            pass
        return res
    # 《》span：开 = 缝里的《（属下一字起），闭 = 字后的》
    def book_spans(ch, gp_):
        res = []; stack = []
        for k in range(len(ch)):
            for m in gp_[k]:
                if m == '《': stack.append(k+1)
                elif m == '》' and stack: s0 = stack.pop(); res.append((s0, k))
        return res
    ob = book_spans(oc, og); wb = book_spans(wc, wg)
    i2j = {}; j2i = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal' or (tag == 'replace' and i2-i1 == j2-j1):
            for k in range(i2-i1): i2j[i1+k] = j1+k; j2i[j1+k] = i1+k
    wset = {(a, b) for a, b in wb}
    obm = set()
    for a, b in ob:
        if a in i2j and b in i2j: obm.add((i2j[a], i2j[b]))
    wonly = [(a, b) for a, b in wb if (a, b) not in obm]
    wmap = {}
    for a, b in ob:
        if a in i2j and b in i2j: wmap[(i2j[a], i2j[b])] = (a, b)
    oonly = [(a, b) for a, b in ob if not (a in i2j and b in i2j and (i2j[a], i2j[b]) in wset)]
    ent_at = collections.defaultdict(list)
    for (a, b, ty, stt, eid) in oents: ent_at[(a, b)].append((ty, stt))
    def oent_over(a, b):
        r = [(ty, stt, x1, x2) for (x1, x2, ty, stt, eid) in oents if not (x2 < a or x1 > b)]
        return r
    def seglen(i):
        # 我方在缝 i 之前/之后，到最近的非《》标点的距离
        def isp(k): return strip_books(og[k]) != ''
        l = 0
        k = i - 1
        while k >= 0 and not isp(k) and oa[k].split(':')[0] == oa[i].split(':')[0]: l += 1; k -= 1
        r = 0; k = i + 1
        while k < len(oc) and not isp(k) and oa[k].split(':')[0] == oa[i].split(':')[0]: r += 1; k += 1
        return l + 1, r + 1
    QT = set('「」『』《》')
    def autocls(i, sa, sb, ar='', br=''):
        a = set(sa); b = set(sb)
        q = set('「」『』：')
        core = lambda s: ''.join(c for c in s if c not in QT)
        if (set(ar) & set('「」『』')) and (set(br) & set('《》')) and core(ar) == core(br):
            return 'H引号↔书名号同位', '我方用「」标篇名／名目，维基用《》；风格差异，待 Maren 定统一'
        if sa == '' and '、' in sb and '》' in br and '《' in br:
            return 'H随书名号', '维基因把前后各标成《》才出顿号，是否补随专名线（§三）判'
        if (a | b) & set('（）·') and not (a & q):
            return 'E版本差异', '维基用（）/·，我方夹注与书名分隔另记'
        if (a | b) & q:
            nq = lambda s: ''.join(c for c in s if c not in '：')
            if nq(ar) == nq(br): return 'A冒号差', '引号前有无冒号，两可'
            c2 = lambda s: ''.join(c for c in s if c not in '：「」『』《》')
            qm = set('「」『』')
            if not (set(ar) & qm) and (set(br) & qm) and c2(ar) == c2(br): return 'D1维基有引号', '引文起讫，按引号规则（P8）判'
            if (set(ar) & qm) and not (set(br) & qm) and c2(ar) == c2(br): return 'D2我方有引号', '我方更细，不改'
            return 'D3引号其他', '人看'
        if sa == '' and '、' in sb: return 'C建议补顿号', '维基有并列顿号、我方无'
        if sa == '' : 
            l, r = seglen(i)
            return ('C建议补' if l + r >= 22 else 'C可不补'), f'邻句长 {l}+{r}'
        if sb == '':
            return ('B我方更细' if sa in ('、',) else 'B我有维基无'), ''
        if set(sa) <= set('，；。、') and set(sb) <= set('，；。、'): return 'A句读粗细', ''
        return 'F其他', '人看'
    def ctx(i, w=8): return ''.join(oc[max(0, i-w+1):i+1]) + '｜' + ''.join(oc[i+1:i+1+w])
    def strip_books(s): return ''.join(c for c in s if c not in '《》')
    diffs = [(i, j, a, b) for (i, j, a, b) in rows if a != b]
    d_pun = [(i, j, strip_books(a), strip_books(b), a, b) for (i, j, a, b) in diffs if strip_books(a) != strip_books(b)]
    # ---- 引号候选（#535 引号政策：直接引语整句用「」；短语引、篇名不加引号，篇名用《》）----
    if '--quote-json' in sys.argv:
        def qspans(ch, gp_, op, cl):
            res = []; st = {'「': [], '『': []}
            for k in range(len(ch)):
                for m in gp_[k]:
                    if m in op: st[m].append(k + 1)
                    elif m in cl:
                        o = '「' if m == '」' else '『'
                        if st[o]: s0 = st[o].pop(); res.append((s0, k, o, len(st['「']) if o == '「' else 1))
            return res
        wq = qspans(wc, wg, '「『', '」』'); oq = qspans(oc, og, '「『', '」』')
        oq_by = {(a, b): (o, d) for (a, b, o, d) in oq}
        cands = []; dbg = collections.Counter()
        for (a, b, o, d) in wq:
            dbg['wq'] += 1
            if d != 0 or o != '「' or a not in j2i or b not in j2i: continue
            dbg['mapped'] += 1
            ia, ib = j2i[a], j2i[b]
            inner = ''.join(oc[ia:ib + 1])
            intro = ''.join(oc[max(0, ia - 4):ia])
            if (ia, ib) in oq_by:
                dbg['both'] += 1; continue
            if any(m in '「」『』' for k in range(ia, ib + 1) for m in og[k]) or (ia > 0 and any(m in '「」『』' for m in og[ia - 1])):
                dbg['ours_has'] += 1; continue
            body_len = sum(1 for c in inner if c not in '，。、；：？！')
            kind = 'D直接引语' if (body_len >= 10 and re.search('[曰云稱謂載言序]', intro)) else 'D短语引'
            cands.append(dict(kind=kind, block=name, start=oa[ia], end=oa[ib], idx=[ia, ib], intro=intro, text=inner, wiki_open=o))
        hs = []
        for (a, b) in wb:
            if a in j2i and b in j2i and (j2i[a], j2i[b]) in oq_by:
                ia, ib = j2i[a], j2i[b]
                hs.append(dict(kind='H篇名改书名号', block=name, start=oa[ia], end=oa[ib], idx=[ia, ib], text=''.join(oc[ia:ib + 1]), our_open=oq_by[(ia, ib)][0]))
        qj = sys.argv[sys.argv.index('--quote-json') + 1]
        json.dump(dict(D=cands, H=hs), open(qj, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(dict(dbg)); print('quote candidates', collections.Counter(c['kind'] for c in cands), 'H', len(hs))
    # 错位：我方在 g 有标点而维基无、且维基在 g±1 有同种标点而我方无
    byi = {i: (sa, sb) for (i, j, sa, sb, a, b) in d_pun}
    shift = {}
    for i, (sa, sb) in byi.items():
        if sa and not sb:
            for d in (-1, 1):
                o = byi.get(i + d)
                if o and not o[0] and o[1] and set(o[1]) <= set('，。、；：？！') and set(sa) <= set('，。、；：？！') and not set(sb) & set('「」『』（）'):
                    shift[i] = i + d; shift[i + d] = i
    if '--pairs-json' in sys.argv:
        def seg(ch, gp_, c0, w=20):
            return ''.join(ch[k] + gp_[k] for k in range(max(0, c0 - w), min(len(ch), c0 + w + 1)))
        done = set(); prs = []
        for i, i2 in shift.items():
            key = tuple(sorted((i, i2)))
            if key in done: continue
            done.add(key)
            a = i2j.get(key[0])
            if a is None: continue
            b2 = i2j.get(key[1])
            prs.append(dict(block=name, anchors=[oa[key[0]], oa[key[1]]], idx=list(key), ours_gap=[og[key[0]], og[key[1]]], wiki_gap=[wg[a] if a is not None else None, wg[b2] if b2 is not None else None], ours=seg(oc, og, key[0]), wiki=seg(wc, wg, a)))
        json.dump(prs, open(sys.argv[sys.argv.index('--pairs-json') + 1], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    d_bk = [(i, j, a, b) for (i, j, a, b) in diffs if strip_books(a) == strip_books(b)]
    cat = collections.Counter()
    for i, j, sa, sb, a, b in d_pun:
        cat['我有维基无' if sb == '' else '维基有我无' if sa == '' else '两者不同'] += 1
    nmark = sum(1 for (_, _, a, b) in rows if strip_books(a) or strip_books(b))
    print('维基节：', [(h[:14], sty.get(k)) for k, h in enumerate(wheads)])
    print(f'我 {len(oc)} 字 / 维基 {len(wc)} 字；对齐相同 {eq}；文字差异段 {len(txt)}；异体学得 {dict(list(var.items())[:20])}')
    print('缝总数(有标点的缝)', nmark, '；标点差异', len(d_pun), dict(cat), '；《》差异', len(d_bk))
    if out:
        L = [f'# 标点对照：四庫總目 {vol} {name} ↔ 维基文库\n']
        L.append(f'- 我方 {len(oc)} 字；维基 {len(wc)} 字（已去标记、合并行）；对齐相同 {eq} 字；文字差异段 {len(txt)}。\n- 有标点的缝 {nmark}；标点差异 {len(d_pun)}（{dict(cat)}）；《》span 差异见 §三。\n- 异体（维基→我，白名单）：{var}\n- 维基「旧式（仅句号）」节 {len(old)}/{len(wheads)}，其字 {nold[0]} 不比标点。\n')
        L.append('\n## 一、标点差异（逐缝）\n\n| # | 锚点 | 上下文（｜为缝） | 我 | 维基 | 预分类 | 备注 |\n|--|--|--|--|--|--|--|')
        for n, (i, j, sa, sb, a, b) in enumerate(d_pun, 1):
            c = '我有维基无' if sb == '' else '维基有我无' if sa == '' else '两者不同'
            cl, nt = autocls(i, sa, sb, a, b)
            if i in shift and not ((set(a) | set(b)) & set('「」『』《》')): cl, nt = 'G错位疑', f'与缝{oa[shift[i]]}互为错位（我方标点疑偏一格）'
            L.append(f'| {n} | {oa[i]} | {ctx(i)} | {a or "∅"} | {b or "∅"} | {cl} | {nt} |')
        L.append('\n## 二、文字差异（回书影核，分类③）\n\n| # | 类 | 我方 | 维基 | 锚点 |\n|--|--|--|--|--|')
        for n, (tag, i1, i2, j1, j2) in enumerate(txt, 1):
            L.append(f'| {n} | {tag} | {"".join(oc[max(0,i1-3):i1])}[{"".join(oc[i1:i2])}]{"".join(oc[i2:i2+3])} | {"".join(wc[max(0,j1-3):j1])}[{"".join(wc[j1:j2])}]{"".join(wc[j2:j2+3])} | {oa[i1] if i1 < len(oa) else ""} |')
        # 《》span：同 / 边界不同(重叠) / 仅维基 / 仅我方；旧式节内的「仅我方」不比
        def ov(x, y): return not (x[1] < y[0] or y[1] < x[0])
        ob_w = [(i2j.get(a), i2j.get(b)) for a, b in ob]            # 我方 span 映到维基坐标
        same = [k for k, (a, b) in enumerate(ob) if (ob_w[k][0], ob_w[k][1]) in wset]
        sameW = {ob_w[k] for k in same}
        diffb = []; wonly2 = []; used_o = set()
        for (a, b) in wb:
            if (a, b) in sameW: continue
            hit = [k for k, (x, y) in enumerate(ob_w) if x is not None and y is not None and ov((a, b), (x, y)) and k not in same]
            if hit: diffb.append(((a, b), hit)); used_o.update(hit)
            else: wonly2.append((a, b))
        oonly2 = [k for k in range(len(ob)) if k not in same and k not in used_o]
        oonly_cmp = [k for k in oonly2 if ob_w[k][0] is None or wsec[ob_w[k][0]] not in old]
        oonly_old = [k for k in oonly2 if k not in oonly_cmp]
        def oents_str(a, b):
            es = oent_over(a, b)
            return '；'.join(f'{ty}:{stt}[{"".join(oc[x1:x2+1])}]' for ty, stt, x1, x2 in es) or '无'
        def wctx(a, b): return f'{"".join(wc[max(0,a-5):a])}《{"".join(wc[a:b+1])}》{"".join(wc[b+1:b+6])}'
        def octx(a, b): return f'{"".join(oc[max(0,a-5):a])}《{"".join(oc[a:b+1])}》{"".join(oc[b+1:b+6])}'
        L.append(f'\n## 三、《》span 对照（专名线）\n\n- 我方 {len(ob)}；维基 {len(wb)}；两边一致 {len(same)}；边界不同 {len(diffb)}；**仅维基 {len(wonly2)}**；**仅我方 {len(oonly_cmp)}**（另 {len(oonly_old)} 个落在维基旧式节，不可比）。\n')
        L.append('### 3a 仅维基有《》（漏标候选；看「我方该处实体」）\n\n| # | 书名 | 上下文 | 我方该处实体 | 锚点 |\n|--|--|--|--|--|')
        for n, (a, b) in enumerate(wonly2, 1):
            ia = j2i.get(a); ib = j2i.get(b)
            es = oents_str(ia, ib) if ia is not None and ib is not None else '无'
            L.append(f'| {n} | 《{"".join(wc[a:b+1])}》 | {wctx(a,b)} | {es} | {oa[ia] if ia is not None else ""} |')
        L.append('\n### 3b 边界不同\n\n| # | 维基 | 我方 | 上下文(维基) |\n|--|--|--|--|')
        for n, ((a, b), hit) in enumerate(diffb, 1):
            os_ = '、'.join('《' + ''.join(oc[ob[k][0]:ob[k][1]+1]) + '》' for k in hit)
            L.append(f'| {n} | 《{"".join(wc[a:b+1])}》 | {os_} | {wctx(a,b)} |')
        L.append('\n### 3c 仅我方有《》（维基新式节内无）\n\n| # | 书名 | 上下文 | 我方实体 | 锚点 |\n|--|--|--|--|--|')
        for n, k in enumerate(oonly_cmp, 1):
            a, b = ob[k]
            L.append(f'| {n} | 《{"".join(oc[a:b+1])}》 | {octx(a,b)} | {oents_str(a,b)} | {oa[a]} |')
        open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
main()
