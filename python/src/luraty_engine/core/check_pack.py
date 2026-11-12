r"""Conformance checks for a language pack, run against the REAL data a host is about to load.

Every test in this repo uses hand-written fixtures that are correct by construction. That means
no test can ever catch the failure that actually happens in production: the engine code is right
and the 20,000-word pack file is wrong. This function is the layer for that.

It is exported so a host can run it at load time, and so a pack author can run it in their own
CI. A pack that fails these is not a pack that crashes — it is a pack that works, quietly, and
teaches nobody anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from luraty_engine._js import number_to_string
from luraty_engine.model import LanguagePack

PackProblemKind = Literal[
    "empty-vocabulary",
    "tokenizer-matches-nothing",
    "unstable-key",
    "compare-always-true",
    "compare-rejects-identity",
    "candidates-disagree-with-key",
    "candidates-empty",
    "candidates-repeat",
    "candidates-not-canonical",
]


@dataclass(frozen=True, slots=True)
class PackProblem:
    kind: PackProblemKind
    message: str


@dataclass(frozen=True, slots=True)
class PackSample:
    """Words that should tokenize under the pack's own pattern, supplied by the caller."""

    # A sentence in the target language, exactly as a learner would meet it.
    text: str


def check_pack(pack: LanguagePack, sample: PackSample) -> tuple[PackProblem, ...]:
    r"""Check a built pack against a sample of real text.

    Returns an empty array when the pack looks healthy. The sample matters: the checks that mean
    anything are the ones run against text in the script the pack is actually for, which is why the
    caller supplies it rather than the engine guessing.
    """
    problems: list[PackProblem] = []

    tokens = pack.split(sample.text)

    if len(tokens) == 0:
        problems.append(
            PackProblem(
                kind="tokenizer-matches-nothing",
                message=f'pack "{pack.id}" tokenized the sample text into nothing. The tokenize pattern probably '
                "does not cover this script.",
            )
        )
        # Everything below reads tokens, so there is nothing further worth reporting.
        return tuple(problems)

    keys = [pack.key(t) for t in tokens]

    # ── The wrong-separator check ─────────────────────────────────────────────────────────────────
    # A frequency list split on the wrong character yields one enormous "word", so every lookup
    # misses. The pack still builds, still tokenizes, and silently ranks nothing — and because affix
    # stripping consults the same table, it stops working too. Leipzig, OpenSubtitles and wordfreq
    # are all one word per line, so this is the likeliest real-world pack defect there is.
    ranked = sum(1 for k in keys if pack.rank(k) is not None)
    if ranked == 0:
        problems.append(
            PackProblem(
                kind="empty-vocabulary",
                message=f'pack "{pack.id}" ranked none of the {number_to_string(len(keys))} words in the sample. The '
                "frequency list is probably empty or in an unexpected format.",
            )
        )

    # ── Key stability ─────────────────────────────────────────────────────────────────────────────
    # If keying a canonical form changes it again, the same word files itself under two keys
    # depending on the route it took, and a learner's knowledge is silently split in half.
    for key in keys:
        if pack.key(key) != key:
            problems.append(
                PackProblem(
                    kind="unstable-key",
                    message=f'pack "{pack.id}" key() is not idempotent: "{key}" keys again to "{pack.key(key)}". '
                    "The same word will be tracked under two different keys.",
                )
            )
            # One report, not one per token: instability is a property of `key()` itself, so a broken
            # pack would otherwise emit thousands of identical problems and bury everything below.
            break

    # ── Candidates agree with the key ─────────────────────────────────────────────────────────────
    # ⚠️ THIS IS THE CHECK THAT MAKES A MULTI-COLUMN LEMMA TABLE SAFE TO SHIP, and no unit test can
    # stand in for it: fixtures are written correct by construction, and the table that breaks the
    # rule is a host's 90,000-row generated file where one row grew a second column in the wrong
    # order.
    #
    # The failure it catches is silent and specific. A reader taps a word, is shown the readings
    # `candidates()` offers, picks the first — and is credited for a unit `key()` never names, so the
    # scheduler goes on treating the word as unmet no matter how often she looks it up. Everything
    # renders, nothing errors, and the learner's own answer is filed against a word she did not
    # choose.
    for token in tokens:
        offered = pack.candidates(token)

        if len(offered) == 0:
            problems.append(
                PackProblem(
                    kind="candidates-empty",
                    message=f'pack "{pack.id}" candidates() returned nothing for "{token}". Every form must offer '
                    "at least the reading key() gives it, or a tapped word shows no meaning at all.",
                )
            )
            # One report per kind, for the reason key stability gives: these are properties of the
            # function rather than of the token, so a broken pack buries everything below.
            break

        if offered[0] != pack.key(token):
            problems.append(
                PackProblem(
                    kind="candidates-disagree-with-key",
                    message=f'pack "{pack.id}" candidates("{token}") leads with "{offered[0]}" but key() '
                    f'says "{pack.key(token)}". A learner picking the first reading would be credited for a '
                    "different word than the engine addresses.",
                )
            )
            break

    for token in tokens:
        offered = pack.candidates(token)
        if len(set(offered)) == len(offered):
            continue
        problems.append(
            PackProblem(
                kind="candidates-repeat",
                message=f'pack "{pack.id}" candidates("{token}") offers the same reading more than once: '
                f"{', '.join(offered)}. A learner cannot choose between two identical senses.",
            )
        )
        break

    # ⚠️ EVERY reading must be canonical, not only the first. This is the key-stability check applied
    # to the readings a learner can actually pick, and it is a separate failure: element zero is
    # `key`'s own answer and is already covered above, while elements one and beyond are reachable
    # only through a tap. A second reading that keys onward to something else means the learner who
    # picks it is credited under an address no other route to that word ever produces — one word,
    # two unit keys, and the split shows up as her gap.
    for token in tokens:
        offered = pack.candidates(token)
        drifting = next((reading for reading in offered if pack.key(reading) != reading), None)
        if drifting is None:
            continue
        problems.append(
            PackProblem(
                kind="candidates-not-canonical",
                message=f'pack "{pack.id}" candidates("{token}") offers "{drifting}", which key() turns into '
                f'"{pack.key(drifting)}". A learner choosing that reading is credited under a different '
                "unit than the same word reached any other way.",
            )
        )
        break

    # ── Grading sanity ────────────────────────────────────────────────────────────────────────────
    # "Marks everything correct" is the worst failure this package can have, and the one nobody
    # reports — learners do not complain about being told they are right.
    first = keys[0] if keys else None
    if first is not None:
        if pack.compare(first, first) != 1:
            problems.append(
                PackProblem(
                    kind="compare-rejects-identity",
                    message=f'pack "{pack.id}" compare() rejects "{first}" against itself.',
                )
            )
        nonsense = "\x00zzq\x00"
        if pack.compare(nonsense, first) == 1:
            problems.append(
                PackProblem(
                    kind="compare-always-true",
                    message=f'pack "{pack.id}" compare() accepts unrelated input as correct. Every answer will be '
                    "marked right.",
                )
            )

    return tuple(problems)
