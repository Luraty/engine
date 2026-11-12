"""JavaScript runtime semantics the engine's behaviour is defined in terms of."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from json.decoder import scanstring
from json.encoder import encode_basestring
from typing import Any, Final


class _Undefined:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNDEFINED"

    def __bool__(self) -> bool:
        return False


UNDEFINED: Final = _Undefined()

MAX_EXACT_INTEGER: Final = 2**53
MAX_ARRAY_INDEX: Final = 2**32 - 2

# ECMAScript WhiteSpace + LineTerminator: what `\s` matches and `trim` removes.
WHITESPACE: Final = (
    "\t\n\x0b\x0c\r \xa0            "
    "    　﻿"
)
_WHITESPACE_RUN: Final = re.compile("[" + re.escape(WHITESPACE) + "]+")

_SURROGATE_PAIR: Final = re.compile("[\ud800-\udbff][\udc00-\udfff]")
_LONE_SURROGATE: Final = re.compile("[\ud800-\udfff]")

OBJECT_PROTOTYPE_PROPERTIES: Final = frozenset(
    {
        "constructor",
        "__defineGetter__",
        "__defineSetter__",
        "hasOwnProperty",
        "__lookupGetter__",
        "__lookupSetter__",
        "isPrototypeOf",
        "propertyIsEnumerable",
        "toString",
        "valueOf",
        "__proto__",
        "toLocaleString",
    }
)


# ── Strings ─────────────────────────────────────────────────────────────────────────────────────


def canon(s: str) -> str:
    """Join adjacent surrogates: in JS a high and a low code unit next to each other ARE one character."""
    if _SURROGATE_PAIR.search(s) is None:
        return s
    return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def utf16_key(s: str) -> bytes:
    """Sort key ordering strings by UTF-16 code unit, which is what JS `<` compares."""
    return s.encode("utf-16-be", "surrogatepass")


def utf16_len(s: str) -> int:
    if s.isascii():
        return len(s)
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def _relative_index(value: int | float, length: int) -> int:
    # ToIntegerOrInfinity, then the relative-index clamp of String.prototype.slice.
    if value != value:
        return 0
    if value in (math.inf, -math.inf):
        return length if value > 0 else 0
    n = int(value)
    return max(length + n, 0) if n < 0 else min(n, length)


def utf16_slice(s: str, start: int | float, end: int | float | None = None) -> str:
    """`String.prototype.slice`, whose indices are UTF-16 code units."""
    length = utf16_len(s)
    a = _relative_index(start, length)
    b = length if end is None else _relative_index(end, length)
    if a >= b:
        return ""
    if length == len(s):
        return s[a:b]
    return s.encode("utf-16-le", "surrogatepass")[2 * a : 2 * b].decode("utf-16-le", "surrogatepass")


def utf16_units(s: str) -> list[str]:
    """One string per UTF-16 code unit."""
    raw = s.encode("utf-16-le", "surrogatepass")
    return [raw[i : i + 2].decode("utf-16-le", "surrogatepass") for i in range(0, len(raw), 2)]


def starts_with(s: str, prefix: str) -> bool:
    """`String.prototype.startsWith`, which can match half of a surrogate pair."""
    if s.startswith(prefix):
        return True
    if not prefix or not "\ud800" <= prefix[-1] <= "\udbff":
        return False
    return utf16_units(s)[: utf16_len(prefix)] == utf16_units(prefix)


def trim(s: str) -> str:
    return s.strip(WHITESPACE)


def split_whitespace(s: str) -> list[str]:
    r"""`s.split(/\s+/)`. Keeps the empty pieces a leading or trailing run produces."""
    return _WHITESPACE_RUN.split(s)


# Python 3.13 ships Unicode 15.1; the twin ran on Node 24 with Unicode 17. These are the code points
# whose case data differs, measured against `toLowerCase` for every code point.
_LOWER_OVERRIDES: Final = {
    0x1C89: 0x1C8A,
    0xA7CB: 0x0264,
    0xA7CC: 0xA7CD,
    0xA7CE: 0xA7CF,
    0xA7D2: 0xA7D3,
    0xA7D4: 0xA7D5,
    0xA7DA: 0xA7DB,
    0xA7DC: 0x019B,
    **{0x10D50 + i: 0x10D70 + i for i in range(22)},
    **{0x16EA0 + i: 0x16EBB + i for i in range(25)},
}

_CASE_PROXIES: Final[dict[int, str]] = {}


def _set_case_proxies(ranges: Iterable[tuple[int, int]], proxy: str) -> None:
    for lo, hi in ranges:
        for code in range(lo, hi + 1):
            _CASE_PROXIES[code] = proxy


_set_case_proxies(
    [
        (0x1C89, 0x1C8A),
        (0xA7CB, 0xA7CF),
        (0xA7D2, 0xA7D2),
        (0xA7D4, 0xA7D4),
        (0xA7DA, 0xA7DC),
        (0x10D50, 0x10D65),
        (0x10D70, 0x10D85),
        (0x16EA0, 0x16EB8),
        (0x16EBB, 0x16ED3),
    ],
    "a",
)
_set_case_proxies(
    [
        (0x0897, 0x0897),
        (0x1ACF, 0x1ADD),
        (0x1AE0, 0x1AEB),
        (0xA7F1, 0xA7F1),
        (0x10D4E, 0x10D4E),
        (0x10D69, 0x10D6D),
        (0x10D6F, 0x10D6F),
        (0x10EC5, 0x10EC5),
        (0x10EFA, 0x10EFC),
        (0x113BB, 0x113C0),
        (0x113CE, 0x113CE),
        (0x113D0, 0x113D0),
        (0x113D2, 0x113D2),
        (0x113E1, 0x113E2),
        (0x11B60, 0x11B60),
        (0x11B62, 0x11B64),
        (0x11B66, 0x11B66),
        (0x11DD9, 0x11DD9),
        (0x11F5A, 0x11F5A),
        (0x1611E, 0x16129),
        (0x1612D, 0x1612F),
        (0x16D40, 0x16D42),
        (0x16D6B, 0x16D6C),
        (0x16FF2, 0x16FF3),
        (0x1E5EE, 0x1E5EF),
        (0x1E6E3, 0x1E6E3),
        (0x1E6E6, 0x1E6E6),
        (0x1E6EE, 0x1E6EF),
        (0x1E6F5, 0x1E6F5),
        (0x1E6FF, 0x1E6FF),
    ],
    "'",
)
_set_case_proxies([(0x0295, 0x0295), (0x1171E, 0x1171E)], "0")


def _sigma_aware_lower(s: str) -> str:
    lowered = s.lower()
    contextual = s.translate(_CASE_PROXIES).lower()
    return "".join(
        c if o in "σς" else o for o, c in zip(lowered, contextual, strict=True)
    ).translate(_LOWER_OVERRIDES)


def to_lower_case(s: str) -> str:
    """`String.prototype.toLowerCase` at Node 24's Unicode version."""
    if s.isascii():
        return s.lower()
    if "Σ" in s and not _CASE_PROXIES.keys().isdisjoint(map(ord, s)):
        return _sigma_aware_lower(s)
    return s.lower().translate(_LOWER_OVERRIDES)


