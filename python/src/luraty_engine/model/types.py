"""The shapes the engine is written around. Types only."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, NewType

# ── Identifiers ─────────────────────────────────────────────────────────────────────────────────

# A moment in time: whole seconds since the Unix epoch, UTC, **starting at 1**.
#
# An instant and not a day number, because spaced repetition happens at two time scales. Learning
# and relearning steps are minutes apart (a new word comes back after 1 minute, then 10), and review
# intervals are days to years apart. A day number can express only the second, which is what made
# "do this word again later today" unrepresentable with day numbers.
#
# Whole seconds rather than a float or a `datetime`: an integer serializes the same everywhere, sorts
# without a timezone, and cannot carry a hidden local offset. The host converts its clock once, at
# the boundary, and nothing in here ever reads a clock.
#
# ⚠️ **INSTANT 0 IS RESERVED AND IS NOT A LEGAL INSTANT.** Zero is the "never" sentinel for every
# date the engine stores, because a max-fold needs an identity element and `0` is it. The constructor
# `instant()` refuses it.
Instant = NewType("Instant", int)

# A language variety, opaque to the engine.
#
# The engine never interprets this — `'fr'`, `'ar-msa'` and `'ar-levantine'` are all just strings
# it carries around. That is what keeps the engine language-agnostic.
#
# It is part of the unit key rather than only the profile because a diglossic language keeps two
# varieties in play at once: the dialect a learner speaks at home and the standard they read. They
# are related but different systems and must be measured separately.
Variety = NewType("Variety", str)

# The address of one piece of knowledge: `direction:variety:word`.
#
# ⚠️ The word comes LAST on purpose. Parsing takes the first two segments and treats the entire
# remainder as the word, so a word containing a colon cannot corrupt the key. Put the word in the
# middle and some language, somewhere, eventually breaks the parser.
UnitKey = NewType("UnitKey", str)

# Which way the knowledge runs.
#
# These are tracked as SEPARATE states for the same word, and that is not a detail — the gap
# between what a heritage speaker recognises and what they can actually say is the single defining
# feature of the learner this engine exists for. Collapse the two and you have measured the wrong
# thing.
Direction = Literal["recognise", "produce"]

# Which channel a piece of knowledge is held in — the first segment of a unit key.
#
# Derived from `MODALITIES` so the value and the type cannot drift. Writing the union by hand
# beside the array is two statements of one fact, and the day someone adds a seventh only one of
# them moves.
#
# ⚠️ **A WORD IS ONE UNIT PER MODALITY, WITH ITS OWN RUNG.** `recognise:ar:قلب` and
# `pronounce:ar:قلب` are different addresses that know nothing about each other. That is the
# learner model's own claim (ADR-0002) — unevenness is the normal case — extended from two channels
# to five.
#
# ⚠️ **`Direction` IS THE NARROW SIBLING, NOT A LEGACY NAME.** `recognise | produce` is what
# `coverage()`, `summarize()`'s per-skill scope and the estimate model mean, because the
# recognise/produce gap is the measured thing. A `Direction` is assignable to a `Modality`; the
# reverse is not, and that asymmetry is doing real work — it is what stops
# `coverage({ direction: 'pronounce' })` compiling.
Modality = Literal["recognise", "produce", "pronounce", "write", "hear", "skill", "phrase"]


@dataclass(frozen=True, slots=True)
class UnitParts:
    r"""The parts of a unit key.

    ⚠️ **`modality`, RENAMED FROM `direction` BY ADR-0022.** The rename is deliberate rather than
    cosmetic: while the field was a `Direction`, a caller could reasonably read `parts.direction` as
    "she either recognises or produces this", and that is false the moment a `pronounce:` or `skill:`
    key parses. A field that can hold `'skill'` must not be called a direction.
    """

    modality: Modality
    variety: Variety
    word: str


@dataclass(frozen=True, slots=True)
class SkillParts:
    variety: Variety
    skill: str


# ── The unit ────────────────────────────────────────────────────────────────────────────────────

# How a retrieval went, on Anki's four-button scale.
#
# - `again`: she could not produce it. A lapse.
# - `hard`: she got it, with effort.
# - `good`: she got it.
# - `easy`: she got it without thinking.
#
# Every rating except `again` is a success: it moves `last_proven` and resets `lapses`.
Rating = Literal["again", "hard", "good", "easy"]

# Where a unit is in the spaced-repetition cycle. The FSRS card states, plus `new`.
#
# - `new`: never retrieved. No memory model yet.
# - `learning`: retrieved, still working through the learning steps (minutes apart).
# - `review`: graduated. Scheduled in days by its stability.
# - `relearning`: was in review, failed, and is working through the relearning steps.
CardState = Literal["new", "learning", "review", "relearning"]


@dataclass(frozen=True, slots=True)
class PriorNone:
    kind: Literal["none"] = field(default="none", init=False)


@dataclass(frozen=True, slots=True)
class PriorClaimed:
    # The host says she knows this. Nobody has checked.
    kind: Literal["claimed"] = field(default="claimed", init=False)
    # When the claim was made. Monotone max-fold, so re-claiming is safe and order-free.
    on: Instant


# What the host asserted about this unit before anybody measured anything.
#
# A discriminated union rather than a `claimed_on` with `0` meaning "never", so a claim can never be
# confused with its absence.
Prior = PriorNone | PriorClaimed


@dataclass(frozen=True, slots=True)
class UnitState:
    r"""What the engine believes about one unit, in one modality and variety.

    Two halves. The **memory** half is an FSRS card — `card`, `step`, `stability`, `difficulty`,
    `due` — and only a `Retrieval` changes it. The **record** half — `seen`, `last_seen`,
    `last_helped`, `prior` — is what happened to the unit outside of being tested.

    ⚠️ **ONLY RETRIEVAL MOVES MEMORY.** Reading a word, tapping its gloss or claiming it changes no
    stability, no difficulty and no due date. FSRS models what a retrieval proves, and nothing else
    proves anything.
    """

    # Total ENCOUNTERS of any kind: a retrieval, a passive sighting, a gloss tap. Never decreases.
    # A claim does NOT increment this, because nobody encountered anything.
    seen: int
    # The last instant ANY encounter arrived. Reporting only; nothing schedules on it.
    last_seen: Instant
    # The last instant she asked for HELP — tapped a gloss, revealed the meaning. `0` means never.
    #
    # Proves nothing and moves no memory. It moves the unit up the queue: see `plan`.
    last_helped: Instant
    # What the host claimed before anything was measured. See `Prior`.
    prior: Prior
    # Where the unit is in the spaced-repetition cycle. See `CardState`.
    card: CardState
    # Index of the current learning or relearning step. `0` outside those states.
    step: int
    # FSRS stability, in days: how long until recall probability falls to 90%. `0.0` while `new`.
    stability: float
    # FSRS difficulty, from 1 (easy) to 10 (hard). `0.0` while `new`.
    difficulty: float
    # When the unit is next due. `0` while `new`, which nothing schedules on.
    due: Instant
    # The last instant a RETRIEVAL was attempted, whatever the rating. `0` means never asked.
    last_asked: Instant
    # The last instant a retrieval SUCCEEDED (any rating but `again`). `0` means never proven.
    last_proven: Instant
    # How many retrievals this unit has had, of any rating.
    reviews: int
    # Consecutive `again` ratings. Reset to 0 by any success. Never moved by exposure or help.
    #
    # Report-only: it feeds `Session.stuck` and nothing else.
    lapses: int


# ── Evidence ────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Retrieval:
    r"""A real retrieval: she was asked, and she answered.

    The only variant that moves the memory model. Everything the engine trusts, it trusts because of
    one of these.
    """

    kind: Literal["retrieval"] = field(default="retrieval", init=False)
    unit: UnitKey
    rating: Rating
    at: Instant


@dataclass(frozen=True, slots=True)
class Exposure:
    r"""Met it and moved on. Reading a word in a passage and not asking about it.

    Moves `seen` and `last_seen` and nothing else. Not asking is not proof of knowing.
    """

    kind: Literal["exposure"] = field(default="exposure", init=False)
    unit: UnitKey
    at: Instant


@dataclass(frozen=True, slots=True)
class Help:
    r"""Tapped the gloss, or revealed the answer.

    Moves `seen`, `last_seen` and `last_helped`. Proves nothing and is not a lapse; `plan` uses
    `last_helped` to bring the unit forward.
    """

    kind: Literal["help"] = field(default="help", init=False)
    unit: UnitKey
    at: Instant


@dataclass(frozen=True, slots=True)
class Claim:
    r"""The host asserts prior knowledge. Nobody has checked.

    Sets `UnitState.prior` and touches nothing else, so it can never overwrite a measurement. A claim
    pays off at the first retrieval: a claimed unit that is new and retrieved with `good` is scheduled
    as `easy`, so a word she says she knows and then proves skips the learning steps.
    """

    kind: Literal["claim"] = field(default="claim", init=False)
    unit: UnitKey
    at: Instant


# One observation about the learner.
#
# ⚠️ Evidence describes the LEARNER, not the exercise. There is no `source` field: a flashcard, a
# cloze and a speaking task all arrive here in the same shape.
#
# ### What each variant may do — the complete table
#
# | variant              | seen | last_seen | last_helped | prior | memory (FSRS) | last_asked | last_proven | lapses |
# | -------------------- | ---- | --------- | ----------- | ----- | ------------- | ---------- | ----------- | ------ |
# | retrieval, again     | +1   | → at      | –           | –     | review        | → at       | –           | +1     |
# | retrieval, otherwise | +1   | → at      | –           | –     | review        | → at       | → at        | → 0    |
# | exposure             | +1   | → at      | –           | –     | –             | –          | –           | –      |
# | help                 | +1   | → at      | → at        | –     | –             | –          | –           | –      |
# | claim                | –    | –         | –           | set   | –             | –          | –           | –      |
#
# "→ at" is a max-fold, so those fields do not depend on arrival order. The memory column does: FSRS
# is a sequence of reviews, so an offline queue must be sorted by `at` before it is recorded.
Evidence = Retrieval | Exposure | Help | Claim

# The tag. Useful for reporting without narrowing the whole union.
EvidenceKind = Literal["retrieval", "exposure", "help", "claim"]


# ── The profile ─────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Profile:
    r"""Everything the engine believes about one learner, in one language.

    **One profile per language, always.** Two languages are two profiles with nothing shared — you
    are a different person in each one, and a heritage speaker's Arabic tells you nothing useful
    about their French. A diglossic language keeps two *varieties* inside one profile (the dialect
    and the standard), because they interfere with each other and must be compared; but they are
    still measured separately, which is why the variety is part of every unit key.

    **This is a value, not an object.** Nothing mutates it — `record()` returns a new one. That is
    what lets a test fork a learner to ask "what if she had failed this?", diff two profiles, and
    bisect a replay that went wrong. None of it is possible with state hidden inside a class.

    **It is also derived, not authoritative.** The evidence log is the truth; a profile is a fold
    over it. So when the memory model changes — and it will, several times — that is a re-fold
    rather than a migration.
    """

    # The language this profile is for, as the host names it. Varieties of it (a dialect and a
    # standard) live inside, distinguished per unit key.
    language: str
    # The learner's current instant. Advanced explicitly by the host via `advance_to`, never read
    # from a clock — there is no clock in here to read.
    now: Instant
    # Sparse. A unit the learner has never met is genuinely absent rather than present-and-empty,
    # which is exactly what `UnitState | undefined` on lookup is telling you. Use the total accessor
    # instead of reaching for `??` at every call site.
    #
    # Unevenness needs no special representation here: "B1 listening, A1 writing" is just a dense
    # layer of `recognise` keys over a sparse layer of `produce` ones. If the abstraction were wrong,
    # this is where it would show.
    units: Mapping[UnitKey, UnitState]

    def __post_init__(self) -> None:
        if not isinstance(self.units, MappingProxyType):
            object.__setattr__(self, "units", MappingProxyType(dict(self.units)))


# ── Packs ───────────────────────────────────────────────────────────────────────────────────────

# A canonical word form: the pack's answer to "are these two the same word?".
Lemma = str

# The named transformations a pack may compose. A CLOSED set, on purpose.
#
# Closed because this is what lets a language be added as data rather than code: the pack file
# names the steps, the engine owns the implementations. An open set (arbitrary functions in config)
# would just be code with extra steps, and could not be shipped as JSON.
#
# These are named by SCRIPT rather than generically. A `strip_diacritics` that claims to work
# everywhere is a lie — the Arabic and Latin cases have nothing in common mechanically, and hiding
# that behind one name is how the wrong one gets applied to the wrong language.
#
# The implementations live in `normalize/`.
NormalizeStep = Literal[
    "lowercase",
    "stripPunctuation",
    "stripArabicDiacritics",
    "stripTatweel",
    "normalizeArabicAlef",
    "normalizeArabicFinals",
    "foldLatinDiacritics",
    "foldGermanUmlauts",
]


@dataclass(frozen=True, slots=True)
class TokenizeConfig:
    """How a pack turns text into surface tokens."""

    strategy: Literal["regex"]
    # A character-class pattern matched globally. Not a full regex — a pattern for what counts as a
    # word character, so a pack file cannot smuggle in catastrophic backtracking.
    pattern: str


@dataclass(frozen=True, slots=True)
class AffixConfig:
    r"""Prefix stripping, for languages that attach particles to the front of a word."""

    # Prefixes to strip, longest first.
    prefixes: Sequence[str]
    # Only strip when the remainder is a word the pack has heard of.
    #
    # This is what makes affix stripping safe without a morphological analyser. Arabic و ("and") is a
    # legitimate prefix, so ولد would strip to لد — which is not a word. Checking the remainder
    # against the frequency list stops that, and the frequency list is already there.
    only_if_remainder_known: bool


@dataclass(frozen=True, slots=True)
class CompoundConfig:
    r"""Splitting compound words, for languages that build them productively.

    ⚠️ GERMAN IS WHY THIS EXISTS, and the error it fixes runs in the dangerous direction.
    `Bahnhofstraße`, `Krankenversicherung` and every other productive compound is absent from any
    frequency list and always will be — the set is infinite. Without this, each one reads as an
    unknown word, so coverage UNDERSTATES a German learner's comprehension and the engine feeds
    easier and easier text to someone who understood the passage fine.

    ⚠️ THE TRADE, stated plainly because it is a real one. A decomposed compound keys to its HEAD —
    `Bahnhofstraße` → `straße` — so a learner who has proven `Straße` is credited with every
    compound ending in it. That is right for comprehension, which is what coverage measures: German
    compounds are transparent, and treating them as separate vocabulary is exactly the "flattened by
    a real book" failure this product exists to avoid. It is wrong for production, where
    `Bahnhofstraße` is a word you either know or do not.

    Safety comes from the same place as affix stripping: a split is accepted ONLY if every part is a
    word the frequency list contains. Nothing is guessed.
    """

    # Shortest acceptable part.
    #
    # ⚠️ Not optional and not 2. German is full of two-letter fragments that are also words — `ei`,
    # `so`, `an`, `um` — and at 2 almost any long word "decomposes" into nonsense. 4 is the
    # conservative default.
    min_part_length: int
    # Linking morphemes allowed between parts: German writes `Bahnhof-s-straße`, `Blume-n-topf`.
    #
    # The empty string must be included for compounds that join directly.
    linkers: Sequence[str]


@dataclass(frozen=True, slots=True)
class PackConfig:
    """Everything a pack declares about its language, as data."""

    id: str
    tokenize: TokenizeConfig
    # Applied in order to produce the canonical form.
    normalize: Sequence[NormalizeStep]
    # Applied in order before comparing an answer. Often the same list as `normalize`.
    compare: Sequence[NormalizeStep]
    affixes: AffixConfig | None = None
    # Compound splitting. Absent means the language does not build words this way.
    compounds: CompoundConfig | None = None


@dataclass(frozen=True, slots=True)
class PackData:
    """The data half of a pack: which words exist, and how common they are."""

    # Words ordered by frequency, most common first, separated by single spaces.
    #
    # A string rather than `{ "de": 1, "la": 2 }` because the POSITION is the rank, so no numbers are
    # stored at all. For 20k words that is roughly 180 KB instead of about 1.5 MB — and on Hermes the
    # object version is a multi-megabyte `JSON.parse` on the main thread before the first frame,
    # doubled if two languages are loaded.
    frequency: str
    # Optional surface → canonical map, for languages where affix rules are not enough.
    #
    # ⚠️ **A FORM MAY LIST MORE THAN ONE LEMMA, PRIMARY FIRST — and the list is the honest shape for
    # an unvocalised script.** Written Arabic drops the short vowels, so كتب is *he wrote*, *books*
    # and *he was made to write*, and a table with one column has to pick one of them silently. A
    # single string is still accepted and still means what it always meant; it is the unambiguous
    # case, not a different format.
    #
    # The FIRST entry is what `LanguagePack.key` returns, so a table that grows a second column
    # changes no unit key, no coverage figure and no schedule. The rest are reachable only through
    # `LanguagePack.candidates`, which exists so a reader can be shown what a form *can* be
    # instead of one guess wearing a confident face.
    #
    # Order carries meaning and nothing here sorts it: the pack author states which reading is
    # likeliest, because the engine has no basis on which to decide.
    #
    # Empty arrays, and entries that normalize away to nothing, are dropped — a form left with no
    # usable lemma is treated as absent from the table rather than as a form that keys to "".
    #
    # `create_pack` copies either shape into a `Map` anyway, so an object was always a transient that
    # existed to satisfy this type. A pack with more than ~100k rows should build the `Map` directly:
    # no ceiling, one fewer full copy at launch.
    lemmas: Mapping[str, str | Sequence[str]] | None = None


@dataclass(frozen=True, slots=True)
class LanguagePack:
    r"""The language pack contract.

    The engine knows no language. Everything language-specific arrives through this interface, which
    is why one engine can serve French, Arabic and anything else without a branch.

    Four functions was the whole surface. That is not minimalism for its own sake — every function
    here is one the engine genuinely cannot do itself, and nothing else qualifies. The header used to
    end "if a fifth is ever needed, that is a real signal about the design rather than a
    convenience", and `candidates` is that fifth. Here is the signal, stated rather than waved at:

    ⚠️ **`key` ANSWERS "ARE THESE THE SAME WORD?" AND CANNOT ALSO ANSWER "WHAT WORD IS THIS?".** The
    engine only ever needed the first, because it addresses knowledge and never renders meaning. A
    reader needs the second, and in an unvocalised script the second has more than one answer: كتب
    is *he wrote* and *books*, and no amount of canonicalisation makes that one word. Folding the two
    questions into one function is what made the pack table pick a reading silently — 86,910 Arabic
    surface forms, every one committed to exactly one lemma, nothing anywhere recording that a choice
    had been made (#177).

    So the fifth function is not a convenience over the fourth; it is the question the fourth was
    quietly answering wrong. `key` keeps its meaning exactly, `candidates` says what else the form
    could have been, and `candidates(s)[0] === key(s)` is enforced so the two can never drift.
    """

    # Identifies the pack, and IS the variety it addresses.
    #
    # ⚠️ **Branded as `Variety`, and that is a guarantee `create_pack` now enforces.** A pack id
    # containing a colon used to build fine while `variety()` rejected the same string — and if a host
    # forced it through, `unit_key('recognise', 'ar:msa', 'سوق')` produced `recognise:ar:msa:سوق`,
    # which `parse_unit_key` reads back as variety `ar`, word `msa:سوق`. A pack that builds, reports
    # healthy, and silently re-addresses every word it owns.
    #
    # Validating it at the one door that already returns a result makes that unrepresentable, and it
    # is what lets `learner()` default its variety: pack id and variety are the same string in every
    # pack that exists (`de`, `fr`, `ar-msa`), so restating it at the call site was duplication with a
    # live typo hazard — `variety('be')` beside a `de` pack files every unit under an address nothing
    # ever reads, forever, silently.
    #
    # ⚠️ This encodes ONE PACK PER VARIETY. That is true today and it is not free: the day a second
    # German pack ships (a graded-reader one beside the frequency one), both address `de` and the id
    # can no longer be the variety. The fix then is an optional `PackConfig.variety` defaulting to
    # `id` — purely additive, and it breaks no stored unit key.
    id: Variety
    # Text → surface tokens.
    #
    # The engine cannot do this: French splits on spaces and apostrophes, Arabic on spaces, Chinese
    # and Japanese on nothing at all and need a dictionary.
    split: Callable[[str], Sequence[str]]
    # Surface form → canonical form. The answer to "are these the same word?".
    #
    # `vais` and `allons` both key to `aller`; `السوق` keys to `سوق` with the article stripped. The
    # engine then addresses knowledge by this canonical form, so a learner who met `vais` gets credit
    # when they meet `allez`.
    key: Callable[[str], Lemma]
    # Surface form → every canonical form it could be, likeliest first. The answer to "what word is
    # this?", which is a different question from `key`'s.
    #
    # ⚠️ **NEVER EMPTY, AND THE FIRST ELEMENT IS ALWAYS `key(surface)`.** Both halves are load-bearing
    # and both are asserted by `check_pack`. A caller may therefore treat the list as "the answer, plus
    # the answers it beat", which means adding a second column to a pack's lemma table can never move
    # a unit key, a coverage figure or a schedule: everything that reads `key` reads element zero.
    #
    # ⚠️ **A ONE-ELEMENT LIST IS THE COMMON CASE AND MEANS "UNAMBIGUOUS", NOT "UNKNOWN".** A form the
    # pack has never heard of also comes back as one element — whatever `key` derived from it — so
    # length alone does not distinguish confidence from ignorance. Ask `rank` for that.
    #
    # ⚠️ **THE ENGINE ITSELF NEVER CALLS THIS.** Coverage, planning and the fold all address knowledge
    # by `key`, and giving them a list would mean deciding which reading a learner met — a decision
    # belonging to the learner, not to the scheduler. It exists for a host that renders help: showing
    # every sense a form can carry is a learning activity, whereas showing one guessed sense with a
    # caveat attached transfers the risk to the person least able to evaluate it.
    candidates: Callable[[str], Sequence[Lemma]]
    # How common a word is. `1` is the most common word in the language.
    #
    # `undefined` means "not in the list", i.e. rarer than anything the pack knows about.
    #
    # ⚠️ Deliberately NOT `Infinity` for unknown. `JSON.stringify(Infinity)` is `null`, so an
    # infinite rank that reaches a persisted profile or a report silently becomes a null and the
    # failure surfaces somewhere else entirely.
    #
    # This is a property of the LANGUAGE, not of the learner, which is why a pack must carry data and
    # cannot be pure code: you cannot derive how common a word is from one person's history.
    rank: Callable[[Lemma], int | None]
    # Is this answer right? `1` exact, `0` wrong, in between for partial credit.
    #
    # Language-specific because what counts as "the same answer" is: French folds accents, Arabic
    # folds diacritics that are optional in writing anyway.
    compare: Callable[[str, str], int]


# ── Coverage ────────────────────────────────────────────────────────────────────────────────────

# Where a text sits against the band.
#
# Named for what it means to a learner rather than for its position on a number line. `'too-easy'`
# is not good news: a text with nothing unknown in it teaches no vocabulary.
Band = Literal["too-hard", "in-band", "too-easy"]


@dataclass(frozen=True, slots=True)
class CoverageQuery:
    r"""What the engine is being asked to measure.

    A QUERY, not a passage — which is why `direction` belongs on it. Direction is a property of the
    question ("could she read this?" versus "could she say this?"), not of the text.
    """

    # Raw text.
    #
    # Deliberately not a pre-split token array. The pack owns tokenization, and the pack is already
    # an argument — accepting somebody else's tokens creates a second definition of "running token"
    # that the engine cannot police. A caller could split French text with an Arabic tokenizer, or
    # hand in a de-duplicated array, and get a plausible number with nothing able to detect it.
    #
    # To measure several passages together, concatenate them with a space. `split` resets its
    # `lastIndex` on every call, so the token streams concatenate exactly. **Never average two
    # coverage ratios** — 19/20 and 49/50 pool to 68/70 (0.9714) but average to 0.965, and the
    # verdict can flip on the difference.
    text: str
    # Which variety this text is written in. Required, never inferred.
    #
    # A diglossic profile holds two varieties at once — the dialect spoken at home and the standard
    # that is read — and they are measured separately. `profile.language` cannot stand in for this:
    # it is an opaque host string, and a profile with `language: 'ar'` is legitimately queried with
    # a pack whose id is `'ar-msa'`.
    variety: Variety
    # Which way the knowledge has to run. Required, and deliberately without a default.
    #
    # The gap between what a heritage speaker recognises and what they can produce is the single
    # defining feature of the learner this engine exists for. Defaulting to `'recognise'` would be
    # right for reading and silently wrong for a speaking task — and silently is the problem: every
    # number would still look plausible.
    direction: Direction
    # Surface forms in this text that are **not vocabulary** — names, brands, codes, foreign
    # fragments. Counted separately and excluded from the denominator.
    #
    # ⚠️ THE CALLER DECIDES, AND THAT IS THE WHOLE DESIGN. The obvious alternative is for the pack to
    # detect names itself, and for German it cannot: German capitalises EVERY noun, so "capitalised
    # and unknown" catches `Rezession` and `Impfpflicht` exactly as readily as `Toyota`. A pack-level
    # heuristic would hand the learner credit for not knowing ordinary German words, which inflates
    # the number the engine steers on — the one direction of error that must not be allowed.
    #
    # Arabic settles it: it has no letter case at all, so no token-level rule exists there even in
    # principle. Proper-noun detection is a property of the CONTENT, not of the language, and the host
    # is the only party that knows — it has the editor, or an NER pass, or a hand-tagged corpus.
    #
    # Why it matters: measured on held-out German news, names and acronyms are **66% of everything a
    # 10,000-lemma pack does not know**. Counting them makes coverage read 89.6%; excluding them makes
    # the same text read 96.8%, which is the difference between "unreachable" and "in band".
    #
    # Matched on the RAW surface, before normalization, because capitalisation is exactly the signal
    # a host uses to find them.
    ignore: Sequence[str] | None = None


@dataclass(frozen=True, slots=True)
class CoverageNoWords:
    # The pack found no words here.
    #
    # Covers an empty string, punctuation-only text, and the realistic case: text in a script
    # this pack does not cover — `arabic_pack.split('bonjour le monde')` is `[]`. `check_pack`
    # reports the same fact about a pack as `tokenizer-matches-nothing`.
    #
    # There is no coverage of a text with no words. 0/0 is not 0, and it is emphatically not
    # in band — see `COVERAGE_BAND` for why that needs saying out loud.
    kind: Literal["no-words"] = field(default="no-words", init=False)
    # Tokens the caller marked as not vocabulary.
    ignored_tokens: int
    # Tokens that `split()` produced and `key()` reduced to nothing.
    #
    # `0` means the tokenizer itself matched nothing. `> 0` means it matched and every match
    # keyed away to the empty string. One field, two distinguishable diagnoses.
    unkeyable_tokens: int


@dataclass(frozen=True, slots=True)
class CoverageTooShort:
    # Too short for the band to have a representable point.
    #
    # Returned **unconditionally** at this length, never conditionally on where the ratio happens
    # to fall. The counts below are real and useful; it is the CLASSIFICATION that does not
    # resolve. See `COVERAGE_BAND.min_tokens`.
    kind: Literal["too-short"] = field(default="too-short", init=False)
    running_tokens: int
    known_tokens: int
    unknown_tokens: int
    # Running tokens counted unknown that rest on a standing claim. See the header above.
    claimed_tokens: int
    unkeyable_tokens: int
    # Tokens the caller marked as not-vocabulary. See `CoverageQuery.ignore`.
    ignored_tokens: int
    unknown_lemmas: tuple[Lemma, ...]
    # `COVERAGE_BAND.min_tokens - running_tokens`. Always at least 1.
    needs_more_tokens: int


@dataclass(frozen=True, slots=True)
class CoverageMeasured:
    kind: Literal["measured"] = field(default="measured", init=False)
    # Tokens with a non-empty canonical form.
    #
    # RUNNING tokens — a repeat counts every time. `split('de de de la la')` is 5, not 2. The
    # band is a claim about unknown-word density in text a learner actually reads through, so
    # counting types instead would silently inflate every number.
    #
    # `known_tokens + unknown_tokens === running_tokens`, exactly. There is no third bucket:
    # unkeyable tokens are excluded from this count by definition rather than filtered out of it
    # afterwards.
    running_tokens: int
    # Proven knowledge only — see `is_known`. Never includes a bare claim.
    known_tokens: int
    unknown_tokens: int
    # Running tokens resting on a standing claim.
    #
    # ⚠️ MAY BE `> 0` on this variant, and that is not a contradiction: this kind means the band
    # comes out the same either way, which is the honest "it does not matter here" answer.
    claimed_tokens: int
    # Tokens dropped because `key()` returned the empty string.
    # `running_tokens + unkeyable_tokens + ignored_tokens === pack.split(text).length`.
    #
    # Reachable with an ordinary pack, not a contrivance: a run of tatweel — the Arabic
    # elongation character, plain typography — tokenizes as one word and `stripTatweel` erases
    # it. Such a token is structurally unaddressable, because `parse_unit_key` rejects a
    # zero-length word, so it can never be known. Counting it as unknown would push a passage
    # toward `'too-hard'` over a decorative character.
    unkeyable_tokens: int
    # Tokens the caller marked as not vocabulary — names, brands, codes.
    #
    # Excluded from `running_tokens` for the same reason `unkeyable_tokens` is: a learner who does
    # not recognise `Toyota` has no vocabulary gap, and counting it as one makes every text look
    # harder than it is. See `CoverageQuery.ignore`.
    ignored_tokens: int
    # Distinct unknown lemmas, de-duplicated, in first-appearance order.
    #
    # Not sorted: every tiebreak wants a string comparator, the idiomatic one is `localeCompare`,
    # and that is ICU-backed and banned here. First-appearance order is free, deterministic on
    # every runtime, and what a reading screen wants anyway.
    #
    # This is a TYPE count — `unknown_lemmas.length <= unknown_tokens` — and must never be used as
    # a numerator.
    #
    # Deliberately carries no rank. `rank(key(w))` is genuinely `undefined` for words a pack's
    # own frequency list contains, whenever a lemma entry points somewhere the list does not go;
    # shipping the field would ship a number that is missing for no reason a caller can see.
    unknown_lemmas: tuple[Lemma, ...]
    band: Band


@dataclass(frozen=True, slots=True)
class CoverageUnverified:
    # The verdict depends on whether you believe an unchecked claim. See the header above.
    #
    # Both readings are carried and neither is privileged, because the engine genuinely does not
    # know which is right — that is what a placement is for, and this variant is how the engine
    # asks for one.
    kind: Literal["unverified"] = field(default="unverified", init=False)
    running_tokens: int
    # Proven only. The strict reading's numerator.
    known_tokens: int
    unknown_tokens: int
    # Always `> 0` here, and always enough to flip the verdict — or this variant is not returned.
    claimed_tokens: int
    unkeyable_tokens: int
    ignored_tokens: int
    # Unknown under the STRICT reading, so claimed lemmas appear here too.
    unknown_lemmas: tuple[Lemma, ...]
    # Counting only what she has proven.
    strict: Band
    # Counting standing claims as known. Always `!== strict`.
    with_claims: Band
    # Distinct claimed-but-unchecked lemmas in this text, first-appearance order.
    #
    # ⚠️ Feed these — through `key()` and `unit_key()` — straight into `PlanOptions.priority`.
    # Coverage's own uncertainty becomes tomorrow's drill list: the words she is about to read that
    # nobody has checked are exactly the words worth checking, and the loop closes with no new
    # machinery anywhere.
    #
    # A TYPE count like `unknown_lemmas`, and never a numerator.
    claimed_lemmas: tuple[Lemma, ...]


# How much of a text this learner knows.
#
# ⚠️ **FOUR kinds. `'unverified'` is NOT a fourth way of failing to resolve.** `'no-words'` and
# `'too-short'` still mean "I cannot tell" and still carry no band at all. `'unverified'` means
# something sharper: **the verdict CHANGES depending on whether you believe an unchecked
# self-report**, so it carries BOTH readings and makes the caller pick which one to act on.
#
# It exists because of a measured gap. `coverage()` counts a unit known only once it has been
# proven, so a learner placed at 800 claimed words reads ~0% on every text until the app has
# actually drilled them — for months, on the learner whose defining trait is already knowing a lot.
# Counting claims silently instead would compute the band on self-report, which correlates only
# about **r ≈ .39** with tested proficiency. Neither is honest, so the disagreement is surfaced.
#
# The trigger needs no new constant and no threshold to tune. `coverage()` classifies twice —
# strictly (only proven counts) and generously (a standing claim counts too) — and returns
# `'measured'` when the two AGREE. "The answer changes" is the only non-arbitrary definition of
# "I cannot tell" available here. It also self-extinguishes: every verification moves a token from
# claimed to known, so the category drains to `'measured'` with nobody adjusting anything.
#
# Consequently `'measured'` now means something STRONGER than it did in v2: this verdict is robust
# to whether you trust her.
#
# ⚠️ **`band` exists only on `'measured'`, and that is the load-bearing shape decision here.**
#
# The tempting alternative is one flat object with a four-valued band including something like
# `'unknown'`. It reads fine and it leaves this compiling:
#
# ```ts
# if (result.band !== 'in-band') give_them_something_easier();
# ```
#
# The variants are written out in full rather than sharing a base type, matching `UnitState`.
Coverage = CoverageNoWords | CoverageTooShort | CoverageMeasured | CoverageUnverified


# ── The session ─────────────────────────────────────────────────────────────────────────────────

# Why an item is in the session. Derived on every call and stored nowhere.
#
# - `learning`: in its learning steps and due (or due within the learn-ahead window).
# - `relearn`: failed in review, in its relearning steps and due.
# - `review`: graduated and due.
# - `verify`: claimed, never asked. "You told us you know this — let's check."
# - `new`: met but never asked, and not claimed.
# - `ahead`: not due yet, included because the host asked to study ahead.
Why = Literal["learning", "relearn", "review", "verify", "new", "ahead"]


@dataclass(frozen=True, slots=True)
class PlanOptions:
    """What the caller asks of `plan()`."""

    # The instant to plan for. Time is data; there is no clock in here to read.
    now: Instant
    # How many units to drill. Clamped to a whole number ≥ 0.
    max_items: int | float
    # How many units never asked before (`new` and `verify`) may be introduced. Clamped to
    # `[0, max_items]`. Defaults to `floor(max_items / 2)`.
    max_new: int | float | None = None
    # How far ahead a learning or relearning unit may be pulled in, in seconds. Defaults to
    # `LEARN_AHEAD_SECONDS` (20 minutes, Anki's default), so a 10-minute step does not leave a
    # session waiting on the clock.
    learn_ahead_seconds: int | float | None = None
    # Fill slots left over after everything due with units that are NOT due yet, weakest first.
    #
    # This is the "I have time today" and "exam tomorrow" mode. Reviewing early is safe: FSRS
    # credits a review by how much she had forgotten, so an early success raises stability only a
    # little and cannot fake a long-term memory.
    study_ahead: bool = False
    # Which units to prefer when two are otherwise equal — commonest first, typically. Units absent
    # from this list sort after every unit in it. Omit it and the key tiebreak applies.
    priority: Sequence[UnitKey] | None = None


@dataclass(frozen=True, slots=True)
class SessionItem:
    """One thing to do, with the reason it was chosen — so a host can explain itself to a learner."""

    unit: UnitKey
    # Which partition this came from. See `Why`.
    why: Why
    # When the unit was due. `0` for `new` and `verify`, which have no schedule yet.
    due: Instant
    # FSRS's estimate that she would recall it right now, from 0 to 1. `0.0` for units with no memory
    # model yet.
    retrievability: float


@dataclass(frozen=True, slots=True)
class ContentRequest:
    r"""The content this session needs, described rather than fetched."""

    # The units to build retrieval exercises for, in the order they should be presented.
    #
    # ⚠️ **May be longer than `max_items`.** A missing exercise for one word should cost that word,
    # not the session; a host takes the first `max_items` it can actually build.
    units: tuple[UnitKey, ...]
    # The minimum running-token length of any passage this session shows. See
    # `COVERAGE_BAND.min_tokens`.
    min_passage_tokens: int
    # New slots `plan()` was allowed to fill and could NOT, for want of any unmet unit in the
    # profile. The host picks that many words she has not met, shows them, and records the evidence.
    new_units_wanted: int


@dataclass(frozen=True, slots=True)
class ReassessNotDue:
    kind: Literal["not-due"] = field(default="not-due", init=False)
    days_until: int


@dataclass(frozen=True, slots=True)
class ReassessNeverMeasured:
    # Nothing has EVER been successfully retrieved, so there is no span to report.
    kind: Literal["never-measured"] = field(default="never-measured", init=False)
    claims_standing: int


@dataclass(frozen=True, slots=True)
class ReassessDue:
    kind: Literal["due"] = field(default="due", init=False)
    days_since_proven: int
    claims_standing: int


Reassess = ReassessNotDue | ReassessNeverMeasured | ReassessDue


@dataclass(frozen=True, slots=True)
class Session:
    r"""What a learner should do next, and what content the host must fetch to make it possible."""

    now: Instant
    items: tuple[SessionItem, ...]
    content: ContentRequest
    reassess: Reassess
    stuck: tuple[UnitKey, ...]


# ── Reporting ───────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ScopeAll:
    kind: Literal["all"] = field(default="all", init=False)


@dataclass(frozen=True, slots=True)
class ScopeSkill:
    kind: Literal["skill"] = field(default="skill", init=False)
    variety: Variety
    modality: Modality


# What a `Summary` covers.
#
# A union rather than two optional fields, so that "I am blurring MSA and my home dialect into one
# number" is something the caller had to type. It is the same discipline that gives
# `CoverageQuery.direction` no default: for a diglossic learner those are two systems, and one
# number across them is a category error rather than a convenience.
#
# ⚠️ **THE SCOPE KEYS ON `modality`, NOT `direction` (ADR-0022), AND THE PARTITION LAW IS WHY.**
# `summarize` promises that the per-skill scopes partition the profile exactly — nothing
# double-counted, nothing dropped. Once `parse_unit_key` accepts every modality, a `skill:` or
# `pronounce:` unit is counted by `'all'`; if this still asked for a `Direction`, no per-skill scope
# could ever match one and the law would break silently, understating the parts against the whole.
#
# ⚠️ **IT IS ALSO THE PRIMITIVE THE PER-MODALITY DIAGNOSIS NEEDS** (lughaty#166):
# `summarize(profile, { kind: 'skill', modality: 'produce', variety: ar })` against the same for
# `'recognise'` is the recognise-4,100 / produce-640 comparison, with no new function.
SummaryScope = ScopeAll | ScopeSkill


@dataclass(frozen=True, slots=True)
class Summary:
    r"""A snapshot of what the engine believes, small enough to store every day forever.

    The engine stores no history: the host keeps these and the raw evidence log.
    """

    now: Instant
    language: str
    scope: SummaryScope
    units: int
    # Units in each card state.
    new: int
    learning: int
    review: int
    relearning: int
    # See `is_known`.
    known: int
    claims_standing: int
    claims_confirmed: int
    claims_refuted: int
    stuck: int
    days_since_proven: int


# ── Results ─────────────────────────────────────────────────────────────────────────────────────

# Why a stored profile could not be read.
DecodeErrorKind = Literal["not-json", "malformed", "from-the-future", "no-migration"]


@dataclass(frozen=True, slots=True)
class DecodeError:
    """What went wrong, in a form that is safe to log."""

    kind: DecodeErrorKind
    # Human-readable, safe to log. Contains no learner content.
    message: str


@dataclass(frozen=True, slots=True)
class DecodedOk[T]:
    ok: Literal[True] = field(default=True, init=False)
    value: T


@dataclass(frozen=True, slots=True)
class DecodedError:
    ok: Literal[False] = field(default=False, init=False)
    error: DecodeError


# Why decoding returns a value instead of throwing.
#
# This function runs at app launch on data written by an older version of the code. If it throws,
# a learner opens the app and it dies — and the one thing they cannot do about it is downgrade.
# A returned error can be handled: start fresh, restore a backup, report it, keep the bad blob for
# diagnosis. An exception thrown from a module-level load can do none of those.
type Decoded[T] = DecodedOk[T] | DecodedError


# Reachable through untyped JSON only; `Any` documents that the door checks everything itself.
UnknownJson = Any
