#!/usr/bin/env python3
"""entity 实体线后处理：把「修订判准（试点后）」N1–N7 里机器能做的规则做成可重跑脚本。

规则表驱动，每条规则一个函数，注册在 RULES：
  N1 删 work 误标：X彖／X象／大象／X象傳／爻位／卦名（引文定位，不是书）
  N2 删 work 误标：總敘「分爲十類，曰X」的十个类名
  N3 dynasty 误标：「唐會要／唐書／舊唐書…」里的「唐」→ 改标 work
  N4 异体归一后重对现库（需 --book-index）
  N6 同段全名后，后文简称（名／单姓）补标为同一实体（action＝add）
  N7 span 含朝代前缀（明劉日升／魏王弼）→ 拆成 dynasty＋人名

输入  *.entity.json（entities[] 的 text/span/target），文本取同目录同号的 *.char.json（各格 c 依序拼接，
      span 的 start_offset／end_offset 就是这条串里的下标）。
输出  同格式 entity.json（stats 重算）＋ postprocess_log.tsv：
      rule｜entity_id｜action｜before｜after       action ∈ delete／retype／split／add／rebind

用法  python3 entity_postprocess.py in.entity.json [--text in.char.json] [--punct in.punct.json] [--book-index <book-index 根>] [-o out.entity.json]
          [--log postprocess_log.tsv] [--rules N1,N2,N3,N7] [--dry-run]
      --dry-run 只出 log、不写 -o。
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

# ── 常量表 ───────────────────────────────────────────────────────
HEXAGRAMS = (
    '乾坤屯蒙需訟師比小畜履泰否同人大有謙豫隨蠱臨觀噬嗑賁剝復无妄大畜頤大過坎離'
    '咸恆遯大壯晉明夷家人睽蹇解損益夬姤萃升困井革鼎震艮漸歸妹豐旅巽兌渙節中孚小過既濟未濟'
)
# 六十四卦名（按字面切；双字名单列）
HEX_NAMES = [
    '乾', '坤', '屯', '蒙', '需', '訟', '師', '比', '小畜', '履', '泰', '否', '同人', '大有', '謙', '豫',
    '隨', '蠱', '臨', '觀', '噬嗑', '賁', '剝', '復', '无妄', '大畜', '頤', '大過', '坎', '離', '咸', '恆',
    '遯', '大壯', '晉', '明夷', '家人', '睽', '蹇', '解', '損', '益', '夬', '姤', '萃', '升', '困', '井',
    '革', '鼎', '震', '艮', '漸', '歸妹', '豐', '旅', '巽', '兌', '渙', '節', '中孚', '小過', '既濟', '未濟',
]
HEX_RE = '|'.join(sorted(map(re.escape, HEX_NAMES), key=len, reverse=True))

# 總敘「分爲十類」的十个类名
CATEGORY_NAMES = {'易', '書', '詩', '禮', '春秋', '孝經', '五經總義', '四書', '樂', '小學'}
CATEGORY_ANCHOR = '分爲十類'
CATEGORY_WINDOW = 90   # 「分爲十類」之后多少字内算类名枚举

# 朝代前缀：unambiguous 组不会是常见姓；ambiguous 组（魏周唐宋元金吳梁陳齊）需旁证才拆
DYN_UNAMBIGUOUS = ['北宋', '南宋', '東漢', '西漢', '後漢', '北齊', '南齊', '後魏', '北魏', '前秦', '後周',
                   '後唐', '後晉', '後梁', '東晉', '西晉', '明', '漢', '晉', '隋', '遼', '清', '秦', '蜀']
DYN_AMBIGUOUS = ['魏', '周', '唐', '宋', '元', '金', '吳', '梁', '陳', '齊']

# 人工确认过「朝代＋人名」的歧义前缀写法（库里 canonical 把朝代并进了名字）
KNOWN_DYN_PREFIXED = {'魏王弼'}

# N4 异体归一：用 entity_missing.py 的 FOLD（逐字映射，长度不变，只用于查键，原文字符不动），不另写一份
sys.path.insert(0, str(Path(__file__).resolve().parent))   # python3 -I 不带脚本目录
from entity_missing import fold as _fold  # noqa: E402

# 判准 N4 列了、但 entity_missing.FOLD 没收的三个生僻异体（SMP 字，试点里导致 work／人名落空）
_EXTRA = str.maketrans('𫎇𠮓𠈁', '蒙變侂')


def norm_variant(s):
    return _fold(s).translate(_EXTRA)


N1_PATTERNS = [
    # 卦名＋卦／彖／象…（乾卦、震彖、賁大象、坤象傳、乾卦彖傳）；单独的卦名不删（可能是书名简称）
    re.compile(r'^(%s)(卦|卦彖傳|彖|象|大象|彖傳|象傳|大象傳)$' % HEX_RE),
    re.compile(r'^大象$'),
    re.compile(r'^(乾坤|乾坤二卦)$'),
    re.compile(r'^(初|二|三|四|五|上)(九|六)$'),             # 初九、上六
    re.compile(r'^(九|六)(二|三|四|五|上)$'),                # 九五、六二
    re.compile(r'^(%s)?(九|六)(一|二|三|四|五|上)$' % HEX_RE),   # 謙六五、震九四
]


# ── 读写 ────────────────────────────────────────────────────────
def load_text(char_path):
    with open(char_path, encoding='utf-8') as f:
        d = json.load(f)
    return ''.join(c['c'] for p in d['pages'] for col in p['columns'] for c in col['cells'])


def load_breaks(punct_path):
    """段界：punct.json 里 kind＝break 的 char_offset（该字之后断段）。文件不存在返回空表（N6 把全册当一段，不建议）。"""
    if not punct_path or not Path(punct_path).exists():
        return []
    with open(punct_path, encoding='utf-8') as f:
        d = json.load(f)
    return [x['char_offset'] for x in d.get('punctuations', []) if x.get('kind') == 'break']


def next_id(entities):
    n = max((int(e['id'][1:]) for e in entities if re.fullmatch(r'e\d+', e['id'])), default=0)
    while True:
        n += 1
        yield 'e%05d' % n


def fmt(e):
    return '%s:%s' % (e['type'], e['text'])


class Log:
    def __init__(self):
        self.rows = []

    def add(self, rule, eid, action, before, after):
        self.rows.append((rule, eid, action, before, after))

    def tsv(self):
        head = 'rule\tentity_id\taction\tbefore\tafter'
        return '\n'.join([head] + ['\t'.join(r) for r in self.rows]) + '\n'


# ── 规则 ────────────────────────────────────────────────────────
def rule_n1(ents, text, log, ids, ctx=None):
    out = []
    for e in ents:
        if e['type'] == 'work' and any(p.match(e['text']) for p in N1_PATTERNS):
            log.add('N1', e['id'], 'delete', fmt(e), '-')
            continue
        out.append(e)
    return out


def rule_n2(ents, text, log, ids, ctx=None):
    anchors = [m.start() for m in re.finditer(CATEGORY_ANCHOR, text)]
    out = []
    for e in ents:
        s = e['span']['start_offset']
        in_win = any(a <= s <= a + CATEGORY_WINDOW for a in anchors)
        prev = text[s - 1:s]
        if e['type'] == 'work' and e['text'] in CATEGORY_NAMES and in_win and prev == '曰':
            log.add('N2', e['id'], 'delete', fmt(e), '-')
            continue
        out.append(e)
    return out


N3_AFTER = re.compile(r'^(書|會要)')
N3_PREFIX = ('舊', '新')


def rule_n3(ents, text, log, ids, ctx=None):
    """dynasty「唐」后紧跟 書／會要：改标 work（舊唐書／新唐書／唐書／唐會要）；后面的篇名（經籍志等）不在本规则标。"""
    out = []
    for e in ents:
        if e['type'] == 'dynasty' and e['text'] == '唐':
            s, t = e['span']['start_offset'], e['span']['end_offset']
            m = N3_AFTER.match(text[t:t + 2])
            if m:
                ns = s - 1 if text[s - 1:s] in N3_PREFIX else s
                ne = t + len(m.group(0))
                new = copy.deepcopy(e)
                new['type'] = 'work'
                new['text'] = text[ns:ne]
                new['span'] = {'start_offset': ns, 'end_offset': ne}
                new['anchor'] = dict(e['anchor'])
                new['target'] = {'status': 'new_candidate', 'canonical_name': new['text'],
                                 'note': 'N3 由 dynasty「唐」改标；待重对现库'}
                log.add('N3', e['id'], 'retype', fmt(e), fmt(new))
                out.append(new)
                continue
        out.append(e)
    return out


def _dyn_prefix(e, names_here):
    """返回 (prefix, rest) 或 None。"""
    t = e['text']
    for d in DYN_UNAMBIGUOUS:
        if t.startswith(d) and len(t) - len(d) >= 2:
            return d, t[len(d):]
    for d in DYN_AMBIGUOUS:
        if t.startswith(d) and len(t) - len(d) >= 2:
            rest = t[len(d):]
            tg = e['target']
            canon = tg.get('canonical_name', '')
            # 旁证：库里 canonical 正是整个 text（魏了翁）不拆；canonical＝rest，或同册别处单独出现过 rest（魏王弼／王弼）才拆
            if canon == t and t in KNOWN_DYN_PREFIXED:
                return d, rest
            if tg.get('status') == 'matched' and canon == t:
                continue
            if (tg.get('status') == 'matched' and canon == rest) or rest in names_here:
                return d, rest
    return None


def rule_n7(ents, text, log, ids, ctx=None):
    names_here = {e['text'] for e in ents if e['type'] == 'people'}
    out = []
    for e in ents:
        if e['type'] != 'people':
            out.append(e)
            continue
        r = _dyn_prefix(e, names_here)
        if not r:
            out.append(e)
            continue
        d, rest = r
        s, t = e['span']['start_offset'], e['span']['end_offset']
        dyn = copy.deepcopy(e)
        dyn['id'] = next(ids)
        dyn['type'] = 'dynasty'
        dyn['text'] = d
        dyn['span'] = {'start_offset': s, 'end_offset': s + len(d)}
        dyn['target'] = {'status': 'new_candidate', 'canonical_name': d, 'note': 'N7 由人名前缀拆出；待重对现库'}
        per = copy.deepcopy(e)
        per['text'] = rest
        per['span'] = {'start_offset': s + len(d), 'end_offset': t}
        tg = e['target']
        if tg.get('status') == 'matched' and tg.get('canonical_name') != rest:
            per['target'] = {'status': 'new_candidate', 'canonical_name': rest,
                             'note': 'N7 拆前缀后原 matched 的名不符，待重对现库'}
        else:
            canon = tg.get('canonical_name', '')
            per['target'] = dict(tg, canonical_name=canon[len(d):] if canon.startswith(d) else rest) \
                if tg.get('status') != 'matched' else dict(tg)
        log.add('N7', e['id'], 'split', fmt(e), '%s + %s' % (fmt(dyn), fmt(per)))
        out.extend([dyn, per])
    return out



N6_MIN_FULL, N6_MAX_FULL = 3, 4


def _para_end(breaks, pos, n):
    """pos 之后第一个段界（段界＝break 所在字之后）；没有就取文末。"""
    import bisect
    i = bisect.bisect_right(breaks, pos)
    return breaks[i] + 1 if i < len(breaks) else n


def rule_n6(ents, text, log, ids, ctx, surname=False):
    """同段已出现全名后，后文未被标的简称标为同一实体：
    ①名简称（王應麟→應麟）；②单姓简称（鄭玄→鄭）仅 surname=True（规则 N6s）时做：002／003 抽样精度太差
    （王韓＝王弼＋韓康伯、費氏易、太極圖…），默认不做。
    「全名」＝本册已标的 people 全名（3–4 字）；全名在段里出现（不要求那一处已被标，漏标的由 N8 处理）就算已出现。
    前一字就是该姓的（胡一桂的「一桂」）是全名的再现，不当简称。新实体 target 同代表实体，norm 指向全名，
    log action＝add。"""
    breaks = ctx.get('breaks', [])
    covered = sorted((e['span']['start_offset'], e['span']['end_offset']) for e in ents)

    def is_free(s, t):
        return all(t <= a or s >= b for a, b in covered)

    rep = {}
    for e in ents:
        if e['type'] == 'people' and N6_MIN_FULL <= len(e['text']) <= N6_MAX_FULL \
                and _dyn_prefix(e, set()) is None and not e['text'].endswith(('氏易', '易')):
            rep.setdefault(e['text'], e)       # 同名多个实体时取第一个（位置最靠前）
    n = len(text)
    # 每个全名在每段的首次出现
    first = {}                                   # (full, para_end) -> start
    for full in rep:
        i = text.find(full)
        while i >= 0:
            first.setdefault((full, _para_end(breaks, i, n)), i)
            i = text.find(full, i + 1)
    fulls_by_para = {}
    for (full, pend) in first:
        fulls_by_para.setdefault(pend, []).append(full)

    adds, done = [], set()
    for (full, pend), p0 in sorted(first.items(), key=lambda kv: kv[1]):
        e = rep[full]
        peers = fulls_by_para[pend]
        given = full[-2:] if len(full) == 3 else full[1:]
        forms = []
        if sum(1 for f in peers if f.endswith(given)) == 1:
            forms.append(('given', given))
        if surname and sum(1 for f in peers if f[0] == full[0]) == 1:
            forms.append(('surname', full[0]))
        for kind, short in forms:
            i = p0 + len(full)
            while True:
                i = text.find(short, i, pend)
                if i < 0:
                    break
                j = i + len(short)
                full_again = kind == 'given' and text[i - 1:i] == full[0]
                if is_free(i, j) and (i, j) not in done and not full_again:
                    done.add((i, j))
                    new = copy.deepcopy(e)
                    new['id'] = next(ids)
                    new['text'] = short
                    new['span'] = {'start_offset': i, 'end_offset': j}
                    new['norm'] = full
                    new['target'] = dict(e['target'])
                    new['target']['note'] = 'N6 %s简称，同段全名「%s」' % ('名' if kind == 'given' else '姓', full)
                    adds.append((new, e))
                    covered.append((i, j))
                i = j
    for new, e in adds:
        log.add('N6', new['id'], 'add', '-', '%s（%s，同%s）' % (fmt(new), new['target']['note'][3:6], e['id']))
    return ents + [x for x, _ in adds]


def rule_n4(ents, text, log, ids, ctx):
    """异体归一后重对现库：new_candidate 的 text 经 norm_variant 归一后，在名索引里同类型恰有一个条目 → 改 matched。
    名索引由 --book-index 提供（见 load_name_index）。无索引时本规则不动作。
    原文字符保留（text 不改），只改 target。"""
    idx = ctx.get('name_index')
    if not idx:
        return ents
    out = []
    for e in ents:
        tg = e['target']
        if tg.get('status') == 'new_candidate':
            key = norm_variant(e['text'])
            hits = idx.get((e['type'], key), [])
            if key != e['text'] and len(hits) == 1:
                eid, canon = hits[0]
                before = fmt(e) + ':new_candidate'
                e = copy.deepcopy(e)
                e['target'] = {'status': 'matched', 'entity_id': eid, 'canonical_name': canon,
                               'href': 'book-index://%s/%s' % ('Work' if e['type'] == 'work' else 'Entity', eid),
                               'note': 'N4 异体归一「%s」→「%s」后对上现库' % (e['text'], key)}
                log.add('N4', e['id'], 'rebind', before, '%s:matched:%s' % (fmt(e), eid))
        out.append(e)
    return out


def load_name_index(book_index_root):
    """book-index 名索引 → {(type, 异体归一名): [(id, 原名)]}。people 取 index/entities 里 subtype＝people 的
    primary_name（≥2 字），work 取 index/works 的 title（≥3 字），长度门槛同 entity_missing.load_index。
    别名（alt_names）不在索引里，本规则不用。无根目录返回空表（N4 不动作）。"""
    idx = {}
    if not book_index_root:
        return idx
    root = Path(book_index_root)
    if root.is_file():   # 名索引.tsv：type／entity_id／canonical_name 三列（people、work 才进）
        with open(root, encoding='utf-8') as fh:
            next(fh, None)
            for ln in fh:
                t, eid, n = (ln.rstrip('\n').split('\t') + ['', '', ''])[:3]
                if (t == 'people' and len(n) >= 2) or (t == 'work' and len(n) >= 3):
                    idx.setdefault((t, norm_variant(n)), []).append((eid, n))
        return idx
    for f in sorted(root.glob('index/entities/*.json')):
        with open(f, encoding='utf-8') as fh:
            for k, v in json.load(fh).items():
                n = v.get('primary_name', '')
                if v.get('subtype') == 'people' and len(n) >= 2:
                    idx.setdefault(('people', norm_variant(n)), []).append((k, n))
    for f in sorted(root.glob('index/works/*.json')):
        with open(f, encoding='utf-8') as fh:
            for k, v in json.load(fh).items():
                n = v.get('title', '')
                if len(n) >= 3:
                    idx.setdefault(('work', norm_variant(n)), []).append((k, n))
    return idx


def rule_n6s(ents, text, log, ids, ctx):
    return rule_n6(ents, text, log, ids, ctx, surname=True)


RULES = {'N1': rule_n1, 'N2': rule_n2, 'N3': rule_n3, 'N4': rule_n4, 'N6': rule_n6, 'N7': rule_n7}
OPT_RULES = {'N6s': rule_n6s}   # 不在默认集里，--rules 点名才跑


# ── 主流程 ──────────────────────────────────────────────────────
def check_no_overlap(ents):
    prev = None
    for e in sorted(ents, key=lambda x: (x['span']['start_offset'], x['span']['end_offset'])):
        if prev and e['span']['start_offset'] < prev['span']['end_offset']:
            return [prev['id'], e['id']]
        prev = e
    return None


def recount(doc):
    es = doc['entities']
    st = doc.setdefault('stats', {})
    st['total_entities'] = len(es)
    st['matched'] = sum(e['target']['status'] == 'matched' for e in es)
    st['new_candidates'] = sum(e['target']['status'] == 'new_candidate' for e in es)
    plural = {'work': 'works', 'people': 'people', 'place': 'places', 'office': 'offices', 'dynasty': 'dynasties'}
    for ty, key in plural.items():
        st[key] = sum(e['type'] == ty for e in es)


def run(doc, text, rules, breaks=None, name_index=None):
    log = Log()
    ents = doc['entities']
    ids = next_id(ents)
    ctx = {'breaks': sorted(breaks or []), 'name_index': name_index or {}}
    for r in rules:
        ents = (RULES.get(r) or OPT_RULES[r])(ents, text, log, ids, ctx or {})
    out = copy.deepcopy(doc)
    out['entities'] = sorted(ents, key=lambda x: (x['span']['start_offset'], x['span']['end_offset']))
    recount(out)
    return out, log


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('entity_json')
    ap.add_argument('--text', help='同册 char.json（默认把 .entity.json 换成 .char.json）')
    ap.add_argument('--punct', help='同册 punct.json，取段界给 N6 用（默认把 .entity.json 换成 .punct.json）')
    ap.add_argument('--book-index', help='open-guji/book-index 根目录或 名索引.tsv（N4 用；不给则 N4 不动作）')
    ap.add_argument('-o', '--out')
    ap.add_argument('--log', default='postprocess_log.tsv')
    ap.add_argument('--rules', default='N1,N2,N3,N7,N6,N4', help='逗号分隔；默认 N1,N2,N3,N7,N6,N4（可选 N6s＝单姓简称，精度低）')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    rules = [r.strip() for r in a.rules.split(',') if r.strip()]
    bad = [r for r in rules if r not in RULES and r not in OPT_RULES]
    if bad:
        sys.exit('未实现的规则：%s（已有 %s）' % (','.join(bad), ','.join(list(RULES) + list(OPT_RULES))))
    p = Path(a.entity_json)
    char = Path(a.text) if a.text else p.with_name(p.name.replace('.entity.json', '.char.json'))
    with open(p, encoding='utf-8') as f:
        doc = json.load(f)
    text = load_text(char)
    punct = a.punct or str(p.with_name(p.name.replace('.entity.json', '.punct.json')))
    out, log = run(doc, text, rules, load_breaks(punct), load_name_index(a.book_index))
    ov = check_no_overlap(out['entities'])
    if ov:
        sys.exit('后处理后出现 span 重叠：%s，未写出' % ov)
    from collections import Counter
    cnt = Counter(r[0] for r in log.rows)
    print('规则触发：', dict(cnt) or '无', '；实体 %d → %d' % (len(doc['entities']), len(out['entities'])))
    with open(a.log, 'w', encoding='utf-8') as f:
        f.write(log.tsv())
    if not a.dry_run:
        if not a.out:
            sys.exit('非 --dry-run 需要 -o')
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
