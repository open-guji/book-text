"""F-OV-13：图片格与插图块（guji-format 09 guji-fig v0.1、02 §4.7、01 §3.6；GUJI-737／739）。"""
import copy
import hashlib
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
spec = importlib.util.spec_from_file_location('vtf', os.path.join(HERE, '..', 'validate_text_format.py'))
vtf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtf)

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 2450"><circle cx="10" cy="10" r="5" fill="currentColor"/></svg>'


def sha(b):
    return hashlib.sha256(b).hexdigest()


CHAR = {
    "$schema": "https://open-guji.org/schema/char/v0.3.json", "version": "0.5.3", "book_id": "96mid1ogzk", "volume": 5,
    "pages": [
        {"page": 148, "columns": [{"col": 2, "cells": [
            {"a": "148:2:13", "c": "作"}, {"a": "148:2:14", "c": "□", "fig": "f148-2-14"}, {"a": "148:2:15", "c": "形"}]}]},
        {"page": 149, "columns": [
            {"col": 1, "cells": [{"a": "149:1:1", "c": "河"}]},
            {"col": 2, "kind": "figure", "span": 4, "fig": "p149-fig1", "cells": []}]},
    ],
}
CORD = {
    "$schema": "https://open-guji.org/schema/cord/v0.2.json", "book_id": "96mid1ogzk", "volume": 5,
    "pages": [
        {"page": 148, "canvas": {"id": "x"}, "cells": [
            {"a": "148:2:13", "box": [1645, 1730, 115, 123]}, {"a": "148:2:14", "box": [1648, 1873, 116, 44]},
            {"a": "148:2:15", "box": [1647, 1970, 111, 105]}]},
        {"page": 149, "canvas": {"id": "y"}, "cells": [{"a": "149:1:1", "box": [1810, 340, 160, 120]}],
         "marks": [{"kind": "figure", "fig": "p149-fig1", "col": 2, "span": 4, "box": [900, 330, 880, 2450]}]},
    ],
}
NORM = {"schema": "guji-norm/0.2", "book_id": "96mid1ogzk", "volume": 5, "table": None, "items": []}


def fig_doc():
    return {
        "$schema": "https://open-guji.org/schema/fig/v0.1.json", "book_id": "96mid1ogzk", "volume": 5,
        "figures": [
            {"id": "f148-2-14", "kind": "inline", "page": 148, "box": [1648, 1873, 116, 44], "alt": "左半圈连一实点",
             "file": "fig/005/f148-2-14.png", "sha256": sha(PNG), "mime": "image/png", "width": 120, "height": 48,
             "source": "crop", "by": "cv:export"},
            {"id": "p149-fig1", "kind": "block", "page": 149, "box": [900, 330, 880, 2450], "alt": "河圖",
             "file": "fig/005/p149-fig1.svg", "sha256": sha(SVG), "mime": "image/svg+xml", "width": 880, "height": 2450,
             "source": "redraw", "by": "human:示例"},
        ],
    }


@pytest.fixture
def vdir(tmp_path):
    d = tmp_path / 'fig' / '005'
    d.mkdir(parents=True)
    (d / 'f148-2-14.png').write_bytes(PNG)
    (d / 'p149-fig1.svg').write_bytes(SVG)
    return str(tmp_path)


def subs(fd, vdir, char=None, cord=None, norm=None):
    return [s for _m, s in vtf.fig_problems(fd, char or CHAR, cord if cord is not None else CORD,
                                            norm if norm is not None else NORM, vdir, '005')]


def test_valid_passes(vdir):
    assert subs(fig_doc(), vdir) == []


def test_old_char_without_fig_passes():
    old = {"$schema": "https://open-guji.org/schema/char/v0.1.json", "book_id": "b", "volume": 1,
           "pages": [{"page": 1, "columns": [{"col": 1, "cells": [{"a": "1:1:1", "c": "□", "lacuna": True}]}]}]}
    assert vtf.fig_problems(None, old) == []


# 1. 声明
def test_char_with_fig_needs_fig_file():
    assert 'nofig' in [s for _m, s in vtf.fig_problems(None, CHAR)]


def test_char_schema_must_be_v03(vdir):
    c = copy.deepcopy(CHAR)
    c['$schema'] = 'https://open-guji.org/schema/char/v0.2.json'
    assert 'char_schema' in subs(fig_doc(), vdir, char=c)


# 2. 引用两头对上
def test_missing_reference(vdir):
    fd = fig_doc()
    del fd['figures'][1]
    assert 'ref:p149-fig1' in subs(fd, vdir)


def test_orphan_figure(vdir):
    fd = fig_doc()
    extra = copy.deepcopy(fd['figures'][0])
    extra['id'] = 'f999-1-1'
    fd['figures'].append(extra)
    assert '2:orphan' in subs(fd, vdir)


def test_kind_must_match_reference(vdir):
    fd = fig_doc()
    fd['figures'][0]['kind'] = 'block'
    assert '0:kind' in subs(fd, vdir)


