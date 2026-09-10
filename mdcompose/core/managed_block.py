"""The managed block: the region of a file mdcompose owns exclusively.

Everything outside a managed block belongs to the user and is never touched.
Everything inside it is mdcompose's to rewrite. That single rule is what makes
it safe to regenerate a file the user also edits by hand.

The marker format is a compatibility surface. Once a user's files contain
managed blocks, changing the markers would orphan every block already written,
and mdcompose would silently treat a previously-managed region as user text.
Treat the constants below as frozen. The one change still allowed was made here
before any release: the prefix was ``agentsmd`` while the project carried that
name, and was aligned to ``mdcompose`` while nothing on disk depended on it.

Two entry points exist on purpose. :func:`scan` never raises and reports a
malformed file as data, which is what lets a reporting command list one bad file
alongside several good ones. :func:`parse` raises instead, which is what a write
path wants, because writing into a file whose boundaries cannot be determined
risks destroying user content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mdcompose.core import files
from mdcompose.core.exit_codes import AttentionError

# Block ids used by the files mdcompose manages. The composition change is what
# specifies these; they are named here because drift detection has to know which
# block belongs to which file, and that arrives first.
AGENTS_COMPOSITION_BLOCK = "agents-composition"
CLAUDE_MANAGED_BLOCK = "claude-managed"

MARKER_PREFIX = "mdcompose"

_MARKER_PATTERN = re.compile(
    r"^<!--\s*" + MARKER_PREFIX + r":(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*):(?P<kind>start|end)\s*-->$"
)
_FENCE_PATTERN = re.compile(r"^(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

ProblemKind = Literal["unmatched-start", "unmatched-end", "duplicate-id", "nested"]


def start_marker(block_id: str) -> str:
    """Return the exact start marker line for a block id."""
    return f"<!-- {MARKER_PREFIX}:{block_id}:start -->"


def end_marker(block_id: str) -> str:
    """Return the exact end marker line for a block id."""
    return f"<!-- {MARKER_PREFIX}:{block_id}:end -->"


@dataclass(frozen=True, slots=True)
class ManagedBlock:
    """One recognized block, with its content and where its markers sit.

    Line numbers are 1-based and refer to the marker lines themselves, so an
    error message can point a user at the line they need to look at.
    """

    block_id: str
    start_line: int
    end_line: int
    content: str

    @property
    def content_hash(self) -> str:
        """The hash of this block's content, normalized.

        Covers the content only, never the marker lines or anything outside
        them, so an edit elsewhere in the file cannot change it.
        """
        return files.hash_content(self.content)


@dataclass(frozen=True, slots=True)
class BlockProblem:
    """A malformed marker arrangement, described well enough to act on."""

    kind: ProblemKind
    message: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What a scan found: either every block, or the problem that stopped it."""

    blocks: tuple[ManagedBlock, ...]
    problem: BlockProblem | None

    @property
    def is_well_formed(self) -> bool:
        return self.problem is None

    def find(self, block_id: str) -> ManagedBlock | None:
        """Return the block with this id, or None when the file has no such block."""
        for block in self.blocks:
            if block.block_id == block_id:
                return block
        return None


class _FenceState:
    """Tracks whether the scanner is inside a fenced code block.

    A marker quoted inside a code fence is documentation, not a marker. Without
    this, anyone who writes about the marker format in their own AGENTS.md, this
    project's own documentation included, would have their file reported as
    malformed. The fence is closed only by a fence of the same character that is
    at least as long and carries no info string, which is what the markdown
    specification requires.
    """

    __slots__ = ("_character", "_length")

    def __init__(self) -> None:
        self._character = ""
        self._length = 0

    @property
    def is_open(self) -> bool:
        return self._length > 0

    def consume(self, stripped_line: str) -> bool:
        """Feed one line, and return whether the scanner should skip it."""
        match = _FENCE_PATTERN.match(stripped_line)
        if match is None:
            return self.is_open
        fence = match.group("fence")
        if not self.is_open:
            self._character = fence[0]
            self._length = len(fence)
            return True
        closes = (
            fence[0] == self._character
            and len(fence) >= self._length
            and not match.group("info").strip()
        )
        if closes:
            self._character = ""
            self._length = 0
        return True


def scan(text: str) -> ScanResult:
    """Find every managed block in text without raising.

    Stops at the first malformed arrangement and reports it, because once the
    markers stop making sense there is nothing trustworthy left to find.

    Lines inside a fenced code block are skipped: a marker quoted as an example
    is documentation, not a marker.
    """
    blocks: list[ManagedBlock] = []
    seen_start_lines: dict[str, int] = {}
    open_id: str | None = None
    open_line = 0
    content_start = 0
    lines = text.splitlines()
    fence = _FenceState()

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if fence.consume(stripped):
            continue
        marker = _MARKER_PATTERN.match(stripped)
        if marker is None:
            continue
        block_id = marker.group("id")
        if marker.group("kind") == "start":
            problem = _problem_for_start(block_id, index, open_id, open_line, seen_start_lines)
            if problem is not None:
                return ScanResult(blocks=tuple(blocks), problem=problem)
            open_id = block_id
            open_line = index
            content_start = index
            continue

        if open_id != block_id:
            return ScanResult(
                blocks=tuple(blocks),
                problem=BlockProblem(
                    kind="unmatched-end",
                    message=(
                        f"end marker for block '{block_id}' on line {index} has no "
                        "matching start marker before it"
                    ),
                ),
            )
        blocks.append(
            ManagedBlock(
                block_id=block_id,
                start_line=open_line,
                end_line=index,
                content=_join(lines[content_start : index - 1]),
            )
        )
        seen_start_lines[block_id] = open_line
        open_id = None

    if open_id is not None:
        return ScanResult(
            blocks=tuple(blocks),
            problem=BlockProblem(
                kind="unmatched-start",
                message=(
                    f"start marker for block '{open_id}' on line {open_line} has no "
                    "matching end marker"
                ),
            ),
        )
    return ScanResult(blocks=tuple(blocks), problem=None)


