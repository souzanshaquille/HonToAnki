import json

import pytest

from hontoanki import config


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "_CONFIG_PATH", tmp_path / "config.json")
    return tmp_path


def test_fresh_config_defaults_to_eng(isolated_config):
    assert config.get_default_lang() == "eng"
    assert json.loads((isolated_config / "config.json").read_text()) == {"default_lang": "eng"}


def test_set_and_get_roundtrip(isolated_config):
    config.set_default_lang("ger")
    assert config.get_default_lang() == "ger"


def test_set_invalid_lang_raises(isolated_config):
    with pytest.raises(ValueError):
        config.set_default_lang("xx")


def test_corrupt_config_falls_back(isolated_config):
    (isolated_config / "config.json").write_text("{not json")
    assert config.get_default_lang() == "eng"


def test_unknown_lang_in_config_falls_back(isolated_config):
    (isolated_config / "config.json").write_text(json.dumps({"default_lang": "xx"}))
    assert config.get_default_lang() == "eng"


def test_missing_key_falls_back(isolated_config):
    (isolated_config / "config.json").write_text(json.dumps({}))
    assert config.get_default_lang() == "eng"
