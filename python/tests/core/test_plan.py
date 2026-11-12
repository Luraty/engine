"""`plan`: Anki-style session building over FSRS state."""

from luraty_engine import (
    LEARN_AHEAD_SECONDS,
    OVER_ASK,
    REASSESS_AFTER_DAYS,
    SECONDS_PER_DAY,
    STUCK_AFTER_LAPSES,
    Claim,
    Exposure,
    Help,
    PlanOptions,
    Retrieval,
    create_profile,
    deserialize,
    plan,
    record,
    serialize,
    unit_key,
    unit_state,
    variety,
)

V = variety("ar")
T0 = 1_800_000_000


def U(word):
    return unit_key("recognise", V, word)


def profile_with(*evidence):
    return record(create_profile("ar", T0), list(evidence))


def P(profile, now, max_items=10, **options):
    return plan(profile, PlanOptions(now=now, max_items=max_items, **options))


def whys(session):
    return [(item.unit, item.why) for item in session.items]


def test_an_empty_profile_asks_for_new_words():
    session = P(create_profile("ar", T0), T0, max_items=10)
    assert session.items == ()
    assert session.content.new_units_wanted == 5


def test_met_words_are_new_and_claims_are_verify():
    p = profile_with(Exposure(unit=U("a"), at=T0), Claim(unit=U("b"), at=T0))
    assert whys(P(p, T0)) == [(U("b"), "verify"), (U("a"), "new")]


def test_a_learning_step_comes_back_minutes_later():
    p = profile_with(Retrieval(unit=U("a"), rating="good", at=T0))
    due = unit_state(p, U("a")).due
    assert whys(P(p, due - LEARN_AHEAD_SECONDS - 1)) == []
    assert whys(P(p, due - LEARN_AHEAD_SECONDS)) == [(U("a"), "learning")]


def test_a_review_is_absent_until_due():
    p = profile_with(Retrieval(unit=U("a"), rating="easy", at=T0))
    due = unit_state(p, U("a")).due
    assert whys(P(p, due - 1)) == []
    assert whys(P(p, due)) == [(U("a"), "review")]


def test_a_failed_review_comes_back_as_relearn():
    p = profile_with(Retrieval(unit=U("a"), rating="easy", at=T0))
    due = unit_state(p, U("a")).due
    p = record(p, [Retrieval(unit=U("a"), rating="again", at=due)])
    assert whys(P(p, due + 600)) == [(U("a"), "relearn")]


def test_order_is_learning_then_review_then_verify_then_new():
    p = profile_with(
        Retrieval(unit=U("rev"), rating="easy", at=T0),
        Claim(unit=U("ver"), at=T0),
        Exposure(unit=U("new"), at=T0),
    )
    now = unit_state(p, U("rev")).due
    p = record(p, [Retrieval(unit=U("lrn"), rating="good", at=now)])
    session = P(p, now + 600)
    assert [item.why for item in session.items] == ["learning", "review", "verify", "new"]


def test_reviews_are_ordered_weakest_first():
    p = profile_with(
        Retrieval(unit=U("weak"), rating="hard", at=T0),
        Retrieval(unit=U("strong"), rating="easy", at=T0),
    )
    now = T0 + 400 * SECONDS_PER_DAY
    p = record(p, [Retrieval(unit=U("weak"), rating="easy", at=T0 + 1)])
    session = P(p, now)
    recalls = [item.retrievability for item in session.items]
    assert recalls == sorted(recalls)


def test_max_new_is_a_hard_cap():
    p = profile_with(*(Exposure(unit=U(f"w{i}"), at=T0) for i in range(20)))
    session = P(p, T0, max_items=10, max_new=3)
    assert len(session.items) == 3
    assert session.content.new_units_wanted == 0


def test_max_new_defaults_to_half():
    p = profile_with(*(Exposure(unit=U(f"w{i}"), at=T0) for i in range(20)))
    assert P(p, T0, max_items=10) == P(p, T0, max_items=10, max_new=5)


def test_verify_leaves_room_for_new_material():
    claims = [Claim(unit=U(f"c{i}"), at=T0) for i in range(50)]
    news = [Exposure(unit=U(f"n{i}"), at=T0) for i in range(50)]
    session = P(profile_with(*claims, *news), T0, max_items=10, max_new=3)
    counts = [item.why for item in session.items]
    assert counts.count("verify") == 7
    assert counts.count("new") == 3


