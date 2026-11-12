"""Measuring a text against what a learner knows."""

from __future__ import annotations

from typing import Literal

from luraty_engine.core.profile import unit_state
from luraty_engine.model import (
    COVERAGE_BAND,
    Band,
    Coverage,
    CoverageMeasured,
    CoverageNoWords,
    CoverageQuery,
    CoverageTooShort,
    CoverageUnverified,
    LanguagePack,
    Lemma,
    Profile,
    has_standing_claim,
    is_known,
    unit_key,
)


def _classify(running_tokens: int, unknown_tokens: int) -> Band:
    r"""Classify a token count against the band. Integers only — see `COVERAGE_BAND`.

    Not exported, deliberately. Exporting it would reopen the exact hole that taking `text` closes:
    a caller could supply counts from its own tokenizer and get an authoritative-looking verdict on
    a token stream the engine never saw.
    """
    # Denser than one unknown in 20 — below 95%.
    if unknown_tokens * COVERAGE_BAND.hard_edge_one_unknown_in > running_tokens:
        return "too-hard"
    # Sparser than one unknown in 50 — above 98%. Includes zero unknowns, which is the case a
    # reviewer is most likely to file as a bug: a text a learner knows entirely teaches no
    # vocabulary, so it is too easy rather than perfect.
    if unknown_tokens * COVERAGE_BAND.easy_edge_one_unknown_in < running_tokens:
        return "too-easy"
    # Both edges are CLOSED. (20, 1) is 0.95 exactly and (50, 1) is 0.98 exactly; ADR-0003 describes
    # the band by naming its endpoints, so including them is the faithful reading.
    return "in-band"


def coverage(profile: Profile, pack: LanguagePack, query: CoverageQuery) -> Coverage:
    r"""How much of a text this learner knows, classified against ADR-0003 invariant 1.

    Total: it never throws and returns no `Decoded<>` wrapper. Nothing here is a trust boundary —
    `text` is just text, and every input has an honest total answer, including "there is nothing to
    measure".

    **What counts as known** is exactly one thing: the unit is in the `understood` box for the
    requested direction and variety. Not "has met it" — a heritage speaker often recognises a word's
    shape while holding only its domestic sense, and will not ask; letting that count would make the
    register gap this engine exists to find invisible by construction, in the very number selection
    is steered by. Not a rank proxy either: the pack is a tokenizer and a keyer here, and `rank()` is
    never called.

    **The grain is the word**, deliberately. Chunks are first-class ITEMS in ADR-0003, not first-class
    TOKENS; the band's construct is word families over running text, so letting a known chunk claim
    its whole span would inflate coverage against its own source. When chunks arrive they change what
    makes a token known — they must never change what a token IS.
    """
    surfaces = pack.split(query.text)
    # A Set so a long ignore list costs nothing per token. Raw surfaces, not keys — capitalisation is
    # the signal, and `key()` has already thrown it away.
    ignore = set(query.ignore if query.ignore is not None else ())

    running_tokens = 0
    known_tokens = 0
    claimed_tokens = 0
    unkeyable_tokens = 0
    ignored_tokens = 0
    unknown_lemmas: list[Lemma] = []
    claimed_lemmas: list[Lemma] = []
    # Doubles as the memo for the profile lookup, so a word repeated 40 times costs one lookup. The
    # insertion order of a Map is the first-appearance order the result promises.
    seen: dict[Lemma, Literal["known", "claimed", "unknown"]] = {}

    for surface in surfaces:
        # Checked BEFORE keying: the caller marked a raw surface, and keying would lowercase it.
        if surface in ignore:
            ignored_tokens += 1
            continue

        lemma = pack.key(surface)

        # Not a running token. `unit_key(d, v, '')` mints an address `parse_unit_key` rejects, so an empty
        # lemma can never be known — leaving it in the denominator would cap coverage below 1 for a
        # typographic reason, and a read-only function would be minting keys that cannot round-trip.
        if len(lemma) == 0:
            unkeyable_tokens += 1
            continue

        running_tokens += 1

        verdict = seen.get(lemma)
        if verdict is None:
            state = unit_state(profile, unit_key(query.direction, query.variety, lemma))
            # ⚠️ Order matters, and only in one direction: a unit can be BOTH claimed and proven, because
            # a claim survives being checked. Proof wins — it is the stronger fact, and counting a
            # confirmed word as merely claimed would keep the text `'unverified'` forever.
            verdict = "known" if is_known(state) else "claimed" if has_standing_claim(state) else "unknown"
            seen[lemma] = verdict
            # Both are unknown under the STRICT reading, which is what `unknown_lemmas` has always meant.
            if verdict != "known":
                unknown_lemmas.append(lemma)
            if verdict == "claimed":
                claimed_lemmas.append(lemma)
        if verdict == "known":
            known_tokens += 1
        if verdict == "claimed":
            claimed_tokens += 1

    unknown_tokens = running_tokens - known_tokens

    # ⚠️ MUST come before the band test. The integer test is TRUE at (0, 0) — `0 * 20 <= 0` and
    # `0 * 50 >= 0` — so without this guard an empty string reports itself as perfectly pitched
    # material. Every other test in the suite has tokens, so nothing else would ever see it.
    if running_tokens == 0:
        return CoverageNoWords(unkeyable_tokens=unkeyable_tokens, ignored_tokens=ignored_tokens)

    # ⚠️ Also before the band test, and UNCONDITIONALLY — not only when the ratio lands somewhere
    # awkward. At 19 tokens with 10 unknown (47% coverage) the answer is still `'too-short'`.
    # Making the floor depend on the value being classified is how non-monotonic selection gets in.
    if running_tokens < COVERAGE_BAND.min_tokens:
        return CoverageTooShort(
            running_tokens=running_tokens,
            known_tokens=known_tokens,
            unknown_tokens=unknown_tokens,
            claimed_tokens=claimed_tokens,
            unkeyable_tokens=unkeyable_tokens,
            ignored_tokens=ignored_tokens,
            unknown_lemmas=tuple(unknown_lemmas),
            needs_more_tokens=COVERAGE_BAND.min_tokens - running_tokens,
        )

    # ⚠️ CLASSIFY TWICE. `strict` believes only what she has proven; `with_claims` also believes what
    # she said. When they agree the answer does not depend on trusting her, and saying `'measured'` is
    # honest. When they disagree, no single band is honest — so both are returned and the caller
    # decides. See `Coverage`.
    strict = _classify(running_tokens, unknown_tokens)
    with_claims = _classify(running_tokens, unknown_tokens - claimed_tokens)

    if strict != with_claims:
        return CoverageUnverified(
            running_tokens=running_tokens,
            known_tokens=known_tokens,
            unknown_tokens=unknown_tokens,
            claimed_tokens=claimed_tokens,
            unkeyable_tokens=unkeyable_tokens,
            ignored_tokens=ignored_tokens,
            unknown_lemmas=tuple(unknown_lemmas),
            strict=strict,
            with_claims=with_claims,
            claimed_lemmas=tuple(claimed_lemmas),
        )

    return CoverageMeasured(
        running_tokens=running_tokens,
        known_tokens=known_tokens,
        unknown_tokens=unknown_tokens,
        claimed_tokens=claimed_tokens,
        unkeyable_tokens=unkeyable_tokens,
        ignored_tokens=ignored_tokens,
        unknown_lemmas=tuple(unknown_lemmas),
        band=strict,
    )
