"""Fail if any file mdcompose authors or generates contains a non-ASCII character.

The rule is not stylistic. A Windows console on a cp1252 or cp437 code page
cannot encode an em dash, an en dash, a smart quote, an arrow, an ellipsis, a
non-breaking space, or an emoji, so emitting one raises an encoding error on a
primary target platform. Emoji also break column alignment through ambiguous
width. Any code point above U+007F is rejected, so this covers all of the above.

CI and a pre-commit hook both run this. The hook passes the staged files as
arguments; CI runs it with none and it scans every tracked text file.

    uv run python scripts/check_ascii.py            # every tracked text file
    uv run python scripts/check_ascii.py a.py b.md  # just these

Not scanned: binary files, lockfiles (`.lock`, a tool artifact full of hashes),
and the test fixtures that deliberately carry specific bytes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "fixtures", "runtime-env"}
SKIP_SUFFIXES = {".lock"}


def tracked_files() -> list[Path]:
    """Every tracked file, via git so no venv, cache, or build output is walked."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(name) for name in completed.stdout.split("\0") if name]


def is_authored(path: Path) -> bool:
    """True if this is a file whose characters mdcompose is responsible for."""
    if SKIP_DIRS & set(path.parts):
        return False
    return path.suffix not in SKIP_SUFFIXES


def text_of(raw: bytes) -> str | None:
    """Decode a file, or None if it is binary."""
    if b"\0" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def non_ascii(text: str) -> list[str]:
    """The sorted distinct code points above U+007F in the text, as ``U+XXXX``."""
    return sorted({f"U+{ord(char):04X}" for char in text if ord(char) > 127})


def main(argv: list[str]) -> int:
    candidates = [Path(argument) for argument in argv] if argv else tracked_files()

    offenders = []
    for path in candidates:
        if not path.is_file() or not is_authored(path):
            continue
        text = text_of(path.read_bytes())
        if text is None:
            continue
        found = non_ascii(text)
        if found:
            offenders.append(f"{path.as_posix()}: {' '.join(found)}")

    if offenders:
        print("non-ASCII characters in authored or generated files:")
        for line in sorted(offenders):
            print("  " + line)
        return 1
    print(f"{len(candidates)} paths checked, all plain ASCII")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
