import luraty_engine as L
from luraty_engine import (
    Retrieval,
    advance_to,
    create_profile,
    instant,
    is_skill,
    is_unit_key,
    keys_for,
    plan,
    record,
    skill_key,
    variety,
)

AR = variety("ar")


def test_keeps_the_three_part_shape():
    assert str(skill_key(AR, "past-agreement")) == "skill:ar:past-agreement"


def test_does_not_collide_with_a_word():
    word = keys_for("recognise", AR, ["past-agreement"])[0]
    assert str(word) != str(skill_key(AR, "past-agreement"))


def test_tells_a_host_what_a_key_is():
    assert is_skill(skill_key(AR, "x"))
    assert not is_skill(keys_for("recognise", AR, ["x"])[0])


def test_is_accepted_by_is_unit_key():
    assert is_unit_key(str(skill_key(AR, "past-agreement")))
    assert not is_unit_key("skill:ar:")
    assert not is_unit_key("skill:")


def test_is_scheduled_by_the_same_plan():
    skill = skill_key(AR, "past-agreement")
    profile = create_profile("ar", instant(1))
    profile = record(profile, [Retrieval(unit=skill, rating="good", at=instant(1))])
    profile = advance_to(profile, instant(30))
    session = plan(profile, L.PlanOptions(now=instant(30), max_items=5))
    assert skill in [item.unit for item in session.items]
