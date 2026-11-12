import math

import pytest

from support.alphabets import any_text, text_for
from support.packs import arabic_pack, french_pack
from support.prop import for_all

PACKS = [("french", french_pack), ("arabic", arabic_pack)]
each = pytest.mark.parametrize("name,pack", PACKS, ids=["french", "arabic"])


@each
def test_key_is_idempotent(name, pack):
    def check(s):
        once = pack.key(s)
        assert pack.key(once) == once

    for_all(check, text_for(pack.id))


@each
def test_key_is_total(name, pack):
    def check(s):
        assert isinstance(pack.key(s), str)

    for_all(check, any_text)


@each
def test_split_never_invents_characters(name, pack):
    def check(s):
        assert len("".join(pack.split(s))) <= len(s)

    for_all(check, text_for(pack.id))


@each
def test_split_never_throws(name, pack):
    for_all(lambda s: pack.split(s) and None, any_text)


@each
def test_split_is_not_call_order_dependent(name, pack):
    def check(s):
        assert pack.split(s) == pack.split(s)

    for_all(check, text_for(pack.id))


@each
def test_compare_accepts_an_answer_against_itself_unless_it_normalizes_away(name, pack):
    def check(s):
        self_score = pack.compare(s, s)
        assert self_score in (0, 1)
        if self_score == 0:
            assert pack.compare("zzq", s) == 0
            assert pack.compare(s, "zzq") == 0

    for_all(check, text_for(pack.id))


@each
def test_compare_is_discriminating(name, pack):
    def check(s):
        if len(pack.split(s)) > 0:
            assert pack.compare(s, "zzqxwv") == 0

    for_all(check, text_for(pack.id))


@each
def test_compare_is_symmetric(name, pack):
    def check(a, b):
        assert pack.compare(a, b) == pack.compare(b, a)

    for_all(check, text_for(pack.id), text_for(pack.id))


@each
def test_compare_returns_a_score_between_0_and_1(name, pack):
    def check(a, b):
        assert 0 <= pack.compare(a, b) <= 1

    for_all(check, text_for(pack.id), text_for(pack.id))


@each
def test_rank_returns_a_positive_integer_or_none(name, pack):
    def check(s):
        r = pack.rank(pack.key(s))
        if r is None:
            return
        assert isinstance(r, int)
        assert r > 0
        assert math.isfinite(r)

    for_all(check, text_for(pack.id))


@each
def test_every_token_can_be_keyed_and_looked_up(name, pack):
    def check(text):
        for token in pack.split(text):
            key = pack.key(token)
            assert isinstance(key, str)
            pack.rank(key)

    for_all(check, text_for(pack.id))
