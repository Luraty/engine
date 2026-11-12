r"""Building a language pack from configuration and data.

This is the answer to "can a language be added without writing code?". Yes: a pack is a JSON
config naming which transformations to apply, plus two data files. The engine owns the
transformations; the pack owns the choices.

A language that genuinely needs something new — Chinese and Japanese have no spaces and need
dictionary segmentation — means adding one strategy here, once, after which it is available to
every language.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any, Final

from luraty_engine import _js
from luraty_engine.model import (
    Decoded,
    DecodedError,
    DecodedOk,
    DecodeError,
    LanguagePack,
    Lemma,
    NormalizeStep,
    PackConfig,
    PackData,
    variety,
)
from luraty_engine.normalize import NORMALIZE_STEPS, apply_steps, is_normalize_step

_MAX_PATTERN_LENGTH: Final = 200

# A single character class followed by `+`, and nothing else.
#
# The class body accepts escapes (`\\u0600`, `\\]`) and any character that is not an unescaped
# `]`. A character class cannot backtrack catastrophically — there is no nesting and no
# alternation to explore — so this shape is safe by construction rather than by inspection.
_CHARACTER_CLASS_PATTERN: Final = re.compile(r"\[(?:\\[^\n\r  ]|[^\]\\])+\]\+")

_MAX_CODE_POINT: Final = 0x10FFFF
_DIGITS: Final = [(0x30, 0x39)]
_WORD: Final = [(0x30, 0x39), (0x41, 0x5A), (0x5F, 0x5F), (0x61, 0x7A)]
_SPACE: Final = [(ord(c), ord(c)) for c in _js.WHITESPACE]
_HEX: Final = frozenset("0123456789abcdefABCDEF")
_SYNTAX_CHARACTERS: Final = frozenset("^$\\.*+?()[]{}|/-")
_CONTROL_ESCAPES: Final = {"f": 0x0C, "n": 0x0A, "r": 0x0D, "t": 0x09, "v": 0x0B, "b": 0x08}


class _InvalidExpression(Exception):
    pass


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for lo, hi in sorted(ranges):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def _complement(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    next_free = 0
    for lo, hi in _merge(ranges):
        if lo > next_free:
            out.append((next_free, lo - 1))
        next_free = hi + 1
    if next_free <= _MAX_CODE_POINT:
        out.append((next_free, _MAX_CODE_POINT))
    return out


def _hex_at(body: str, start: int, count: int) -> int | None:
    digits = body[start : start + count]
    if len(digits) != count or not _HEX.issuperset(digits):
        return None
    return int(digits, 16)


def _class_atom(body: str, i: int) -> tuple[int | None, list[tuple[int, int]], int]:
    """One ClassAtom under the `u` flag: (code point or None, class-escape ranges, next index)."""
    ch = body[i]
    if ch != "\\":
        return ord(ch), [], i + 1

    i += 1
    esc = body[i]
    i += 1
    if esc in _CONTROL_ESCAPES:
        return _CONTROL_ESCAPES[esc], [], i
    if esc in _SYNTAX_CHARACTERS:
        return ord(esc), [], i
    if esc == "d":
        return None, _DIGITS, i
    if esc == "D":
        return None, _complement(_DIGITS), i
    if esc == "w":
        return None, _WORD, i
    if esc == "W":
        return None, _complement(_WORD), i
    if esc == "s":
        return None, _SPACE, i
    if esc == "S":
        return None, _complement(_SPACE), i
    if esc == "c":
        letter = body[i : i + 1]
        if letter.isascii() and letter.isalpha():
            return ord(letter) % 32, [], i + 1
        raise _InvalidExpression
    if esc == "0":
        if body[i : i + 1].isascii() and body[i : i + 1].isdigit():
            raise _InvalidExpression
        return 0, [], i
    if esc == "x":
        code = _hex_at(body, i, 2)
        if code is None:
            raise _InvalidExpression
        return code, [], i + 2
    if esc == "u":
        return _unicode_escape(body, i)
    if esc in "pP" and body[i : i + 1] == "{":
        raise NotImplementedError(
            r"\p{…} in a tokenize pattern: Python's stdlib has no Unicode property tables "
            r"matching the JS engine's, so this cannot be reproduced exactly"
        )
    raise _InvalidExpression


def _unicode_escape(body: str, i: int) -> tuple[int, list[tuple[int, int]], int]:
    if body[i : i + 1] == "{":
        end = body.find("}", i + 1)
        digits = body[i + 1 : end] if end > 0 else ""
        if not digits or not _HEX.issuperset(digits) or int(digits, 16) > _MAX_CODE_POINT:
            raise _InvalidExpression
        return int(digits, 16), [], end + 1
    code = _hex_at(body, i, 4)
    if code is None:
        raise _InvalidExpression
    i += 4
    if 0xD800 <= code <= 0xDBFF and body[i : i + 2] == "\\u":
        low = _hex_at(body, i + 2, 4)
        if low is not None and 0xDC00 <= low <= 0xDFFF:
            return 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00), [], i + 6
    return code, [], i


def _compile_tokenizer(pattern: str) -> re.Pattern[str] | None:
    """`new RegExp(pattern, 'gu')` for a `[…]+` pattern. None means the class is empty."""
    body = pattern[1:-2]
    n = len(body)
    i = 0
    negate = body.startswith("^")
    if negate:
        i = 1
    ranges: list[tuple[int, int]] = []
    while i < n:
        low, low_set, i = _class_atom(body, i)
        if i < n and body[i] == "-" and i + 1 < n:
            high, _, i = _class_atom(body, i + 1)
            if low is None or high is None or low > high:
                raise _InvalidExpression
            ranges.append((low, high))
        elif low is None:
            ranges.extend(low_set)
        else:
            ranges.append((low, low))
    merged = _complement(ranges) if negate else _merge(ranges)
    if not merged:
        return None
    return re.compile(
        "["
        + "".join(
            f"\\U{lo:08x}" if lo == hi else f"\\U{lo:08x}-\\U{hi:08x}" for lo, hi in merged
        )
        + "]+"
    )


def _fail(message: str) -> DecodedError:
    return DecodedError(error=DecodeError(kind="malformed", message=message))


def _check_steps(steps: object, name: str) -> Decoded[Sequence[NormalizeStep]]:
    r"""Check a step list against the closed set the engine actually implements.

    ⚠️ WITHOUT THIS, `create_pack` BROKE ITS OWN CONTRACT — it promises a `Decoded` rather than a
    throw, precisely because a config is a JSON file a human wrote. An unrecognised step reached
    `apply_step`'s exhaustive switch and came back out as `assert_never`'s exception.

    Three measured failures, all from configs a real author would plausibly write:

    - `normalize: ['strip_diacritics']` **threw** from inside `create_pack`. That name is not an
      invention — it is the obvious generic guess, and it is the one the engine deliberately does not
      have (Arabic and Latin diacritics have nothing in common mechanically, so one name over both is
      how the wrong fold gets applied to the wrong language).
    - `compare: ['normalize_alef']` was **worse: the pack BUILT**, reported healthy, and threw later
      from `compare()` — when a learner submitted an answer. The compare list is never touched at
      build time, so nothing looked at it until mid-session.
    - `normalize: 'lowercase'` — a string where a JSON file should hold an array — threw complaining
      about a step named `"l"`, because a string iterates character by character.

    `strategy` was already widened to `string` and checked, with a comment explaining that the type is
    a claim about intent rather than about what is in memory. The same argument always applied to
    these two fields; it just was not carried across.
    """
    if not _js.is_array(steps):
        return _fail(f'"{name}" must be a list of steps')
    for step in steps:  # type: ignore[attr-defined]
        if not is_normalize_step(step):
            allowed = ", ".join(NORMALIZE_STEPS)
            shown = _js.json_stringify(step)
            return _fail(
                f"unknown {name} step {'undefined' if shown is None else shown} — must be one of: {allowed}"
            )
    return DecodedOk(value=steps)  # type: ignore[arg-type]


def _build_ranks(frequency: str, normalize: Sequence[NormalizeStep]) -> dict[str, int]:
    r"""Parse the frequency list into a rank lookup, **keyed by the normalized form**.

    Built once when the pack is created, not on every call. The data arrives as a rank-ordered string
    because the position IS the rank — see `PackData.frequency` for why that matters on a
    phone.

    The Map doubles as the pack's lexicon: "is this a word at all?" is `has()`, which is what makes
    safe affix stripping possible without a morphological analyser.

    ⚠️ NORMALIZED, and that is a correctness fix rather than tidying.

    This map used to be indexed by the RAW word from the frequency string, while every lookup against
    it — `rank()` and, crucially, the `only_if_remainder_known` guard in `strip_prefixes` — passes a
    NORMALIZED form. So the two sides disagreed for every word any normalize step touches.

    Measured on this repo's own fixtures, before the fix:

    - `key('المدينة')` returned `المدينه` — the article `ال` was NOT stripped, because the guard
      looked up `مدينه` (finals normalized) in a map holding `مدينة`. Meanwhile `key('مدينة')`
      returned `مدينه`. **One word, two unit keys.** A learner who proves `مدينة` gets no credit for
      `المدينة`, forever, and the engine reports it as their gap.
    - `rank(key(w))` was `undefined` for **7 of the 34** Arabic fixture words and for French `est`
      (the 12th commonest word in its own list).

    Nothing errored. The pack built, tokenized and graded; it just quietly filed the article-bearing
    and bare forms of a word apart, which is systematic pessimism that reads as the learner's fault.
    It is exactly the shape of the wrong-separator bug below — a pack that works, quietly, and
    teaches nobody anything.

    The rank NUMBER still comes from the position in the raw list, so normalization cannot renumber
    anything: two entries that collapse to one form keep the earlier one's rank, and every later
    word keeps the position it had.
    """
    ranks: dict[str, int] = {}
    rank = 0
    # ⚠️ ANY whitespace, not just a space. Splitting on ' ' alone meant a newline-separated list
    # produced exactly one giant "word" — so `rank()` returned undefined for everything, and affix
    # stripping stopped dead, because `only_if_remainder_known` consults this same map and every lookup
    # missed. The pack reported healthy the whole time.
    #
    # This is not a hypothetical format: Leipzig, OpenSubtitles and wordfreq — the three sources this
    # project's own guide recommends — are all one word per line. The first real pack anyone builds
    # would have hit it.
    for word in _js.split_whitespace(frequency):
        if len(word) == 0:
            continue
        # Incremented BEFORE the normalization check, because the rank is the position in the list the
        # pack author wrote. A word that normalizes away still occupied a slot.
        rank += 1
        normalized = apply_steps(normalize, word)
        # A frequency entry that normalizes to nothing (a lone tatweel, a stray diacritic) is not a
        # word. Keeping it would put the empty string in the lexicon, and `strip_prefixes` would then
        # accept any prefix whose remainder normalizes away.
        if len(normalized) == 0:
            continue
        # First occurrence wins: a duplicate later in the list is rarer by definition, and silently
        # overwriting would make the more common entry disappear. After normalization this also covers
        # pairs that collapse — French `marche` and `marché` are one lexical entry, and the earlier
        # (commoner) position is the honest rank for it.
        if normalized not in ranks:
            ranks[normalized] = rank
    return ranks


def _table_rows(table: object) -> list[tuple[str, Any]]:
    """Walk `data.lemmas` as `Object.keys` would, or in insertion order for a Map-shaped table."""
    if isinstance(table, Mapping):
        if isinstance(table, dict) and not isinstance(table, OrderedDict):
            return [(key, table[key]) for key in _js.own_keys(table)]
        return list(table.items())
    if isinstance(table, (list, tuple)):
        return [(str(i), entry) for i, entry in enumerate(table)]
    if isinstance(table, str):
        return [(str(i), unit) for i, unit in enumerate(_js.utf16_units(table))]
    return []


def _build_lemmas(
    table: object, normalize: Sequence[NormalizeStep]
) -> dict[str, tuple[Lemma, ...]]:
    # A Map, not the plain object it arrives as — and this is a correctness fix, not a preference.
    #
    # Property testing found it in seconds: `lemmas['constructor']` on a plain object returns
    # `Object.prototype.constructor`, which is a FUNCTION. So `key('constructor')` returned a
    # function where every caller expects a string, and `key('toString')`, `key('__proto__')` and
    # `key('valueOf')` are all the same bug. Real text contains these words.
    #
    # A Map has no prototype chain to fall through, which removes the whole class rather than
    # patching the instances of it.
    #
    # ⚠️ BOTH SIDES NORMALIZED, for exactly the reason `build_ranks` normalizes — this is the same
    # defect, and fixing it there only fixed half of it.
    #
    # `key()` looks this table up with an already-normalized surface form, so a raw key can never
    # match. Found with real German: a pack author writes the natural `"läuft": "laufen"`, and
    # `key('läuft')` normalizes to `laeuft`, misses the table entirely, and returns `laeuft` — so the
    # inflected form and the infinitive become two separate units and proving one never credits the
    # other.
    #
    # The VALUE is normalized too, and that matters just as much: leaving it raw would make
    # `key('läuft')` return `laufen` while `key('läufst')` … also returns `laufen`, but
    # `key('laufen')` returns `laufen` — fine here, yet the moment a lemma target itself contains an
    # umlaut (`"zählt": "zählen"`) the raw value `zählen` and the normalized `zaehlen` are two
    # different addresses for one word. Normalizing both ends means a pack file can be written in
    # ordinary German and still address knowledge consistently.
    #
    # ⚠️ ONE MAP HOLDS THE WHOLE LIST, AND `key` READS ELEMENT ZERO — rather than two maps kept in
    # step. A pack whose `key` table and `candidates` table could disagree is the same defect as the
    # frequency list and `key()` disagreeing (#106) and the normalize chain and the lemma table
    # disagreeing (see `build_ranks`): two descriptions of one language, with nothing making them
    # agree. Deriving one from the other by construction is the only fix that stays fixed.
    lemmas: dict[str, tuple[Lemma, ...]] = {}
    for surface, entry in _table_rows(table):
        source = apply_steps(normalize, surface)
        if len(source) == 0:
            continue
        # First entry wins, matching `build_ranks` — a duplicate later in the file is the author's
        # second thought, and silently overwriting makes the first one vanish without a word. Checked
        # BEFORE the values are normalized, so a duplicate costs nothing on a 90k-row table.
        if source in lemmas:
            continue
        readings: list[Lemma] = []
        if isinstance(entry, str):
            normalized = apply_steps(normalize, entry)
            if len(normalized) != 0:
                readings.append(normalized)
        elif _js.is_array(entry):
            for candidate in entry:
                if not isinstance(candidate, str):
                    continue
                normalized = apply_steps(normalize, candidate)
                # A lemma that normalizes away is not a lemma. Dropping it here rather than storing "" is
                # what keeps `candidates` from ever handing a caller an empty string to render.
                if len(normalized) == 0:
                    continue
                # ⚠️ DEDUPED AFTER NORMALIZATION, NOT BEFORE. Two spellings of one lemma are one reading,
                # and in an unvocalised script that is the ordinary case rather than an author's mistake:
                # كَتَبَ and كتب are the same row written twice. Left in, the reader is offered the same
                # sense twice and asked to choose between it, which is worse than no choice at all.
                if normalized not in readings:
                    readings.append(normalized)
        if readings:
            lemmas[source] = tuple(readings)
    return lemmas


def _sorted_prefixes(prefixes: object) -> list[Any]:
    # Longest prefix first, so ال is tried before ا and the more specific rule wins.
    items = list(_js.iterate(prefixes))
    if len(items) < 2:
        return items
    lengths = [_js.length(item) for item in items]
    unmeasured = [length != length for length in lengths]
    if any(unmeasured) and not all(unmeasured):
        raise NotImplementedError(
            "affix prefixes mixing strings with values that have no length: the JS comparator "
            "returns NaN for some pairs, so the order is whatever V8's sort does"
        )
    if all(unmeasured):
        return items
    return [
        item for _, item in sorted(zip(lengths, items, strict=True), key=lambda pair: -pair[0])
    ]


def create_pack(config: PackConfig | Mapping[str, Any], data: PackData | Mapping[str, Any]) -> Decoded[LanguagePack]:
    r"""Build a `LanguagePack`.

    Returns a `Decoded` rather than throwing, because config is untrusted input: it comes from
    a JSON file that a human wrote, possibly for a different version of this engine.
    """
    # ⚠️ THE SHAPE IS CHECKED BEFORE ANY FIELD IS READ, and leaving that out was a real bug.
    #
    # The rest of this function widens each field to `string` and checks it, on the correct argument
    # that a JSON file a human wrote may not match the type. But it then reached straight into
    # `config.tokenize.strategy` — so a config MISSING `tokenize` entirely threw
    # `Cannot read properties of undefined (reading 'strategy')`.
    if not _js.is_object(config):
        return _fail("pack config is not an object")
    config_id = _js.read(config, "id")
    if not isinstance(config_id, str) or len(config_id) == 0:
        return _fail("pack has no id")

    # ⚠️ THE ID MUST BE A LEGAL VARIETY, because `LanguagePack.id` IS the variety — see the field's
    # docstring. Before this check a pack id of `'ar:msa'` built cleanly while `variety()` rejected
    # the same string, and a host that used it as a variety got `recognise:ar:msa:سوق`, which
    # `parse_unit_key` reads back as variety `ar`, word `msa:سوق`. A pack that builds, reports healthy,
    # and silently re-addresses every word it owns.
    #
    # Routed through the blessed constructor rather than re-testing for a colon here, so there is one
    # definition of "legal variety" and this cannot drift from it.
    pack_variety = variety(config_id)
    if pack_variety is None:
        return _fail(f'pack id "{config_id}" is not a legal variety — it must not contain ":"')
    tokenize = _js.read(config, "tokenize")
    if not _js.is_object(tokenize):
        return _fail('pack config has no "tokenize" section')
    pattern = _js.read(tokenize, "pattern")
    if not isinstance(pattern, str):
        return _fail('pack config has no "tokenize.pattern"')

    if not _js.is_object(data):
        return _fail("pack data is not an object")
    frequency = _js.read(data, "frequency")
    if not isinstance(frequency, str):
        return _fail('pack data has no "frequency" string')

    # Widened to `string` on purpose. The type says this can only be 'regex', but the value came out
    # of a JSON file that a human wrote — possibly against a different version of this engine — so
    # the type is a claim about intent, not about what is actually in memory. Checking a
    # "impossible" case is the whole job at a trust boundary.
    strategy = _js.read(tokenize, "strategy")
    if strategy != "regex":
        return _fail(f'unknown tokenize strategy "{_js.to_string(strategy)}"')
    pattern = _js.canon(pattern)
    if _js.utf16_len(pattern) > _MAX_PATTERN_LENGTH:
        return _fail("tokenize pattern is suspiciously long")

    # ⚠️ THE SHAPE IS ENFORCED, not just the length.
    #
    # This guard used to be the length cap alone, with a comment claiming it stopped a pack file
    # smuggling in catastrophic backtracking. That claim was simply false: `(a+)+b` is six
    # characters, sailed through, and took 790 MILLISECONDS to fail on a 27-character string. On a
    # phone that is a frozen app on the first sentence a learner reads, and it scales exponentially.
    #
    # So the pattern must be exactly a character class with a `+`: `[...]+`. That is not a
    # restriction in practice — it is what every real tokenizer pattern already looks like
    # (`[a-z]+`, `[؀-ۿ]+`, `[a-z_a-Zà-öø-ÿ']+`) — and it makes runaway backtracking
    # impossible by construction rather than by hoping nobody writes a nested quantifier. It also
    # makes the code match what `TokenizeConfig.pattern` always claimed to be: "not a full regex".
    if _CHARACTER_CLASS_PATTERN.fullmatch(pattern) is None:
        return _fail(
            f'tokenize pattern must be a single character class followed by "+", such as "[a-z]+" — got "{pattern}"'
        )

    # Both lists, checked BEFORE anything uses them — `compare`'s especially, because nothing at build
    # time would otherwise touch it and the throw would land mid-session on a learner's answer.
    normalize_steps = _check_steps(_js.read(config, "normalize"), "normalize")
    if not normalize_steps.ok:
        return normalize_steps
    compare_steps = _check_steps(_js.read(config, "compare"), "compare")
    if not compare_steps.ok:
        return compare_steps

    # Everything below reads these, never `config.normalize` / `config.compare` — hold the parsed
    # value, not the unchecked one, so the check cannot be bypassed by a later edit reaching past it.
    normalize = normalize_steps.value
    compare = compare_steps.value

    try:
        # Compiled once, here, so a broken pattern is a pack-loading error rather than a crash on the
        # first sentence a learner reads.
        tokenizer = _compile_tokenizer(pattern)
    except _InvalidExpression:
        return _fail(f"tokenize pattern is not a valid expression: {pattern}")

    ranks = _build_ranks(frequency, normalize)
    lemmas = _build_lemmas(_js.nullish(_js.read(data, "lemmas"), {}), normalize)

    affixes = _js.read(config, "affixes")
    prefixes = _sorted_prefixes(_js.nullish(_js.read_optional(affixes, "prefixes"), []))
    only_if_remainder_known = _js.is_truthy(
        _js.nullish(_js.read_optional(affixes, "onlyIfRemainderKnown"), True)
    )

    def strip_prefixes(word: str) -> str:
        # ⚠️ A WORD THE LIST ALREADY KNOWS IS NEVER STRIPPED, and leaving this out was a real bug.
        #
        # German `geben` (to give) is in every frequency list, and `ge` is the participle prefix, and
        # `ben` happened to be a listed word too — so `key('geben')` returned `ben` while the lemma
        # table mapped `gibt`, `gab` and `gegeben` onto `geben`. One word, two unit keys, and measured
        # against real news text it cost 105 running tokens: the commonest genuinely-unknown "word" in
        # the whole sample was a verb every learner knows.
        #
        # The same guard already protects compound splitting a few lines down. A word that is in the
        # lexicon is a word, not a thing to take apart.
        if word in ranks:
            return word

        for prefix in prefixes:
            if not _js.starts_with(word, _js.to_string(prefix)):
                continue
            remainder = _js.utf16_slice(word, _js.length(prefix))
            if len(remainder) == 0:
                continue
            # The guard that makes this safe without a morphological analyser. Arabic و ("and") is a real
            # prefix, so ولد would strip to لد, which is not a word. Checking the remainder against the
            # frequency list — which is already loaded — refuses the strip unless the result is something
            # the language actually contains.
            if only_if_remainder_known and remainder not in ranks:
                continue
            return remainder
        return word

    compounds = _js.read(config, "compounds")
    # Longest realistic German compound. Past this it is a scanner artefact, not a word.
    max_compound_length: Final = 40

    def decompose(word: str, depth: int = 0) -> tuple[str, ...] | None:
        # Split a compound into known parts, head last. Returns undefined when it does not decompose.
        #
        # Longest-part-first from the left, so `Bahnhofstraße` prefers `bahnhof` over `bahn`. Every part
        # must be a word the frequency list contains — that is the whole safety argument, and it is the
        # same one `only_if_remainder_known` makes for affixes.
        word_length = _js.utf16_len(word)
        if depth > 4 or word_length > max_compound_length:
            return None
        if word in ranks and word_length >= _js.to_number(
            _js.nullish(_js.read_optional(compounds, "minPartLength"), 4)
        ):
            return (word,)
        if compounds is _js.UNDEFINED:
            return None

        min_part = _js.to_number(_js.read(compounds, "minPartLength"))
        cut: int | float = word_length - min_part
        while cut >= min_part:
            head = _js.utf16_slice(word, 0, cut)
            if head in ranks:
                for linker in _js.iterate(_js.read(compounds, "linkers")):
                    if not _js.starts_with(word, head + _js.to_string(linker)):
                        continue
                    rest = _js.utf16_slice(word, cut + _js.length(linker))
                    if _js.utf16_len(rest) < min_part:
                        continue
                    tail = decompose(rest, depth + 1)
                    if tail is not None:
                        return (head, *tail)
            cut -= 1
        return None

    def key_of_normalized(normalized: str) -> Lemma:
        # An explicit lemma entry beats a derived one: irregular forms are exactly the ones affix rules
        # get wrong, and they are why the map exists.
        #
        # ⚠️ ELEMENT ZERO, AND THE TABLE GUARANTEES THERE IS ONE — every list reaching the map has at
        # least one member, so this is not an optional read dressed as a definite one. The primary is
        # whatever the pack author wrote first; the engine has no basis on which to reorder it.
        mapped = lemmas.get(normalized)
        if mapped is not None:
            return mapped[0]

        stripped = strip_prefixes(normalized)
        # A word the list already knows is never a compound — `Fenster` must not decompose into
        # `fen` + `ster`, and checking membership first makes that impossible rather than unlikely.
        if compounds is _js.UNDEFINED or stripped in ranks:
            return stripped

        parts = decompose(stripped)
        # Head-final: German compounds take their meaning and their gender from the last element.
        # A single-element result is not a compound, so it changes nothing.
        if parts is not None and len(parts) > 1:
            return parts[-1]
        return stripped

    def key(surface: str) -> Lemma:
        return key_of_normalized(apply_steps(normalize, surface))

    def candidates(surface: str) -> tuple[Lemma, ...]:
        # Every reading of a surface form, likeliest first.
        #
        # ⚠️ **IT DEFERS TO `key`'s OWN BODY FOR EVERYTHING THE TABLE DOES NOT LIST, RATHER THAN
        # REPEATING ITS LOGIC.** Affix stripping and compound splitting are guesses too — arguably better
        # candidate generators than the table — and re-deriving them here would be a second
        # implementation of `key`, free to drift from the first. `key_of_normalized` is that body, shared
        # rather than copied, so the two enter the same code one step apart and cannot disagree.
        #
        # The consequence is worth stating: a form reached by stripping ال off a word comes back as one
        # candidate, not two, even though the unstripped form may also be a word. Widening that is a
        # decision about how much doubt to show a reader, and it belongs in a pack's data rather than in
        # a rule the engine applies to every language at once.
        normalized = apply_steps(normalize, surface)
        listed = lemmas.get(normalized)
        if listed is not None:
            return listed
        # ⚠️ NEVER EMPTY. The contract promises at least one element and promises the first is `key`'s
        # answer, and both are what let a caller render this list without a length check. `key` on an
        # unknown form returns the normalized form itself, which is the honest single candidate: it is
        # what the engine would address the word by if the learner proved it.
        return (key_of_normalized(normalized),)

    def split(text: str) -> tuple[str, ...]:
        if tokenizer is None:
            return ()
        return tuple(tokenizer.findall(_js.canon(text)))

    def rank(lemma: Lemma) -> int | None:
        return ranks.get(lemma)

    def compare_answers(given: str, expected: str) -> int:
        a = _js.trim(apply_steps(compare, given))
        b = _js.trim(apply_steps(compare, expected))

        # ⚠️ An expected answer that normalizes to nothing scores ZERO, always — including when the
        # learner also submitted nothing.
        #
        # This used to return 1 when both sides came out empty, which meant `compare('!!!', '?')`
        # was a correct answer: both normalize away to nothing, and nothing equals nothing. One
        # punctuation-only answer key in a content batch would mark every learner correct on that
        # item forever, and it would never be reported — nobody complains about being told they are
        # right.
        #
        # An unanswerable key is a content bug, and the honest score for it is 0. Awarding credit
        # would be the engine covering up for its own content.
        #
        # ⚠️ Nothing in this package will TELL you it happened. `check_pack` takes a text sample, not
        # answer keys, so it cannot see one — catching them is a job for whatever pipeline mints the
        # content. This comment used to claim `check_pack` flagged it, which it never did.
        if len(b) == 0:
            return 0

        return 1 if a == b else 0

    return DecodedOk(
        value=LanguagePack(
            id=pack_variety,
            split=split,
            key=key,
            candidates=candidates,
            rank=rank,
            compare=compare_answers,
        )
    )

