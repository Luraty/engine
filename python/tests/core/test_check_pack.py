from dataclasses import replace

from luraty_engine import PackSample, check_pack, create_pack
from support.packs import FRENCH_CONFIG, arabic_pack, french_pack

ARABIC_SAMPLE = PackSample(text="ذهبت إلى السوق مع أخي في الصباح")
FRENCH_SAMPLE = PackSample(text="Je vais au marché avec l'automne qui arrive")


def kinds(pack, sample=FRENCH_SAMPLE):
    return [p.kind for p in check_pack(pack, sample)]


def test_passes_a_healthy_pack():
    assert check_pack(french_pack, FRENCH_SAMPLE) == ()
    assert check_pack(arabic_pack, ARABIC_SAMPLE) == ()


def test_catches_a_frequency_list_in_the_wrong_format():
    broken = create_pack(FRENCH_CONFIG, {"frequency": "wordsthatarenotinthetext"})
    assert broken.ok
    assert "empty-vocabulary" in kinds(broken.value)


def test_catches_a_tokenizer_pointed_at_the_wrong_script():
    assert "tokenizer-matches-nothing" in kinds(arabic_pack)


def test_catches_a_pack_marking_every_answer_correct():
    assert "compare-always-true" in kinds(replace(french_pack, compare=lambda a, b: 1))


def test_catches_a_pack_rejecting_a_word_against_itself():
    assert "compare-rejects-identity" in kinds(replace(french_pack, compare=lambda a, b: 0))


def test_catches_an_unstable_key():
    n = [0]

    def unstable(s):
        n[0] += 1
        return f"{french_pack.key(s)}{(n[0] - 1) % 2}"

    assert "unstable-key" in kinds(replace(french_pack, key=unstable))


def test_reports_something_a_human_can_act_on():
    broken = create_pack(FRENCH_CONFIG, {"frequency": "zzz"})
    assert broken.ok
    for problem in check_pack(broken.value, FRENCH_SAMPLE):
        assert "fr" in problem.message
        assert len(problem.message) > 20


# ── candidates ──────────────────────────────────────────────────────────────────────────────────


def test_candidates_passes_the_real_packs():
    assert check_pack(french_pack, FRENCH_SAMPLE) == ()
    assert check_pack(arabic_pack, ARABIC_SAMPLE) == ()


def test_candidates_passes_on_a_sample_whose_words_are_ambiguous():
    assert check_pack(arabic_pack, PackSample(text="كتب مدرسة في السوق")) == ()
    assert len(arabic_pack.candidates("كتب")) > 1
    assert len(arabic_pack.candidates("مدرسة")) > 1


def test_catches_a_candidate_list_not_leading_with_the_key():
    bad = replace(french_pack, candidates=lambda s: ["zzz", french_pack.key(s)])
    assert "candidates-disagree-with-key" in kinds(bad)


def test_catches_an_empty_candidate_list():
    assert "candidates-empty" in kinds(replace(french_pack, candidates=lambda s: []))


def test_catches_a_repeated_reading():
    bad = replace(french_pack, candidates=lambda s: [french_pack.key(s), french_pack.key(s)])
    assert "candidates-repeat" in kinds(bad)


def test_catches_a_second_reading_not_canonical():
    bad = replace(french_pack, candidates=lambda s: [french_pack.key(s), "vais"])
    assert french_pack.key("vais") == "aller"
    assert "candidates-not-canonical" in kinds(bad)


def test_reports_each_candidate_fault_once():
    barren = replace(french_pack, candidates=lambda s: [])
    assert len([p for p in check_pack(barren, FRENCH_SAMPLE) if p.kind == "candidates-empty"]) == 1


def test_names_the_token_and_both_readings():
    bad = replace(arabic_pack, candidates=lambda s: ["سوق", arabic_pack.key(s)])
    problem = next(p for p in check_pack(bad, ARABIC_SAMPLE) if p.kind == "candidates-disagree-with-key")
    assert "سوق" in problem.message
    assert arabic_pack.id in problem.message
