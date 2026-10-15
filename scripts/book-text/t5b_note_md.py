#!/usr/bin/env python3
"""T5b 记法半收尾（overview#535/#543）：宋史藝文志 d59f2gdp696q
  ① md：夹注 `（（…））` → `<…>`（spec/03 F-MD-01：宋史的 `（（…））` 是存量允许，随改版转）；
     4 处夹注「开括号在上一段末尾、夹注正文整段在下一段」（017/022/034/042 各 1）按 json 的位置处理——
     开括号挪到下一段段首，使 `<…>` 同段闭合；012、039 各 1 处是**真跨段**的夹注（开括号后还有字、
     夹注正文被抬头书名拆在几段里），不动位置，只换括号字符，列入待审。
  ② json：017/022/034 三章 sections[].content 里剩下的 `⟨…⟩` → `<…>`（只动 content；author_info 等其他字段不动，同 #55）。
核对：转后每章 md 各段的 `<…>` 多重集 == json 对应条目 content 的 `<…>` 多重集；括号逐段平衡。命中数断言。
用法：t5b_note_md.py <book-text根> [--apply]"""
import glob, json, re, sys, collections
root = sys.argv[1]; apply = '--apply' in sys.argv
(d,) = glob.glob(f'{root}/Work/*/*/*/d59f2gdp696q/default')
CROSS = re.compile(r'（（(\n\n)([^\n]*））)(?=\n|$)')   # 上段末尾的 （（ + 空行 + 下段以 ）） 结尾
def blocks(md): return [b for b in re.split(r'\n\s*\n', md) if b.strip() and not b.lstrip().startswith('#')]
tot = collections.Counter(); outs = {}
for f in sorted(glob.glob(d + '/[0-9][0-9][0-9].md')):
    ch = f[-6:-3]; t = open(f, encoding='utf-8').read()
    # ① 跨段
    def fix(m):
        nxt = m.group(2)
        if '（（' in nxt: return m.group(0)       # 下段自己也有开括号，不是单纯跨段
        tot['cross_md'] += 1
        return m.group(1) + '（（' + nxt
    t2 = CROSS.sub(fix, t)
    n_open, n_close = t2.count('（（'), t2.count('））'); assert n_open == n_close, (ch, n_open, n_close)
    for i, ln in enumerate(t2.split('\n'), 1):
        if ln.count('（（') != ln.count('））'):
            assert ch in ('012', '039'), ('逐行不平衡', ch, ln[:50]); tot['genuine_span_lines'] += 1
    t3 = t2.replace('（（', '<').replace('））', '>'); tot['md_pairs'] += n_open
    # json 核对 + 017/022/034 转换
    jf = f[:-3] + '.json'; raw = open(jf, encoding='utf-8').read(); j = json.loads(raw); nl = raw.endswith('\n')
    assert json.dumps(j, indent=2, ensure_ascii=False) + ('\n' if nl else '') == raw
    jc = 0
    for s in j['sections']:
        c = s.get('content')
        if c and ('⟨' in c or '⟩' in c):
            assert ch in ('017', '022', '034'), (ch, c[:30])
            s['content'] = c.replace('⟨', '<').replace('⟩', '>'); jc += c.count('⟨')
    tot['json_pairs'] += jc
    jb = [s for s in j['sections'] if s.get('type') == 'book']; mb = blocks(t3)
    assert len(jb) == len(mb), (ch, len(jb), len(mb))
    for s, b in zip(jb, mb):
        if ch in ('012', '039'): continue          # 真跨段夹注，json／md 本就拆法不同，见头注
        a = collections.Counter(re.findall(r'<[^<>]*>', s['content'])); bb = collections.Counter(re.findall(r'<[^<>]*>', b))
        assert a == bb, ('夹注多重集不一致', ch, s['content'][:40], list((a - bb).items())[:2], list((bb - a).items())[:2])
    outs[f] = t3
    if jc: outs[jf] = json.dumps(j, indent=2, ensure_ascii=False) + ('\n' if nl else '')
print(dict(tot), '写', len(outs), '个文件')
assert tot['cross_md'] == 4 and tot['genuine_span_lines'] == 4, ('跨段数应为 4＋真跨段 4 行', dict(tot))
if apply:
    for p, s in outs.items(): open(p, 'w', encoding='utf-8').write(s)
    print('已写')
