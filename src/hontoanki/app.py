import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import fugashi
import genanki
import orjson
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.prompt import Confirm, Prompt

from .anki_utils import create_model, extract_data, stable_id
from .config import LANGUAGES, get_default_lang, set_default_lang
from .dictionary import load_dictionary
from .epub_utils import get_book_data, is_japanese

console = Console()
EXPORTS_DIR = Path.cwd() / "exports"


def _safe_filename(name: str, limit: int = 100) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return (safe[:limit].rstrip() or "book")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert Japanese EPUB books to Anki flashcard decks.",
        epilog="Without arguments, runs in interactive mode.",
    )
    parser.add_argument("--epub", "-e", metavar="PATH", help="Path to .epub file (headless mode)")
    parser.add_argument("--particles", "-p", action="store_true", help="Include particles/grammar")
    parser.add_argument("--output", "-o", metavar="DIR", help="Output directory (default: ./exports)")
    parser.add_argument("--json", "-j", action="store_true", help="Also export vocabulary as JSON")
    parser.add_argument("--tts", action="store_true", help="Add text-to-speech audio (AnkiDroid/AnkiMobile)")
    parser.add_argument("--lang", "-l", metavar="CODE", choices=list(LANGUAGES.keys()),
                        help="Dictionary language code (one-time override)")
    parser.add_argument("--download-lang", "--dl", metavar="CODE", choices=list(LANGUAGES.keys()),
                        help="Download dictionary for a language and exit")
    parser.add_argument("--set-default-lang", metavar="CODE", choices=list(LANGUAGES.keys()),
                        help="Persist a default language for future runs")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed parsing info")
    return parser.parse_args(argv)


def pause():
    try:
        input("\nPress Enter to exit...")
    except (KeyboardInterrupt, EOFError):
        pass


def _prompt_lang(default_lang):
    codes = ", ".join(LANGUAGES.keys())
    console.print(f"Using [bold]{LANGUAGES[default_lang]}[/bold] ({default_lang}) — Enter to keep, or pick: {codes}")
    return Prompt.ask("Enter language code", default=default_lang, choices=list(LANGUAGES.keys()))


def _prompt_epub_path() -> Path:
    while True:
        raw = Prompt.ask("\n[bold yellow]Paste .epub Book Path[/bold yellow]").strip().strip('"')
        epub_path = Path(raw)
        if not raw:
            console.print("[bold red]Please paste a path to an .epub file.[/bold red]")
        elif not epub_path.exists() or not epub_path.is_file():
            console.print(f"[bold red]File not found:[/bold red] {epub_path}")
        elif epub_path.suffix.lower() != ".epub":
            console.print(f"[bold red]Not an .epub file:[/bold red] {epub_path}")
        else:
            return epub_path


def _exit_or_pause(args, msg, code=1):
    console.print(msg)
    if args.epub:
        sys.exit(code)
    pause()
    sys.exit(code)


def is_wanted_pos(node, include_particles):
    pos = node.feature.pos1
    if include_particles:
        return True
    exclude = ["助詞", "助動詞", "記号", "感動詞", "補助記号"]
    return pos not in exclude


def _open_in_anki(path):
    if not Confirm.ask("\nOpen in Anki?", default=True):
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
        console.print("[green]Launching Anki...[/green]")
    except Exception as e:
        console.print(f"[yellow]Could not open Anki: {e}[/yellow]")


def _extract_lemmas(tagger, text, include_particles) -> list[str]:
    lemmas = []
    for node in tagger(text):
        if not is_japanese(node.surface):
            continue
        if not is_wanted_pos(node, include_particles):
            continue
        lemma = node.feature.lemma
        lemmas.append(lemma if (lemma and lemma != "*") else node.surface)
    return lemmas


def _chapter_words(tagger, text, dict_index, include_particles, seen, lang="eng"):
    lemmas = _extract_lemmas(tagger, text, include_particles)
    freq = Counter(lemmas)
    result = []
    for word in sorted(freq, key=lambda x: -freq[x]):
        if word in seen:
            continue
        seen.add(word)
        entries = dict_index.get(word, [])
        if not entries:
            continue
        entry = extract_data(entries[0], lang)
        result.append((word, entry, freq[word]))
    return result


