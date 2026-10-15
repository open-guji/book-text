import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import entity_postprocess as ep  # noqa: E402


def ent(i, ty, text, text_all, nth=0, status='new_candidate', canon=None):
    s = -1
    for _ in range(nth + 1):
        s = text_all.index(text, s + 1)
    tg = {'status': status, 'canonical_name': canon or text}
    if status == 'matched':
        tg['entity_id'] = 'x%d' % i
    return {'id': 'e%05d' % i, 'type': ty, 'text': text, 'anchor': {'start': '1:1:1', 'end': '1:1:1'},
            'span': {'start_offset': s, 'end_offset': s + len(text)}, 'target': tg, 'source': 't'}


def wj(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)


def doc(ents):
    return {'entities': ents, 'stats': {}}


class N1(unittest.TestCase):
    def run_n1(self, texts):
        text = ''.join(texts)
        ents = [ent(i, 'work', t, text, nth=0) for i, t in enumerate(texts, 1)]
        out, log = ep.run(doc(ents), text, ['N1'])
        return [e['text'] for e in out['entities']], log

    def test_deletes_pilot_patterns(self):
        # 试点易類一里的真实例：卦名、X彖、X大象、X象傳、爻位
        bad = ['乾卦', '坤卦', '乾坤', '復彖', '大象', '賁大象', '坤象傳', '賁象傳', '震彖傳', '乾卦彖傳',
               '六五', '上六', '謙六五', '震九四']
        kept, log = self.run_n1(bad)
        self.assertEqual(kept, [])
        self.assertEqual(len(log.rows), len(bad))

    def test_keeps_real_works(self):
        # 书名里碰巧含「象」「卦」不能删（002／003 里实测出现过的误伤）
        good = ['易本象', '疇象', '周易', '易象鉤解', '卦變考', '乾', '師']
        kept, log = self.run_n1(good)
        self.assertEqual(kept, good)
        self.assertEqual(log.rows, [])

    def test_only_work_type(self):
        text = '乾卦'
        out, _ = ep.run(doc([ent(1, 'place', '乾卦', text)]), text, ['N1'])
        self.assertEqual(len(out['entities']), 1)


class N2(unittest.TestCase):
    TEXT = '故分爲十類曰易曰書曰詩曰禮曰春秋曰孝經曰五經總義曰四書曰樂曰小學' + '又有易學之書' + '易'

    def test_deletes_ten_categories(self):
        t = self.TEXT
        names = ['易', '書', '詩', '禮', '春秋', '孝經', '五經總義', '四書', '樂', '小學']
        ents = [ent(i, 'work', n, t) for i, n in enumerate(names, 1)]
        out, log = ep.run(doc(ents), t, ['N2'])
        self.assertEqual(out['entities'], [])
        self.assertEqual(len(log.rows), 10)

    def test_keeps_outside_window(self):
        t = self.TEXT
        far = '，' * 200 + '曰易'
        t2 = t + far
        e = ent(1, 'work', '易', t2, nth=2)   # 最后一个「易」，在窗口外
        out, log = ep.run(doc([e]), t2, ['N2'])
        self.assertEqual(len(out['entities']), 1)

    def test_keeps_without_yue_prefix(self):
        t = '分爲十類而論易'
        out, _ = ep.run(doc([ent(1, 'work', '易', t)]), t, ['N2'])
        self.assertEqual(len(out['entities']), 1)


class N3(unittest.TestCase):
    def test_tang_to_work(self):
        t = '開元七年唐會要載' + '舊唐書經籍志稱' + '新唐書藝文志作' + '是書唐書無傳'
        ents = [ent(i, 'dynasty', '唐', t, nth=k, status='matched') for k, i in enumerate((1, 2, 3, 4))]
        out, log = ep.run(doc(ents), t, ['N3'])
        self.assertEqual([(e['type'], e['text']) for e in out['entities']],
                         [('work', '唐會要'), ('work', '舊唐書'), ('work', '新唐書'), ('work', '唐書')])
        for e in out['entities']:
            self.assertEqual(e['target']['status'], 'new_candidate')
            self.assertEqual(t[e['span']['start_offset']:e['span']['end_offset']], e['text'])
        self.assertEqual([r[2] for r in log.rows], ['retype'] * 4)

    def test_tang_as_dynasty_kept(self):
        t = '唐孔穎達撰'
        out, log = ep.run(doc([ent(1, 'dynasty', '唐', t, status='matched')]), t, ['N3'])
        self.assertEqual(out['entities'][0]['type'], 'dynasty')
        self.assertEqual(log.rows, [])


