# Creating and moving a profile through time.

from __future__ import annotations

from types import MappingProxyType

from luraty_engine._js import OBJECT_PROTOTYPE_PROPERTIES
from luraty_engine.model import UNMET, Instant, Profile, UnitKey, UnitState


def advance_to(profile: Profile, now: Instant) -> Profile:
    r"""Move the profile to an instant.

    The host calls this; the engine never reads a clock, because there is no clock in here to read.
    Time is data, which is what makes a session replayable from a seed.

    Monotonic: going backwards returns the profile unchanged rather than throwing. A host whose
    device clock jumps backwards (timezone change, manual correction, a phone that was off) should
    not be able to corrupt a learner's history, and it certainly should not crash their app.
    """
    if now <= profile.now:
        return profile
    return Profile(language=profile.language, now=now, units=profile.units)


def create_profile(language: str, start: Instant) -> Profile:
    """A learner who has met nothing yet."""
    return Profile(language=language, now=start, units=MappingProxyType({}))


def has_met(profile: Profile, key: UnitKey) -> bool:
    """Whether the learner has ever met this unit. Distinct from "knows it"."""
    return key in profile.units or key in OBJECT_PROTOTYPE_PROPERTIES


def unit_state(profile: Profile, key: UnitKey) -> UnitState:
    r"""The state of a unit, total.

    An unmet unit reads as `UNMET`: every counter zero, every date zero, no claim. The engine's
    honest default is that you do not know a word until something says otherwise — and that never
    having met a word is not a claim about it.

    ⚠️ `last_seen` defaults to `0`, not `profile.now`. v2 returned today, which asserted a sighting
    that never happened; `plan()` never read it and `coverage()` never read it, so nothing depended on
    the lie, but `summarize()` would have. Corrected while the wire was open.
    """
    return profile.units.get(key, UNMET)
