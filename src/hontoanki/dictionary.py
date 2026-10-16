import json
import re
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import orjson
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from .config import LANGUAGES, get_data_dir

console = Console()

GITHUB_RELEASES = "https://github.com/scriptin/jmdict-simplified/releases"
USER_AGENT = "HonToAnki/0.2.0"
CACHE_TTL = 3600  # 1 hour


def _dict_pattern(lang: str = "eng"):
    if lang == "eng":
        return "jmdict-examples-eng-*.json"
    return f"jmdict-{lang}-*.json"


def find_dict_file(dict_dir: Path, lang: str = "eng"):
    matches = sorted(dict_dir.glob(_dict_pattern(lang)), key=lambda p: p.name)
    return matches[-1] if matches else None


def _get_latest_tag():
    cache_path = get_data_dir() / "tag_cache.json"

    if cache_path.exists():
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            if time.time() - cached["timestamp"] < CACHE_TTL:
                return cached["tag"]
        except (OSError, ValueError, KeyError):
            pass

    req = Request(f"{GITHUB_RELEASES}/latest", headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urlopen(req, timeout=15) as resp:
            final_url = resp.url
    except (URLError, HTTPError, TimeoutError) as e:
        raise RuntimeError(f"Could not check latest dictionary version: {e}") from e

    m = re.search(r"/tag/([^/]+)$", final_url)
    if not m:
        raise RuntimeError(f"Could not extract tag from redirect URL: {final_url}")
    tag = m.group(1)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({"timestamp": time.time(), "tag": tag}, f)

    return tag


def _get_asset_name(tag: str, lang: str) -> str:
    if lang == "eng":
        return f"jmdict-examples-eng-{tag}.json.zip"
    return f"jmdict-{lang}-{tag}.json.zip"


def _quote_tag(tag: str) -> str:
    return tag.replace("+", "%2B")


def _download_asset(url: str, dest_dir: Path, display_name: str):
    zip_path = dest_dir / "dict.zip"
    console.print(f"Downloading [cyan]{display_name}[/cyan]...")

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            with Progress(
                TextColumn("[green]Downloading dictionary..."),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task("download", total=total)
                with open(zip_path, "wb") as f:
                    while chunk := resp.read(8192):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
    except (URLError, HTTPError, TimeoutError) as e:
        if zip_path.exists():
            zip_path.unlink()
        raise RuntimeError(f"Dictionary download failed: {e}") from e

    console.print("[green]Extracting...[/green]")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()


def download_dictionary(dict_dir: Path, lang: str = "eng"):
    console.print("[bold]Dictionary not found. Downloading...[/bold]")

    tag = _get_latest_tag()
    asset_name = _get_asset_name(tag, lang)
    download_url = f"{GITHUB_RELEASES}/download/{_quote_tag(tag)}/{asset_name}"

    _download_asset(download_url, dict_dir, asset_name)

    found = find_dict_file(dict_dir, lang)
    if not found:
        raise RuntimeError(f"Extracted dictionary not found in {dict_dir}")

    for old in sorted(dict_dir.glob(_dict_pattern(lang)), key=lambda p: p.name)[:-1]:
        if old != found:
            old.unlink()

    console.print(f"[green]Dictionary saved to {found}[/green]")
    return found


def load_dictionary(lang: str = "eng"):
    data_dir = get_data_dir()
    dict_dir = data_dir / "dict" / lang
    dict_dir.mkdir(parents=True, exist_ok=True)

    dict_path = find_dict_file(dict_dir, lang)

    if not dict_path:
        old_dict_dir = data_dir / "dict"
        if lang == "eng":
            dict_path = find_dict_file(old_dict_dir, lang)

    if not dict_path:
        project_dict = Path(__file__).parent.parent.parent / "dict"
        dict_path = find_dict_file(project_dict, lang)

    if not dict_path:
        dict_path = download_dictionary(dict_dir, lang)

    with console.status("[bold green]Loading JMdict..."):
        with open(dict_path, "rb") as f:
            jmdict = orjson.loads(f.read())

        idx = defaultdict(list)
        words = jmdict["words"]

        for entry in words:
            kanji = entry.get("kanji")
            if kanji:
                for k in kanji:
                    idx[k["text"]].append(entry)
            kana = entry.get("kana")
            if kana:
                for r in kana:
                    idx[r["text"]].append(entry)

    lang_name = LANGUAGES.get(lang, lang.upper())
    console.print(f"[green]Dictionary loaded ({len(idx)} entries, {lang_name}).[/green]")
    return idx
