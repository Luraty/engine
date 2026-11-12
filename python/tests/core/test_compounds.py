from luraty_engine import create_pack

CONFIG = {
    "id": "de-test",
    "tokenize": {"strategy": "regex", "pattern": "[a-zA-ZäöüÄÖÜßẞ]+"},
    "normalize": ["lowercase", "stripPunctuation", "foldGermanUmlauts", "foldLatinDiacritics"],
    "compare": ["lowercase", "stripPunctuation", "foldGermanUmlauts", "foldLatinDiacritics"],
    "compounds": {"minPartLength": 4, "linkers": ["", "s", "n", "en", "es", "er"]},
}
WORDS = (
    "bahnhof strasse haupt kranken versicherung arbeit losigkeit bundes regierung kinder "
    "garten spiel platz woerter buch hand tasche schreib tisch fenster brett haus tuer "
    "sonne schein blume topf zeit punkt fahr karte"
)


def _pack():
    built = create_pack(CONFIG, {"frequency": WORDS})
    assert built.ok
    return built.value


de = _pack()


def test_keys_a_compound_to_its_head():
    assert de.key("Bahnhofstraße") == "strasse"
    assert de.key("Blumentopf") == "topf"
    assert de.key("Schreibtisch") == "tisch"
    assert de.key("Handtasche") == "tasche"
    assert de.key("Fahrkarte") == "karte"


def test_handles_the_linking_morphemes():
    assert de.key("Bundesregierung") == "regierung"
    assert de.key("Blumentopf") == "topf"
    assert de.key("Sonnenschein") == "schein"


def test_splits_three_part_compounds():
    assert de.key("Hauptbahnhofstrasse") == "strasse"


def test_never_splits_a_word_the_list_knows():
    for word in ["fenster", "garten", "strasse", "bahnhof", "versicherung", "haus"]:
        assert de.key(word) == word, word


def test_leaves_a_word_alone_when_parts_are_not_real():
    assert de.key("Xyzabcdefgh") == "xyzabcdefgh"
    assert de.key("Quatschwort") == "quatschwort"


def test_refuses_parts_shorter_than_the_minimum():
    assert de.key("Haustür") == "tuer"
    loose = create_pack({**CONFIG, "compounds": {"minPartLength": 2, "linkers": [""]}}, {"frequency": "haus tuer ei so an um eisen"})
    assert loose.ok
    assert de.key("eisen") == "eisen"


def test_is_off_unless_a_pack_asks():
    config = {k: v for k, v in CONFIG.items() if k != "compounds"}
    no_compounds = create_pack(config, {"frequency": WORDS})
    assert no_compounds.ok
    assert no_compounds.value.key("Bahnhofstraße") == "bahnhofstrasse"


def test_is_idempotent():
    for word in ["Bahnhofstraße", "Bundesregierung", "Hauptbahnhofstrasse", "Haustür"]:
        once = de.key(word)
        assert de.key(once) == once, word
