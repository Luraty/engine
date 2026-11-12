"""Deciding what a learner should do next."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final, cast

from luraty_engine import _js
from luraty_engine.core.memory import retrievability
from luraty_engine.model import (
    COVERAGE_BAND,
    LEARN_AHEAD_SECONDS,
    NEVER,
    SECONDS_PER_DAY,
    ContentRequest,
    Instant,
    PlanOptions,
    Profile,
    Reassess,
    ReassessDue,
    ReassessNeverMeasured,
    ReassessNotDue,
    Session,
    SessionItem,
    UnitKey,
    UnitState,
    Why,
    has_standing_claim,
)

# How many more units to name than the session will use.
#
# Not a learning constant — an engineering one, about hosts. A content store will not have an
# exercise for every unit, and a session that shrinks because one word had no card is a worse
# failure than naming a few spares. Three is enough to absorb a two-thirds miss rate.
OVER_ASK: Final = 3

# Days without a single successful retrieval before `plan()` asks for a re-measurement.
#
# ⚠️ PROVISIONAL, and a product rhythm rather than a finding. It counts from the last PROOF, so a
# learner drilling daily and getting things right is never nagged.
REASSESS_AFTER_DAYS: Final = 30

# Consecutive failed retrievals before a unit is reported in `Session.stuck` (Anki calls these
# leeches). Report-only: the unit stays in rotation, and what to do about it is the host's call.
STUCK_AFTER_LAPSES: Final = 6


def _clamp(value: object, fallback: int | float) -> int | float:
    """Whole, non-negative, and finite. A bad option is clamped, never thrown at the caller."""
    if not _js.is_number(value) or not math.isfinite(cast(float, value)):
        return fallback
    return max(0, _js.trunc(_js.number(cast(float, value))))


def _helped_since_asked(state: UnitState) -> bool:
    r"""She tapped the gloss after the last time she was tested on it.

    That is the best moment to test it: she met it, wanted it, and could not produce it. A unit like
    this is treated as due now, whatever its schedule says. Proves nothing — the memory model is
    untouched until the retrieval actually happens.
    """
    return state.last_helped > state.last_asked


def plan(profile: Profile, options: PlanOptions) -> Session:
    r"""Decide what to do next.

    **Takes no language pack**: scheduling is language-free, and only measurement needs a language.
    When the profile cannot fill the new-material budget, the engine REQUESTS words rather than
    picking them: `ContentRequest.new_units_wanted`.

    ### The order, Anki's

    1. **Learning and relearning** units due by `now + learn_ahead_seconds`, earliest due first.
       Minutes-scale steps, so they come first or they go stale.
    2. **Reviews** that are due, lowest retrievability first — the ones she is likeliest to have
       forgotten.
    3. **Verifications**: claimed, never asked. Checking a word she says she knows is not teaching
       her one, so these are not charged to `max_new`.
    4. **New** units, at most `max_new` of them.
    5. **Ahead**, only with `study_ahead`: everything not yet due, lowest retrievability first.

    A unit she tapped the gloss on since her last retrieval counts as due now (see
    `_helped_since_asked`). Within new and verify, the most recently helped come first. Every
    remaining tie goes to `options.priority`, then to the unit key, so a session is a pure function of
    the profile and the options.

    `max_items` bounds the whole session. `max_new` is a hard cap: a session with nothing due and few
    new units is short rather than padded.

    **Total.** No throws. Bad numbers are clamped.
    """
    now = options.now
    max_items = _clamp(options.max_items, 0)
    max_new = min(_clamp(options.max_new, _js.floor(max_items / 2)), max_items)
    horizon = now + _clamp(options.learn_ahead_seconds, LEARN_AHEAD_SECONDS)

    priority: dict[UnitKey, int] = {}
    for index, unit in enumerate(options.priority if options.priority is not None else ()):
        priority.setdefault(unit, index)

    def tiebreak(unit: UnitKey) -> tuple[float, bytes]:
        return (priority.get(unit, math.inf), _js.utf16_key(unit))

    learning: list[SessionItem] = []
    reviews: list[SessionItem] = []
    verify: list[tuple[UnitState, SessionItem]] = []
    new: list[tuple[UnitState, SessionItem]] = []
    ahead: list[SessionItem] = []
    stuck: list[UnitKey] = []
    last_proven_anywhere = NEVER
    claims_standing = 0

    for unit, state in profile.units.items():
        if state.last_proven > last_proven_anywhere:
            last_proven_anywhere = state.last_proven
        if state.lapses >= STUCK_AFTER_LAPSES:
            stuck.append(unit)
        if has_standing_claim(state):
            claims_standing += 1

        if state.card == "new":
            why: Why = "verify" if state.prior.kind == "claimed" else "new"
            item = SessionItem(unit=unit, why=why, due=NEVER, retrievability=0.0)
            (verify if why == "verify" else new).append((state, item))
            continue

        recall = retrievability(state, now)
        helped = _helped_since_asked(state)

        if state.card in ("learning", "relearning"):
            why = "learning" if state.card == "learning" else "relearn"
            if state.due <= horizon or helped:
                learning.append(SessionItem(unit=unit, why=why, due=state.due, retrievability=recall))
                continue
        elif state.due <= now or helped:
            reviews.append(SessionItem(unit=unit, why="review", due=state.due, retrievability=recall))
            continue

        ahead.append(SessionItem(unit=unit, why="ahead", due=state.due, retrievability=recall))

    learning.sort(key=lambda item: (item.due, *tiebreak(item.unit)))
    reviews.sort(key=lambda item: (item.retrievability, *tiebreak(item.unit)))
    ahead.sort(key=lambda item: (item.retrievability, item.due, *tiebreak(item.unit)))

    def never_asked_order(entry: tuple[UnitState, SessionItem]) -> tuple[int, float, bytes]:
        state, item = entry
        return (-state.last_helped, *tiebreak(item.unit))

    verify.sort(key=never_asked_order)
    new.sort(key=never_asked_order)

    partitions = (
        learning,
        reviews,
        [item for _, item in verify],
        [item for _, item in new],
        ahead if options.study_ahead else [],
    )

    items = _select(partitions, max_items, max_new)
    named = _with_spares(partitions, items, max_items * OVER_ASK, max_new * OVER_ASK)

    taken_new = sum(1 for item in items if item.why == "new")
    room_for_new = min(max_new, max_items - sum(1 for item in items if item.why != "new"))
    content = ContentRequest(
        units=tuple(item.unit for item in named),
        min_passage_tokens=COVERAGE_BAND.min_tokens,
        new_units_wanted=int(max(0, room_for_new - taken_new)) if len(new) == taken_new else 0,
    )

    return Session(
        now=now,
        items=tuple(items),
        content=content,
        reassess=_reassessment(now, last_proven_anywhere, claims_standing),
        stuck=tuple(sorted(stuck, key=_js.utf16_key)),
    )


def _select(
    partitions: Sequence[Sequence[SessionItem]], limit: int | float, new_limit: int | float
) -> list[SessionItem]:
    r"""Take items partition by partition, in order, up to `limit`, admitting at most `new_limit` new.

    ⚠️ New material is RESERVED its share before verification takes the rest. Without that, a
    placement of 800 claims would fill every session for weeks and no new word could ever arrive.
    """
    learning, reviews, verify, new, ahead = partitions
    chosen: list[SessionItem] = []

    def take(source: Sequence[SessionItem], room: int | float) -> None:
        for item in source:
            if room <= 0 or len(chosen) >= limit:
                return
            chosen.append(item)
            room -= 1

    take(learning, limit)
    take(reviews, limit)
    reserved = min(new_limit, len(new), max(0, limit - len(chosen)))
    take(verify, limit - len(chosen) - reserved)
    take(new, min(new_limit, limit - len(chosen)))
    take(ahead, limit - len(chosen))
    return chosen


def _with_spares(
    partitions: Sequence[Sequence[SessionItem]],
    items: Sequence[SessionItem],
    limit: int | float,
    new_limit: int | float,
) -> list[SessionItem]:
    r"""The session, then the spares, in partition order — still capped.

    ⚠️ `content.units` MUST BEGIN WITH `items`. The contract is that a host takes the first
    `max_items` it can build, so any prefix of this list has to agree with the session.
    """
    chosen = {item.unit for item in items}
    named = list(items)
    introduced = sum(1 for item in items if item.why == "new")
    for item in (item for part in partitions for item in part):
        if len(named) >= limit:
            break
        if item.unit in chosen:
            continue
        if item.why == "new":
            if introduced >= new_limit:
                continue
            introduced += 1
        named.append(item)
    return named


def _reassessment(now: Instant, last_proven: Instant, claims_standing: int) -> Reassess:
    r"""Whether it is time to re-measure. See `Reassess`."""
    if last_proven == NEVER:
        return ReassessNeverMeasured(claims_standing=claims_standing)

    days_since_proven = max(0, (now - last_proven) // SECONDS_PER_DAY)
    if days_since_proven >= REASSESS_AFTER_DAYS:
        return ReassessDue(days_since_proven=days_since_proven, claims_standing=claims_standing)
    return ReassessNotDue(days_until=REASSESS_AFTER_DAYS - days_since_proven)
