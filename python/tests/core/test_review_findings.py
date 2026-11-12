import dataclasses

import pytest

from luraty_engine import (
    Claim,
    PlanOptions,
    PriorClaimed,
    Retrieval,
    ScopeAll,
    ScopeSkill,
    create_profile,
    instant,
    deserialize,
    has_standing_claim,
    plan,
    record,
    serialize,
    summarize,
    unit_key,
    unit_state,
    variety,
)
from luraty_engine.model import UNMET

V = variety("de")


def U(word):
    return unit_key("recognise", V, word)


DAY = 86_400
RATING = {"known": "good", "unknown": "again"}


def drill(word, outcome, d):
    return Retrieval(unit=U(word), rating=RATING[outcome], at=d)


def P(p, d, new=5):
    return plan(p, PlanOptions(now=d, max_items=5, max_new=new))


def test_refuses_day_zero():
    assert instant(0) is None
    assert instant(1) == 1


def test_does_not_read_a_first_day_drill_as_never_asked():
    p = record(create_profile("de", 1), [drill("haus", "known", 1)])
    assert unit_state(p, U("haus")).last_asked == 1
    assert P(p, 2).items[0].why == "learning"


def test_does_not_count_a_day_one_refuted_claim_as_standing():
    p = record(create_profile("de", 1), [Claim(unit=U("haus"), at=1), drill("haus", "unknown", 1)])
    assert not has_standing_claim(unit_state(p, U("haus")))
    s = summarize(p, ScopeAll())
    assert s.claims_refuted == 1
    assert s.claims_standing == 0


def test_gives_the_same_answer_at_every_epoch():
    def build(epoch):
        return record(
            create_profile("de", epoch),
            [Claim(unit=U("a"), at=epoch), drill("a", "known", epoch), drill("a", "unknown", epoch + DAY)],
        )

    early = summarize(build(1), ScopeAll())
    late = summarize(build(20_661), ScopeAll())
    assert early.claims_confirmed == late.claims_confirmed
    assert early.claims_standing == late.claims_standing
    assert early.claims_refuted == late.claims_refuted
    assert early.claims_confirmed == 1


def test_says_never_measured():
    placed = record(create_profile("de", 20_661), [Claim(unit=U("a"), at=20_661), Claim(unit=U("b"), at=20_661)])
    r = P(placed, 20_661, 0).reassess
    assert r.kind == "never-measured"
    assert r.claims_standing == 2
    assert not hasattr(r, "days_since_proven")


def test_reports_a_real_span_once_proven():
    p = record(create_profile("de", 20_661), [drill("a", "known", 20_661)])
    r = P(p, 20_661 + 40 * DAY, 0).reassess
    assert r.kind == "due"
    assert r.days_since_proven == 40


def test_sorts_stuck():
    p = create_profile("de", 1)
    for i in range(1, 7):
        p = record(p, [drill("zzz", "unknown", i)])
    for i in range(1, 7):
        p = record(p, [drill("aaa", "unknown", i)])
    loaded = deserialize(serialize(p))
    assert loaded.ok
    assert P(p, 20) == P(loaded.value, 20)
    assert P(p, 20).stuck == (U("aaa"), U("zzz"))


def test_unmet_is_frozen():
    p = create_profile("de", 1)
    state = unit_state(p, U("never-met"))
    assert state is UNMET
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.card = "review"
    with pytest.raises(dataclasses.FrozenInstanceError):
        UNMET.prior.kind = "claimed"
    assert unit_state(p, U("another")).card == "new"


def test_drops_a_unit_whose_key_cannot_be_parsed():
    bogus = unit_key("recognise", V, "")
    p = record(create_profile("de", 1), [Retrieval(unit=bogus, rating="good", at=1), drill("hund", "known", 1)])
    assert summarize(p, ScopeAll()).units == 1
    assert summarize(p, ScopeSkill(variety=V, modality="recognise")).units == 1
    assert len(p.units) == 2


def test_serializes_a_claimed_prior_and_a_graduated_card():
    p = record(create_profile("de", 1), [Claim(unit=U("a"), at=7)])
    p = record(p, [drill("a", "known", 8)])
    text = serialize(p)
    assert text.startswith('{"v":1,"language":"de","now":1,"units":[["recognise:de:a",1,8,0,7,2,0,')
    back = deserialize(text)
    assert back.ok
    assert back.value == p
    assert unit_state(back.value, U("a")).prior == PriorClaimed(on=7)
