from luraty_engine import create_pack
from support.packs import FRENCH_CONFIG, FRENCH_DATA, arabic_pack, french_pack


def test_rejects_a_pack_with_no_id():
    assert not create_pack({**FRENCH_CONFIG, "id": ""}, FRENCH_DATA).ok


def test_rejects_an_unknown_tokenize_strategy_without_throwing():
    bad = create_pack({**FRENCH_CONFIG, "tokenize": {"strategy": "dictionary", "pattern": "x"}}, FRENCH_DATA)
    assert not bad.ok
    assert "dictionary" in bad.error.message


def test_rejects_an_invalid_pattern_at_load_time():
    assert not create_pack({**FRENCH_CONFIG, "tokenize": {"strategy": "regex", "pattern": "[a-"}}, FRENCH_DATA).ok


def test_accepts_an_empty_frequency_list():
    empty = create_pack(FRENCH_CONFIG, {"frequency": ""})
    assert empty.ok
    assert empty.value.rank("de") is None


def test_does_not_fall_through_for_constructor():
    for word in ["constructor", "toString", "valueOf", "__proto__", "hasOwnProperty"]:
        assert isinstance(french_pack.key(word), str)
        assert isinstance(arabic_pack.key(word), str)


def test_french_splits_on_words():
    assert french_pack.split("Je vais au marché.") == ("Je", "vais", "au", "marché")


def test_french_maps_inflected_forms():
    assert french_pack.key("vais") == "aller"
    assert french_pack.key("allez") == "aller"
    assert french_pack.key("vont") == "aller"


def test_french_folds_accents_and_case():
    assert french_pack.key("MARCHÉ") == french_pack.key("marche")


def test_french_strips_elision_only_when_real_word_remains():
    assert french_pack.key("l'automne") == "automne"
    assert french_pack.key("d'zzz") == "d'zzz"


def test_french_ranks():
    de, pain = french_pack.rank("de"), french_pack.rank("pain")
    assert de is not None and pain is not None
    assert de < pain
    assert french_pack.rank("zzzznotaword") is None


def test_french_accepts_answer_differing_by_accent_or_case():
    assert french_pack.compare("MARCHE", "marché") == 1
    assert french_pack.compare("pain", "vendre") == 0


def test_arabic_splits():
    assert arabic_pack.split("ذهبت إلى السوق") == ("ذهبت", "إلى", "السوق")


def test_arabic_strips_the_definite_article():
    assert arabic_pack.key("السوق") == "سوق"


def test_arabic_refuses_to_strip_when_remainder_not_a_word():
    assert arabic_pack.key("ولد") == "ولد"
    assert arabic_pack.key("وقت") == "وقت"


def test_arabic_ignores_optional_diacritics():
    assert arabic_pack.key("سُوق") == "سوق"
    assert arabic_pack.compare("سُوق", "سوق") == 1


def test_arabic_collapses_alef_spellings():
    assert arabic_pack.key("أحمد") == arabic_pack.key("احمد")
    assert arabic_pack.key("إلى") == arabic_pack.key("الى")


def test_arabic_collapses_teh_marbuta_and_alef_maksura():
    assert arabic_pack.key("مدينة") == arabic_pack.key("مدينه")


def test_arabic_ignores_tatweel():
    assert arabic_pack.key("كتـــاب") == "كتاب"


def test_gives_both_packs_the_same_shape():
    for pack in [french_pack, arabic_pack]:
        assert isinstance(pack.id, str)
        for name in ("split", "key", "candidates", "rank", "compare"):
            assert callable(getattr(pack, name))


def test_produces_different_key_counts():
    fr = [french_pack.key(t) for t in french_pack.split("Je vais au marché")]
    ar = [arabic_pack.key(t) for t in arabic_pack.split("ذهبت إلى السوق")]
    assert len(fr) == 4
    assert len(ar) == 3
    assert "سوق" in ar
