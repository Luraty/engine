# The model's plain values — the numbers and frozen shapes the types are written around.

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

from luraty_engine.model.types import Direction, Instant, Modality, PriorNone, UnitState

# The channels a piece of knowledge can be held in, as data. `Modality` is derived from this so the
# two cannot drift.
#
# ⚠️ **THE FIRST SEGMENT OF EVERY UNIT KEY, AND THE REASON A TOOL COSTS THE ENGINE NOTHING**
# (ADR-0022). `plan()` never parses a key — it reads `profile.units` as opaque addresses with rungs
# — so a new modality inherits spacing, the rung ladder, review gaps, `Reassess` and stuck-detection
# for free. Grammar proved it: `skill:ar:<id>` is scheduled by the same `plan()` as a word, with no
# branch anywhere.
#
# ⚠️ **`skill` LIVES HERE RATHER THAN BEING SMUGGLED IN.** It used to be a hand-written cast in
# `skill_key` that bypassed `unit_key`, plus a second arm in `is_unit_key` to stop `persist` rejecting
# the key it had just minted — and `persist` fails the WHOLE profile on one unparseable key, so a
# learner who did one grammar lesson could never load hers again. That bug was found by reading
# `persist`, not by a test. Pronunciation and writing would have been smuggles two and three.
#
# ⚠️ **ORDER IS NOT A RANKING** and nothing may depend on it. The first two are `Direction` — the
# recognise/produce asymmetry that is the measured core of the learner model (ADR-0002) — and they
# come first only because they are the two that existed.
MODALITIES: Final[tuple[Modality, ...]] = (
    # She understood it when she met it.
    "recognise",
    # She produced it from meaning.
    "produce",
    # She said it, and the sounds were right.
    "pronounce",
    # She wrote it.
    "write",
    # She understood it by ear, with no text in front of her.
    "hear",
    # A grammar rule she holds, rather than a word.
    #
    # ⚠️ Never introduced by `plan()` — no pack contains grammar. A skill enters a profile the first
    # time she is asked one, which is correct rather than a limitation: a rule she has never been
    # taught is not due for review.
    "skill",
    # A phrase she produces, keyed by its exact text: no pack key, no lemma.
    #
    # ⚠️ Never introduced by `plan()`, like `skill`: a phrase enters a profile when she adds it as a
    # card. Its key is the phrase as written, so two spellings are two units on purpose — the exact
    # form is what she is practising.
    "phrase",
)

# All directions, for iteration. Derived from the union so the two cannot drift apart.
DIRECTIONS: Final[tuple[Direction, ...]] = ("recognise", "produce")


# The instant that means "never".
#
# Exported so that nothing reimplements `== 0` and so the meaning is greppable. It is deliberately
# NOT constructible through `instant()` — that function rejects it.
NEVER: Final = cast(Instant, 0)

SECONDS_PER_MINUTE: Final = 60
SECONDS_PER_DAY: Final = 86_400

# ── Spaced repetition (FSRS) ────────────────────────────────────────────────────────────────────
#
# These are Anki's defaults, and the defaults of the FSRS reference implementation the engine uses.

# The recall probability a review is scheduled at. 0.9 means a unit comes back when FSRS estimates a
# 10% chance she has forgotten it. Higher means more reviews; lower means fewer.
DESIRED_RETENTION: Final = 0.9

# Delays between the steps a NEW unit works through before it graduates to day-scale review.
LEARNING_STEPS_SECONDS: Final[tuple[int, ...]] = (1 * SECONDS_PER_MINUTE, 10 * SECONDS_PER_MINUTE)

# Delays between the steps a FAILED review works through before it graduates again.
RELEARNING_STEPS_SECONDS: Final[tuple[int, ...]] = (10 * SECONDS_PER_MINUTE,)

# The longest review interval, in days. A hundred years: effectively no ceiling.
MAXIMUM_INTERVAL_DAYS: Final = 36_500

# How far ahead a learning or relearning unit may be pulled into a session. Anki's default.
LEARN_AHEAD_SECONDS: Final = 20 * SECONDS_PER_MINUTE

# Bump when the wire shape changes, and add the matching migration in the same commit.
#
# Not the same as the package version — the API can change many times without the stored bytes
# changing at all, and vice versa.
PROFILE_SCHEMA_VERSION: Final = 1

# How many elements a `WireRowV1` has. Read by `serialize` and `parse_row`.
WIRE_ROW_LENGTH: Final = 14

@dataclass(frozen=True, slots=True)
class _CoverageBand:
    # The 95% edge — at most 1 unknown word per 20 running tokens.
    #
    # Denser than this is **too hard**: comprehension is minimal and inferring unknown words from
    # context stops working (~52% correct at 90% coverage, against ~80% inside the band).
    hard_edge_one_unknown_in: int = 20
    # The 98% edge — at least 1 unknown word per 50 running tokens.
    #
    # Sparser than this is **too easy**: comprehension is fine and there is little left to learn from
    # the input.
    easy_edge_one_unknown_in: int = 50
    # Below this many running tokens the band has **no representable point**, so no verdict is honest.
    #
    # ⚠️ Derived, not an independent literal. `unknown_tokens` is a non-negative integer, and zero
    # unknowns is 100% coverage — which is above the band, not inside it. So landing in band needs at
    # least one unknown token, which needs `1 * hard_edge_one_unknown_in <= running_tokens`.
    #
    # Enumerated, because this is the kind of claim that should not rest on an argument: for every
    # n ≤ 19 the only reachable coverages are 1.00000 (u=0) and at most 0.94737 (n=19, u=1).
    # `'in-band'` cannot occur. The first (n, u) that reaches it is (20, 1) = 0.95 exactly.
    #
    # It is exported so that a future `plan()` can carry the floor outward. The engine cannot fetch
    # content, so if the host is never told "at least 20 running tokens", it supplies a nine-word
    # sentence and the band objective is unsatisfiable by construction, silently, forever.
    min_tokens: int = 20


# The band, expressed the way ADR-0003 states it: **integer unknown-token density.**
#
# The ADR says "1 unknown word in 50" and "1 in 20". So the test is
# `unknown * 20 <= tokens && unknown * 50 >= tokens` — two multiplications by small integers and
# two comparisons. No division, no float literal, no epsilon, nothing whose formatting differs by
# runtime.
#
# This is not floating-point superstition. The float form is exact: `19 / 20 === 0.95` and
# `49 / 50 === 0.98` are both true, because IEEE754 division and decimal-literal parsing are both
# correctly rounded onto the same real value. But that exactness is a proof no reviewer can audit
# at a glance, and it dies to any edit that looks like tidying — a percentage hop
# (`ratio * 100 >= 95`), a defensive `- 1e-9` that silently widens the band, a stray `Math.round`.
# The integer form has no proof to break, and it reads as the ADR's own sentence.
#
# Exact while `50 * unknown_tokens < 2^53`, which is about 1.8e14 tokens.
COVERAGE_BAND: Final = _CoverageBand()

# The state of a unit nothing has ever said anything about.
#
# Every date is `0` — never seen, never asked, never proven, never due. Zero is also the identity
# element of the max-fold in `record`.
UNMET: Final = UnitState(
    seen=0,
    last_seen=NEVER,
    last_helped=NEVER,
    prior=PriorNone(),
    card="new",
    step=0,
    stability=0.0,
    difficulty=0.0,
    due=NEVER,
    last_asked=NEVER,
    last_proven=NEVER,
    reviews=0,
    lapses=0,
)
