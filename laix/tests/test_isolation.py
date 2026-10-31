"""Isolation guards for the portable LAIX package.

Two independent checks:

1. no forbidden imports (host application, web framework, database, numerics);
2. no executable GeoResponse domain nouns, ignoring docstrings, comments and a
   short, explicit exception list.

The tests also run the scanners against a synthetic bad package, so a guard that
silently stopped detecting anything would fail.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

import laix

ROOT = Path(laix.__file__).resolve().parent
FORBIDDEN_MODULES = {"georesponse", "fastapi", "sqlite3", "numpy"}
DOMAIN_NOUNS = ("georesponse", "alert", "imagery", "analyst", "sla", "satellite")

# ``sla_breached`` is a portable policy attribute consumed by the adapter, and
# the rationale string is part of the frozen decision output.  Both are allowed
# by name; no other executable domain noun is.
EXECUTABLE_EXCEPTIONS = {
    ("policy.py", "sla_breached"),
    ("policy.py", "a hard deadline or SLA is already breached"),
}


def _python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.parts:
            continue
        yield path


def forbidden_imports(root: Path) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for path in _python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in FORBIDDEN_MODULES:
                        hits.append({"file": path.name, "line": node.lineno, "module": module})
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in FORBIDDEN_MODULES:
                    hits.append({"file": path.name, "line": node.lineno, "module": module})
    return hits


def _docstrings(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _matches(token: str) -> bool:
    lowered = token.lower()
    return any(noun in lowered for noun in DOMAIN_NOUNS)


def domain_noun_hits(root: Path) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for path in _python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            token: str | None = None
            if isinstance(node, ast.Name):
                token = node.id
            elif isinstance(node, ast.Attribute):
                token = node.attr
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                token = node.name
            elif isinstance(node, ast.arg):
                token = node.arg
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                token = node.value
            if token is None or not _matches(token):
                continue
            if (path.name, token) in EXECUTABLE_EXCEPTIONS:
                continue
            hits.append({"file": path.name, "line": getattr(node, "lineno", 0), "token": token})
    return hits


def test_package_has_no_forbidden_imports() -> None:
    assert forbidden_imports(ROOT) == []


def test_import_guard_detects_each_forbidden_module(tmp_path: Path) -> None:
    package = tmp_path / "laix"
    package.mkdir()
    (package / "bad.py").write_text(
        "import fastapi\nimport sqlite3\nimport numpy\nfrom georesponse import Scope\n",
        encoding="utf-8",
    )
    modules = {hit["module"] for hit in forbidden_imports(package)}
    assert modules == {"fastapi", "sqlite3", "numpy", "georesponse"}


def test_package_has_no_executable_domain_nouns() -> None:
    assert domain_noun_hits(ROOT) == []


def test_domain_noun_guard_detects_a_leak(tmp_path: Path) -> None:
    package = tmp_path / "laix"
    package.mkdir()
    (package / "bad.py").write_text("alert_count = 1\nimagery_path = 'x'\n", encoding="utf-8")
    tokens = {hit["token"] for hit in domain_noun_hits(package)}
    assert {"alert_count", "imagery_path"}.issubset(tokens)


def test_domain_noun_guard_ignores_docstrings_and_comments(tmp_path: Path) -> None:
    package = tmp_path / "laix"
    package.mkdir()
    (package / "ok.py").write_text(
        '"""Alert imagery for an analyst; SLA and satellite are documented here."""\n'
        "# alert imagery analyst sla satellite\n"
        "value = 1\n",
        encoding="utf-8",
    )
    assert domain_noun_hits(package) == []


def test_adapter_is_not_inside_the_portable_package() -> None:
    assert not (ROOT / "georesponse").exists()
    assert not (ROOT / "laix_adapter").exists()
