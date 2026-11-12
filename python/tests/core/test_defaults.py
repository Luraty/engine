from luraty_engine import (
    Exposure,
    LearnerContext,
    PlanOptions,
    Retrieval,
    create_pack,
    create_profile,
    learner,
    plan,
    record,
    unit_key,
    variety,
    vocabulary_of,
)
from support.packs import german_pack

DE = variety("de")
WORDS = vocabulary_of(german_pack, "der die und haus brot mann wasser gehen essen kind")


def test_rejects_a_colon_bearing_id():
    built = create_pack(
        {"id": "ar:msa", "tokenize": {"strategy": "regex", "pattern": "[a-z]+"}, "normalize": [], "compare": []},
        {"frequency": "a b"},
    )
    assert not built.ok
    assert "legal variety" in built.error.message


def test_brands_the_id():
    assert german_pack.id == "de"
    assert unit_key("recognise", german_pack.id, "haus") == unit_key("recognise", DE, "haus")


def test_addresses_same_units_as_explicit_variety():
    implicit = learner(create_profile("de", 1), LearnerContext(pack=german_pack)).answer("haus", "good", 1)
    explicit = learner(create_profile("de", 1), LearnerContext(pack=german_pack, variety=DE)).answer("haus", "good", 1)
    assert implicit.profile == explicit.profile
    assert implicit.variety == DE


def test_still_lets_a_diglossic_host_choose():
    levantine = variety("ar-levantine")
    two = learner(create_profile("ar", 1), LearnerContext(pack=german_pack, variety=levantine)).answer("haus", "good", 1)
    assert unit_key("recognise", levantine, "haus") in two.profile.units
    assert unit_key("recognise", german_pack.id, "haus") not in two.profile.units


def exposures(words):
    return [Exposure(unit=unit_key("recognise", DE, w), at=1) for w in words]


def test_max_new_matches_explicit_floor():
    p = record(create_profile("de", 1), exposures(WORDS))
    for max_items in [4, 5, 8, 12, 20]:
        implicit = plan(p, PlanOptions(now=9, max_items=max_items))
        explicit = plan(p, PlanOptions(now=9, max_items=max_items, max_new=max_items // 2))
        assert implicit == explicit, max_items


def test_puts_due_reviews_before_new_material():
    p = create_profile("de", 1)
    proven, fresh = WORDS[:5], WORDS[5:]
    drills = [Retrieval(unit=unit_key("recognise", DE, w), rating="easy", at=1) for w in proven]
    p = record(record(p, drills), exposures(fresh))
    session = plan(p, PlanOptions(now=1 + 60 * 86_400, max_items=6))
    assert [i.why for i in session.items] == ["review"] * 5 + ["new"]


def test_a_motivated_learner_gets_more_by_planning_again():
    anna = learner(create_profile("de", 1), LearnerContext(pack=german_pack, vocabulary=WORDS)).claim(WORDS, 1)
    rounds = served = 0
    while True:
        s = anna.plan(PlanOptions(now=1, max_items=4))
        if len(s.items) == 0:
            break
        rounds += 1
        served += len(s.items)
        for item in s.items:
            anna = anna.record([Retrieval(unit=item.unit, rating="good", at=1)])
        assert rounds < 20, "should terminate"
    assert served == len(WORDS)
    assert rounds > 1
    assert anna.plan(PlanOptions(now=1, max_items=4)).items == ()


def test_read_is_how_words_enter_the_profile():
    empty = learner(create_profile("de", 1), LearnerContext(pack=german_pack, vocabulary=WORDS))
    assert empty.plan(PlanOptions(now=1, max_items=10)).items == ()
    after = empty.read("Der Mann trinkt Wasser und isst Brot.", 1)
    session = after.plan(PlanOptions(now=1, max_items=10))
    assert len(session.items) > 0
    assert all(i.why == "new" for i in session.items)
    for state in after.profile.units.values():
        assert state.seen == 1
        assert state.last_asked == 0
        assert state.last_proven == 0
        assert state.card == "new"
    assert after.summary().known == 0
