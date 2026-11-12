# The model — types only, plus the small total functions that construct and read them.
#
# `core/` depends on this; this depends on nothing but `utils/`. That direction never reverses.
#
# ⚠️ ONE DECLARATION PER FILE. Constructors and predicates at the root, one per file named after
# them; types under `types/` (and `types/wire/` for the persisted shapes, which have the opposite
# change policy from everything else); plain values in `constants.py`. See ADR-0009 in the parent repo.
#
# This barrel is the module's only public face. `core/` imports from here, never from a leaf.

from __future__ import annotations

from typing import TypeIs, cast

from luraty_engine import _js
from luraty_engine.model.constants import (
    COVERAGE_BAND,
    DIRECTIONS,
    DESIRED_RETENTION,
    LEARN_AHEAD_SECONDS,
    LEARNING_STEPS_SECONDS,
    MAXIMUM_INTERVAL_DAYS,
    MODALITIES,
    NEVER,
    PROFILE_SCHEMA_VERSION,
    RELEARNING_STEPS_SECONDS,
    SECONDS_PER_DAY,
    SECONDS_PER_MINUTE,
    UNMET,
    WIRE_ROW_LENGTH,
)
from luraty_engine.model.types import (
    AffixConfig,
    Band,
    Claim,
    CompoundConfig,
    ContentRequest,
    Coverage,
    CoverageMeasured,
    CoverageNoWords,
    CoverageQuery,
    CoverageTooShort,
    CoverageUnverified,
    CardState,
    Decoded,
    DecodedError,
    DecodedOk,
    DecodeError,
    DecodeErrorKind,
    Direction,
    Evidence,
    EvidenceKind,
    Exposure,
    Help,
    Instant,
    LanguagePack,
    Lemma,
    Modality,
    NormalizeStep,
    PackConfig,
    PackData,
    PlanOptions,
    Prior,
    PriorClaimed,
    PriorNone,
    Profile,
    Rating,
    Reassess,
    ReassessDue,
    ReassessNeverMeasured,
    ReassessNotDue,
    Retrieval,
    ScopeAll,
    ScopeSkill,
    Session,
    SessionItem,
    SkillParts,
    Summary,
    SummaryScope,
    TokenizeConfig,
    UnitKey,
    UnitParts,
    UnitState,
    Variety,
    Why,
)

__all__ = [
    "AffixConfig",
    "Band",
    "COVERAGE_BAND",
    "Claim",
    "CompoundConfig",
    "ContentRequest",
    "Coverage",
    "CoverageMeasured",
    "CoverageNoWords",
    "CoverageQuery",
    "CoverageTooShort",
    "CoverageUnverified",
    "DIRECTIONS",
    "CardState",
    "DecodeError",
    "DecodeErrorKind",
    "Decoded",
    "DecodedError",
    "DecodedOk",
    "Direction",
    "Evidence",
    "EvidenceKind",
    "Exposure",
    "Help",
    "Instant",
    "DESIRED_RETENTION",
    "LEARN_AHEAD_SECONDS",
    "LEARNING_STEPS_SECONDS",
    "LanguagePack",
    "Lemma",
    "MAXIMUM_INTERVAL_DAYS",
    "MODALITIES",
    "Modality",
    "NEVER",
    "NormalizeStep",
    "PROFILE_SCHEMA_VERSION",
    "PackConfig",
    "PackData",
    "PlanOptions",
    "Prior",
    "PriorClaimed",
    "PriorNone",
    "Profile",
    "Rating",
    "Reassess",
    "ReassessDue",
    "ReassessNeverMeasured",
    "ReassessNotDue",
    "Retrieval",
    "SKILL",
    "RELEARNING_STEPS_SECONDS",
    "SECONDS_PER_DAY",
    "SECONDS_PER_MINUTE",
    "ScopeAll",
    "ScopeSkill",
    "Session",
    "SessionItem",
    "SkillParts",
    "Summary",
    "SummaryScope",
    "TokenizeConfig",
    "UNMET",
    "UnitKey",
    "UnitParts",
    "UnitState",
    "Variety",
    "WIRE_ROW_LENGTH",
    "Why",
    "instant",
    "has_standing_claim",
    "is_direction",
    "is_known",
    "is_modality",
    "is_skill",
    "is_unit_key",
    "parse_skill_key",
    "parse_unit_key",
    "phrase_key",
    "is_phrase",
    "PHRASE",
    "skill_key",
    "unit_key",
    "variety",
]

# The modality that marks a unit as a skill rather than a word.
SKILL = "skill"
# The modality that marks a unit as a phrase, keyed by its exact text.
PHRASE = "phrase"


