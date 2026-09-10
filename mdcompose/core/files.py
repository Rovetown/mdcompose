"""Reading and writing text files: encoding, byte order marks, line endings.

Two rules in here carry most of the weight elsewhere in mdcompose.

Comparison is normalization-aware. Content that differs only by a byte order
mark or by line ending convention is the same content, so a file checked out
with CRLF on Windows and with LF under WSL hashes identically. Without that, a
committed manifest would report drift on a file nobody touched.

Writing preserves a file's existing line endings. Rewriting a CRLF file as LF
would make git report every line as changed. That is only safe because
comparison normalizes, so preserving CRLF cannot itself cause drift. The two
decisions hold each other up.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from mdcompose.core.exit_codes import AttentionError

LF = "\n"
CRLF = "\r\n"
BOM = "\ufeff"

#: The largest file mdcompose will read into memory. Every file it handles is a
#: markdown config document, kilobytes at most; anything past this is a mistake
#: or a hostile input, and refusing it is better than an out-of-memory kill.
MAX_READ_BYTES = 16 * 1024 * 1024


def read_text(path: Path) -> str:
    """Return the file's text with any byte order mark removed.

    Line endings are returned exactly as stored, so a caller can write the file
    back in its original convention. Use :func:`normalize` before comparing.

    Raises ``AttentionError`` if the file is missing, larger than
    :data:`MAX_READ_BYTES`, unreadable, or not valid UTF-8. Invalid bytes are
    never replaced with substitution characters, because hashing corrupted
    content is worse than refusing to read it.
    """
    if not path.is_file():
        raise AttentionError(f"{path}: not a readable file")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AttentionError(f"{path}: cannot be read ({exc.strerror})") from exc
    if size > MAX_READ_BYTES:
        raise AttentionError(
            f"{path}: {size} bytes is past the {MAX_READ_BYTES}-byte limit; "
            "mdcompose reads text config files, not files this size"
        )
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AttentionError(f"{path}: cannot be read ({exc.strerror})") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AttentionError(
            f"{path}: unsupported encoding, mdcompose reads UTF-8 only "
            f"(invalid byte at offset {exc.start})"
        ) from exc
    return strip_bom(text)


def strip_bom(text: str) -> str:
    """Return text without a leading byte order mark."""
    if text.startswith(BOM):
        return text[len(BOM) :]
    return text


def normalize(text: str) -> str:
    """Return the canonical form of text used for comparison and hashing.

    Strips a leading byte order mark and converts every line ending to LF. A
    difference in trailing blank lines is a real difference and survives.
    """
    return strip_bom(text).replace(CRLF, LF).replace("\r", LF)


def content_equal(left: str, right: str) -> bool:
    """Return whether two pieces of content are equal under normalization."""
    return normalize(left) == normalize(right)


def hash_content(text: str) -> str:
    """Return the hex SHA-256 of text in its normalized form.

    Because the input is normalized first, the same content produces the same
    hash on every platform, which is what allows a hash to be committed.
    """
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def detect_line_ending(text: str) -> str:
    """Return the dominant line ending in text, LF or CRLF.

    A file mixing both conventions has no correct answer, so the more frequent
    wins and a tie resolves to LF.
    """
    crlf_count = text.count(CRLF)
    lone_lf_count = text.count(LF) - crlf_count
    if crlf_count > lone_lf_count:
        return CRLF
    return LF


def line_ending_for(path: Path) -> str:
    """Return the line ending to use when writing path.

    An existing file keeps its own convention. A new file gets LF.
    """
    if path.is_file():
        return detect_line_ending(read_text(path))
    return LF


def write_text(path: Path, text: str, *, line_ending: str = LF) -> None:
    """Write text to path as UTF-8 with no byte order mark, atomically.

    The bytes go to a scratch file in the same directory and are then renamed
    over the target, so an interrupted write leaves the previous file intact
    rather than a truncated one, and no reader ever sees a half-written file.
    A byte order mark is never written, including when the file being replaced
    had one. When the target is a symlink the link is replaced by a real file
    rather than followed, so a write cannot escape the directory it names.
    """
    body = normalize(text)
    if line_ending == CRLF:
        body = body.replace(LF, CRLF)
    scratch = path.with_name(f".{path.name}.mdcompose-{os.getpid()}")
    try:
        scratch.write_bytes(body.encode("utf-8"))
        scratch.replace(path)
    except OSError as exc:
        scratch.unlink(missing_ok=True)
        raise AttentionError(f"{path}: cannot be written ({exc.strerror})") from exc


def write_if_changed(path: Path, text: str) -> bool:
    """Write text to path only if it differs from what is already there.

    Returns whether anything was written. An existing file keeps its own line
    ending convention. Comparison is normalization-aware, so rewriting the same
    content into a CRLF file is correctly detected as no change.
    """
    line_ending = LF
    if path.is_file():
        existing = read_text(path)
        line_ending = detect_line_ending(existing)
        if content_equal(existing, text):
            return False
    write_text(path, text, line_ending=line_ending)
    return True


def path_exists(path: Path) -> bool:
    """Return whether path exists, treating any failure to find out as absent.

    ``Path.exists`` is not consistent across the Python versions this project
    supports. On 3.13 and later it delegates to ``os.path.exists``, which
    swallows every OSError. On 3.11 and 3.12 it re-raises anything other than a
    small set of errno values, so a directory the user cannot stat raises
    ``PermissionError`` instead of answering the question.

    A tool whose job is reporting on paths must not fail because one path is
    unreadable, and the answer a caller needs is the same either way: mdcompose
    cannot see it, so it is reported as absent. Deciding here rather than
    relying on the standard library makes the behavior identical on every
    supported version.
    """
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def normalized_path(path: Path) -> str:
    """Return path in the form two references to the same file always share.

    Case-folded and fully resolved, falling back to an absolute but unresolved
    path when the target cannot be resolved. For comparing two paths, never for
    storing one.
    """
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return os.path.normcase(str(resolved))