class N4(unittest.TestCase):
    IDX = {('work', '溫公易說'): [('w1', '溫公易說')], ('people', '朱彝尊'): [('p1', '朱彝尊'), ('p2', '朱彝尊')],
           ('work', '易學啓蒙通釋'): [('w2', '易學啓蒙通釋')]}

    def test_rebind_variant(self):
        t = '温公易說'
        out, log = ep.run(doc([ent(1, 'work', '温公易說', t)]), t, ['N4'], name_index=self.IDX)
        e = out['entities'][0]
        self.assertEqual(e['text'], '温公易說')                   # 原文字符保留
        self.assertEqual(e['target']['status'], 'matched')
        self.assertEqual(e['target']['entity_id'], 'w1')
        self.assertEqual(log.rows[0][2], 'rebind')

    def test_multi_char_variants(self):
        t = '易學啟𫎇通釋'
        out, _ = ep.run(doc([ent(1, 'work', t, t)]), t, ['N4'], name_index=self.IDX)
        self.assertEqual(out['entities'][0]['target']['entity_id'], 'w2')

    def test_ambiguous_index_not_bound(self):
        t = '朱彞尊'
        out, log = ep.run(doc([ent(1, 'people', t, t)]), t, ['N4'], name_index=self.IDX)
        self.assertEqual(out['entities'][0]['target']['status'], 'new_candidate')
        self.assertEqual(log.rows, [])

    def test_no_index_noop(self):
        t = '温公易說'
        out, log = ep.run(doc([ent(1, 'work', t, t)]), t, ['N4'])
        self.assertEqual(log.rows, [])

    def test_norm_variant_table(self):
        self.assertEqual(ep.norm_variant('朱彞尊孔頴達古經解鈎沈紫巖易傳易璇璣韓𠈁冑'),
                         '朱彝尊孔穎達古經解鉤沈紫岩易傳易璿璣韓侂冑')


class N6(unittest.TestCase):
    def mk(self, t, fulls, breaks=()):
        ents = [ent(i, 'people', f, t, status='matched', canon=f) for i, f in enumerate(fulls, 1)]
        return ep.run(doc(ents), t, ['N6'], breaks)

    def test_given_name_after_full_name(self):
        t = '宋王應麟編應麟字伯厚'
        out, log = self.mk(t, ['王應麟'])
        new = [e for e in out['entities'] if e['text'] == '應麟']
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]['norm'], '王應麟')
        self.assertEqual(new[0]['target']['entity_id'], 'x1')
        self.assertEqual(t[new[0]['span']['start_offset']:new[0]['span']['end_offset']], '應麟')
        self.assertEqual(log.rows[0][2], 'add')

    def test_full_name_untagged_still_counts(self):
        # 段里全名出现但没被标（漏标）也算「已出现」：用别处标过的同名全名
        t = '王應麟輯此書。' + '宋王應麟編應麟字伯厚'
        out, _ = self.mk(t, ['王應麟'])
        self.assertEqual(sum(e['text'] == '應麟' for e in out['entities']), 1)

    def test_not_across_paragraph(self):
        t = '王應麟輯此書。' + '應麟字伯厚'
        out, log = self.mk(t, ['王應麟'], breaks=[6])   # 第 6 字（。）之后断段
        self.assertEqual(log.rows, [])

    def test_full_name_again_not_short_form(self):
        # 胡一桂、胡炳文并列：「胡一桂」里的「一桂」前一字是姓，是全名再现，不当简称
        t = '胡一桂撰董楷胡一桂胡炳文'
        out, log = self.mk(t, ['胡一桂'])
        self.assertEqual(log.rows, [])

    def test_ambiguous_given_name_skipped(self):
        t = '王應麟與李應麟並稱應麟'
        out, log = self.mk(t, ['王應麟', '李應麟'])
        self.assertEqual(log.rows, [])

    def test_surname_only_opt_in(self):
        t = '鄭玄注鄭曰'
        ents = [ent(1, 'people', '鄭玄注'[:2], t, status='matched', canon='鄭玄')]
        out, log = ep.run(doc(ents), t, ['N6'])
        self.assertEqual(log.rows, [])   # 默认不做单姓简称

    def test_overlap_with_existing_entity_skipped(self):
        t = '王應麟編應麟字伯厚'
        ents = [ent(1, 'people', '王應麟', t, status='matched', canon='王應麟'), ent(2, 'people', '應麟', t, nth=1)]
        out, log = ep.run(doc(ents), t, ['N6'])
        self.assertEqual(log.rows, [])


