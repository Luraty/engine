"""`serialize` / `deserialize`: the v1 wire format."""

import json

import pytest

from luraty_engine import (
    PROFILE_SCHEMA_VERSION,
    Claim,
    Exposure,
    Help,
    Retrieval,
    create_profile,
    deserialize,
    record,
    serialize,
    unit_key,
    variety,
)

V = variety("ar")
T0 = 1_800_000_000


def U(word):
    return unit_key("recognise", V, word)


def rich_profile():
    return record(
        create_profile("ar", T0),
        [
            Claim(unit=U("claimed"), at=T0),
            Retrieval(unit=U("claimed"), rating="good", at=T0 + 1),
            Retrieval(unit=U("learning"), rating="good", at=T0),
            Retrieval(unit=U("relearning"), rating="easy", at=T0),
            Retrieval(unit=U("relearning"), rating="again", at=T0 + 9 * 86_400),
            Exposure(unit=U("seen"), at=T0),
            Help(unit=U("helped"), at=T0 + 5),
        ],
    )


def test_is_at_schema_one():
    assert PROFILE_SCHEMA_VERSION == 1


def test_round_trips_every_card_state():
    p = rich_profile()
    back = deserialize(serialize(p))
    assert back.ok
    assert back.value == p
    assert {state.card for state in p.units.values()} == {"new", "learning", "review", "relearning"}


def test_is_canonical_regardless_of_insertion_order():
    p = rich_profile()
    reversed_units = dict(reversed(list(p.units.items())))
    from luraty_engine import Profile

    assert serialize(Profile(language="ar", now=T0, units=reversed_units)) == serialize(p)


def test_writes_the_documented_row_order():
    p = record(create_profile("ar", T0), [Claim(unit=U("a"), at=T0), Exposure(unit=U("a"), at=T0 + 2)])
    assert serialize(p) == (
        '{"v":1,"language":"ar","now":1800000000,"units":'
        '[["recognise:ar:a",1,1800000002,0,1800000000,0,0,0,0,0,0,0,0,0]]}'
    )


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("not json", "not-json"),
        ("[]", "malformed"),
        ('{"v":0,"language":"ar","now":1,"units":[]}', "no-migration"),
        ('{"v":2,"language":"ar","now":1,"units":[]}', "from-the-future"),
        ('{"v":1,"language":"ar","units":[]}', "malformed"),
        ('{"v":1,"language":"ar","now":1,"units":[["recognise:ar:a",1]]}', "malformed"),
        ('{"v":1,"language":"ar","now":1,"units":[["recognise:ar:a",1,1,0,null,9,0,0,0,0,0,0,0,0]]}', "malformed"),
        ('{"v":1,"language":"ar","now":1,"units":[["recognise:ar:a",1,1,0,null,2,0,-1,0,0,0,0,0,0]]}', "malformed"),
        ('{"v":1,"language":"ar","now":1,"units":[["bad",1,1,0,null,0,0,0,0,0,0,0,0,0]]}', "malformed"),
    ],
)
def test_rejects_bad_input_without_throwing(text, kind):
    decoded = deserialize(text)
    assert not decoded.ok
    assert decoded.error.kind == kind


def test_rejects_a_duplicate_unit():
    row = ["recognise:ar:a", 1, 1, 0, None, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    text = json.dumps({"v": 1, "language": "ar", "now": 1, "units": [row, row]})
    assert deserialize(text).error.kind == "malformed"
