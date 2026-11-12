"""`record`: how each kind of evidence changes a unit, under the FSRS memory model."""

from luraty_engine import (
    LEARNING_STEPS_SECONDS,
    RELEARNING_STEPS_SECONDS,
    SECONDS_PER_DAY,
    Claim,
    Exposure,
    Help,
    PriorClaimed,
    Retrieval,
    create_profile,
    is_known,
    record,
    unit_key,
    unit_state,
    variety,
)

V = variety("ar")
T0 = 1_800_000_000
U = unit_key("recognise", V, "كتاب")


def fold(*evidence):
    return unit_state(record(create_profile("ar", T0), list(evidence)), U)


def ask(rating, at):
    return Retrieval(unit=U, rating=rating, at=at)


def graduated(at=T0):
    """Through both learning steps with `good`, ending in review."""
    first = LEARNING_STEPS_SECONDS[0]
    second = LEARNING_STEPS_SECONDS[1]
    return [ask("good", at), ask("good", at + first + second)]


# ── Learning steps ──────────────────────────────────────────────────────────────────────────────


def test_a_first_good_starts_the_learning_steps():
    state = fold(ask("good", T0))
    assert state.card == "learning"
    assert state.step == 1
    assert state.due == T0 + LEARNING_STEPS_SECONDS[1]
    assert not is_known(state)


def test_a_first_again_restarts_at_the_first_step():
    state = fold(ask("again", T0))
    assert state.card == "learning"
    assert state.step == 0
    assert state.due == T0 + LEARNING_STEPS_SECONDS[0]
    assert state.lapses == 1
    assert state.last_proven == 0


def test_easy_skips_the_learning_steps():
    state = fold(ask("easy", T0))
    assert state.card == "review"
    assert state.due >= T0 + SECONDS_PER_DAY
    assert is_known(state)


def test_finishing_the_steps_graduates_to_day_scale_review():
    state = fold(*graduated())
    assert state.card == "review"
    assert state.step == 0
    assert state.due - state.last_asked >= SECONDS_PER_DAY
    assert is_known(state)


# ── Review, lapse, relearning ───────────────────────────────────────────────────────────────────


def test_successful_reviews_on_schedule_space_out():
    evidence = graduated()
    state = fold(*evidence)
    gaps = []
    for _ in range(4):
        evidence.append(ask("good", state.due))
        gaps.append(state.due - state.last_asked)
        state = fold(*evidence)
    assert gaps == sorted(gaps)
    assert gaps[-1] > 4 * gaps[0]


def test_a_lapse_in_review_goes_to_relearning_minutes_later():
    evidence = graduated()
    due = fold(*evidence).due
    state = fold(*evidence, ask("again", due))
    assert state.card == "relearning"
    assert state.due == due + RELEARNING_STEPS_SECONDS[0]
    assert not is_known(state)
    assert state.lapses == 1


def test_a_lapse_lowers_stability():
    evidence = graduated()
    before = fold(*evidence)
    after = fold(*evidence, ask("again", before.due))
    assert after.stability < before.stability


def test_relearning_graduates_back_to_review():
    evidence = graduated()
    due = fold(*evidence).due
    evidence += [ask("again", due), ask("good", due + RELEARNING_STEPS_SECONDS[0])]
    assert fold(*evidence).card == "review"


def test_harder_ratings_schedule_sooner():
    evidence = graduated()
    due = fold(*evidence).due
    hard, good, easy = (fold(*evidence, ask(r, due)).due for r in ("hard", "good", "easy"))
    assert hard < good < easy


def test_an_early_review_buys_less_than_one_on_time():
    evidence = graduated()
    due = fold(*evidence).due
    early = fold(*evidence, ask("good", evidence[-1].at + SECONDS_PER_DAY // 2))
    on_time = fold(*evidence, ask("good", due))
    assert early.stability < on_time.stability


def test_cramming_the_same_day_does_not_fake_long_term_memory():
    evidence = graduated()
    stability = fold(*evidence).stability
    at = evidence[-1].at
    crammed = evidence + [ask("good", at + 60 * i) for i in range(1, 11)]
    assert fold(*crammed).stability < stability * 3


# ── Bookkeeping ─────────────────────────────────────────────────────────────────────────────────


def test_counts_reviews_and_resets_lapses_on_success():
    state = fold(ask("again", T0), ask("again", T0 + 60), ask("good", T0 + 120))
    assert state.reviews == 3
    assert state.lapses == 0
    assert state.seen == 3
    assert state.last_asked == T0 + 120
    assert state.last_proven == T0 + 120


def test_hard_is_a_success():
    state = fold(ask("hard", T0))
    assert state.last_proven == T0
    assert state.lapses == 0


def test_exposure_moves_no_memory():
    state = fold(Exposure(unit=U, at=T0))
    assert state.card == "new"
    assert state.seen == 1
    assert state.last_seen == T0
    assert state.last_asked == 0


def test_help_moves_no_memory_and_is_not_a_lapse():
    before = fold(*graduated())
    after = fold(*graduated(), Help(unit=U, at=T0 + SECONDS_PER_DAY))
    assert (after.card, after.stability, after.due, after.lapses) == (
        before.card,
        before.stability,
        before.due,
        before.lapses,
    )
    assert after.last_helped == T0 + SECONDS_PER_DAY
    assert after.seen == before.seen + 1


def test_claim_sets_prior_and_nothing_else():
    state = fold(Claim(unit=U, at=T0))
    assert state.prior == PriorClaimed(on=T0)
    assert state.seen == 0
    assert state.card == "new"


def test_a_claim_proven_with_good_is_scheduled_as_easy():
    claimed = fold(Claim(unit=U, at=T0), ask("good", T0))
    plain_easy = fold(ask("easy", T0))
    assert claimed.card == "review"
    assert (claimed.stability, claimed.due) == (plain_easy.stability, plain_easy.due)


def test_a_claim_answered_hard_or_again_gets_no_bonus():
    for rating in ("hard", "again"):
        claimed = fold(Claim(unit=U, at=T0), ask(rating, T0))
        plain = fold(ask(rating, T0))
        assert (claimed.card, claimed.stability, claimed.due) == (plain.card, plain.stability, plain.due)


def test_bookkeeping_dates_never_rewind():
    state = fold(ask("good", T0 + 500), Exposure(unit=U, at=T0), ask("good", T0 + 100))
    assert state.last_seen == T0 + 500
    assert state.last_asked == T0 + 500
    assert state.last_proven == T0 + 500


def test_a_late_arriving_retrieval_is_folded_at_the_last_one():
    in_order = fold(ask("good", T0), ask("good", T0 + 600))
    late = fold(ask("good", T0 + 600), ask("good", T0))
    assert late.due >= late.last_asked
    assert late.card == in_order.card == "review"


def test_batch_and_sequence_agree():
    profile = create_profile("ar", T0)
    evidence = [*graduated(), Exposure(unit=U, at=T0 + 5), Help(unit=U, at=T0 + 7)]
    one_by_one = profile
    for item in evidence:
        one_by_one = record(one_by_one, [item])
    assert record(profile, evidence) == one_by_one


def test_empty_evidence_returns_the_same_profile():
    profile = create_profile("ar", T0)
    assert record(profile, []) is profile
