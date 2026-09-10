"""The package name and the installed version.

These sit here rather than in ``cli.py`` so a command module can build a
manifest's ``generated_by`` string without importing the CLI adapter. ``cli.py``
imports every command module to register it, so the reverse edge closes an
import cycle, which CodeQL's ``py/cyclic-import`` flags even when the import is
deferred into a function body.
"""

from __future__ import annotations

from importlib import metadata

PACKAGE_NAME = "mdcompose"


def resolve_version() -> str:
    """Return the installed version, the same string recorded in a manifest.

    Falls back to a marker rather than raising when package metadata is
    unavailable, which happens only in a source tree that was never installed.
    """
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0+unknown"


def generated_by() -> str:
    """The ``generated_by`` value a manifest records: the name and the version."""
    return f"{PACKAGE_NAME} {resolve_version()}"
