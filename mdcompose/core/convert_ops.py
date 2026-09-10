"""Moving unmanaged content between a project's AGENTS.md and CLAUDE.md.

`convert` is the mirror of `import`: `import` brings a file's sections in from
outside, `convert` moves them between the two files this project already has.
Both work only with content outside managed blocks. `init` owns the blocks;
`convert` owns the regions around them, and the two never write the same bytes.

A conversion is planned in full before anything is written: the source with the
moved sections removed, and the target with them appended. The target is written
first so a failure there leaves the source whole rather than losing content that
now lives nowhere.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from mdcompose.core import composition, files, import_ops, managed_block, sections
from mdcompose.core.config import Mode
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.sections import Section


@dataclass(frozen=True, slots=True)
class ConversionPlan:
    """Everything a conversion would do, worked out before a byte is written."""

    source_path: Path
    target_path: Path
    moved: tuple[Section, ...]
    source_before: str
    source_after: str
    target_before: str
    target_after: str
    new_block_mode: Mode | None = None

    @property
    def is_empty(self) -> bool:
        return not self.moved


def unmanaged_sections(text: str, source_path: Path) -> tuple[Section, ...]:
    """The source's sections that lie outside every managed block.

    A managed block is a hard boundary: it is never read as content, and a
    section never spans one. Raises ``AttentionError`` on malformed markers.
    """
    normalized = files.normalize(text)
    blocks = managed_block.parse(normalized, source_path)
    block_lines: set[int] = set()
    for block in blocks:
        block_lines.update(range(block.start_line, block.end_line + 1))

    lines = normalized.split("\n")
    offsets = _line_offsets(lines)
    result: list[Section] = []
    for first, last in _unmanaged_segments(len(lines), block_lines):
        segment = normalized[offsets[first - 1] : min(offsets[last], len(normalized))]
        for section in sections.parse_sections(segment, source_name=source_path.name):
            # A trailing blank line in the segment text can push parse_sections'
            # last section one line past the segment. Clamp so a removal can
            # never reach into the managed block that follows.
            result.append(
                replace(
                    section,
                    start_line=min(section.start_line + first - 1, last),
                    end_line=min(section.end_line + first - 1, last),
                )
            )
    return tuple(result)


def plan_conversion(
    source_path: Path,
    target_path: Path,
    *,
    moved: Sequence[Section],
    source_text: str,
    target_text: str,
    new_block_mode: Mode | None = None,
) -> ConversionPlan:
    """Build the plan: source with ``moved`` removed, target with it appended.

    When ``new_block_mode`` is set the target is a CLAUDE.md with no managed
    block, so one is created in that mode before the moved content is appended
    after it, in the user-owned region.
    """
    normalized_source = files.normalize(source_text)
    content = sections.extract(moved)
    target_base = files.normalize(target_text)
    if new_block_mode is not None:
        block_content = ""
        if new_block_mode == composition.IMPORT:
            block_content = composition.import_directive("AGENTS.md")
        target_base = managed_block.upsert(
            target_base, managed_block.CLAUDE_MANAGED_BLOCK, block_content, target_path
        )
    return ConversionPlan(
        source_path=source_path,
        target_path=target_path,
        moved=tuple(moved),
        source_before=normalized_source,
        source_after=_remove_sections(normalized_source, moved),
        target_before=files.normalize(target_text),
        target_after=import_ops.appended(target_base, content),
        new_block_mode=new_block_mode,
    )


def render_diff(plan: ConversionPlan) -> str:
    """A unified diff of every change the conversion would make to both files.

    Both sides are shown: the moved content leaving the source, and the same
    content arriving in the target. This is what a user confirms against, and
    what a scripted run prints so the change is on the record.
    """
    parts = [
        _file_diff(plan.source_path.name, plan.source_before, plan.source_after),
        _file_diff(plan.target_path.name, plan.target_before, plan.target_after),
    ]
    return "\n\n".join(part for part in parts if part)


def _file_diff(name: str, before: str, after: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), fromfile=name, tofile=name, lineterm=""
    )
    return "\n".join(lines)


def apply_conversion(plan: ConversionPlan) -> None:
    """Write the target, then remove from the source.

    Target first: if that write fails the source is untouched, so the content is
    never lost, only un-moved.
    """
    if plan.is_empty:
        return
    files.write_text(
        plan.target_path, plan.target_after, line_ending=files.line_ending_for(plan.target_path)
    )
    files.write_text(
        plan.source_path, plan.source_after, line_ending=files.line_ending_for(plan.source_path)
    )


def _remove_sections(text: str, moved: Sequence[Section]) -> str:
    """Return text with each moved section's lines gone, seams tidied.

    Managed block lines are never in a section's range, so a block is untouched.
    """
    if not moved:
        return text
    lines = text.split("\n")
    drop: set[int] = set()
    for section in moved:
        drop.update(range(section.start_line, section.end_line + 1))
    kept = [line for number, line in enumerate(lines, start=1) if number not in drop]
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip("\n")
    return f"{collapsed}\n" if collapsed else collapsed


def _unmanaged_segments(line_count: int, block_lines: set[int]) -> list[tuple[int, int]]:
    """Contiguous 1-based line ranges that hold no managed block line."""
    segments: list[tuple[int, int]] = []
    current: tuple[int, int] | None = None
    for number in range(1, line_count + 1):
        if number in block_lines:
            if current is not None:
                segments.append(current)
                current = None
            continue
        current = (current[0], number) if current is not None else (number, number)
    if current is not None:
        segments.append(current)
    return segments


def _line_offsets(lines: Sequence[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    return offsets


def require_different(source_path: Path, target_path: Path) -> None:
    """Refuse a conversion whose source and target are the same file."""
    if files.normalized_path(source_path) == files.normalized_path(target_path):
        raise AttentionError("convert needs a different source and target, not the same file")
