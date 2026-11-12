# The memory model: FSRS, through the reference implementation (`fsrs` on PyPI).
#
# This file is the only one that knows FSRS exists. Everything else reads `UnitState`'s plain fields,
# so swapping the algorithm or its parameters is an edit here and nowhere else.

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Final

from fsrs import Card, Rating, Scheduler, State

from luraty_engine.model import (
    DESIRED_RETENTION,
    LEARNING_STEPS_SECONDS,
    MAXIMUM_INTERVAL_DAYS,
    NEVER,
    RELEARNING_STEPS_SECONDS,
    CardState,
    Instant,
    UnitState,
)
from luraty_engine.model import Rating as EngineRating

_RATINGS: Final[dict[EngineRating, Rating]] = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}

_STATES: Final[dict[State, CardState]] = {
    State.Learning: "learning",
    State.Review: "review",
    State.Relearning: "relearning",
}

_FSRS_STATES: Final[dict[CardState, State]] = {value: key for key, value in _STATES.items()}

# FSRS uses the card id only to seed fuzzing, and fuzzing is off.
_CARD_ID: Final = 1


@cache
def scheduler() -> Scheduler:
    r"""The one FSRS scheduler, with the engine's parameters.

    ⚠️ **FUZZING IS OFF.** Fuzzing spreads due dates with a random number generator, which would make
    the same evidence fold to different profiles. The engine's sessions are a pure function of the
    profile, so the schedule has to be too.
    """
    return Scheduler(
        desired_retention=DESIRED_RETENTION,
        learning_steps=tuple(timedelta(seconds=s) for s in LEARNING_STEPS_SECONDS),
        relearning_steps=tuple(timedelta(seconds=s) for s in RELEARNING_STEPS_SECONDS),
        maximum_interval=MAXIMUM_INTERVAL_DAYS,
        enable_fuzzing=False,
    )


def _datetime(at: Instant) -> datetime:
    return datetime.fromtimestamp(at, UTC)


def _instant(at: datetime) -> Instant:
    return Instant(int(at.timestamp()))


def _card(state: UnitState) -> Card:
    if state.card == "new":
        return Card(card_id=_CARD_ID, due=_datetime(Instant(1)))
    return Card(
        card_id=_CARD_ID,
        state=_FSRS_STATES[state.card],
        step=state.step if state.card in ("learning", "relearning") else None,
        stability=state.stability,
        difficulty=state.difficulty,
        due=_datetime(state.due),
        last_review=_datetime(state.last_asked),
    )


def review(state: UnitState, rating: EngineRating, at: Instant) -> UnitState:
    r"""Apply one retrieval to the memory half of a unit.

    Only the FSRS fields move here — `card`, `step`, `stability`, `difficulty` and `due`. The
    bookkeeping (`last_asked`, `reviews`, `lapses`, …) belongs to `record`.

    ⚠️ **A RETRIEVAL OLDER THAN THE LAST ONE IS FOLDED AT THE LAST ONE'S INSTANT.** FSRS cannot run
    backwards in time; an offline queue replayed out of order would otherwise compute a negative
    elapsed time. Sort by `at` before recording and this never triggers.
    """
    when = max(at, state.last_asked)
    card, _ = scheduler().review_card(_card(state), _RATINGS[rating], _datetime(when))
    return replace(
        state,
        card=_STATES[card.state],
        step=card.step if card.step is not None else 0,
        stability=float(card.stability) if card.stability is not None else 0.0,
        difficulty=float(card.difficulty) if card.difficulty is not None else 0.0,
        due=_instant(card.due),
    )


def retrievability(state: UnitState, now: Instant) -> float:
    r"""FSRS's estimate that she would recall this unit at `now`, from 0 to 1.

    `0.0` for a unit with no memory model yet — never retrieved.
    """
    if state.card == "new" or state.last_asked == NEVER:
        return 0.0
    return float(scheduler().get_card_retrievability(_card(state), _datetime(max(now, state.last_asked))))