# ── Numbers ─────────────────────────────────────────────────────────────────────────────────────


def is_number(v: object) -> bool:
    """`typeof v === 'number'`. A `bool` is an `int` in Python and is not one here."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_integer(v: object) -> bool:
    """`Number.isInteger`."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v) and v.is_integer()


def number(v: int | float) -> int | float:
    """The canonical Python value of a JS number: an `int` wherever every integer is exact."""
    if isinstance(v, int):
        if -MAX_EXACT_INTEGER <= v <= MAX_EXACT_INTEGER:
            return v
        try:
            return float(v)
        except OverflowError:
            return math.inf if v > 0 else -math.inf
    if v.is_integer() and -MAX_EXACT_INTEGER <= v <= MAX_EXACT_INTEGER:
        return int(v)
    return v


def add(a: int | float, b: int | float) -> int | float:
    """`a + b` with double-precision rounding once the sum leaves the exact-integer range."""
    total = a + b
    if isinstance(total, int) and not -MAX_EXACT_INTEGER <= total <= MAX_EXACT_INTEGER:
        return number(float(a) + float(b))
    return number(total)


def trunc(v: int | float) -> int | float:
    """`Math.trunc` for finite numbers."""
    if isinstance(v, int) or abs(v) >= MAX_EXACT_INTEGER:
        return number(v)
    return int(v)


def floor(v: int | float) -> int | float:
    """`Math.floor` for finite numbers."""
    if isinstance(v, int) or abs(v) >= MAX_EXACT_INTEGER:
        return number(v)
    return math.floor(v)


