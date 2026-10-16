import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_postprocess_replay as c  # noqa: E402

HEAD = 'rule\tentity_id\taction\tbefore\tafter\n'


def _log(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(HEAD + body, encoding='utf-8')
    return p


def test_read_log_ignores_ids_and_filters_rules(tmp_path):
    p = _log(tmp_path, 'a.tsv',
             'N6\te01806\tadd\t-\tpeople:子夏（名简称，同e00015）\n'
             'N1\te00434\tdelete\twork:乾卦彖傳\t-\n')
    got = c.read_log(p, {'N6'})
    assert got == {('N6', 'add', '-', 'people:子夏（名简称，同e*）'): 1}


def test_renumbered_ids_compare_equal(tmp_path):
    a = _log(tmp_path, 'a.tsv', 'N6\te1\tadd\t-\tpeople:一桂（名简称，同e00371）\n')
    b = _log(tmp_path, 'b.tsv', 'N6\te9\tadd\t-\tpeople:一桂（名简称，同e00685）\n')
    assert c.read_log(a, {'N6'}) == c.read_log(b, {'N6'})
