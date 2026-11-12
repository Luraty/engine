"""A small property-testing harness; the port has no third-party generators."""

import os
import random
from collections.abc import Callable
from typing import Any

type Gen = Callable[[random.Random], Any]

RUNS = 100


def for_all(check: Callable[..., None], *gens: Gen, runs: int = RUNS) -> None:
    seed = int(os.environ.get("PROP_SEED", random.SystemRandom().randrange(2**32)))
    r = random.Random(seed)
    for i in range(runs):
        args = [g(r) for g in gens]
        try:
            check(*args)
        except AssertionError as e:
            raise AssertionError(f"run {i} failed (PROP_SEED={seed}) on {args!r}: {e}") from e


def constant_from(*values: Any) -> Gen:
    return lambda r: r.choice(values)


def integer(lo: int, hi: int) -> Gen:
    return lambda r: r.randint(lo, hi)


def boolean() -> Gen:
    return lambda r: r.random() < 0.5


def tuple_of(*gens: Gen) -> Gen:
    return lambda r: tuple(g(r) for g in gens)


def one_of(*gens: Gen) -> Gen:
    return lambda r: r.choice(gens)(r)


def weighted(*pairs: tuple[int, Gen]) -> Gen:
    gens = [g for _, g in pairs]
    weights = [w for w, _ in pairs]
    return lambda r: r.choices(gens, weights)[0](r)


def filtered(gen: Gen, pred: Callable[[Any], bool]) -> Gen:
    def run(r: random.Random) -> Any:
        while True:
            value = gen(r)
            if pred(value):
                return value

    return run


def mapped(gen: Gen, fn: Callable[[Any], Any]) -> Gen:
    return lambda r: fn(gen(r))


def array(gen: Gen, min_length: int = 0, max_length: int = 10) -> Gen:
    return lambda r: [gen(r) for _ in range(r.randint(min_length, max_length))]


def string_of(units: list[str], min_length: int = 0, max_length: int = 10) -> Gen:
    return lambda r: "".join(r.choice(units) for _ in range(r.randint(min_length, max_length)))


def any_code_point_string(max_length: int = 10) -> Gen:
    def run(r: random.Random) -> str:
        out = []
        for _ in range(r.randint(0, max_length)):
            band = r.random()
            if band < 0.4:
                out.append(chr(r.randint(0, 0x7F)))
            elif band < 0.7:
                out.append(chr(r.randint(0, 0xFFFF)))
            else:
                out.append(chr(r.randint(0, 0x10FFFF)))
        return "".join(out)

    return run


def double() -> Gen:
    specials = [float("nan"), float("inf"), float("-inf"), 0.0, -0.0, 1e308, -1e308, 5e-324]

    def run(r: random.Random) -> float:
        k = r.random()
        if k < 0.2:
            return r.choice(specials)
        if k < 0.6:
            return r.uniform(-20, 20)
        return r.uniform(-1e308, 1e308)

    return run


def json_text(max_depth: int = 3) -> Gen:
    """Well-formed JSON of no particular shape."""

    def value(r: random.Random, depth: int) -> Any:
        scalars = [None, True, False, 0, -1, 5, 2.5, 1e21, "", "a", "v", "units", "😀", "recognise:ar:x"]
        if depth <= 0 or r.random() < 0.4:
            return r.choice(scalars)
        if r.random() < 0.5:
            return [value(r, depth - 1) for _ in range(r.randint(0, 3))]
        keys = ["v", "language", "day", "units", "a", "box", "seen"]
        return {r.choice(keys): value(r, depth - 1) for _ in range(r.randint(0, 4))}

    import json

    return lambda r: json.dumps(value(r, max_depth))
