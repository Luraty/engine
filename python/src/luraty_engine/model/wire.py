"""The persisted shapes. Opposite change policy from everything else: a copy of these is in storage somewhere and can never be recompiled."""

from __future__ import annotations

from typing import Literal, TypedDict

# One unit, as the positional row v1 stores:
#
#   [key, seen, last_seen, last_helped, prior, card, step, stability, difficulty, due, last_asked,
#    last_proven, reviews, lapses]
#
# Dates are instants (`0` = never); `prior` is `null` or the instant of the claim; `card` indexes
# `CARD_STATES` in `core/persist.py`.
#
# ⚠️ APPEND, NEVER INSERT. A future version adds fields at the end so every existing position keeps
# its index, and its migration is a push rather than a reshuffle.
WireRowV1 = tuple[str, int, int, int, int | None, int, int, float, float, int, int, int, int, int]


class WireProfileV1(TypedDict):
    """A whole profile, as stored by schema v1 — the current one."""

    v: Literal[1]
    language: str
    now: int
    units: list[WireRowV1]


# The current wire shape. Point this at the newest version; leave the older ones untouched.
WireProfile = WireProfileV1
