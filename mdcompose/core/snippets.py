"""The snippet library: a flat directory of markdown files, one snippet each.

The storage format is the decision this whole module rests on. A single store,
JSON or SQLite, would give faster queries and atomic multi-snippet writes, and
would cost hand-editability, comments in metadata, clean diffs,
filename-as-identity, and, decisively, the ability to read your own conventions
without the tool that wrote them. The library is the user's own writing. Putting
it behind a format that needs mdcompose to read would make the tool a dependency
of the user's notes, which inverts the point of having a library.

So: one markdown file per snippet, YAML frontmatter then body, filename minus the
extension as the id. mdcompose writes nothing else into that directory, which is
what lets a user keep it in git or a synced folder without the tool fighting them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

import yaml

from mdcompose.core import files
from mdcompose.core.exit_codes import AttentionError

SNIPPET_SUFFIX = ".md"

AppliesTo = Literal["agents", "claude", "both"]
DEFAULT_APPLIES_TO: AppliesTo = "both"

_APPLIES_TO_VALUES: tuple[str, ...] = get_args(AppliesTo)
_FRONTMATTER_FENCE = "---"
_VALID_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Unrecognized frontmatter fields are simply not read, so a user experimenting
# with an extra field is never blocked. There is deliberately no list of known
# fields to check against: a wrong-typed known field is fatal, an unknown one is
# ignored, and neither needs an allowlist.


@dataclass(frozen=True, slots=True)
class Snippet:
    """One snippet: its id, its metadata, and its body.

    The id is derived from the filename and is never stored in the file, so the
    two cannot drift apart. Renaming the file renames the snippet.
    """

    id: str
    body: str
    title: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    applies_to: AppliesTo = DEFAULT_APPLIES_TO
    stack_signals: tuple[str, ...] = ()
    category: str | None = None
    order: int | None = None
    source_path: str | None = None
    source_heading: str | None = None
    imported_at: str | None = None
    path: Path | None = None

    @property
    def display_name(self) -> str:
        """What to show a person. The title if there is one, else the id."""
        return self.id if self.title is None else self.title

    def applies_to_agents(self) -> bool:
        return self.applies_to in {"agents", DEFAULT_APPLIES_TO}

    def applies_to_claude(self) -> bool:
        return self.applies_to in {"claude", DEFAULT_APPLIES_TO}

    def matches_tag(self, tag: str) -> bool:
        return tag in self.tags

    def matches_category(self, category: str) -> bool:
        return self.category == category


def id_for(path: Path) -> str:
    """Return the snippet id a file path implies."""
    return path.stem


def is_snippet_file(path: Path) -> bool:
    """Return whether an entry in the library is a snippet.

    Anything that is not a regular markdown file is not a snippet and is left
    entirely alone: a subdirectory, a symlink mdcompose did not create, a `.git`
    directory, a stray text file.
    """
    return path.is_file() and path.suffix == SNIPPET_SUFFIX


def validate_id(candidate: str) -> str:
    """Return the id unchanged, or refuse a value unusable as a filename."""
    if _VALID_ID.match(candidate) is None or candidate != Path(candidate).name:
        raise AttentionError(
            f"'{candidate}' is not usable as a snippet name. Use letters, digits, "
            "dots, dashes and underscores, and no path separators."
        )
    return candidate


def parse(text: str, snippet_id: str, *, path: Path | None = None) -> Snippet:
    """Parse one snippet from its file contents.

    A file with no frontmatter is still a valid snippet: the whole text is the
    body and every field takes its default. That keeps the barrier to writing a
    snippet as low as writing markdown.
    """
    metadata, body = _split_frontmatter(text, snippet_id)
    return Snippet(
        id=snippet_id,
        body=body,
        title=_as_str(metadata, "title", snippet_id),
        description=_as_str(metadata, "description", snippet_id),
        tags=_as_str_list(metadata, "tags", snippet_id),
        applies_to=_as_applies_to(metadata, snippet_id),
        stack_signals=_as_str_list(metadata, "stack_signals", snippet_id),
        category=_as_str(metadata, "category", snippet_id),
        order=_as_int(metadata, "order", snippet_id),
        source_path=_as_str(metadata, "source_path", snippet_id),
        source_heading=_as_str(metadata, "source_heading", snippet_id),
        imported_at=_as_str(metadata, "imported_at", snippet_id),
        path=path,
    )


def _split_frontmatter(text: str, snippet_id: str) -> tuple[Mapping[str, object], str]:
    """Separate a leading YAML frontmatter block from the markdown body."""
    normalized = files.normalize(text)
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, normalized

    for index in range(1, len(lines)):
        if lines[index].strip() != _FRONTMATTER_FENCE:
            continue
        block = "\n".join(lines[1:index])
        body = "\n".join(lines[index + 1 :])
        return _parse_yaml(block, snippet_id), body.lstrip("\n")

    raise AttentionError(
        f"snippet '{snippet_id}': the frontmatter block is opened but never closed"
    )


def _parse_yaml(block: str, snippet_id: str) -> Mapping[str, object]:
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise AttentionError(
            f"snippet '{snippet_id}': frontmatter is not valid YAML ({exc})"
        ) from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise AttentionError(f"snippet '{snippet_id}': frontmatter must be a mapping of fields")
    return loaded


def _as_str(metadata: Mapping[str, object], key: str, snippet_id: str) -> str | None:
    if key not in metadata or metadata[key] is None:
        return None
    value = metadata[key]
    if not isinstance(value, str):
        raise AttentionError(f"snippet '{snippet_id}': '{key}' must be a string")
    return value


def _as_int(metadata: Mapping[str, object], key: str, snippet_id: str) -> int | None:
    if key not in metadata or metadata[key] is None:
        return None
    value = metadata[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AttentionError(f"snippet '{snippet_id}': '{key}' must be a whole number")
    return value


def _as_str_list(metadata: Mapping[str, object], key: str, snippet_id: str) -> tuple[str, ...]:
    if key not in metadata or metadata[key] is None:
        return ()
    value = metadata[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AttentionError(f"snippet '{snippet_id}': '{key}' must be a list of strings")
    return tuple(value)


def _as_applies_to(metadata: Mapping[str, object], snippet_id: str) -> AppliesTo:
    value = _as_str(metadata, "applies_to", snippet_id)
    if value is None:
        return DEFAULT_APPLIES_TO
    if value not in _APPLIES_TO_VALUES:
        allowed = ", ".join(f"'{item}'" for item in _APPLIES_TO_VALUES)
        raise AttentionError(
            f"snippet '{snippet_id}': 'applies_to' must be one of {allowed}, found '{value}'"
        )
    return value  # type: ignore[return-value]


def read(path: Path) -> Snippet:
    """Read and parse one snippet file."""
    return parse(files.read_text(path), id_for(path), path=path)


def load_library(library: Path) -> tuple[Snippet, ...]:
    """Read every snippet in the library, sorted by id.

    An absent directory is an empty library, not an error, and is not created.
    Entries that are not markdown files are skipped in silence: they belong to
    the user, and reporting them would make a git checkout look broken.
    """
    if not files.path_exists(library) or not library.is_dir():
        return ()
    return tuple(
        read(path) for path in sorted(library.iterdir(), key=lambda item: item.name)
        if is_snippet_file(path)
    )


def path_for(library: Path, snippet_id: str) -> Path:
    """Return where a snippet with this id lives, without touching the disk."""
    return library / f"{validate_id(snippet_id)}{SNIPPET_SUFFIX}"


def find(snippets: Iterable[Snippet], snippet_id: str) -> Snippet | None:
    """Return the snippet with this id, or None."""
    for snippet in snippets:
        if snippet.id == snippet_id:
            return snippet
    return None


def filter_snippets(
    snippets: Iterable[Snippet],
    *,
    tag: str | None = None,
    category: str | None = None,
) -> tuple[Snippet, ...]:
    """Narrow a set of snippets. Every filter supplied must match.

    Filters narrow rather than widen, so supplying two of them cannot return
    more than supplying one.
    """
    return tuple(
        snippet
        for snippet in snippets
        if (tag is None or snippet.matches_tag(tag))
        and (category is None or snippet.matches_category(category))
    )


def compose_order(selection: Sequence[Snippet]) -> tuple[Snippet, ...]:
    """Return the selection in the order it should be composed.

    Snippets carrying an ``order`` come first, ascending. Everything else keeps
    the order it was selected in.

    Unordered snippets sort last rather than at some default value, so adding an
    ``order`` to one snippet cannot silently reshuffle every other snippet in the
    file. A tie keeps selection order, which makes the result predictable without
    the user having to reason about the sort.
    """
    ordered = [
        (snippet.order, index, snippet)
        for index, snippet in enumerate(selection)
        if snippet.order is not None
    ]
    unordered = [snippet for snippet in selection if snippet.order is None]
    ordered.sort(key=lambda item: (item[0], item[1]))
    return tuple([item[2] for item in ordered] + unordered)


def render(snippet: Snippet) -> str:
    """Render a snippet back to file contents: frontmatter, then body.

    Only fields that carry a value are written, so a minimal snippet stays
    minimal rather than growing a wall of nulls.
    """
    metadata: dict[str, object] = {}
    if snippet.title is not None:
        metadata["title"] = snippet.title
    if snippet.description is not None:
        metadata["description"] = snippet.description
    if snippet.tags:
        metadata["tags"] = list(snippet.tags)
    if snippet.applies_to != DEFAULT_APPLIES_TO:
        metadata["applies_to"] = snippet.applies_to
    if snippet.stack_signals:
        metadata["stack_signals"] = list(snippet.stack_signals)
    if snippet.category is not None:
        metadata["category"] = snippet.category
    if snippet.order is not None:
        metadata["order"] = snippet.order
    if snippet.source_path is not None:
        metadata["source_path"] = snippet.source_path
    if snippet.source_heading is not None:
        metadata["source_heading"] = snippet.source_heading
    if snippet.imported_at is not None:
        metadata["imported_at"] = snippet.imported_at

    if not metadata:
        return snippet.body
    block = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"{_FRONTMATTER_FENCE}\n{block}{_FRONTMATTER_FENCE}\n\n{snippet.body}"


def write(library: Path, snippet: Snippet) -> Path:
    """Write a snippet into the library, creating the directory if needed.

    The only thing mdcompose ever writes into the library is a snippet file. A
    symlink at the target is refused rather than followed: it is an entry
    mdcompose did not create, and writing through it would land the content
    outside the library.
    """
    target = path_for(library, snippet.id)
    if target.is_symlink():
        raise AttentionError(f"{target}: refusing to write a snippet through a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(target, render(snippet), line_ending=files.line_ending_for(target))
    return target


@dataclass(frozen=True, slots=True)
class LibraryView:
    """The library as one value, so a command reads the disk once."""

    directory: Path
    snippets: tuple[Snippet, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not self.snippets

    @property
    def exists(self) -> bool:
        return files.path_exists(self.directory)

    def find(self, snippet_id: str) -> Snippet | None:
        return find(self.snippets, snippet_id)

    def require(self, snippet_id: str) -> Snippet:
        """Return the named snippet, or refuse with the id named."""
        snippet = self.find(snippet_id)
        if snippet is None:
            raise AttentionError(
                f"no snippet '{snippet_id}' in the library at {self.directory.as_posix()}"
            )
        return snippet


def view(library: Path) -> LibraryView:
    """Read the library once and return it as a value."""
    return LibraryView(directory=library, snippets=load_library(library))
