# Text transformations, written the hard way on purpose.
#
# Every function here has a one-line idiomatic version that uses `String.prototype.normalize()` or
# `Intl`, and every one of those is unavailable on Hermes, which ships without full ICU. They are
# green on Node, green in a browser, and broken on the device this actually runs on — the worst
# possible failure shape, because the tests pass.
#
# Unicode property escapes (`\p{L}`, `\p{M}`) are avoided for the same reason: their behaviour has
# historically differed between engines, and this package's whole claim is that it behaves
# identically on all three.
#
# So: explicit code-point ranges and an explicit mapping table. Bigger, uglier, and correct
# everywhere.
#
# ⚠️ THIS WAS `internal/text.ts`, AND THE SPLIT FROM `utils/` IS THE POINT. The mechanism —
# `transform`, `fold_table` — knows no language and lives in `utils/`. Everything here knows one:
# which code points Arabic writers vary on, and that German wants the opposite fold from French.
# **Nothing here is ever exported from `luraty_engine/__init__.py`**, exactly as `internal/` promised.

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, TypeIs, get_args

from luraty_engine._js import canon, to_lower_case
from luraty_engine.model.types import NormalizeStep
from luraty_engine.utils import assert_never, fold_table, transform

# U+0640, the elongation character. Purely decorative — it carries no sound and no meaning.
TATWEEL: Final = 0x0640

# Alef variants writers use interchangeably: آ أ إ ٱ all collapse to ا.
#
# Not a simplification. Arabic writers genuinely vary here, so treating أحمد and احمد as different
# words would fragment a learner's knowledge across spellings of the same thing.
ALEF_VARIANTS: Final = frozenset({0x0622, 0x0623, 0x0625, 0x0671})
ALEF: Final = "ا"

# ة → ه and ى → ي: the other pair writers vary on, especially word-finally.
TEH_MARBUTA: Final = 0x0629
HEH: Final = "ه"
ALEF_MAKSURA: Final = 0x0649
YEH: Final = "ي"

# What a replacer returns to delete a character.
DELETE: Final = ""

# Accented Latin letters → their base form.
#
# An explicit table because `'é'.normalize('NFD')` is the idiomatic way and it is ICU-backed. The
# table covers French thoroughly and the common Spanish, German, Portuguese and Nordic letters —
# enough for the languages in scope, and trivially extended.
LATIN_FOLD: Final = {
    "à": "a",
    "á": "a",
    "â": "a",
    "ã": "a",
    "ä": "a",
    "å": "a",
    "ā": "a",
    "è": "e",
    "é": "e",
    "ê": "e",
    "ë": "e",
    "ē": "e",
    "ì": "i",
    "í": "i",
    "î": "i",
    "ï": "i",
    "ī": "i",
    "ò": "o",
    "ó": "o",
    "ô": "o",
    "õ": "o",
    "ö": "o",
    "ø": "o",
    "ō": "o",
    "ù": "u",
    "ú": "u",
    "û": "u",
    "ü": "u",
    "ū": "u",
    "ý": "y",
    "ÿ": "y",
    "ñ": "n",
    "ç": "c",
    "æ": "ae",
    "œ": "oe",
    "ß": "ss",
}

# German umlauts to their two-letter forms: ä→ae, ö→oe, ü→ue, ß→ss.
#
# ⚠️ THE POINT IS THAT THIS IS NOT `LATIN_FOLD`, AND GERMAN IS WHY.
#
# The pack module already argues that a generic `strip_diacritics` is a lie because Arabic and Latin
# have nothing in common mechanically. German shows the same mistake one level further down: French
# and German are the *same script* and want *opposite* answers. French `é→e` is correct — `café` and
# `cafe` are one word. German `ö→o` is wrong, and destructively so. Measured against the real fold
# table, every one of these pairs collapsed to one key:
#
# | folded to `o`/`a`/`u` | …which is a different word |
# | --------------------- | -------------------------- |
# | schön (beautiful)     | schon (already)            |
# | zählen (to count)     | zahlen (to pay)            |
# | fördern (to promote)  | fordern (to demand)        |
# | drücken (to press)    | drucken (to print)         |
# | schwül (humid)        | schwul (gay)               |
# | Bär (bear)            | Bar (bar)                  |
#
# A learner who proved `zahlen` would be credited with `zählen`, and the engine would then never
# teach them one of the two. The two-letter fold is also what German itself does when umlauts are
# unavailable — passports, domain names, phone books — so it is the language's own convention
# rather than an invention.
#
# `ß→ss` is shared with `LATIN_FOLD` and correct in both.
GERMAN_FOLD: Final = {
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "ß": "ss",
    # The capitals are here so the step does not silently depend on `lowercase` running first. A pack
    # author who omits it gets the right answer anyway.
    "Ä": "ae",
    "Ö": "oe",
    "Ü": "ue",
    "ẞ": "ss",
}
PUNCTUATION: Final = frozenset(
    ord(ch)
    for ch in [
        *'.,;:!?"`()[]{}<>«»„“”‘’–—-_/\\|@#$%^&*+=~',
        "،",  # ، Arabic comma
        "؛",  # ؛ Arabic semicolon
        "؟",  # ؟ Arabic question mark
        "٪",  # ٪ Arabic percent
        "۔",  # ۔ Urdu full stop
    ]
)