# ── Identifiers ─────────────────────────────────────────────────────────────────────────────────


def instant(n: int | float) -> Instant | None:
    r"""Build an `Instant`. Rejects negatives, non-integers, and **zero**.

    Zero is the never-sentinel — see `model/types.py`. Rejecting it here is what makes that sentinel
    unambiguous.
    """
    if not _js.is_integer(n) or n < NEVER + 1:
        return None
    return cast(Instant, _js.number(n))


def is_direction(s: str) -> TypeIs[Direction]:
    """Is this string one of the two directions?"""
    return s == "recognise" or s == "produce"


def is_modality(s: str) -> TypeIs[Modality]:
    r"""Is this string one of the modalities?

    ⚠️ Not a utility: `(s: string) => boolean` passes the signature clause, but the body knows the
    engine's own vocabulary. See `utils.py` for the test.

    ⚠️ **THE ONLY GATE ON WHAT MAY BE ADDRESSED.** `parse_unit_key` calls it, `is_unit_key` narrows
    through it, and `persist` fails a whole profile on a key it rejects — so a modality that is not in
    `MODALITIES` cannot enter a profile at all. That is the point: a free-form segment would let
    a host typo a channel into existence and silently create units nothing will ever schedule.
    """
    return s in MODALITIES


def parse_unit_key(key: str) -> UnitParts | None:
    r"""Take a unit key apart. Returns `undefined` for anything malformed — this runs against persisted
    data, which is the one place the engine cannot assume its own invariants held.

    ⚠️ **IT NOW PARSES EVERY MODALITY, INCLUDING `skill:` (ADR-0022), AND THAT CHANGED WHO IS
    COUNTED.** Before, a skill key failed here, so `in_scope` dropped it from EVERY summary scope
    including `'all'` — a learner's grammar was invisible to `Summary.known`. It is now counted, and
    the per-skill scope keys on `modality` so the partition law still holds exactly.
    """
    first_colon = key.find(":")
    if first_colon < 0:
        return None
    second_colon = key.find(":", first_colon + 1)
    if second_colon < 0:
        return None

    modality = key[:first_colon]
    variety_part = key[first_colon + 1 : second_colon]
    # Everything after the second colon, so a word may contain colons freely.
    word = key[second_colon + 1 :]

    if not is_modality(modality):
        return None
    if len(variety_part) == 0 or len(word) == 0:
        return None

    return UnitParts(modality=modality, variety=cast(Variety, variety_part), word=word)


def is_unit_key(key: str) -> TypeIs[UnitKey]:
    r"""Is this string a well-formed unit key?

    The narrowing form of `parse_unit_key`, for the caller that only needs the yes/no — chiefly
    `deserialize`, which must reject a bad key from storage rather than take it apart.

    ⚠️ **THE SECOND ARM IS GONE, AND THAT IS THE POINT OF ADR-0022.** It used to read
    `parse_unit_key(key) !== undefined || parse_skill_key(key) !== undefined`, because a `skill:` key had
    no `Direction` in its first segment and `parse_unit_key` rejected it by design. `persist` validates
    every key on load and fails the whole blob as malformed when one does not parse — so without that
    arm, a learner who did one grammar lesson could never open her profile again. It was found by
    reading `persist` rather than by a failing test, because the skill test never round-tripped
    through serialization.

    That is a patch per namespace, and the next two namespaces were pronunciation and writing. Now the
    modality is checked in one place, so there is nothing to forget.
    """
    return parse_unit_key(key) is not None


def parse_skill_key(key: str) -> SkillParts | None:
    r"""Read a skill key back into its parts.

    ⚠️ **`parse_unit_key` NOW HANDLES SKILL KEYS TOO (ADR-0022), SO THIS IS A CONVENIENCE RATHER THAN A
    NECESSITY.** It used to be load-bearing: `UnitParts.direction` was a `Direction` and a skill has
    none, so `parse_unit_key` rejected `skill:` outright and this was the only way to read one. Now the
    first segment is a `Modality` and both parse. What this still buys is the SHAPE — it returns
    `{ variety, skill }`, so a caller that has already established it holds a skill does not have to
    re-check a modality field it knows the value of.

    ⚠️ **A HOST USES THIS TO DECIDE WHAT TO DRAW.** The scheduler never calls it; the moment `plan()`
    asks what kind of unit something is, grammar has its own scheduler again.
    """
    prefix = f"{SKILL}:"
    if not key.startswith(prefix):
        return None

    rest = key[len(prefix) :]
    colon = rest.find(":")
    if colon < 0:
        return None

    variety_part = rest[:colon]
    # Everything after, so a skill id may contain colons freely — the same rule words get.
    skill = rest[colon + 1 :]
    if len(variety_part) == 0 or len(skill) == 0:
        return None

    return SkillParts(variety=cast(Variety, variety_part), skill=skill)