def _problem_for_start(
    block_id: str,
    line: int,
    open_id: str | None,
    open_line: int,
    seen_start_lines: dict[str, int],
) -> BlockProblem | None:
    """Decide whether a start marker is legal where it appears."""
    if open_id is not None and open_id != block_id:
        return BlockProblem(
            kind="nested",
            message=(
                f"block '{block_id}' starting on line {line} is nested inside block "
                f"'{open_id}' starting on line {open_line}; managed blocks cannot nest"
            ),
        )
    if open_id == block_id:
        return BlockProblem(
            kind="duplicate-id",
            message=(
                f"block '{block_id}' starts again on line {line} while the block "
                f"started on line {open_line} is still open"
            ),
        )
    if block_id in seen_start_lines:
        return BlockProblem(
            kind="duplicate-id",
            message=(
                f"block '{block_id}' appears twice, starting on line "
                f"{seen_start_lines[block_id]} and again on line {line}"
            ),
        )
    return None


def _join(content_lines: list[str]) -> str:
    """Rebuild block content from its lines.

    Content is joined with line feeds regardless of how the file stored them.
    Comparison and hashing normalize anyway, and a write path re-applies the
    file's own convention, so nothing downstream depends on the original bytes.
    """
    if not content_lines:
        return ""
    return "\n".join(content_lines) + "\n"


def parse(text: str, source: Path) -> tuple[ManagedBlock, ...]:
    """Find every managed block, refusing a file whose markers are malformed.

    Raises ``AttentionError`` naming the file and the problem. A caller that
    needs to keep going, such as a command reporting on several files at once,
    should use :func:`scan` instead.
    """
    result = scan(text)
    if result.problem is not None:
        raise AttentionError(f"{source}: {result.problem.message}")
    return result.blocks


def read_blocks(path: Path) -> ScanResult:
    """Read a file and scan it for managed blocks, without raising on markers.

    Encoding problems still raise, because a file that cannot be decoded has no
    lines to scan in the first place.
    """
    return scan(files.read_text(path))


def upsert(text: str, block_id: str, content: str, source: Path) -> str:
    """Return text with the named block holding new content.

    Replaces the block's content when the block exists, and appends a new block
    at the end when it does not. Every byte outside the block is preserved,
    including in a file that existed long before mdcompose ran, which is the
    guarantee the whole managed block idea exists to provide.

    Refuses a file whose markers are malformed. There is no safe way to write
    into a file whose boundaries cannot be determined, so this raises rather
    than guessing.
    """
    blocks = parse(text, source)
    existing = next((block for block in blocks if block.block_id == block_id), None)
    if existing is None:
        return _append_block(text, block_id, content)
    return _replace_block(text, existing, content)


def _replace_block(text: str, block: ManagedBlock, content: str) -> str:
    """Swap one block's content, leaving both marker lines where they are."""
    lines = files.normalize(text).split("\n")
    before = lines[: block.start_line]
    after = lines[block.end_line - 1 :]
    return "\n".join([*before, *_content_lines(content), *after])


def _append_block(text: str, block_id: str, content: str) -> str:
    """Add a new block at the end, separated from existing content by one blank line."""
    body = files.normalize(text)
    prefix = "" if not body.strip() else body.rstrip("\n") + "\n\n"
    block = "\n".join(
        [start_marker(block_id), *_content_lines(content), end_marker(block_id)]
    )
    return f"{prefix}{block}\n"


def _content_lines(content: str) -> list[str]:
    """Split block content into the lines that sit between the markers."""
    normalized = files.normalize(content)
    if not normalized.strip():
        return []
    return normalized.rstrip("\n").split("\n")


def remove(text: str, block_id: str, source: Path, *, keep_content: bool) -> str:
    """Return text with the named block's markers removed.

    With ``keep_content`` the content stays behind as plain markdown, so the file
    still serves whatever reads it. Without it, the content goes too.

    The blank lines the markers occupied are collapsed, so removing a block twice
    changes nothing the second time and the result reads as hand-written rather
    than processed.
    """
    blocks = parse(text, source)
    block = next((item for item in blocks if item.block_id == block_id), None)
    if block is None:
        return files.normalize(text)

    lines = files.normalize(text).split("\n")
    kept = _content_lines(block.content) if keep_content else []
    rebuilt = [*lines[: block.start_line - 1], *kept, *lines[block.end_line :]]
    return _collapse_blank_runs(rebuilt, block.start_line - 1)


def without_managed_blocks(text: str, source: Path) -> str:
    """Return text with every managed block removed, markers and content both.

    Raises ``AttentionError`` when the markers are malformed: a file whose
    boundaries cannot be read cannot have its blocks taken out safely. Used by
    ``import`` and ``convert``, which work only with the user's own content and
    never with what a managed block holds.
    """
    result = files.normalize(text)
    for block in parse(result, source):
        result = remove(result, block.block_id, source, keep_content=False)
    return result


def _collapse_blank_runs(lines: list[str], seam: int) -> str:
    """Collapse a run of blank lines at the seam left by removed markers."""
    start = seam
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    end = seam
    while end < len(lines) and not lines[end].strip():
        end += 1
    if end > start:
        separator = [] if start == 0 or end >= len(lines) else [""]
        lines = [*lines[:start], *separator, *lines[end:]]
    text = "\n".join(lines).rstrip("\n")
    return "" if not text else text + "\n"