# Every step, as a runtime value.
NORMALIZE_STEPS: Final[tuple[NormalizeStep, ...]] = get_args(NormalizeStep)

# The same names as a Set, which is what membership is actually tested against.
#
# ⚠️ A Set and not the object in `NORMALIZE_STEPS`, for the reason `create_pack` uses a Map for its lemma
# table: `'constructor' in STEPS` is TRUE through the prototype chain, so an object lookup would
# validate `constructor`, `toString`, `__proto__` and `valueOf` and then throw from `apply_step`. A
# Set has no prototype chain to fall through, which removes the class rather than guarding each
# case.
_STEP_NAMES: Final[frozenset[str]] = frozenset(NORMALIZE_STEPS)


def is_arabic_diacritic(code: int) -> bool:
    r"""The short-vowel marks and friends: fathatan through sukun (U+064B–U+0652), plus shadda,
    superscript alef (U+0670) and the Quranic marks at U+0653–U+0655.

    Stripping them is not lossy in practice — real Arabic writing omits them almost entirely, so a
    learner typing an undiacritised word and a bank containing a diacritised one must match.

    ⚠️ **U+06D6–U+06ED, THE QUR'ANIC ANNOTATION BLOCK, IS INCLUDED — and omitting it silently cut
    words in half.** Measured 2026-08-01 on al-Baqarah 2:2: `هُدًۭى` carries U+06ED ARABIC SMALL LOW
    MEEM *between* the tanween and the alef maksura. Without this range the mark survives
    normalisation, so `key()` returns a string no lemma table contains — and worse, a tokenizer built
    from the same character set splits the word into `هُدً` and `ى`: two fragments, neither of them a
    word.

    The block holds recitation and pause signs — sajdah, the small high seen, the small low meem.
    They tell a reciter how to *say* a word; none of them changes *which* word it is, which is
    exactly the test for belonging here.

    The corrected token count over the full mushaf is **77,878**, down from 80,811 — and 77,878 is
    independently what the `ar-x-quran` pack build reports, which is the reason to believe this range
    is now right rather than merely wider.

    ⚠️ A pack widening its tokenizer to match must also DROP tokens that normalise to nothing. Some
    of these signs stand alone between words, so a wider character class admits tokens made of no
    letters at all.
    """
    return 0x064B <= code <= 0x0655 or code == 0x0670 or 0x06D6 <= code <= 0x06ED


_DROP_ARABIC_DIACRITIC: Final = {c: DELETE for c in range(0x0600, 0x0700) if is_arabic_diacritic(c)}
_DROP_PUNCTUATION: Final = {c: DELETE for c in PUNCTUATION}
_DROP_TATWEEL: Final = {TATWEEL: DELETE}
_TO_ALEF: Final = {c: ALEF for c in ALEF_VARIANTS}
_TO_FINAL: Final = {TEH_MARBUTA: HEH, ALEF_MAKSURA: YEH}
_FOLD_LATIN: Final = fold_table(LATIN_FOLD)
_FOLD_GERMAN: Final = fold_table(GERMAN_FOLD)


def is_normalize_step(value: object) -> TypeIs[NormalizeStep]:
    """Is this a step the engine actually has?"""
    return isinstance(value, str) and value in _STEP_NAMES


def strip_punctuation(s: str) -> str:
    return transform(s, _DROP_PUNCTUATION)


def strip_arabic_diacritics(s: str) -> str:
    return transform(s, _DROP_ARABIC_DIACRITIC)


def strip_tatweel(s: str) -> str:
    return transform(s, _DROP_TATWEEL)


def normalize_arabic_alef(s: str) -> str:
    return transform(s, _TO_ALEF)


def normalize_arabic_finals(s: str) -> str:
    return transform(s, _TO_FINAL)


def fold_latin_diacritics(s: str) -> str:
    return transform(s, _FOLD_LATIN)


def fold_german_umlauts(s: str) -> str:
    r"""German umlauts to their two-letter forms. See `GERMAN_FOLD` for the six word pairs this keeps
    apart, and for why it is emphatically not `foldLatinDiacritics`.
    """
    return transform(s, _FOLD_GERMAN)


def apply_step(step: NormalizeStep, s: str) -> str:
    """Apply one named step. Exhaustive, so adding a step to the union breaks this until it is handled."""
    match step:
        case "lowercase":
            # NOT toLocaleLowerCase: that is ICU-backed and, worse, locale-dependent — the Turkish
            # dotless-i rule would make the same word normalize differently on a Turkish phone.
            return to_lower_case(s)
        case "stripPunctuation":
            return strip_punctuation(s)
        case "stripArabicDiacritics":
            return strip_arabic_diacritics(s)
        case "stripTatweel":
            return strip_tatweel(s)
        case "normalizeArabicAlef":
            return normalize_arabic_alef(s)
        case "normalizeArabicFinals":
            return normalize_arabic_finals(s)
        case "foldLatinDiacritics":
            return fold_latin_diacritics(s)
        case "foldGermanUmlauts":
            return fold_german_umlauts(s)
        case _:
            assert_never(step, "NormalizeStep")


def apply_steps(steps: Sequence[NormalizeStep], s: str) -> str:
    """Apply steps in order."""
    out = canon(s)
    for step in steps:
        out = apply_step(step, out)
    return out
