from luraty_engine import (
    Claim,
    PriorClaimed,
    claims_for,
    create_profile,
    exposures_for,
    keys_for,
    parse_unit_key,
    record,
    unit_key,
    unit_state,
    variety,
    vocabulary_of,
    words_in,
)
from support.packs import german_pack

DE = variety("de")


def test_vocabulary_keeps_frequency_order_and_drops_duplicates():
    words = vocabulary_of(german_pack, "der haus hause der brot")
    assert len(set(words)) == len(words)
    assert words[0] == german_pack.key("der")


def test_vocabulary_drops_surfaces_the_pack_cannot_key():
    for w in vocabulary_of(german_pack, "der ... !!! brot"):
        assert len(w) > 0


def test_vocabulary_is_total_on_junk():
    assert vocabulary_of(german_pack, "") == ()
    assert vocabulary_of(german_pack, "   \n\t  ") == ()


def test_keys_mints_only_keys_that_parse_back():
    keys = keys_for("recognise", DE, ["haus", "brot"])
    for k in keys:
        assert parse_unit_key(k) is not None
    assert keys == (unit_key("recognise", DE, "haus"), unit_key("recognise", DE, "brot"))


def test_keys_skips_an_empty_word():
    assert len(keys_for("recognise", DE, ["haus", "", "brot"])) == 2


def test_keys_preserves_order_and_does_not_dedupe():
    assert len(keys_for("recognise", DE, ["b", "a", "b"])) == 3


def test_claims_record_a_prior_and_nothing_else():
    p = record(create_profile("de", 1), claims_for("recognise", DE, ["haus", "brot"], 1))
    haus = unit_state(p, unit_key("recognise", DE, "haus"))
    assert haus.prior == PriorClaimed(on=1)
    assert haus.seen == 0
    assert haus.card == "new"
    assert haus.last_asked == 0


def test_claims_equivalent_to_hand_written_map():
    by_hand = tuple(Claim(unit=unit_key("recognise", DE, w), at=1) for w in ["haus", "brot"])
    assert claims_for("recognise", DE, ["haus", "brot"], 1) == by_hand


def test_turns_a_passage_into_evidence_that_proves_nothing():
    p = record(
        create_profile("de", 1),
        exposures_for("recognise", DE, words_in(german_pack, "Der Mann geht aus dem Haus."), 1),
    )
    for state in p.units.values():
        assert state.seen == 1
        assert state.last_seen == 1
        assert state.last_asked == 0
        assert state.last_proven == 0
        assert state.card == "new"


def test_words_in_dedupes():
    words = words_in(german_pack, "der der der Mann der der")
    assert len(set(words)) == len(words)


def test_words_in_total_on_text_with_no_words():
    assert words_in(german_pack, "???  ...") == ()
    assert exposures_for("recognise", DE, [], 1) == ()
