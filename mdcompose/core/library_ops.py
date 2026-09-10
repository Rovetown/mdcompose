"""Operations on the snippet library that a command drives: remove, adopt.

These live in core rather than in the CLI layer because they are behavior, not
presentation. Each returns a description of what it did, and each takes the
user's decision as an argument rather than asking for it, so the CLI owns the
prompting and core owns the outcome. That is what keeps every prompt scriptable:
a flag and an answered prompt reach this code identically.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mdcompose.core import files, snippets
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.manifest import Manifest
from mdcompose.core.snippets import Snippet

Resolution = Literal["keep", "overwrite", "skip"]

KEEP: Resolution = "keep"
OVERWRITE: Resolution = "overwrite"
SKIP: Resolution = "skip"

AdoptOutcome = Literal["written", "already-present", "kept", "overwritten", "skipped"]


@dataclass(frozen=True, slots=True)
class Collision:
    """An embedded snippet whose id already exists locally with other content."""

    snippet_id: str
    embedded: str
    local: str


@dataclass(frozen=True, slots=True)
class AdoptPlan:
    """What adopting would do, worked out before anything is written.

    Deciding first and writing second means the user sees every collision up
    front instead of being asked one question per file mid-write.
    """

    to_write: tuple[Snippet, ...]
    already_present: tuple[str, ...]
    collisions: tuple[Collision, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.to_write or self.already_present or self.collisions)


@dataclass(frozen=True, slots=True)
class AdoptResult:
    """What adopting actually did, per snippet id."""

    outcomes: Mapping[str, AdoptOutcome]

    def ids_with(self, outcome: AdoptOutcome) -> tuple[str, ...]:
        return tuple(
            snippet_id for snippet_id, value in sorted(self.outcomes.items()) if value == outcome
        )


def plan_adopt(
    manifest: Manifest,
    library: snippets.LibraryView,
    *,
    only: tuple[str, ...] = (),
) -> AdoptPlan:
    """Work out what adopting the manifest's embedded snippets would do.

    Comparison is normalization-aware, so a snippet differing from its library
    copy only by line endings or a byte order mark counts as already present
    rather than as a conflict. Without that, every cross-platform checkout would
    look like a library full of collisions.
    """
    if only:
        _require_known_ids(manifest, only)

    to_write: list[Snippet] = []
    already_present: list[str] = []
    collisions: list[Collision] = []

    for entry in manifest.snippets_in_order():
        if only and entry.id not in only:
            continue
        local = library.find(entry.id)
        if local is None:
            to_write.append(_snippet_from_manifest(entry.id, entry.content, entry.applies_to))
            continue
        if files.content_equal(local.body, entry.content):
            already_present.append(entry.id)
            continue
        collisions.append(
            Collision(snippet_id=entry.id, embedded=entry.content, local=local.body)
        )

    return AdoptPlan(
        to_write=tuple(to_write),
        already_present=tuple(already_present),
        collisions=tuple(collisions),
    )


def _require_known_ids(manifest: Manifest, requested: tuple[str, ...]) -> None:
    known = {entry.id for entry in manifest.snippets}
    unknown = sorted(set(requested) - known)
    if unknown:
        listed = ", ".join(f"'{item}'" for item in unknown)
        raise AttentionError(
            f"{manifest.source}: no embedded snippet named {listed}. "
            f"Available: {', '.join(sorted(known)) or 'none'}"
        )


def _snippet_from_manifest(snippet_id: str, content: str, applies_to: str) -> Snippet:
    """Build a library snippet from a manifest entry.

    Only what the manifest carries is set. A manifest records the content and
    what it applies to, not the descriptive metadata a user would write, so the
    adopted snippet starts minimal rather than with invented fields.
    """
    resolved = (
        applies_to
        if applies_to in {"agents", "claude", snippets.DEFAULT_APPLIES_TO}
        else snippets.DEFAULT_APPLIES_TO
    )
    return Snippet(
        id=snippets.validate_id(snippet_id),
        body=content,
        applies_to=resolved,  # type: ignore[arg-type]
    )


def apply_adopt(
    plan: AdoptPlan,
    library_directory: Path,
    *,
    resolutions: Mapping[str, Resolution],
) -> AdoptResult:
    """Carry out an adoption plan, using the decision made for each collision.

    A collision with no decision is left alone rather than guessed at, so a
    caller that forgets to answer cannot silently overwrite a user's snippet.
    """
    outcomes: dict[str, AdoptOutcome] = {}

    for snippet in plan.to_write:
        snippets.write(library_directory, snippet)
        outcomes[snippet.id] = "written"

    for snippet_id in plan.already_present:
        outcomes[snippet_id] = "already-present"

    for collision in plan.collisions:
        decision = resolutions.get(collision.snippet_id, KEEP)
        if decision == OVERWRITE:
            snippets.write(
                library_directory,
                _snippet_from_manifest(
                    collision.snippet_id, collision.embedded, snippets.DEFAULT_APPLIES_TO
                ),
            )
            outcomes[collision.snippet_id] = "overwritten"
        elif decision == SKIP:
            outcomes[collision.snippet_id] = "skipped"
        else:
            outcomes[collision.snippet_id] = "kept"

    return AdoptResult(outcomes=outcomes)


def remove_snippet(library: snippets.LibraryView, snippet_id: str) -> Path:
    """Delete a snippet from the library.

    Refuses an unknown id by name. Deletes only the snippet file, and never
    touches a project that already composed it: composition copies content, so a
    composed file keeps working after its source snippet is gone.
    """
    snippet = library.require(snippet_id)
    if snippet.path is None:
        raise AttentionError(f"snippet '{snippet_id}' has no file on disk to remove")
    snippet.path.unlink()
    return snippet.path


def replace_body(library: snippets.LibraryView, snippet_id: str, text: str) -> Path:
    """Replace a snippet's file contents, validating before writing.

    The candidate is parsed first, so a supplied body with broken frontmatter is
    refused and the existing snippet is left exactly as it was.
    """
    snippet = library.require(snippet_id)
    snippets.parse(text, snippet_id)
    target = snippets.path_for(library.directory, snippet_id)
    files.write_text(target, text, line_ending=files.line_ending_for(target))
    return snippet.path if snippet.path is not None else target
