# -*- coding: utf-8 -*-
"""單測：migrate_texts.py（T51 #307-B，卡 #309）。

用最小合成 fixture（tempfile），不依賴真實 book-text／book-text-private——
那兩倉只讀，只用來做人工勘查與干跑，見卡 #309 交付的
項目進展/古籍文本/進度/E-文本整理本/texts-migration-stats.md。

覆蓋範圍：key 映射規則、default 選擇規則（含整理本優先、來源序 維基＞Kanripo＞識典、同源章數多者優先
Kanripo 平局規則）、三位編號規則、卷名匹配（含 juan_text_match.py 起步規則的
擴充：冊/串數字、中文數字、別名、兜底配對）、manifest 字段來源（collated 常量
vs full_text 讀 source）、TSV 兩行寫法、隱藏版本識別。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import migrate_texts as M  # noqa: E402


def _write(p, obj_or_text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if isinstance(obj_or_text, (dict, list)):
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(obj_or_text, f, ensure_ascii=False)
    else:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(obj_or_text)


# ───────────────────────── key 映射 / 保留字 ─────────────────────────────────

class TestKeyMapping(unittest.TestCase):
    def test_dirname_to_source_key(self):
        self.assertEqual(M._dirkey_to_source_key('wikisource-01'), ('wikisource', 1))
        self.assertEqual(M._dirkey_to_source_key('wikisource-02'), ('wikisource', 2))
        self.assertEqual(M._dirkey_to_source_key('kanripo-01'), ('kanripo', 1))
        self.assertEqual(M._dirkey_to_source_key('shidian-07'), ('shidian', 7))

    def test_seq_to_key(self):
        self.assertEqual(M._seq_to_key('wikisource', 1), 'wikisource')
        self.assertEqual(M._seq_to_key('wikisource', 2), 'wikisource-2')
        self.assertEqual(M._seq_to_key('kanripo', 1), 'kanripo')

    def test_reserved_keys(self):
        for k in ('default', 'manifest', 'fragments', 'sources'):
            self.assertIn(k, M.RESERVED_KEYS)


# ───────────────────────── 三位編號 ──────────────────────────────────────────

class TestChapterNumbering(unittest.TestCase):
    def test_three_digit_filenames_from_apply_plan(self):
        root = tempfile.mkdtemp()
        _make_simple_fulltext_work(root, 'w0000000001', n_chapters=3, source_name='維基文庫')
        owners, warnings = M.scan_all(root)
        self.assertEqual(len(owners), 1)
        o = owners[0]
        file_actions, manifests, version_indexes = M.build_apply_plan(owners)
        names = sorted(os.path.basename(dst) for _, dst in file_actions if dst.endswith('.md'))
        self.assertEqual(names, ['001.md', '002.md', '003.md'])


# ───────────────────────── default 選擇規則 ──────────────────────────────────

def _make_simple_fulltext_work(root, wid, n_chapters, source_name, key_dir='wikisource-01',
                                license_='CC BY-SA 4.0', grade='source'):
    shard = M.owner_shard_dir('Work', wid)
    base = os.path.join(root, shard, 'full_text', key_dir)
    chapters = []
    for i in range(1, n_chapters + 1):
        fname = f'{i:03d}.md'
        _write(os.path.join(base, fname), f'# 第{i}章\n正文 {i}')
        chapters.append({'n': i, 'title': f'第{i}章', 'file': fname})
    idx = {
        'work_id': wid,
        'version_label': f'{wid}（{source_name}）',
        'source': {'name': source_name, 'url': f'https://example.org/{wid}', 'license': license_},
        'total_chapters': n_chapters,
        'text_quality': {'grade': grade},
        'chapters': chapters,
    }
    _write(os.path.join(base, 'index.json'), idx)


def _make_collated_work(root, wid, juan_titles, matched_text=True):
    shard = M.owner_shard_dir('Work', wid)
    base = os.path.join(root, shard, 'collated_edition')
    juan_files = []
    for i, title in enumerate(juan_titles, 1):
        jf = f'juan/{i:03d}.json'
        _write(os.path.join(base, jf), {'title': title, 'sections': []})
        juan_files.append(jf)
        if matched_text:
            _write(os.path.join(base, 'text', f'{title}.md'), f'# {title}\n正文')
    idx = {
        'work_id': wid, 'type': 'catalog', 'total_entries': len(juan_titles) * 5,
        'juan_files': juan_files,
        'text_quality': {'grade': 'rough'},
    }
    _write(os.path.join(base, 'index.json'), idx)


class TestDefaultSelection(unittest.TestCase):
    def test_collated_always_wins_default(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000002'
        _make_collated_work(root, wid, ['卷一', '卷二'])
        _make_simple_fulltext_work(root, wid, n_chapters=99, source_name='維基文庫')  # 章數遠多於整理本
        owners, warnings = M.scan_all(root)
        o = owners[0]
        self.assertEqual(o.versions[0].source, 'collated')
        self.assertEqual(o.versions[0].key, 'default')

    def test_wikisource_beats_kanripo_even_with_fewer_chapters(self):
        # 用戶 09-30（#307）：整理本 → 維基 → Kanripo → 識典，章數只在同源內比
        root = tempfile.mkdtemp()
        wid = 'w0000000003'
        _make_simple_fulltext_work(root, wid, n_chapters=5, source_name='維基文庫', key_dir='wikisource-01')
        _make_simple_fulltext_work(root, wid, n_chapters=11, source_name='Kanripo', key_dir='kanripo-01')
        owners, warnings = M.scan_all(root)
        o = owners[0]
        self.assertEqual(o.versions[0].source, 'wikisource')
        self.assertEqual(o.versions[0].chapters_total, 5)
        others = {v.source: v.key for v in o.versions if not v.is_default}
        self.assertEqual(others['kanripo'], 'kanripo')

    def test_wikisource_wins_tie(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000004'
        _make_simple_fulltext_work(root, wid, n_chapters=7, source_name='維基文庫', key_dir='wikisource-01')
        _make_simple_fulltext_work(root, wid, n_chapters=7, source_name='Kanripo', key_dir='kanripo-01')
        owners, warnings = M.scan_all(root)
        o = owners[0]
        self.assertEqual(o.versions[0].source, 'wikisource')

    def test_single_version_is_default_regardless(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000005'
        _make_simple_fulltext_work(root, wid, n_chapters=1, source_name='維基文庫')
        owners, warnings = M.scan_all(root)
        self.assertEqual(owners[0].versions[0].key, 'default')

    def test_wikisource_second_copy_gets_dash2(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000006'
        _make_simple_fulltext_work(root, wid, n_chapters=5, source_name='維基文庫', key_dir='wikisource-01')
        _make_simple_fulltext_work(root, wid, n_chapters=3, source_name='維基文庫', key_dir='wikisource-02')
        owners, warnings = M.scan_all(root)
        o = owners[0]
        keys = sorted(v.key for v in o.versions)
        self.assertEqual(keys, ['default', 'wikisource-2'])


# ───────────────────────── manifest 字段來源 ─────────────────────────────────

class TestManifestFieldSources(unittest.TestCase):
    def test_collated_kindnote_source_field_ignored_silently(self):
        """09-30 勘查踩到的真實坑：65 部裡有 1 部 index.json 帶一個
        「kind/note」風格的 source 欄——那是「據何底本整理」的說明，不是版權
        信息，不能當 license 用，也不必為它特地示警（它不含任何
        license/source_name/source_url/name/url 字段）。"""
        root = tempfile.mkdtemp()
        wid = 'w0000000007'
        _make_collated_work(root, wid, ['卷一'])
        idx_path = os.path.join(root, M.owner_shard_dir('Work', wid), 'collated_edition', 'index.json')
        ij = json.load(open(idx_path, encoding='utf-8'))
        ij['source'] = {'kind': '目錄', 'note': '據某PDF解析'}
        _write(idx_path, ij)

        owners, warnings = M.scan_all(root)
        v = owners[0].versions[0]
        self.assertEqual(v.source_name, '開源古籍')
        self.assertEqual(v.license, 'CC0 1.0')
        self.assertIsNone(v.source_url)
        hits = [w for w in warnings if w[0] == 'collated_has_source_field']
        self.assertEqual(len(hits), 0)

    def test_collated_license_like_source_field_flagged_for_review(self):
        """萬一哪部整理本的 source 欄真的給了 license/source_name/source_url
        之類版權字段，要在 warnings 裡點名，供人複核；常量仍照樣采用（腳本不
        自作主張改規則），只是不能靜默吞掉這個發現。"""
        root = tempfile.mkdtemp()
        wid = 'w0000000013'
        _make_collated_work(root, wid, ['卷一'])
        idx_path = os.path.join(root, M.owner_shard_dir('Work', wid), 'collated_edition', 'index.json')
        ij = json.load(open(idx_path, encoding='utf-8'))
        ij['source'] = {'license': 'CC0', 'name': '某人工整理'}
        _write(idx_path, ij)

        owners, warnings = M.scan_all(root)
        v = owners[0].versions[0]
        self.assertEqual(v.license, 'CC0 1.0')  # 常量優先，不被覆蓋
        hits = [w for w in warnings if w[0] == 'collated_has_source_field']
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], wid)

    def test_fulltext_reads_source_and_grade(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000008'
        _make_simple_fulltext_work(root, wid, n_chapters=2, source_name='維基文庫',
                                    license_='CC BY-SA 4.0', grade='fine')
        owners, warnings = M.scan_all(root)
        v = owners[0].versions[0]
        self.assertEqual(v.source_name, '維基文庫')
        self.assertEqual(v.license, 'CC BY-SA 4.0')
        self.assertEqual(v.quality, 'fine')


# ───────────────────────── TSV 兩行寫法 ──────────────────────────────────────

class TestTsvRows(unittest.TestCase):
    def test_collated_chapter_gets_two_old_path_rows(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000009'
        _make_collated_work(root, wid, ['卷一'])
        owners, warnings = M.scan_all(root)
        header, rows = M.build_tsv_rows(owners)
        self.assertEqual(header, ['old_path', 'old_key', 'new_path', 'new_key', 'is_default'])
        ch1_rows = [r for r in rows if '=001' in r[0] or 'juan/001.json' in r[0]]
        self.assertEqual(len(ch1_rows), 2)
        styles = sorted(r[0].split('juan=')[-1] for r in ch1_rows)
        self.assertEqual(styles, ['001', 'juan/001.json'])
        for r in ch1_rows:
            self.assertEqual(r[2], f'/read/{wid}/001')  # default 版本 URL 不帶 key
            self.assertEqual(r[4], 'yes')

    def test_fulltext_non_default_row_has_key_segment(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000010'
        _make_collated_work(root, wid, ['卷一'])
        _make_simple_fulltext_work(root, wid, n_chapters=1, source_name='維基文庫')
        owners, warnings = M.scan_all(root)
        header, rows = M.build_tsv_rows(owners)
        wiki_rows = [r for r in rows if r[3] == 'wikisource']
        self.assertTrue(wiki_rows)
        for r in wiki_rows:
            self.assertEqual(r[2], f'/read/{wid}/wikisource/001')
            self.assertEqual(r[4], 'no')


# ───────────────────────── 隱藏版本 ──────────────────────────────────────────

class TestHiddenVersion(unittest.TestCase):
    def test_text_underscore_dir_becomes_extra_version(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000011'
        _make_collated_work(root, wid, ['卷一', '卷二'])
        base = os.path.join(root, M.owner_shard_dir('Work', wid), 'collated_edition')
        _write(os.path.join(base, 'text_適園叢書本', '卷一.md'), '# 卷一\n適園本正文')
        _write(os.path.join(base, 'text_適園叢書本', '卷二.md'), '# 卷二\n適園本正文')

        owners, warnings = M.scan_all(root)
        o = owners[0]
        keys = sorted(v.key for v in o.versions)
        self.assertIn('shiyuan', keys)
        hv = [v for v in o.versions if v.key == 'shiyuan'][0]
        self.assertEqual(hv.chapters_total, 2)
        self.assertFalse(hv.is_default)
        hits = [w for w in warnings if w[0] == 'hidden_version_found']
        self.assertEqual(len(hits), 1)

    def test_unknown_hidden_dir_gets_slugified_and_flagged(self):
        root = tempfile.mkdtemp()
        wid = 'w0000000012'
        _make_collated_work(root, wid, ['卷一'])
        base = os.path.join(root, M.owner_shard_dir('Work', wid), 'collated_edition')
        _write(os.path.join(base, 'text_某某新校本', '卷一.md'), '# 卷一\n某某新校本正文')
        owners, warnings = M.scan_all(root)
        o = owners[0]
        keys = [v.key for v in o.versions]
        self.assertTrue(any(k != 'default' and k != 'collated' for k in keys if k not in ('default',)))
        hits = [w for w in warnings if w[0] == 'hidden_version_unmapped_slug']
        self.assertEqual(len(hits), 1)


# ───────────────────────── 卷名匹配（match_collated_texts）────────────────────

class TestJuanTextMatch(unittest.TestCase):
    def _build(self, root, juan_specs, text_names):
        """juan_specs: [(filename, title, source_juan_or_None), ...]"""
        base = os.path.join(root, 'collated_edition')
        juan_files = []
        for fname, title, source_juan in juan_specs:
            obj = {'title': title}
            if source_juan:
                obj['source_juan'] = source_juan
            _write(os.path.join(base, 'juan', fname), obj)
            juan_files.append(f'juan/{fname}')
        for t in text_names:
            _write(os.path.join(base, 'text', t), f'# {t}\n正文')
        _write(os.path.join(base, 'index.json'), {'juan_files': juan_files})
        return base

    def test_cn_to_num(self):
        self.assertEqual(M.cn_to_num('十'), 10)
        self.assertEqual(M.cn_to_num('二十三'), 23)
        self.assertEqual(M.cn_to_num('四十七'), 47)
        self.assertEqual(M.cn_to_num('一'), 1)

    def test_extract_num_prefers_arabic_then_cn(self):
        self.assertEqual(M._extract_num('第89册', ''), 89)
        self.assertEqual(M._extract_num('卷四十七　頌贊', ''), 47)
        self.assertEqual(M._extract_num('易類', ''), None)

    def test_literal_title_match(self):
        root = tempfile.mkdtemp()
        self._build(root, [('001.json', '易類', None)], ['易類.md'])
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(matches, {'juan/001.json': 'text/易類.md'})

    def test_ce_suffix_digit_match(self):
        root = tempfile.mkdtemp()
        self._build(root, [('001.json', '第89册', None)], ['089册.md'])
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(matches, {'juan/001.json': 'text/089册.md'})

    def test_traditional_ce_char_normalized(self):
        root = tempfile.mkdtemp()
        self._build(root, [('001.json', '49冊[親軍衛]', None)], ['49册.md'])
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(matches, {'juan/001.json': 'text/49册.md'})

    def test_cn_numeral_in_title_matches_juan_underscore_file(self):
        root = tempfile.mkdtemp()
        self._build(root, [('046.json', '卷四十七　頌贊', None)], ['juan_47.md'])
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(matches, {'juan/046.json': 'text/juan_47.md'})

    def test_fulu_alias(self):
        root = tempfile.mkdtemp()
        self._build(root, [('205.json', '附錄', None)], ['fulu.md'])
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(matches, {'juan/205.json': 'text/fulu.md'})

    def test_fallback_pairs_only_when_exactly_one_each_side(self):
        root = tempfile.mkdtemp()
        self._build(root, [('001.json', '重訂序、凡例、分類說明', '序文')], ['00_序言部分.md'])
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(matches, {})
        self.assertEqual(fallback, {'juan/001.json': 'text/00_序言部分.md'})
        self.assertEqual(unmatched, [])

    def test_fallback_does_not_fire_with_multiple_leftovers(self):
        root = tempfile.mkdtemp()
        # 一卷配不上，但兩個候選文本都沒被認領——不該瞎配，維持 unmatched
        self._build(root, [('001.json', '完全無關標題XYZ', None)],
                    ['某甲.md', '某乙.md'])
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(fallback, {})
        self.assertEqual(unmatched, ['juan/001.json'])
        self.assertEqual(sorted(leftover), ['text/某乙.md', 'text/某甲.md'])

    def test_no_text_dir_returns_none_unmatched(self):
        root = tempfile.mkdtemp()
        base = os.path.join(root, 'collated_edition')
        _write(os.path.join(base, 'juan', '001.json'), {'title': '卷一'})
        _write(os.path.join(base, 'index.json'), {'juan_files': ['juan/001.json']})
        matches, fallback, unmatched, leftover = M.match_collated_texts(base)
        self.assertEqual(matches, {})
        self.assertEqual(fallback, {})
        self.assertIsNone(unmatched)
        self.assertEqual(leftover, [])

    def test_filename_number_priority_avoids_false_positional_collision(self):
        """09-30 真實反例（d59dh3vo9af4 縮小版）：juan json 自己檔名的數字要優
        先於標題裡的數字，否則位置上的巧合會把不同卷的文本錯配在一起。"""
        root = tempfile.mkdtemp()
        specs = [
            ('001.json', '卷首1', None),
            ('002.json', '卷首2', None),
            ('003.json', '卷001', None),  # 檔名數字=3，標題數字=1；應配 juan003.md
            ('004.json', '卷197', None),  # 標題數字=197，檔名數字=4；juan197 不存在，需落回標題數字
        ]
        texts = ['juan001.md', 'juan002.md', 'juan003.md', 'juan197.md']
        self._build(root, specs, texts)
        matches, fallback, unmatched, leftover = M.match_collated_texts(os.path.join(root, 'collated_edition'))
        self.assertEqual(matches.get('juan/001.json'), 'text/juan001.md')
        self.assertEqual(matches.get('juan/002.json'), 'text/juan002.md')
        self.assertEqual(matches.get('juan/003.json'), 'text/juan003.md')
        self.assertEqual(matches.get('juan/004.json'), 'text/juan197.md')


# ───────────────────────── shard() 與 build_index.py 對齊 ─────────────────────

class TestShard(unittest.TestCase):
    def test_shard_matches_build_index_algorithm(self):
        # 照搬 build_index.py 的 shard()，算法有變動要兩邊一起改（見腳本內註解）。
        def ref_shard(i):
            h = 0
            for c in i:
                h = ((h * 31) + ord(c)) & 0xFFFFFFFF
            return '%x' % (h % 16)
        for wid in ('d59f2hqc0c1t', 'd59f2mel8d1c', 'abc', '0000000000'):
            self.assertEqual(M.shard(wid), ref_shard(wid))


if __name__ == '__main__':
    unittest.main()
