"""The engine's dependency boundary, in Python terms."""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
BANNED_FRAMEWORKS = {"fastapi", "flask", "django", "starlette", "sqlalchemy", "supabase", "requests", "httpx"}


def imports_of(package):
    for path in (SRC / package).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield path, alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                yield path, node.module.split(".")[0]


# FSRS is the engine's memory model, used through its reference implementation, and the one
# third-party import the engine has. It is pure Python with no dependencies of its own.
THIRD_PARTY = {"fsrs"}


def test_engine_imports_only_the_stdlib_and_fsrs():
    for path, top in imports_of("luraty_engine"):
        assert top in sys.stdlib_module_names or top in {"luraty_engine"} | THIRD_PARTY, (path, top)


def test_only_the_memory_model_imports_fsrs():
    for path, top in imports_of("luraty_engine"):
        if top == "fsrs":
            assert path.name == "memory.py", path


def test_declares_no_framework_or_database_dependency():
    for path, top in imports_of("luraty_engine"):
        assert top not in BANNED_FRAMEWORKS, path