def _process_chapters(tagger, chapters, model, dict_index, book_title, include_particles, lang="eng"):
    seen = set()
    decks = []
    vocab_data = []

    with Progress() as progress:
        task = progress.add_task("Processing chapters...", total=len(chapters))

        for i, chapter in enumerate(chapters):
            chapter_num = f"{i + 1:02d}"
            chapter_label = f"{chapter_num}_{chapter.title}"

            words = _chapter_words(tagger, chapter.text, dict_index, include_particles, seen, lang)
            if not words:
                progress.console.print(f"  [dim]- {chapter_label} (No new words)[/dim]")
                progress.update(task, advance=1)
                continue

            deck_name = f"{book_title} Vocab::{chapter_label}"
            deck = genanki.Deck(stable_id(deck_name), deck_name)
            chapter_vocab = []

            for word, entry, freq in words:
                chapter_vocab.append({
                    "word": str(word),
                    "reading": str(entry.reading),
                    "meaning": str(entry.meaning),
                    "frequency": freq,
                    "example": str(entry.example),
                })
                deck.add_note(genanki.Note(
                    model=model,
                    fields=[
                        str(word), str(entry.reading), str(entry.meaning),
                        f"Ch.{chapter_num} (Freq: {freq})",
                        str(entry.example),
                    ],
                ))

            decks.append(deck)
            vocab_data.append({
                "number": chapter_num,
                "title": chapter.title,
                "words": chapter_vocab,
            })

            progress.console.print(
                f"  ({i + 1}) [green]✓[/green] {deck_name} ([bold]{len(words)}[/bold] new words)"
            )
            progress.update(task, advance=1)

    return vocab_data, decks


def _export_json(path, book_title, vocab_data):
    payload = {"book": book_title, "chapters": vocab_data}
    with open(path, "wb") as f:
        f.write(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
    console.print(f"[green]JSON export saved to {path}[/green]")


def _show_summary(apkg_path, vocab_data, decks, has_json):
    total_cards = sum(len(c["words"]) for c in vocab_data)
    total_chapters = len(decks)
    lines = [
        "[bold green]Success![/bold green]",
        f"Deck exported: {apkg_path}",
        f"Total cards: [bold]{total_cards}[/bold] across [bold]{total_chapters}[/bold] chapters",
    ]
    if has_json:
        lines.append(f"Vocabulary JSON: {apkg_path.with_suffix('.json')}")
    lines.append("Import the .apkg into Anki to start studying.")
    console.print(Panel("\n".join(lines)))


def main():
    try:
        _main()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Cancelled.[/yellow]")
        sys.exit(1)


def _main():
    args = _parse_args()
    console.print(Panel.fit("[bold blue]Epub to Anki (Chapter Mode)[/bold blue]"))

    if args.set_default_lang:
        set_default_lang(args.set_default_lang)
        lang_name = LANGUAGES[args.set_default_lang]
        console.print(f"[green]Default language set to [bold]{lang_name}[/bold] ({args.set_default_lang})[/green]")

    if args.download_lang:
        lang_name = LANGUAGES[args.download_lang]
        console.print(f"Downloading dictionary: [bold]{lang_name}[/bold] ({args.download_lang})...")
        try:
            load_dictionary(args.download_lang)
            console.print(f"[green]Dictionary downloaded: [bold]{lang_name}[/bold] ({args.download_lang})[/green]")
        except RuntimeError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)
        return

    default_lang = get_default_lang()
    lang = args.lang or default_lang

    if not args.epub:
        lang = _prompt_lang(default_lang)

    lang_name = LANGUAGES.get(lang, lang.upper())
    console.print(f"Dictionary: [bold]{lang_name}[/bold] ({lang})")

    tagger = fugashi.Tagger()

    try:
        dict_index = load_dictionary(lang)
    except RuntimeError as e:
        _exit_or_pause(args, f"[bold red]Error:[/bold red] {e}")

    if args.epub:
        epub_path = Path(args.epub)
        include_particles = args.particles
    else:
        epub_path = _prompt_epub_path()
        include_particles = Confirm.ask("Include particles/grammar?", default=False)

    if not epub_path.exists():
        _exit_or_pause(args, f"[bold red]File not found:[/bold red] {epub_path}")
        return

    with console.status("[bold green]Reading EPUB spine...[/bold green]"):
        book_title, chapters = get_book_data(epub_path)

    if args.verbose:
        console.print(f"[dim]Title: {book_title}, Chapters in TOC: {len(chapters)}[/dim]")

    if not chapters:
        _exit_or_pause(args, "[bold red]No Japanese content found in this EPUB![/bold red]")
        return

    model = create_model(with_tts=args.tts)
    vocab_data, decks = _process_chapters(tagger, chapters, model, dict_index, book_title, include_particles, lang)

    if not decks:
        _exit_or_pause(args, "[bold red]No cards generated![/bold red]")
        return

    output_dir = Path(args.output) if args.output else EXPORTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{_safe_filename(book_title)}_Vocab.apkg"

    genanki.Package(decks).write_to_file(out_path)

    if args.json:
        _export_json(out_path.with_suffix(".json"), book_title, vocab_data)

    _show_summary(out_path, vocab_data, decks, args.json)

    if args.epub:
        return
    _open_in_anki(out_path)
    pause()


if __name__ == "__main__":
    main()
