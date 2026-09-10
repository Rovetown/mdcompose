"""Choosing sections to import and writing them into a project file.

The selection interface is a plain callable, the same shape as the snippet
picker's: core decides *what* can be chosen and in what order the result is
applied, the CLI supplies the interaction, and a test supplies a stub. That is
what keeps the picker library out of the core layer.

Imported content is always appended at the end of the target file, which is
outside every managed block. `init` regenerates only the block's content, so
anything appended here survives every later run untouched and untracked: it is a
one-off paste, and the way to make it managed is `--save-as-snippet`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal

from mdcompose.core import files, snippets
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.sections import Section
from mdcompose.core.snippets import LibraryView, Snippet

#: What saving a snippet under a given id would do against the current library.
SnippetStatus = Literal["new", "identical", "collision"]
NEW: SnippetStatus = "new"
IDENTICAL: SnippetStatus = "identical"
COLLISION: SnippetStatus = "collision"

#: How to resolve a collision: replace the library copy, keep it, or save under
#: a different id.
CollisionChoice = Literal["keep", "overwrite", "rename"]
KEEP: CollisionChoice = "keep"
OVERWRITE: CollisionChoice = "overwrite"
RENAME: CollisionChoice = "rename"
COLLISION_CHOICES: tuple[CollisionChoice, ...] = (KEEP, OVERWRITE, RENAME)

#: Picks sections from those on offer. Given the available sections, returns the
#: chosen ones. Order and de-duplication are core's job, not the picker's.
SectionSelector = Callable[[Sequence[Section]], Sequence[Section]]


def resolve_selection(
    available: Sequence[Section],
    *,
    requested_headings: Sequence[str] | None,
    selector: SectionSelector | None,
) -> tuple[Section, ...]:
    """Work out which sections to apply, always returned in source order.

    Named headings win and skip the picker. Otherwise the picker is opened; with
    no picker and no headings there is nothing to ask with, so this refuses and
    names the flag.
    """
    if requested_headings is not None:
        return match_headings(available, requested_headings)
    if selector is None:
        raise AttentionError(
            "no section was named and there is no terminal to open the picker on. "
            "Pass --section with a heading from the source."
        )
    picked = set(selector(available))
    return tuple(section for section in available if section in picked)


def match_headings(
    available: Sequence[Section], headings: Sequence[str]
) -> tuple[Section, ...]:
    """Resolve heading names to sections in source order, naming any that miss."""
    present = {section.heading for section in available}
    missing = [name for name in headings if name not in present]
    if missing:
        listed = ", ".join(f"'{name}'" for name in missing)
        raise AttentionError(f"no section titled {listed} in the source file")
    wanted = set(headings)
    return tuple(section for section in available if section.heading in wanted)


def apply_to_target(target: Path, content: str) -> bool:
    """Append imported content to the end of the target file, outside any block.

    Creates the file when it does not exist. Everything already there, a managed
    block included, is preserved. Returns whether anything was written, which is
    always true here because appending the same content twice is a real change.
    """
    if not content.strip("\n"):
        return False
    existing = files.read_text(target) if _is_file(target) else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(target, appended(existing, content), line_ending=files.line_ending_for(target))
    return True


def appended(existing: str, content: str) -> str:
    """Return ``existing`` with ``content`` added after it, separated by a blank line.

    A pure function so a caller can show the result in a diff before it is
    written. Empty content leaves the text unchanged.
    """
    addition = content.strip("\n")
    base = files.normalize(existing)
    if not addition:
        return base
    prefix = base.rstrip("\n") + "\n\n" if base.strip() else ""
    return f"{prefix}{addition}\n"


def _is_file(path: Path) -> bool:
    return files.path_exists(path) and path.is_file()


def build_snippet(
    *,
    name: str,
    body: str,
    source_path: str,
    source_heading: str | None,
    category: str | None,
    tags: Sequence[str],
    today: str,
) -> Snippet:
    """Assemble a library snippet from extracted content and the flags given.

    ``title`` is the source heading because that is what the user would type
    anyway. ``category`` and ``tags`` have no source in the file, so they come
    only from flags. The three provenance fields record where the content came
    from; they are optional in the format and never reach composed output.
    """
    return Snippet(
        id=snippets.validate_id(name),
        body=body,
        title=source_heading,
        category=category,
        tags=tuple(tags),
        source_path=source_path,
        source_heading=source_heading,
        imported_at=today,
    )


def snippet_status(library: LibraryView, snippet: Snippet) -> SnippetStatus:
    """Whether saving this snippet is new, a no-op, or a genuine collision.

    Comparison is normalization-aware, so a library copy that differs only by
    line endings or a byte order mark counts as identical rather than as a
    collision. Only the body is compared: the frontmatter a save would write,
    provenance included, is not content the user is choosing between.
    """
    existing = library.find(snippet.id)
    if existing is None:
        return NEW
    if files.content_equal(existing.body, snippet.body):
        return IDENTICAL
    return COLLISION


def write_snippet(library: LibraryView, snippet: Snippet, *, overwrite: bool = False) -> Path:
    """Write a snippet into the library, creating the directory if absent.

    Refuses an id that is already taken unless ``overwrite`` says otherwise, so a
    collision cannot be resolved by accident.
    """
    if not overwrite and library.find(snippet.id) is not None:
        raise AttentionError(
            f"a snippet named '{snippet.id}' already exists in the library at "
            f"{library.directory.as_posix()}"
        )
    return snippets.write(library.directory, snippet)


def rename_snippet(snippet: Snippet, new_name: str) -> Snippet:
    """Return the same snippet under a new, validated id."""
    return replace(snippet, id=snippets.validate_id(new_name))
