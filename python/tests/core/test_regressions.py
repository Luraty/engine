from luraty_engine import Retrieval, create_pack, create_profile, is_known, record, unit_key, unit_state, variety
from support.packs import FRENCH_CONFIG, FRENCH_DATA, arabic_pack, french_pack, german_pack

AR = variety("ar-msa")


def test_compare_rejects_an_answer_key_normalizing_to_nothing():
    assert french_pack.compare("!!!", "?") == 0
    assert french_pack.compare("", "...") == 0
    assert french_pack.compare("", "") == 0
    assert arabic_pack.compare("؟؟", "،") == 0
    assert french_pack.compare("marché", "MARCHE") == 1
    assert arabic_pack.compare("سُوق", "سوق") == 1


def test_grades_trailing_punctuation_identically():
    for given, expected in [("marche.", "marche"), ("marche ", "marche"), ("MARCHE", "marche")]:
        assert french_pack.compare(given, expected) == 1, given
    assert arabic_pack.compare("سوق.", "سوق") == 1
    assert arabic_pack.compare("سوق ", "سوق") == 1


def test_parses_a_newline_separated_frequency_list():
    newlines = create_pack(FRENCH_CONFIG, {**FRENCH_DATA, "frequency": "\n".join(FRENCH_DATA["frequency"].split(" "))})
    assert newlines.ok
    assert newlines.value.rank("de") == 1
    assert newlines.value.key("l'automne") == "automne"


def test_refuses_a_catastrophic_pattern():
    for evil in ["(a+)+b", "(a|a)*$", "^(a+)+$"]:
        assert not create_pack({**FRENCH_CONFIG, "tokenize": {"strategy": "regex", "pattern": evil}}, FRENCH_DATA).ok, evil
    for good in ["[a-z]+", "[\\u0600-\\u06FF]+", "[a-zA-Zà-öø-ÿ']+"]:
        assert create_pack({**FRENCH_CONFIG, "tokenize": {"strategy": "regex", "pattern": good}}, FRENCH_DATA).ok, good


def test_never_rewinds_any_anchor():
    k = unit_key("recognise", AR, "سوق")
    p = record(
        create_profile("ar", 1),
        [Retrieval(unit=k, rating="good", at=39), Retrieval(unit=k, rating="good", at=40)],
    )
    before = unit_state(p, k)
    assert (before.last_seen, before.last_asked, before.last_proven) == (40, 40, 40)
    assert is_known(before)
    p = record(p, [Retrieval(unit=k, rating="good", at=3)])
    after = unit_state(p, k)
    assert after.last_seen == 40
    assert after.seen == 3
    assert after.last_proven == 40


def test_keys_words_that_collide_with_object_prototype():
    for word in ["constructor", "toString", "valueOf", "__proto__", "hasOwnProperty"]:
        assert isinstance(french_pack.key(word), str)
        assert isinstance(arabic_pack.key(word), str)


def test_strips_a_french_elision():
    assert french_pack.key("l'automne") == "automne"
    assert french_pack.key("L'AUTOMNE") == "automne"


def test_indexes_frequency_by_normalized_form():
    assert arabic_pack.key("المدينة") == arabic_pack.key("مدينة")
    assert arabic_pack.key("المدرسة") == arabic_pack.key("مدرسة")
    assert arabic_pack.key("الحكومة") == arabic_pack.key("حكومة")
    for word in ["على", "أن", "إلى", "مدرسة", "جريدة", "حكومة", "مدينة"]:
        assert arabic_pack.rank(arabic_pack.key(word)) is not None, word
    assert arabic_pack.key("السوق") == "سوق"
    assert french_pack.rank("marche") == french_pack.rank(french_pack.key("marché"))
    assert french_pack.key("est") == "etre"
    assert french_pack.rank("etre") is None


def test_keeps_german_umlaut_pairs_apart():
    for umlaut, plain in [
        ("schön", "schon"),
        ("zählen", "zahlen"),
        ("fördern", "fordern"),
        ("drücken", "drucken"),
        ("schwül", "schwul"),
        ("Bär", "Bar"),
        ("wählen", "Wahlen"),
    ]:
        assert german_pack.key(umlaut) != german_pack.key(plain), umlaut
    assert german_pack.key("schön") == "schoen"
    assert german_pack.key("über") == "ueber"
    assert german_pack.key("Straße") == "strasse"
    assert french_pack.key("marché") == french_pack.key("marche")


def test_grades_german_case_and_eszett():
    assert german_pack.compare("STRASSE", "Straße") == 1
    assert german_pack.compare("grosse", "große") == 1
    assert german_pack.compare("schon", "schön") == 0


def test_refuses_a_german_ge_strip_without_a_word():
    assert german_pack.key("gesehen") == "sehen"
    assert german_pack.key("gelesen") == "lesen"
    assert german_pack.key("Geld") == "geld"
    assert german_pack.key("gehen") == "gehen"
    assert german_pack.key("gerade") == "gerade"


def test_indexes_the_lemma_table_by_normalized_form():
    assert german_pack.key("läuft") == "laufen"
    assert german_pack.key("fährt") == "fahren"
    assert german_pack.key("trägt") == "tragen"
    assert german_pack.key("zählt") == "zaehlen"
    assert german_pack.key("zählen") == "zaehlen"
    assert german_pack.key("zählt") == german_pack.key("zählen")
    assert german_pack.key("zahlt") == "zahlen"
    assert german_pack.key("zählt") != german_pack.key("zahlt")
