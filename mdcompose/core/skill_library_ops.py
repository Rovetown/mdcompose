"""Operations on the skill library that a command drives: remove, adopt.

Mirrors ``library_ops.py``, not a generalization of it: a skill has no
``applies_to``, which is exactly the field `_snippet_from_manifest` reads when
reconstructing a library entry, so a shared generic layer would carry a field
that means nothing on this side. See design.md for the reasoning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mdcompose.core import files, skills
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.manifest import Manifest
from mdcompose.core.skills import Skill

Resolution = Literal["keep", "overwrite"]

KEEP: Resolution = "keep"
OVERWRITE: Resolution = "overwrite"
RESOLUTIONS: tuple[Resolution, ...] = (KEEP, OVERWRITE)

AdoptOutcome = Literal["written", "already-present", "kept", "overwritten"]


@dataclass(frozen=True, slots=True)
class Collision:
    """An embedded skill whose id already exists locally with other content."""

    skill_id: str
    embedded: str
    local: str


@dataclass(frozen=True, slots=True)
class AdoptPlan:
    """What adopting would do, worked out before anything is written."""

    to_write: tuple[Skill, ...]
    already_present: tuple[str, ...]
    collisions: tuple[Collision, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.to_write or self.already_present or self.collisions)


@dataclass(frozen=True, slots=True)
class AdoptResult:
    """What adopting actually did, per skill id."""

    outcomes: Mapping[str, AdoptOutcome]

    def ids_with(self, outcome: AdoptOutcome) -> tuple[str, ...]:
        return tuple(
            skill_id for skill_id, value in sorted(self.outcomes.items()) if value == outcome
        )


def plan_adopt(
    manifest: Manifest,
    library: skills.LibraryView,
    *,
    only: tuple[str, ...] = (),
) -> AdoptPlan:
    """Work out what adopting the manifest's embedded skills would do.

    Comparison is normalization-aware, so a skill differing from its library
    copy only by line endings or a byte order mark counts as already present
    rather than as a conflict.
    """
    if only:
        _require_known_ids(manifest, only)

    to_write: list[Skill] = []
    already_present: list[str] = []
    collisions: list[Collision] = []

    for entry in manifest.skills_in_order():
        if only and entry.id not in only:
            continue
        local = library.find(entry.id)
        if local is None:
            to_write.append(_skill_from_manifest(entry.id, entry.content))
            continue
        if files.content_equal(local.body, entry.content):
            already_present.append(entry.id)
            continue
        collisions.append(Collision(skill_id=entry.id, embedded=entry.content, local=local.body))

    return AdoptPlan(
        to_write=tuple(to_write),
        already_present=tuple(already_present),
        collisions=tuple(collisions),
    )


def _require_known_ids(manifest: Manifest, requested: tuple[str, ...]) -> None:
    known = {entry.id for entry in manifest.skills}
    unknown = sorted(set(requested) - known)
    if unknown:
        listed = ", ".join(f"'{item}'" for item in unknown)
        raise AttentionError(
            f"{manifest.source}: no embedded skill named {listed}. "
            f"Available: {', '.join(sorted(known)) or 'none'}"
        )


def _skill_from_manifest(skill_id: str, content: str) -> Skill:
    """Build a library skill from a manifest entry.

    Only what the manifest carries is set: id and content. A manifest entry
    records no descriptive metadata a user would write by hand, so the
    adopted skill starts minimal rather than with invented fields.
    """
    return Skill(id=skills.validate_id(skill_id), body=content)


def apply_adopt(
    plan: AdoptPlan,
    library_directory: Path,
    *,
    resolutions: Mapping[str, Resolution],
) -> AdoptResult:
    """Carry out an adoption plan, using the decision made for each collision.

    A collision with no decision is left alone rather than guessed at, so a
    caller that forgets to answer cannot silently overwrite a user's skill.
    """
    outcomes: dict[str, AdoptOutcome] = {}

    for skill in plan.to_write:
        skills.write(library_directory, skill)
        outcomes[skill.id] = "written"

    for skill_id in plan.already_present:
        outcomes[skill_id] = "already-present"

    for collision in plan.collisions:
        if resolutions.get(collision.skill_id, KEEP) == OVERWRITE:
            skills.write(
                library_directory,
                _skill_from_manifest(collision.skill_id, collision.embedded),
            )
            outcomes[collision.skill_id] = "overwritten"
        else:
            outcomes[collision.skill_id] = "kept"

    return AdoptResult(outcomes=outcomes)


def remove_skill(library: skills.LibraryView, skill_id: str) -> Path:
    """Delete a skill from the skill library.

    Refuses an unknown id by name. Deletes only the skill file, and never
    touches a project that already composed it: composition copies content, so
    a composed file keeps working after its source skill is gone.
    """
    skill = library.require(skill_id)
    if skill.path is None:
        raise AttentionError(f"skill '{skill_id}' has no file on disk to remove")
    skill.path.unlink()
    return skill.path


def replace_body(library: skills.LibraryView, skill_id: str, text: str) -> Path:
    """Replace a skill's file contents, validating before writing.

    The candidate is parsed first, so a supplied body with broken frontmatter
    is refused and the existing skill is left exactly as it was.
    """
    skill = library.require(skill_id)
    skills.parse(text, skill_id)
    target = skills.path_for(library.directory, skill_id)
    files.write_text(target, text, line_ending=files.line_ending_for(target))
    return skill.path if skill.path is not None else target
