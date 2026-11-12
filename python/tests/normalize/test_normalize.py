from luraty_engine.normalize import apply_step, apply_steps
from support.alphabets import arabic_text, french_text
from support.prop import constant_from, for_all, one_of


def strip_ar(s):
    return apply_step("stripArabicDiacritics", s)


def test_removes_every_mark_in_the_fathatan_sukun_range():
    for cp in range(0x064B, 0x0653):
        assert strip_ar(f"سوق{chr(cp)}") == "سوق", hex(cp)


def test_removes_every_mark_in_the_quranic_annotation_block():
    for cp in range(0x06D6, 0x06EE):
        assert strip_ar(f"سوق{chr(cp)}") == "سوق", hex(cp)


def test_leaves_letters_either_side_of_interior_annotation_joined():
    assert strip_ar("هُدًۭى") == "هدى"


def test_does_not_strip_letters_immediately_outside_the_block():
    assert strip_ar("ە") == "ە"
    assert strip_ar("ۮ") == "ۮ"


def test_removes_the_superscript_alef_and_quranic_marks():
    assert strip_ar("سٰوق") == "سوق"
    for cp in range(0x0653, 0x0656):
        assert strip_ar(f"سوق{chr(cp)}") == "سوق"


def test_leaves_letters_either_side_of_the_range_alone():
    assert strip_ar("ي") == "ي"
    assert strip_ar("ٖ") == "ٖ"
    assert strip_ar("سوق") == "سوق"


def test_diacritics_leaves_latin_untouched():
    assert strip_ar("marché") == "marché"


def test_strip_tatweel_removes_only_u0640():
    assert apply_step("stripTatweel", "كتـــاب") == "كتاب"
    assert apply_step("stripTatweel", "كتاب") == "كتاب"
    assert apply_step("stripTatweel", "ؿف") == "ؿف"


def test_folds_every_alef_variant():
    for variant in ["آ", "أ", "إ", "ٱ"]:
        assert apply_step("normalizeArabicAlef", variant) == "ا", variant


def test_leaves_the_plain_alef_and_everything_else_alone():
    fold = lambda s: apply_step("normalizeArabicAlef", s)  # noqa: E731
    assert fold("ا") == "ا"
    assert fold("ب") == "ب"
    assert fold("ؤ") == "ؤ"


def test_folds_teh_marbuta_and_alef_maksura():
    assert apply_step("normalizeArabicFinals", "مدينة") == "مدينه"
    assert apply_step("normalizeArabicFinals", "على") == "علي"
    assert apply_step("normalizeArabicFinals", "هي") == "هي"
    assert apply_step("normalizeArabicFinals", "ب") == "ب"


def fold_latin(s):
    return apply_step("foldLatinDiacritics", s)


def test_folds_every_accented_vowel():
    for given, expected in [
        ("àáâãäåā", "aaaaaaa"),
        ("èéêëē", "eeeee"),
        ("ìíîïī", "iiiii"),
        ("òóôõöøō", "ooooooo"),
        ("ùúûüū", "uuuuu"),
        ("ýÿ", "yy"),
    ]:
        assert fold_latin(given) == expected, given


def test_folds_letters_that_expand_to_two():
    assert fold_latin("æ") == "ae"
    assert fold_latin("œ") == "oe"
    assert fold_latin("ß") == "ss"


def test_folds_n_tilde_and_c_cedilla():
    assert fold_latin("ñ") == "n"
    assert fold_latin("ç") == "c"


def test_leaves_unaccented_latin_and_other_scripts_alone():
    assert fold_latin("marche") == "marche"
    assert fold_latin("سوق") == "سوق"


def test_latin_fold_is_case_sensitive_by_design():
    assert fold_latin("É") == "É"
    assert apply_steps(["lowercase", "foldLatinDiacritics"], "É") == "e"


def fold_de(s):
    return apply_step("foldGermanUmlauts", s)


def test_folds_each_umlaut_to_two_letters():
    assert fold_de("ä") == "ae"
    assert fold_de("ö") == "oe"
    assert fold_de("ü") == "ue"
    assert fold_de("ß") == "ss"


def test_keeps_apart_the_six_pairs():
    for with_umlaut, without in [
        ("schön", "schon"),
        ("zählen", "zahlen"),
        ("fördern", "fordern"),
        ("drücken", "drucken"),
        ("schwül", "schwul"),
        ("Bär", "Bar"),
    ]:
        assert fold_de(with_umlaut) != fold_de(without)


def test_folds_the_capitals_too():
    assert fold_de("Ä") == "ae"
    assert fold_de("Ö") == "oe"
    assert fold_de("Ü") == "ue"
    assert fold_de("ẞ") == "ss"
    assert fold_de("BÄR") == "BaeR"


def test_german_leaves_everything_else_alone():
    assert fold_de("haus") == "haus"
    assert fold_de("café") == "café"
    assert fold_de("سوق") == "سوق"
    assert fold_de("") == ""


def strip_p(s):
    return apply_step("stripPunctuation", s)


def test_removes_latin_punctuation():
    assert strip_p("a.b,c;d:e!f?g") == "abcdefg"
    assert strip_p("«quoted»") == "quoted"


def test_removes_arabic_punctuation():
    assert strip_p("سوق،") == "سوق"
    assert strip_p("سوق؟") == "سوق"
    assert strip_p("سوق؛") == "سوق"
    assert strip_p("٪") == ""


def test_keeps_the_straight_apostrophe():
    assert strip_p("l'automne") == "l'automne"


def test_removes_the_typographic_quotes():
    assert strip_p("‘a’") == "a"
    assert strip_p("“a”") == "a"


def test_keeps_letters_and_digits():
    assert strip_p("abc123سوق") == "abc123سوق"


def test_lowercases_latin_and_leaves_arabic_alone():
    assert apply_step("lowercase", "MARCHÉ") == "marché"
    assert apply_step("lowercase", "سوق") == "سوق"


def test_apply_steps_in_order():
    assert apply_steps(["lowercase", "foldLatinDiacritics"], "MARCHÉ") == "marche"
    assert apply_steps(["foldLatinDiacritics", "lowercase"], "MARCHÉ") == "marché"


def test_apply_steps_empty_list_returns_input():
    assert apply_steps([], "MARCHÉ") == "MARCHÉ"


STEPS = [
    "lowercase",
    "stripPunctuation",
    "stripArabicDiacritics",
    "stripTatweel",
    "normalizeArabicAlef",
    "normalizeArabicFinals",
    "foldLatinDiacritics",
]


def test_apply_steps_never_throws_never_non_string():
    def check(s):
        out = apply_steps(STEPS, s)
        assert isinstance(out, str)
        assert len(out) <= len(s) * 2

    for_all(check, one_of(arabic_text, french_text))


def test_every_step_is_idempotent():
    def check(s, step):
        once = apply_step(step, s)
        assert apply_step(step, once) == once

    for_all(check, one_of(arabic_text, french_text), constant_from(*STEPS))
