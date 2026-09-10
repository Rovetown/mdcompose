"""Turning a snippet selection into the content of AGENTS.md and CLAUDE.md.

Mode is a property of CLAUDE.md alone. AGENTS.md is byte-identical whichever mode
a project uses, because AGENTS.md is always plain import-agnostic markdown: the
`@import` directive is a Claude Code mechanism and no other tool resolves it.
Keeping the mode recorded per pair matches how a user thinks about it, while only
one branch in this module ever reads it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mdcompose.core import files, managed_block
from mdcompose.core.config import Mode
from mdcompose.core.snippets import Snippet, compose_order

IMPORT: Mode = "import"
COPY: Mode = "copy"

SEPARATOR = "\n"

Scope = Literal["agents", "claude"]


@dataclass(frozen=True, slots=True)
class Composition:
    """The content both managed blocks should hold for one selection and mode."""

    agents_block: str
    claude_block: str
    snippet_ids: tuple[str, ...]
    imports: str | None


def compose(
    selection: Sequence[Snippet],
    *,
    mode: Mode,
    import_target: str = "AGENTS.md",
) -> Composition:
    """Work out both blocks' content from one selection.

    ``import_target`` is the path CLAUDE.md points at in import mode, relative to
    CLAUDE.md itself. It is normally the AGENTS.md beside it, but a subdirectory
    CLAUDE.md may import one from elsewhere in the repository.
    """
    ordered = compose_order(selection)
    return Composition(
        agents_block=_join_bodies(item for item in ordered if item.applies_to_agents()),
        claude_block=(
            import_directive(import_target)
            if mode == IMPORT
            else _join_bodies(item for item in ordered if item.applies_to_claude())
        ),
        snippet_ids=tuple(item.id for item in ordered),
        imports=import_target if mode == IMPORT else None,
    )


def import_directive(target: str) -> str:
    """Return the import directive CLAUDE.md carries in import mode."""
    return f"@{target}\n"


def _join_bodies(selected: Iterable[Snippet]) -> str:
    """Concatenate snippet bodies with one blank line between them."""
    bodies = [files.normalize(item.body).strip("\n") for item in selected]
    present = [body for body in bodies if body]
    if not present:
        return ""
    return SEPARATOR.join(f"{body}\n" for body in present)


def apply_to_file(
    path: Path,
    block_id: str,
    content: str,
) -> bool:
    """Write one block into a file, returning whether anything changed.

    Creates the file when it does not exist. Preserves every byte outside the
    block, and preserves the file's existing line endings. Returns False when the
    result would be identical to what is already there, so a repeat run is a
    no-op rather than a rewrite.
    """
    existing = files.read_text(path) if files.path_exists(path) and path.is_file() else ""
    updated = managed_block.upsert(existing, block_id, content, path)
    if existing and files.content_equal(existing, updated):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(path, updated, line_ending=files.line_ending_for(path))
    return True
