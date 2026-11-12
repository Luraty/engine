from dataclasses import replace

from luraty_engine import (
    COVERAGE_BAND,
    CoverageNoWords,
    CoverageQuery,
    Exposure,
    Retrieval,
    coverage,
    create_profile,
    record,
    unit_key,
    variety,
)
from support.packs import arabic_pack, french_pack

FR = variety("fr")
AR = variety("ar-msa")


def knowing(pack, v, direction, words, language="fr"):
    evidence = []
    for word in words:
        unit = unit_key(direction, v, pack.key(word))
        evidence += [Retrieval(unit=unit, rating="easy", at=1)]
    return record(create_profile(language, 1), evidence)


def text(known, unknown):
    return " ".join(["de"] * known + ["zzz"] * unknown)


knows_de = knowing(french_pack, FR, "recognise", ["de"])


def Q(t, v=FR, direction="recognise", ignore=None):
    return CoverageQuery(text=t, variety=v, direction=direction, ignore=ignore)


def band_of(known, unknown):
    result = coverage(knows_de, french_pack, Q(text(known, unknown)))
    return result.band if result.kind == "measured" else result.kind


def test_reports_no_words():
    nothing = CoverageNoWords(unkeyable_tokens=0, ignored_tokens=0)
    assert coverage(knows_de, french_pack, Q("")) == nothing
    assert coverage(knows_de, french_pack, Q("12345 !!! ...")) == nothing
    assert coverage(knows_de, arabic_pack, Q("bonjour le monde", AR)) == nothing


def test_excludes_a_token_keying_to_nothing():
    passage = "سوق كتاب ـــ مدرسة"
    assert arabic_pack.key("ـــ") == ""
    result = coverage(create_profile("ar", 1), arabic_pack, Q(passage, AR))
    assert result.kind == "too-short"
    assert result.running_tokens == 3
    assert result.unkeyable_tokens == 1
    assert result.known_tokens + result.unknown_tokens == result.running_tokens
    assert result.running_tokens + result.unkeyable_tokens == len(arabic_pack.split(passage))


def test_reports_no_words_with_unkeyable_count():
    assert coverage(create_profile("ar", 1), arabic_pack, Q("ـــ", AR)) == CoverageNoWords(
        unkeyable_tokens=1, ignored_tokens=0
    )


def test_applies_the_length_floor_before_the_ratio():
    assert band_of(11, 0) == "too-short"
    assert band_of(18, 1) == "too-short"
    assert band_of(9, 10) == "too-short"
    result = coverage(knows_de, french_pack, Q(text(11, 0)))
    assert result.kind == "too-short"
    assert result.needs_more_tokens == COVERAGE_BAND.min_tokens - 11
    assert result.unknown_tokens == 0


def test_classifies_the_band_at_every_boundary():
    for known, unknown, expected in [
        (18, 1, "too-short"),
        (19, 1, "in-band"),
        (20, 1, "in-band"),
        (38, 2, "in-band"),
        (37, 3, "too-hard"),
        (49, 1, "in-band"),
        (50, 1, "too-easy"),
        (95, 5, "in-band"),
        (94, 6, "too-hard"),
        (98, 2, "in-band"),
        (99, 1, "too-easy"),
        (100, 0, "too-easy"),
        (0, 100, "too-hard"),
    ]:
        assert band_of(known, unknown) == expected, (known, unknown)


def test_never_consults_rank():
    def boom(_):
        raise RuntimeError("rank() must never be called by coverage()")

    pack = replace(french_pack, rank=boom, compare=lambda a, b: 0)
    coverage(knows_de, pack, Q(text(20, 1)))


def test_does_not_count_exposure_as_knowledge():
    query = Q(text(0, 25))
    fresh = create_profile("fr", 1)
    before = coverage(fresh, french_pack, query)
    unit = unit_key("recognise", FR, french_pack.key("zzz"))
    exposed = record(fresh, [Exposure(unit=unit, at=1) for _ in range(40)])
    assert coverage(exposed, french_pack, query) == before
    tested = record(exposed, [Retrieval(unit=unit, rating="easy", at=2)])
    after = coverage(tested, french_pack, query)
    assert after.kind == "measured"
    assert after.unknown_tokens == 0
    assert after.known_tokens == 25


