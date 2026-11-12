"""`summarize`: counts by card state, knowledge, claims, and the span since the last proof."""

from luraty_engine import (
    SECONDS_PER_DAY,
    STUCK_AFTER_LAPSES,
    Claim,
    Exposure,
    Retrieval,
    ScopeAll,
    ScopeSkill,
    advance_to,
    create_profile,
    record,
    summarize,
    unit_key,
    variety,
)

V = variety("ar")
T0 = 1_800_000_000


def U(word, modality="recognise"):
    return unit_key(modality, V, word)


def profile():
    p = record(
        create_profile("ar", T0),
        [
            Exposure(unit=U("new"), at=T0),
            Retrieval(unit=U("learning"), rating="good", at=T0),
            Retrieval(unit=U("review"), rating="easy", at=T0),
            Retrieval(unit=U("relearning"), rating="easy", at=T0),
            Retrieval(unit=U("relearning"), rating="again", at=T0 + 20 * SECONDS_PER_DAY),
            Claim(unit=U("standing"), at=T0),
            Claim(unit=U("confirmed"), at=T0),
            Retrieval(unit=U("confirmed"), rating="good", at=T0),
            Claim(unit=U("refuted"), at=T0),
            Retrieval(unit=U("refuted"), rating="again", at=T0),
            Retrieval(unit=U("said", "produce"), rating="easy", at=T0),
        ],
    )
    return advance_to(p, T0 + 25 * SECONDS_PER_DAY)


def test_counts_units_by_card_state():
    s = summarize(profile(), ScopeAll())
    assert (s.new, s.learning, s.review, s.relearning) == (2, 2, 3, 1)
    assert s.units == s.new + s.learning + s.review + s.relearning


def test_known_means_in_review():
    assert summarize(profile(), ScopeAll()).known == 3


def test_splits_claims_by_what_happened_to_them():
    s = summarize(profile(), ScopeAll())
    assert (s.claims_standing, s.claims_confirmed, s.claims_refuted) == (1, 1, 1)


def test_scopes_to_one_skill():
    s = summarize(profile(), ScopeSkill(variety=V, modality="produce"))
    assert (s.units, s.known) == (1, 1)


def test_counts_whole_days_since_the_last_proof():
    assert summarize(profile(), ScopeAll()).days_since_proven == 25


def test_counts_stuck_units():
    evidence = [Retrieval(unit=U("x"), rating="again", at=T0 + i) for i in range(STUCK_AFTER_LAPSES)]
    assert summarize(record(create_profile("ar", T0), evidence), ScopeAll()).stuck == 1
