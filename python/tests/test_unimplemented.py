"""Inputs whose exact JS behaviour cannot be reproduced stop loudly instead of guessing."""

import pytest

from luraty_engine import create_pack

CONFIG = {"id": "x", "tokenize": {"strategy": "regex", "pattern": "[a]+"}, "normalize": [], "compare": []}


@pytest.mark.parametrize("pattern", ["[\\p{L}]+", "[\\P{Script=Arabic}]+", "[a\\p{Lu}]+"])
def test_unicode_property_escape_raises(pattern):
    with pytest.raises(NotImplementedError):
        create_pack({**CONFIG, "tokenize": {"strategy": "regex", "pattern": pattern}}, {"frequency": ""})


def test_prefixes_with_an_inconsistent_comparator_raise():
    with pytest.raises(NotImplementedError):
        create_pack({**CONFIG, "affixes": {"prefixes": ["ab", 5, "abc"]}}, {"frequency": ""})