class N7(unittest.TestCase):
    def test_split_unambiguous_prefix(self):
        t = '明劉日升撰'
        out, log = ep.run(doc([ent(1, 'people', '明劉日升', t)]), t, ['N7'])
        self.assertEqual([(e['type'], e['text']) for e in out['entities']],
                         [('dynasty', '明'), ('people', '劉日升')])
        for e in out['entities']:
            self.assertEqual(t[e['span']['start_offset']:e['span']['end_offset']], e['text'])
        self.assertEqual(log.rows[0][2], 'split')
        self.assertEqual(len({e['id'] for e in out['entities']}), 2)

    def test_split_matched_known_prefix(self):
        t = '魏王弼注'
        e = ent(1, 'people', '魏王弼', t, status='matched', canon='魏王弼')
        out, _ = ep.run(doc([e]), t, ['N7'])
        self.assertEqual([x['text'] for x in out['entities']], ['魏', '王弼'])
        self.assertEqual(out['entities'][1]['target']['status'], 'new_candidate')

    def test_surname_not_split(self):
        # 魏了翁：库里 canonical 就是 魏了翁，魏是姓
        t = '魏了翁撰，又魏了翁'
        e = ent(1, 'people', '魏了翁', t, status='matched', canon='魏了翁')
        out, log = ep.run(doc([e]), t, ['N7'])
        self.assertEqual(len(out['entities']), 1)
        self.assertEqual(log.rows, [])

    def test_two_char_name_not_split(self):
        t = '明復'
        out, log = ep.run(doc([ent(1, 'people', '明復', t)]), t, ['N7'])
        self.assertEqual(len(out['entities']), 1)


class Cli(unittest.TestCase):
    def test_cli_roundtrip_and_stats(self):
        t = '乾卦明劉日升撰'
        ents = [ent(1, 'work', '乾卦', t), ent(2, 'people', '明劉日升', t)]
        d = doc(ents)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, '002.entity.json')
            wj(p, d)
            cells = [{'a': '1:1:%d' % i, 'c': c} for i, c in enumerate(t, 1)]
            wj(os.path.join(td, '002.char.json'), {'pages': [{'columns': [{'cells': cells}]}]})
            out = os.path.join(td, 'out.json')
            log = os.path.join(td, 'log.tsv')
            self.assertEqual(ep.main([p, '-o', out, '--log', log]), 0)
            with open(out) as f:
                o = json.load(f)
            self.assertEqual(o['stats']['total_entities'], 2)
            self.assertEqual(o['stats']['people'], 1)
            self.assertEqual(o['stats']['dynasties'], 1)
            with open(log) as f:
                rows = f.read().splitlines()
            self.assertEqual(rows[0], 'rule\tentity_id\taction\tbefore\tafter')
            self.assertEqual(len(rows), 3)

    def test_dry_run_writes_no_out(self):
        t = '乾卦'
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, '002.entity.json')
            wj(p, doc([ent(1, 'work', '乾卦', t)]))
            wj(os.path.join(td, '002.char.json'), {'pages': [{'columns': [{'cells': [{'a': 'x', 'c': c} for c in t]}]}]})
            out = os.path.join(td, 'out.json')
            ep.main([p, '--dry-run', '-o', out, '--log', os.path.join(td, 'l.tsv')])
            self.assertFalse(os.path.exists(out))


if __name__ == '__main__':
    unittest.main()
