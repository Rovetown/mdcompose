"""The boundary between the core layer and the CLI layer.

Core behavior is meant to be documented as a contract independent of Python and
of Typer, so a future port reimplements a specification rather than translating
this code. That is only true while core knows nothing about the CLI.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

import mdcompose.core

CORE_ROOT = Path(mdcompose.core.__file__).parent
CORE_MODULES = sorted(module.name for module in pkgutil.iter_modules([str(CORE_ROOT)]))


def imported_names(source: Path) -> set[str]:
    """Return every module name the file imports, however it imports it."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_the_core_layer_has_modules_to_check() -> None:
    assert CORE_MODULES, "expected core modules to be discoverable"


@pytest.mark.parametrize("name", CORE_MODULES)
def test_every_core_module_imports_cleanly(name: str) -> None:
    assert importlib.import_module(f"mdcompose.core.{name}") is not None


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_never_imports_the_cli(name: str) -> None:
    imports = imported_names(CORE_ROOT / f"{name}.py")
    assert not any(module.startswith("mdcompose.cli") for module in imports)


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_never_imports_the_cli_framework(name: str) -> None:
    """Typer and Click belong to the adapter, not to the behavior being specified."""
    imports = imported_names(CORE_ROOT / f"{name}.py")
    forbidden = {module.split(".")[0] for module in imports} & {"typer", "click", "rich"}
    assert not forbidden, f"mdcompose.core.{name} imports {sorted(forbidden)}"


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_uses_absolute_imports(name: str) -> None:
    tree = ast.parse((CORE_ROOT / f"{name}.py").read_text(encoding="utf-8"))
    relative = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level and node.level > 0
    ]
    assert not relative
