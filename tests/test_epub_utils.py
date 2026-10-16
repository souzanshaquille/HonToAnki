import ebooklib
from ebooklib import epub

from hontoanki.epub_utils import Chapter, get_book_data, get_toc_map, is_japanese


def test_is_japanese():
    assert is_japanese("猫が好き")
    assert is_japanese("hello 猫")
    assert not is_japanese("hello world")
    assert not is_japanese("")


def test_get_toc_map_flat_and_nested():
    toc = [
        ebooklib.epub.Link("ch1.xhtml", "Chapter 1", "ch1"),
        ("Section", [
            ebooklib.epub.Link("ch2.xhtml#frag", "Chapter 2", "ch2"),
        ]),
    ]
    assert get_toc_map(toc) == {"ch1.xhtml": "Chapter 1", "ch2.xhtml": "Chapter 2"}


def test_get_toc_map_first_wins_on_basename_collision():
    toc = [
        ebooklib.epub.Link("a/ch.xhtml", "First", "u1"),
        ebooklib.epub.Link("b/ch.xhtml", "Second", "u2"),
    ]
    assert get_toc_map(toc) == {"ch.xhtml": "First"}


def _make_epub(path, title="Test Book"):
    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("ja")
    c1 = epub.EpubHtml(title="First", file_name="ch1.xhtml", content="<h1>一</h1><p>猫が好きです。今日は良い天気ですね。</p>")
    c2 = epub.EpubHtml(title="Second", file_name="ch2.xhtml", content="<h1>二</h1><p>犬も好きです。明日も頑張りましょう。</p>")
    book.add_item(c1)
    book.add_item(c2)
    book.toc = [epub.Link("ch1.xhtml", "First", "ch1"), epub.Link("ch2.xhtml", "Second", "ch2")]
    book.spine = ["nav", c1, c2]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(path, book)
    return path


def test_get_book_data_parses_chapters(tmp_path):
    epub_path = _make_epub(str(tmp_path / "book.epub"))
    title, chapters = get_book_data(epub_path)
    assert title == "Test Book"
    assert [c.title for c in chapters] == ["First", "Second"]
    assert all(isinstance(c, Chapter) and "猫" in chapters[0].text or "犬" in c.text for c in chapters)


def test_get_book_data_skips_non_japanese(tmp_path):
    book = epub.EpubBook()
    book.set_title("Mixed")
    book.set_language("en")
    en = epub.EpubHtml(title="EN", file_name="en.xhtml", content="<p>" + "hello world " * 20 + "</p>")
    ja = epub.EpubHtml(title="JA", file_name="ja.xhtml", content="<p>猫が好きです。今日は良い天気ですね。明日も散歩に行きましょう。</p>")
    book.add_item(en)
    book.add_item(ja)
    book.toc = [epub.Link("en.xhtml", "EN", "en"), epub.Link("ja.xhtml", "JA", "ja")]
    book.spine = ["nav", en, ja]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    path = str(tmp_path / "mixed.epub")
    epub.write_epub(path, book)

    _, chapters = get_book_data(path)
    assert [c.title for c in chapters] == ["JA"]
