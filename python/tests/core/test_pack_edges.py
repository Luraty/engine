import re
from collections import OrderedDict

from luraty_engine import create_pack
from support.packs import FRENCH_CONFIG, FRENCH_DATA, french_pack


def build(**over):
    return create_pack({**FRENCH_CONFIG, **over}, FRENCH_DATA)


def test_names_a_missing_id():
    r = build(id="")
    assert not r.ok
    assert r.error.kind == "malformed"
    assert re.search("id", r.error.message, re.I)


def test_names_an_over_long_pattern():
    long = f"[{'a-z' * 100}]+"
    assert len(long) > 200
    r = build(tokenize={"strategy": "regex", "pattern": long})
    assert not r.ok
    assert re.search("long", r.error.message, re.I)


def test_quotes_the_offending_pattern_back():
    r = build(tokenize={"strategy": "regex", "pattern": "a+"})
    assert not r.ok
    assert "a+" in r.error.message
    assert "[a-z]+" in r.error.message


def test_names_an_unparseable_character_class():
    r = build(tokenize={"strategy": "regex", "pattern": "[\\u{ZZZZ}]+"})
    assert not r.ok
    assert len(r.error.message) > 10


def test_rejects_an_unknown_normalize_step():
    r = build(normalize=["stripDiacritics"])
    assert not r.ok
    assert r.error.kind == "malformed"
    assert "stripDiacritics" in r.error.message
    assert "foldLatinDiacritics" in r.error.message


def test_rejects_an_unknown_compare_step_at_build_time():
    r = build(compare=["normalizeAlef"])
    assert not r.ok
    assert "normalizeAlef" in r.error.message


def test_rejects_a_step_list_that_is_not_a_list():
    r = build(normalize="lowercase")
    assert not r.ok
    assert "normalize" in r.error.message


def test_rejects_a_name_only_reachable_through_the_prototype_chain():
    for name in ["constructor", "toString", "__proto__", "valueOf"]:
        assert not build(normalize=[name]).ok, name


def test_accepts_every_step_the_engine_implements():
    every = [
        "lowercase",
        "stripPunctuation",
        "stripArabicDiacritics",
        "stripTatweel",
        "normalizeArabicAlef",
        "normalizeArabicFinals",
        "foldLatinDiacritics",
        "foldGermanUmlauts",
    ]
    assert build(normalize=every, compare=every).ok


def test_works_with_no_affix_config():
    r = build()
    no_affixes = create_pack({k: v for k, v in FRENCH_CONFIG.items() if k != "affixes"}, FRENCH_DATA)
    assert r.ok
    assert no_affixes.ok
    assert no_affixes.value.key("l'automne") == "l'automne"


def test_tries_the_longest_prefix_first():
    pack = create_pack(
        {
            **FRENCH_CONFIG,
            "tokenize": {"strategy": "regex", "pattern": "[a-z]+"},
            "normalize": ["lowercase"],
            "affixes": {"prefixes": ["a", "ab"], "onlyIfRemainderKnown": True},
            "compare": ["lowercase"],
        },
        {"frequency": "cd bcd"},
    )
    assert pack.ok
    assert pack.value.key("abcd") == "cd"


def test_defaults_only_if_remainder_known_to_safe():
    pack = create_pack({**FRENCH_CONFIG, "affixes": {"prefixes": ["d'"]}}, FRENCH_DATA)
    assert pack.ok
    assert pack.value.key("d'zzz") == "d'zzz"


def test_never_strips_a_prefix_that_is_the_entire_word():
    pack = create_pack(
        {
            **FRENCH_CONFIG,
            "tokenize": {"strategy": "regex", "pattern": "[a-z]+"},
            "normalize": ["lowercase"],
            "affixes": {"prefixes": ["de"], "onlyIfRemainderKnown": False},
            "compare": ["lowercase"],
        },
        {"frequency": "de la"},
    )
    assert pack.ok
    assert pack.value.key("de") == "de"


def test_gives_rank_1_to_the_first_word():
    assert french_pack.rank("de") == 1


def test_keeps_the_first_occurrence_when_a_word_repeats():
    pack = create_pack(FRENCH_CONFIG, {"frequency": "a b a"})
    assert pack.ok
    assert pack.value.rank("a") == 1


def test_ignores_runs_of_whitespace():
    pack = create_pack(FRENCH_CONFIG, {"frequency": "  a \n\n b  \t c "})
    assert pack.ok
    assert pack.value.rank("a") == 1
    assert pack.value.rank("b") == 2
    assert pack.value.rank("c") == 3


def test_compare_ignores_surrounding_whitespace():
    assert french_pack.compare("  marche  ", "marche") == 1
    assert french_pack.compare("marche", "  marche  ") == 1
    assert french_pack.compare("\tmarche\n", "marche") == 1


def test_compare_does_not_ignore_inner_whitespace():
    assert french_pack.compare("mar che", "marche") == 0


def test_split_returns_nothing_for_no_matches():
    assert french_pack.split("123 456") == ()
    assert french_pack.split("") == ()


def test_split_is_unaffected_by_call_count():
    text = "je vais au marche"
    first = french_pack.split(text)
    assert french_pack.split(text) == first
    assert french_pack.split(text) == first
    assert len(first) == 4


ROWS = {"chevaux": "cheval", "chevals": "cheval", "portes": ["porte", "porter"]}
from_record = create_pack(FRENCH_CONFIG, {**FRENCH_DATA, "lemmas": ROWS})
from_map = create_pack(FRENCH_CONFIG, {**FRENCH_DATA, "lemmas": OrderedDict(ROWS)})


def test_builds_from_either_shape():
    assert from_record.ok
    assert from_map.ok


def test_keys_every_surface_identically():
    for surface in ["chevaux", "chevals", "portes", "cheval", "inconnu"]:
        assert from_map.value.key(surface) == from_record.value.key(surface)
    assert from_map.value.key("chevaux") == "cheval"


def test_offers_the_same_candidates():
    for surface in ["portes", "chevaux", "inconnu"]:
        assert from_map.value.candidates(surface) == from_record.value.candidates(surface)
    assert from_map.value.candidates("portes") == ("porte", "porter")
    assert from_map.value.candidates("portes")[0] == from_map.value.key("portes")


def test_drops_an_unusable_row_from_a_map_as_from_an_object():
    bad = {"": "cheval", "chevaux": ""}
    rec = create_pack(FRENCH_CONFIG, {**FRENCH_DATA, "lemmas": bad})
    mapped = create_pack(FRENCH_CONFIG, {**FRENCH_DATA, "lemmas": OrderedDict(bad)})
    assert mapped.ok == rec.ok
    assert mapped.value.key("chevaux") == rec.value.key("chevaux")


def test_is_not_fooled_by_an_empty_map():
    mapped = create_pack(FRENCH_CONFIG, {**FRENCH_DATA, "lemmas": OrderedDict()})
    rec = create_pack(FRENCH_CONFIG, {**FRENCH_DATA, "lemmas": {}})
    assert mapped.ok and rec.ok
    assert mapped.value.key("chevaux") == rec.value.key("chevaux")
