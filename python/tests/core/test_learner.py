from luraty_engine import (
    Claim,
    CoverageQuery,
    Help,
    LearnerContext,
    PlanOptions,
    Retrieval,
    ScopeSkill,
    coverage,
    create_profile,
    learner,
    plan,
    record,
    serialize,
    summarize,
    unit_key,
    variety,
    vocabulary_of,
)
from support.packs import german_pack

DE = variety("de")
WORDS = vocabulary_of(german_pack, "der die und haus brot mann wasser gehen")
CTX = LearnerContext(pack=german_pack, variety=DE, vocabulary=WORDS)


def L():
    return learner(create_profile("de", 1), CTX)


def U(word, direction="recognise"):
    return unit_key(direction, DE, word)


def test_facade_for_a_placement():
    assert L().claim(WORDS, 1).profile == record(create_profile("de", 1), [Claim(unit=U(w), at=1) for w in WORDS])


def test_facade_for_an_answer():
    assert L().answer("haus", "good", 1).profile == record(
        create_profile("de", 1), [Retrieval(unit=U("haus"), rating="good", at=1)]
    )


def test_facade_for_session_coverage_summary():
    text = "Der Mann geht aus dem Haus. Die Frau trinkt Wasser und isst Brot heute."
    anna = L().claim(WORDS, 1).answer("haus", "good", 2)
    options = PlanOptions(now=9, max_items=5, max_new=2)
    assert anna.plan(options) == plan(
        anna.profile, PlanOptions(now=9, max_items=5, max_new=2, priority=[U(w) for w in WORDS])
    )
    assert anna.coverage(text) == coverage(
        anna.profile, german_pack, CoverageQuery(text=text, variety=DE, direction="recognise")
    )
    assert anna.summary() == summarize(anna.profile, ScopeSkill(variety=DE, modality="recognise"))
    assert anna.save() == serialize(anna.profile)


def test_returns_a_new_handle():
    before = L()
    after = before.claim(WORDS, 1)
    assert len(before.profile.units) == 0
    assert len(after.profile.units) > 0
    assert after is not before


def test_chains_without_hidden_state():
    chained = L().claim(WORDS, 1).answer("haus", "good", 2).on(9)
    stepwise = learner(L().claim(WORDS, 1).answer("haus", "good", 2).profile, CTX).on(9)
    assert chained.profile == stepwise.profile


def test_exposes_the_raw_profile():
    anna = L().claim(WORDS, 1)
    via_free = record(anna.profile, [Retrieval(unit=U("brot"), rating="again", at=3)])
    assert learner(via_free, CTX).summary().claims_refuted == 1


def test_defaults_priority_but_allows_override():
    anna = L().claim(WORDS, 1)
    reversed_keys = [U(w) for w in reversed(WORDS)]
    options = PlanOptions(now=9, max_items=3, max_new=0)
    overridden = PlanOptions(now=9, max_items=3, max_new=0, priority=reversed_keys)
    assert anna.plan(overridden).items[0].unit != anna.plan(options).items[0].unit


def test_falls_back_to_key_tiebreak():
    bare = learner(create_profile("de", 1), LearnerContext(pack=german_pack, variety=DE)).claim(["zebra", "apfel"], 1)
    assert [i.unit for i in bare.plan(PlanOptions(now=9, max_items=2, max_new=0)).items] == [U("apfel"), U("zebra")]


def test_addresses_same_unit_for_surface_or_lemma():
    surface = L().answer("HAUS", "good", 1)
    lemma = L().answer("haus", "good", 1)
    assert surface.profile == lemma.profile
    assert U("haus") in surface.profile.units
    assert len(surface.profile.units) == 1


def test_agrees_with_read_and_claim():
    via_answer = L().answer("Haus", "good", 1)
    via_read = L().read("Haus", 1)
    via_claim = L().claim(["Haus"], 1)
    assert list(via_answer.profile.units) == list(via_read.profile.units)
    assert list(via_claim.profile.units) == list(via_read.profile.units)


def test_is_a_no_op_on_already_keyed_input():
    assert L().claim(WORDS, 1).profile == record(create_profile("de", 1), [Claim(unit=U(w), at=1) for w in WORDS])


def test_drops_a_word_the_pack_cannot_key():
    assert len(L().answer("!!!", "good", 1).profile.units) == 0


def proven():
    return L().answer("haus", "good", 1).answer("haus", "good", 2).answer("haus", "good", 3)


def test_help_moves_no_memory():
    before = proven().profile.units[U("haus")]
    after = proven().help("haus", 4).profile.units[U("haus")]
    memory = ("card", "step", "stability", "difficulty", "due", "last_asked", "last_proven", "reviews")
    assert all(getattr(after, field) == getattr(before, field) for field in memory)
    assert after.last_helped == 4


def test_help_is_not_a_lapse():
    assert proven().help("haus", 4).profile.units[U("haus")].lapses == 0


def test_help_matches_the_free_function():
    assert proven().help("haus", 4).profile == record(proven().profile, [Help(unit=U("haus"), at=4)])


def test_help_canonicalises():
    assert proven().help("HAUS", 4).profile == proven().help("haus", 4).profile


def test_coverage_honours_ignore():
    text = "Anna geht aus dem Haus. Anna trinkt Wasser und Anna isst Brot heute in Berlin."
    anna = L().claim(WORDS, 1)
    with_ignore = anna.coverage(text, ignore=["Anna"])
    assert with_ignore != anna.coverage(text)
    assert with_ignore == coverage(
        anna.profile, german_pack, CoverageQuery(text=text, variety=DE, direction="recognise", ignore=["Anna"])
    )


def test_addresses_the_skill_the_handle_was_built_for():
    speak = learner(
        create_profile("de", 1), LearnerContext(pack=german_pack, variety=DE, vocabulary=WORDS, direction="produce")
    ).answer("haus", "good", 1)
    assert U("haus", "produce") in speak.profile.units
    assert U("haus") not in speak.profile.units
    assert speak.summary().scope == ScopeSkill(variety=DE, modality="produce")
