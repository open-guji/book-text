import importlib.util
import json
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('check_license', os.path.join(HERE, '..', 'check_license.py'))
check_license = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_license)


def test_license_rejects_null_and_unknown():
    with tempfile.TemporaryDirectory() as root:
        for i, lic in enumerate(['CC0 1.0', None, '未知']):
            d = os.path.join(root, 'Book', 'a', 'b', 'c', f'id{i}')
            os.makedirs(d)
            with open(os.path.join(d, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump({'id': f'id{i}', 'versions': [{'key': 'default', 'license': lic}]}, f, ensure_ascii=False)
        counts, bad = check_license.check(root)
        assert len(bad) == 2
        assert {v for _, v in bad} == {None, '未知'}
        assert counts["'CC0 1.0'"] == 1