def test_due_work_comes_before_new_and_bounds_the_session():
    proven = [Retrieval(unit=U(f"r{i}"), rating="easy", at=T0) for i in range(12)]
    news = [Exposure(unit=U(f"n{i}"), at=T0) for i in range(5)]
    session = P(profile_with(*proven, *news), T0 + 60 * SECONDS_PER_DAY, max_items=10)
    assert [item.why for item in session.items] == ["review"] * 10


def test_study_ahead_fills_spare_slots_with_not_yet_due_units():
    p = profile_with(*(Retrieval(unit=U(f"r{i}"), rating="easy", at=T0) for i in range(3)))
    now = T0 + 60
    assert P(p, now).items == ()
    ahead = P(p, now, study_ahead=True)
    assert [item.why for item in ahead.items] == ["ahead"] * 3


def test_study_ahead_never_displaces_due_work():
    p = profile_with(
        Retrieval(unit=U("due"), rating="easy", at=T0),
        Retrieval(unit=U("later"), rating="easy", at=T0 + 30 * SECONDS_PER_DAY),
    )
    now = unit_state(p, U("due")).due
    assert whys(P(p, now, max_items=1, study_ahead=True)) == [(U("due"), "review")]


def test_a_gloss_tap_makes_a_scheduled_unit_due_now():
    p = profile_with(Retrieval(unit=U("a"), rating="easy", at=T0))
    p = record(p, [Help(unit=U("a"), at=T0 + 60)])
    assert whys(P(p, T0 + 120)) == [(U("a"), "review")]


def test_helped_new_words_come_first():
    p = profile_with(
        Exposure(unit=U("a"), at=T0),
        Exposure(unit=U("b"), at=T0),
        Help(unit=U("c"), at=T0),
    )
    assert [unit for unit, _ in whys(P(p, T0))][0] == U("c")


def test_priority_breaks_ties():
    p = profile_with(*(Exposure(unit=U(w), at=T0) for w in ("a", "b", "c")))
    session = P(p, T0, max_items=3, max_new=3, priority=[U("c"), U("a")])
    assert [item.unit for item in session.items] == [U("c"), U("a"), U("b")]


def test_content_units_start_with_the_session_and_add_spares():
    p = profile_with(*(Exposure(unit=U(f"w{i:02}"), at=T0) for i in range(40)))
    session = P(p, T0, max_items=4, max_new=2)
    units = session.content.units
    assert units[: len(session.items)] == tuple(item.unit for item in session.items)
    assert len(units) == 2 * OVER_ASK


def test_reports_stuck_units_sorted():
    evidence = []
    for word in ("zz", "aa"):
        evidence += [Retrieval(unit=U(word), rating="again", at=T0 + i) for i in range(STUCK_AFTER_LAPSES)]
    assert P(profile_with(*evidence), T0 + 1000).stuck == (U("aa"), U("zz"))


def test_reassess_counts_whole_days_since_the_last_proof():
    p = profile_with(Retrieval(unit=U("a"), rating="good", at=T0))
    assert P(p, T0 + (REASSESS_AFTER_DAYS - 1) * SECONDS_PER_DAY).reassess.kind == "not-due"
    due = P(p, T0 + REASSESS_AFTER_DAYS * SECONDS_PER_DAY).reassess
    assert due.kind == "due"
    assert due.days_since_proven == REASSESS_AFTER_DAYS


def test_bad_options_are_clamped_not_thrown():
    p = profile_with(Exposure(unit=U("a"), at=T0))
    assert P(p, T0, max_items=-3).items == ()
    assert P(p, T0, max_items=float("nan")).items == ()
    assert len(P(p, T0, max_items=2.9).items) == 1


def test_a_session_survives_a_save_and_load():
    p = profile_with(
        Retrieval(unit=U("a"), rating="good", at=T0),
        Retrieval(unit=U("b"), rating="easy", at=T0),
        Claim(unit=U("c"), at=T0),
        Exposure(unit=U("d"), at=T0),
    )
    loaded = deserialize(serialize(p)).value
    for now in (T0, T0 + 600, T0 + 10 * SECONDS_PER_DAY):
        assert P(p, now, study_ahead=True) == P(loaded, now, study_ahead=True)
