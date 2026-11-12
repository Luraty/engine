# Doing one thing to many words.
#
# ⚠️ **THIS MODULE EXISTS BECAUSE THE SAME LOOP WAS HAND-WRITTEN FIVE TIMES.** `vocabulary_of` lived
# in `testing/` and was never exported, so the identical "split the frequency list, key each word,
# drop empties, drop duplicates" loop was then rewritten in `testing/demo.ts`, twice in a script,
# and in two pack build scripts. Writing a helper five times and publishing it zero times is the API
# missing it, not the callers being lazy.
#
# Everything here is a pure transform over strings — no I/O, no new concepts, nothing that touches
# the state model. Each one is the shortest honest way to express something every host does on day
# one.

from __future__ import annotations

from collections.abc import Sequence

from luraty_engine._js import split_whitespace
from luraty_engine.model import (
    Claim,
    Instant,
    Exposure,
    LanguagePack,
    Lemma,
    Modality,
    UnitKey,
    Variety,
    unit_key,
)


def keys_for(modality: Modality, v: Variety, words: Sequence[str]) -> tuple[UnitKey, ...]:
    r"""Address a list of words, in one direction and variety.

    Chiefly for `PlanOptions.priority`: `keys_for('recognise', de, vocabulary_of(pack, frequency))` is
    the whole of the frequency tiebreak a host needs.

    ⚠️ **Empty words are skipped**, and that is a real guard rather than tidiness. `unit_key(d, v, '')`
    returns `"recognise:de:"`, which `parse_unit_key` rejects for having no word — and `record` writes
    whatever key it is handed, so one empty string in a caller's list puts a permanently unaddressable
    unit in the profile. A review found exactly that reaching `summarize`, where it broke the law that
    the per-skill scopes partition the whole.

    Order is preserved and duplicates are NOT removed: `priority` takes the first index it sees, so a
    caller who wants dedup should use `vocabulary_of`, which does it.
    """
    return tuple(unit_key(modality, v, word) for word in words if len(word) != 0)


def claims_for(
    modality: Modality, v: Variety, words: Sequence[str], at: Instant
) -> tuple[Claim, ...]:
    r"""Turn the output of a placement into evidence.

    **The single most common day-one operation**, and until this existed it was a four-field object
    literal inside a `.map` at every call site.

    A claim says the host believes she knows this and nobody has checked. It buys no head start on its
    own — see `Claim` — so this cannot inflate anything; what it buys is that day one is not an empty
    screen, that those words come back labelled `'verify'` rather than `'new'`, and that `coverage()`
    can say "it depends whether you believe her" instead of confidently reporting 0%.
    """
    return tuple(Claim(unit=unit, at=at) for unit in keys_for(modality, v, words))


def exposures_for(
    modality: Modality, v: Variety, words: Sequence[str], at: Instant
) -> tuple[Exposure, ...]:
    r"""Everything she met while reading, as evidence that proves nothing.

    Pass the DISTINCT words of a passage — `vocabulary_of` is not right here, because a passage is text
    rather than a frequency list; split it with `pack.split` and key each surface.

    ⚠️ Exposure is the weakest signal the engine has and it is deliberately weaker than it looks: it
    moves `seen` and `last_seen` and nothing else. A heritage speaker recognises a word's shape while
    holding only its domestic sense and will not ask, so if not-asking counted as knowing, the register
    gap this engine exists to find would be invisible by construction.

    If she tapped the gloss on a word, that is `Help`, not this — and it is the more informative of the
    two, because it is her telling you she does not have it.
    """
    return tuple(Exposure(unit=unit, at=at) for unit in keys_for(modality, v, words))


def vocabulary_of(pack: LanguagePack, frequency: str) -> tuple[Lemma, ...]:
    r"""Every distinct canonical word a pack's frequency list contains, **commonest first**.

    The order is the whole value: it is what a host passes as `PlanOptions.priority`, and without it a
    session of equally-overdue words comes back alphabetically.

    Two filters, and both matter. **Unkeyable surfaces are dropped** — `key()` can return the empty
    string (a run of Arabic tatweel is a real example), and `unit_key(d, v, '')` mints an address
    `parse_unit_key` rejects, so such a unit could never be known or even addressed. **Duplicates are
    dropped, first occurrence winning** — many surfaces collapse to one lemma, and the earliest
    position is the honest rank for it.
    """
    out: list[Lemma] = []
    seen: set[Lemma] = set()
    for word in split_whitespace(frequency):
        if len(word) == 0:
            continue
        lemma = pack.key(word)
        if len(lemma) == 0 or lemma in seen:
            continue
        seen.add(lemma)
        out.append(lemma)
    return tuple(out)


def words_in(pack: LanguagePack, text: str) -> tuple[Lemma, ...]:
    r"""The distinct canonical words of a passage, in first-appearance order.

    The reading-side counterpart of `vocabulary_of`: same dedup and same unkeyable filter, but over
    real text rather than a frequency list. Feed the result to `exposures_for`.
    """
    out: list[Lemma] = []
    seen: set[Lemma] = set()
    for surface in pack.split(text):
        lemma = pack.key(surface)
        if len(lemma) == 0 or lemma in seen:
            continue
        seen.add(lemma)
        out.append(lemma)
    return tuple(out)
