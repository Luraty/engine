from functools import reduce

from luraty_engine import create_profile, deserialize, is_unit_key, record, serialize, variety
from luraty_engine._js import is_integer
from support.evidence import arb_evidence
from support.prop import any_code_point_string, array, for_all, json_text, mapped, one_of

AR = variety("ar-msa")
LEV = variety("ar-levantine")
WORDS = ["سوق", "كتاب", "a", "Z", "é", "0", "99", "a:b", "ñ", " ", "ZZZ"]
ARB_EVIDENCE = one_of(arb_evidence(AR, WORDS, max_at=500 * 86_400), arb_evidence(LEV, WORDS, max_at=500 * 86_400))
ARB_PROFILE = mapped(array(ARB_EVIDENCE, max_length=60), lambda ev: record(create_profile("ar", 1), ev))


def test_round_trips():
    def check(profile):
        back = deserialize(serialize(profile))
        assert back.ok
        assert back.value == profile

    for_all(check, ARB_PROFILE)


def test_is_idempotent():
    def check(profile):
        once = serialize(profile)
        back = deserialize(once)
        assert back.ok
        assert serialize(back.value) == once

    for_all(check, ARB_PROFILE)


def test_is_canonical_regardless_of_how_built():
    def check(evidence):
        batched = record(create_profile("ar", 1), evidence)
        one_by_one = reduce(lambda p, e: record(p, [e]), evidence, create_profile("ar", 1))
        assert serialize(one_by_one) == serialize(batched)

    for_all(check, array(ARB_EVIDENCE, max_length=40))


def test_never_throws_on_arbitrary_text():
    for_all(lambda text: deserialize(text) and None, any_code_point_string())


def test_never_throws_on_arbitrary_json():
    for_all(lambda text: deserialize(text) and None, json_text())


def test_never_returns_a_half_built_profile():
    def check(text):
        result = deserialize(text)
        if result.ok:
            assert isinstance(result.value.language, str)
            assert is_integer(result.value.now)
            assert all(is_unit_key(k) for k in result.value.units)
        else:
            assert len(result.error.message) > 0

    for_all(check, json_text())
