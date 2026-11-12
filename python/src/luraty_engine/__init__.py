# The public API of the Luraty engine.
#
# This barrel is the ONLY thing a consumer may import. Everything else under src/ is internal —
# if a caller needs something, export it here deliberately.
#
# ⚠️ Hand-written allowlist. Never `export * from './something'`: a wildcard makes every future
# internal file public by default, and a barrel you cannot narrow is an engine you cannot replace.
#
# Built so far: the state (what the engine believes about a learner and how evidence changes it),
# persistence, language packs, coverage, and planning.
#
# The engine of record. It started as the Python twin of @luraty/engine@0.5.1; since 0.6.0 (FSRS
# scheduling) the TypeScript package is deprecated and TypeScript hosts call this one through
# `luraty_cli`. Parity vectors still pin packs and normalization against the TS packages:
#  UPDATE_PARITY=1 node scripts/generate_parity_vectors.mjs

from __future__ import annotations

from typing import Final

from luraty_engine.core.bulk import (
    claims_for,
    exposures_for,
    keys_for,
    vocabulary_of,
    words_in,
)
from luraty_engine.core.check_pack import PackProblem, PackProblemKind, PackSample, check_pack
from luraty_engine.core.coverage import coverage
from luraty_engine.core.learner import Learner, LearnerContext, learner
from luraty_engine.core.pack import create_pack
from luraty_engine.core.persist import deserialize, serialize
from luraty_engine.core.memory import retrievability
from luraty_engine.core.plan import (
    OVER_ASK,
    REASSESS_AFTER_DAYS,
    STUCK_AFTER_LAPSES,
    plan,
)
from luraty_engine.core.profile import advance_to, create_profile, has_met, unit_state
from luraty_engine.core.record import record
from luraty_engine.core.summary import summarize
from luraty_engine.model import (
    COVERAGE_BAND,
    DESIRED_RETENTION,
    DIRECTIONS,
    LEARN_AHEAD_SECONDS,
    LEARNING_STEPS_SECONDS,
    MAXIMUM_INTERVAL_DAYS,
    MODALITIES,
    NEVER,
    PROFILE_SCHEMA_VERSION,
    RELEARNING_STEPS_SECONDS,
    SECONDS_PER_DAY,
    SECONDS_PER_MINUTE,
    PHRASE,
    SKILL,
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
    has_standing_claim,
    instant,
    is_known,
    is_modality,
    is_phrase,
    is_skill,
    is_unit_key,
    parse_skill_key,
    parse_unit_key,
    phrase_key,
    skill_key,
    unit_key,
    variety,
)

__all__ = [
    # Identifiers
    "Instant",
    "NEVER",
    "SECONDS_PER_DAY",
    "SECONDS_PER_MINUTE",
    "Direction",
    "Modality",
    "UnitKey",
    "UnitParts",
    "Variety",
    "DIRECTIONS",
    "MODALITIES",
    "instant",
    "is_modality",
    "is_unit_key",
    "parse_unit_key",
    "unit_key",
    "variety",
    # What the engine believes
    "Prior",
    "PriorNone",
    "PriorClaimed",
    "CardState",
    "Rating",
    "UnitState",
    "has_standing_claim",
    "is_known",
    "DESIRED_RETENTION",
    "LEARNING_STEPS_SECONDS",
    "RELEARNING_STEPS_SECONDS",
    "MAXIMUM_INTERVAL_DAYS",
    "LEARN_AHEAD_SECONDS",
    "retrievability",
    "Profile",
    # What changes it
    "Claim",
    "Evidence",
    "EvidenceKind",
    "Exposure",
    "Help",
    "Retrieval",
    # Language packs
    "AffixConfig",
    "CompoundConfig",
    "LanguagePack",
    "Lemma",
    "NormalizeStep",
    "PackConfig",
    "PackData",
    "TokenizeConfig",
    "create_pack",
    "PackProblem",
    "PackProblemKind",
    "PackSample",
    "check_pack",
    # Results
    "Decoded",
    "DecodedOk",
    "DecodedError",
    "DecodeError",
    "DecodeErrorKind",
    # Persistence
    "PROFILE_SCHEMA_VERSION",
    # Coverage
    "Band",
    "Coverage",
    "CoverageNoWords",
    "CoverageTooShort",
    "CoverageMeasured",
    "CoverageUnverified",
    "CoverageQuery",
    "COVERAGE_BAND",
    "coverage",
    # Planning
    "ContentRequest",
    "PlanOptions",
    "Reassess",
    "ReassessNotDue",
    "ReassessNeverMeasured",
    "ReassessDue",
    "Session",
    "SessionItem",
    "Why",
    "OVER_ASK",
    "plan",
    "REASSESS_AFTER_DAYS",
    "STUCK_AFTER_LAPSES",
    # Doing one thing to many words
    "claims_for",
    "exposures_for",
    "keys_for",
    "vocabulary_of",
    "words_in",
    # Skills
    "SKILL",
    "is_skill",
    "skill_key",
    "PHRASE",
    "is_phrase",
    "phrase_key",
    "parse_skill_key",
    "SkillParts",
    # The fluent handle
    "Learner",
    "LearnerContext",
    "learner",
    # Reporting
    "Summary",
    "SummaryScope",
    "ScopeAll",
    "ScopeSkill",
    "summarize",
    # Operations
    "advance_to",
    "create_profile",
    "has_met",
    "unit_state",
    "record",
    "deserialize",
    "serialize",
    "ENGINE_API_VERSION",
]

ENGINE_API_VERSION: Final = "0.6.0"
