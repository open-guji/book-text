import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from t_entity_split import normalize, split_office, clean_place_span

OFF = {"尚書", "評事", "郎中", "教授"}
INST = {"禮部", "大理寺"}


def test_normalize_defaults():
    assert normalize("尙書郞戸部叅知秘書萬歴") == "尚書郎戶部參知祕書萬曆"


def test_normalize_qing():
    assert normalize("淸江") == "清江"


def test_normalize_uses_file_mapping():
    assert normalize("尙", {"尙": "X"}) == "X"


def test_whole():
    assert split_office("尙書", OFF, INST)["mode"] == "whole"


def test_split_prefix_suffix():
    assert split_office("禮部尚書", OFF, INST) == {"mode": "split", "institution": "禮部", "base": "尚書"}
    assert split_office("大理寺評事", OFF, INST)["base"] == "評事"


def test_tail_only():
    assert split_office("韶州教授", OFF, INST) == {"mode": "tail_only", "scope_text": "韶州", "base": "教授"}


def test_none():
    assert split_office("翰林應奉文字", OFF, INST)["mode"] == "none"


def test_whole_wins_over_split():
    assert split_office("禮部尚書", OFF | {"禮部尚書"}, INST)["mode"] == "whole"


def test_clean_place_span():
    pk = {"臨川", "泰州", "清江"}
    assert clean_place_span("臨川", pk) == ("direct", "臨川")
    assert clean_place_span("臨川人", pk) == ("strip_person", "臨川")
    assert clean_place_span("泰州如臯", pk) == ("prefix", "泰州")
    assert clean_place_span("淸江", pk, {"淸": "清"}) == ("direct", "清江")
    assert clean_place_span("吳玉墀", pk)[0] == "none"
