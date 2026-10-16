import io
import json
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError

import orjson
import pytest

from hontoanki import dictionary
from hontoanki.dictionary import (
    _download_asset,
    _get_asset_name,
    _get_latest_tag,
    _quote_tag,
    download_dictionary,
    find_dict_file,
    load_dictionary,
)


def _touch(directory: Path, name: str) -> Path:
    p = directory / name
    p.write_text("{}")
    return p


def test_find_dict_file_picks_newest(tmp_path):
    _touch(tmp_path, "jmdict-examples-eng-1.0.json")
    newest = _touch(tmp_path, "jmdict-examples-eng-2.0.json")
    assert find_dict_file(tmp_path, "eng") == newest


def test_find_dict_file_none_when_missing(tmp_path):
    assert find_dict_file(tmp_path, "eng") is None


def test_find_dict_file_non_english_pattern(tmp_path):
    _touch(tmp_path, "jmdict-examples-eng-9.9.json")
    assert find_dict_file(tmp_path, "spa") is None
    spa = _touch(tmp_path, "jmdict-spa-1.0.json")
    assert find_dict_file(tmp_path, "spa") == spa


def test_asset_names():
    assert _get_asset_name("3.6.0", "eng") == "jmdict-examples-eng-3.6.0.json.zip"
    assert _get_asset_name("3.6.0", "spa") == "jmdict-spa-3.6.0.json.zip"


def test_quote_tag():
    assert _quote_tag("3.6.0+20250101") == "3.6.0%2B20250101"
    assert _quote_tag("3.6.0") == "3.6.0"


class _FakeResp:
    def __init__(self, url="https://github.com/scriptin/jmdict-simplified/releases/tag/3.6.0",
                 body: bytes = b"", headers=None):
        self.url = url
        self._body = io.BytesIO(body)
        self.headers = headers or {}

    def read(self, n=-1):
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@contextmanager
def _mock_urlopen(monkeypatch, resp=None, exc=None):
    def fake(req, timeout=None):
        if exc is not None:
            raise exc
        return resp

    monkeypatch.setattr(dictionary, "urlopen", fake)
    yield fake


def _isolate_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(dictionary, "get_data_dir", lambda: tmp_path)


def test_get_latest_tag_uses_cache(tmp_path, monkeypatch):
    _isolate_data_dir(monkeypatch, tmp_path)
    (tmp_path / "tag_cache.json").write_text(json.dumps({"timestamp": time.time(), "tag": "cached"}))
    with _mock_urlopen(monkeypatch, exc=AssertionError("must not hit network")):
        assert _get_latest_tag() == "cached"


def test_get_latest_tag_falls_back_on_corrupt_cache(tmp_path, monkeypatch):
    _isolate_data_dir(monkeypatch, tmp_path)
    (tmp_path / "tag_cache.json").write_text("{corrupt")
    with _mock_urlopen(monkeypatch, resp=_FakeResp()):
        assert _get_latest_tag() == "3.6.0"


def test_get_latest_tag_network_error(tmp_path, monkeypatch):
    _isolate_data_dir(monkeypatch, tmp_path)
    with _mock_urlopen(monkeypatch, exc=URLError("offline")):
        with pytest.raises(RuntimeError, match="Could not check latest"):
            _get_latest_tag()


def test_get_latest_tag_bad_redirect(tmp_path, monkeypatch):
    _isolate_data_dir(monkeypatch, tmp_path)
    with _mock_urlopen(monkeypatch, resp=_FakeResp(url="https://example.com/nothing")):
        with pytest.raises(RuntimeError, match="Could not extract tag"):
            _get_latest_tag()


def _zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_download_asset_extracts_and_cleans_zip(tmp_path):
    payload = _zip_bytes({"jmdict-examples-eng-1.0.json": b"{}"})
    resp = _FakeResp(body=payload, headers={"Content-Length": str(len(payload))})
    import hontoanki.dictionary as dmod
    orig = dmod.urlopen
    dmod.urlopen = lambda req, timeout=None: resp
    try:
        _download_asset("http://example.com/x.zip", tmp_path, "x.zip")
    finally:
        dmod.urlopen = orig
    assert (tmp_path / "jmdict-examples-eng-1.0.json").exists()
    assert not (tmp_path / "dict.zip").exists()


def test_download_asset_failure_removes_partial_zip(tmp_path, monkeypatch):
    (tmp_path / "dict.zip").write_bytes(b"partial")
    with _mock_urlopen(monkeypatch, exc=URLError("boom")):
        with pytest.raises(RuntimeError, match="Dictionary download failed"):
            _download_asset("http://example.com/x.zip", tmp_path, "x.zip")
    assert not (tmp_path / "dict.zip").exists()


def test_download_dictionary_removes_superseded(tmp_path, monkeypatch):
    _touch(tmp_path, "jmdict-spa-1.0.json")
    fresh = tmp_path / "jmdict-spa-2.0.json"
    monkeypatch.setattr(dictionary, "_get_latest_tag", lambda: "2.0")

    def fake_download(url, dest_dir, display_name):
        fresh.write_text("{}")

    monkeypatch.setattr(dictionary, "_download_asset", fake_download)
    found = download_dictionary(tmp_path, "spa")
    assert found == fresh
    assert not (tmp_path / "jmdict-spa-1.0.json").exists()


def test_load_dictionary_builds_index(tmp_path, monkeypatch):
    _isolate_data_dir(monkeypatch, tmp_path)
    entry = {
        "kanji": [{"text": "猫"}],
        "kana": [{"text": "ねこ"}],
        "sense": [{"gloss": [{"text": "cat"}]}],
    }
    dict_dir = tmp_path / "dict" / "eng"
    dict_dir.mkdir(parents=True)
    (dict_dir / "jmdict-examples-eng-1.0.json").write_bytes(
        orjson.dumps({"words": [entry]})
    )
    idx = load_dictionary("eng")
    assert idx["猫"] == [entry]
    assert idx["ねこ"] == [entry]
