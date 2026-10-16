from hontoanki.anki_utils import WordEntry, create_model, extract_data, stable_id


def _sense(glosses, examples=None):
    sense = {"gloss": [{"text": g} for g in glosses]}
    if examples is not None:
        sense["examples"] = examples
    return sense


def test_stable_id_deterministic_and_int():
    assert stable_id("abc") == stable_id("abc")
    assert isinstance(stable_id("abc"), int)
    assert stable_id("a") != stable_id("b")


def test_extract_data_reading_prefers_kana():
    entry = {
        "kanji": [{"text": "猫"}],
        "kana": [{"text": "ねこ"}],
        "sense": [_sense(["cat"])],
    }
    got = extract_data(entry)
    assert (got.reading, got.meaning) == ("ねこ", "cat")


def test_extract_data_falls_back_to_kanji():
    entry = {"kanji": [{"text": "猫"}], "kana": [], "sense": [_sense(["cat"])]}
    assert extract_data(entry).reading == "猫"


def test_extract_data_unknown_when_no_senses():
    entry = {"kanji": [], "kana": [{"text": "ねこ"}], "sense": []}
    assert extract_data(entry) == WordEntry("ねこ", "Unknown", "")


def test_extract_data_joins_first_sense_glosses():
    entry = {
        "kana": [{"text": "はし"}],
        "sense": [_sense(["chopsticks", "bridge"]), _sense(["edge"])],
    }
    assert extract_data(entry).meaning == "chopsticks; bridge"


def test_extract_data_picks_matching_example():
    examples = [{
        "sentences": [
            {"lang": "jpn", "text": "猫が好き。"},
            {"lang": "eng", "text": "I like cats."},
        ]
    }]
    entry = {"kana": [{"text": "ねこ"}], "sense": [_sense(["cat"], examples)]}
    got = extract_data(entry)
    assert "猫が好き。" in got.example
    assert "I like cats." in got.example


def test_extract_data_no_matching_translation_gives_empty_example():
    examples = [{
        "sentences": [
            {"lang": "jpn", "text": "猫が好き。"},
            {"lang": "spa", "text": "Me gustan los gatos."},
        ]
    }]
    entry = {"kana": [{"text": "ねこ"}], "sense": [_sense(["cat"], examples)]}
    assert extract_data(entry, "eng").example == ""


def test_create_model_fields():
    model = create_model()
    assert [f["name"] for f in model.fields] == ["Word", "Reading", "Meaning", "Frequency", "Example"]


def test_create_model_lang_attributes():
    model = create_model()
    qfmt = model.templates[0]["qfmt"]
    afmt = model.templates[0]["afmt"]
    assert 'lang="ja"' in qfmt
    assert 'lang="ja"' in afmt
    assert "tts" not in qfmt


def test_create_model_tts_opt_in():
    model = create_model(with_tts=True)
    assert "{{tts ja_JP:Word}}" in model.templates[0]["qfmt"]


def test_example_has_no_inline_styles():
    examples = [{
        "sentences": [
            {"lang": "jpn", "text": "猫が好き。"},
            {"lang": "eng", "text": "I like cats."},
        ]
    }]
    entry = {"kana": [{"text": "ねこ"}], "sense": [{"gloss": [{"text": "cat"}], "examples": examples}]}
    got = extract_data(entry).example
    assert "style=" not in got
    assert 'lang="ja"' in got
