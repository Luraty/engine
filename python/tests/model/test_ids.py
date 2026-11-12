from luraty_engine import DIRECTIONS, instant, parse_unit_key, unit_key, variety
from support.alphabets import any_text, arabic_text, french_text
from support.prop import constant_from, filtered, for_all, one_of


def test_variety_accepts_ordinary_ids():
    assert variety("fr") == "fr"
    assert variety("ar-msa") == "ar-msa"
    assert variety("ar-levantine") == "ar-levantine"


def test_variety_rejects_an_empty_id():
    assert variety("") is None


def test_variety_rejects_a_colon():
    assert variety("ar:msa") is None
    assert variety(":") is None
    assert variety("a:") is None


def test_day_accepts_whole_days_and_refuses_zero():
    assert instant(0) is None
    assert instant(1) == 1
    assert instant(365) == 365


def test_day_rejects_anything_not_a_whole_day():
    assert instant(1.5) is None
    assert instant(-1) is None
    assert instant(float("nan")) is None
    assert instant(float("inf")) is None


def test_directions_lists_exactly_the_directions():
    assert sorted(DIRECTIONS) == ["produce", "recognise"]


AR = variety("ar-msa")


def test_unit_key_builds_the_documented_shape():
    assert unit_key("recognise", AR, "سوق") == "recognise:ar-msa:سوق"
    assert unit_key("produce", AR, "سوق") == "produce:ar-msa:سوق"


def test_unit_key_round_trips_every_part():
    parts = parse_unit_key(unit_key("produce", AR, "كتاب"))
    assert (parts.modality, parts.variety, parts.word) == ("produce", "ar-msa", "كتاب")


def test_unit_key_round_trips_a_word_containing_colons():
    assert parse_unit_key(unit_key("recognise", AR, "a:b:c")).word == "a:b:c"


def test_parse_unit_key_rejects_malformed_keys():
    for bad in [
        "",
        "recognise",
        "recognise:ar-msa",
        ":ar-msa:سوق",
        "recognise::سوق",
        "recognise:ar-msa:",
        "sideways:ar-msa:سوق",
        "RECOGNISE:ar-msa:سوق",
    ]:
        assert parse_unit_key(bad) is None, bad


def test_parse_unit_key_accepts_both_directions_and_only_those():
    for direction in DIRECTIONS:
        assert parse_unit_key(f"{direction}:fr:x").modality == direction
    assert parse_unit_key("recognize:fr:x") is None


def test_unit_key_round_trips_for_any_word_in_any_script():
    def check(direction, v, word):
        parts = parse_unit_key(unit_key(direction, variety(v), word))
        assert (parts.modality, parts.variety, parts.word) == (direction, v, word)

    for_all(
        check,
        constant_from(*DIRECTIONS),
        constant_from("fr", "ar-msa", "ar-levantine"),
        filtered(one_of(arabic_text, french_text), lambda w: len(w) > 0),
    )


def test_parse_unit_key_never_throws():
    for_all(lambda s: parse_unit_key(s) and None, any_text)
