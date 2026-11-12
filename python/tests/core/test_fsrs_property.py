"""Laws that hold for any evidence: the fold, determinism, and the session contract."""

from functools import reduce

from luraty_engine import (
    NEVER,
    PlanOptions,
    create_profile,
    deserialize,
    is_known,
    plan,
    record,
    serialize,
    variety,
)
from support.evidence import arb_evidence
from support.prop import array, boolean, for_all, integer

AR = variety("ar")
WORDS = ["كتاب", "قلم", "بيت", "مدرسة", "ولد", "بنت", "سوق", "ماء"]
EVIDENCE = array(arb_evidence(AR, WORDS, max_at=200 * 86_400), max_length=60)
START = 1


def fold(evidence):
    return record(create_profile("ar", START), sorted(evidence, key=lambda e: e.at))


def test_batch_equals_one_at_a_time():
    def law(evidence):
        ordered = sorted(evidence, key=lambda e: e.at)
        one_by_one = reduce(lambda p, e: record(p, [e]), ordered, create_profile("ar", START))
        assert record(create_profile("ar", START), ordered) == one_by_one

    for_all(law, EVIDENCE)


def test_every_unit_is_internally_consistent():
    def law(evidence):
        for state in fold(evidence).units.values():
            assert state.last_seen >= state.last_asked >= state.last_proven
            assert state.seen >= state.reviews
            if state.card == "new":
                assert state.reviews == 0 and state.due == NEVER and state.stability == 0
            else:
                assert state.reviews > 0
                assert state.due > state.last_asked
                assert state.stability > 0
                assert 1 <= state.difficulty <= 10
            assert is_known(state) == (state.card == "review")

    for_all(law, EVIDENCE)


def test_survives_save_and_load():
    def law(evidence):
        p = fold(evidence)
        decoded = deserialize(serialize(p))
        assert decoded.ok
        assert decoded.value == p

    for_all(law, EVIDENCE)


def test_sessions_honour_their_contract():
    def law(evidence, offset_days, max_items, max_new, ahead):
        p = fold(evidence)
        now = START + offset_days * 86_400
        options = PlanOptions(now=now, max_items=max_items, max_new=max_new, study_ahead=ahead)
        session = plan(p, options)
        units = [item.unit for item in session.items]
        assert len(units) == len(set(units))
        assert len(units) <= max_items
        assert sum(1 for item in session.items if item.why == "new") <= min(max_new, max_items)
        assert all(unit in p.units for unit in units)
        assert session.content.units[: len(units)] == tuple(units)
        assert plan(p, options) == session
        if not ahead:
            assert all(item.why != "ahead" for item in session.items)

    for_all(law, EVIDENCE, integer(0, 400), integer(0, 12), integer(0, 12), boolean())