def unit_key(modality: Modality, v: Variety, word: str) -> UnitKey:
    r"""Build a `UnitKey`.

    ⚠️ **AND SINCE ADR-0022 IT ACTUALLY IS.** `skill_key` used to hand-cast because its first segment
    was not a `Direction`; taking a `Modality` here is what let that cast be deleted, and with it the
    second arm `is_unit_key` needed to stop `persist` rejecting a key the engine had minted.
    """
    return cast(UnitKey, f"{modality}:{v}:{word}")


def skill_key(v: Variety, skill: str) -> UnitKey:
    r"""A unit key for something she KNOWS rather than a word she knows.

    ⚠️ **A GRAMMAR SKILL IS A UNIT, AND THAT IS THE WHOLE POINT.** Founder: *"make grammar skills units
    the engine schedules."* A rule fades on the same curve a word does; giving grammar its own bespoke
    scheduler would mean two answers to "what is due today", and they would disagree within a week. As
    a unit it inherits spacing, the rung ladder, review gaps and `Reassess` for free.

    ⚠️ **NOTHING IN THE SCHEDULER PARSES A KEY, WHICH IS WHY THIS COSTS NOTHING.** `plan()` reads
    `profile.units` as opaque keys with state; it never splits one, never filters on the modality
    segment, never asks what a unit means. Verified before writing this rather than assumed — the only
    `split(':')` in the engine is in `testing/demo.ts`, for display.

    ⚠️ **`skill` IS A `Modality` (ADR-0022), WHICH IS WHY THIS IS NOW THREE LINES.** It used to
    hand-cast, because the first segment was typed `Direction` and `unit_key()` would not take it —
    minting a key the engine's own `parse_unit_key` rejected, and forcing a second arm into `is_unit_key`
    to keep `persist` from failing every profile that held one. A skill is not asked in a direction —
    "recognise the past-tense agreement rule" is not a thing — so it sits in the modality slot beside
    `pronounce` and `hear`, and every key keeps one shape.

    ⚠️ **A SKILL IS NEVER INTRODUCED BY `plan()`.** New units come from the pack's vocabulary and no
    pack contains grammar. A skill enters a profile the first time she is asked one: the lesson records
    evidence, and from that moment it is scheduled like anything else. That is correct rather than a
    limitation — a rule she has never been taught is not due for review.
    """
    return unit_key(SKILL, v, skill)


def is_skill(unit: UnitKey) -> bool:
    r"""Whether a key names a skill.

    ⚠️ For a HOST deciding what to draw, never for the scheduler deciding what is due. The moment the
    engine branches on this, grammar has its own scheduler again.
    """
    return str(unit).startswith(f"{SKILL}:")


def phrase_key(v: Variety, text: str) -> UnitKey | None:
    r"""A unit key for a phrase she practises, keyed by its exact text.

    Whitespace runs collapse to one space and the ends are trimmed, so a stray space is not a second
    phrase. Nothing else changes: no pack key, no lemma, diacritics kept. Returns `None` for text that
    is empty once trimmed.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) == 0:
        return None
    return unit_key(PHRASE, v, collapsed)


def is_phrase(unit: UnitKey) -> bool:
    """Whether a key names a phrase. For a host deciding what to draw, never for the scheduler."""
    return str(unit).startswith(f"{PHRASE}:")


def variety(id: str) -> Variety | None:
    r"""Build a `Variety`. Returns `undefined` rather than throwing — the caller supplies this, so it is
    untrusted input.
    """
    if len(id) == 0 or ":" in id:
        return None
    return cast(Variety, id)


# ── The unit ────────────────────────────────────────────────────────────────────────────────────


def has_standing_claim(state: UnitState) -> bool:
    r"""Claimed, and never yet asked about — the liability a placement creates.

    This is the predicate behind `Why.'verify'` and behind `Summary.claims_standing`. Note that it is
    *not* "has a claim": a claim survives being checked, which is what makes the confirmed/refuted
    split computable from present state with no history at all.
    """
    return state.prior.kind == "claimed" and state.last_asked == NEVER


def is_known(state: UnitState) -> bool:
    r"""Is this unit known?

    ⚠️ THE one predicate, exported so that nothing reimplements it.

    Known means GRADUATED: the unit has worked through its learning steps and sits in day-scale
    review. A unit in `learning` or `relearning` is not known — it was either never learned or has
    just been forgotten — and a bare claim is never known until a retrieval proves it.
    """
    return state.card == "review"
