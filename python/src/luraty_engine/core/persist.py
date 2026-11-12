r"""Turning a profile into bytes and back.

Two rules govern this file, and both exist because the other side of it is a learner's phone:

1. **Serialization is canonical.** Logically identical state produces byte-identical output.
2. **Decoding never throws.** It returns a `Decoded` either way.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final, cast

from luraty_engine import _js
from luraty_engine._js import UNDEFINED, canon, number_to_string, utf16_key
from luraty_engine.model import (
    PROFILE_SCHEMA_VERSION,
    WIRE_ROW_LENGTH,
    CardState,
    Instant,
    Decoded,
    DecodedError,
    DecodedOk,
    DecodeError,
    DecodeErrorKind,
    Prior,
    PriorClaimed,
    PriorNone,
    Profile,
    UnitKey,
    UnitState,
    is_unit_key,
)
from luraty_engine.model.wire import WireRowV1
from luraty_engine.utils import assert_never

# ── Encoding ────────────────────────────────────────────────────────────────────────────────────


def _prior_to_wire(prior: Prior) -> int | None:
    """A prior, flattened for storage. See WireRowV4."""
    match prior.kind:
        case "none":
            return None
        case "claimed":
            return prior.on
        case _:
            assert_never(prior, "Prior")


# The card states, in wire order. A row stores the index.
#
# ⚠️ APPEND ONLY. Reordering this list re-labels every stored unit.
CARD_STATES: Final[tuple[CardState, ...]] = ("new", "learning", "review", "relearning")


def _to_row(key: UnitKey, state: UnitState) -> WireRowV1:
    r"""One unit as a positional row. The order is declared once, on `WireRowV1`."""
    return (
        key,
        state.seen,
        state.last_seen,
        state.last_helped,
        _prior_to_wire(state.prior),
        CARD_STATES.index(state.card),
        state.step,
        state.stability,
        state.difficulty,
        state.due,
        state.last_asked,
        state.last_proven,
        state.reviews,
        state.lapses,
    )


def serialize(profile: Profile) -> str:
    r"""Serialize a profile to a canonical string.

    **Canonical means the same state always produces the same bytes**, which is what makes a
    serialized profile safe to hash, diff, and pin in a golden test. Without the sort, a profile
    built by replaying evidence and the same profile loaded from storage would differ purely by the
    order keys happened to be inserted — identical state, different bytes, and every replay test
    failing at random for reasons nobody can reproduce.

    The comparison is on UTF-16 code units, not a locale-aware collation. That is deliberate twice
    over: `localeCompare` is ICU-backed and therefore unavailable on Hermes, and a *locale-dependent*
    sort would make the canonical form depend on the device's language settings, which is exactly the
    bug this is meant to prevent.
    """
    keys = sorted(profile.units, key=utf16_key)
    wire = {
        "v": PROFILE_SCHEMA_VERSION,
        "language": profile.language,
        "now": profile.now,
        "units": [_to_row(key, profile.units[key]) for key in keys],
    }
    return cast(str, _js.json_stringify(wire))


# ── Decoding ────────────────────────────────────────────────────────────────────────────────────


def _fail(kind: DecodeErrorKind, message: str) -> DecodedError:
    return DecodedError(error=DecodeError(kind=kind, message=message))


def _is_record(v: object) -> bool:
    return isinstance(v, dict)


def _is_whole_number(v: object) -> bool:
    return _js.is_integer(v) and cast(float, v) >= 0


def _is_finite_non_negative(v: object) -> bool:
    return _js.is_number(v) and math.isfinite(cast(float, v)) and cast(float, v) >= 0


def _parse_row(row: list[Any]) -> UnitState | None:
    r"""Parse one stored row into a unit, or `None` if any position is wrong.

    ⚠️ **EVERY POSITION IS CHECKED.** A positional row one element short reads every field after the
    gap as its neighbour, so the length is exact and each slot is validated. Read this beside
    `_to_row`; they are one format written twice.
    """
    if len(row) != WIRE_ROW_LENGTH:
        return None

    (
        _,
        seen,
        last_seen,
        last_helped,
        prior,
        card,
        step,
        stability,
        difficulty,
        due,
        last_asked,
        last_proven,
        reviews,
        lapses,
    ) = row

    whole = (seen, last_seen, last_helped, card, step, due, last_asked, last_proven, reviews, lapses)
    if not all(_is_whole_number(value) for value in whole):
        return None
    if not _is_finite_non_negative(stability) or not _is_finite_non_negative(difficulty):
        return None
    if card >= len(CARD_STATES):
        return None
    # `null` for no claim, a whole instant otherwise. A missing slot is not "never claimed".
    if prior is not None and not _is_whole_number(prior):
        return None

    return UnitState(
        seen=seen,
        last_seen=last_seen,
        last_helped=last_helped,
        prior=PriorNone() if prior is None else PriorClaimed(on=prior),
        card=CARD_STATES[card],
        step=step,
        stability=float(stability),
        difficulty=float(difficulty),
        due=due,
        last_asked=last_asked,
        last_proven=last_proven,
        reviews=reviews,
        lapses=lapses,
    )


# Migrations, keyed by the version they upgrade FROM.
#
# Each is `unknown -> unknown`: a migration operates on data written by code that no longer exists,
# so it cannot be typed against today's shapes without lying. Typing them as the OLD wire type is
# worse — it forces you to keep every historical type alive forever.
#
# ⚠️ When the first real migration lands, it brings its own test with it. A migration that has
# never run on realistic old data is not a migration, it is a hope.
#
# Empty: v1 is the first released format. Earlier development formats were never shipped.
_MIGRATIONS: Final[Mapping[int, Callable[[Any], Any]]] = {}


def _migrate(start: int, data: Any) -> Decoded[Any]:
    r"""Walk the chain from a stored version up to the current one.

    Stepwise rather than one big jump: a future v1 blob upgrades to v2 then v3, reusing the same steps
    a v2 blob takes.
    """
    current = data
    v = start
    while v < PROFILE_SCHEMA_VERSION:
        step = _MIGRATIONS.get(v)
        if step is None:
            return _fail(
                "no-migration",
                f"stored profile is version {number_to_string(v)} and no migration exists to version {number_to_string(v + 1)}",
            )
        current = step(current)
        v += 1
    return DecodedOk(value=current)


def _parse_json(text: object) -> tuple[bool, Any]:
    if isinstance(text, str):
        try:
            return True, _js.json_parse(canon(text))
        except ValueError:
            return False, None
    # JSON.parse stringifies its argument; a number or boolean is itself valid JSON text.
    if isinstance(text, (bool, int, float)):
        return True, text
    return False, None


def deserialize(text: str) -> Decoded[Profile]:
    r"""Read a profile back from a string. Never throws.

    Every failure path returns a named error rather than an exception, because this runs at app
    launch against data written by an older build: a throw here is a learner whose app will not open
    and who cannot downgrade to fix it.
    """
    parsed, raw = _parse_json(text)
    if not parsed:
        return _fail("not-json", "stored profile is not valid JSON")

    if not _is_record(raw):
        return _fail("malformed", "stored profile is not an object")

    version = raw.get("v", UNDEFINED)
    if not _is_whole_number(version):
        return _fail("malformed", "stored profile has no version")

    if version > PROFILE_SCHEMA_VERSION:
        # Written by a newer engine. Migrating forward is impossible and guessing is worse — this is
        # the "app was downgraded, or storage was restored from a newer device" case, and the host
        # should be told rather than handed a silently truncated profile.
        return _fail(
            "from-the-future",
            f"stored profile is version {number_to_string(version)}, but this engine understands at most {number_to_string(PROFILE_SCHEMA_VERSION)}",
        )

    migrated = _migrate(version, raw)
    if not migrated.ok:
        return migrated

    wire = migrated.value
    if not _is_record(wire):
        return _fail("malformed", "migrated profile is not an object")

    language = wire.get("language", UNDEFINED)
    if not isinstance(language, str) or len(language) == 0:
        return _fail("malformed", "profile has no language")
    profile_now = wire.get("now", UNDEFINED)
    if not _is_whole_number(profile_now):
        return _fail("malformed", "profile has no valid now")
    rows = wire.get("units", UNDEFINED)
    if not isinstance(rows, list):
        return _fail("malformed", "profile units are not a list")

    units: dict[UnitKey, UnitState] = {}
    for row in rows:
        if not isinstance(row, list):
            return _fail("malformed", "a unit entry is not a row")
        # ⚠️ THE KEY IS READ AND CHECKED BEFORE THE ROW LENGTH IS, deliberately. A row of the wrong
        # length is exactly what a mis-migrated or hand-edited profile produces, and the whole value of
        # the error is that it NAMES the unit — so the name has to be recovered before the shape is
        # rejected. Position 0 is the key in every version this format has had.
        key = row[0] if row else UNDEFINED
        if not isinstance(key, str) or len(key) == 0:
            return _fail("malformed", "a unit entry has no key")
        key = canon(key)
        # ⚠️ THE KEY IS PARSED, not merely checked for being a non-empty string.
        #
        # This is the one place the engine cannot assume its own invariants held (see
        # `parse_unit_key`), which is exactly why the check belongs here rather than in the host.
        if not is_unit_key(key):
            # Safe to include: a key is a direction, a variety and a word the HOST chose. It is not
            # learner-authored content.
            return _fail("malformed", f'unit key "{key}" is not a valid unit key')
        # Indexed rather than `in`: `'constructor' in {}` is TRUE through the prototype chain, and this
        # package has already been bitten once by exactly that (see `create_pack`'s lemma Map).
        if key in units:
            return _fail("malformed", f'unit "{key}" appears more than once')
        state = _parse_row(row)
        if state is None:
            return _fail("malformed", f'unit "{key}" has an unreadable state')
        units[key] = state

    return DecodedOk(
        value=Profile(
            language=canon(language),
            now=cast(Instant, profile_now),
            units=MappingProxyType(units),
        )
    )