def number_to_string(x: int | float) -> str:
    """`Number::toString` with radix 10."""
    if isinstance(x, int) and -MAX_EXACT_INTEGER <= x <= MAX_EXACT_INTEGER:
        return str(x)
    x = float(x)
    if x != x:
        return "NaN"
    if x in (math.inf, -math.inf):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    mantissa, _, exponent = repr(abs(x)).partition("e")
    whole, _, fraction = mantissa.partition(".")
    digits = whole + fraction
    point = len(whole) + int(exponent or 0)
    stripped = digits.lstrip("0")
    point -= len(digits) - len(stripped)
    digits = stripped.rstrip("0")
    k = len(digits)
    if k <= point <= 21:
        return sign + digits + "0" * (point - k)
    if 0 < point <= 21:
        return sign + digits[:point] + "." + digits[point:]
    if -6 < point <= 0:
        return sign + "0." + "0" * -point + digits
    e = point - 1
    exp = ("+" if e >= 0 else "-") + str(abs(e))
    if k == 1:
        return sign + digits + "e" + exp
    return sign + digits[0] + "." + digits[1:] + "e" + exp


_NUMERIC_LITERAL: Final = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_RADIX_LITERAL: Final = re.compile(r"0(?:[xX][0-9a-fA-F]+|[oO][0-7]+|[bB][01]+)")


def to_number(v: object) -> int | float:
    """`ToNumber` for the values a JSON document can hold."""
    if v is UNDEFINED:
        return math.nan
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return number(v)
    if isinstance(v, str):
        text = trim(v)
        if text == "":
            return 0
        if text in ("Infinity", "+Infinity"):
            return math.inf
        if text == "-Infinity":
            return -math.inf
        if _RADIX_LITERAL.fullmatch(text) is not None:
            return number(int(text, 0))
        if _NUMERIC_LITERAL.fullmatch(text) is not None:
            return number(float(text))
        return math.nan
    return to_number(to_string(v))


# ── Coercion and object access ──────────────────────────────────────────────────────────────────


def is_object(v: object) -> bool:
    """`typeof v === 'object' && v !== null`. Arrays are objects."""
    if v is None or v is UNDEFINED or isinstance(v, (str, bool, int, float)):
        return False
    return not callable(v)


def is_array(v: object) -> bool:
    return isinstance(v, (list, tuple))


def is_truthy(v: object) -> bool:
    if v is None or v is UNDEFINED or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v == v and v != 0
    if isinstance(v, str):
        return v != ""
    return True


def to_string(v: object) -> str:
    """`ToString` for the values a JSON document can hold."""
    if v is UNDEFINED:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return number_to_string(v)
    if isinstance(v, (list, tuple)):
        return ",".join("" if item is None or item is UNDEFINED else to_string(item) for item in v)
    return "[object Object]"


def _to_snake(name: str) -> str:
    return re.sub(r"[A-Z]", lambda m: "_" + m.group(0).lower(), name)


def read(target: object, name: str) -> Any:
    """Property read `target.name` on a config value: a parsed JSON object or a config dataclass.

    A dataclass field left at `None` was never set, so it reads as undefined; in a mapping an
    explicit `None` is JSON `null` and a missing key is undefined.
    """
    if target is None or target is UNDEFINED:
        raise TypeError(f"Cannot read properties of {to_string(target)} (reading '{name}')")
    if isinstance(target, Mapping):
        return target.get(name, UNDEFINED)
    if is_dataclass(target) and not isinstance(target, type):
        snake = _to_snake(name)
        if any(f.name == snake for f in fields(target)):
            value = getattr(target, snake)
            return UNDEFINED if value is None else value
    return UNDEFINED


def read_optional(target: object, name: str) -> Any:
    """`target?.name`."""
    if target is None or target is UNDEFINED:
        return UNDEFINED
    return read(target, name)


def nullish(v: Any, fallback: Any) -> Any:
    """`v ?? fallback`."""
    return fallback if v is None or v is UNDEFINED else v


def iterate(v: object) -> Iterable[Any]:
    """`for…of` / spread over a JSON value: arrays and strings iterate, nothing else does."""
    if isinstance(v, (list, tuple, str)):
        return v
    raise TypeError(f"{to_string(v)} is not iterable")


def length(v: object) -> int | float:
    """`v.length` for a JSON value, as a number; undefined reads as NaN."""
    if v is None or v is UNDEFINED:
        raise TypeError(f"Cannot read properties of {to_string(v)} (reading 'length')")
    if isinstance(v, str):
        return utf16_len(v)
    if isinstance(v, (list, tuple)):
        return len(v)
    return math.nan


def _is_array_index(key: str) -> bool:
    if not key.isascii() or not key.isdigit() or (len(key) > 1 and key[0] == "0"):
        return False
    return len(key) <= 10 and int(key) <= MAX_ARRAY_INDEX


