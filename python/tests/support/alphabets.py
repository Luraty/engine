"""Script-aware string generators, ported from src/testing/alphabets.ts."""

from support.prop import any_code_point_string, array, constant_from, mapped, string_of

_ARABIC_LETTERS_BASE = list("ابتثجحخدذرزسشصضطظعغفقكلمنهوي")

ARABIC_UNITS = [*_ARABIC_LETTERS_BASE, "أ", "إ", "آ", "ٱ", "ة", "ى", "ً", "ُ", "ِ", "ّ", "ْ", "ٰ", "ـ", "،", "؟", " "]

FRENCH_UNITS = [
    *"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    *"àâäéèêëîïôöùûüÿçœæ",
    *"ÀÂÄÉÈÊËÎÏÔÖÙÛÜŸÇŒÆ",
    "'",
    " ",
    ".",
    ",",
]

arabic_text = string_of(ARABIC_UNITS)
french_text = string_of(FRENCH_UNITS)
any_text = any_code_point_string()

ARABIC_LETTERS = [*_ARABIC_LETTERS_BASE, "أ", "إ", "آ", "ٱ", "ة", "ى"]
FRENCH_LETTERS = [*"abcdefghijklmnopqrstuvwxyz", *"àâäéèêëîïôöùûüÿçæ"]


def text_for(pack_id):
    return arabic_text if pack_id.startswith("ar") else french_text


def _passage(letters, words):
    word = string_of(letters, min_length=1, max_length=8)
    return mapped(array(word, min_length=words, max_length=words), " ".join)


def passage_for(pack_id, words):
    return _passage(ARABIC_LETTERS if pack_id.startswith("ar") else FRENCH_LETTERS, words)


__all__ = [
    "any_text",
    "arabic_text",
    "constant_from",
    "french_text",
    "passage_for",
    "text_for",
]
