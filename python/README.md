# luraty-engine (Python)

Python port of [`@luraty/engine`](../README.md): the learner model, language packs and coverage.
Scheduling uses [FSRS](https://pypi.org/project/fsrs/); it is the only dependency.

```bash
pip install "luraty-engine @ git+https://github.com/Luraty/engine@<tag-or-sha>#subdirectory=python"
```

```python
from luraty_engine import create_profile, instant

profile = create_profile("ar", instant(0))
```

## Develop

```bash
cd python
uv sync
uv run pytest
```

`tests/parity/` holds fixtures generated from the TypeScript package; `tests/test_parity.py`
asserts the port matches them.
