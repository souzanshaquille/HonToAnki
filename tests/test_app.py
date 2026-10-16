from types import SimpleNamespace

import pytest

from hontoanki import app
from hontoanki.app import (
    _chapter_words,
    _extract_lemmas,
    _parse_args,
    _safe_filename,
    is_wanted_pos,
)


def _node(surface, pos1="名詞", lemma=None):
    return SimpleNamespace(surface=surface, feature=SimpleNamespace(pos1=pos1, lemma=lemma))


def test_safe_filename_strips_illegal_chars():
    assert _safe_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_safe_filename_blank_falls_back():
    assert _safe_filename("   ") == "book"
    assert _safe_filename("") == "book"


def test_safe_filename_truncates():
    assert len(_safe_filename("x" * 200)) == 100


def test_exports_dir_defaults_to_cwd():
    from pathlib import Path
    assert app.EXPORTS_DIR == Path.cwd() / "exports"


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.epub is None
    assert args.particles is False
    assert args.output is None
    assert args.json is False
    assert args.lang is None


def test_parse_args_rejects_bad_lang():
    with pytest.raises(SystemExit):
        _parse_args(["--lang", "xx"])


def test_is_wanted_pos_filters_particles():
    assert not is_wanted_pos(_node("は", pos1="助詞"), False)
    assert not is_wanted_pos(_node("。", pos1="記号"), False)
    assert is_wanted_pos(_node("猫"), False)
    assert is_wanted_pos(_node("は", pos1="助詞"), True)


def test_extract_lemmas_skips_non_japanese_and_particles():
    tagger = lambda text: [  # noqa: E731
        _node("猫", lemma="猫"),
        _node("は", pos1="助詞", lemma="は"),
        _node("hello", lemma="hello"),
        _node("走る", lemma="走る"),
    ]
    assert _extract_lemmas(tagger, "猫はhello走る", False) == ["猫", "走る"]
    assert _extract_lemmas(tagger, "猫はhello走る", True) == ["猫", "は", "走る"]


def test_extract_lemmas_falls_back_to_surface():
    tagger = lambda text: [_node("猫", lemma="*"), _node("犬", lemma=None)]  # noqa: E731
    assert _extract_lemmas(tagger, "猫犬", False) == ["猫", "犬"]


def _entry_for(word):
    return {"kana": [{"text": word}], "sense": [{"gloss": [{"text": f"{word}-meaning"}]}]}


def test_chapter_words_sorts_by_frequency_and_skips_unknown():
    tagger = lambda text: [_node("猫", lemma="猫")] * 3 + [_node("犬", lemma="犬"), _node("鳥", lemma="鳥")]  # noqa: E731
    seen = set()
    words = _chapter_words(tagger, "text", {"猫": [_entry_for("猫")], "犬": [_entry_for("犬")]}, False, seen)
    assert [(w, f) for w, _, f in words] == [("猫", 3), ("犬", 1)]
    assert seen == {"猫", "犬", "鳥"}


def test_chapter_words_dedups_across_chapters():
    tagger = lambda text: [_node("猫", lemma="猫")]  # noqa: E731
    index = {"猫": [_entry_for("猫")]}
    seen = set()
    assert len(_chapter_words(tagger, "t", index, False, seen)) == 1
    assert _chapter_words(tagger, "t", index, False, seen) == []


def test_prompt_lang_returns_choice(monkeypatch):
    from hontoanki import app as appmod
    monkeypatch.setattr(appmod.Prompt, "ask", lambda *a, **k: "spa")
    assert appmod._prompt_lang("eng") == "spa"


def test_prompt_epub_path_reprompts_until_valid(tmp_path, monkeypatch):
    from hontoanki import app as appmod
    good = tmp_path / "book.epub"
    good.write_bytes(b"fake")
    answers = iter(["", str(tmp_path / "missing.epub"), str(tmp_path / "notes.txt"), str(good)])
    monkeypatch.setattr(appmod.Prompt, "ask", lambda *a, **k: next(answers))
    (tmp_path / "notes.txt").write_text("x")
    assert appmod._prompt_epub_path() == good


def test_exit_or_pause_headless_exits_nonzero():
    from hontoanki import app as appmod
    args = SimpleNamespace(epub="book.epub")
    with pytest.raises(SystemExit) as exc:
        appmod._exit_or_pause(args, "msg")
    assert exc.value.code == 1


def test_exit_or_pause_interactive_pauses_then_exits(monkeypatch):
    from hontoanki import app as appmod
    args = SimpleNamespace(epub=None)
    monkeypatch.setattr(appmod, "pause", lambda: None)
    with pytest.raises(SystemExit) as exc:
        appmod._exit_or_pause(args, "msg")
    assert exc.value.code == 1


@pytest.mark.parametrize("exc", [KeyboardInterrupt, EOFError])
def test_main_handles_cancel_cleanly(monkeypatch, exc):
    from hontoanki import app as appmod

    def boom():
        raise exc()

    monkeypatch.setattr(appmod, "_main", boom)
    with pytest.raises(SystemExit):
        appmod.main()
