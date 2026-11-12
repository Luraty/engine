r"""A fluent handle on one learner, for hosts that would rather not thread four arguments.

⚠️ **ENTIRELY OPTIONAL, AND IT ADDS NO POWER.** Every method here delegates to a function that is
still exported and still works exactly as before. If you prefer the free functions, use them; the
two styles produce identical profiles and can be mixed in one file.

### Why this exists at all

*"Why functional? Why not `profile.plan()`?"* — a fair question, and the answer separates two
things that were being conflated.

**Purity is load-bearing.** Value-in / value-out is what lets a test fork a learner, diff two
profiles, bisect a replay, and simulate four hundred headless learners from a seed. It is the
property everything else in this package rests on and it is not negotiable.

**Free functions are not.** `profile.plan(...)` returning a new value is equally pure. The default
was never justified, and the ceremony it costs is real: a host repeats `direction`, `variety` and
`day` at every call site, and the same "turn a word list into evidence" `.map` gets written again
and again.

So the core stays pure and free-function, and this wraps it.

### The rules it keeps

- **Immutable.** Every method that records evidence returns a NEW `Learner`. Nothing mutates.
- **`profile` is always reachable**, so you can drop back to the free functions at any moment —
  this is a convenience, never a wall.
- **No hidden state.** A `Learner` is its profile plus the constants (`pack`, `variety`,
  `direction`, `vocabulary`) a host would otherwise pass to every call. It stores nothing about
  the learner that the profile does not.
- **No I/O.** `save()` returns a string; where it goes is still yours.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from luraty_engine.core.bulk import claims_for, exposures_for, keys_for, words_in
from luraty_engine.core.coverage import coverage
from luraty_engine.core.persist import serialize
from luraty_engine.core.plan import plan
from luraty_engine.core.profile import advance_to
from luraty_engine.core.record import record
from luraty_engine.core.summary import summarize
from luraty_engine.model import (
    Coverage,
    CoverageQuery,
    Instant,
    Direction,
    Evidence,
    Help,
    LanguagePack,
    Rating,
    PlanOptions,
    Profile,
    Retrieval,
    ScopeSkill,
    Session,
    Summary,
    SummaryScope,
    UnitKey,
    Variety,
)


@dataclass(frozen=True, slots=True)
class LearnerContext:
    """What a Learner needs besides the profile — the arguments you would otherwise repeat."""

    # The language pack. Only `coverage` and the word helpers use it.
    pack: LanguagePack
    # Which variety these operations address. **Defaults to `pack.id`.**
    #
    # Pack id and variety are the same string in every pack that exists (`de`, `fr`, `ar-msa`), and
    # `create_pack` now validates the id as a legal variety — so restating it here was duplication
    # with a live typo hazard: `variety('be')` beside a `de` pack files every unit under an address
    # nothing ever reads, forever and silently.
    #
    # ⚠️ **Pass it explicitly when it genuinely differs.** The case that matters is diglossia: a
    # Levantine-speaking learner reading MSA has one profile with two varieties in it, and if you
    # ever run one pack over both, the default would merge her reading and her home dialect into one
    # unit key — the exact category error the two-variety design exists to prevent.
    variety: Variety | None = None
    # Which direction these operations address. Defaults to `'recognise'`.
    #
    # ⚠️ A default here is safe in a way `CoverageQuery.direction` deliberately is not: this is a
    # handle a host constructs and names, so `read` versus `speak` is visible at the call site rather
    # than buried in one argument of one call.
    direction: Direction | None = None
    # The pack's own vocabulary, commonest first — usually `vocabulary_of(pack, frequency)`.
    #
    # ⚠️ Supplied by the host rather than read off the pack, because **a `LanguagePack` does not carry
    # its frequency list**. It carries `rank(lemma)`, which answers "how common is this?" and cannot
    # enumerate. That is deliberate: the list is the host's data, and the engine holding a copy of
    # 10,000 words per language is exactly the memory cost `PackData.frequency` being a string avoids.
    #
    # Omit it and `plan()` falls back to the key tiebreak, which sorts alphabetically — deterministic,
    # correct, and a bad lesson. See `PlanOptions.priority`.
    vocabulary: Sequence[str] | None = None


@dataclass(frozen=True, slots=True)
class Learner:
    """One learner, one language, one skill — with the engine's functions hanging off it.

    Construct with `learner`.
    """

    # The underlying value. Pass it to any free function; this is never a one-way door.
    profile: Profile
    pack: LanguagePack
    variety: Variety
    direction: Direction
    _context: LearnerContext = field(repr=False, compare=False)
    _priority_cache: list[tuple[UnitKey, ...]] = field(default_factory=list, repr=False, compare=False)

    def _next(self, profile: Profile) -> Learner:
        return learner(profile, self._context)

    def _canonical(self, words: Sequence[str]) -> tuple[str, ...]:
        # Put a host's words into the pack's canonical form before they become unit keys.
        #
        # ⚠️ **THIS IS THE WHOLE REASON THE HANDLE CARRIES A PACK.** The free functions cannot do it —
        # `keys_for` takes no pack, so its contract is "hand me lemmas" and its callers pass the output of
        # `vocabulary_of`. The facade has the pack, so a host writing the obvious thing must not be
        # silently wrong.
        #
        # And it was. `answer('Schlüssel', …)` wrote to `recognise:de:schlüssel`, while `read()`,
        # `coverage()` and every lemma from `vocabulary_of` address `recognise:de:schluessel` — the German
        # pack transliterates umlauts. Two units, one word, no error, no failing test: the shipped example
        # only ever used words identical to their own keys (`haus`, `verordnung`), so nothing caught it.
        #
        # Safe for already-keyed input because `key` is idempotent — a pack property law
        # (`pack.property.test.ts`), and verified across all 9,981 lemmas of the real German pack.
        return tuple(self.pack.key(w) for w in words)

    def _default_priority(self) -> tuple[UnitKey, ...]:
        if not self._priority_cache:
            vocabulary = self._context.vocabulary if self._context.vocabulary is not None else ()
            self._priority_cache.append(
                keys_for(self.direction, self.variety, self._canonical(vocabulary))
            )
        return self._priority_cache[0]

    # ── writing ───────────────────────────────────────────────────────────────────────────────────

    def record(self, evidence: Sequence[Evidence]) -> Learner:
        """Fold in evidence you built yourself. The escape hatch: everything else here is sugar over it."""
        return self._next(record(self.profile, evidence))

    def answer(self, word: str, rating: Rating, at: Instant) -> Learner:
        """She was asked, and answered."""
        return self._next(
            record(
                self.profile,
                [
                    Retrieval(unit=unit, rating=rating, at=at)
                    for unit in keys_for(self.direction, self.variety, self._canonical([word]))
                ],
            )
        )

    def claim(self, words: Sequence[str], at: Instant) -> Learner:
        """The host says she knows these; nobody has checked. The output of a placement."""
        return self._next(
            record(self.profile, claims_for(self.direction, self.variety, self._canonical(words), at))
        )

    def read(self, text: str, at: Instant) -> Learner:
        """She read this text. Mints a unit for every word in it and proves nothing."""
        return self._next(
            record(
                self.profile,
                exposures_for(self.direction, self.variety, words_in(self.pack, text), at),
            )
        )

    def help(self, word: str, at: Instant) -> Learner:
        """She tapped the gloss — the most informative thing that happens while reading."""
        return self._next(
            record(
                self.profile,
                [
                    Help(unit=unit, at=at)
                    for unit in keys_for(self.direction, self.variety, self._canonical([word]))
                ],
            )
        )

    def on(self, now: Instant) -> Learner:
        """Move her forward in time. Refuses to go backwards, like `advance_to`."""
        return self._next(advance_to(self.profile, now))

    # ── reading ───────────────────────────────────────────────────────────────────────────────────

    def plan(self, options: PlanOptions) -> Session:
        r"""What to practise.

        `priority` defaults to `LearnerContext.vocabulary`, keyed once and cached — the answer
        almost every host wants, and ten lines to build by hand. Pass your own to override.
        """
        priority = options.priority if options.priority is not None else self._default_priority()
        return plan(self.profile, replace(options, priority=priority))

    def coverage(self, text: str, ignore: Sequence[str] | None = None) -> Coverage:
        """How hard is this text for her?"""
        return coverage(
            self.profile,
            self.pack,
            CoverageQuery(text=text, variety=self.variety, direction=self.direction, ignore=ignore),
        )

    def summary(self, scope: SummaryScope | None = None) -> Summary:
        """A fixed-size snapshot to persist and diff. Defaults to this skill, not the whole profile."""
        return summarize(
            self.profile,
            scope if scope is not None else ScopeSkill(variety=self.variety, modality=self.direction),
        )

    def save(self) -> str:
        """Canonical bytes. Where they go is still yours."""
        return serialize(self.profile)


def learner(profile: Profile, context: LearnerContext) -> Learner:
    r"""Wrap a profile.

    ```ts
    const words = vocabulary_of(pack, frequency);
    const anna = learner(create_profile('de', t1), { pack, variety: de, vocabulary: words });
    const session = anna.claim(words.slice(0, 400), t1).plan({ now: t1, max_items: 8, max_new: 3 });
    ```

    Cheap: it holds three references and keys the vocabulary lazily, on the first `plan()` that does
    not supply its own `priority`.
    """
    pack = context.pack
    # No error channel and no throw: `create_pack` already rejected an id that is not a legal variety,
    # so `pack.id` is a `Variety` by type and this default cannot fail.
    resolved_variety = context.variety if context.variety is not None else pack.id
    direction = context.direction if context.direction is not None else "recognise"
    return Learner(
        profile=profile,
        pack=pack,
        variety=resolved_variety,
        direction=direction,
        _context=context,
    )