def own_keys(obj: Mapping[str, Any]) -> list[str]:
    """Property order of a JS object: array indices ascending, then strings by insertion."""
    keys = list(obj)
    indices = [k for k in keys if _is_array_index(k)]
    if not indices:
        return keys
    indices.sort(key=int)
    return indices + [k for k in keys if not _is_array_index(k)]


# ── JSON ────────────────────────────────────────────────────────────────────────────────────────


def _json_number(text: str) -> int | float:
    # float(), not int(): every JSON number is a double, and int() refuses very long digit strings.
    return number(float(text))


def _reject_constant(text: str) -> None:
    raise ValueError(f"not JSON: {text}")


_DECODER: Final = json.JSONDecoder(
    parse_float=_json_number, parse_int=_json_number, parse_constant=_reject_constant
)

_WS: Final = re.compile(r"[ \t\n\r]*")
_JSON_NUMBER: Final = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")


def _parse_iterative(s: str) -> Any:
    """JSON.parse without recursion, for documents nested deeper than the C scanner will go."""
    stack: list[Any] = []
    keys: list[str | None] = []
    pos = _WS.match(s, 0).end()  # type: ignore[union-attr]
    while True:
        value: Any
        ch = s[pos : pos + 1]
        if ch == "[":
            pos = _WS.match(s, pos + 1).end()  # type: ignore[union-attr]
            if s[pos : pos + 1] == "]":
                value, pos = [], pos + 1
            else:
                stack.append([])
                keys.append(None)
                continue
        elif ch == "{":
            pos = _WS.match(s, pos + 1).end()  # type: ignore[union-attr]
            if s[pos : pos + 1] == "}":
                value, pos = {}, pos + 1
            else:
                if s[pos : pos + 1] != '"':
                    raise ValueError("expected a key")
                key, pos = scanstring(s, pos + 1, True)
                pos = _WS.match(s, pos).end()  # type: ignore[union-attr]
                if s[pos : pos + 1] != ":":
                    raise ValueError("expected a colon")
                pos = _WS.match(s, pos + 1).end()  # type: ignore[union-attr]
                stack.append({})
                keys.append(key)
                continue
        elif ch == '"':
            value, pos = scanstring(s, pos + 1, True)
        elif s.startswith("null", pos):
            value, pos = None, pos + 4
        elif s.startswith("true", pos):
            value, pos = True, pos + 4
        elif s.startswith("false", pos):
            value, pos = False, pos + 5
        else:
            matched = _JSON_NUMBER.match(s, pos)
            if matched is None:
                raise ValueError("expected a value")
            value, pos = _json_number(matched.group(0)), matched.end()

        while True:
            if not stack:
                if _WS.match(s, pos).end() != len(s):  # type: ignore[union-attr]
                    raise ValueError("extra data")
                return value
            top = stack[-1]
            if isinstance(top, list):
                top.append(value)
            else:
                top[keys[-1]] = value
            pos = _WS.match(s, pos).end()  # type: ignore[union-attr]
            ch = s[pos : pos + 1]
            if ch == ",":
                pos = _WS.match(s, pos + 1).end()  # type: ignore[union-attr]
                if isinstance(top, dict):
                    if s[pos : pos + 1] != '"':
                        raise ValueError("expected a key")
                    keys[-1], pos = scanstring(s, pos + 1, True)
                    pos = _WS.match(s, pos).end()  # type: ignore[union-attr]
                    if s[pos : pos + 1] != ":":
                        raise ValueError("expected a colon")
                    pos = _WS.match(s, pos + 1).end()  # type: ignore[union-attr]
                break
            if (ch == "]" and isinstance(top, list)) or (ch == "}" and isinstance(top, dict)):
                value = stack.pop()
                keys.pop()
                pos += 1
                continue
            raise ValueError("expected a delimiter")


def json_parse(text: str) -> Any:
    """`JSON.parse`. Raises ValueError for exactly what it rejects."""
    try:
        return _DECODER.decode(text)
    except RecursionError:
        return _parse_iterative(text)


def _quote(s: str) -> str:
    return _LONE_SURROGATE.sub(
        lambda m: f"\\u{ord(m.group(0)):04x}", encode_basestring(canon(s))
    )


def json_stringify(v: object) -> str | None:
    """`JSON.stringify`, returning None where it returns undefined."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, str):
        return _quote(v)
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            return "null"
        return number_to_string(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(json_stringify(item) or "null" for item in v) + "]"
    if isinstance(v, Mapping):
        parts = []
        for key in own_keys(v):
            encoded = json_stringify(v[key])
            if encoded is not None:
                parts.append(_quote(key) + ":" + encoded)
        return "{" + ",".join(parts) + "}"
    return None
