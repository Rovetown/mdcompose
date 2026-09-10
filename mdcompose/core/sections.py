"""Heading-based section extraction from a markdown file.

`import` and `convert` both need to take an existing CLAUDE.md or AGENTS.md apart
along its headings, offer the pieces for selection, and reassemble the chosen
ones without altering a byte. A section is a heading and everything under it down
to the next heading of the same or higher level, so a nested subsection travels
with its parent, and every heading level is offered so a subsection can also be
taken on its own.

The scan is line-based and fence-aware, the same shape as the managed block
marker scan in ``managed_block``: a ``#`` inside a fenced code block is example
text, not a heading, because these files routinely contain fenced markdown.

Content is never transformed. Every ``Section.content`` is a verbatim slice of
the normalized source, and the slices that are contained in no other section
tile the file exactly, which is what lets an extract-and-reassemble round trip
reproduce the source.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from mdcompose.core import files

#: An ATX heading: up to three leading spaces, one to six hashes, then either a
#: space and the text or nothing. A run of trailing hashes is a closing sequence,
#: not part of the text.
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?: +(.*?)\s*|\s*)$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_CLOSING_HASHES = re.compile(r"\s+#+\s*$")


@dataclass(frozen=True, slots=True)
class Section:
    """One heading's worth of a file, or a synthetic section for headingless text.

    ``level`` is 1 to 6 for a real heading and 0 for a synthetic section: the
    text before the first heading, or the whole of a file that has no headings.
    ``start_line`` and ``end_line`` are 1-based and inclusive. ``content`` is a
    verbatim slice of the normalized source, heading line included.
    """

    heading: str
    level: int
    content: str
    start_line: int
    end_line: int
    synthetic: bool = False

    def contains(self, other: Section) -> bool:
        """Whether this section wholly encloses another, distinct section."""
        return (
            self != other
            and self.start_line <= other.start_line
            and self.end_line >= other.end_line
        )


class _Fence:
    """Tracks whether the scanner is inside a fenced code block.

    Mirrors ``managed_block._FenceState``: a fence closes only on a fence of the
    same character, at least as long, with no info string.
    """

    __slots__ = ("_character", "_length")

    def __init__(self) -> None:
        self._character = ""
        self._length = 0

    @property
    def is_open(self) -> bool:
        return self._length > 0

    def consume(self, line: str) -> bool:
        """Feed one line; return whether the scanner should skip it."""
        match = _FENCE.match(line)
        if match is None:
            return self.is_open
        fence = match.group(1)
        if not self.is_open:
            self._character = fence[0]
            self._length = len(fence)
            return True
        closes = (
            fence[0] == self._character
            and len(fence) >= self._length
            and not match.group(2).strip()
        )
        if closes:
            self._character = ""
            self._length = 0
        return True


@dataclass(frozen=True, slots=True)
class _Heading:
    line: int
    level: int
    text: str


def parse_sections(text: str, *, source_name: str) -> tuple[Section, ...]:
    """Break a markdown file into every section it offers, in document order.

    Sections are returned at every heading level, so a parent is followed by its
    children. Text before the first heading, or a whole file with no headings, is
    returned as one synthetic section named for the source.
    """
    normalized = files.normalize(text)
    if not normalized:
        return ()
    lines = normalized.split("\n")
    offsets = _line_offsets(lines)
    headings = _scan_headings(lines)

    if not headings:
        return (Section(source_name, 0, normalized, 1, len(lines), synthetic=True),)

    result: list[Section] = []
    first = headings[0].line
    if first > 1:
        result.append(
            Section(source_name, 0, _slice(normalized, offsets, 1, first - 1), 1, first - 1, True)
        )
    for index, heading in enumerate(headings):
        end = _section_end(headings, index, len(lines))
        result.append(
            Section(
                heading.text,
                heading.level,
                _slice(normalized, offsets, heading.line, end),
                heading.line,
                end,
            )
        )
    return tuple(result)


def maximal(candidates: Sequence[Section]) -> tuple[Section, ...]:
    """Return the sections contained in no other section, in source order.

    These tile the file: concatenating their content reproduces the source.
    """
    ordered = sorted(candidates, key=lambda section: section.start_line)
    return tuple(
        section for section in ordered if not any(other.contains(section) for other in ordered)
    )


def extract(selection: Sequence[Section]) -> str:
    """Concatenate the selected sections in source order.

    A section wholly contained in another selected section is dropped, so
    selecting a parent and one of its children applies the content once.
    """
    unique: list[Section] = []
    for section in selection:
        if section not in unique:
            unique.append(section)
    kept = [
        section for section in unique if not any(other.contains(section) for other in unique)
    ]
    kept.sort(key=lambda section: section.start_line)
    return "".join(section.content for section in kept)


def filter_by_keyword(candidates: Sequence[Section], keyword: str) -> tuple[Section, ...]:
    """Return the sections whose heading or content contains the keyword.

    Matching is case-insensitive. A parent surfaces automatically when only its
    child matches, because a parent's content includes its children.
    """
    needle = keyword.casefold()
    return tuple(section for section in candidates if needle in section.content.casefold())


def _line_offsets(lines: Sequence[str]) -> list[int]:
    """Character index where each line starts, plus one past the end."""
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    return offsets


def _slice(text: str, offsets: Sequence[int], start_line: int, end_line: int) -> str:
    """The verbatim text of lines ``start_line`` to ``end_line``, 1-based inclusive."""
    return text[offsets[start_line - 1] : min(offsets[end_line], len(text))]


def _scan_headings(lines: Sequence[str]) -> list[_Heading]:
    fence = _Fence()
    headings: list[_Heading] = []
    for number, line in enumerate(lines, start=1):
        if fence.consume(line):
            continue
        match = _HEADING.match(line)
        if match is None:
            continue
        text = _CLOSING_HASHES.sub("", match.group(2) or "").strip()
        headings.append(_Heading(number, len(match.group(1)), text))
    return headings


def _section_end(headings: Sequence[_Heading], index: int, last_line: int) -> int:
    """The last line of the section that opens at ``headings[index]``."""
    level = headings[index].level
    for following in headings[index + 1 :]:
        if following.level <= level:
            return following.line - 1
    return last_line
