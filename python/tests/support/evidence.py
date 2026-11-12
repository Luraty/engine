"""Generators for evidence."""

import luraty_engine as L
from support.prop import constant_from, integer, one_of, tuple_of, weighted

RATINGS = ("again", "hard", "good", "easy")


def arb_unit(variety, words, directions=("recognise", "produce")):
    return lambda r: L.unit_key(r.choice(directions), variety, r.choice(words))


def _record(kind, unit, at, **extra):
    def make(r):
        match kind:
            case "retrieval":
                return L.Retrieval(unit=unit(r), rating=extra["rating"](r), at=at(r))
            case "exposure":
                return L.Exposure(unit=unit(r), at=at(r))
            case "help":
                return L.Help(unit=unit(r), at=at(r))
            case "claim":
                return L.Claim(unit=unit(r), at=at(r))

    return make


def arb_evidence(variety, words, directions=("recognise", "produce"), max_at=400 * 86_400):
    unit = arb_unit(variety, words, directions)
    at = integer(1, max_at)
    return weighted(
        (6, _record("retrieval", unit, at, rating=constant_from(*RATINGS))),
        (2, _record("exposure", unit, at)),
        (2, _record("help", unit, at)),
        (2, _record("claim", unit, at)),
    )


def arb_passive(variety, words, directions=("recognise", "produce"), max_at=400 * 86_400):
    unit = arb_unit(variety, words, directions)
    at = integer(1, max_at)
    return one_of(_record("exposure", unit, at), _record("help", unit, at), _record("claim", unit, at))


def kinds_in(evidence):
    return {e.kind for e in evidence}


__all__ = ["arb_evidence", "arb_passive", "arb_unit", "kinds_in", "tuple_of"]
