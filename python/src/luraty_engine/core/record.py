# Folding evidence into a profile.
#
# This is the only function in the engine that changes what is believed about a learner. Everything
# else reads.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from types import MappingProxyType

from luraty_engine import _js
from luraty_engine.core.memory import review
from luraty_engine.model import (
    UNMET,
    Evidence,
    Instant,
    Prior,
    PriorClaimed,
    Profile,
    Rating,
    UnitState,
)
from luraty_engine.utils import assert_never


def later(a: Instant, b: Instant) -> Instant:
    r"""Later of two instants.

    ⚠️ MONOTONIC, and every bookkeeping date in `UnitState` folds through it, so a late-arriving
    piece of evidence can never rewind a unit.
    """
    return a if a > b else b


def claimed(prior: Prior, at: Instant) -> Prior:
    r"""Fold one claim into a unit's prior. A max-fold, so re-claiming is safe and order-free."""
    match prior.kind:
        case "none":
            return PriorClaimed(on=at)
        case "claimed":
            return PriorClaimed(on=later(prior.on, at))
        case _:
            assert_never(prior, "Prior")


def _effective_rating(state: UnitState, rating: Rating) -> Rating:
    r"""What a retrieval is worth once a claim is taken into account.

    ⚠️ **A CLAIM PROVEN ON ITS FIRST RETRIEVAL IS SCHEDULED AS `easy`.** She said she knows it and
    then showed it: two signals from different sources. Scheduling that as `good` would walk a word
    she has known for years through the minute-scale learning steps. Only the first retrieval, only
    `good`, only a claimed unit: a bare claim still proves nothing, and a claim followed by `again` or
    `hard` is scheduled exactly as the rating says.
    """
    if state.card == "new" and state.prior.kind == "claimed" and rating == "good":
        return "easy"
    return rating


def apply_one(state: UnitState, evidence: Evidence) -> UnitState:
    r"""Apply one piece of evidence to one unit's state. See the table on `Evidence`."""
    match evidence.kind:
        case "retrieval":
            remembered = evidence.rating != "again"
            reviewed = review(state, _effective_rating(state, evidence.rating), evidence.at)
            return replace(
                reviewed,
                seen=_js.add(state.seen, 1),
                last_seen=later(state.last_seen, evidence.at),
                last_asked=later(state.last_asked, evidence.at),
                last_proven=later(state.last_proven, evidence.at) if remembered else state.last_proven,
                reviews=_js.add(state.reviews, 1),
                lapses=0 if remembered else _js.add(state.lapses, 1),
            )

        case "exposure":
            # Met and moved on. Nobody asked, so nothing is proven and no memory moves.
            return replace(
                state,
                seen=_js.add(state.seen, 1),
                last_seen=later(state.last_seen, evidence.at),
            )

        case "help":
            # She met it and wanted it. Proves nothing; `plan` reads `last_helped` to bring it forward.
            return replace(
                state,
                seen=_js.add(state.seen, 1),
                last_seen=later(state.last_seen, evidence.at),
                last_helped=later(state.last_helped, evidence.at),
            )

        case "claim":
            # Sets `prior` and nothing else — nobody encountered anything.
            return replace(state, prior=claimed(state.prior, evidence.at))

        case _:
            assert_never(evidence, "Evidence")


def record(profile: Profile, evidence: Sequence[Evidence]) -> Profile:
    r"""Fold evidence into a profile, returning a new profile.

    **This is a fold.** Applying evidence one item at a time equals applying it in one batch:
    `record(record(p, [a]), [b])` and `record(p, [a, b])` give the same profile.

    ⚠️ **THE MEMORY MODEL IS ORDER-DEPENDENT.** FSRS is a sequence of reviews, so `[again, good]` and
    `[good, again]` end in different places. The bookkeeping dates are max-folds and are not.
    A host syncing an offline queue must sort it by `at` before folding it, and must keep the raw
    evidence log: a re-fold from the log is the repair path and the migration path.

    The profile's `now` is NOT advanced here. Evidence carries the instant it happened, which may be
    in the past. Moving the learner through time is `advance_to`.
    """
    if len(evidence) == 0:
        return profile

    units = dict(profile.units)

    for item in evidence:
        units[item.unit] = apply_one(units.get(item.unit, UNMET), item)

    return Profile(language=profile.language, now=profile.now, units=MappingProxyType(units))