# 3. 图片格与图列自身
def test_fig_cell_c_must_be_box(vdir):
    c = copy.deepcopy(CHAR)
    c['pages'][0]['columns'][0]['cells'][1]['c'] = '○'
    assert 'cell:148:2:14:c' in subs(fig_doc(), vdir, char=c)


def test_fig_cell_not_with_lacuna(vdir):
    c = copy.deepcopy(CHAR)
    c['pages'][0]['columns'][0]['cells'][1]['lacuna'] = True
    assert 'cell:148:2:14:mixed' in subs(fig_doc(), vdir, char=c)


def test_figure_column_must_be_empty(vdir):
    c = copy.deepcopy(CHAR)
    c['pages'][1]['columns'][1]['cells'] = [{"a": "149:2:1", "c": "河"}]
    assert 'col:149:2:cells' in subs(fig_doc(), vdir, char=c)


def test_fig_on_body_column(vdir):
    c = copy.deepcopy(CHAR)
    c['pages'][1]['columns'][0]['fig'] = 'p149-fig1'
    assert 'col:149:1:notfig' in subs(fig_doc(), vdir, char=c)


# 4. 文件
def test_file_missing(vdir):
    os.remove(os.path.join(vdir, 'fig', '005', 'f148-2-14.png'))
    assert '0:nofile' in subs(fig_doc(), vdir)


def test_sha_mismatch(vdir):
    fd = fig_doc()
    fd['figures'][0]['sha256'] = '0' * 64
    assert '0:sha' in subs(fd, vdir)


def test_too_big(vdir):
    big = PNG + b'0' * (1024 * 1024)
    with open(os.path.join(vdir, 'fig', '005', 'f148-2-14.png'), 'wb') as f:
        f.write(big)
    fd = fig_doc()
    fd['figures'][0]['sha256'] = sha(big)
    assert '0:size' in subs(fd, vdir)


@pytest.mark.parametrize('bad', [
    b'<svg><script>alert(1)</script></svg>',
    b'<svg><image href="x.png"/></svg>',
    b'<svg><use href="https://example.com/a.svg#x"/></svg>',
    b'<svg onload="x()"></svg>',
])
def test_svg_unsafe(vdir, bad):
    with open(os.path.join(vdir, 'fig', '005', 'p149-fig1.svg'), 'wb') as f:
        f.write(bad)
    fd = fig_doc()
    fd['figures'][1]['sha256'] = sha(bad)
    assert '1:svg' in subs(fd, vdir)


def test_svg_internal_href_ok(vdir):
    ok = b'<svg><defs><path id="p" d="M0 0"/></defs><use href="#p"/></svg>'
    with open(os.path.join(vdir, 'fig', '005', 'p149-fig1.svg'), 'wb') as f:
        f.write(ok)
    fd = fig_doc()
    fd['figures'][1]['sha256'] = sha(ok)
    assert subs(fd, vdir) == []


def test_crop_must_be_raster(vdir):
    fd = fig_doc()
    fd['figures'][1]['source'] = 'crop'
    assert '1:source' in subs(fd, vdir)


def test_path_must_match_id_and_chapter(vdir):
    fd = fig_doc()
    fd['figures'][0]['file'] = 'fig/004/f148-2-14.png'
    assert '0:path' in subs(fd, vdir)


# 5. 页与框对 cord
def test_inline_box_mismatch(vdir):
    fd = fig_doc()
    fd['figures'][0]['box'] = [1648, 1873, 116, 60]
    assert '0:box' in subs(fd, vdir)


def test_inline_page_mismatch(vdir):
    fd = fig_doc()
    fd['figures'][0]['page'] = 147
    assert '0:page' in subs(fd, vdir)


def test_multi_cell_figure_uses_outer_box(vdir):
    c = copy.deepcopy(CHAR)
    c['pages'][0]['columns'][0]['cells'][2] = {"a": "148:2:15", "c": "□", "fig": "f148-2-14"}
    fd = fig_doc()
    fd['figures'][0]['box'] = [1647, 1873, 117, 202]
    assert subs(fd, vdir, char=c) == []


def test_block_needs_cord_mark(vdir):
    d = copy.deepcopy(CORD)
    del d['pages'][1]['marks']
    assert '1:mark' in subs(fig_doc(), vdir, cord=d)


def test_block_col_span_must_match(vdir):
    d = copy.deepcopy(CORD)
    d['pages'][1]['marks'][0]['span'] = 3
    assert '1:col' in subs(fig_doc(), vdir, cord=d)


def test_cord_schema_must_be_v02(vdir):
    d = copy.deepcopy(CORD)
    d['$schema'] = 'https://open-guji.org/schema/cord/v0.1.json'
    assert 'cord_schema' in subs(fig_doc(), vdir, cord=d)


# 6. norm 不许有图片格
def test_norm_on_fig_cell(vdir):
    n = copy.deepcopy(NORM)
    n['items'] = [{"a": "148:2:14", "c": "□", "t": "○"}]
    assert 'norm:148:2:14' in subs(fig_doc(), vdir, norm=n)
