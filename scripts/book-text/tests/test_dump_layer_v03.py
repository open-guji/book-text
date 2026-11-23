import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import original_version as OV  # noqa: E402


def test_v03_layer_one_entry_per_line(tmp_path):
    doc = {"$schema": "https://open-guji.org/schema/punct/v0.3.json", "version": "0.1.0", "default_source": "a",
           "punctuations": [{"mark": "。", "anchor": "1:1:1"}, {"mark": "，", "anchor": "1:1:2", "source": "b"}]}
    p = tmp_path / "001.punct.json"
    OV.dump_json(str(p), doc)
    txt = p.read_text(encoding="utf-8")
    assert txt == ('{\n  "$schema": "https://open-guji.org/schema/punct/v0.3.json",\n  "version": "0.1.0",\n'
                   '  "default_source": "a",\n  "punctuations": [\n    {"mark": "。", "anchor": "1:1:1"},\n'
                   '    {"mark": "，", "anchor": "1:1:2", "source": "b"}\n  ]\n}\n')
    assert json.loads(txt) == doc


def test_v02_layer_stays_indent2(tmp_path):
    doc = {"$schema": "https://open-guji.org/schema/entity/v0.2.json", "entities": [{"id": "e1"}]}
    p = tmp_path / "001.entity.json"
    OV.dump_json(str(p), doc)
    assert p.read_text(encoding="utf-8") == json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
