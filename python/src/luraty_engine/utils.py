# Utilities — mechanisms that belong to no module.
#
# This is the folder `internal/` used to be, renamed and narrowed. **Nothing here is ever exported
# from `luraty_engine/__init__.py`**; that was `internal/`'s whole point and it survives unchanged. What changed
# is the admission rule, which used to be "small and mechanical" and is now checkable.
#
# ⚠️ TWO CLAUSES, AND BOTH MUST HOLD:
#
#  1. the signature mentions **no domain type** — no `Profile`, `UnitState`, `NormalizeStep`;
#  2. the body knows **no module's vocabulary** — no languages, no rungs, no wire offsets.
#
# Both are needed, and the near misses are the proof. All three of these were in `internal/text.ts`
# and none of them qualify:
#
#  `apply_step(step, s)`     — clause 1 fails. `NormalizeStep` is a domain type.
#  `foldGermanUmlauts(s)`   — clause 1 passes, clause 2 fails: it knows German, and knows that
#                             German wants the OPPOSITE fold from French. Moved to `normalize/`.
#  `is_normalize_step(v)`     — takes `unknown`, returns a domain predicate. `normalize/`.
#
# A function that passes both can be read, tested and replaced without knowing what this package is
# for — which is the only thing that makes a `utils/` folder something other than a junk drawer.

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Never

from luraty_engine._js import canon


def assert_never(value: Never, what: str) -> Never:
    r"""Exhaustiveness checking.

    The throw is unreachable if the types are honest. It exists for the case where they are not —
    data deserialized from an older version, say.
    """
    raise RuntimeError(f"unhandled {what}: {json.dumps(value, default=repr)}")


def fold_table(source: Mapping[str, str]) -> Mapping[int, str]:
    """A character → replacement mapping, as a code-point table."""
    return {ord(ch): to for ch, to in source.items()}


def transform(s: str, replace: Mapping[int, str]) -> str:
    """Rebuild a string by code point: a key found in `replace` is substituted, a miss keeps the character.

    The iteration is code-point-exact: a surrogate pair is one character and an unpaired surrogate
    is its own. `replace` maps to `''` to delete a character or to a replacement.
    """
    return canon(s.translate(replace))
