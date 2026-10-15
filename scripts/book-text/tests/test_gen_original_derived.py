# -*- coding: utf-8 -*-
"""單測：gen_original_derived.find_original_dirs 認 manifest 的 is_original（original 可放 default/，#497 吻合度報告 §五·1）。"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import gen_original_derived as G  # noqa: E402


def _w(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


class FindOriginalDirs(unittest.TestCase):
    def test_default_marked_is_original(self):
        with tempfile.TemporaryDirectory() as root:
            e = os.path.join(root, "Book", "a", "b", "c", "x1")
            _w(os.path.join(e, "manifest.json"), {"versions": [{"key": "default", "is_original": True}]})
            _w(os.path.join(e, "default", "index.json"), {})
            self.assertEqual(G.find_original_dirs(root), [os.path.join(e, "default")])
            self.assertEqual(G.find_original_dirs(e), [os.path.join(e, "default")])
            self.assertEqual(G.find_original_dirs(os.path.join(e, "default")), [os.path.join(e, "default")])

    def test_legacy_original_dir(self):
        with tempfile.TemporaryDirectory() as root:
            e = os.path.join(root, "Work", "a", "b", "c", "x2")
            _w(os.path.join(e, "original", "index.json"), {})
            self.assertEqual(G.find_original_dirs(root), [os.path.join(e, "original")])

    def test_non_original_ignored_and_empty_fails(self):
        with tempfile.TemporaryDirectory() as root:
            e = os.path.join(root, "Work", "a", "b", "c", "x3")
            _w(os.path.join(e, "manifest.json"), {"versions": [{"key": "default"}]})
            _w(os.path.join(e, "default", "index.json"), {})
            self.assertEqual(G.find_original_dirs(root), [])
            self.assertEqual(G.main([root, "--check"]), 1)


if __name__ == "__main__":
    unittest.main()
