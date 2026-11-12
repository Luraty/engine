import pytest

from luraty_engine import Claim, CoverageQuery, Retrieval, coverage, create_profile, record, unit_key, variety
from support.alphabets import any_text, passage_for, text_for
from support.packs import arabic_pack, french_pack
from support.prop import array, for_all, integer

BANDS = ("too-hard", "in-band", "too-easy")
PACKS = [(french_pack, variety("fr")), (arabic_pack, variety("ar-msa"))]
each = pytest.mark.parametrize("pack,v", PACKS, ids=["fr", "ar-msa"])
NAT = integer(0, 2**31 - 1)


def counts(result):
    if result.kind == "no-words":
        return dict(running=0, known=0, unknown=0, unkeyable=result.unkeyable_tokens, lemmas=())
    return dict(
        running=result.running_tokens,
        known=result.known_tokens,
        unknown=result.unknown_tokens,
        unkeyable=result.unkeyable_tokens,
        lemmas=result.unknown_lemmas,
    )


def lemmas_of(pack, text):
    out = []
    seen = set()
    for surface in pack.split(text):
        lemma = pack.key(surface)
        if len(lemma) == 0 or lemma in seen:
            continue
        seen.add(lemma)
        out.append(lemma)
    return out


def knowing(v, lemmas, language):
    evidence = []
    for lemma in lemmas:
        unit = unit_key("recognise", v, lemma)
        evidence += [Retrieval(unit=unit, rating="easy", at=1)]
    return record(create_profile(language, 1), evidence)


def claim_all(profile, v, lemmas):
    return record(profile, [Claim(unit=unit_key("recognise", v, lemma), at=1) for lemma in lemmas])


def query(text, v):
    return CoverageQuery(text=text, variety=v, direction="recognise")


@each
def test_never_throws(pack, v):
    empty = create_profile(pack.id, 1)
    for_all(lambda text: coverage(empty, pack, query(text, v)) and None, any_text)


@each
def test_accounts_for_every_token_exactly_once(pack, v):
    def check(text, picks):
        lemmas = lemmas_of(pack, text)
        known = [lemmas[n % max(len(lemmas), 1)] for n in picks] if lemmas else []
        c = counts(coverage(knowing(v, known, pack.id), pack, query(text, v)))
        assert c["known"] + c["unknown"] == c["running"]
        assert c["running"] + c["unkeyable"] == len(pack.split(text))
        assert 0 <= c["known"] <= c["running"]
        assert len(c["lemmas"]) <= c["unknown"]
        assert len(set(c["lemmas"])) == len(c["lemmas"])

    for_all(check, text_for(pack.id), array(NAT))


@each
def test_is_monotone_in_knowledge(pack, v):
    empty = create_profile(pack.id, 1)

    def check(text, n):
        lemmas = lemmas_of(pack, text)
        before = counts(coverage(empty, pack, query(text, v)))
        promoted = lemmas[: n % (len(lemmas) + 1)]
        after = counts(coverage(knowing(v, promoted, pack.id), pack, query(text, v)))
        assert after["running"] == before["running"]
        assert after["known"] >= before["known"]
        assert after["unknown"] <= before["unknown"]

    for_all(check, text_for(pack.id), NAT)


@each
def test_pools_by_concatenation(pack, v):
    def check(a, b, n):
        lemmas = lemmas_of(pack, a) + lemmas_of(pack, b)
        profile = knowing(v, lemmas[: n % (len(lemmas) + 1)], pack.id)
        ca = counts(coverage(profile, pack, query(a, v)))
        cb = counts(coverage(profile, pack, query(b, v)))
        both = counts(coverage(profile, pack, query(f"{a} {b}", v)))
        assert both["running"] == ca["running"] + cb["running"]
        assert both["known"] == ca["known"] + cb["known"]
        assert both["unknown"] == ca["unknown"] + cb["unknown"]
        assert both["unkeyable"] == ca["unkeyable"] + cb["unkeyable"]
        assert set(both["lemmas"]) == {*ca["lemmas"], *cb["lemmas"]}

    for_all(check, text_for(pack.id), text_for(pack.id), NAT)


@each
def test_reaches_all_three_bands(pack, v):
    runs = 400
    tally = dict.fromkeys(BANDS, 0)

    def check(text, unknown_wanted):
        lemmas = lemmas_of(pack, text)
        keep = max(len(lemmas) - unknown_wanted, 0)
        result = coverage(knowing(v, lemmas[:keep], pack.id), pack, query(text, v))
        assert result.kind == "measured"
        assert result.running_tokens == 100
        tally[result.band] += 1

    for_all(check, passage_for(pack.id, 100), integer(0, 100), runs=runs)
    missing = [b for b in BANDS if tally[b] == 0]
    assert missing == [], f"never generated: {missing} in {runs} runs: {tally}"


@each
def test_returns_unverified_exactly_when_readings_disagree(pack, v):
    observed = set()

    def check(text, proven_wanted, claimed_wanted):
        lemmas = lemmas_of(pack, text)
        proven = lemmas[: min(proven_wanted, len(lemmas))]
        claimed = lemmas[len(proven) : len(proven) + claimed_wanted]
        profile = claim_all(knowing(v, proven, pack.id), v, claimed)
        result = coverage(profile, pack, query(text, v))
        observed.add(result.kind)
        if result.kind == "unverified":
            assert result.strict != result.with_claims
            assert result.claimed_tokens > 0
            assert len(result.claimed_lemmas) <= len(result.unknown_lemmas)
            assert result.known_tokens + result.unknown_tokens == result.running_tokens
        if result.kind == "measured":
            assert result.known_tokens == result.running_tokens - result.unknown_tokens

    for_all(check, passage_for(pack.id, 100), integer(0, 100), integer(0, 100))
    assert "unverified" in observed, "never generated an unverified passage"
    assert "measured" in observed, "never generated a settled passage"


@each
def test_never_counts_an_unchecked_claim_as_proven(pack, v):
    def check(text):
        profile = claim_all(create_profile(pack.id, 1), v, lemmas_of(pack, text))
        assert counts(coverage(profile, pack, query(text, v)))["known"] == 0

    for_all(check, passage_for(pack.id, 100))


@each
def test_never_asks_classifier_about_negative_unknowns(pack, v):
    def check(text, a, b):
        lemmas = lemmas_of(pack, text)
        proven = lemmas[: min(a, len(lemmas))]
        claimed = lemmas[max(0, len(proven) - b) :]
        r = coverage(claim_all(knowing(v, proven, pack.id), v, claimed), pack, query(text, v))
        if r.kind == "no-words":
            return
        assert 0 <= r.claimed_tokens <= r.unknown_tokens
        assert r.known_tokens + r.unknown_tokens == r.running_tokens

    for_all(check, passage_for(pack.id, 60), integer(0, 60), integer(0, 60))
