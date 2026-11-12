from luraty_engine import create_pack
from support.packs import ARABIC_CONFIG, ARABIC_DATA, GERMAN_CONFIG, GERMAN_DATA, arabic_pack, french_pack


def built_ar(lemmas):
    r = create_pack(ARABIC_CONFIG, {**ARABIC_DATA, "lemmas": lemmas})
    assert r.ok
    return r.value


def test_leads_with_the_key():
    for word in ["كتب", "مدرسة", "سوق", "الكتاب", "zzq"]:
        assert arabic_pack.candidates(word)[0] == arabic_pack.key(word)


def test_offers_both_readings():
    assert arabic_pack.candidates("كتب") == ("كتب", "كتاب")


def test_offers_exactly_one_reading_otherwise():
    assert arabic_pack.candidates("سوق") == ("سوق",)
    assert len(arabic_pack.candidates("zzq")) == 1
    assert arabic_pack.rank("سوق") is not None
    assert arabic_pack.rank(arabic_pack.key("zzq")) is None


def test_reads_a_plain_string_entry():
    assert french_pack.key("vais") == "aller"
    assert french_pack.candidates("vais") == ("aller",)


def test_normalizes_every_candidate():
    r = create_pack(GERMAN_CONFIG, {**GERMAN_DATA, "lemmas": {**GERMAN_DATA["lemmas"], "zählt": ["zählen", "zahlen"]}})
    assert r.ok
    assert r.value.candidates("zählt") == ("zaehlen", "zahlen")


def test_drops_a_repeat_only_after_normalizing():
    assert built_ar({"كتب": ["كَتَبَ", "كتب", "كتاب"]}).candidates("كتب") == ("كتب", "كتاب")


def test_all_candidates_normalize_away_means_absent():
    p = built_ar({"سوق": ["ـ", ""]})
    assert p.key("سوق") == "سوق"
    assert p.candidates("سوق") == ("سوق",)


def test_promotes_the_next_reading_when_first_is_unusable():
    p = built_ar({"كتب": ["ـ", "كتاب"]})
    assert p.key("كتب") == "كتاب"
    assert p.candidates("كتب") == ("كتاب",)


def test_treats_an_empty_list_the_same():
    assert built_ar({"سوق": []}).candidates("سوق") == ("سوق",)


def test_ignores_a_non_string_in_the_list():
    assert built_ar({"كتب": ["كتب", None, 7, "كتاب"]}).candidates("كتب") == ("كتب", "كتاب")


def test_never_returns_an_empty_list():
    for word in ["", " ", "ـ", "؟", " ", "\ud800"]:
        assert len(arabic_pack.candidates(word)) >= 1


def test_keeps_the_author_order():
    p = built_ar({"كتب": ["كتاب", "كتب"]})
    assert p.candidates("كتب") == ("كتاب", "كتب")
    assert p.key("كتب") == "كتاب"


def test_first_row_wins_a_duplicate_surface():
    assert built_ar({"كَتَب": ["كتب", "كتاب"], "كتب": ["مدرس"]}).candidates("كتب") == ("كتب", "كتاب")