def test_measures_one_direction_only():
    reader = knowing(french_pack, FR, "recognise", ["de"])
    passage = text(25, 0)
    recognise = coverage(reader, french_pack, Q(passage))
    assert recognise.kind == "measured" and recognise.known_tokens == 25
    produce = coverage(reader, french_pack, Q(passage, direction="produce"))
    assert produce.kind == "measured"
    assert produce.known_tokens == 0
    assert produce.unknown_tokens == produce.running_tokens


def test_measures_one_variety_only():
    lev = variety("ar-levantine")
    msa = knowing(arabic_pack, AR, "recognise", ["سوق"], "ar")
    passage = " ".join(["سوق"] * 25)
    as_msa = coverage(msa, arabic_pack, Q(passage, AR))
    assert as_msa.kind == "measured" and as_msa.known_tokens == 25
    as_lev = coverage(msa, arabic_pack, Q(passage, lev))
    assert as_lev.kind == "measured"
    assert as_lev.known_tokens == 0


def test_reports_a_beginner_as_zero_known():
    result = coverage(create_profile("fr", 1), french_pack, Q(text(0, 30)))
    assert result.kind == "measured"
    assert result.known_tokens == 0
    assert result.band == "too-hard"


def test_counts_running_tokens_not_types():
    result = coverage(knows_de, french_pack, Q("de de de la la"))
    assert result.kind == "too-short"
    assert result.running_tokens == 5
    assert result.known_tokens == 3
    assert result.unknown_tokens == 2
    assert result.unknown_lemmas == ("la",)


def test_lists_unknown_lemmas_once_each():
    result = coverage(knows_de, french_pack, Q("pain de eau pain de eau maison"))
    assert result.kind == "too-short"
    assert result.unknown_lemmas == ("pain", "eau", "maison")


def test_credits_two_surfaces_keying_to_same_lemma():
    result = coverage(knowing(french_pack, FR, "recognise", ["vais"]), french_pack, Q("vais allons vont"))
    assert result.kind == "too-short"
    assert result.known_tokens == 3
    assert result.unknown_lemmas == ()


def test_credits_an_arabic_word_through_its_article():
    result = coverage(knowing(arabic_pack, AR, "recognise", ["مدينة"], "ar"), arabic_pack, Q("المدينة مدينة", AR))
    assert result.kind == "too-short"
    assert result.known_tokens == 2


def test_excludes_caller_marked_tokens_from_the_denominator():
    passage = f"{text(24, 0)} Toyota Senegal"
    counted = coverage(knows_de, french_pack, Q(passage))
    assert counted.kind == "measured"
    assert counted.running_tokens == 26
    assert counted.unknown_tokens == 2
    assert counted.ignored_tokens == 0
    ignored = coverage(knows_de, french_pack, Q(passage, ignore=["Toyota", "Senegal"]))
    assert ignored.kind == "measured"
    assert ignored.running_tokens == 24
    assert ignored.unknown_tokens == 0
    assert ignored.ignored_tokens == 2
    assert ignored.running_tokens + ignored.unkeyable_tokens + ignored.ignored_tokens == len(french_pack.split(passage))


def test_matches_the_raw_surface():
    result = coverage(knows_de, french_pack, Q(f"{text(24, 0)} Marche marche", ignore=["Marche"]))
    assert result.kind == "measured"
    assert result.ignored_tokens == 1
    assert result.running_tokens == 25


def test_does_not_let_an_ignore_list_turn_text_into_no_words_silently():
    assert coverage(knows_de, french_pack, Q("de de de", ignore=["de"])) == CoverageNoWords(
        unkeyable_tokens=0, ignored_tokens=3
    )
