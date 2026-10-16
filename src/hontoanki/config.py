import json
import os
import sys
from pathlib import Path


LANGUAGES = {
    "eng": "English",
    "spa": "Spanish",
    "fre": "French",
    "ger": "German",
    "rus": "Russian",
    "dut": "Dutch",
    "hun": "Hungarian",
    "swe": "Swedish",
    "slv": "Slovenian",
}


def get_data_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "HonToAnki"


_CONFIG_DIR = get_data_dir()
_CONFIG_PATH = _CONFIG_DIR / "config.json"
_DEFAULT_CONFIG = {"default_lang": "eng"}


def _ensure_config():
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "w") as f:
            json.dump(_DEFAULT_CONFIG, f)


def _read_config():
    _ensure_config()
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return dict(_DEFAULT_CONFIG)


def _write_config(config):
    _ensure_config()
    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_default_lang():
    cfg = _read_config()
    lang = cfg.get("default_lang", "eng")
    return lang if lang in LANGUAGES else "eng"


def set_default_lang(lang):
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language code: {lang}")
    cfg = _read_config()
    cfg["default_lang"] = lang
    _write_config(cfg)
