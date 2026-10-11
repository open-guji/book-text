import importlib.util
import json
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('check_license', os.path.join(HERE, '..', 'check_license.py'))
check_license = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_license)


def test_license_rejects_null_unknown_and_cc0_on_non_original():
    cases = [('CC0 1.0', True), (None, False), ('未知', False), ('CC0 1.0', False)]
    with tempfile.TemporaryDirectory() as root:
        for i, (lic, orig) in enumerate(cases):
            d = os.path.join(root, 'Book', 'a', 'b', 'c', f'id{i}')
            os.makedirs(d)
            v = {'key': 'default', 'license': lic, 'is_original': orig}
            with open(os.path.join(d, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump({'id': f'id{i}', 'versions': [v]}, f, ensure_ascii=False)
        counts, bad = check_license.check(root)
        assert len(bad) == 3
        reasons = ' '.join(r for _, r in bad)
        assert 'license=None' in reasons and "license='未知'" in reasons and 'CC0 1.0 仅限 is_original' in reasons
        assert counts["'CC0 1.0'"] == 2
