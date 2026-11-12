import luraty_engine as L
from luraty_engine import (
    MODALITIES,
    Retrieval,
    ScopeAll,
    ScopeSkill,
    advance_to,
    create_profile,
    deserialize,
    is_modality,
    is_unit_key,
    parse_unit_key,
    plan,
    record,
    serialize,
    skill_key,
    summarize,
    unit_key,
    variety,
)

AR = variety("ar")


def test_carries_the_two_directions_plus_the_four_channels():
    assert list(MODALITIES) == ["recognise", "produce", "pronounce", "write", "hear", "skill", "phrase"]


def test_accepts_every_modality_and_nothing_else():
    for m in MODALITIES:
        assert is_modality(m)
    for bad in ["recognize", "Produce", "speak", "listen", "skills", "", "pronounce "]:
        assert not is_modality(bad), bad


def test_key_is_built_by_blessed_constructor_and_read_back():
    for modality in MODALITIES:
        key = unit_key(modality, AR, "قلب")
        assert str(key) == f"{modality}:ar:قلب"
        assert parse_unit_key(str(key)).modality == modality
        assert is_unit_key(str(key))


def test_survives_serialize_deserialize():
    p = create_profile("ar", 1)
    keys = [unit_key(m, AR, "قلب") for m in MODALITIES]
    p = record(p, [Retrieval(unit=u, rating="good", at=1) for u in keys])
    back = deserialize(serialize(p))
    assert back.ok
    assert sorted(back.value.units) == sorted(keys)


def test_one_word_in_two_modalities_is_two_units():
    heard = unit_key("hear", AR, "قلب")
    said = unit_key("pronounce", AR, "قلب")
    p = create_profile("ar", 1)
    p = record(p, [Retrieval(unit=heard, rating="good", at=1), Retrieval(unit=said, rating="again", at=1)])
    assert p.units[heard].last_proven == 1
    assert p.units[said].last_proven == 0
    assert p.units[heard].step == 1
    assert p.units[said].step == 0
    assert p.units[said].lapses == 1
    assert p.units[heard].lapses == 0


def test_every_modality_is_scheduled_by_the_same_plan():
    for modality in MODALITIES:
        unit = unit_key(modality, AR, "قلب")
        p = create_profile("ar", 1)
        p = record(p, [Retrieval(unit=unit, rating="good", at=1)])
        p = advance_to(p, 30)
        session = plan(p, L.PlanOptions(now=30, max_items=5))
        assert unit in [i.unit for i in session.items], modality


def test_counts_a_grammar_skill_in_all():
    skill = skill_key(AR, "past-agreement")
    p = create_profile("ar", 1)
    p = record(p, [Retrieval(unit=skill, rating="good", at=1)])
    assert summarize(p, ScopeAll()).units == 1
    assert summarize(p, ScopeSkill(variety=AR, modality="skill")).units == 1
    assert summarize(p, ScopeSkill(variety=AR, modality="recognise")).units == 0


def test_partitions_a_profile_holding_every_modality():
    p = create_profile("ar", 1)
    p = record(p, [Retrieval(unit=unit_key(m, AR, "قلب"), rating="good", at=1) for m in MODALITIES])
    total = summarize(p, ScopeAll()).units
    parts = [summarize(p, ScopeSkill(variety=AR, modality=m)).units for m in MODALITIES]
    assert total == len(MODALITIES)
    assert sum(parts) == total


def test_still_refuses_a_key_with_no_word():
    for modality in MODALITIES:
        assert not is_unit_key(f"{modality}:ar:")
        assert not is_unit_key(f"{modality}:")
    assert not is_unit_key("speak:ar:قلب")


def test_builds_a_skill_key_through_unit_key():
    built = skill_key(AR, "past-agreement")
    direct = unit_key("skill", AR, "past-agreement")
    assert str(built) == str(direct)
    assert is_unit_key(str(built))
