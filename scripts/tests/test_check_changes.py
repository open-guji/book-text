"""check_changes.py（GUJI-559 方案 C：CHANGES.md 三项对应）单测，GUJI-593 接入 CI 时补。"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('check_changes', os.path.join(HERE, '..', 'check_changes.py'))
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

HEAD = "| 日期 | 册 | 线 | 版本 | 说明 | PR |\n|---|---|---|---|---|---|\n"


def row(note, chg="→0.1.0", line="文本", date="2026-10-17", vol="96mid1ogzk/004"):
    return f"| {date} | {vol} | {line} | {chg} | {note} | #1 |\n"


def test_full_row_passes():
    note = "cv 0.2.0（commit 4a9388ac；cv 侧 vol04-r1＝本册 004-r1）；ws 快照 snap/x/vol04/20261017T1243（guji-workspace 23676b12）"
    assert cc.check(HEAD + row(note)) == []


def test_missing_r_number_and_cv():
    errs = cc.check(HEAD + row("ws 快照 snap/x/vol04/20261017T1243（guji-workspace 23676b12）"))
    assert len(errs) == 2
    assert "r 号" in errs[0] and "第 3 行" in errs[0]
    assert "cv commit" in errs[1]


def test_chapter_r_number_ok():
    assert cc.check(HEAD + row("cv 9587e67c＋ws da2b5ff4d，快照 e7f093a26（004-r1）")) == []


def test_skipped_rows():
    bad = "快照 e7f093a26"
    text = HEAD + row(bad, chg="0.1.1（不变）") + row(bad, line="标点") + row("无快照的说明") + row(bad, date="2026-10-16")
    assert cc.check(text, since="2026-10-17") == []
    assert len(cc.check(text)) == 2  # 不带 --since-date 时旧行也查

