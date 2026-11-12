import pytest

from luraty_engine import create_pack
from support.alphabets import any_text, text_for
from support.packs import ARABIC_CONFIG, ARABIC_DATA, arabic_pack, french_pack
from support.prop import array, constant_from, for_all, mapped

PACKS = [("french", french_pack), ("arabic", arabic_pack)]


@pytest.mark.parametrize("name,pack", PACKS, ids=["french", "arabic"])
def test_never_returns_an_empty_list(name, pack):
    for_all(lambda s: _ge1(pack.candidates(s)), text_for(pack.id))


def _ge1(offered):
    assert len(offered) >= 1


@pytest.mark.parametrize("name,pack", PACKS, ids=["french", "arabic"])
def test_leads_with_exactly_what_key_returns(name, pack):
    def check(s):
        assert pack.candidates(s)[0] == pack.key(s)

    for_all(check, text_for(pack.id))


@pytest.mark.parametrize("name,pack", PACKS, ids=["french", "arabic"])
def test_is_total(name, pack):
    def check(s):
        offered = pack.candidates(s)
        assert isinstance(offered, tuple)
        for reading in offered:
            assert isinstance(reading, str)

    for_all(check, any_text)


@pytest.mark.parametrize("name,pack", PACKS, ids=["french", "arabic"])
def test_is_stable(name, pack):
    def check(s):
        assert pack.candidates(s) == pack.candidates(s)

    for_all(check, text_for(pack.id))


AMBIGUOUS_ROWS = {
    "كتب": ["كتب", "كتاب"],
    "مدرسة": ["مدرسة", "مدرس"],
    "عامل": ["عامل", "عمل", "معمل"],
    "سوق": ["سوق"],
    "بيت": ["بيت", "بيوت"],
    "ولد": ["ولد", "ميلاد", "والد"],
}
_built = create_pack(
    ARABIC_CONFIG,
    {**ARABIC_DATA, "frequency": f"{ARABIC_DATA['frequency']} كتاب مدرس عمل معمل بيوت ميلاد والد", "lemmas": AMBIGUOUS_ROWS},
)
assert _built.ok
ambiguous = _built.value
AMBIGUOUS_TEXT = mapped(array(constant_from(*AMBIGUOUS_ROWS, "zzq", "في"), min_length=1, max_length=12), " ".join)
seen = {"multi": 0, "single": 0}


def test_holds_every_law_on_forms_with_more_than_one_reading():
    def check(text):
        for token in ambiguous.split(text):
            offered = ambiguous.candidates(token)
            seen["multi" if len(offered) > 1 else "single"] += 1
            assert len(offered) >= 1
            assert offered[0] == ambiguous.key(token)
            assert len(set(offered)) == len(offered)
            for reading in offered:
                assert ambiguous.key(reading) == reading

    for_all(check, AMBIGUOUS_TEXT)


def test_actually_reached_both_branches():
    assert seen["multi"] > 0, f"no multi-candidate form was generated ({seen['single']} single-candidate tokens seen)"
    assert seen["single"] > 0, "no single-candidate form was ever generated"
