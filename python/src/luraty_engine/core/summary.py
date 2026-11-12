# Reducing a learner to a number small enough to keep forever.

from __future__ import annotations

from typing import Literal

from luraty_engine.core.plan import STUCK_AFTER_LAPSES
from luraty_engine.model import (
    NEVER,
    SECONDS_PER_DAY,
    Profile,
    Summary,
    SummaryScope,
    UnitKey,
    UnitState,
    is_known,
    parse_unit_key,
)
from luraty_engine.utils import assert_never


def claim_bucket(state: UnitState) -> Literal["standing", "confirmed", "refuted"] | None:
    """Which of the three claim buckets this unit is in, if any. See `Summary.claims_refuted`."""
    if state.prior.kind != "claimed":
        return None
    if state.last_asked == NEVER:
        return "standing"
    return "refuted" if state.last_proven == NEVER else "confirmed"


def in_scope(key: UnitKey, scope: SummaryScope) -> bool:
    r"""Does this unit fall inside the scope being summarised?

    ⚠️ **EVERY SCOPE PARSES THE KEY, INCLUDING `'all'`**, and the reason is a law rather than tidiness.
    `summarize` promises that the four per-skill scopes partition the profile exactly — nothing
    double-counted, nothing dropped. `unit_key(d, v, '')` mints `"recognise:fr:"`, which `parse_unit_key`
    rejects for having no word; `record` writes whatever key it is handed, so such a unit can reach a
    profile. If `'all'` counted it and no skill scope could, the partition would silently be off by
    one for every malformed key present.

    The alternative — having `'all'` return true unconditionally and calling the law approximate — was
    rejected: an unaddressable unit is not a unit anybody can act on, so counting it in a headline
    number is the worse error.
    """
    parts = parse_unit_key(key)
    if parts is None:
        return False
    match scope.kind:
        case "all":
            return True
        case "skill":
            # Matched on the PARSED parts rather than a string prefix. A prefix test would need the
            # caller's variety to be free of colons — true today by construction, and exactly the kind of
            # invariant that stops being true quietly.
            #
            # ⚠️ `modality`, not `direction` (ADR-0022). Since `parse_unit_key` accepts every modality, a
            # `skill:` or `pronounce:` unit reaches `'all'`; keying this on a two-member `Direction` would
            # leave those units in the whole and in no part, breaking the partition law above.
            return parts.modality == scope.modality and parts.variety == scope.variety
        case _:
            assert_never(scope, "SummaryScope")


def summarize(profile: Profile, scope: SummaryScope) -> Summary:
    r"""Summarise a learner.

    O(units), and deliberately NOT cached on the profile. A denormalised counter is a cache, a cache
    rots, and the one that rots here would be the number shown on the home screen. It is also what
    keeps `record` the only function that writes to a profile.

    Total: every scope has an honest answer, including "no units match", which reports zeros and a
    `days_since_proven` of the full span since the epoch.
    """
    by_card = {"new": 0, "learning": 0, "review": 0, "relearning": 0}
    units = 0
    known = 0
    claims_standing = 0
    claims_confirmed = 0
    claims_refuted = 0
    stuck = 0
    last_proven = NEVER

    for key, state in profile.units.items():
        if not in_scope(key, scope):
            continue

        units += 1
        by_card[state.card] += 1

        if is_known(state):
            known += 1
        if state.lapses >= STUCK_AFTER_LAPSES:
            stuck += 1
        if state.last_proven > last_proven:
            last_proven = state.last_proven

        bucket = claim_bucket(state)
        if bucket == "standing":
            claims_standing += 1
        if bucket == "confirmed":
            claims_confirmed += 1
        if bucket == "refuted":
            claims_refuted += 1

    return Summary(
        now=profile.now,
        language=profile.language,
        scope=scope,
        units=units,
        new=by_card["new"],
        learning=by_card["learning"],
        review=by_card["review"],
        relearning=by_card["relearning"],
        known=known,
        claims_standing=claims_standing,
        claims_confirmed=claims_confirmed,
        claims_refuted=claims_refuted,
        stuck=stuck,
        days_since_proven=max(0, (profile.now - last_proven) // SECONDS_PER_DAY),
    )
